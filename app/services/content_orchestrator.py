"""
ContentOrchestrator — Pipeline AI sinh nội dung cho video tự động.

Flow: Video → Thumbnail (FFmpeg) → Gemini phân tích → Caption + Hashtags

Dùng:
    from app.services.content_orchestrator import ContentOrchestrator
    orch = ContentOrchestrator()
    result = orch.generate_caption(video_path="/path/to/video.mp4", style="affiliate")
    # → {"caption": "...", "hashtags": ["#abc", ...], "keywords": ["..."]}
"""
import subprocess
import os
import hashlib
import time
import logging
import json
import re

from app.services.gemini_rpa import GeminiRPAService
import app.config as config

logger = logging.getLogger(__name__)

# ─── Configurable paths (từ app/config.py, không hard-code) ───
THUMB_DIR = str(config.THUMB_DIR)


class ContentOrchestrator:
    """Điều phối pipeline: Video → Thumbnail → Gemini → Caption."""

    # ─── Whisper Singleton Cache (fix D: init 1 lần, reuse mãi) ───
    _whisper_model = None

    @classmethod
    def _get_whisper_model(cls):
        """Lazy-load WhisperModel 1 lần duy nhất, reuse cho tất cả requests."""
        if cls._whisper_model is None:
            from faster_whisper import WhisperModel
            model_size = config.WHISPER_MODEL_SIZE
            logger.info("Khởi tạo WhisperModel '%s' (1 lần duy nhất)...", model_size)
            t0 = time.time()
            cls._whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("WhisperModel sẵn sàng (init %.1fs)", time.time() - t0)
        return cls._whisper_model

    def __init__(self):
        self.gemini = GeminiRPAService()
        os.makedirs(THUMB_DIR, exist_ok=True)

    # ─── Helpers ───

    @staticmethod
    def _file_hash(path: str) -> str:
        """Tạo hash ngắn từ (đường dẫn + mtime) để tránh race condition / đè file."""
        mtime = str(os.path.getmtime(path))
        return hashlib.md5((path + mtime).encode()).hexdigest()

    @staticmethod
    def _run_ffmpeg(cmd: list, timeout: int = 30, label: str = "ffmpeg") -> subprocess.CompletedProcess:
        """Chạy FFmpeg/ffprobe với check=True, log stderr khi fail."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
            return result
        except subprocess.CalledProcessError as e:
            logger.error("[%s] Exit code %d. stderr: %s", label, e.returncode, (e.stderr or "")[:500])
            raise
        except subprocess.TimeoutExpired:
            logger.error("[%s] Timeout sau %ds", label, timeout)
            raise

    # ─── Fix B: 1 lệnh FFmpeg select+tile thay vì 6 lần decode ───

    def extract_keyframes_collage(self, video_path: str) -> str | None:
        """Trích 6 khung hình + ghép collage 3x2 bằng 1 lệnh FFmpeg duy nhất."""
        if not os.path.exists(video_path):
            return None

        fhash = self._file_hash(video_path)
        collage_path = os.path.join(THUMB_DIR, f"{fhash}_collage.jpg")

        # Nếu collage đã tồn tại và > 0 bytes → cache hit
        if os.path.exists(collage_path) and os.path.getsize(collage_path) > 0:
            logger.info("Collage cache hit: %s", collage_path)
            return collage_path

        t0 = time.time()

        try:
            # Lấy duration
            probe = self._run_ffmpeg(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
                timeout=10, label="ffprobe-duration"
            )
            duration = float(probe.stdout.strip())
        except Exception:
            duration = 30.0  # fallback nếu ffprobe fail

        # Tính 6 mốc thời gian phân bổ đều
        pts = [duration * p for p in [0.10, 0.25, 0.40, 0.60, 0.75, 0.90]]

        # FPS-based frame numbers (cần fps để tính)
        try:
            fps_probe = self._run_ffmpeg(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video_path],
                timeout=10, label="ffprobe-fps"
            )
            num, den = map(int, fps_probe.stdout.strip().split("/"))
            fps = num / den
        except Exception:
            fps = 30.0

        frame_nums = [int(pt * fps) for pt in pts]

        # 1 lệnh FFmpeg: select 6 frame + tile 3x2
        select_expr = "+".join([f"eq(n\\,{n})" for n in frame_nums])
        filter_str = f"select='{select_expr}',scale=400:-1,tile=3x2"

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", filter_str,
            "-frames:v", "1",
            "-q:v", "2",
            collage_path
        ]

        try:
            self._run_ffmpeg(cmd, timeout=60, label="ffmpeg-collage")
        except Exception as e:
            logger.error("FFmpeg Collage lỗi: %s", e)
            return None

        # Validate output
        if not os.path.exists(collage_path) or os.path.getsize(collage_path) == 0:
            logger.error("Collage file rỗng hoặc không tồn tại: %s", collage_path)
            return None

        logger.info("Collage OK (%.1fs): %s", time.time() - t0, collage_path)
        return collage_path

    # ─── Fix D: Whisper singleton + cleanup try/finally ───

    def extract_transcript(self, video_path: str) -> str:
        """Trích xuất Audio → Whisper STT. Model cached singleton."""
        fhash = self._file_hash(video_path)
        audio_path = os.path.join(THUMB_DIR, f"{fhash}.mp3")

        try:
            self._run_ffmpeg(
                ["ffmpeg", "-y", "-i", video_path, "-q:a", "0", "-map", "a", audio_path],
                timeout=15, label="ffmpeg-audio"
            )
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                return ""  # Video không có audio track
        except Exception:
            return ""

        try:
            model = self._get_whisper_model()
            t0 = time.time()
            logger.info("Chạy Whisper '%s' bóc tách lời nói...", config.WHISPER_MODEL_SIZE)
            segments, _ = model.transcribe(audio_path, beam_size=5)
            text = " ".join([seg.text for seg in segments])
            logger.info("Whisper xong (%.1fs): %d ký tự", time.time() - t0, len(text))
            return text.strip()
        except Exception as e:
            logger.error("Lỗi Whisper STT: %s", e)
            return ""
        finally:
            # Luôn cleanup mp3 tạm, kể cả khi Whisper crash (fix E)
            try:
                os.remove(audio_path)
            except OSError:
                pass

    # ─── Generate Caption (Pipeline chính) ───

    def generate_caption(self, video_path: str, style: str = "general", context: str = "") -> dict:
        """Pipeline Multimodal Decomposition: (Collage + Transcript) → Gemini → Caption."""
        result = {"caption": "", "hashtags": [], "keywords": []}

        if not os.path.exists(video_path):
            logger.error("File media không tồn tại: %s", video_path)
            return result

        ext = os.path.splitext(video_path)[1].lower()
        is_image = ext in ['.jpg', '.jpeg', '.png']

        if is_image:
            logger.info("Bước 1/3: Đầu vào là Ảnh, bỏ qua tạo Collage và Transcript...")
            target_image = video_path
            
            # Thay đổi chữ BÁN HÀNG tương ứng với style
            intro_action = "viết CAPTION BÁN HÀNG" if style == "sales" else "viết CAPTION"
            prompt_intro = f"Hãy phân tích Hình ảnh được cung cấp để {intro_action}. Chú ý đọc và hiểu các Text/Chữ có sẵn trong ảnh, tập trung vào trọng tâm sản phẩm."
        else:
            logger.info("Bước 1/3: Đầu vào là Video, trích xuất 6 khung hình Collage...")
            target_image = self.extract_keyframes_collage(video_path)
            if not target_image:
                logger.error("Không thể tạo hình ảnh Collage đại diện từ Video!")
                return result

            logger.info("Bước 2/3: Chạy AI Whisper bóc tách âm thanh sang Text...")
            transcript = self.extract_transcript(video_path)
            logger.info("Transcript hoàn thành: %s ký tự", len(transcript))

            # Truncate transcript to avoid diluting Gemini context
            max_tlen = config.MAX_TRANSCRIPT_LENGTH
            if len(transcript) > max_tlen:
                transcript = transcript[:max_tlen].rsplit(" ", 1)[0]
                logger.info("Transcript cắt ngắn còn %d ký tự (max %d)", len(transcript), max_tlen)

            intro_action = "viết CAPTION BÁN HÀNG" if style == "sales" else "viết CAPTION"
            prompt_intro = f"""Hãy phân tích Hình ảnh (6 khung hình lưới 2x3 trích từ Video) và kết hợp với Audio Transcript đính kèm bên dưới để {intro_action}.
