"""
Chạy quét kênh TikTok đối thủ (từ Account.competitor_urls) → thêm ViralMaterial status=NEW.
Dùng cho: worker Maintenance (định kỳ 1h) và API quét thủ công (POST /viral/force-scan).
Kiểm tra trùng: video đã có trong bảng (bất kể target_page) thì bỏ qua.
"""
import json
import logging
from urllib.parse import urlparse, parse_qs

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Account, ViralMaterial, SystemState
from app.services.tiktok_scraper import TikTokScraper
import app.config as config

logger = logging.getLogger(__name__)


def get_default_min_views(db: Session) -> int:
    """Lấy ngưỡng view tối thiểu: ưu tiên system_state.viral_min_views, không có thì dùng config."""
    state = db.query(SystemState).filter(SystemState.id == 1).first()
    if state and getattr(state, "viral_min_views", None) is not None:
        return int(state.viral_min_views)
    return getattr(config, "VIRAL_MIN_VIEWS", 10000)


def get_default_max_videos_per_channel(db: Session) -> int:
    """Số video tối đa mỗi kênh. 0 hoặc None = lấy nhiều nhất (cap 500)."""
    state = db.query(SystemState).filter(SystemState.id == 1).first()
    val = None
    if state and getattr(state, "viral_max_videos_per_channel", None) is not None:
        val = int(state.viral_max_videos_per_channel)
    if val is None:
        val = getattr(config, "VIRAL_MAX_VIDEOS_PER_CHANNEL", 50)
    if val <= 0:
        return 500  # "lấy hết" = cap 500 để tránh timeout / rate limit
    return min(val, 500)


def _normalize_video_url(url: str) -> str:
    """Chuẩn hóa URL video (bỏ query, rstrip /) để so trùng."""
    if not url or not url.strip():
        return url or ""
    u = url.strip().split("?")[0].rstrip("/")
    return u


def run_tiktok_competitor_scan(db: Session) -> tuple[int, int]:
    """
    Quét tất cả kênh TikTok trong competitor_urls của các account active.
    Returns (total_new_videos, num_channels_scanned).
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
                url = entry.get("url", "")
                tp_raw = entry.get("target_page") or entry.get("target_pages")
            else:
                url = str(entry)
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
        return 0, 0

    logger.info("[VIRAL_SCAN] Scanning %d TikTok channels...", len(tiktok_channels))
    scraper = TikTokScraper()
    total_found = 0

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
            # Trùng video đã quét trước đó (bất kể target_page / account). So khớp cả URL đã chuẩn hóa và URL có query.
            existing = db.query(ViralMaterial).filter(
                or_(
                    ViralMaterial.url == norm_url,
                    ViralMaterial.url.like(norm_url + "?%"),
                )
            ).first()
            if existing:
                continue

            mat = ViralMaterial(
                url=norm_url,
                platform="tiktok",
                title=vid.get("title", "")[:200],
                views=vid.get("view_count", 0),
                scraped_by_account_id=account_id,
                target_page=channel_target_page,
                status="NEW",
            )
            db.add(mat)
            total_found += 1

        db.commit()

    logger.info("[VIRAL_SCAN] Done. %d new videos from %d channels.", total_found, len(tiktok_channels))
    return total_found, len(tiktok_channels)
