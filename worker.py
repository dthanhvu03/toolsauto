import time
import logging
import signal
import sys
import os
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.services.queue import QueueService
from app.services.job import JobService
from app.config import WORKER_TICK_SECONDS, WORKER_CRASH_THRESHOLD_SECONDS
from app.adapters.dispatcher import Dispatcher
from app.services.worker import WorkerService
from app.services.cleanup import CleanupService
from app.services.account import AccountService
import app.config as config
from app.services.metrics_checker import MetricsChecker
from app.services.notifier import NotifierService, TelegramNotifier

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from typing import Optional

# Global flag to control the main loop
RUNNING = True
CURRENT_JOB_ID = None
CURRENT_POLLER: Optional['TelegramPoller'] = None


def handle_sigterm(signum, frame): # pylint: disable=unused-argument
    """Graceful shutdown handler for SIGTERM/SIGINT."""
    global RUNNING, CURRENT_POLLER # pylint: disable=global-statement
    logger.warning("Received termination signal. Preparing to shut down...")
    RUNNING = False
    
    # Stop poller immediately so it releases the lock and stops processing
    if CURRENT_POLLER:
        logger.info("Stopping TelegramPoller gracefully...")
        CURRENT_POLLER.stop()
    
    if CURRENT_JOB_ID is not None:
        logger.warning("Waiting for Job %s to finish before exiting...", CURRENT_JOB_ID)
    else:
        logger.info("No active job, exiting safely.")
        sys.exit(0)

def register_signals():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)


def check_crash_recovery(db: Session):
    """Resets jobs stuck in RUNNING based on stale heartbeats."""
    logger.info("Checking for crashed (stale heartbeat) jobs to recover...")
    recovered_count = QueueService.recover_crashed_jobs(db, WORKER_CRASH_THRESHOLD_SECONDS)
    if recovered_count > 0:
        logger.warning("Recovered %s crashed jobs. Sent back to PENDING.", recovered_count)

def process_single_job(db: Session):
    """
    Attempts to claim and process one job.
    Returns True if a job was found, False otherwise.
    """
    global CURRENT_JOB_ID # pylint: disable=global-statement
    
    job = QueueService.claim_next_job(db)
    if not job:
        return False
        
    CURRENT_JOB_ID = job.id
    logger.info("[Job %s] Claimed for account '%s' on %s", job.id, job.account.name, job.platform)
    
    try:
        # SAFETY GUARD: Never publish a job with un-processed AI placeholder
        if job.caption and "[AI_GENERATE]" in job.caption:
            logger.warning("[Job %s] BLOCKED: Caption still contains [AI_GENERATE]. Resetting to DRAFT.", job.id)
            job.status = "DRAFT"
            db.commit()
            CURRENT_JOB_ID = None
            return True  # Return True so worker doesn't sleep, it'll find the next real job
        
        # Pre-dispatch validation might go here if daily limits weren't checked in SQL
        # Using the dispatcher which guarantees an adapter cleanup finally block:
        publish_result = Dispatcher.dispatch(job, db=db)
        
        if publish_result.ok:
            logger.info("[Job %s] Successfully published!", job.id)
            post_url = publish_result.details.get("post_url") if publish_result.details else None
            JobService.mark_done(
                db=db, 
                job=job, 
                details="Success", 
                external_post_id=publish_result.external_post_id,
                post_url=post_url
            )
            NotifierService.notify_job_done(job, post_url=post_url)
        else:
            logger.error("[Job %s] Publish failed: %s (Fatal: %s)", job.id, publish_result.error, publish_result.is_fatal)
            JobService.mark_failed_or_retry(
                db=db, 
                job=job, 
                error_msg=publish_result.error or "Unknown failure",
                is_fatal=publish_result.is_fatal,
                error_type="FATAL" if publish_result.is_fatal else "RETRYABLE"
            )
            # Gửi Telegram khi lỗi fatal hoặc hết retry
            if publish_result.is_fatal or job.tries >= job.max_tries:
                NotifierService.notify_job_failed(job, publish_result.error)
            
            # Check if Dispatcher signaled a catastrophic session death 
            if publish_result.details and publish_result.details.get("invalidate_account"):
                logger.error("[Job %s] Adapter triggered account invalidation. Disabling account '%s'.", job.id, job.account.name)
                AccountService.invalidate_account(
                    db=db, 
                    account_id=job.account.id, 
                    reason=publish_result.error
                )
                NotifierService.notify_account_invalid(job.account.name, publish_result.error)
                
            
    except Exception as e: # pylint: disable=broad-except
        logger.exception("[Job %s] Unhandled worker exception processing job: %s", job.id, e)
        JobService.mark_failed_or_retry(db, job, str(e), is_fatal=False)
        
    finally:
        # Cleanup temporary processed media if job reached terminal state
        try:
            db.refresh(job) # Ensure we have latest status
            if job.status in ["DONE", "FAILED"]:
                if job.processed_media_path and os.path.exists(job.processed_media_path):
                    logger.info("[Job %s] Terminal state reached. Cleaning up temporary media: %s", job.id, job.processed_media_path)
                    os.remove(job.processed_media_path)
        except Exception as cleanup_err:
            logger.warning("[Job %s] Failed to clean up media file: %s", job.id, cleanup_err)
            
        CURRENT_JOB_ID = None
        
    return True