CHÚ Ý QUAN TRỌNG: TRONG ẢNH CÓ THỂ CÓ CHỮ (SUBTITLE). BẠN NÊN ƯU TIÊN ĐỌC CÁC CHỮ ĐÓ.

Audio Transcript (có thể bắt chữ bị sai do giọng AI), hãy tham khảo kết hợp với Hình ảnh:
"{transcript if transcript else '(Video không có giọng nói)'}" """

        # Define dynamic sections based on style
        # Default assume NO sales for non-sales styles
        sales_rules = ""
        seo_rules = ""

        if style == "sales":
            style_guide = "tập trung vào lợi ích sản phẩm, kích thích mua hàng, có CTA rõ ràng"
            tone_of_voice = "Cân bằng sự thân thiện và tính cụ thể. Có cấu trúc review rõ (Mở - Trải nghiệm thực - Kết). Xoáy sâu vào Pain-point (nỗi đau) của khách hàng để chốt sale."
            formatting_rules = """- TIÊU CHÍ: Viết khoảng 4-5 dòng, tập trung nêu bật lợi ích và đẩy cảm xúc mua hàng.
- Tiêu đề (Hook) in hoa hoặc kẹp giữa biểu tượng (Ví dụ: 🔥 [TIÊU ĐỀ] 🔥) để dừng ngón tay người dùng.
- Xuống dòng thoáng mắt (mỗi câu 1 dòng).
- Sử dụng ít Emoji (2-4 cái cho cả bài), đúng ngữ cảnh."""
            sales_rules = """[ACCESSTRADE CONVERSION TIPS (LAST-CLICK OPTIMIZED)]
