import logging
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path

# Repo root on sys.path so this worker works without PYTHONPATH=.
_root = Path(__file__).resolve().parents[4]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Setup logging before importing app.* modules.
from app.utils.logger import setup_shared_logger

setup_shared_logger("app")
logger = setup_shared_logger(__name__ if __name__ != "__main__" else "threads_publisher")

import app.config as config
from sqlalchemy.orm import Session

from app.adapters.dispatcher import Dispatcher
from app.constants import JobStatus, Platform
from app.core.database.core import SessionLocal
from app.core import settings as runtime_settings
from app.core.account import AccountService
from app.core.queue.job import JobService
from app.core.notifier.service import NotifierService
from app.core.queue.worker import WorkerService


from app.core.queue.publisher_runtime import (
    kill_if_stuck as _kill_if_stuck_shared,
    start_heartbeat_thread,
    claim_precheck,
    claim_next_job_respecting_daily,
    postpone_if_sleeping,
    recover_stale_jobs,
)

RUNNING = True
CURRENT_JOB_ID = None


def kill_if_stuck(label: str, timeout: int) -> threading.Timer:
    return _kill_if_stuck_shared(logger, label, timeout)


def handle_sigterm(signum, frame) -> None:
    """Graceful shutdown handler for SIGTERM/SIGINT."""
    del signum, frame
    global RUNNING
    RUNNING = False
    logger.warning("Received termination signal. Preparing to shut down...")
    if CURRENT_JOB_ID is not None:
        logger.warning("Waiting for Job %s to finish before exiting...", CURRENT_JOB_ID)
    else:
        logger.info("No active job, exiting safely.")
        sys.exit(0)


def register_signals() -> None:
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)


def check_crash_recovery(db: Session) -> None:
    recover_stale_jobs(db, logger, config.WORKER_CRASH_THRESHOLD_SECONDS)


def process_single_job(db: Session) -> bool:
    """Claim and process one eligible Threads job."""
    global CURRENT_JOB_ID

    threads_platform = (
        Platform.THREADS.value if hasattr(Platform.THREADS, "value") else str(Platform.THREADS)
    )
    if not claim_precheck(
        db,
        logger,
        platform=threads_platform,
        prefix="[THREADS_PUBLISHER] ",
        default_max_concurrent=1,
        fuzzy_platform=True,
    ):
        return False

    logger.debug("[THREADS_PUBLISHER] Attempting to claim job for platform: %s", threads_platform)
    job, claim_note = claim_next_job_respecting_daily(
        db,
        platform=threads_platform,
        logger=logger,
        prefix="[THREADS_PUBLISHER] ",
    )
    if not job:
        if claim_note == "daily_exhausted":
            logger.info("[THREADS_PUBLISHER] All claimed candidates hit daily limit this tick.")
        else:
            logger.debug("[THREADS_PUBLISHER] No eligible job found.")
        return False

    heartbeat_stop = threading.Event()
    try:
        if postpone_if_sleeping(db, job, logger, prefix="[THREADS_PUBLISHER] "):
            return True

        CURRENT_JOB_ID = job.id
        logger.info(
            "[THREADS_PUBLISHER] [Job-%s] [CLAIM] Account='%s' Platform=%s",
            job.id,
            job.account.name if job.account else "?",
            job.platform,
        )

        heartbeat_thread = start_heartbeat_thread(
            job.id, heartbeat_stop, interval=60, logger=logger
        )

        suicide_timer = kill_if_stuck(
            f"Threads Job {job.id} Publish",
            timeout=config.PUBLISHER_PUBLISH_DEADLINE_SEC,
        )
        try:
            logger.info(
                "[THREADS_PUBLISHER] [Job-%s] [PUBLISH] Starting Threads publish...",
                job.id,
            )
            publish_result = Dispatcher.dispatch(job, db=db)
        finally:
            heartbeat_stop.set()
            try:
                heartbeat_thread.join(timeout=5)
            except Exception:
                pass
            suicide_timer.cancel()

        post_url = publish_result.details.get("post_url") if publish_result.details else None
        if publish_result.ok and not post_url:
            logger.warning(
                "[THREADS_PUBLISHER] [Job-%s] Adapter reported success without post_url — "
                "marking DONE to prevent duplicate publish; reconciliation can backfill URL.",
                job.id,
            )

        if publish_result.ok:
            logger.info(
                "[THREADS_PUBLISHER] [Job-%s] [DONE] Successfully published.",
                job.id,
            )
            JobService.mark_done(
                db=db,
                job=job,
                details="Success",
                external_post_id=publish_result.external_post_id,
                post_url=post_url,
            )
            NotifierService.notify_job_done(job, post_url=post_url)

            apply_runtime_overrides_to_config(db)
            delay_sec = runtime_settings.get_int(
                "publish.delay_min_sec",
                config.POST_DELAY_MIN_SEC,
                db=db,
            )
            delay_cap = runtime_settings.get_int(
                "publish.delay_max_sec",
                config.POST_DELAY_MAX_SEC,
                db=db,
            )
            if delay_cap < delay_sec:
                delay_cap = delay_sec
            cooldown = delay_sec if delay_sec == delay_cap else random.randint(
                delay_sec, delay_cap
            )
            logger.info(
                "[THREADS_PUBLISHER] [Job-%s] [COOLDOWN] Sleeping %ss before next poll.",
                job.id,
                cooldown,
            )
            time.sleep(cooldown)
        else:
            logger.error(
                "[THREADS_PUBLISHER] [Job-%s] [FAILED] Publish failed: %s (Fatal: %s)",
                job.id,
                publish_result.error,
                publish_result.is_fatal,
            )
            JobService.mark_failed_or_retry(
                db=db,
                job=job,
                error_msg=publish_result.error or "Unknown failure",
                is_fatal=publish_result.is_fatal,
                error_type="FATAL" if publish_result.is_fatal else "RETRYABLE",
            )
            if publish_result.is_fatal or job.tries >= job.max_tries:
                NotifierService.notify_job_failed(job, publish_result.error)

            if publish_result.details and publish_result.details.get("invalidate_account"):
                reason = publish_result.error or "Session invalid"
                if publish_result.details.get("checkpointed"):
                    reason = f"Checkpoint/login: {reason}"
                logger.error(
                    "[THREADS_PUBLISHER] [Job-%s] [ACCOUNT_INVALID] Disabling account '%s'.",
                    job.id,
                    job.account.name if job.account else "?",
                )
                AccountService.invalidate_account(
                    db=db,
                    account_id=job.account.id,
                    reason=reason,
                )
                if job.account:
                    NotifierService.notify_account_invalid(
                        job.account.name,
                        reason,
                    )
    except Exception as exc:
        try:
            heartbeat_stop.set()
        except Exception:
            pass
        db.rollback()
        logger.exception(
            "[THREADS_PUBLISHER] [Job-%s] Unhandled exception while processing job: %s",
            getattr(job, "id", None),
            exc,
        )
        JobService.mark_failed_or_retry(
            db,
            job,
            str(exc),
            is_fatal=False,
            error_type="RETRYABLE",
        )
    finally:
        try:
            db.rollback()
            db.refresh(job)
            should_cleanup = False
            if job.status == JobStatus.DONE:
                should_cleanup = True
            elif job.status == JobStatus.FAILED and job.tries >= job.max_tries:
                should_cleanup = True

            if should_cleanup:
                processed_path = job.resolved_processed_media_path
                if processed_path and os.path.exists(processed_path):
                    logger.info(
                        "[THREADS_PUBLISHER] [Job-%s] [CLEANUP] Removing processed media: %s",
                        job.id,
                        processed_path,
                    )
                    os.remove(processed_path)

                media_path = job.resolved_media_path
                if media_path and os.path.exists(media_path):
                    logger.info(
                        "[THREADS_PUBLISHER] [Job-%s] [CLEANUP] Removing original media: %s",
                        job.id,
                        media_path,
                    )
                    os.remove(media_path)
        except Exception as cleanup_err:
            logger.warning(
                "[THREADS_PUBLISHER] [Job-%s] Cleanup warning: %s",
                getattr(job, "id", None),
                cleanup_err,
            )

        CURRENT_JOB_ID = None

    return True


