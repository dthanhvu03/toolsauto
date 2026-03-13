import time
import logging
import signal
import sys
import os
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.services.queue import QueueService
from app.services.job import JobService
from app.config import WORKER_TICK_SECONDS
from app.services.worker import WorkerService
from app.services.notifier import NotifierService

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [AI_WORKER] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

import app.config as config

RUNNING = True
CURRENT_JOB_ID = None

# Gemini Circuit Breaker
GEMINI_CONSECUTIVE_FAILURES = 0
GEMINI_CIRCUIT_OPEN = False
GEMINI_CIRCUIT_RESET_TIME = 0

def handle_sigterm(signum, frame):
    """Graceful shutdown handler for SIGTERM/SIGINT."""
    global RUNNING
    logger.warning("Received termination signal. Preparing to shut down...")
    RUNNING = False
    
    if CURRENT_JOB_ID is not None:
        logger.warning("Waiting for AI Job %s to finish before exiting...", CURRENT_JOB_ID)
    else:
        logger.info("No active job, exiting safely.")
        sys.exit(0)

def register_signals():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

def process_draft_job(db: Session):
    """
    Attempts to claim and process one DRAFT job for AI Caption Generation.
    Returns True if a job was found, False otherwise.
    """
    global CURRENT_JOB_ID, GEMINI_CONSECUTIVE_FAILURES, GEMINI_CIRCUIT_OPEN
    
    if GEMINI_CIRCUIT_OPEN:
        return False
        
    # Needs a dedicated claim function if multiple workers run, but our claim_draft_job 
    # uses FOR UPDATE / row locking appropriately if we wrap it in transactions.
    # SQLite doesn't truly do FOR UPDATE (it's database level), but our single AI worker ensures safety.
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
            
            # Pass AI generated keywords to notifier temporarily
            job._ai_keywords = ai_result.get("keywords", [])
            
            db.commit()
            logger.info("[Job %s] AI Generation complete. Awaiting user approval.", job.id)
            NotifierService.notify_draft_ready(job)
            
            # Khởi động lại đếm lỗi trên thành công
            GEMINI_CONSECUTIVE_FAILURES = 0
        else:
            job.status = "DRAFT"
            job.last_error = "AI Generation returned empty result"
            db.commit()
            GEMINI_CONSECUTIVE_FAILURES += 1
            logger.warning("[Job %s] AI Generation returned empty. Kept as DRAFT for retry. NOT notifying. Failures: %d/3", job.id, GEMINI_CONSECUTIVE_FAILURES)
            _check_gemini_circuit(db)
        
    except Exception as e:
        logger.exception("[Job %s] Unhandled exception during AI Generation: %s", job.id, e)
        if type(e).__name__ == "GeminiMaxRetriesExceeded":
            logger.error("[Job %s] GEMINI KHÔNG PHẢN HỒI SAU 3 LẦN THỬ! Mark FAILED.", job.id)
            job.status = "FAILED"
            job.last_error = f"Gemini RPA Failed: {e}"
            db.commit()
            GEMINI_CONSECUTIVE_FAILURES += 1
            error_msg_template = (
                f"🚨 *GEMINI RPA FAILED*\n"
                f"❌ Job ID: {job.id}\n"
                f"⚠️ Error: Gemini không phản hồi sau 3 lần thử retry.\n"
                f"🛑 Trạng thái: Đã kẹt ở FAILED (Cần xử lý tay)."
            )
            NotifierService._broadcast(error_msg_template)
            _check_gemini_circuit(db)
        else:
            job.status = "DRAFT"
            job.last_error = f"AI Generation Error: {e}"
            db.commit()
    finally:
        CURRENT_JOB_ID = None
        
    return True

def _check_gemini_circuit(db):
    global GEMINI_CONSECUTIVE_FAILURES, GEMINI_CIRCUIT_OPEN, GEMINI_CIRCUIT_RESET_TIME
    if GEMINI_CONSECUTIVE_FAILURES >= 3 and not GEMINI_CIRCUIT_OPEN:
        logger.error("🚨 3 CONSECUTIVE GEMINI FAILURES DETECTED! OPENING CIRCUIT BREAKER FOR 1 HOUR.")
        GEMINI_CIRCUIT_OPEN = True
        GEMINI_CIRCUIT_RESET_TIME = time.time() + 3600
        try:
            NotifierService._broadcast(
                "🚨 *CRITICAL ALERT: GEMINI CIRCUIT BREAKER OPEN* 🚨\n\n"
                "Worker AI Generator đã ngưng hoạt động vì lỗi Gemini liên tục (3 lần).\n"
                "👉 Hãy kiểm tra lại cookies hoặc reload trình duyệt để lấy cookie mới.\n"
                "⏱ Hệ thống sẽ tự thử lại sau 1 GIỜ."
            )
        except Exception:
            pass

def run_loop():
    """Main AI Generator loop."""
    global RUNNING, GEMINI_CIRCUIT_OPEN, GEMINI_CIRCUIT_RESET_TIME
    from app.services.notifier import TelegramNotifier
    import app.config as config
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))

    logger.info("AI Worker started. Press Ctrl+C to stop.")
    
    register_signals()
    logger.info("Entering AI polling loop. Tick=60s")
    
    while RUNNING:
        try:
            # Check Circuit Breaker timer
            if GEMINI_CIRCUIT_OPEN:
                if time.time() >= GEMINI_CIRCUIT_RESET_TIME:
                    logger.info("⏱ Circuit Breaker timeout reached. Closing circuit and retrying...")
                    GEMINI_CIRCUIT_OPEN = False
                    GEMINI_CONSECUTIVE_FAILURES = 0 # reset partial
                else:
                    time.sleep(60)
                    continue

            with SessionLocal() as db:
                state = WorkerService.get_or_create_state(db)
                
                if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                    logger.warning(f"Received pending command: {state.pending_command}. Graceful exit requested.")
                    break
                    
                if state.worker_status == "PAUSED":
                    time.sleep(60)
                    continue
                
                found_job = process_draft_job(db)
                
            if not found_job and RUNNING:
                # We can afford to wait a bit longer for AI drafts, e.g. 60 seconds
                time.sleep(60)
                
        except Exception:
            logger.exception("AI Worker encountered a core loop error. Will retry.")
            time.sleep(60)
            
    logger.info("AI Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()
