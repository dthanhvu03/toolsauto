"""Resolve yt-dlp binary so subprocess works when venv is not on PATH (PM2 / Windows)."""
from __future__ import annotations

import os
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


def platform_needs_impersonate(platform: str | None) -> bool:
    """TikTok + Douyin hay bị trang bot — cùng cờ --impersonate chrome khi có curl_cffi."""
    return (platform or "").strip().lower() in ("tiktok", "douyin")


_SKIP_WIN_USERS = {"Public", "Default", "Default User", "All Users", "desktop.ini"}


def chrome_cookies_readable(profile: Path) -> bool:
    """True khi SQLite Cookies mở được — WSL hay bị Permission denied / Default rỗng."""
    for cookie in (profile / "Network" / "Cookies", profile / "Cookies"):
        if not cookie.is_file():
            continue
        try:
            with cookie.open("rb") as fh:
                fh.read(16)
            return True
        except OSError:
            return False
    return False


def _best_chrome_profile(user_data: Path) -> Path | None:
    profiles: list[Path] = []
    default = user_data / "Default"
    if default.is_dir():
        profiles.append(default)
    extra = [p for p in user_data.glob("Profile *") if p.is_dir()]
    extra.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    profiles.extend(extra)
    for p in profiles:
        if chrome_cookies_readable(p):
            return p
    if chrome_cookies_readable(user_data):
        return user_data
    return None


def resolve_chrome_user_data() -> Path | None:
    """Thư mục Chrome User Data để yt-dlp đọc cookie (WSL → Chrome Windows nếu có)."""
    raw = (os.getenv("YTDLP_CHROME_USER_DATA") or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_dir() else None
    candidates: list[Path] = [
        Path.home() / ".config" / "google-chrome",
        Path.home() / ".config" / "chromium",
    ]
    users_root = Path("/mnt/c/Users")
    if users_root.is_dir():
        try:
            for child in users_root.iterdir():
                if child.name in _SKIP_WIN_USERS or not child.is_dir():
                    continue
                ud = child / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
                if ud.is_dir():
                    candidates.append(ud)
        except OSError:
            pass
    for c in candidates:
        if c.is_dir() and _best_chrome_profile(c) is not None:
            return c
    return None


def browser_cookie_args(platform: str | None) -> tuple[str, ...]:
    """
    Douyin bắt cookie trình duyệt kể cả chưa login (yt-dlp: Fresh cookies are needed).
    Ưu tiên file Netscape → spec env → Chrome profile có Cookies đọc được.
    Không log nội dung cookie. Không trỏ Default rỗng (yt-dlp treo 60s trên WSL).
    """
    if (platform or "").strip().lower() != "douyin":
        return ()
    cookie_file = (os.getenv("YTDLP_COOKIES_FILE") or "").strip()
    if cookie_file and Path(cookie_file).is_file():
        return ("--cookies", cookie_file)
    spec = (os.getenv("YTDLP_COOKIES_FROM_BROWSER") or "").strip()
    if spec:
        return ("--cookies-from-browser", spec)
    raw = (os.getenv("YTDLP_CHROME_USER_DATA") or "").strip()
    if raw:
        ud = Path(raw)
        if ud.is_dir():
            return ("--cookies-from-browser", f"chrome:{ud}")
        return ()
    ud = resolve_chrome_user_data()
    if ud is None:
        return ()
    profile = _best_chrome_profile(ud)
    if profile is None:
        return ()
    return ("--cookies-from-browser", f"chrome:{profile}")
