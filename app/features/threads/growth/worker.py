"""Worker Threads Growth (PM2 ``Threads_Growth``, PLAN-158): quét Threads theo từ khóa → AI viết reply →
tự đăng bài đủ điểm trong hạn mức; bài điểm thấp hơn chờ duyệt (web / Telegram).

Mỗi nhịp (``TICK_SEC``):
- ``growth.enabled`` tắt hoặc chưa đăng nhập → nghỉ.
- Tới hạn ``growth.scan_interval_min`` → vòng quét (mở trình duyệt, tìm từng từ khóa, đóng trình duyệt) → nhận bài.
- Có bài ``approved`` + còn hạn mức → mở trình duyệt đăng lần lượt, giãn cách ngẫu nhiên.
Checkpoint / mất đăng nhập → tự tắt ``growth.enabled`` + báo Telegram; không thử vượt.

Chạy tay một vòng: ``python -m app.features.threads.growth.worker --once``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from app.core import settings
from app.core.database.core import SessionLocal
from app.features.threads.adapter import ThreadsSessionInvalidError
from app.features.threads.growth import notify
from app.features.threads.growth import session as growth_session
from app.features.threads.growth.browser import GrowthBrowser
from app.features.threads.growth.config import TargetBot, WorkerConfig, load_profiles, load_worker_config
from app.features.threads.growth.evaluator import GrowthEvaluator
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost, is_vietnamese
from app.utils.logger import setup_shared_logger

logger = logging.getLogger("threads_growth")

TICK_SEC = 60


@dataclass
class CycleReport:
    scanned: int = 0
    ingested: int = 0
    auto: int = 0
    pending: int = 0
    posted: int = 0
    failed: int = 0
    quota_note: str = ""
    errors: List[str] = field(default_factory=list)
    posted_items: List[Dict] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {**self.__dict__, "errors": list(self.errors), "posted_items": list(self.posted_items)}


class GrowthWorker:
    def __init__(
        self,
        runner: Optional[GrowthRunner] = None,
        browser_factory: Callable[[str], GrowthBrowser] = GrowthBrowser,
        db_factory=SessionLocal,
        notifier=notify,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.runner = runner or GrowthRunner()
        self.browser_factory = browser_factory
        self.db_factory = db_factory
        self.notify = notifier
        self.sleep = sleep
        self.now = now
        self.last_scan: Optional[datetime] = None

    # ── tiện ích ───────────────────────────────────────────────
    def _profile_path(self) -> Optional[str]:
        with self.db_factory() as db:
            st = growth_session.status(db)
        if not st.ready:
            logger.info("growth: chưa đăng nhập Threads (%s) — nghỉ", st.login_status)
            return None
        if growth_session.profile_locked():
            logger.info("growth: profile đang mở (cửa sổ đăng nhập?) — nghỉ")
            return None
        return st.profile_path

    def _disable(self, reason: str) -> None:
        logger.error("growth: checkpoint / mất đăng nhập → tự tắt: %s", reason)
        with self.db_factory() as db:
            settings.upsert_setting(db, "growth.enabled", "false", updated_by="threads_growth_worker")
            growth_session.mark(db, False, reason)
        self.notify.send(self.notify.checkpoint_text(reason))

    def _fresh(self, post: ScannedPost, cfg: WorkerConfig) -> bool:
        if cfg.top_level_only and post.is_reply:
            return False
        if cfg.vietnamese_only and not is_vietnamese(post.content):
            return False
        if self.runner.storage.is_thread_scanned(post.thread_id):
            return False
        if post.created_at and post.created_at < self.now() - timedelta(hours=cfg.max_post_age_hours):
            return False
        if cfg.author_cooldown_days and self.runner.storage.replied_author_since(
            post.author, self.now() - timedelta(days=cfg.author_cooldown_days)
        ):
            return False
        return True

    # ── quét ───────────────────────────────────────────────────
    def scan(self, profile_path: str, cfg: WorkerConfig, report: CycleReport) -> List[tuple[ScannedPost, TargetBot]]:
        found: Dict[str, tuple[ScannedPost, TargetBot]] = {}
        jobs = [(bot, kw) for bot, prof in load_profiles().items() for kw in prof.keywords]
        random.shuffle(jobs)  # không quét cùng một thứ tự mỗi vòng
        with self.browser_factory(profile_path) as browser:
            for bot, kw in jobs:
                try:
                    posts = browser.search_recent(kw, limit=cfg.posts_per_keyword)
                except ThreadsSessionInvalidError:
                    raise
                except Exception as exc:
                    report.errors.append(f"tìm «{kw}»: {exc}")
                    logger.warning("growth: tìm %r lỗi: %s", kw, exc)
                    continue
                report.scanned += len(posts)
                for p in posts:
                    if p.thread_id not in found and self._fresh(p, cfg):
                        found[p.thread_id] = (p, bot)
                self.sleep(random.uniform(4, 9))
        return list(found.values())

    def ingest(self, items: List[tuple[ScannedPost, TargetBot]], cfg: WorkerConfig, report: CycleReport) -> None:
        async def _all():
            for post, kw_bot in items:
                bot = GrowthEvaluator.classify_target_bot(post.content) or kw_bot
                pid = await self.runner.ingest_scanned_post(
                    post, forced_bot=bot, auto_post_min=cfg.auto_post_min_relevance
                )
                if not pid:
                    continue
                report.ingested += 1
                row = self.runner.storage.get_post_by_id(pid)
                if row and row["status"] == "approved":
                    report.auto += 1
                else:
                    report.pending += 1

        asyncio.run(_all())
        if not cfg.telegram_review:
            return  # tự động hoàn toàn: không hỏi duyệt từng bài, chỉ báo cáo sau vòng
        for row in self.runner.storage.unnotified_pending(limit=10):
            if self.notify.notify_pending(row):
                self.runner.storage.mark_notified(row["id"])

    # ── đăng ───────────────────────────────────────────────────
    def post_queue(self, profile_path: str, report: CycleReport) -> None:
        queue = self.runner.storage.approved_queue(limit=20)
        if not queue:
            return
        quota = self.runner.posting_quota(self.now())
        if not quota.allowed:
            report.quota_note = quota.reason
            return
        with self.browser_factory(profile_path) as browser:
            for i, post in enumerate(queue):
                quota = self.runner.posting_quota(self.now())
                if not quota.allowed:
                    report.quota_note = quota.reason
                    break
                text = post.get("actual_reply") or post["suggested_reply"]
                try:
                    url = browser.reply(post["post_url"], text)
                except ThreadsSessionInvalidError:
                    raise
                except Exception as exc:
                    self.runner.mark_failed(post["id"], str(exc))
                    report.failed += 1
                    logger.warning("growth: đăng reply #%s lỗi: %s", post["id"], exc)
                else:
                    self.runner.mark_posted(post["id"], reply_url=url)
                    report.posted += 1
                    report.posted_items.append({
                        "id": post["id"], "bot": post["target_bot"], "variant": post["variant"],
                        "author": post["author"], "post_url": post["post_url"], "reply_url": url, "text": text,
                    })
                    logger.info("growth: đã reply #%s → %s", post["id"], url or post["post_url"])
                if i < len(queue) - 1:
                    self.sleep(self.runner.next_delay_sec())

    # ── nhịp ───────────────────────────────────────────────────
    def tick(self, force_scan: bool = False) -> Optional[CycleReport]:
        cfg = load_worker_config()
        if not cfg.enabled and not force_scan:
            return None
        profile = self._profile_path()
        if not profile:
            return None
        report = CycleReport()
        due = force_scan or self.last_scan is None or (
            self.now() - self.last_scan >= timedelta(minutes=cfg.scan_interval_min)
        )
        try:
            if due:
                self.last_scan = self.now()
                self.ingest(self.scan(profile, cfg, report), cfg, report)
            self.post_queue(profile, report)
        except ThreadsSessionInvalidError as exc:
            self._disable(str(exc))
            report.errors.append(str(exc))
            return report
        if due or report.posted or report.failed:
            logger.info("growth: vòng xong %s", report.as_dict())
            if report.posted or report.failed:
                self.notify.send(self.notify.cycle_text(report.as_dict()))
        return report

    def run_forever(self) -> None:
        logger.info("Threads_Growth worker started")
        while True:
            try:
                self.tick()
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("growth: lỗi vòng — thử lại sau")
            self.sleep(TICK_SEC + random.uniform(0, 15))


def main(argv: Optional[List[str]] = None) -> int:
    setup_shared_logger("app")
    setup_shared_logger("threads_growth")
    parser = argparse.ArgumentParser(description="Threads Growth worker")
    parser.add_argument("--once", action="store_true", help="Chạy đúng một vòng (quét + đăng) rồi thoát")
    args = parser.parse_args(argv)
    worker = GrowthWorker()
    if args.once:
        report = worker.tick(force_scan=True)
        print(report.as_dict() if report else "Không chạy (chưa đăng nhập / profile đang mở)")
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
