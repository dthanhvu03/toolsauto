"""
Chạy quét kênh TikTok đối thủ (từ Account.competitor_urls) → thêm ViralMaterial status=NEW.
Dùng cho: worker Maintenance (định kỳ 1h) và API quét thủ công (POST /viral/force-scan).
Kiểm tra trùng: video đã có trong bảng (bất kể target_page) thì bỏ qua.
PLAN-046: quota per handle/day + mega-views gate (runtime_settings).
"""
import json
import logging
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from sqlalchemy.orm import Session

from app.core.database.models import Account, ViralMaterial, SystemState
from app.core.account import AccountService
from app.features.viral_intake.tiktok_scraper import TikTokScraper
import app.config as config
from app.constants import ViralStatus


logger = logging.getLogger(__name__)


def get_default_min_views(db: Session) -> int:
    """Lấy ngưỡng view: SystemState → runtime_settings → config."""
    state = db.query(SystemState).filter(SystemState.id == 1).first()
    if state and getattr(state, "viral_min_views", None) is not None:
        return int(state.viral_min_views)
    try:
        from app.core import settings as runtime_settings

        v = runtime_settings.get_effective(db, "viral.min_views")
        if v is not None:
            return int(v)
    except Exception:
        pass
    return getattr(config, "VIRAL_MIN_VIEWS", 10000)


def get_default_max_videos_per_channel(db: Session) -> int:
    """Số video tối đa mỗi kênh. 0 hoặc None = lấy nhiều nhất (cap 500)."""
    state = db.query(SystemState).filter(SystemState.id == 1).first()
    val = None
    if state and getattr(state, "viral_max_videos_per_channel", None) is not None:
        val = int(state.viral_max_videos_per_channel)
    if val is None:
        try:
            from app.core import settings as runtime_settings

            v = runtime_settings.get_effective(db, "viral.max_videos_per_channel")
            if v is not None:
                val = int(v)
        except Exception:
            val = None
    if val is None:
        val = getattr(config, "VIRAL_MAX_VIDEOS_PER_CHANNEL", 50)
    if val <= 0:
        return 500  # "lấy hết" = cap 500 để tránh timeout / rate limit
    return min(val, 500)


def _diversify_config(db: Session) -> dict:
    """Read PLAN-046 diversify knobs (safe defaults)."""
    from app.core import settings as runtime_settings

    def _bool(key: str, default: bool) -> bool:
        try:
            v = runtime_settings.get_effective(db, key)
            if v is None:
                return default
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            return default

    def _int(key: str, default: int) -> int:
        try:
            v = runtime_settings.get_effective(db, key)
            return int(v) if v is not None else default
        except Exception:
            return default

    def _str(key: str, default: str) -> str:
        try:
            v = runtime_settings.get_effective(db, key)
            return str(v).strip().lower() if v is not None else default
        except Exception:
            return default

    return {
        "enabled": _bool("viral.diversify_enabled", True),
        "max_per_handle": _int("viral.max_clips_per_handle_per_day", 3),
        "quota_scope": _str("viral.quota_scope", "page"),
        "mega_threshold": _int("viral.mega_views_threshold", 2_000_000),
        "mega_action": _str("viral.mega_views_action", "flag"),
    }


def _day_start_ts() -> int:
    """Unix ts at local calendar day start (server local)."""
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def _normalize_video_url(url: str) -> str:
    """Chuẩn hóa URL video (bỏ query, rstrip /) để so trùng."""
    if not url or not url.strip():
        return url or ""
    u = url.strip().split("?")[0].rstrip("/")
    return u


def _count_handle_today(
    db: Session,
    handle: str,
    target_page: str | None,
    scope: str,
    day_start: int,
) -> int:
    if not handle:
        return 0
    q = db.query(ViralMaterial).filter(
        ViralMaterial.created_at >= day_start,
        ViralMaterial.url.ilike(f"%tiktok.com/@{handle}/%"),
    )
    if scope == "page" and target_page:
        q = q.filter(ViralMaterial.target_page == target_page)
    return int(q.count() or 0)


