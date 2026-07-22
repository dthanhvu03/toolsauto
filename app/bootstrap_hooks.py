"""Register cross-feature hooks from composition root (ADR-007)."""
from __future__ import annotations

import random
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.core import feature_hooks
from app.core.account import get_discovery_keywords
from app.core.database.models import Account, DiscoveredChannel


def register_feature_hooks() -> None:
    from app.features.viral_intake.processor import ViralProcessorService
    from app.features.viral_intake.scan import get_default_min_views, run_tiktok_competitor_scan
    from app.features.viral_intake.discovery_scraper import DiscoveryScraper
    from app.features.telegram_bot.poller import TelegramPoller

    def viral_process_all(db: Session):
        return ViralProcessorService().process_all(db)

    def viral_tiktok_scan(db: Session):
        return run_tiktok_competitor_scan(db)

    def viral_min_views(db: Session):
        return get_default_min_views(db)

    def viral_force_discovery(db: Session) -> Tuple[List[DiscoveredChannel], List[str], int]:
        scraper = DiscoveryScraper()
        total_found = 0
        scan_log: List[str] = []
        accounts = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        for acc in accounts:
            keywords = get_discovery_keywords(acc)
            if not keywords:
                continue
            selected = random.sample(keywords, min(2, len(keywords)))
            for kw in selected:
                try:
                    found = scraper.discover_for_keyword(kw, acc.id, db)
                    total_found += found
                    scan_log.append(f"✅ '{acc.name}' / kw='{kw}': {found} kênh mới")
                except Exception as e:
                    scan_log.append(f"❌ '{acc.name}' / kw='{kw}': lỗi {str(e)[:80]}")
        return total_found, scan_log

    def viral_discover_keyword(keyword: str, account_id: int, db: Session) -> int:
        return DiscoveryScraper().discover_for_keyword(keyword, account_id, db)

    def telegram_make_poller(token: str, chat_id: str):
        return TelegramPoller(token, chat_id)

    feature_hooks.register("viral.process_all", viral_process_all)
    feature_hooks.register("viral.tiktok_scan", viral_tiktok_scan)
    feature_hooks.register("viral.min_views", viral_min_views)
    feature_hooks.register("viral.force_discovery", viral_force_discovery)
    feature_hooks.register("viral.discover_keyword", viral_discover_keyword)
    feature_hooks.register("telegram.make_poller", telegram_make_poller)