- Tạo hiệu ứng FOMO ở cuối bài: Nhấn mạnh số lượng giới hạn, ưu đãi kết thúc trong ngày, voucher xịn.
- Kêu gọi hành động (CTA): Kết thúc caption bằng câu kêu gọi bình luận từ khóa liên quan đến sản phẩm. AI tự phân tích sản phẩm và chọn từ khóa phù hợp nhất. Ví dụ: 💬 Bình luận "[TỪ KHÓA SẢN PHẨM]" để nhận link ưu đãi!
- TUYỆT ĐỐI KHÔNG chèn link URL vào trong caption. Chỉ kêu gọi bình luận từ khóa."""
            seo_rules = """[SEO OPTIMIZATION]
- Chèn khéo léo 2-3 từ khóa tìm kiếm (search volume cao) trực tiếp vào tự nhiên trong ngữ cảnh của câu, thay vì chỉ nhồi nhét ở cuối bài.
- Sử dụng các cụm từ khóa mở rộng (long-tail keywords) mà khách hàng thường gõ khi tìm giải pháp cho vấn đề của họ."""

        elif style == "short":
            style_guide = "cực kỳ ngắn gọn, gây tò mò tức thì, độ vọt cao. KHÔNG LÀM DÀI DÒNG QUẢNG CÁO BÁN HÀNG."
            tone_of_voice = "Nhịp siêu nhanh, thẳng thắn, không giải thích dài dòng. Dứt khoát và gợi sự tò mò mạnh mẽ."
            formatting_rules = """- TIÊU CHÍ TỐI THƯỢNG: CỰC KỲ NGẮN GỌN. Người dùng lướt Reel/Shorts không thích đọc dài.
