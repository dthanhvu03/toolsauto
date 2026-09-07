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
MAX_VIDEOS_CAP = 500
_ERROR_MAX_LEN = 200

MSG_VIDEO_LINK = "Đây là link video, không phải kênh — dùng ô dán link video ở trên."
MSG_FB_IG = (
    "Facebook/Instagram không liệt kê được danh sách video (yt-dlp không hỗ trợ) — "
    "chỉ dán từng link video ở ô dán link."
)
MSG_UNKNOWN = "Không nhận diện được kênh. Dán URL kênh TikTok (@handle) hoặc YouTube (@handle, /channel/…)."

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
    ) -> tuple[bool, str, int | None]:
        found, reason = _classify(url)
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
            target_page=(target_page or "").strip() or None,
            enabled=True,
            last_found=0,
        )
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
                error = stderr.splitlines()[-1] if stderr else f"yt-dlp exit {result.returncode}"
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
            db.add(
                ViralMaterial(
                    url=url,
                    platform=source.platform,
                    title=title,
                    views=views,
                    scraped_by_account_id=None,
                    target_page=source.target_page,
                    status=ViralStatus.NEW,
                )
            )
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
