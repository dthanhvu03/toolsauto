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
import hashlib
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from app.core import settings
from app.core.database.core import SessionLocal
from app.features.threads.adapter import ThreadsSessionInvalidError
from app.features.threads.growth import content, conversions, notify
from app.features.threads.growth import session as growth_session
from app.features.threads.growth.browser import GrowthBrowser
from app.features.threads.growth.config import ABVariant, TargetBot, WorkerConfig, load_profiles, load_worker_config
from app.features.threads.growth.evaluator import GrowthEvaluator
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost, is_vietnamese
from app.utils.logger import setup_shared_logger

logger = logging.getLogger("threads_growth")

TICK_SEC = 60
FOLLOWUP_EVERY = timedelta(minutes=20)   # nhịp kiểm người hỏi lại
FOLLOWUP_RECHECK = timedelta(hours=3)    # mỗi reply của mình kiểm lại tối đa 3 giờ / lần
FOLLOWUP_PAGES = 6                       # số reply của mình mở mỗi nhịp
OWN_POST_WINDOW = timedelta(hours=2)     # khung giờ đăng bài riêng còn hiệu lực bao lâu
OWN_POST_RETRY = timedelta(minutes=15)   # AI lỗi → thử lại trong khung
REWRITE_EVERY = timedelta(minutes=30)    # thử cho AI viết lại bài đang dùng câu mẫu
# 06/11: Playwright treo ngay sau khi mở trình duyệt (16 phút không một dòng log, mọi lệnh đều có timeout 60s) — PM2 không
# biết để restart. Mọi vòng lặp của worker đều đi qua ``sleep`` → hẹn giờ lại ở đó; quá WATCHDOG_SEC không sleep = treo.
WATCHDOG_SEC = 20 * 60