def run_loop() -> None:
    """Main Threads publisher loop."""
    global RUNNING

    from app.core.notifier.service import TelegramNotifier

    NotifierService.register(
        TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    )

    logger.info("Threads Publisher Worker started. Press Ctrl+C to stop.")
    stagger_sec = random.uniform(1, 3)
    logger.info("Staggering startup: sleeping for %.2fs...", stagger_sec)
    time.sleep(stagger_sec)

    register_signals()
    with SessionLocal() as db:
        try:
            check_crash_recovery(db)
        except Exception as exc:
            db.rollback()
            logger.warning("Crash recovery check failed: %s", exc)

        try:
            state = WorkerService.get_or_create_state(db)
            state.worker_started_at = int(time.time())
            db.commit()
        except Exception:
            db.rollback()
            raise

    logger.info("Entering polling loop. Tick=%ss", config.WORKER_TICK_SECONDS)
    idle_sleep = config.WORKER_TICK_SECONDS
    idle_sleep_cap = int(os.getenv("THREADS_PUBLISHER_IDLE_SLEEP_CAP_SEC", "60"))

    while RUNNING:
        found_job = False
        try:
            with SessionLocal() as db:
                try:
                    state = WorkerService.get_or_create_state(db)
                    WorkerService.update_heartbeat(db, CURRENT_JOB_ID)

                    if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                        logger.warning(
                            "Received pending command: %s. Graceful exit requested.",
                            state.pending_command,
                        )
                        break

                    if state.worker_status == "PAUSED":
                        time.sleep(config.WORKER_TICK_SECONDS)
                        continue

                    config.SAFE_MODE = state.safe_mode
                    found_job = process_single_job(db)
                except Exception:
                    db.rollback()
                    raise

            if not found_job and RUNNING:
                time.sleep(idle_sleep)
                idle_sleep = min(idle_sleep * 2, idle_sleep_cap)
            else:
                idle_sleep = config.WORKER_TICK_SECONDS
        except Exception:
            logger.exception("Threads Publisher encountered a core loop error. Will retry.")
            time.sleep(config.WORKER_TICK_SECONDS)

    logger.info("Threads Publisher process completed gracefully.")


if __name__ == "__main__":
    run_loop()