- Giữ bài viết ĐÚNG 1-2 dòng (dưới 100 ký tự). Đi thẳng vào trọng tâm, loại bỏ mọi từ ngữ thừa thãi.
- Chỉ cần một câu nói vu vơ, hài hước nảy ra từ video. KHÔNG CẦN CHỐT SALE. Tuyệt đối không viết lan man."""

        elif style == "daily":
            style_guide = "đời thường, tâm sự, kể chuyện, mộc mạc. TUYỆT ĐỐI KHÔNG BÁN HÀNG."
            tone_of_voice = "Như một người bạn đang tâm sự mỏng, chia sẻ câu chuyện hàng ngày. Giọng điệu chân thành, gần gũi, tuyệt đối KHÔNG mang hơi hướm quảng cáo phô trương."
            formatting_rules = """- TIÊU CHÍ: Kể chuyện (Storytelling) nhẹ nhàng, mộc mạc.
- Khoảng 3-5 dòng, hành văn tự nhiên như văn nói.
- Hạn chế tối đa dùng icon/emoji loè loẹt.
- Không cần in hoa tiêu đề. Cứ viết tự nhiên như đang viết status cá nhân.
- TUYỆT ĐỐI KHÔNG DÙNG KÊU GỌI HÀNH ĐỘNG MUA HÀNG HAY CMT."""

        elif style == "humor":
            style_guide = "hài hước, châm biếm, bắt trend mạng xã hội. CHỈ GIẢI TRÍ, KHÔNG BÁN HÀNG."
            tone_of_voice = "Giọng Gen Z, dí dỏm, lầy lội, dùng từ ngữ trending mạng xã hội, mang tính giải trí cao."
            formatting_rules = """- TIÊU CHÍ: Giải trí, gây cười, đọc xong là muốn share/tag bạn bè.
- Viết khoảng 2-4 dòng. Cấu trúc punchline (câu chốt bất ngờ).
- Dùng nhiều emoji lầy lội (😂, 🤡, 💀, 💅).
- TUYỆT ĐỐI KHÔNG CHỐT SALE HAY KÊU GỌI ĐỂ LẠI BÌNH LUẬN XIN LINK."""

        else: # default fallback
            style_guide = "ngắn gọn, hấp dẫn"
            tone_of_voice = "Ngắn gọn, rành mạch, không sáo rỗng."
            formatting_rules = """- TIÊU CHÍ TỐI THƯỢNG: CỰC KỲ NGẮN GỌN.
- Giữ bài viết chỉ khoảng 3-4 dòng (150-250 ký tự). Đi thẳng vào trọng tâm.
- Xuống dòng thoáng mắt (mỗi câu 1 dòng)."""

        # Bóc tách Tiêu đề gốc nạp vào Context nếu có
        import re
        viral_title_match = re.search(r'### ORIGINAL_VIRAL_TITLE:\s*(.*?)\s*###', context)
        viral_title = viral_title_match.group(1) if viral_title_match else ""

        # Bơm Tiêu đề gốc vào prompt_intro
        if viral_title:
            prompt_intro += f"\n\n**[💡 QUAN TRỌNG: CẢM HỨNG VIRAL TỪ TIÊU ĐỀ GỐC CỦA VIDEO]**\n" \
                            f"Video này từng lọt top trending nhờ tiêu đề: \"{viral_title}\".\n" \
                            f"Hãy bám sát và biến tấu nội dung dựa trên ý chính của tiêu đề này (phóng đại thêm mức độ hấp dẫn, nhưng không copy y hệt)."
            
        context_block = f"\n\n[INPUT VARIABLES]\n- Tên/Loại sản phẩm: Sản phẩm tương ứng trong ảnh/video\n- Phong cách/Tệp KH mục tiêu: {style_guide}"

        # ─── Fix G: Prompt placeholder trung tính, tránh ám thị domain sai ───
        mega_prompt = f"""# MEGA PROMPT: CHUYÊN GIA CONTENT FACEBOOK ADS & ACCESSTRADE

[ROLE]
Bạn là một Chuyên gia Digital Marketing & Copywriter thực chiến tại Việt Nam lọt top 1% trong mảng Facebook Ads và Affiliate (Accesstrade). Nhiệm vụ của bạn là viết caption bán hàng, review sản phẩm hoặc kịch bản video ngắn cực kỳ thu hút, nhắm góc nhìn sâu sắc, tối ưu tỷ lệ chuyển đổi (CVR) và tuân thủ tuyệt đối quy định của Meta.