def process_draft_job(db: Session):
    """
    Attempts to claim and process one DRAFT job for AI Caption Generation.
    Returns True if a job was found, False otherwise.
    """
    global CURRENT_JOB_ID # pylint: disable=global-statement
    
    job = QueueService.claim_draft_job(db)
    if not job:
        return False
        
    CURRENT_JOB_ID = job.id
    logger.info("[Job %s] Claimed DRAFT for AI Generation", job.id)
    
    try:
        from app.services.content_orchestrator import ContentOrchestrator
        import re
        
        target_video = job.processed_media_path if job.processed_media_path else job.media_path
        
        existing_salt_match = re.search(r'\[ref:[a-zA-Z0-9]+\]|#v\d{4}', job.caption or "")
        existing_salt = existing_salt_match.group(0) if existing_salt_match else ""
        user_context = (job.caption or "").replace(r"[AI_GENERATE]", "").replace(existing_salt, "").strip()
        
        if user_context.startswith("Context:"):
            user_context = user_context.replace("Context:", "", 1).strip()
            
        orchestrator = ContentOrchestrator()
        ai_result = orchestrator.generate_caption(target_video, style="general", context=user_context)
        
        if ai_result and ai_result.get("caption"):
            final_text = ai_result["caption"].strip()
            if ai_result.get("hashtags"):
                final_text += "\n\n" + " ".join(ai_result["hashtags"])
            if existing_salt:
                final_text += f"\n\n{existing_salt}"
                
            job.caption = final_text
            job.status = "DRAFT"
            db.commit()
            logger.info("[Job %s] AI Generation complete. Awaiting user approval.", job.id)
            NotifierService.notify_draft_ready(job)
        else:
            # AI failed — keep as DRAFT so it will be retried next tick
            job.status = "DRAFT"
            job.last_error = "AI Generation returned empty result"
            db.commit()
            logger.warning("[Job %s] AI Generation returned empty. Kept as DRAFT for retry. NOT notifying.", job.id)
        
    except Exception as e: # pylint: disable=broad-except
        logger.exception("[Job %s] Unhandled exception during AI Generation: %s", job.id, e)
        job.status = "DRAFT"
        job.last_error = f"AI Generation Error: {e}"
        db.commit()
    finally:
        CURRENT_JOB_ID = None
        
    return True
DAILY_SUMMARY_HOUR = 23  # Gửi báo cáo lúc 23:00 hằng ngày
_last_summary_date = None  # Track ngày đã gửi để tránh duplicate


def _check_daily_summary(db):
    """Gửi báo cáo tổng hợp ngày nếu đến giờ."""
    global _last_summary_date  # pylint: disable=global-statement
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_dt = datetime.now(ZoneInfo(config.TIMEZONE))
    today = now_dt.strftime("%Y-%m-%d")

    if now_dt.hour == DAILY_SUMMARY_HOUR and _last_summary_date != today:
        logger.info("Sending daily summary report...")
        try:
            NotifierService.notify_daily_summary(db)
            _last_summary_date = today
            logger.info("Daily summary sent successfully.")
        except Exception as e:
            logger.error("Daily summary failed: %s", e)


def run_loop(register_sig=True):
    """Main worker 24/7 loop."""
    global RUNNING, CURRENT_POLLER # pylint: disable=global-statement
    logger.info("Worker started. Press Ctrl+C to stop gracefully.")
    
    if register_sig:
        register_signals()
    
    # Check for orphaned jobs from previous crashes first
    # Đăng ký Telegram channel + Poller
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
        logger.info("Telegram notifier registered.")
        
        # Start polling thread cho inline button callbacks
        from app.services.telegram_poller import TelegramPoller
        CURRENT_POLLER = TelegramPoller(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        CURRENT_POLLER.start()
    
    with SessionLocal() as db:
        check_crash_recovery(db)
        # Record startup time for uptime tracking (Phase C)
        state = WorkerService.get_or_create_state(db)
        state.worker_started_at = int(time.time())
        db.commit()
        
    logger.info("Entering polling loop. Tick=%ss", WORKER_TICK_SECONDS)
    
    while RUNNING:
        try:
            with SessionLocal() as db:
                # 1. Sync State & Heartbeat
                state = WorkerService.get_or_create_state(db)
                WorkerService.update_heartbeat(db, CURRENT_JOB_ID)
                
                # 2. Check Pending Commands
                if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                    logger.warning(f"Received pending command: {state.pending_command}. Graceful exit requested.")
                    WorkerService.clear_command(db)
                    break # Exit the while loop gracefully
                    
                # 3. Check PAUSE Status
                if state.worker_status == "PAUSED":
                    time.sleep(WORKER_TICK_SECONDS)
                    continue
                    
                # 4. Process Job
                # We inject safe_mode into config globally for this tick so adapters see it
                config.SAFE_MODE = state.safe_mode
                
                found_job = process_single_job(db)
                
                # If no PENDING jobs, process DRAFT AI Generation jobs
                if not found_job:
                    found_job = process_draft_job(db)
                
                # 5. Cleanup — archive/delete old media files, purge stale .tmp files
                CleanupService.run(db)
                
                # 6. Check 24h Metrics for published posts (1 job per tick)
                MetricsChecker.check_pending(db)
                
                # 7. Daily Summary Report (once per day at configured hour)
                _check_daily_summary(db)
                
            if not found_job and RUNNING:
                # Polling wait only if no job found
                time.sleep(WORKER_TICK_SECONDS)
        except Exception: # pylint: disable=broad-except
            logger.exception("Worker encountered a core loop error. Will retry.")
            time.sleep(WORKER_TICK_SECONDS)
            
    logger.info("Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()

