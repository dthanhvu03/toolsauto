"""Shared helpers for FB / Threads / AI publisher-style workers.

Keeps claim-loop boilerplate in one place; platform-specific logic stays in features.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.core.observability.system_monitor import SystemMonitorService
from app.core.queue.queue import QueueService
from app.core.settings import apply_runtime_overrides_to_config


def kill_if_stuck(logger: logging.Logger, label: str, timeout: int) -> threading.Timer:
    """Hard timeout — exit so PM2 restarts a hung Playwright/browser worker."""

    def suicide() -> None:
        logger.error(
            "[FATAL DEADLOCK] %s hung for over %ss. Exiting to trigger restart.",
            label,
            timeout,
        )
        os._exit(1)

    timer = threading.Timer(timeout, suicide)
    timer.daemon = True
    timer.start()
    return timer


def clear_claim_locks(job) -> None:
    """Clear RUNNING claim fields when postponing back to PENDING."""
    job.locked_at = None
    job.last_heartbeat_at = None
    job.started_at = None


def start_heartbeat_thread(
    job_id: int,
    stop_event: threading.Event,
    *,
    interval: int = 60,
    logger: Optional[logging.Logger] = None,
) -> threading.Thread:
    from app.core.database.core import SessionLocal
    from app.core.queue.job import JobService

    log = logger or logging.getLogger(__name__)

    def _loop() -> None:
        while not stop_event.is_set():
            try:
                with SessionLocal() as hb_db:
                    JobService.update_heartbeat(hb_db, job_id)
            except Exception as exc:
                log.debug("[HEARTBEAT] job=%s refresh failed: %s", job_id, exc)
            stop_event.wait(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def resource_blocks_claim(db: Session, logger: logging.Logger, prefix: str = "") -> bool:
    """Return True if RAM / browser pressure says pause claiming."""
    health = SystemMonitorService().check_health()
    ram_threshold = runtime_settings.get_int("worker.publisher.ram_threshold", 95, db=db)
    if health.get("ram_percent") and health["ram_percent"] > ram_threshold:
        logger.warning(
            "%sRAM pressure high (%s%%). Pausing claim.",
            prefix,
            health["ram_percent"],
        )
        return True
    max_browsers = runtime_settings.get_int(
        "worker.publisher.max_browser_instances", 15, db=db
    )
    if health.get("chrome_playwright_count") and health["chrome_playwright_count"] >= max_browsers:
        logger.warning(
            "%sBrowser instances high (%s). Pausing claim.",
            prefix,
            health["chrome_playwright_count"],
        )
        return True
    return False


def recover_stale_jobs(db: Session, logger: logging.Logger, threshold_seconds: int) -> int:
    logger.info("Checking for stale RUNNING jobs to recover...")
    recovered = QueueService.recover_crashed_jobs(db, threshold_seconds)
    if recovered > 0:
        logger.warning("Recovered %s stale jobs back to queue.", recovered)
    return recovered


def count_running_for_platform(db: Session, platform: str, *, fuzzy: bool = False) -> int:
    """Count RUNNING jobs for a platform (exact or LIKE '%platform%')."""
    from app.core.database.models import Job
    from app.constants import JobStatus

    q = db.query(Job).filter(Job.status == JobStatus.RUNNING)
    if fuzzy:
        q = q.filter(Job.platform.like(f"%{platform}%"))
    else:
        q = q.filter(Job.platform == platform)
    return q.count()


def claim_precheck(
    db: Session,
    logger: logging.Logger,
    *,
    platform: str,
    prefix: str = "",
    default_max_concurrent: int = 1,
    fuzzy_platform: bool = False,
) -> bool:
    """
    Shared pre-claim gate: refresh settings, concurrent account cap, RAM/browser.
    Returns True if claiming may proceed.
    """
    refresh_runtime_settings(db)
    max_concurrent = runtime_settings.get_int(
        "publish.max_concurrent_accounts", default_max_concurrent, db=db
    )
    running = count_running_for_platform(db, platform, fuzzy=fuzzy_platform)
    if running >= max_concurrent:
        logger.info(
            "%sSafety limit: %s/%s active %s jobs. Pause claim.",
            prefix,
            running,
            max_concurrent,
            platform,
        )
        return False
    if resource_blocks_claim(db, logger, prefix=prefix):
        return False
    return True


def postpone_if_sleeping(db: Session, job, logger: logging.Logger, prefix: str = "") -> bool:
    """If account is sleeping, postpone job 10m and clear locks. Returns True if postponed."""
    import time
    from app.constants import JobStatus

    if not (job.account and getattr(job.account, "is_sleeping", False)):
        return False
    logger.info(
        "%s[Job-%s] Account '%s' sleeping. Postpone 10m.",
        prefix,
        job.id,
        job.account.name,
    )
    job.status = JobStatus.PENDING
    job.schedule_ts = int(time.time()) + 600
    clear_claim_locks(job)
    db.commit()
    return True


def postpone_if_daily_limit(db: Session, job, logger: logging.Logger, prefix: str = "") -> bool:
    """
    Enforce daily publish cap after claim; postpone to tomorrow if exceeded.

    Gate order (publish):
      1) claim cooldown (account.cooldown_seconds via finished_at)
      2) this daily cap
      3) sleep window
      4) post_delay sleep after DONE

    Cap resolution:
      - publish.posts_per_page_per_day > 0 and job.target_page → count DONE today on that page (+ platform)
      - else account.daily_limit > 0 → count DONE today for account (+ page if set) on platform
      - 0 = OFF
    """
    from datetime import datetime, time as time_obj
    from zoneinfo import ZoneInfo

    import app.config as app_config
    from app.constants import JobStatus
    from app.core.database.models import Job

    page_cap = 0
    try:
        page_cap = int(runtime_settings.get_int("publish.posts_per_page_per_day", 0, db=db) or 0)
    except Exception:
        page_cap = 0

    use_page_scope = bool(page_cap > 0 and (job.target_page or "").strip())
    effective = page_cap if use_page_scope else 0
    if not effective and job.account:
        effective = int(getattr(job.account, "daily_limit", 0) or 0)

    if not job.account or effective <= 0:
        return False

    today_start = int(
        datetime.combine(
            datetime.now(ZoneInfo(app_config.TIMEZONE)).date(),
            time_obj.min,
        ).timestamp()
    )

    q = db.query(Job).filter(
        Job.status == JobStatus.DONE,
        Job.finished_at >= today_start,
        Job.platform == job.platform,
    )
    if use_page_scope:
        q = q.filter(Job.target_page == job.target_page)
    else:
        q = q.filter(Job.account_id == job.account_id)
        if job.target_page:
            q = q.filter(Job.target_page == job.target_page)

    posted_today = q.count()
    if posted_today < effective:
        return False

    scope = job.target_page if use_page_scope else (job.target_page or f"account#{job.account_id}")
    logger.info(
        "%s[Job-%s] [DAILY_LIMIT] '%s' reached %s/%s. Postpone to tomorrow.",
        prefix,
        job.id,
        scope,
        posted_today,
        effective,
    )
    job.status = JobStatus.PENDING
    job.schedule_ts = today_start + 86400 + 3600  # tomorrow ~01:00 local
    clear_claim_locks(job)
    db.commit()
    return True


def refresh_runtime_settings(db: Session) -> None:
    apply_runtime_overrides_to_config(db)


def make_signal_handlers(
    *,
    get_running: Callable[[], bool],
    set_running: Callable[[bool], None],
    get_current_job_id: Callable[[], Optional[int]],
    logger: logging.Logger,
) -> Callable[[], None]:
    """Return register_signals() that toggles shared RUNNING flag for the worker."""

    def handle_sigterm(signum, frame) -> None:
        del signum, frame
        set_running(False)
        logger.warning("Received termination signal. Preparing to shut down...")
        job_id = get_current_job_id()
        if job_id is not None:
            logger.warning("Waiting for Job %s to finish before exiting...", job_id)
        else:
            logger.info("No active job, exiting safely.")
            sys.exit(0)

    def register_signals() -> None:
        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

    return register_signals
