"""Resolve yt-dlp binary path so subprocess works when venv/bin is not in PATH (e.g. PM2)."""
import shutil
import sys
from pathlib import Path


def yt_dlp_binary() -> str:
    """PATH first, else same dir as current Python (venv/bin khi chạy qua venv). Không resolve symlink để giữ đúng thư mục python đang chạy."""
    b = shutil.which("yt-dlp")
    if b:
        return b
    # Cùng thư mục với sys.executable (tránh resolve symlink → /usr/bin)
    bin_dir = Path(sys.executable).parent
    yt_dlp = bin_dir / "yt-dlp"
    if yt_dlp.exists():
        return str(yt_dlp)
    return "yt-dlp"
