"""
Nguồn quét tự động (ADR-019) — kênh TikTok / YouTube Shorts độc lập với account.

``SourceService`` là hợp đồng cố định giữa UI (router/template) và backend:
``list_sources`` / ``add_source`` / ``set_enabled`` / ``delete_source`` / ``scan_source`` /
``scan_all``. Quét bằng ``yt-dlp --flat-playlist --dump-json`` (không cookie, không browser);
video đạt ``min_views`` được ghi thành ``ViralMaterial(NEW, scraped_by_account_id=None)``
để sweep nền nhặt (ADR-018: không account → READY).
"""
from __future__ import annotations

import json
import logging
import random
import re
import subprocess
import time
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy.orm import Session

import app.config as config
from app.constants import ViralStatus
from app.core import settings as runtime_settings
from app.core.database.models import ViralMaterial, ViralSource
from app.core.database.models.base import now_ts
from app.core.yt_dlp_path import yt_dlp_cmd
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
        if "failed to parse json" in low:
            # Đo 2026-09-11: cùng nguồn, cùng lệnh chạy bằng yt-dlp 2026.08.19 ra 21 video 3/3 lần;
            # máy bot của Owner báo câu này ⇒ hoặc yt-dlp cũ, hoặc TikTok trả trang kiểm tra bot.
            return "TikTok trả về trang không phải dữ liệu." + (
                _ytdlp_diagnosis() or " Thường do yt-dlp cũ hoặc bị chặn tạm — xem trang Sức khỏe."
            )
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
    for prefix in ("www.", "m.", "vm.", "vt."):
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

    if host in ("facebook.com", "fb.watch", "fb.com", "instagram.com"):
        return None, MSG_FB_IG
    return None, MSG_UNKNOWN


def _www_variants(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    bare = host[4:] if host.startswith("www.") else host
    tail = parts.path + (f"?{parts.query}" if parts.query else "")
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
    cmd = yt_dlp_cmd("--dump-json", "--no-warnings", "--playlist-items", "1", video_url)
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
        src.target_pages_list = list(target_pages or [])
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

    # ---- scan ----------------------------------------------------------
    @staticmethod
    def scan_source(db: Session, source: ViralSource) -> tuple[int, int, str | None]:
        """Quét 1 nguồn → tạo material NEW. Trả ``(found, skipped, error|None)``; không raise."""
        min_views = source.min_views if source.min_views is not None else _setting_int(
            db, "viral.min_views", getattr(config, "VIRAL_MIN_VIEWS", 10000)
        )
        max_videos = source.max_videos if source.max_videos is not None else _setting_int(
            db, "viral.max_videos_per_channel", getattr(config, "VIRAL_MAX_VIDEOS_PER_CHANNEL", 50)
        )
        if not max_videos or max_videos <= 0:
            max_videos = MAX_VIDEOS_CAP
        max_videos = min(int(max_videos), MAX_VIDEOS_CAP)

        found = skipped = 0
        error: str | None = None
        now = time.time()
        tracker = _load_rate_limits() if source.platform == "tiktok" else {}
        if tracker.get(source.url, 0) > now:
            wait_min = int((tracker[source.url] - now) / 60)
            error = f"Đang bị rate limit, thử lại sau {wait_min} phút"
        else:
            cmd = yt_dlp_cmd(
                "--flat-playlist", "--dump-json", "--playlist-end", str(max_videos),
                "--no-warnings", source.url,
            )
            logger.info("[VIRAL_SOURCES] Scan %s (max=%d, min_views=%d)", source.url, max_videos, min_views)
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
                found, skipped = SourceService._ingest_lines(db, source, result.stdout or "", min_views)

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
    def _ingest_lines(db: Session, source: ViralSource, stdout: str, min_views: int) -> tuple[int, int]:
        found = skipped = 0
        seen_this_run: set[str] = set()
        for line in stdout.splitlines():
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
            )
            # ADR-020: chép danh sách Page của nguồn sang material; setter cũng ghi
            # `target_page` = Page đầu tiên để mọi chỗ đọc `mat.target_page` cũ không vỡ.
            mat.target_pages_list = source.target_pages_list
            db.add(mat)
            seen_this_run.add(url)
            found += 1
        return found, skipped

    @staticmethod
    def scan_all(db: Session, *, only_due: bool = True) -> dict:
        """Quét mọi nguồn ``enabled`` (``only_due``: bỏ nguồn quét chưa quá ``viral.source_scan_interval_min``)."""
        interval_sec = max(1, _setting_int(db, "viral.source_scan_interval_min", 60)) * 60
        now = int(now_ts())
        sources = (
            db.query(ViralSource)
            .filter(ViralSource.enabled == True)  # noqa: E712
            .order_by(ViralSource.last_scanned_at.asc().nullsfirst(), ViralSource.id.asc())
            .all()
        )
        if only_due:
            sources = [s for s in sources if not s.last_scanned_at or now - int(s.last_scanned_at) >= interval_sec]

        summary = {"found": 0, "scanned": 0, "errors": 0, "skipped": 0}
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
        return summary