def _hung(signum, frame) -> None:  # noqa: ARG001
    logger.error("growth: worker không tiến triển %s phút — thoát để PM2 khởi động lại", WATCHDOG_SEC // 60)
    os._exit(3)


def watchdog_sleep(seconds: float) -> None:
    """``time.sleep`` có hẹn giờ chống treo (chỉ dùng khi chạy thật, không dùng trong test)."""
    signal.alarm(int(seconds) + WATCHDOG_SEC)
    time.sleep(seconds)
    signal.alarm(WATCHDOG_SEC)


_DEAD_BROWSER_HINTS = ("has been closed", "browser has disconnected", "target closed")


def browser_dead(exc: BaseException) -> bool:
    """Chromium đã chết (bị diệt / crash) — mọi thao tác sau đều lỗi, phải dừng vòng chứ không đánh lỗi từng bài."""
    text = str(exc).lower()
    return any(h in text for h in _DEAD_BROWSER_HINTS)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
    own_posts: List[Dict] = field(default_factory=list)
    followups: List[Dict] = field(default_factory=list)
    rewritten: int = 0
    customers: Optional[Dict] = None

    @property
    def acted(self) -> bool:
        return bool(self.posted or self.failed or self.own_posts or self.followups)

    def as_dict(self) -> Dict:
        return {**self.__dict__, "errors": list(self.errors), "posted_items": list(self.posted_items),
                "own_posts": list(self.own_posts), "followups": list(self.followups)}


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
        self.last_followup: Optional[datetime] = None
        self.last_rewrite: Optional[datetime] = None
        self.own_retry_at: Optional[datetime] = None

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
        if post.reach < cfg.min_reach:
            return False
        if cfg.author_cooldown_days and self.runner.storage.replied_author_since(
            post.author, self.now() - timedelta(days=cfg.author_cooldown_days)
        ):
            return False
        return True

    # ── quét ───────────────────────────────────────────────────
    def scan(self, profile_path: str, cfg: WorkerConfig, report: CycleReport) -> List[tuple[ScannedPost, TargetBot]]:
        found: Dict[str, tuple[ScannedPost, TargetBot]] = {}
        authors: set[str] = set()  # mỗi vòng tối đa 1 bài / tác giả (cooldown chỉ thấy bài đã lưu)
        tabs = (False, True) if cfg.search_top else (False,)
        jobs = [(bot, kw, top) for bot, prof in load_profiles().items() for kw in prof.keywords for top in tabs]
        random.shuffle(jobs)  # không quét cùng một thứ tự mỗi vòng
        with self.browser_factory(profile_path) as browser:
            for bot, kw, top in jobs:
                try:
                    posts = browser.search_recent(kw, limit=cfg.posts_per_keyword, top=top)
                except ThreadsSessionInvalidError:
                    raise
                except Exception as exc:
                    if browser_dead(exc):
                        report.errors.append(f"trình duyệt bị đóng khi tìm «{kw}» — dừng quét vòng này")
                        logger.warning("growth: trình duyệt bị đóng khi tìm %r — dừng quét", kw)
                        break
                    report.errors.append(f"tìm «{kw}»: {exc}")
                    logger.warning("growth: tìm %r lỗi: %s", kw, exc)
                    continue
                report.scanned += len(posts)
                for p in posts:
                    author = (p.author or "").lower()
                    if p.thread_id not in found and author not in authors and self._fresh(p, cfg):
                        found[p.thread_id] = (p, bot)
                        authors.add(author)
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
        cfg = load_worker_config()
        done_authors: set[str] = set()
        with self.browser_factory(profile_path) as browser:
            for i, post in enumerate(queue):
                quota = self.runner.posting_quota(self.now())
                if not quota.allowed:
                    report.quota_note = quota.reason
                    break
                created = _parse_ts(post.get("post_created_at"))
                if created and created < self.now() - timedelta(hours=cfg.max_post_age_hours):
                    # Bài nằm hàng chờ quá lâu (hết suất ngày) — reply muộn chìm dưới đáy, không đáng một suất.
                    self.runner.reject(post["id"], "bài đã cũ — quá thời gian tối đa trước khi tới lượt đăng")
                    continue
                author = (post["author"] or "").lower()
                if author in done_authors or (cfg.author_cooldown_days and self.runner.storage.posted_to_author_since(
                    post["author"], self.now() - timedelta(days=cfg.author_cooldown_days)
                )):
                    self.runner.reject(post["id"], "trùng tác giả — đã reply người này trong thời gian chờ")
                    logger.info("growth: bỏ #%s — đã reply @%s gần đây", post["id"], post["author"])
                    continue
                text = post.get("actual_reply") or post["suggested_reply"]
                try:
                    url = browser.reply(post["post_url"], text)
                except ThreadsSessionInvalidError:
                    raise
                except Exception as exc:
                    if browser_dead(exc):
                        # Bài này + phần còn lại giữ nguyên «Chờ đăng», vòng sau mở trình duyệt mới đăng tiếp.
                        report.errors.append("trình duyệt bị đóng giữa chừng — vòng sau đăng tiếp")
                        logger.warning("growth: trình duyệt bị đóng khi đăng #%s — dừng, giữ hàng chờ", post["id"])
                        break
                    self.runner.mark_failed(post["id"], str(exc))
                    report.failed += 1
                    logger.warning("growth: đăng reply #%s lỗi: %s", post["id"], exc)
                else:
                    done_authors.add(author)
                    self.runner.mark_posted(post["id"], reply_url=url)
                    report.posted += 1
                    report.posted_items.append({
                        "id": post["id"], "bot": post["target_bot"], "variant": post["variant"],
                        "author": post["author"], "post_url": post["post_url"], "reply_url": url, "text": text,
                    })
                    logger.info("growth: đã reply #%s → %s", post["id"], url or post["post_url"])
                if i < len(queue) - 1:
                    self.sleep(self.runner.next_delay_sec())

    # ── bài riêng (PLAN-159) ───────────────────────────────────
    def _own_post_slot(self, cfg: WorkerConfig) -> Optional[str]:
        """Khung giờ đang tới lượt mà chưa đăng: ``"2026-11-06 20:15"`` — lệch ngẫu nhiên cố định 0–25 phút / khung."""
        now_vn = self.now().astimezone(content.ICT)
        day = now_vn.date().isoformat()
        for raw in str(cfg.own_post_times).replace(";", ",").split(","):
            raw = raw.strip()
            try:
                hh, mm = (int(x) for x in raw.split(":"))
                base = now_vn.replace(hour=hh, minute=mm, second=0, microsecond=0)
            except ValueError:
                continue
            slot = f"{day} {hh:02d}:{mm:02d}"
            jitter = int(hashlib.md5(slot.encode()).hexdigest(), 16) % 26
            if base + timedelta(minutes=jitter) <= now_vn < base + OWN_POST_WINDOW:
                if not self.runner.storage.own_post_slot_done(slot):
                    return slot
        return None

    def post_own(self, profile_path: str, cfg: WorkerConfig, report: CycleReport) -> None:
        if not cfg.own_posts_enabled or (self.own_retry_at and self.now() < self.own_retry_at):
            return
        slot = self._own_post_slot(cfg)
        if not slot:
            return
        storage = self.runner.storage
        draft = asyncio.run(content.write_own_post(self.now(), storage.own_post_refs(self.now() - timedelta(days=3))))
        if draft is None:
            self.own_retry_at = self.now() + OWN_POST_RETRY  # AI lỗi / hết deal mới → thử lại trong khung
            logger.info("growth: bài riêng khung %s chưa viết được — thử lại sau", slot)
            return
        try:
            with self.browser_factory(profile_path) as browser:
                url = browser.create_post(draft.text)
        except ThreadsSessionInvalidError:
            raise
        except Exception as exc:
            if browser_dead(exc):
                self.own_retry_at = self.now() + OWN_POST_RETRY
                return
            storage.save_own_post(slot, draft.kind, draft.ref, draft.text, "failed", error=str(exc))
            report.errors.append(f"bài riêng: {exc}")
            logger.warning("growth: đăng bài riêng lỗi: %s", exc)
            return
        storage.save_own_post(slot, draft.kind, draft.ref, draft.text, "posted", post_url=url)
        report.own_posts.append({"kind": draft.kind, "url": url, "text": draft.text})
        logger.info("growth: đã đăng bài riêng (%s) → %s", draft.kind, url)

    # ── trả lời người hỏi lại (PLAN-159) ───────────────────────
    def followups(self, profile_path: str, cfg: WorkerConfig, report: CycleReport) -> None:
        now = self.now()
        if not cfg.followup_enabled or (self.last_followup and now - self.last_followup < FOLLOWUP_EVERY):
            return
        self.last_followup = now
        storage = self.runner.storage
        left = cfg.followup_max_per_day - storage.count_followups_since(now - timedelta(days=1))
        if left <= 0:
            return
        targets = storage.followup_targets(now - timedelta(hours=cfg.followup_lookback_hours),
                                           now - FOLLOWUP_RECHECK, FOLLOWUP_PAGES)
        if not targets:
            return
        with self.browser_factory(profile_path) as browser:
            for target in targets:
                try:
                    comments = browser.replies_to_me(target["reply_url"])
                except ThreadsSessionInvalidError:
                    raise
                except Exception as exc:
                    if browser_dead(exc):
                        return
                    logger.warning("growth: đọc trả lời dưới #%s lỗi: %s", target["id"], exc)
                    continue
                ai_down = False
                for c in comments:
                    if left <= 0:
                        return  # hết suất hôm nay: KHÔNG đánh dấu đã kiểm — người còn lại trả lời ngày mai
                    if storage.followup_seen(c.thread_id):
                        continue
                    our = target.get("actual_reply") or target["suggested_reply"]
                    verdict, text = asyncio.run(content.write_followup(TargetBot(target["target_bot"]), our, c.content))
                    if verdict == "error":
                        ai_down = True  # AI lỗi: để lần sau (không đánh dấu đã kiểm reply này)
                        break
                    if verdict == "skip":
                        storage.save_followup(c.thread_id, target["id"], c.author, c.content, c.post_url, "skipped")
                        continue
                    try:
                        url = browser.reply(c.post_url, text)
                    except ThreadsSessionInvalidError:
                        raise
                    except Exception as exc:
                        if browser_dead(exc):
                            return
                        storage.save_followup(c.thread_id, target["id"], c.author, c.content, c.post_url, "failed",
                                              reply_text=text, error=str(exc))
                        continue
                    storage.save_followup(c.thread_id, target["id"], c.author, c.content, c.post_url, "answered",
                                          reply_text=text, reply_url=url)
                    left -= 1
                    report.followups.append({"author": c.author, "comment": c.content, "text": text,
                                             "url": url or c.post_url, "bot": target["target_bot"]})
                    logger.info("growth: đã trả lời lại @%s dưới #%s", c.author, target["id"])
                    self.sleep(self.runner.next_delay_sec())
                if ai_down:
                    return
                storage.mark_followup_checked(target["id"], now)

    # ── AI viết lại bài đang dùng câu mẫu ──────────────────────
    def rewrite_fallbacks(self, cfg: WorkerConfig, report: CycleReport) -> None:
        now = self.now()
        if self.last_rewrite and now - self.last_rewrite < REWRITE_EVERY:
            return
        self.last_rewrite = now
        for row in self.runner.storage.fallback_pending(limit=5):
            post = asyncio.run(self.runner.switch_variant(row["id"], ABVariant(row["variant"])))
            if not post or str(post.get("ai_analysis") or "").startswith("Fallback"):
                return  # AI vẫn lỗi — đợi lượt sau
            report.rewritten += 1
            if not cfg.telegram_review and row["relevance_score"] >= cfg.auto_post_min_relevance:
                self.runner.approve_and_prepare(row["id"])

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
            self.rewrite_fallbacks(cfg, report)
            self.post_queue(profile, report)
            self.post_own(profile, cfg, report)
            self.followups(profile, cfg, report)
        except ThreadsSessionInvalidError as exc:
            self._disable(str(exc))
            report.errors.append(str(exc))
            return report
        if due or report.acted:
            logger.info("growth: vòng xong %s", report.as_dict())
            if report.acted:
                try:
                    report.customers = conversions.report()
                except Exception as exc:  # báo cáo khách không được làm hỏng vòng
                    logger.warning("growth: đọc khách mới lỗi: %s", exc)
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
    if args.once:
        worker = GrowthWorker()
        report = worker.tick(force_scan=True)
        print(report.as_dict() if report else "Không chạy (chưa đăng nhập / profile đang mở)")
        return 0
    signal.signal(signal.SIGALRM, _hung)
    signal.alarm(WATCHDOG_SEC)
    GrowthWorker(sleep=watchdog_sleep).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
