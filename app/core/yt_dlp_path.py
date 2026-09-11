"""Resolve yt-dlp binary so subprocess works when venv is not on PATH (PM2 / Windows)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def yt_dlp_binary() -> str | list[str]:
    """Return a subprocess argv head: path string or ``[python, -m, yt_dlp]``.

    Thứ tự (ADR-029): binary cạnh ``sys.executable`` → ``python -m yt_dlp`` → PATH → tên trần.

    **PATH đứng sau cùng, không phải đầu tiên.** Ngày 2026-09-09 máy Owner có một
    ``yt-dlp.exe`` cài toàn cục **cũ 17 tháng** nằm trên PATH, thắng bản 2026.8.19 ghim trong
    ``requirements.txt`` — quét TikTok gãy âm thầm, mà trang Sức khỏe lại đọc phiên bản gói
    trong venv nên vẫn báo "ổn". Hai nấc đầu đi theo đúng trình thông dịch đang chạy tool nên
    **luôn khớp bản đã ghim**; PATH chỉ còn là phương án dự phòng — đúng ý định ban đầu của
    hàm này ("để chạy được khi venv không nằm trên PATH").
    """
    bin_dir = Path(sys.executable).parent
    for name in ("yt-dlp.exe", "yt-dlp", "yt_dlp.exe"):
        candidate = bin_dir / name
        if candidate.is_file():
            return str(candidate)

    # Linux layout if somehow used
    linux_bin = bin_dir.parent / "bin" / "yt-dlp"
    if linux_bin.is_file():
        return str(linux_bin)

    # Gói cài trong chính trình thông dịch đang chạy — vẫn là bản đã ghim, vẫn hơn PATH.
    try:
        import yt_dlp  # noqa: F401

        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        pass

    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    return "yt-dlp"


def yt_dlp_cmd(*args: str) -> list[str]:
    """Build full argv for yt-dlp with optional trailing args."""
    head = yt_dlp_binary()
    if isinstance(head, list):
        return [*head, *args]
    return [head, *args]


def impersonate_args() -> tuple[str, ...]:
    """
    ``("--impersonate", "chrome")`` khi ``curl_cffi`` có mặt, không thì rỗng.

    TikTok chặn IP lạ bằng trang kiểm tra bot: máy dev liệt kê kênh bình thường, laptop Owner
    trả "Failed to parse JSON" (2026-09-11). Giả Chrome (``--impersonate``) qua được, NHƯNG
    cờ này **bắt buộc** có ``curl_cffi`` — thiếu gói là yt-dlp dừng ngay với
    ``Impersonate target "chrome" is not available``, tức bật cứng cờ là làm hỏng luôn máy
    đang chạy tốt. Nên: có gói thì dùng, không có thì chạy như cũ và để tin lỗi chỉ đường.
    """
    try:
        import curl_cffi  # noqa: F401

        return ("--impersonate", "chrome")
    except ImportError:
        return ()
