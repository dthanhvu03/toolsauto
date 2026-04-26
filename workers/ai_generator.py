import time
import logging
import signal
import sys
import os
import threading
from pathlib import Path

# Repo root on sys.path so `python workers/ai_generator.py` works without PYTHONPATH=.
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.services.job_queue import QueueService
from app.services.job import JobService
from app.config import WORKER_TICK_SECONDS
from app.services.worker import WorkerService
from app.services.notifier_service import NotifierService
from app.services.affiliate_ai import AffiliateAIService
from app.database.models import AffiliateLink
import urllib3

# Setup Logging
from app.utils.logger import setup_shared_logger
logger = setup_shared_logger(__name__ if __name__ != "__main__" else "ai_generator")

import app.config as config
from app.services import settings as runtime_settings
from app.constants import JobStatus


RUNNING = True
CURRENT_JOB_ID = None

# Gemini Circuit Breaker
GEMINI_CONSECUTIVE_FAILURES = 0
GEMINI_CIRCUIT_OPEN = False
GEMINI_CIRCUIT_RESET_TIME = 0

# Infra backoff (when chromedriver/UI freezes / local read timeouts)
GEMINI_INFRA_BACKOFF_LEVEL = 0
GEMINI_NEXT_ALLOWED_TS = 0
GEMINI_INFRA_BACKOFF_SCHEDULE_SEC = [300, 900, 1800]  # 5m -> 15m -> 30m

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
    global GEMINI_INFRA_BACKOFF_LEVEL, GEMINI_NEXT_ALLOWED_TS

    # Apply runtime overrides (DB) to this process config (Whisper/limits/toggles)
    try:
        from app.services.settings import apply_runtime_overrides_to_config
        apply_runtime_overrides_to_config(db)
    except Exception:
        pass
    
    if GEMINI_CIRCUIT_OPEN:
        return False

    # If infra backoff is active, don't claim any new jobs yet.
    if GEMINI_NEXT_ALLOWED_TS and time.time() < GEMINI_NEXT_ALLOWED_TS:
        return False
        
    # Needs a dedicated claim function if multiple workers run, but our claim_draft_job 
    # uses FOR UPDATE / row locking appropriately if we wrap it in transactions.
    # SQLite doesn't truly do FOR UPDATE (it's database level), but our single AI worker ensures safety.
    job = QueueService.claim_draft_job(db)
    if not job:
        return False
        
    CURRENT_JOB_ID = job.id
    logger.info("[AI_GEN] [Job-%s] [CLAIM] Claimed DRAFT for AI generation", job.id)
    try:
        NotifierService._broadcast(
            f"🤖 <b>AI đang xử lý</b>\n"
            f"📋 Job #{job.id} | {job.platform} ({job.account.name if job.account else 'Unknown'})\n"
            f"⏳ Trạng thái: AI_PROCESSING"
        )
    except Exception:
        pass
    
    heartbeat_stop = threading.Event()
    heartbeat_interval = 60

    def _heartbeat_loop(job_id: int):
        while not heartbeat_stop.is_set():
            try:
                with SessionLocal() as hb_db:
                    JobService.update_heartbeat(hb_db, job_id)
            except Exception as hb_err:
                # [HB-Fix] Log at DEBUG level to reduce main log noise
                logger.debug("[AI_GEN] [Job-%s] [HEARTBEAT] Refresh failed: %s", job_id, hb_err)
            heartbeat_stop.wait(heartbeat_interval)

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(job.id,),
        daemon=True,
    )
    heartbeat_thread.start()
    
    try:
        from app.services.content_orchestrator import ContentOrchestrator
        from app.services.content_orchestrator import OutputContractViolation
        import re
        
        target_video = job.resolved_processed_media_path if job.resolved_processed_media_path else job.resolved_media_path
        
        existing_salt_match = re.search(r'\[ref:[a-zA-Z0-9]+\]|#v\d{4}', job.caption or "")
        existing_salt = existing_salt_match.group(0) if existing_salt_match else ""
        user_context = (job.caption or "").replace(r"[AI_GENERATE]", "").replace(existing_salt, "").strip()
        
        if user_context.startswith("Context:"):
            user_context = user_context.replace("Context:", "", 1).strip()
            
        orchestrator = ContentOrchestrator()
        ai_style = getattr(job, "ai_style", "short") or "short"

        # Resolve page name & niches for page-aware caption generation
        page_name = ""
        page_niches = []
        if job.target_page and job.account:
            for p in (job.account.managed_pages_list or []):
                if p.get("url") and job.target_page in p["url"]:
                    page_name = p.get("name", "")
                    break
            pn_map = job.account.page_niches_map or {}
            for p_url, niches in pn_map.items():
                if job.target_page in p_url:
                    page_niches = niches if isinstance(niches, list) else []
                    break

        # Fetch available affiliate keywords from DB to let AI match products
        try:
            from app.database.models import AffiliateLink
            aff_keywords = [link.keyword for link in db.query(AffiliateLink).all()]
        except Exception:
            aff_keywords = []

        try:
            ai_result = orchestrator.generate_caption(
                target_video, style=ai_style, context=user_context,
                page_name=page_name, page_niches=page_niches,
                affiliate_keywords=aff_keywords
            )
        except OutputContractViolation as e:
            # Strict JSON mode: do not save prose/options. Retry later with backoff (max 3).
            idx = min(GEMINI_INFRA_BACKOFF_LEVEL, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
            backoff_sec = GEMINI_INFRA_BACKOFF_SCHEDULE_SEC[idx]
            GEMINI_INFRA_BACKOFF_LEVEL = min(GEMINI_INFRA_BACKOFF_LEVEL + 1, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
            GEMINI_NEXT_ALLOWED_TS = time.time() + backoff_sec

            try:
                job.tries = int(job.tries or 0) + 1
            except Exception:
                job.tries = 1

            max_retries = runtime_settings.get_int("ai.max_retries", 3, db=db)
            if int(job.tries) <= max_retries:
                job.status = JobStatus.DRAFT
                job.last_error = f"Gemini output contract violation (try {job.tries}/3). Backoff {backoff_sec}s."
                db.commit()
                logger.warning("[AI_GEN] [Job-%s] [CONTRACT_RETRY] Output contract violation. Keep DRAFT + backoff %ss (try=%s/3).", job.id, backoff_sec, job.tries)
                try:
                    NotifierService._broadcast(
                        f"⚠️ <b>Gemini trả sai format (không phải JSON)</b>\n"
                        f"📋 Job #{job.id}\n"
                        f"⏳ Backoff: {int(backoff_sec/60)} phút rồi tự thử lại.\n"
                        f"📝 Lý do: Enforce JSON output contract"
                    )
                except Exception:
                    pass
                return True
            else:
                job.status = JobStatus.FAILED
                job.last_error = "Gemini output contract violated repeatedly (>3)."
                db.commit()
                logger.error("[AI_GEN] [Job-%s] [CONTRACT_FAILED] Output contract violated repeatedly. Mark FAILED.", job.id)
                try:
                    NotifierService._broadcast(
                        f"🚨 <b>Gemini sai format liên tục</b>\n"
                        f"❌ Job #{job.id}\n"
                        f"🛑 Đã quá 3 lần retry. Mark FAILED.\n"
                        f"👉 Cần xem lại prompt/rules."
                    )
                except Exception:
                    pass
                return True
        
        if ai_result and ai_result.get("caption"):
            final_text = ai_result["caption"].strip()
            hashtags = ai_result.get("hashtags")
            if hashtags:
                final_text += "\n\n" + " ".join(hashtags)
            if existing_salt:
                final_text += f"\n\n{existing_salt}"
                
            job.caption = final_text
            job.status = JobStatus.DRAFT
            
            # Pass AI generated keywords to notifier temporarily
            job._ai_keywords = ai_result.get("keywords") or []
            
            # Xử lý Affiliate Link Injector
            matched_aff_kw = ai_result.get("affiliate_keyword")
            if matched_aff_kw and matched_aff_kw in aff_keywords:
                # Find the corresponding template
                try:
                    from app.database.models import AffiliateLink
                    aff_link = db.query(AffiliateLink).filter(AffiliateLink.keyword == matched_aff_kw).first()
                    if aff_link:
                        # Thay thế placeholder [LINK] bằng URL thực tế
                        comment_text = aff_link.comment_template.replace("[LINK]", aff_link.url)
                        # Gán thẳng vào auto_comment_text của Job
                        job.auto_comment_text = comment_text
                        logger.info("[AI_GEN] [Job-%s] [AFFILIATE] Auto-injected keyword: %s", job.id, matched_aff_kw)
                except Exception as e:
                    logger.error("[AI_GEN] [Job-%s] [AFFILIATE_ERR] Error attaching Affiliate Link: %s", job.id, e)

            
            db.commit()
            logger.info("[AI_GEN] [Job-%s] [DRAFT_READY] AI generation complete. Awaiting user approval.", job.id)
            NotifierService.notify_draft_ready(job)
            try:
                NotifierService._broadcast(
                    f"✅ <b>AI đã trả lời xong</b>\n"
                    f"📋 Job #{job.id}\n"
                    f"🟡 Đang chờ anh duyệt (DRAFT)"
                )
            except Exception:
                pass
            
            # Khởi động lại đếm lỗi trên thành công
            GEMINI_CONSECUTIVE_FAILURES = 0
            GEMINI_INFRA_BACKOFF_LEVEL = 0
            GEMINI_NEXT_ALLOWED_TS = 0
        else:
            try:
                job.tries = int(job.tries or 0) + 1
            except Exception:
                job.tries = 1

            max_retries = runtime_settings.get_int("ai.max_retries", 3, db=db)
            if int(job.tries) <= max_retries:
                job.status = JobStatus.DRAFT
                job.last_error = f"AI Generation returned empty result (try {job.tries}/3)"
                db.commit()
                # Thêm backoff để không lặp vô cực
                idx = min(GEMINI_INFRA_BACKOFF_LEVEL, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                backoff_sec = GEMINI_INFRA_BACKOFF_SCHEDULE_SEC[idx]
                GEMINI_INFRA_BACKOFF_LEVEL = min(GEMINI_INFRA_BACKOFF_LEVEL + 1, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                GEMINI_NEXT_ALLOWED_TS = time.time() + backoff_sec
                
                logger.warning("[AI_GEN] [Job-%s] [EMPTY_RETRY] AI returned empty. Keep DRAFT + backoff %ss (try=%d/3).", job.id, backoff_sec, job.tries)
            else:
                job.status = JobStatus.FAILED
                job.last_error = "AI Generation returned empty repeatedly (>3). Mark FAILED."
                db.commit()
                logger.error("[AI_GEN] [Job-%s] [EMPTY_FAILED] AI returned empty repeatedly. Mark FAILED.", job.id)
                try:
                    NotifierService._broadcast(
                        f"🚨 <b>Lỗi AI Trả về Rỗng Liên Tục</b>\n"
                        f"❌ Job #{job.id}\n"
                        f"🛑 Đã quá 3 lần retry bị rỗng. Đánh dấu FAILED."
                    )
                except Exception:
                    pass
        
    except Exception as e:
        logger.exception("[AI_GEN] [Job-%s] [EXCEPTION] Unhandled exception during AI generation: %s", job.id, e)
        if type(e).__name__ == "GeminiMaxRetriesExceeded":
            msg = str(e)

            # Policy per PLAN-20260317-01 (Review):
            # - Auth/Cookie/Captcha => FAILED + circuit breaker
            # - Infra timeout/driver crash => DO NOT FAILED; backoff and retry later
            from app.constants import GEMINI_INFRA_MARKERS, GEMINI_AUTH_MARKERS
            infra_markers = GEMINI_INFRA_MARKERS
            auth_markers = GEMINI_AUTH_MARKERS

            is_infra = any(m in msg for m in infra_markers)
            is_auth = any(m.lower() in msg.lower() for m in auth_markers)
            is_policy = any(p in msg.lower() for p in ["content policy", "safety", "unsafe", "can't help", "refuse"])

            if is_infra and not is_auth:
                # Backoff globally (machine is under pressure / chromedriver hanged)
                idx = min(GEMINI_INFRA_BACKOFF_LEVEL, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                backoff_sec = GEMINI_INFRA_BACKOFF_SCHEDULE_SEC[idx]
                GEMINI_INFRA_BACKOFF_LEVEL = min(GEMINI_INFRA_BACKOFF_LEVEL + 1, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                GEMINI_NEXT_ALLOWED_TS = time.time() + backoff_sec
                # Per-plan: backoff retry tối đa 3 lần rồi mới FAILED
                try:
                    job.tries = int(job.tries or 0) + 1
                except Exception:
                    job.tries = 1
                max_retries = runtime_settings.get_int("ai.max_retries", 3, db=db)
                if int(job.tries) <= max_retries:
                    job.status = JobStatus.DRAFT
                    job.last_error = f"Gemini infra timeout (try {job.tries}/3). Backoff {backoff_sec}s. Last: {msg}"
                    db.commit()
                    logger.error("[AI_GEN] [Job-%s] [INFRA_TIMEOUT] Keep DRAFT + backoff %ss (try=%s/3).", job.id, backoff_sec, job.tries)
                else:
                    job.status = JobStatus.FAILED
                    job.last_error = f"Gemini infra timeout exceeded (>{3} retries). Last: {msg}"
                    db.commit()
                    logger.error("[AI_GEN] [Job-%s] [INFRA_FAILED] Infra timeout exceeded retries. Mark FAILED.", job.id)
                try:
                    NotifierService._broadcast(
                        f"⚠️ <b>Gemini RPA bị timeout/hạ tầng</b>\n"
                        f"📋 Job #{job.id}\n"
                        f"⏳ Backoff: {int(backoff_sec/60)} phút rồi tự thử lại.\n"
                        f"📝 Error: {msg[:180]}"
                    )
                except Exception:
                    pass
                # DO NOT increment circuit-breaker failures for infra
            elif is_auth:
                # Cookie/auth issues: FAILED + open circuit breaker immediately
                job.status = JobStatus.FAILED
                job.last_error = f"Gemini auth/cookie failed: {msg}"
                db.commit()
                GEMINI_CONSECUTIVE_FAILURES = 999
                GEMINI_CIRCUIT_OPEN = True
                GEMINI_CIRCUIT_RESET_TIME = time.time() + 1800  # 30m
                try:
                    NotifierService._broadcast(
                        f"🚨 <b>GEMINI COOKIE/AUTH FAILED</b>\n"
                        f"❌ Job #{job.id}\n"
                        f"🛑 Circuit breaker: tạm ngưng 30 phút.\n"
                        f"👉 Cần login lấy cookie mới.\n"
                        f"📝 Error: {msg[:220]}"
                    )
                except Exception:
                    pass
            elif is_policy:
                # Content policy refusal: FAILED (user needs to adjust content/prompt)
                job.status = JobStatus.FAILED
                job.last_error = f"Gemini content policy refused: {msg}"
                db.commit()
                try:
                    NotifierService._broadcast(
                        f"🚫 <b>Gemini từ chối (Content Policy)</b>\n"
                        f"❌ Job #{job.id}\n"
                        f"📝 Error: {msg[:220]}"
                    )
                except Exception:
                    pass
            else:
                logger.error("[AI_GEN] [Job-%s] [AUTH_FAILED] Gemini auth/logic failed after retries. Mark FAILED.", job.id)
                job.status = JobStatus.FAILED
                job.last_error = f"Gemini RPA Failed: {e}"
                db.commit()
                GEMINI_CONSECUTIVE_FAILURES += 1
                error_msg_template = (
                    f"🚨 <b>GEMINI RPA FAILED</b>\n"
                    f"❌ Job ID: {job.id}\n"
                    f"⚠️ Error: Gemini không phản hồi sau 3 lần thử retry.\n"
                    f"🛑 Trạng thái: FAILED (cần kiểm tra cookie/prompt)."
                )
                NotifierService._broadcast(error_msg_template)
                _check_gemini_circuit(db)
        else:
            try:
                job.tries = int(job.tries or 0) + 1
            except Exception:
                job.tries = 1

            max_retries = runtime_settings.get_int("ai.max_retries", 3, db=db)
            if int(job.tries) <= max_retries:
                job.status = JobStatus.DRAFT
                job.last_error = f"AI Generation Error (try {job.tries}/3): {e}"
                db.commit()
                
                idx = min(GEMINI_INFRA_BACKOFF_LEVEL, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                backoff_sec = GEMINI_INFRA_BACKOFF_SCHEDULE_SEC[idx]
                GEMINI_INFRA_BACKOFF_LEVEL = min(GEMINI_INFRA_BACKOFF_LEVEL + 1, len(GEMINI_INFRA_BACKOFF_SCHEDULE_SEC) - 1)
                GEMINI_NEXT_ALLOWED_TS = time.time() + backoff_sec
                
                logger.warning("[AI_GEN] [Job-%s] [EXCEPTION_RETRY] Unhandled exception: %s. Keep DRAFT + backoff %ss (try=%d/3).", job.id, e, backoff_sec, job.tries)
            else:
                job.status = JobStatus.FAILED
                job.last_error = f"AI Generation Error repeatedly (>3): {e}. Mark FAILED."
                db.commit()
                logger.error("[AI_GEN] [Job-%s] [EXCEPTION_FAILED] AI generation error exceeded retries. Mark FAILED.", job.id)
                try:
                    NotifierService._broadcast(
                        f"🚨 <b>Lỗi AI Generation Liên Tục</b>\n"
                        f"❌ Job #{job.id}\n"
                        f"🛑 Đã quá 3 lần retry bị lỗi. Đánh dấu FAILED.\n"
                        f"⚠️ Lỗi: {str(e)[:100]}"
                    )
                except Exception:
                    pass
    finally:
        heartbeat_stop.set()
        try:
            heartbeat_thread.join(timeout=5)
        except Exception:
            pass
        CURRENT_JOB_ID = None
        
    return True

def _process_pending_affiliate_links(db: Session):
    """
    Finds AffiliateLinks with ai_status=JobStatus.PENDING and generates comments.
    Processes one link per tick to minimize rate limiting impact.
    """
    link = db.query(AffiliateLink).filter(AffiliateLink.ai_status == JobStatus.PENDING).first()
    if not link:
        return

    link.ai_status = "PROCESSING"
    db.commit()
    
    logger.info(f"[AffiliateBot] Generating comment for keyword: {link.keyword}")
    try:
        new_comment = AffiliateAIService.generate_comment(link.keyword, link.url)
        if new_comment:
            link.comment_template = new_comment
            link.ai_status = JobStatus.DONE
            logger.info(f"[AffiliateBot] Successfully generated comment for: {link.keyword}")
        else:
            link.ai_status = JobStatus.FAILED
            logger.warning(f"[AffiliateBot] Failed to generate comment for: {link.keyword}")
    except Exception as e:
        link.ai_status = JobStatus.FAILED
        logger.error(f"[AffiliateBot] Exception generating comment: {e}")
    
    db.commit()

def _check_gemini_circuit(db):
    global GEMINI_CONSECUTIVE_FAILURES, GEMINI_CIRCUIT_OPEN, GEMINI_CIRCUIT_RESET_TIME
    if GEMINI_CONSECUTIVE_FAILURES >= 3 and not GEMINI_CIRCUIT_OPEN:
        logger.error("🚨 3 CONSECUTIVE GEMINI FAILURES DETECTED! OPENING CIRCUIT BREAKER FOR 1 HOUR.")
        GEMINI_CIRCUIT_OPEN = True
        GEMINI_CIRCUIT_RESET_TIME = time.time() + 3600
        try:
            NotifierService._broadcast(
                "🚨 <b>CRITICAL ALERT: GEMINI CIRCUIT BREAKER OPEN</b> 🚨\n\n"
                "Worker AI Generator đã ngưng hoạt động vì lỗi Gemini liên tục (3 lần).\n"
                "👉 Hãy kiểm tra lại cookies hoặc reload trình duyệt để lấy cookie mới.\n"
                "⏱ Hệ thống sẽ tự thử lại sau 1 GIỜ."
            )
        except Exception:
            pass

def _auto_style_default(db):
    """If a job has been AWAITING_STYLE for > 30 minutes, default to 'short' and move to DRAFT."""
    from app.database.models import Job
    import time
    
    threshold_ts = int(time.time()) - 1800 # 30 mins
    
    jobs_to_update = db.query(Job).filter(
        Job.status == JobStatus.AWAITING_STYLE,
        Job.created_at < threshold_ts
    ).all()
    
    if jobs_to_update:
        logger.info("Auto-defaulting %d AWAITING_STYLE jobs to 'short' (30m timeout passed)", len(jobs_to_update))
        for j in jobs_to_update:
            j.ai_style = "short"
            j.status = JobStatus.DRAFT
            
            # Optionally notify that it was auto-selected
            from app.services.notifier_service import NotifierService
            account_name = j.account.name if j.account else "Unknown"
            try:
                NotifierService._broadcast(f"⏳ <b>Hết thời gian chờ (30 phút)</b>\nJob #{j.id} ({account_name}) đã tự động được chọn phong cách: NGẮN GỌN (SHORT).\nAI đang tiến hành viết nội dung...")
            except Exception:
                pass
        db.commit()

def run_loop():
    """Main AI Generator loop."""
    global RUNNING, GEMINI_CIRCUIT_OPEN, GEMINI_CIRCUIT_RESET_TIME
    from app.services.notifier_service import TelegramNotifier
    import app.config as config
    from app.services import settings as runtime_settings
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))

    logger.info("AI Worker started. Press Ctrl+C to stop.")
    
    # ─── MANGAGE STUCK JOBS ON STARTUP ───
    try:
        from app.database.models import Job
        with SessionLocal() as db:
            stuck_jobs = db.query(Job).filter(Job.status == JobStatus.AI_PROCESSING).update({"status": JobStatus.DRAFT})
            if stuck_jobs > 0:
                logger.info("Reset %d stuck jobs from AI_PROCESSING to DRAFT on startup.", stuck_jobs)
            db.commit()
    except Exception as e:
        logger.error("Failed to reset stuck AI jobs on startup: %s", e)
    
    register_signals()
    logger.info("Entering AI polling loop. Tick=60s")
    # Adaptive idle backoff to reduce DB polling when no draft jobs
    idle_sleep = int(os.getenv("AI_IDLE_SLEEP_BASE_SEC", "30"))
    idle_sleep_cap = int(os.getenv("AI_IDLE_SLEEP_CAP_SEC", "120"))
    
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
                
                # Check for jobs that need auto-defaulting because user didn't respond to telegram style selection
                _auto_style_default(db)
                
                # Check for affiliate links needing AI comments (Phase 3 SaaS Hardening)
                _process_pending_affiliate_links(db)
                
                found_job = process_draft_job(db)
                
            if not found_job and RUNNING:
                time.sleep(idle_sleep)
                idle_sleep = min(idle_sleep * 2, idle_sleep_cap)
            else:
                idle_sleep = int(os.getenv("AI_IDLE_SLEEP_BASE_SEC", "30"))
                
        except Exception:
            logger.exception("AI Worker encountered a core loop error. Will retry.")
            time.sleep(60)
            
    logger.info("AI Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()
