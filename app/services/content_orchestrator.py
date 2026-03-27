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
import math

from app.services.gemini_rpa import GeminiRPAService
import app.config as config

logger = logging.getLogger(__name__)

# ─── Configurable paths (từ app/config.py, không hard-code) ───
THUMB_DIR = str(config.THUMB_DIR)


class OutputContractViolation(Exception):
    """Gemini did not return a valid JSON caption schema after repair attempts."""
    pass


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

        # Nếu file không có stream video (ví dụ bị nhãn .mp4 nhưng thực chất chỉ có audio)
        # thì không thể tạo collage → trả None để pipeline fallback sang text-only.
        try:
            has_video = self._run_ffmpeg(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                timeout=10,
                label="ffprobe-has-video",
            )
            if not (has_video.stdout or "").strip():
                logger.warning("No video stream detected: %s", video_path)
                return None
        except Exception:
            logger.warning("No video stream detected (ffprobe fail): %s", video_path)
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

        total_frames = 0
        try:
            # nb_read_frames thường chính xác hơn nếu ffprobe hỗ trợ codec này
            nb_probe = self._run_ffmpeg(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-count_frames",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_read_frames",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                timeout=10, label="ffprobe-fps"
            )
            nb_txt = (nb_probe.stdout or "").strip()
            total_frames = int(nb_txt) if nb_txt.isdigit() else 0
        except Exception:
            total_frames = 0

        # Nếu không có nb_frames, ước lượng từ duration * fps
        fps = 0.0
        if total_frames <= 0:
            try:
                fps_probe = self._run_ffmpeg(
                    [
                        "ffprobe",
                        "-v",
                        "quiet",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=r_frame_rate",
                        "-of",
                        "csv=p=0",
                        video_path,
                    ],
                    timeout=10,
                    label="ffprobe-fps",
                )
                num, den = map(int, fps_probe.stdout.strip().split("/"))
                fps = num / den if den else 0.0
            except Exception:
                fps = 0.0

            if fps <= 0:
                fps = 30.0  # fallback nếu ffprobe fail

            total_frames = int(max(1, math.floor(duration * fps)))

        total_frames = max(1, total_frames)
        step = max(1, total_frames // 6)  # đảm bảo select ra >= 6 frames khi total_frames đủ lớn
        logger.info(
            "Collage frames: duration=%.2fs fps=%.2f total_frames=%d step=%d",
            duration,
            fps,
            total_frames,
            step,
        )

        # 1 lệnh FFmpeg: select 6 frame + tile 3x2
        select_expr = f"not(mod(n\\,{step}))"
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
            # Fallback: chỉ cần 1 frame (để job không bị kẹt retry vô hạn)
            try:
                ts = max(0.0, min(duration, duration * 0.55))
                fallback_cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(ts),
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=400:-1",
                    "-q:v",
                    "2",
                    collage_path,
                ]
                logger.warning("Collage fallback: chụp 1 frame tại t=%.2fs", ts)
                self._run_ffmpeg(fallback_cmd, timeout=30, label="ffmpeg-collage-fallback")
            except Exception as e2:
                logger.error("FFmpeg Collage fallback vẫn fail: %s", e2)
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

    def generate_caption(self, video_path: str, style: str = "general", context: str = "",
                          page_name: str = "", page_niches: list | None = None) -> dict:
        """Pipeline Multimodal Decomposition: (Collage + Transcript) → Gemini → Caption."""
        result = {"caption": "", "hashtags": [], "keywords": []}

        if not video_path or not os.path.exists(video_path):
            logger.error("File media không tồn tại hoặc None: %s", video_path)
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
            logger.info("Bước 2/3: Chạy AI Whisper bóc tách âm thanh sang Text...")
            transcript = self.extract_transcript(video_path)
            logger.info("Transcript hoàn thành: %s ký tự", len(transcript))

            # Truncate transcript to avoid diluting Gemini context
            max_tlen = config.MAX_TRANSCRIPT_LENGTH
            if transcript and len(transcript) > max_tlen:
                transcript = transcript[:max_tlen].rsplit(" ", 1)[0]
                logger.info("Transcript cắt ngắn còn %d ký tự (max %d)", len(transcript), max_tlen)

            intro_action = "viết CAPTION BÁN HÀNG" if style == "sales" else "viết CAPTION"
            if target_image:
                if transcript:
                    prompt_intro = f"""Hãy phân tích Hình ảnh (6 khung hình lưới 2x3 trích từ Video) và kết hợp với Audio Transcript đính kèm bên dưới để {intro_action}.
CHÚ Ý QUAN TRỌNG: TRONG ẢNH CÓ THỂ CÓ CHỮ (SUBTITLE). BẠN NÊN ƯU TIÊN ĐỌC CÁC CHỮ ĐÓ.

Audio Transcript (có thể bắt chữ bị sai do giọng AI), hãy tham khảo kết hợp với Hình ảnh:
"{transcript}" """
                else:
                    logger.info("Video không có transcript (chỉ có nhạc nền). Dùng Hình ảnh làm đầu vào chính.")
                    prompt_intro = f"""Hãy phân tích Hình ảnh (6 khung hình lưới 2x3 trích từ Video) để {intro_action}.
CHÚ Ý QUAN TRỌNG: TRONG ẢNH CÓ THỂ CÓ CHỮ (SUBTITLE). BẠN NÊN ƯU TIÊN ĐỌC CÁC CHỮ ĐÓ.
Video này không có giọng người nói (chỉ có nhạc nền hoặc cảnh hành động). Hãy phác thảo lại nội dung và thông điệp của video dựa trên các khung hình."""
            else:
                if not transcript:
                    logger.error("Không có cả hình ảnh lẫn transcript từ media: %s", video_path)
                    return result
                    
                logger.warning("Fallback text-only (no collage possible): %s", video_path)
                prompt_intro = f"""Không thể trích xuất được hình ảnh/video collage từ media này.
Hãy dựa hoàn toàn vào Audio Transcript bên dưới để {intro_action}.

Audio Transcript (có thể bắt chữ bị sai do giọng AI):
"{transcript}" """

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

        # Bóc tách BOOST_CONTEXT (Smart Boost cho FB page đang viral)
        boost_match = re.search(r'### BOOST_CONTEXT:\s*(.*?)\s*###', context)
        boost_context = boost_match.group(1) if boost_match else ""

        if boost_context:
            prompt_intro += (
                f"\n\n**[🚀 AUTO-BOOST CONTEXT: PAGE ĐANG VIRAL]**\n"
                f"{boost_context}\n"
                f"Hãy viết caption PHẢI PHÙ HỢP với phong cách của page. "
                f"QUAN TRỌNG: Thuật toán ưu tiên 'Completion Rate'. Do đó dòng caption đầu tiên (Hook) "
                f"phải cực kỳ gây tò mò, giật gân, hoặc tranh cãi nhẹ để giữ chân người xem 15-20s đầu tiên!"
            )
            
        context_block = f"\n\n[INPUT VARIABLES]\n- Tên/Loại sản phẩm: Sản phẩm tương ứng trong ảnh/video\n- Phong cách/Tệp KH mục tiêu: {style_guide}"

        # Page-aware context injection
        if page_name or page_niches:
            niches_str = ", ".join(page_niches) if page_niches else "chưa xác định"
            context_block += f"\n- Fanpage đăng bài: {page_name or 'Không rõ'}\n- Lĩnh vực/Niche của page: {niches_str}"

        # ─── New V3 Component: Multi-Brain Intelligence Factory ───
        from app.services.brain_factory import BrainFactory
        
        # Determine Primary Niche for Specialized Persona
        primary_niche = "general"
        if page_niches:
            primary_niche = page_niches[0] # Pick the first niche as primary
        elif "lamdep" in (page_name or "").lower() or "da_dep" in (page_name or "").lower():
            primary_niche = "beauty" # Fallback detection from name
        
        brain_persona = BrainFactory.get_persona_prompt(primary_niche)
        visual_hook_logic = BrainFactory.get_visual_hook_instruction()
        algo_secrets = BrainFactory.get_engagement_secrets()

        # ─── Fix G: Prompt placeholder trung tính, tránh ám thị domain sai ───
        mega_prompt = f"""# MEGA PROMPT: CHUYÊN GIA CONTENT FACEBOOK ADS & ACCESSTRADE
        
[AI BRAIN SPECIALIZATION]
{brain_persona}

[ROLE]
Bạn là một Chuyên gia Digital Marketing & Copywriter thực chiến tại Việt Nam lọt top 1% trong mảng Facebook Ads và Affiliate (Accesstrade). Nhiệm vụ của bạn là viết caption bán hàng, review sản phẩm hoặc kịch bản video ngắn cực kỳ thu hút, nhắm góc nhìn sâu sắc, tối ưu tỷ lệ chuyển đổi (CVR) và tuân thủ tuyệt đối quy định của Meta.

[CONTEXT & MISSION]
{prompt_intro}
{visual_hook_logic}

[TARGET AUDIENCE TONE OF VOICE]
{tone_of_voice}

{algo_secrets}

[FACEBOOK ADS COMPLIANCE & BEST PRACTICES]
- TUYỆT ĐỐI KHÔNG dùng từ ngữ quy chụp thuộc tính cá nhân (Ví dụ: CẤM nói "Bạn đang bị mụn?", "Bạn đang béo?"). Hãy chuyển sang góc nhìn khách quan (Ví dụ: "Giải quyết tình trạng mụn...", "Mẹo giúp vóc dáng thon gọn...").
- TUYỆT ĐỐI KHÔNG đưa ra các cam kết tuyệt đối, sai sự thật (đặc biệt mảng Sức khỏe, Tài chính - YMYL).

[CHỐNG ẢO GIÁC - ANTI-HALLUCINATION RULES]
- TUYỆT ĐỐI KHÔNG được bịa ra tên người, tên app, tên thương hiệu nào không xuất hiện trong hình ảnh/transcript.
- KHÔNG được gọi tên riêng cá nhân (ví dụ: "Chào Vũ", "Bạn Lan ơi").
- KHÔNG nhắc đến bất kỳ app, dịch vụ hoặc platform cụ thể nào (ví dụ: "Hoàn Xu", "Shopee", "Lazada") trừ khi xuất hiện RÕ RÀNG trong hình ảnh hoặc transcript.
- Nội dung caption PHẢI PHÙ HỢP với lĩnh vực/niche của Fanpage đăng bài (xem INPUT VARIABLES bên dưới). Ví dụ: page Skincare thì viết về chăm sóc da, page Thời trang thì viết về quần áo.

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
  "keywords": ["keyword 1", "keyword 2", "keyword 3"],
  "reasoning": "giải thích ngắn gọn về chiến lược visual hook và persona đã chọn"
}}}}
```

Hãy bắt đầu viết JSON ngay bây giờ:"""

        prompt = mega_prompt + "\n\n" + context_block + "\n\n" + output_rules

        logger.info("Bước 3/3: Bắn Prompt và Ảnh lên Gemini RPA...")
        t0 = time.time()
        # Gọi Gemini
        raw_json = self.gemini.ask_with_file(prompt, target_image)
        logger.info("Gemini RPA xong (%.1fs)", time.time() - t0)

        if not raw_json:
            logger.error("Gemini không phản hồi")
            return result
        
        # Parse JSON
        import json as _json
        try:
            # Clean possible markdown wrap
            clean_json = raw_json.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json.split("```json")[-1].split("```")[0].strip()
            elif clean_json.startswith("```"):
                clean_json = clean_json.split("```")[-1].split("```")[0].strip()
            
            data = _json.loads(clean_json)
            result["caption"] = data.get("caption", "")
            result["hashtags"] = data.get("hashtags", [])
            result["keywords"] = data.get("keywords", [])
            
            # ─── New V4 Step: Save AI Strategic Reasoning ───
            if hasattr(self, 'current_job') and self.current_job:
                self.current_job.ai_reasoning = data.get("reasoning", "")
                logger.info("AI Reasoning captured: %s", self.current_job.ai_reasoning)

        except Exception as e:
            logger.error("Lỗi parse JSON từ Gemini: %s. Raw: %s", e, raw_json)
            # Fallback to old parsing if new parsing fails
            result = self._parse_response(raw_json, strict_json=True)

        # Triệt để: nếu Gemini không trả đúng JSON schema → ép 1 vòng "self-repair" (không re-upload file).
        # Điều kiện: response không hề chứa dấu hiệu JSON keys, hoặc parse ra caption rỗng.
        if not self._is_valid_caption_schema_json(json.dumps(result, ensure_ascii=False)): # Use json.dumps to ensure it's a string representation of the result dict
            try:
                repair_prompt = self._build_repair_prompt(raw_json) # Use raw_json for repair
                t1 = time.time()
                repaired = self.gemini.ask(repair_prompt)
                logger.info("Self-repair JSON xong (%.1fs)", time.time() - t1)
                if repaired:
                    repaired_result = self._parse_response(repaired, strict_json=True)
                    if self._is_valid_caption_schema_json(repaired):
                        result = repaired_result
            except Exception as e:
                logger.warning("Self-repair JSON failed: %s", e)

        # STRICT: fail-closed if still not valid JSON (do not let fallback fill garbage)
        if not self._is_valid_caption_schema_json(json.dumps(result, ensure_ascii=False)):
            raise OutputContractViolation("Gemini did not return valid JSON caption schema")

        # ─── Anti-Hallucination Guard: detect prompt echo-back ───
        caption_lower = (result.get("caption") or "").lower()
        HALLUCINATION_MARKERS = [
            "chuyên gia content facebook ads",
            "chuyên gia digital marketing",
            "accesstrade đã sẵn sàng",
            "hỗ trợ bạn tối ưu ngân sách",
            "cho tôi thông tin",
            "lên ngay dàn bài",
            "bạn muốn vít ads",
            "chiến dịch affiliate",
            "tư duy a/b testing",
            "chào vũ",
        ]
        hallucination_hits = sum(1 for m in HALLUCINATION_MARKERS if m in caption_lower)
        if hallucination_hits >= 2:
            logger.error(
                "HALLUCINATION DETECTED (%d markers matched). Caption is prompt echo-back. Rejecting.",
                hallucination_hits,
            )
            raise OutputContractViolation(
                f"Gemini hallucinated prompt echo-back ({hallucination_hits} markers). "
                f"Caption preview: {caption_lower[:120]}"
            )

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

    def _parse_response(self, text: str, strict_json: bool = False) -> dict:
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

        # Layer 4: Non-JSON fallback (DISABLED in strict_json mode)
        if not result.get("caption"):
            if strict_json:
                # Fail closed: do not guess caption from prose/options.
                return self._validate_schema(result)
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
    def _extract_json_candidate(text: str) -> str | None:
        """Try to extract JSON text from a response (codefence or outermost braces)."""
        if not text:
            return None
        m = re.search(r"```json\\s*\\n(.*?)\\n\\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1].strip()
        return None

    def _is_valid_caption_schema_json(self, text: str) -> bool:
        """Strict validator: must be JSON dict with caption (non-empty str) and list hashtags/keywords."""
        cand = self._extract_json_candidate(text) or text
        data = self._try_json_loads(cand)
        if not isinstance(data, dict):
            return False
        caption = data.get("caption")
        hashtags = data.get("hashtags")
        keywords = data.get("keywords")
        if not isinstance(caption, str) or not caption.strip():
            return False
        if not isinstance(hashtags, list) or not all(isinstance(x, (str, int, float, bool)) for x in hashtags):
            return False
        if not isinstance(keywords, list) or not all(isinstance(x, (str, int, float, bool)) for x in keywords):
            return False
        return True

    def _build_repair_prompt(self, raw_response: str) -> str:
        """Non-interactive repair prompt: convert raw response to required JSON schema only."""
        max_len = getattr(config, "MAX_CAPTION_LENGTH", 300)
        return f"""CHUYỂN ĐỔI NỘI DUNG THÀNH JSON.

YÊU CẦU BẮT BUỘC:
- CHỈ TRẢ VỀ DUY NHẤT JSON, KHÔNG markdown, KHÔNG giải thích, KHÔNG hỏi lại.
- Không được trả Option 1/2/3.
- JSON phải có đúng 3 keys: caption, hashtags, keywords.
- caption: string tiếng Việt, ngắn gọn, không vượt quá {max_len} ký tự.
- hashtags: array string (mỗi phần tử bắt đầu bằng #).
- keywords: array string.

OUTPUT JSON TEMPLATE:
{{"caption":"...","hashtags":["#a","#b","#c"],"keywords":["k1","k2","k3"]}}

NỘI DUNG ĐẦU VÀO (hãy chuyển sang JSON theo template, không thêm chữ ngoài JSON):
{raw_response}"""

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