[CONTEXT & MISSION]
{prompt_intro}

[TARGET AUDIENCE TONE OF VOICE]
{tone_of_voice}

[FACEBOOK ADS COMPLIANCE & BEST PRACTICES]
- TUYỆT ĐỐI KHÔNG dùng từ ngữ quy chụp thuộc tính cá nhân (Ví dụ: CẤM nói "Bạn đang bị mụn?", "Bạn đang béo?"). Hãy chuyển sang góc nhìn khách quan (Ví dụ: "Giải quyết tình trạng mụn...", "Mẹo giúp vóc dáng thon gọn...").
- TUYỆT ĐỐI KHÔNG đưa ra các cam kết tuyệt đối, sai sự thật (đặc biệt mảng Sức khỏe, Tài chính - YMYL).

{sales_rules}

{seo_rules}

[FORMATTING RULES]
{formatting_rules}
"""

        output_rules = f"""[OUTPUT INSTRUCTIONS]
BẠN THỰC THI NHIỆM VỤ NÀY NHƯ MỘT API TRẢ VỀ DỮ LIỆU THUẦN TÚY. KHÔNG DẠNG TRÒ CHUYỆN. KHÔNG MÔ TẢ. KHÔNG CHÀO HỎI. KHÔNG GIẢI TRÌNH.
Tuyệt đối KHÔNG ĐƯA RA CÁC LỰA CHỌN (Option 1, Option 2...). CHỈ VIẾT DUY NHẤT 1 BÀI HOÀN CHỈNH TỐT NHẤT. Bắt đầu viết ngay lập tức bằng JSON.

[GIỚI HẠN ĐỘ DÀI]
- Caption CỰC KỲ NGẮN, lý tưởng từ 150 đến 250 ký tự. KHÔNG ĐƯỢC vượt quá {{config.MAX_CAPTION_LENGTH}} ký tự. Càng ngắn gọn, súc tích càng tốt.
- Hashtags: 3 đến {config.MAX_HASHTAGS} hashtags.
- Keywords: 3 đến {config.MAX_KEYWORDS} keywords.

YÊU CẦU ĐẦU RA (BẮT BUỘC TRẢ VỀ CHÍNH XÁC ĐỊNH DẠNG JSON SAU, KHÔNG THÊM BẤT KỲ CHỮ NÀO BÊN NGOÀI KHỐI JSON):
```json
{{{{
  "caption": "điền nội dung caption phù hợp với quy tắc ở trên vào đây",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],
  "keywords": ["keyword 1", "keyword 2", "keyword 3"]
}}}}
```
"""

        prompt = mega_prompt + "\n\n" + context_block + "\n\n" + output_rules

        logger.info("Bước 3/3: Bắn Prompt và Ảnh lên Gemini RPA...")
        t0 = time.time()
        response = self.gemini.ask_with_file(prompt, target_image)
        logger.info("Gemini RPA xong (%.1fs)", time.time() - t0)

        if not response:
            logger.error("Gemini không phản hồi")
            return result

        result = self._parse_response(response)

        # Triệt để: nếu Gemini không trả đúng JSON schema → ép 1 vòng "self-repair" (không re-upload file).
        # Điều kiện: response không hề chứa dấu hiệu JSON keys, hoặc parse ra caption rỗng.
        looks_like_json = ("```json" in response) or ('"caption"' in response and '"hashtags"' in response)
        if (not looks_like_json) or (not (result.get("caption") or "").strip()):
            try:
                repair_prompt = f"""Bạn vừa trả lời KHÔNG đúng định dạng. Hãy CHUYỂN nội dung dưới đây thành JSON đúng schema.

YÊU CẦU:
- CHỈ TRẢ VỀ DUY NHẤT JSON (không markdown, không giải thích, không text bên ngoài).
- Schema:
{{
  "caption": "string",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "keywords": ["kw1", "kw2", "kw3"]
}}
- Caption ngắn gọn, không vượt quá {getattr(config, "MAX_CAPTION_LENGTH", 300)} ký tự.

