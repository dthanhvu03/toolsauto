"""
Nguồn quét tự động (ADR-019) — kênh TikTok / YouTube Shorts độc lập với account.

``SourceService`` là hợp đồng cố định giữa UI (router/template) và backend:
``list_sources`` / ``add_source`` / ``set_enabled`` / ``delete_source`` / ``scan_source`` /
``scan_all``. Quét bằng ``yt-dlp --flat-playlist --dump-json``; TikTok thêm
``--impersonate chrome`` (cần ``curl_cffi``) vì TikTok trả trang rỗng nếu không giả trình duyệt.
video đạt ``min_views`` được ghi thành ``ViralMaterial(NEW, scraped_by_account_id=None)``
để sweep nền nhặt (ADR-018: không account → READY).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import random
import re
import subprocess
import time
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

import app.config as config
from app.core.notifier.service import NotifierService
from app.constants import JobStatus, ViralStatus
from app.core import settings as runtime_settings
from app.core.database.models import Job, ViralMaterial, ViralSource
from app.core.database.models.base import now_ts
from app.core.yt_dlp_path import impersonate_args, yt_dlp_cmd
from app.features.viral_intake.intake import normalize_source_url
from app.features.viral_intake.tiktok_scraper import (
    RATE_LIMIT_BACKOFF_HOURS,
    _load_rate_limits,
    _save_rate_limits,
)

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SEC = 90
# Dò channel_id chỉ đọc metadata MỘT video nên ngắn hơn hẳn một lượt quét kênh.
RESOLVE_TIMEOUT_SEC = 60
MAX_VIDEOS_CAP = 500
_ERROR_MAX_LEN = 300  # đủ chỗ cho câu dịch + bản yt-dlp + lệnh sửa

# PLAN-161: nguồn quét thành công mà không ra video mới N lần liền → coi là cạn, tự nghỉ rồi tự thử lại.
EMPTY_SCANS_TO_REST = 3
REST_HOURS = 24
# PLAN-164: kênh còn dưới LOW_READY video chưa hẹn và không còn nguồn nào đang quét → tự bật lại một nguồn đang tắt.
LOW_READY = 5
REVIVE_MIN_OFF_SEC = 24 * 3600  # chủ bot vừa tắt (< 24 giờ) thì không bật lại
REVIVE_COOLDOWN_SEC = 7 * 24 * 3600  # mỗi nguồn tự bật tối đa 1 lần / 7 ngày
ACTIVE_PAGE_DAYS = 14  # chỉ lo cho kênh còn đăng Buffer gần đây (kênh đã bỏ thì không bật nguồn)

# ADR-028: TikTok trả trang kênh thiếu dữ liệu với một số tài khoản; yt-dlp báo đúng câu này
# và gợi ý dùng `tiktokuser:<channel_id>`. CẢNH BÁO: cùng thông báo này cũng nổ khi channel_id
# sai hoặc bị cắt cụt — đừng đọc nó rồi kết luận vội là kênh không cứu được.
_TIKTOK_NO_SECONDARY_ID = "unable to extract secondary user id"
MSG_TIKTOK_NEED_VIDEO_LINK = (
    "TikTok không cho liệt kê kênh này bằng @handle. Mở kênh, copy link MỘT video bất kỳ của "
    "họ rồi dán vào ô URL kênh — tool tự dò ra kênh từ video đó."
)

MSG_VIDEO_LINK = "Đây là link video, không phải kênh — dùng ô dán link video ở trên."
MSG_FB_IG = (
    "Facebook/Instagram không liệt kê được danh sách video (yt-dlp không hỗ trợ) — "
    "chỉ dán từng link video ở ô dán link."
)
MSG_UNKNOWN = "Không nhận diện được kênh. Dán URL kênh TikTok (@handle) hoặc YouTube (@handle, /channel/…)."

# Đầu dòng lỗi yt-dlp: "ERROR: <id hoặc handle>: <lý do>". Với nguồn `tiktokuser:` cái <id>
# là sec_uid dài 60 ký tự — chiếm gần hết chỗ trong tin Telegram (cắt ở 120), phần có nghĩa
# bị mất. Bỏ nó đi; Owner đã biết nguồn nào vì lỗi nằm ngay dưới tên nguồn.
_YTDLP_ERROR_HEAD_RE = re.compile(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*)?(?:[A-Za-z0-9_\-.@]{6,}:\s*)?", re.IGNORECASE)


def _ytdlp_diagnosis() -> str:
    """
    Một mệnh đề tự khai bản yt-dlp ĐANG CHẠY so với bản ghim — dán vào tin lỗi để Owner
    khỏi phải đi mở trang Sức khỏe rồi quay lại. Dùng đúng phép đo của ADR-029.
    Không bao giờ ném; đo không được thì trả chuỗi rỗng.
    """
    try:
        from app.core.observability.health import _ytdlp_version_status

        st = _ytdlp_version_status()
        cur, pin = st.get("installed"), st.get("pinned")
        if not cur:
            return ""
        if st.get("outdated"):
            return (f" yt-dlp đang chạy {cur}, bản ghim {pin} ⇒ CŨ. "
                    r"Chạy: venv\Scripts\python.exe -m pip install -r requirements.txt")
        if st.get("mismatch"):
            return f" yt-dlp đang chạy {cur} khác bản trong venv ({st.get('package')}) — có bản lạ chen vào PATH."
        return f" yt-dlp {cur} đúng bản ghim ⇒ không phải do phần mềm cũ; TikTok đang chặn tạm, thử lại sau 1 giờ."
    except Exception:
        return ""


def humanize_scan_error(platform: str, stderr: str) -> str:
    """
    Dịch dòng cuối stderr của yt-dlp thành câu Owner hành động được — như ``processor``
    đã làm cho lượt tải (ADR-033: lệnh phải nói thật, và nói cho người đọc được).

    Không nhận ra thì trả nguyên dòng đã bỏ đầu ``ERROR: <id>:`` — vẫn còn là sự thật,
    chỉ không dịch.
    """
    tail = ""
    for line in reversed((stderr or "").strip().splitlines()):
        if line.strip():
            tail = line.strip()
            break
    if not tail:
        return "yt-dlp không nói lý do"
    low = tail.lower()
    if platform == "tiktok":
        if _TIKTOK_NO_SECONDARY_ID in low:
            return MSG_TIKTOK_NEED_VIDEO_LINK
        if "failed to parse json" in low or "unexpected response" in low:
            # Đo 2026-09-11: cùng nguồn, cùng lệnh chạy bằng yt-dlp 2026.08.19 ra 21 video 3/3 lần;
            # máy bot của Owner báo câu này ⇒ hoặc yt-dlp cũ, hoặc TikTok trả trang kiểm tra bot.
            goi_y = ""
            if not impersonate_args():
                # Laptop Owner 2026-09-11: đúng bản yt-dlp mà vẫn hỏng — TikTok chặn IP bằng trang
                # kiểm tra bot; giả Chrome qua được nhưng cần curl_cffi (nhánh Cursor dd66ede).
                goi_y = r" Máy này CHƯA có curl_cffi để giả Chrome — chạy: venv\Scripts\python.exe -m pip install -r requirements.txt"
            return "TikTok trả về trang kiểm tra bot thay vì dữ liệu." + (
                _ytdlp_diagnosis() or " Thường do yt-dlp cũ hoặc bị chặn tạm — xem trang Sức khỏe."
            ) + goi_y
        if "unable to extract" in low:
            return "TikTok đổi cấu trúc trang, yt-dlp không đọc được — cập nhật yt-dlp." + _ytdlp_diagnosis()
        if "429" in low or "rate limit" in low or "too many" in low:
            return "TikTok chặn vì quét quá dày (429) — tool tự đợi, thử lại sau."
    if "404" in low or "not found" in low or "does not exist" in low:
        return "Kênh không tồn tại hoặc đã đổi tên."
    if "private" in low:
        return "Kênh riêng tư — yt-dlp không xem được."
    if "timed out" in low or "timeout" in low:
        return "Mạng chậm, yt-dlp hết giờ chờ — thử lại."
    return _YTDLP_ERROR_HEAD_RE.sub("", tail, count=1).strip() or tail


_HANDLE_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _bare_host(host: str) -> str:
    for prefix in ("www.", "m.", "vm.", "vt.", "web.", "mbasic.", "touch."):
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def _classify(url: str) -> tuple[tuple[str, str, str] | None, str]:
    """Trả ``((platform, canonical, handle), "")`` hoặc ``(None, lý_do)``."""
    raw = (url or "").strip()
    if not raw:
        return None, MSG_UNKNOWN
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    raw_host = (parts.hostname or "").lower()
    if raw_host in ("vt.tiktok.com", "vm.tiktok.com"):
        return None, MSG_VIDEO_LINK  # link rút gọn luôn trỏ tới 1 video
    host = _bare_host(raw_host)
    segs = [s for s in (parts.path or "").split("/") if s]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        if not segs or not segs[0].startswith("@"):
            return None, MSG_VIDEO_LINK if segs and segs[0] in ("t", "v") else MSG_UNKNOWN
        if len(segs) >= 2 and segs[1] in ("video", "photo"):
            return None, MSG_VIDEO_LINK
        handle = segs[0][1:]
        if not handle or not _HANDLE_RE.match(handle):
            return None, MSG_UNKNOWN
        return ("tiktok", f"https://www.tiktok.com/@{handle}", handle), ""

    if host == "youtu.be":
        return None, MSG_VIDEO_LINK
    if host == "youtube.com":
        if not segs:
            return None, MSG_UNKNOWN
        head = segs[0]
        if head == "shorts" or head == "watch" or query.get("v"):
            return None, MSG_VIDEO_LINK
        if head.startswith("@"):
            handle = head[1:]
            if not handle or not _HANDLE_RE.match(handle):
                return None, MSG_UNKNOWN
            return ("youtube", f"https://www.youtube.com/@{handle}/shorts", handle), ""
        if head in ("channel", "c", "user") and len(segs) >= 2 and _HANDLE_RE.match(segs[1]):
            return ("youtube", f"https://www.youtube.com/{head}/{segs[1]}/shorts", segs[1]), ""
        return None, MSG_UNKNOWN

    if host == "fb.watch":
        return None, MSG_VIDEO_LINK

    if host in ("facebook.com", "fb.com"):
        if not segs:
            return None, MSG_UNKNOWN
        head = segs[0].lower()
        if head in ("reel", "reels", "watch", "share") or "story" in head:
            return None, MSG_VIDEO_LINK
        if head == "profile.php":
            pid = query.get("id")
            if pid:
                canonical = f"https://www.facebook.com/profile.php?id={pid}&sk=reels_tab"
                return ("facebook", canonical, f"fb_user_{pid}"), ""
            return None, MSG_UNKNOWN
        if head == "p":
            if len(segs) >= 2:
                page_handle = segs[1]
                if len(segs) >= 3 and segs[2].lower() in ("videos", "posts", "reel", "photos", "watch"):
                    return None, MSG_VIDEO_LINK
                canonical = f"https://www.facebook.com/p/{page_handle}/reels"
                return ("facebook", canonical, f"fb_page_{page_handle}"), ""
            return None, MSG_UNKNOWN
        if len(segs) >= 2:
            sub = segs[1].lower()
            if sub in ("videos", "posts", "reel", "photos"):
                return None, MSG_VIDEO_LINK
        handle = segs[0]
        if handle.lower() in ("home", "messages", "notifications", "friends", "marketplace", "watch", "gaming", "groups", "events"):
            return None, MSG_UNKNOWN
        canonical = f"https://www.facebook.com/{handle}/reels"
        return ("facebook", canonical, handle), ""

    if host == "instagram.com":
        return None, MSG_FB_IG
    return None, MSG_UNKNOWN


def _www_variants(url: str) -> tuple[str, str]:
    from urllib.parse import urlencode
    parts = urlsplit(url)
    host = parts.hostname or ""
    bare = host[4:] if host.startswith("www.") else host
    tracking_params = {"mibextid", "ref", "fbclid", "sfnsn", "locale", "utm_source", "utm_medium", "utm_campaign", "__tn__"}
    filtered_query = []
    if parts.query:
        filtered_query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in tracking_params]
    clean_path = parts.path.rstrip("/")
    tail = clean_path + (f"?{urlencode(filtered_query)}" if filtered_query else "")
    return f"https://{bare}{tail}", f"https://www.{bare}{tail}"


def _setting_int(db: Session, key: str, fallback: int) -> int:
    try:
        return int(runtime_settings.get_int(key, fallback, db=db))
    except Exception:
        return fallback


def _video_url(platform: str, handle: str, data: dict) -> str | None:
    vid = str(data.get("id") or "").strip()
    raw = data.get("url") or data.get("webpage_url") or data.get("original_url") or ""
    if platform == "tiktok":
        # TikTok: `uploader` là @handle chữ, `uploader_id` là id số — phải dùng handle chữ để
        # cùng dạng scan.py đang lưu (www + /@handle/video/<id>) và khớp quota theo handle.
        h = str(data.get("uploader") or handle or data.get("uploader_id") or "").lstrip("@")
        if vid and h:
            return f"https://www.tiktok.com/@{h}/video/{vid}"
        return raw.split("?")[0].rstrip("/") if raw.startswith("http") else None
    if vid:
        return normalize_source_url(f"https://youtube.com/shorts/{vid}")
    return normalize_source_url(raw) if raw.startswith("http") else None


def _resolve_tiktok_user_from_video(video_url: str) -> tuple[tuple[str, str, str] | None, str]:
    """
    ADR-028 — link MỘT video TikTok → nguồn kênh dạng ``tiktokuser:<channel_id>``.

    Dùng khi TikTok không cho liệt kê kênh bằng ``@handle``. Đây là hàm **có mạng**, nên tách
    hẳn khỏi ``_classify`` (vốn thuần, rẻ, có test) và không bao giờ raise: hỏng gì cũng trả
    ``(None, thông báo tiếng Việt)`` để ``add_source`` hiện toast như mọi nhánh từ chối khác.
    """
    cmd = yt_dlp_cmd(
        "--dump-json", "--no-warnings", "--playlist-items", "1",
        *impersonate_args(), video_url,
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=RESOLVE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return None, f"Quá {RESOLVE_TIMEOUT_SEC}s chưa đọc được video — thử lại hoặc dùng link video khác."
    except (FileNotFoundError, OSError) as exc:
        return None, f"Không chạy được yt-dlp: {exc}"

    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()
        return None, f"Không đọc được video này: {tail[-1][:_ERROR_MAX_LEN] if tail else 'yt-dlp lỗi'}"

    line = next((ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("{")), "")
    try:
        data = json.loads(line) if line else {}
    except json.JSONDecodeError:
        data = {}

    channel_id = str(data.get("channel_id") or "").strip()
    handle = str(data.get("uploader") or "").strip().lstrip("@")
    if not channel_id:
        return None, "Video này không có channel_id — thử link video khác của cùng kênh."
    if not handle:
        handle = channel_id[:24]
    return ("tiktok", f"tiktokuser:{channel_id}", handle), ""



def _load_rest_state() -> dict[str, dict]:
    """Trạng thái nghỉ của nguồn, khoá = id nguồn (chuỗi). Hỏng / chưa có file → rỗng."""
    try:
        with open(config.VIRAL_SOURCE_REST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_rest_state(state: dict[str, dict]) -> None:
    try:
        config.VIRAL_SOURCE_REST_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.VIRAL_SOURCE_REST_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(config.VIRAL_SOURCE_REST_FILE)
    except OSError as exc:
        logger.warning("[VIRAL_SOURCES] Không ghi được trạng thái nghỉ: %s", exc)


@contextlib.contextmanager
def _rest_state_locked():
    """Đọc → sửa → ghi trạng thái nghỉ dưới khoá file: Maintenance và web (quét tay) có thể quét cùng lúc."""
    lock_path = config.VIRAL_SOURCE_REST_FILE.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = _load_rest_state()
            yield state
            _save_rest_state(state)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _rest_entry(state: dict[str, dict], src: ViralSource) -> dict:
    """Mục trạng thái của nguồn; bỏ qua mục cũ nếu nguồn đã đổi URL (hoặc id bị dùng lại)."""
    entry = state.get(str(src.id)) or {}
    return entry if entry.get("url") == src.url else {}


def _page_names() -> dict[str, str]:
    data = runtime_settings.get_json("BUFFER_CHANNELS") or []
    return {
        str(item["id"]).strip(): str(item.get("name") or item["id"]).strip()
        for item in data
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _notify(message: str) -> None:
    try:
        NotifierService._broadcast(message)
    except Exception as exc:  # tin báo hỏng không được làm hỏng vòng quét
        logger.warning("[VIRAL_SOURCES] Gửi Telegram lỗi: %s", exc)


def _note_scan_result(db: Session, src: ViralSource, found: int, error: str | None, now: int) -> None:
    """PLAN-161: cập nhật chuỗi lần quét rỗng; đủ ngưỡng thì cho nguồn nghỉ và báo một lần."""
    if error:
        return  # lỗi quét không phải dấu hiệu nguồn cạn
    with _rest_state_locked() as state:
        _apply_scan_result(db, state, src, found, now)


def _apply_scan_result(db: Session, state: dict[str, dict], src: ViralSource, found: int, now: int) -> None:
    key = str(src.id)
    name = src.handle or src.url
    entry = _rest_entry(state, src)
    if found > 0:
        if entry.get("notified"):
            _notify(f"🔔 Nguồn @{name} có lại {found} video mới — quét bình thường trở lại.")
            logger.info("[VIRAL_SOURCES] Nguồn %s có lại video (+%d), hết nghỉ", name, found)
        state.pop(key, None)
        return
    streak = int(entry.get("empty_streak") or 0) + 1
    entry["empty_streak"] = streak
    entry["url"] = src.url
    if streak >= EMPTY_SCANS_TO_REST:
        entry["rest_until"] = now + REST_HOURS * 3600
        logger.info(
            "[VIRAL_SOURCES] Nguồn %s cạn (%d lần quét liền không có video mới) — nghỉ %d giờ",
            name, streak, REST_HOURS,
        )
        if not entry.get("notified"):
            ready = SourceService._ready_by_page(db)
            names = _page_names()
            pages = "\n".join(
                f"• {names.get(p, p)}: còn {ready.get(p, 0)} video chưa hẹn" for p in src.target_pages_list if p
            )
            _notify(
                f"🔕 Nguồn @{name} hết video mới ({streak} lần quét liền) — bot tự nghỉ, "
                f"{REST_HOURS} giờ sau tự thử lại.\n{pages}\nKênh sắp hết bài thì cần thêm nguồn mới."
            )
            entry["notified"] = True
    state[key] = entry



def _revive_sources_for_starving_pages(db: Session, now: int) -> list[int]:
    """PLAN-164: kênh thiếu bài mà không còn nguồn nào đang quét → bật lại một nguồn đang tắt của kênh đó.

    Trả danh sách id nguồn vừa bật. Mỗi kênh tối đa một nguồn mỗi vòng.
    """
    all_sources = db.query(ViralSource).order_by(
        ViralSource.last_scanned_at.asc().nullsfirst(), ViralSource.id.asc()
    ).all()
    if not all_sources:
        return []
    rest = _load_rest_state()
    ready = SourceService._ready_by_page(db)

    def awake(src: ViralSource) -> bool:
        return src.enabled and int(_rest_entry(rest, src).get("rest_until") or 0) <= now

    active_pages = {
        page for (page,) in db.query(Job.target_page)
        .filter(Job.platform == "buffer", Job.created_at >= now - ACTIVE_PAGE_DAYS * 86400)
        .distinct()
        if page
    }
    pages = {p for src in all_sources for p in src.target_pages_list if p and p in active_pages}
    starving = sorted(
        p for p in pages
        if ready.get(p, 0) < LOW_READY
        and not any(awake(src) and p in src.target_pages_list for src in all_sources)
    )
    if not starving:
        return []

    revived: list[int] = []
    names = _page_names()
    with _rest_state_locked() as state:
        for page in starving:
            for src in all_sources:
                if src.enabled or page not in src.target_pages_list or src.id in revived:
                    continue
                if now - int(src.updated_at or 0) < REVIVE_MIN_OFF_SEC:
                    continue  # chủ bot vừa tắt — để yên
                mark = state.get(f"revive:{src.id}") or {}
                if now - int(mark.get("at") or 0) < REVIVE_COOLDOWN_SEC:
                    continue
                src.enabled = True
                db.commit()
                state[f"revive:{src.id}"] = {"at": now, "page": page, "url": src.url}
                state.pop(str(src.id), None)  # bắt đầu lại chuỗi quét rỗng từ 0
                revived.append(src.id)
                name = src.handle or src.url
                logger.info("[VIRAL_SOURCES] Kênh %s thiếu bài (%d) → tự bật lại nguồn %s", page[-6:], ready.get(page, 0), name)
                _notify(
                    f"🔌 Kênh {names.get(page, page)} còn {ready.get(page, 0)} video chưa hẹn, không còn nguồn nào đang quét "
                    f"→ bot tự bật lại nguồn @{name}. Không muốn dùng nguồn này thì xoá nguồn."
                )
                break
    return revived


class SourceService:
    """Hợp đồng ADR-019 mục 2."""

    # ---- detect / CRUD -------------------------------------------------
    @staticmethod
    def detect_channel(url: str) -> tuple[str, str, str] | None:
        """``(platform, canonical_url, handle)`` cho URL kênh; ``None`` nếu không phải kênh hỗ trợ."""
        found, _ = _classify(url)
        return found

    @staticmethod
    def reject_reason(url: str) -> str:
        """Lý do từ chối (rỗng nếu URL là kênh hợp lệ) — cho UI hiện message."""
        found, reason = _classify(url)
        return "" if found else reason

    @staticmethod
    def list_sources(db: Session) -> list[ViralSource]:
        return db.query(ViralSource).order_by(ViralSource.id.asc()).all()

    @staticmethod
    def add_source(
        db: Session,
        url: str,
        *,
        min_views: int | None = None,
        max_videos: int | None = None,
        target_page: str | None = None,
        target_pages: list[str] | None = None,
    ) -> tuple[bool, str, int | None]:
        """
        ADR-020: ``target_pages`` = danh sách Page đích (mỗi video nhân bản ra tất cả).
        ``target_page`` cũ vẫn dùng được (UI cũ) — coi như danh sách 1 phần tử.
        """
        found, reason = _classify(url)
        if not found and reason == MSG_VIDEO_LINK and "tiktok.com" in (url or "").lower():
            # ADR-028: link video TikTok không còn bị từ chối thẳng — dò ra kênh từ chính nó.
            found, reason = _resolve_tiktok_user_from_video(url)
        if not found:
            return False, reason, None
        platform, canonical, handle = found
        existing = db.query(ViralSource).filter(ViralSource.url == canonical).first()
        if existing:
            return False, f"Nguồn đã có (#{existing.id}): {canonical}", existing.id
        src = ViralSource(
            platform=platform,
            url=canonical,
            handle=handle,
            min_views=int(min_views) if min_views not in (None, "") else None,
            max_videos=int(max_videos) if max_videos not in (None, "") else None,
            enabled=True,
            last_found=0,
        )
        # setter chuẩn hoá (strip, bỏ rỗng, bỏ trùng, giữ thứ tự) rồi ghi cả target_page đầu tiên
        src.target_pages_list = target_pages if target_pages else [target_page or ""]
        db.add(src)
        db.commit()
        db.refresh(src)
        return True, f"Đã thêm nguồn {platform} @{handle}", src.id

    @staticmethod
    def set_enabled(db: Session, source_id: int, enabled: bool) -> bool:
        src = db.get(ViralSource, source_id)
        if not src:
            return False
        src.enabled = bool(enabled)
        db.commit()
        return True

    @staticmethod
    def update_source(
        db: Session,
        source_id: int,
        *,
        min_views=None,
        max_videos=None,
        target_pages: list[str] | None = None,
    ) -> tuple[bool, str]:
        """
        Sửa tại chỗ Min views / Max video / Page đích của một nguồn (ADR-026).

        Rỗng (``None`` hoặc ``""``) nghĩa là **về mặc định** — ghi NULL để nguồn dùng lại
        ``viral.min_views`` / ``viral.max_videos_per_channel``; KHÔNG phải "giữ số cũ".
        ``target_pages`` rỗng ⇒ xoá cả ``target_pages`` lẫn ``target_page`` legacy, để
        "đã xoá hết Page" không còn sót một Page cũ ở nguồn sự thật thứ hai.

        ``url`` / ``platform`` / ``handle`` không sửa được — đổi kênh thì xoá rồi thêm mới.
        Không raise: giá trị sai ⇒ ``(False, thông báo)`` và **không ghi gì**.
        """
        src = db.get(ViralSource, source_id)
        if not src:
            return False, f"Không tìm thấy nguồn #{source_id}"

        def _opt_int(raw, label: str):
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                return True, None, ""
            try:
                return True, int(str(raw).strip()), ""
            except (TypeError, ValueError):
                return False, None, f"{label} phải là số nguyên."

        ok, new_min, msg = _opt_int(min_views, "Min views")
        if not ok:
            return False, msg
        ok, new_max, msg = _opt_int(max_videos, "Max video/lần")
        if not ok:
            return False, msg
        if new_min is not None and new_min < 0:
            return False, "Min views không được âm."
        if new_max is not None and not 1 <= new_max <= MAX_VIDEOS_CAP:
            return False, f"Max video/lần phải trong khoảng 1–{MAX_VIDEOS_CAP}."

        src.min_views = new_min
        src.max_videos = new_max
        if target_pages is not None:
            src.target_pages_list = list(target_pages)
        db.commit()
        db.refresh(src)

        pages = len(src.target_pages_list)
        shown_min = f"{new_min:,}" if new_min is not None else "mặc định"
        shown_max = new_max if new_max is not None else "mặc định"
        shown_pages = f"{pages} Page đích" if pages else "không Page đích"
        return True, (
            f"Đã lưu nguồn @{src.handle or src.url} — min views {shown_min}, "
            f"max video {shown_max}, {shown_pages}."
        )

    @staticmethod
    def delete_source(db: Session, source_id: int) -> bool:
        src = db.get(ViralSource, source_id)
        if not src:
            return False
        db.delete(src)
        db.commit()
        return True

    @staticmethod
    def waiting_count(db: Session, source_id: int) -> int:
        """Video trạng thái NEW gắn đúng nguồn này. Video không gắn nguồn không đếm."""
        return (
            db.query(ViralMaterial)
            .filter(
                ViralMaterial.source_id == source_id,
                ViralMaterial.status == ViralStatus.NEW,
            )
            .count()
        )

    @staticmethod
    def set_source_limits(
        db: Session,
        source_id: int,
        *,
        min_views=None,
        max_videos=None,
    ) -> tuple[bool, str]:
        """
        Chỉ sửa mức xem và số video tối đa của một nguồn.

        Rỗng nghĩa là ghi NULL để lần quét dùng mức chung. Không đụng trang đích.
        Giá trị sai thì không ghi gì.
        """
        src = db.get(ViralSource, source_id)
        if not src:
            return False, f"Không tìm thấy nguồn #{source_id}"

        def _opt_int(raw, label: str):
            if raw is None or (isinstance(raw, str) and not str(raw).strip()):
                return True, None, ""
            try:
                return True, int(str(raw).strip()), ""
            except (TypeError, ValueError):
                return False, None, f"{label} phải là số nguyên."

        ok, new_min, msg = _opt_int(min_views, "Min views")
        if not ok:
            return False, msg
        ok, new_max, msg = _opt_int(max_videos, "Max video/lần")
        if not ok:
            return False, msg
        if new_min is not None and new_min < 0:
            return False, "Min views không được âm."
        if new_max is not None and not 1 <= new_max <= MAX_VIDEOS_CAP:
            return False, f"Max video/lần phải trong khoảng 1–{MAX_VIDEOS_CAP}."

        src.min_views = new_min
        src.max_videos = new_max
        db.commit()
        db.refresh(src)
        if new_min is None and new_max is None:
            return True, f"Nguồn #{source_id} dùng lại mức chung."
        xem = f"{new_min:,}" if new_min is not None else "chung"
        toi_da = str(new_max) if new_max is not None else "chung"
        return True, f"Nguồn #{source_id}: mức xem {xem}, tối đa {toi_da}."

    # ---- scan ----------------------------------------------------------
    @staticmethod
    def scan_source(db: Session, source: ViralSource) -> tuple[int, int, str | None]:
        """Quét 1 nguồn → tạo material NEW. Trả ``(found, skipped, error|None)``; không raise."""
        if not source.enabled:
            return 0, 0, None
        min_views = source.min_views if source.min_views is not None else _setting_int(
            db, "viral.min_views", getattr(config, "VIRAL_MIN_VIEWS", 10000)
        )
        shared_max = _setting_int(
            db, "viral.max_videos_per_channel", getattr(config, "VIRAL_MAX_VIDEOS_PER_CHANNEL", 50)
        )
        accept_cap = source.max_videos if source.max_videos is not None else shared_max
        if not accept_cap or accept_cap <= 0:
            accept_cap = MAX_VIDEOS_CAP
        accept_cap = min(int(accept_cap), MAX_VIDEOS_CAP)
        shared_cap = shared_max if shared_max and shared_max > 0 else accept_cap
        shared_cap = min(int(shared_cap), MAX_VIDEOS_CAP)
        fetch_window = min(max(accept_cap, shared_cap), MAX_VIDEOS_CAP)

        found = skipped = 0
        error: str | None = None
        now = time.time()
        tracker = _load_rate_limits() if source.platform == "tiktok" else {}
        if tracker.get(source.url, 0) > now:
            wait_min = int((tracker[source.url] - now) / 60)
            error = f"Đang bị rate limit, thử lại sau {wait_min} phút"
        elif source.platform == "facebook":
            logger.info("[VIRAL_SOURCES] Scan Facebook %s (max=%d)", source.url, accept_cap)
            try:
                from app.features.viral_intake.facebook_scraper import scan_facebook_reels
                reels = scan_facebook_reels(source.url, max_videos=accept_cap)
                seen_this_run: set[str] = set()
                for r_url in reels:
                    if found >= accept_cap:
                        break
                    clean_url = (r_url or "").strip()
                    if not clean_url:
                        continue
                    variants = _www_variants(clean_url)
                    if clean_url in seen_this_run or db.query(ViralMaterial.id).filter(ViralMaterial.url.in_(variants)).first():
                        skipped += 1
                        continue
                    mat = ViralMaterial(
                        url=clean_url,
                        platform="facebook",
                        title=f"Facebook Reel {source.handle or ''}".strip(),
                        views=0,
                        scraped_by_account_id=None,
                        status=ViralStatus.NEW,
                        source_id=source.id,
                    )
                    mat.target_pages_list = source.target_pages_list
                    db.add(mat)
                    seen_this_run.add(clean_url)
                    found += 1
            except Exception as exc:
                error = f"Lỗi quét Facebook: {exc}"
        else:
            # TikTok chặn IP lạ bằng trang kiểm tra bot — giả Chrome qua được, nhưng CHỈ khi có
            # curl_cffi (xem `impersonate_args`); bật cứng là hỏng máy đang chạy tốt.
            extra = impersonate_args() if source.platform == "tiktok" else ()
            cmd = yt_dlp_cmd(
                "--flat-playlist", "--dump-json", "--playlist-end", str(fetch_window),
                "--no-warnings", *extra, source.url,
            )
            logger.info(
                "[VIRAL_SOURCES] Scan %s (max=%d, fetch=%d, min_views=%d)",
                source.url, accept_cap, fetch_window, min_views,
            )
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=SCAN_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                result, error = None, f"yt-dlp timeout sau {SCAN_TIMEOUT_SEC}s"
            except (FileNotFoundError, OSError) as exc:
                result, error = None, f"Không chạy được yt-dlp: {exc}"
            if result is not None and result.returncode != 0:
                stderr = (result.stderr or "").strip()
                low = stderr.lower()
                if source.platform == "tiktok" and ("429" in stderr or "rate limit" in low or "too many" in low):
                    tracker[source.url] = now + RATE_LIMIT_BACKOFF_HOURS * 3600
                    _save_rate_limits(tracker)
                error = humanize_scan_error(source.platform, stderr) if stderr else f"yt-dlp exit {result.returncode}"
            if result is not None and error is None:
                found, skipped = SourceService._ingest_lines(
                    db, source, result.stdout or "", min_views, accept_cap,
                )

        source.last_scanned_at = int(now_ts())
        source.last_found = found
        source.last_error = (error[:_ERROR_MAX_LEN] if error else None)
        db.commit()
        if error:
            logger.warning("[VIRAL_SOURCES] %s: %s", source.url, error[:_ERROR_MAX_LEN])
        else:
            logger.info("[VIRAL_SOURCES] %s: found=%d skipped=%d", source.url, found, skipped)
        return found, skipped, error

    @staticmethod
    def _ingest_lines(
        db: Session, source: ViralSource, stdout: str, min_views: int, max_accept: int,
    ) -> tuple[int, int]:
        found = skipped = 0
        seen_this_run: set[str] = set()
        for line in stdout.splitlines():
            if found >= max_accept:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            try:
                views = int(data.get("view_count") or 0)
            except (TypeError, ValueError):
                views = 0
            url = _video_url(source.platform, source.handle or "", data)
            if not url:
                continue
            if views < min_views:
                skipped += 1
                continue
            variants = _www_variants(url)
            if url in seen_this_run or db.query(ViralMaterial.id).filter(ViralMaterial.url.in_(variants)).first():
                skipped += 1
                continue
            title = str(data.get("title") or "")[:200]
            mat = ViralMaterial(
                url=url,
                platform=source.platform,
                title=title,
                views=views,
                scraped_by_account_id=None,
                status=ViralStatus.NEW,
                source_id=source.id,
            )
            # ADR-020: chép danh sách Page của nguồn sang material; setter cũng ghi
            # `target_page` = Page đầu tiên để mọi chỗ đọc `mat.target_page` cũ không vỡ.
            mat.target_pages_list = source.target_pages_list
            db.add(mat)
            seen_this_run.add(url)
            found += 1
        return found, skipped

    @staticmethod
    def _ready_by_page(db: Session) -> dict[str, int]:
        """Video READY chưa hẹn Buffer. Video đã hẹn vẫn READY khi sync «đã đăng» tắt, nên phải bỏ ra (PLAN-160)."""
        scheduled = (
            db.query(Job.id)
            .filter(
                Job.platform == "buffer",
                Job.status == JobStatus.DONE,
                Job.viral_material_id == ViralMaterial.id,
                Job.target_page == ViralMaterial.target_page,
            )
            .exists()
        )
        rows = (
            db.query(ViralMaterial.target_page, func.count(ViralMaterial.id))
            .filter(
                ViralMaterial.status == ViralStatus.READY,
                ViralMaterial.target_page.isnot(None),
                ~scheduled,
            )
            .group_by(ViralMaterial.target_page)
            .all()
        )
        return {page: int(n) for page, n in rows if page}

    @staticmethod
    def scan_all(db: Session, *, only_due: bool = True) -> dict:
        """Quét mọi nguồn ``enabled`` (``only_due``: bỏ nguồn quét chưa quá ``viral.source_scan_interval_min``)."""
        interval_sec = max(1, _setting_int(db, "viral.source_scan_interval_min", 60)) * 60
        now = int(now_ts())
        revived: list[int] = []
        if only_due:
            try:
                revived = _revive_sources_for_starving_pages(db, now)
            except Exception:  # tự bật nguồn hỏng không được dừng vòng quét
                db.rollback()
                logger.exception("[VIRAL_SOURCES] Tự bật lại nguồn lỗi")
        sources = (
            db.query(ViralSource)
            .filter(ViralSource.enabled == True)  # noqa: E712
            .order_by(ViralSource.last_scanned_at.asc().nullsfirst(), ViralSource.id.asc())
            .all()
        )
        summary = {"found": 0, "scanned": 0, "errors": 0, "skipped": 0, "paused": 0, "resting": 0,
                   "revived": len(revived)}
        rest = _load_rest_state()
        if only_due:
            sources = [s for s in sources if not s.last_scanned_at or now - int(s.last_scanned_at) >= interval_sec]
            # PLAN-161: nguồn cạn đang nghỉ thì chờ tới hạn rồi tự thử lại.
            awake = []
            for src in sources:
                until = int(_rest_entry(rest, src).get("rest_until") or 0)
                if until > now:
                    summary["resting"] += 1
                    continue
                awake.append(src)
            sources = awake
            # PLAN-071: page đủ video chờ đăng thì quét thêm chỉ để video quá hạn bị dọn.
            enough = max(0, _setting_int(db, "viral.source_skip_ready_per_page", 15))
            if enough and sources:
                ready = SourceService._ready_by_page(db)
                due = []
                for src in sources:
                    pages = [p for p in src.target_pages_list if p]
                    if pages and all(ready.get(p, 0) >= enough for p in pages):
                        summary["paused"] += 1
                        logger.info(
                            "[VIRAL_SOURCES] Bỏ quét %s — page đích đã đủ %d video sẵn sàng (%s)",
                            src.handle or src.url, enough,
                            ", ".join(f"{p[-6:]}={ready.get(p, 0)}" for p in pages),
                        )
                        continue
                    due.append(src)
                sources = due

        for idx, src in enumerate(sources):
            if idx:
                time.sleep(random.uniform(2, 5))
            try:
                found, skipped, error = SourceService.scan_source(db, src)
            except Exception as exc:  # phòng hờ — scan_source đã nuốt lỗi yt-dlp
                db.rollback()
                logger.exception("[VIRAL_SOURCES] scan_source #%s crashed", src.id)
                found, skipped, error = 0, 0, str(exc)
            summary["found"] += found
            summary["skipped"] += skipped
            summary["scanned"] += 1
            if error:
                summary["errors"] += 1
            try:
                _note_scan_result(db, src, found, error, int(now_ts()))
            except Exception:  # trạng thái nghỉ hỏng không được dừng vòng quét các nguồn còn lại
                db.rollback()
                logger.exception("[VIRAL_SOURCES] Ghi trạng thái nghỉ nguồn #%s lỗi", src.id)
        return summary
