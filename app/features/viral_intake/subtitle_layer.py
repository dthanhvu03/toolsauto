"""
subtitle_layer — đốt phụ đề tiếng Việt vào video reup (ADR-016).

Mục đích: video reup chỉ "khác gốc" bằng intro/outro/hook; lớp này thêm phụ đề
tiếng Việt đốt thẳng vào khung hình (CapCut-like: chữ trắng, viền đen, đậm, canh
giữa đáy) để video có giá trị hơn với người xem tắt tiếng và khác biệt hơn với
bộ lọc trùng của nền tảng.

Đường đi: ffmpeg bóc audio → faster-whisper (singleton của ContentOrchestrator,
không load model lần hai) → pysubs2 dựng file ASS → ffmpeg ``-vf ass=`` đốt vào
video, audio copy nguyên.

Vì sao KHÔNG karaoke từng chữ: word-level alignment tiếng Việt chưa tin được
(stable-ts đã archive, WhisperX lỗi với VI) — Whisper trả timestamp theo từ nhưng
sai lệch vài trăm ms là thường, karaoke sẽ lộ ngay; theo segment thì sai lệch đó
không nhìn thấy. ADR-016 mục "Ngoài phạm vi".

Nguyên tắc (ADR-016 quyết định 1 & 3): hàm thuần, không biết DB, không import lớp
khác; ``apply()`` không bao giờ raise — lỗi thì log warning, trả ``False`` và
ReupProcessor giữ video của bước trước.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from typing import Any, Optional

import pysubs2

from app import config as app_config
from app.core.media import ffmpeg_path
from app.core.orchestrator import ContentOrchestrator

logger = logging.getLogger(__name__)

DEFAULT_FONTS_DIR = str(os.path.join(app_config.BASE_DIR, "app", "static", "fonts"))
DEFAULT_FONT = "Be Vietnam Pro"
FALLBACK_FONT = "Arial"

_WS_RE = re.compile(r"\s+")


# ─── ffmpeg helpers (copy 3 dòng từ reup_processor để tránh import vòng) ───


def _ffmpeg_bin() -> str:
    return ffmpeg_path.ffmpeg_bin()


def _ffprobe_bin() -> str:
    return ffmpeg_path.ffprobe_bin()


def _probe_duration(video_path: str) -> float:
    """Thời lượng (giây) để tính timeout; 0.0 nếu không đọc được."""
    try:
        result = subprocess.run(
            [
                _ffprobe_bin(), "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        return max(0.0, float((result.stdout or "0").strip() or 0))
    except Exception:
        return 0.0


def _escape_filter_path(path: str) -> str:
    """
    Đường dẫn cho tham số filter ffmpeg (``ass=``, ``fontsdir=``).

    Đã kiểm trên ffmpeg 9 Windows: ``\\`` → ``/`` (tránh escape 2 tầng),
    ``:`` → ``\\:`` (tầng option), bọc trong nháy đơn để khoảng trắng, dấu phẩy,
    ``[]`` không bị filtergraph cắt. ``C:\\a b\\x.ass`` → ``'C\\:/a b/x.ass'``.
    Dấu nháy đơn trong path KHÔNG escape được ổn định — ``burn()`` chép file sang
    thư mục tạm khi gặp.
    """
    p = (path or "").replace("\\", "/").replace(":", "\\:")
    return "'" + p + "'"


# ─── 1. Transcribe ───


def _extract_audio(video_path: str, audio_path: str) -> bool:
    """Bóc audio 16 kHz mono WAV (đúng đầu vào Whisper). False nếu không có audio."""
    cmd = [
        _ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", audio_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        logger.warning("[subtitle_layer] ffmpeg audio extract failed: %s", e)
        return False
    if result.returncode != 0:
        return False
    return os.path.isfile(audio_path) and os.path.getsize(audio_path) > 1024


def transcribe_words(video_path: str, model: Any = None) -> list[dict]:
    """
    Whisper → list ``{"start","end","text"}`` theo SEGMENT (không karaoke).

    ``word_timestamps=True`` để biên segment chính xác hơn; ``vad_filter=True``
    bỏ đoạn im lặng (nhạc nền không bị bịa chữ). Video không có audio → ``[]``.
    ``model=None`` → dùng singleton ``ContentOrchestrator._get_whisper_model()``.
    """
    fd, audio_path = tempfile.mkstemp(prefix="sub_", suffix=".wav")
    os.close(fd)
    try:
        if not _extract_audio(video_path, audio_path):
            logger.info("[subtitle_layer] no audio track: %s", os.path.basename(video_path))
            return []
        if model is None:
            model = ContentOrchestrator._get_whisper_model()
        segments, _info = model.transcribe(
            audio_path,
            language="vi",
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )
        out: list[dict] = []
        for seg in segments:
            text = _WS_RE.sub(" ", unicodedata.normalize("NFC", seg.text or "")).strip()
            if not text:
                continue
            start = float(seg.start)
            end = float(seg.end)
            if end <= start:
                continue
            out.append({"start": start, "end": end, "text": text})
        return out
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


# ─── 2. Build ASS ───


def _wrap_lines(text: str, max_chars: int) -> list[str]:
    """Ngắt theo từ, mỗi dòng ≤ max_chars (từ đơn dài hơn thì đứng một mình)."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}"
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_ass(
    segments: list[dict],
    out_ass_path: str,
    *,
    width: int = 1080,
    height: int = 1920,
    font: str = DEFAULT_FONT,
    font_size: int = 64,
    margin_v: int = 260,
    max_chars: int = 22,
) -> str:
    """
    Dựng file ASS kiểu CapCut: Bold, Outline 3, Shadow 1, trắng viền đen,
    Alignment 2 (bottom-center), MarginV cho 9:16.

    Segment dài → ngắt ≤ ``max_chars``/dòng, tối đa 2 dòng/event; quá 2 dòng thì
    tách thành nhiều event chia đều thời gian. PlayRes cố định ``width×height``,
    libass tự scale theo kích thước video thật.
    """
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = str(int(width))
    subs.info["PlayResY"] = str(int(height))
    subs.info["WrapStyle"] = "2"  # không tự ngắt — ta ngắt bằng \N
    subs.info["ScaledBorderAndShadow"] = "yes"
    subs.styles["Default"] = pysubs2.SSAStyle(
        fontname=font,
        fontsize=float(font_size),
        primarycolor=pysubs2.Color(255, 255, 255),
        secondarycolor=pysubs2.Color(255, 255, 255),
        outlinecolor=pysubs2.Color(0, 0, 0),
        backcolor=pysubs2.Color(0, 0, 0, 128),
        bold=True,
        borderstyle=1,
        outline=3.0,
        shadow=1.0,
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
        marginl=60,
        marginr=60,
        marginv=int(margin_v),
    )

    max_chars = max(8, int(max_chars))
    for seg in segments:
        text = _WS_RE.sub(" ", unicodedata.normalize("NFC", str(seg.get("text") or ""))).strip()
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or 0.0)
        if not text or end <= start:
            continue
        lines = _wrap_lines(text, max_chars)
        chunks = [lines[i:i + 2] for i in range(0, len(lines), 2)]
        slot = (end - start) / len(chunks)
        for i, chunk in enumerate(chunks):
            s = start + i * slot
            e = end if i == len(chunks) - 1 else s + slot
            subs.append(
                pysubs2.SSAEvent(
                    start=pysubs2.make_time(s=s),
                    end=pysubs2.make_time(s=e),
                    text="\\N".join(chunk),
                )
            )

    subs.save(out_ass_path, encoding="utf-8", format_="ass")
    return out_ass_path