def run_tiktok_competitor_scan(db: Session) -> tuple[int, int, int, int]:
    """
    Quét tất cả kênh TikTok trong competitor_urls của các account active.
    Returns (total_new_videos, num_channels_scanned, skipped_quota, skipped_mega).
    """
    accounts = db.query(Account).filter(
        Account.is_active == True,
        Account.competitor_urls != None,
    ).all()

    tiktok_channels = []
    for acc in accounts:
        try:
            data = json.loads(acc.competitor_urls) if acc.competitor_urls else []
            if not isinstance(data, list):
                data = [{"url": str(data), "target_page": None}]
        except (json.JSONDecodeError, TypeError):
            data = [
                {"url": u.strip(), "target_page": None}
                for u in (acc.competitor_urls or "").split(",")
                if u.strip()
            ]

        for entry in data:
            if isinstance(entry, dict):
                url = AccountService.normalize_tiktok_source_url(entry.get("url", ""))
                tp_raw = entry.get("target_page") or entry.get("target_pages")
            else:
                url = AccountService.normalize_tiktok_source_url(str(entry))
                tp_raw = None
            if "tiktok.com/@" not in url.lower():
                continue
            if isinstance(tp_raw, list):
                for tp in tp_raw:
                    tiktok_channels.append((acc.id, url, tp))
            else:
                tiktok_channels.append((acc.id, url, tp_raw))

    if not tiktok_channels:
        logger.info("[VIRAL_SCAN] No TikTok competitor URLs found.")
        return 0, 0, 0, 0

    logger.info("[VIRAL_SCAN] Scanning %d TikTok channels...", len(tiktok_channels))
    scraper = TikTokScraper()
    total_found = 0
    skipped_quota = 0
    skipped_mega = 0

    # Prefetch normalized URL set once — tránh N+1 .first() mỗi video
    existing_norm_urls = {
        _normalize_video_url(u)
        for (u,) in db.query(ViralMaterial.url).all()
        if u
    }

    div = _diversify_config(db)
    day_start = _day_start_ts()
    # In-scan counters: handle(+page) → added this run (avoids re-query every video)
    session_quota: dict[str, int] = {}

    default_min_views = get_default_min_views(db)
    default_max_videos = get_default_max_videos_per_channel(db)
    for account_id, channel_url, channel_target_page in tiktok_channels:
        parsed = urlparse(channel_url)
        q_params = parse_qs(parsed.query)
        custom_min_views = int(q_params.get("min_views", [default_min_views])[0])
        custom_max = int(q_params.get("max_videos", [default_max_videos])[0])
        if custom_max <= 0:
            custom_max = 500
        custom_max = min(custom_max, 500)
        clean_url = channel_url.split("?")[0]

        videos = scraper.scrape_channel(clean_url, max_videos=custom_max, min_views=custom_min_views)

        for vid in videos:
            raw_url = vid.get("url") or ""
            norm_url = _normalize_video_url(raw_url)
            if not norm_url:
                continue
            if norm_url in existing_norm_urls:
                continue

            views = int(vid.get("view_count", 0) or 0)
            handle = AccountService.extract_tiktok_handle(norm_url) or AccountService.extract_tiktok_handle(channel_url)

            if div["enabled"]:
                mega_th = int(div["mega_threshold"] or 0)
                if mega_th > 0 and views >= mega_th and div["mega_action"] == "skip":
                    skipped_mega += 1
                    continue

                max_h = int(div["max_per_handle"] or 0)
                if max_h > 0 and handle:
                    scope = div["quota_scope"] if div["quota_scope"] in ("page", "global") else "page"
                    qkey = f"{handle}|{channel_target_page or ''}" if scope == "page" else handle
                    if qkey not in session_quota:
                        session_quota[qkey] = _count_handle_today(
                            db, handle, channel_target_page, scope, day_start
                        )
                    if session_quota[qkey] >= max_h:
                        skipped_quota += 1
                        continue

            mat = ViralMaterial(
                url=norm_url,
                platform="tiktok",
                title=vid.get("title", "")[:200],
                views=views,
                scraped_by_account_id=account_id,
                target_page=channel_target_page,
                status=ViralStatus.NEW,
            )
            db.add(mat)
            existing_norm_urls.add(norm_url)
            total_found += 1
            if div["enabled"] and handle and int(div["max_per_handle"] or 0) > 0:
                scope = div["quota_scope"] if div["quota_scope"] in ("page", "global") else "page"
                qkey = f"{handle}|{channel_target_page or ''}" if scope == "page" else handle
                session_quota[qkey] = session_quota.get(qkey, 0) + 1

        db.commit()

    logger.info(
        "[VIRAL_SCAN] Done. %d new, quota_skip=%d mega_skip=%d from %d channels.",
        total_found,
        skipped_quota,
        skipped_mega,
        len(tiktok_channels),
    )
    return total_found, len(tiktok_channels), skipped_quota, skipped_mega
