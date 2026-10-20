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

from app.config import MAX_CONCURRENT_ACCOUNTS_MAX
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
    """Return True if RAM / browser pressure says pause claiming.

    Browser gate uses chrome_toolsauto_count (profiles under storage/profiles /
    Playwright), NOT the machine-wide Chrome process count — personal Chrome
    must not block publish on Windows (PLAN-048).
    """
    monitor = SystemMonitorService()
    health = monitor.check_health()
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
    # Prefer ToolsAuto-scoped count. If missing (old monitor), do not fall back
    # to machine-wide chrome_playwright_count — that falsely pauses on Windows.
    toolsauto = health.get("chrome_toolsauto_count")
    if toolsauto is None:
        return False
    if toolsauto >= max_browsers:
        logger.warning(
            "%sBrowser instances high (toolsauto=%s total=%s). Pausing claim.",
            prefix,
            toolsauto,
            health.get("chrome_playwright_count"),
        )
        try:
            monitor.alert_toolsauto_browser_pressure(int(toolsauto), int(max_browsers))
        except Exception:
            pass
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
    max_concurrent = max(1, min(int(MAX_CONCURRENT_ACCOUNTS_MAX), int(max_concurrent or 1)))
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
    from app.constants import JobStatus, JobType
    from app.core.database.models import Job

    if getattr(job, "job_type", None) == JobType.STORY:
        return False

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


_weekly_story_postpone_lock = threading.Lock()


def postpone_if_weekly_story_limit(
    db: Session,
    job,
    now_ts: int | None = None,
    logger: logging.Logger | None = None,
    prefix: str = "",
) -> bool:
    """
    Enforce max 10 stories/week quota per target page for JobType.STORY.
    If the page has reached or exceeded 10 stories in the current ISO week,
    defer job.schedule_ts to next week's Monday 11:30 ICT slot, reset status to PENDING,
    and unset claim locks.
    Protected by _weekly_story_postpone_lock to ensure atomic evaluation and eliminate over-postponement race conditions.
    """
    from datetime import datetime, timedelta
    import time
    from sqlalchemy import and_, or_

    from app.constants import JobStatus, JobType
    from app.core.database.models import Job
    from app.features.story.scheduler import StoryPacingScheduler, ICT

    if getattr(job, "job_type", None) != JobType.STORY:
        return False

    page = (getattr(job, "target_page", None) or "").strip()
    if not page:
        return False

    with _weekly_story_postpone_lock:
        try:
            db.commit()
        except Exception:
            pass
        try:
            db.expire_all()
        except Exception:
            pass

        log = logger or logging.getLogger(__name__)
        ts = now_ts if now_ts is not None else int(time.time())
        moment = datetime.fromtimestamp(ts, tz=ICT)
        week_start_ts, week_end_ts = StoryPacingScheduler.get_week_bounds(moment)

        job_schedule_ts = getattr(job, "schedule_ts", None) or ts
        job_id = getattr(job, "id", None)

        # Unified single atomic query to evaluate completed (DONE) and prior RUNNING stories.
        # Eliminates split-query TOCTOU race conditions where a transitioning job is missed.
        is_done = and_(
            Job.status == JobStatus.DONE,
            or_(
                and_(Job.schedule_ts.isnot(None), Job.schedule_ts >= week_start_ts, Job.schedule_ts < week_end_ts),
                and_(Job.finished_at.isnot(None), Job.finished_at >= week_start_ts, Job.finished_at < week_end_ts),
            ),
        )

        running_filter = and_(
            Job.status == JobStatus.RUNNING,
            or_(
                and_(Job.schedule_ts.isnot(None), Job.schedule_ts >= week_start_ts, Job.schedule_ts < week_end_ts),
                and_(Job.started_at.isnot(None), Job.started_at >= week_start_ts, Job.started_at < week_end_ts),
            ),
        )
        if job_id is not None:
            running_filter = and_(running_filter, Job.id != job_id)
            if job_schedule_ts is not None:
                running_filter = and_(
                    running_filter,
                    or_(
                        Job.schedule_ts < job_schedule_ts,
                        and_(Job.schedule_ts == job_schedule_ts, Job.id < job_id),
                    ),
                )

        prior_count = (
            db.query(Job)
            .filter(
                Job.target_page == page,
                Job.job_type == JobType.STORY,
                or_(is_done, running_filter),
            )
            .count()
        )

        should_postpone = prior_count >= StoryPacingScheduler.WEEKLY_QUOTA

        if not should_postpone:
            return False

        # Calculate next Monday 11:30 ICT slot
        week_start_dt = datetime.fromtimestamp(week_start_ts, tz=ICT)
        next_monday_1130 = week_start_dt + timedelta(days=7, hours=11, minutes=30)
        next_monday_1130_ts = int(next_monday_1130.timestamp())

        log.info(
            "%s[Job-%s] [WEEKLY_STORY_LIMIT] Page '%s' reached weekly quota (prior_active=%s). Postpone to next Monday 11:30 ICT (%s).",
            prefix,
            getattr(job, "id", "?"),
            page,
            prior_count,
            next_monday_1130_ts,
        )
        job.status = JobStatus.PENDING
        job.schedule_ts = next_monday_1130_ts
        clear_claim_locks(job)
        db.commit()
        return True


def claim_next_job_respecting_daily(
    db: Session,
    *,
    platform: str,
    logger: logging.Logger,
    prefix: str = "",
    max_skips: int = 5,
):
    """
    Claim next job; if daily cap forces postpone, try another candidate (same tick).
    Returns (job, 'daily_exhausted'|'empty'|None).
      - (job, None) ready to publish (daily OK; caller still runs sleep check)
      - (None, 'empty') no PENDING eligible
      - (None, 'daily_exhausted') only hit daily-limited jobs this tick
    """
    from app.core.queue.queue import QueueService
    import app.config as config

    skip_cap = max(1, int(getattr(config, "WORKER_MAX_BATCH_SIZE", max_skips) or max_skips))
    skip_cap = min(50, max(skip_cap, int(max_skips)))

    skipped_daily = 0
    for _ in range(skip_cap):
        job = QueueService.claim_next_job(db, platform=platform)
        if not job:
            if skipped_daily:
                return None, "daily_exhausted"
            return None, "empty"
        if postpone_if_weekly_story_limit(db, job, logger=logger, prefix=prefix):
            skipped_daily += 1
            continue
        if postpone_if_daily_limit(db, job, logger, prefix=prefix):
            skipped_daily += 1
            continue
        return job, None
    return None, "daily_exhausted"


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