# ─── 3. Burn ───


def burn(input_path: str, ass_path: str, output_path: str, *, fonts_dir: str) -> bool:
    """
    ``ffmpeg -i in -vf "ass=<ass>:fontsdir=<dir>" -c:a copy out``.

    Timeout = 60 s + 2 × thời lượng. Trả False (không raise) khi ffmpeg lỗi,
    file ra thiếu hoặc quá nhỏ.
    """
    safe_ass = ass_path
    tmp_copy: Optional[str] = None
    if "'" in ass_path:
        # Nháy đơn trong path không escape ổn định qua 2 tầng parser của ffmpeg.
        fd, tmp_copy = tempfile.mkstemp(prefix="sub_", suffix=".ass")
        os.close(fd)
        shutil.copyfile(ass_path, tmp_copy)
        safe_ass = tmp_copy

    vf = f"ass={_escape_filter_path(safe_ass)}"
    if fonts_dir and os.path.isdir(fonts_dir):
        vf += f":fontsdir={_escape_filter_path(fonts_dir)}"
    else:
        logger.warning("[subtitle_layer] fonts_dir missing (%s) — libass dùng font hệ thống", fonts_dir)

    duration = _probe_duration(input_path)
    timeout = int(60 + 2 * (duration or 90.0))
    cmd = [
        _ffmpeg_bin(), "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning(
                "[subtitle_layer] ffmpeg burn failed: %s", (result.stderr or "")[-240:]
            )
            return False
        if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
            logger.warning("[subtitle_layer] burn produced empty file: %s", output_path)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("[subtitle_layer] ffmpeg burn timeout (>%ss)", timeout)
        return False
    finally:
        if tmp_copy:
            try:
                os.remove(tmp_copy)
            except OSError:
                pass


# ─── 4. Apply (điểm vào duy nhất cho ReupProcessor) ───


def apply(
    input_path: str,
    output_path: str,
    *,
    model: Any = None,
    fonts_dir: Optional[str] = None,
    font_size: int = 64,
    margin_v: int = 260,
) -> bool:
    """
    transcribe → build ASS (file tạm cạnh output) → burn → xoá tạm.

    Trả ``False`` và KHÔNG tạo output khi không có segment nào; mọi exception →
    ``logger.warning`` + ``False``. Không bao giờ raise (ADR-016 quyết định 3).
    """
    ass_path = os.path.splitext(output_path)[0] + ".sub.tmp.ass"
    ok = False
    try:
        segments = transcribe_words(input_path, model=model)
        if not segments:
            logger.info("[subtitle_layer] no speech found, skip: %s", os.path.basename(input_path))
            return False
        build_ass(segments, ass_path, font_size=int(font_size), margin_v=int(margin_v))
        ok = burn(input_path, ass_path, output_path, fonts_dir=fonts_dir or DEFAULT_FONTS_DIR)
        if ok:
            logger.info(
                "[subtitle_layer] burned %d segments → %s",
                len(segments), os.path.basename(output_path),
            )
        return ok
    except Exception as e:
        logger.warning("[subtitle_layer] apply failed, keep previous video: %s", e)
        return False
    finally:
        try:
            if os.path.isfile(ass_path):
                os.remove(ass_path)
        except OSError:
            pass
        # Thất bại thì không để output nửa chừng lại cho bước sau
        if not ok:
            try:
                if os.path.isfile(output_path):
                    os.remove(output_path)
            except OSError:
                pass