NỘI DUNG CẦN CHUYỂN:
\"\"\"{response}\"\"\""""
                t1 = time.time()
                repaired = self.gemini.ask(repair_prompt)
                logger.info("Self-repair JSON xong (%.1fs)", time.time() - t1)
                if repaired:
                    repaired_result = self._parse_response(repaired)
                    if (repaired_result.get("caption") or "").strip():
                        result = repaired_result
            except Exception as e:
                logger.warning("Self-repair JSON failed: %s", e)
        logger.info("Hoàn tất: %s...", result["caption"][:50] if result["caption"] else "(empty)")
        return result

    def generate_comments(self, keywords: list, count: int = 5) -> list:
        """Sinh comment affiliate dựa trên keywords."""
        kw_str = ", ".join(keywords[:5])
        prompt = f"""Viết {count} comment ngắn (tiếng Việt) cho video Facebook Reels về: {kw_str}.

Yêu cầu:
- Mỗi comment 1-2 câu, tự nhiên như người thật
- Không spam, không quá quảng cáo
- Đa dạng giọng điệu (hỏi, khen, chia sẻ)

Trả lời mỗi comment trên 1 dòng, đánh số 1. 2. 3. ..."""

        response = self.gemini.ask(prompt)
        if not response:
            return []

        # Parse: tìm các dòng đánh số
        comments = []
        for line in response.split("\n"):
            line = line.strip()
            match = re.match(r'^\d+[\.\\)]\s*(.+)', line)
            if match:
                comments.append(match.group(1).strip())

        return comments[:count]

    # ─── Fix F: Robust JSON Parser + Schema Validation ───

    def _parse_response(self, text: str) -> dict:
        """Parse response Gemini thành dict chuẩn — multi-layer: JSON → repair → regex."""
        logger.info("=========== RAW GEMINI RESPONSE ===========")
        logger.info(text)
        logger.info("===========================================")

        result = {"caption": "", "hashtags": [], "keywords": []}

        # Layer 1: Tìm khối JSON trong markdown ```json ... ```
        json_match = re.search(r'```json\s*\n(.*?)\n\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text  # Fallback: toàn bộ text

        # Layer 2: Tìm outermost { ... } rồi json.loads
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx != -1 and end_idx != -1:
            raw_json = json_str[start_idx:end_idx + 1]

            # 2a: Thử parse thẳng
            data = self._try_json_loads(raw_json)

            # 2b: Nếu fail → thử repair nhẹ
            if data is None:
                repaired = self._repair_json(raw_json)
                data = self._try_json_loads(repaired)

            if data is not None:
                result = self._validate_schema(data)
                return result

        # Layer 3: Regex fallback cho từng field (hỗ trợ escaped quotes + multiline)
        logger.warning("JSON parse thất bại. Dùng Regex Fallback...")

        # Caption: lấy value sau "caption": "..." (hỗ trợ escaped quotes)
        cap_match = re.search(r'"caption"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        if cap_match:
            result["caption"] = cap_match.group(1).replace('\\"', '"').replace('\\n', '\n')

        # Hashtags
        ht_match = re.search(r'"hashtags"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if ht_match:
            result["hashtags"] = re.findall(r'"([^"]+)"', ht_match.group(1))

        # Keywords
        kw_match = re.search(r'"keywords"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if kw_match:
            result["keywords"] = re.findall(r'"([^"]+)"', kw_match.group(1))

        # Layer 4: Nếu Gemini không trả JSON (hay gặp) → rút caption từ plain text
        if not result.get("caption"):
            # Ưu tiên các dòng kiểu "Headline:" / "Caption:" nếu có
            lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
            pick = ""
            for ln in lines:
                m = re.match(r"^(headline|caption)\s*:\s*(.+)$", ln, flags=re.IGNORECASE)
                if m and m.group(2).strip():
                    pick = m.group(2).strip()
                    break
            if not pick and lines:
                pick = lines[0]

            # Fallback hashtags từ text (#tag)
            if not result.get("hashtags"):
                tags = re.findall(r"(#\w+)", text or "")
                if tags:
                    # Deduplicate, keep order, enforce limit later in schema validation
                    seen = set()
                    uniq = []
                    for t in tags:
                        tl = t.lower()
                        if tl in seen:
                            continue
                        seen.add(tl)
                        uniq.append(t)
                    result["hashtags"] = uniq

            # Enforce length hard cap here to avoid overlong captions
            try:
                max_len = int(getattr(config, "MAX_CAPTION_LENGTH", 300))
            except Exception:
                max_len = 300
            result["caption"] = (pick or "").strip()[:max_len]

        result = self._validate_schema(result)
        return result

    @staticmethod
    def _try_json_loads(raw: str) -> dict | None:
        """Thử json.loads, trả None nếu fail."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("json.loads fail: %s", e)
        return None

    @staticmethod
    def _repair_json(raw: str) -> str:
        """Sửa nhẹ JSON phổ biến: trailing comma, single quotes, ..."""
        repaired = raw
        # Xóa trailing commas trước } hoặc ]
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
        # Thay single quotes → double quotes (cẩn thận với apostrophes)
        if '"' not in repaired and "'" in repaired:
            repaired = repaired.replace("'", '"')
        return repaired

    @staticmethod
    def _validate_schema(data: dict) -> dict:
        """Validate + normalize output schema."""
        result = {"caption": "", "hashtags": [], "keywords": []}

        # Caption: phải là string
        caption = data.get("caption", "")
        if isinstance(caption, str):
            result["caption"] = caption.strip()
        elif isinstance(caption, list):
            result["caption"] = "\n".join(str(c) for c in caption).strip()

        # Hashtags: phải là list[str], auto-fix thiếu #, deduplicate, enforce limit
        hashtags = data.get("hashtags", [])
        if isinstance(hashtags, list):
            clean = []
            seen = set()
            for h in hashtags:
                h = str(h).strip()
                if not h:
                    continue
                if not h.startswith("#"):
                    h = "#" + h
                h_lower = h.lower()
                if h_lower not in seen:
                    seen.add(h_lower)
                    clean.append(h)
            result["hashtags"] = clean[:config.MAX_HASHTAGS]

        # Keywords: phải là list[str], enforce limit
        keywords = data.get("keywords", [])
        if isinstance(keywords, list):
            result["keywords"] = [str(k).strip() for k in keywords if str(k).strip()][:config.MAX_KEYWORDS]

        # Triệt để: nếu Gemini không trả keywords/hashtags → tự sinh tối thiểu từ caption
        caption_src = result.get("caption", "")
        if caption_src:
            if not result["keywords"]:
                stop = {
                    # vi
                    "và","là","của","cho","với","một","những","các","đang","đã","sẽ","thì","lại","này","đó",
                    "khi","nếu","vì","từ","đến","trong","ngoài","trên","dưới","còn","rồi","mình","bạn","anh","chị",
                    "em","tụi","chúng","ta","tôi","nó","họ","đây","kia","ấy","nha","nhé","ạ","ơi",
                }
                # lấy token đơn giản (chữ/số/underscore), ưu tiên từ dài
                toks = re.findall(r"[0-9A-Za-zÀ-ỹ_]+", caption_src, flags=re.UNICODE)
                cleaned = []
                seen = set()
                for t in toks:
                    w = t.strip().lower()
                    if len(w) < 4:
                        continue
                    if w in stop:
                        continue
                    if w in seen:
                        continue
                    seen.add(w)
                    cleaned.append(t.strip())
                    if len(cleaned) >= config.MAX_KEYWORDS:
                        break
                result["keywords"] = cleaned

            if not result["hashtags"] and result["keywords"]:
                tags = []
                seen = set()
                for kw in result["keywords"]:
                    # hashtag: bỏ space, giữ chữ/số/underscore
                    slug = re.sub(r"[^0-9A-Za-zÀ-ỹ_]+", "", kw, flags=re.UNICODE)
                    if not slug:
                        continue
                    tag = "#" + slug
                    tl = tag.lower()
                    if tl in seen:
                        continue
                    seen.add(tl)
                    tags.append(tag)
                    if len(tags) >= config.MAX_HASHTAGS:
                        break
                result["hashtags"] = tags

        return result
