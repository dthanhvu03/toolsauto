"""
ADR-043 — tải bản gốc về máy, KHÔNG đi qua luồng reup.

Ranh giới quan trọng nhất của module này là những gì nó *không* làm: không tạo
``ViralMaterial``, không chống trùng, không cắt, không caption, không đụng ``REUP_DIR``.
Đây là kho lưu, không phải kho sản xuất (ADR-042 vừa phải tách hai thứ đó ra).

Mọi lối ra đều là ``dict`` có ``ok`` + ``msg`` tiếng Việt; không bao giờ raise ra poller.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import app.config as config
from app.constants import AccountStatus
from app.core.database.models import Account
from app.core.storage import offsite
from app.core.yt_dlp_path import yt_dlp_cmd
from app.features.viral_intake.intake import _bare_host, _split, detect_platform
from app.features.viral_intake.sources import _ytdlp_diagnosis

logger = logging.getLogger(__name__)

MAX_FILESIZE = "500M"  # "video nào cũng được" + không dọn = đầy ổ; chặn ở đây
PROBE_TIMEOUT_SEC = 60
DOWNLOAD_TIMEOUT_SEC = 600
TELEGRAM_LIMIT_MB = 50.0

_LOGIN_MARKERS = ("login", "log in", "cookies", "private", "not available", "unavailable for certain audiences")


_KNOWN_HOSTS = ("tiktok.com", "youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com")


def _known_host_but_not_video(url: str) -> bool:
    """
    Link kênh / trang cá nhân / playlist của nền tảng đã biết. Chặn TRƯỚC khi gọi yt-dlp:
    với `--no-playlist` yt-dlp vẫn cố lấy video đầu tiên của kênh rồi hỏng bằng thông báo
    thô (đo thật 2026-09-11 với link kênh TikTok) — chặn sớm thì tin nhắn nói đúng chuyện.
    """
    split = _split(url)
    if not split:
        return False
    parts, raw_host = split
    host = _bare_host(raw_host)
    known = any(host == h or host.endswith("." + h) for h in _KNOWN_HOSTS)
    if not known:
        return False
    if detect_platform(url) is None:
        return True
    # `detect_platform` coi MỌI link tiktok.com là "tiktok" (kể cả trang kênh) — với /tai phải
    # chặt hơn: link video có `/video/<id>`, hoặc là link rút gọn vt./vm. (chưa biết đích).
    if host == "tiktok.com" and not raw_host.startswith(("vt.", "vm.")):
        return "/video/" not in (parts.path or "")
    return False


def downloads_dir() -> Path:
    return Path(str(config.DOWNLOADS_DIR)) / time.strftime("%Y-%m")


def _account_with_cookies(db: Session, platform: str) -> Optional[Account]:
    """Tài khoản ACTIVE cùng nền tảng để mượn cookie — chỉ Facebook/Instagram mới cần."""
    if platform not in ("facebook", "instagram") or db is None:
        return None
    return (
        db.query(Account)
        .filter(Account.is_active == True, Account.login_status == AccountStatus.ACTIVE, Account.platform == platform)  # noqa: E712
        .first()
    )


def _with_cookies(cmd: list[str], account: Optional[Account]) -> list[str]:
    if not account or not getattr(account, "profile_path", None):
        return cmd
    return [*cmd, "--cookies-from-browser", f"chromium:{account.profile_path}"]


def _tail(stderr: str) -> str:
    for line in reversed((stderr or "").strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def humanize_fetch_error(platform: str, stderr: str, *, had_cookies: bool) -> str:
    low = (stderr or "").lower()
    if "is a playlist" in low or ("playlist" in low and "no-playlist" not in low):
        return "Đây là link danh sách/kênh — /tai chỉ nhận link MỘT video."
    if "max-filesize" in low or "file is larger than max-filesize" in low:
        return f"Video lớn hơn {MAX_FILESIZE} — không tải để khỏi đầy ổ."
    if any(m in low for m in _LOGIN_MARKERS) and platform in ("facebook", "instagram"):
        if had_cookies:
            return (f"{platform.capitalize()} vẫn từ chối dù đã dùng cookie tài khoản — video riêng tư/nhóm kín, "
                    "hoặc Chrome đang mở profile đó (yt-dlp không đọc được cookie khi Chrome đang chạy).")
        return f"{platform.capitalize()} đòi đăng nhập — cần một tài khoản {platform} ACTIVE trong tool để mượn cookie."
    if "404" in low or "not found" in low or "does not exist" in low or "removed" in low:
        return "Video không tồn tại hoặc đã bị gỡ."
    if "unsupported url" in low:
        return "yt-dlp không hỗ trợ trang này."
    if "failed to parse json" in low or "unable to extract" in low or "unexpected response" in low:
        return f"yt-dlp không đọc được trang {platform}." + (_ytdlp_diagnosis() or " Kiểm tra bản yt-dlp ở trang Sức khỏe.")
    if "timed out" in low or "timeout" in low:
        return "Mạng chậm, yt-dlp hết giờ chờ — thử lại."
    t = _tail(stderr)
    return t[:200] if t else "yt-dlp không nói lý do"


def _probe(url: str, account: Optional[Account]) -> tuple[Optional[dict], str]:
    cmd = _with_cookies(yt_dlp_cmd("--no-playlist", "--skip-download", "--dump-single-json", "--no-warnings", url), account)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, "Read timed out"
    except (FileNotFoundError, OSError) as exc:
        return None, f"Không chạy được yt-dlp: {exc}"
    if r.returncode != 0:
        return None, r.stderr or ""
    try:
        info = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, "Failed to parse JSON"
    if info.get("_type") == "playlist" or info.get("entries"):
        return None, "This URL is a playlist"
    return info, ""


def fetch_original(db: Optional[Session], url: str) -> dict:
    """
    Tải MỘT video về ``tai-ve/<tháng>/<tiêu đề>.mp4``, chép Drive nếu bật.

    Trả ``{"ok", "msg", "path", "drive_path", "size_mb", "title", "sendable"}``.
    ``sendable`` = file ≤ 50 MB, người gọi mới được gửi lên Telegram — hứa gửi rồi lỗi 413
    là nhãn nói dối.
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "msg": "Cần một link http(s)."}
    if _known_host_but_not_video(url):
        return {"ok": False, "msg": "Đây là link kênh / trang cá nhân / danh sách — /tai chỉ nhận link MỘT video."}
    platform = detect_platform(url) or "khac"

    # Không cookie trước: video công khai là đa số, và `--cookies-from-browser` thất bại khi
    # Chrome đang mở profile đó. Chỉ khi Facebook/Instagram từ chối mới thử lại có cookie.
    account: Optional[Account] = None
    info, err = _probe(url, None)
    if info is None and platform in ("facebook", "instagram") and any(m in err.lower() for m in _LOGIN_MARKERS):
        account = _account_with_cookies(db, platform)
        if account is not None:
            info, err = _probe(url, account)
    if info is None:
        return {"ok": False, "msg": humanize_fetch_error(platform, err, had_cookies=account is not None)}

    title = str(info.get("title") or info.get("id") or "video").strip()
    vid = str(info.get("id") or int(time.time()))
    out_dir = downloads_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_template = str(out_dir / f".{vid}.%(ext)s")

    cmd = _with_cookies(
        yt_dlp_cmd("--no-playlist", "--no-warnings", "--max-filesize", MAX_FILESIZE,
                   "--merge-output-format", "mp4", "-o", tmp_template, url),
        account,
    )
    logger.info("[FETCH] %s → %s", url, out_dir)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": f"Tải quá {DOWNLOAD_TIMEOUT_SEC // 60} phút chưa xong — bỏ."}
    if r.returncode != 0:
        return {"ok": False, "msg": humanize_fetch_error(platform, r.stderr, had_cookies=account is not None)}

    tmp = next((p for p in out_dir.glob(f".{vid}.*") if p.is_file() and p.stat().st_size > 0), None)
    if tmp is None:
        return {"ok": False, "msg": "yt-dlp báo xong mà không thấy file — có thể vượt 500 MB nên bị bỏ."}

    final = out_dir / offsite.safe_video_name(tmp.name.lstrip("."), None, title)
    if final.exists():
        final = out_dir / f"{final.stem} [{vid}]{final.suffix}"
    os.replace(tmp, final)

    size_mb = final.stat().st_size / (1024 * 1024)
    drive = offsite.copy_out(str(final), "download", month_folder=True)
    drive_rel = offsite.relative_to_root(drive) if drive else None
    rel = final.relative_to(Path(str(config.STORAGE_MEDIA_DIR))).as_posix() if str(final).startswith(str(config.STORAGE_MEDIA_DIR)) else str(final)
    msg = f"📥 Đã tải: <b>{html_mod.escape(title[:80])}</b> · {size_mb:.1f} MB\n📁 <code>{html_mod.escape(rel)}</code>"
    if drive_rel:
        msg += f"\n📂 Drive: <code>{html_mod.escape(str(drive_rel))}</code>"
    return {
        "ok": True, "msg": msg, "path": str(final), "drive_path": drive_rel,
        "size_mb": round(size_mb, 1), "title": title, "sendable": size_mb <= TELEGRAM_LIMIT_MB,
    }
