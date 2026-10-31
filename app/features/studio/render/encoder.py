"""
Chọn bộ mã hoá hình cho render: NVENC (GPU NVIDIA) khi dùng được, không thì libx264 (CPU).

Dò bằng một lần encode thật rất nhỏ (có ``h264_nvenc`` trong ffmpeg chưa đủ — driver cũ vẫn báo «Driver does not support
the required nvenc API version»). Kết quả nhớ trong tiến trình; render lỗi với NVENC thì ``mark_failed`` → các lần sau
dùng CPU. Ép tay bằng biến môi trường ``STUDIO_ENCODER`` = ``auto`` (mặc định) / ``nvenc`` / ``x264``.

Chỉ phần nén hình chạy trên GPU; lọc (nền mờ, phụ đề, chữ, LUT) vẫn chạy CPU.
"""
from __future__ import annotations

import logging
import os
import subprocess

from app.core.media import ffmpeg_path

logger = logging.getLogger(__name__)

NVENC = "h264_nvenc"
X264 = "libx264"
_cache: dict[str, bool] = {}


def video_args(encoder: str, *, crf: int = 21, preset: str = "veryfast") -> list[str]:
    """Tham số ``-c:v`` tương đương giữa hai bộ mã hoá: cq 28 NVENC ≈ crf 21 x264 (đo trên dự án thật 31/10:
    SSIM 0,99 so với bản x264, file 8,9 MB / 6,7 MB; cq 23 ra 16,7 MB)."""
    if encoder == NVENC:
        return ["-c:v", NVENC, "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(crf + 7), "-b:v", "0",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", X264, "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]


def nvenc_works(ffmpeg: str | None = None) -> bool:
    if "nvenc" not in _cache:
        cmd = [ffmpeg or ffmpeg_path.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
               "-i", "testsrc2=size=256x256:rate=30:duration=0.2", *video_args(NVENC), "-f", "null", "-"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            _cache["nvenc"] = proc.returncode == 0
            if proc.returncode != 0:
                logger.info("[STUDIO] NVENC không dùng được, render bằng CPU: %s", (proc.stderr or "").strip()[-200:])
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("[STUDIO] NVENC không dùng được (%s), render bằng CPU", exc)
            _cache["nvenc"] = False
    return _cache["nvenc"]


def pick(ffmpeg: str | None = None) -> str:
    want = (os.environ.get("STUDIO_ENCODER") or "auto").strip().lower()
    if want == "x264":
        return X264
    if want == "nvenc":
        return NVENC
    return NVENC if nvenc_works(ffmpeg) else X264


def mark_failed() -> None:
    """Render với NVENC hỏng giữa chừng (hết VRAM, driver…) → tiến trình này dùng CPU từ giờ."""
    _cache["nvenc"] = False
