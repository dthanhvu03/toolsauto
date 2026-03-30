import time
import logging
import signal
import sys
import os
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.services.queue import QueueService
from app.services.job import JobService
from app.config import WORKER_CRASH_THRESHOLD_SECONDS
from app.adapters.dispatcher import Dispatcher
from app.services.worker import WorkerService
from app.services.account import AccountService
from app.services.system_monitor import SystemMonitorService
import app.config as config
from app.services.notifier import NotifierService

# Suicide Timer for Deadlock Prevention
import threading

def kill_if_stuck(label: str, timeout: int):
    """
    Sets a hard timeout for blocking operations like browser driving.
    If the timeout is reached, the worker forcefully exits (suicide)
    so that PM2 or systemd can restart it clean, avoiding zombie hangs.
    """
    def suicide():
        logger.error(f"[FATAL DEADLOCK] {label} hung for over {timeout}s! Committing suicide (os._exit) to trigger restart.")
        os._exit(1)
        
    timer = threading.Timer(timeout, suicide)
    timer.daemon = True
    timer.start()
    return timer

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [PUBLISHER] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

RUNNING = True
CURRENT_JOB_ID = None

def handle_sigterm(signum, frame):
    """Graceful shutdown handler for SIGTERM/SIGINT."""
    global RUNNING
    logger.warning("Received termination signal. Preparing to shut down...")
    RUNNING = False
    
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

    # Reset accounts stuck in ENGAGING (stale lock from crashed engagement)
    from app.database.models import Account
    stale_engaging = db.query(Account).filter(
        Account.login_status == "ENGAGING"
    ).all()
    if stale_engaging:
        for acc in stale_engaging:
            acc.login_status = "ACTIVE"
            logger.warning("Reset stale ENGAGING lock for account '%s' → ACTIVE", acc.name)
        db.commit()
        logger.warning("Recovered %d accounts from stale ENGAGING state.", len(stale_engaging))

def process_single_job(db: Session):
    """
    Attempts to claim and process one PENDING job.
    Returns True if a job was found, False otherwise.
    """
    global CURRENT_JOB_ID
    
    from app.database.models import Job
    from app.services.settings import apply_runtime_overrides_to_config

    # Apply runtime overrides (DB) to this process config
    apply_runtime_overrides_to_config(db)
    from app.config import MAX_CONCURRENT_ACCOUNTS
    
    # Pre-check: Limit concurrent Facebook accounts
    running_fb_count = db.query(Job).filter(
        Job.status == "RUNNING", 
        Job.platform == "facebook"
    ).count()
    if running_fb_count >= MAX_CONCURRENT_ACCOUNTS:
        logger.info(f"⏳ Giới hạn an toàn: Đang có {running_fb_count}/{MAX_CONCURRENT_ACCOUNTS} acc FB chạy. Tạm dừng nhận job mới...")
        return False

    # Adaptive Throttling: Pause if system resources are under pressure
    health = SystemMonitorService().check_health()
    if health.get("ram_percent") and health["ram_percent"] > 90:
        logger.warning(f"🛑 Hệ thống quá tải RAM ({health['ram_percent']}%). Tạm dừng claim job trong 60s...")
        return False
    if health.get("chrome_playwright_count") and health["chrome_playwright_count"] >= 15:
        logger.warning(f"🛑 Quá nhiều trình duyệt đang mở ({health['chrome_playwright_count']}). Tạm dừng claim job...")
        return False

    job = QueueService.claim_next_job(db)
    if not job:
        return False
        
    # Enforce Daily Limit (per-page logic)
    effective_daily_limit = 0
    try:
        # Runtime cap overrides account setting (if set)
        effective_daily_limit = int(getattr(config, "POSTS_PER_PAGE_PER_DAY", 0) or 0)
    except Exception:
        effective_daily_limit = 0
    if (not effective_daily_limit) and job.account:
        effective_daily_limit = int(getattr(job.account, "daily_limit", 0) or 0)

    if job.account and effective_daily_limit > 0:
        from datetime import datetime, time as time_obj
        from zoneinfo import ZoneInfo
        import app.config as app_config
        today_start = int(datetime.combine(datetime.now(ZoneInfo(app_config.TIMEZONE)).date(), time_obj.min).timestamp())
        
        # Count DONE jobs today for this SPECIFIC target_page.
        # If POSTS_PER_PAGE_PER_DAY cap is enabled, enforce per-page across all accounts.
        q = db.query(Job).filter(
            Job.target_page == job.target_page,
            Job.status == "DONE",
            Job.finished_at >= today_start
        )
        if not int(getattr(config, "POSTS_PER_PAGE_PER_DAY", 0) or 0):
            q = q.filter(Job.account_id == job.account_id)
        posted_today = q.count()
        
        if posted_today >= effective_daily_limit:
            # Try to reassign to another page that still has quota
            reassigned = False
            if job.account and hasattr(job.account, 'target_pages_list'):
                alt_pages = [p for p in (job.account.target_pages_list or []) if p != job.target_page]
                for alt_page in alt_pages:
                    alt_count = db.query(Job).filter(
                        Job.target_page == alt_page,
                        Job.status == "DONE",
                        Job.finished_at >= today_start
                    )
                    if not int(getattr(config, "POSTS_PER_PAGE_PER_DAY", 0) or 0):
                        alt_count = alt_count.filter(Job.account_id == job.account_id)
                    if alt_count.count() < effective_daily_limit:
                        logger.info("[Job %s] Page '%s' maxed out. Redirecting → '%s'",
                                    job.id, job.target_page, alt_page)
                        job.target_page = alt_page
                        job.status = "PENDING"
                        db.commit()
                        reassigned = True
                        break

            if not reassigned:
                logger.info("[Job %s] Daily limit (%s) reached for ALL pages. Requeuing for tomorrow.",
                            job.id, effective_daily_limit)
                job.status = "PENDING"
                job.schedule_ts = today_start + 86400 + 3600  # Tomorrow 1 AM
                db.commit()
            return True

    # Xin ý kiến giấc ngủ (Human Rest Cycle)
    if job.account and getattr(job.account, 'is_sleeping', False):
        logger.info("[Job %s] Account '%s' is SLEEPING (%s - %s). Postponing job for 10 minutes.", 
                    job.id, job.account.name, job.account.sleep_start_time, job.account.sleep_end_time)
        job.status = "PENDING"
        job.schedule_ts = int(time.time()) + 600
        db.commit()
        return True
        
    CURRENT_JOB_ID = job.id
    logger.info("[Job %s] Claimed for account '%s' on %s", job.id, job.account.name, job.platform)
    
    try:
        # Keep Job.last_heartbeat_at fresh while dispatch/publish is running.
        # Otherwise QueueService.recover_crashed_jobs() may treat it as stale and reset RUNNING -> PENDING.
        import threading
        heartbeat_stop = threading.Event()
        heartbeat_interval = max(20, min(60, int(WORKER_CRASH_THRESHOLD_SECONDS // 3)))

        def _heartbeat_loop(job_id: int):
            while not heartbeat_stop.is_set():
                try:
                    with SessionLocal() as hb_db:
                        JobService.update_heartbeat(hb_db, job_id)
                except Exception as hb_err:
                    logger.warning("[Job %s] Heartbeat refresh failed: %s", job_id, hb_err)
                # Wait with stop support
                heartbeat_stop.wait(heartbeat_interval)

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(job.id,),
            daemon=True,
        )
        heartbeat_thread.start()

        # SAFETY GUARD: Never publish a job with un-processed AI placeholder
        if job.caption and "[AI_GENERATE]" in job.caption:
            logger.warning("[Job %s] BLOCKED: Caption still contains [AI_GENERATE]. Resetting to DRAFT.", job.id)
            job.status = "DRAFT"
            db.commit()
            CURRENT_JOB_ID = None
            return True
        
        # START DEADLOCK TIMER (15 mins hard limit for publishing)
        suicide_timer = kill_if_stuck(f"Job {job.id} Publish", timeout=900)
        
        try:
            publish_result = Dispatcher.dispatch(job, db=db)
        finally:
            heartbeat_stop.set()
            try:
                heartbeat_thread.join(timeout=5)
            except Exception:
                pass
            suicide_timer.cancel() # Cancel if finished normally
        
        
        if publish_result.ok:
            logger.info("[Job %s] Successfully published!", job.id)
            
            import random
            # Re-apply overrides in case settings changed while publishing
            apply_runtime_overrides_to_config(db)
            from app.config import POST_DELAY_MIN_SEC, POST_DELAY_MAX_SEC
            delay_sec = random.randint(POST_DELAY_MIN_SEC, POST_DELAY_MAX_SEC)
            logger.info(f"[Job {job.id}] Nghỉ ngơi {delay_sec}s để giả lập người thật trước khi chốt Job...")
            time.sleep(delay_sec)
            
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
            if publish_result.is_fatal or job.tries >= job.max_tries:
                NotifierService.notify_job_failed(job, publish_result.error)
            
            if publish_result.details and publish_result.details.get("invalidate_account"):
                logger.error("[Job %s] Adapter triggered account invalidation. Disabling account '%s'.", job.id, job.account.name)
                AccountService.invalidate_account(
                    db=db, 
                    account_id=job.account.id, 
                    reason=publish_result.error
                )
                NotifierService.notify_account_invalid(job.account.name, publish_result.error)
                
    except Exception as e:
        try:
            heartbeat_stop.set()
        except Exception:
            pass
        logger.exception("[Job %s] Unhandled worker exception processing job: %s", job.id, e)
        JobService.mark_failed_or_retry(db, job, str(e), is_fatal=False)
        
    finally:
        try:
            db.refresh(job)
            if job.status in ["DONE", "FAILED"]:
                # 1. Dọn file render qua xử lý
                p_path = job.resolved_processed_media_path
                if p_path and os.path.exists(p_path):
                    logger.info("[Job %s] Terminal state reached. Cleaning up processed media: %s", job.id, p_path)
                    os.remove(p_path)
                
                # 2. Dọn luôn file gốc mồ côi
                m_path = job.resolved_media_path
                if m_path and os.path.exists(m_path):
                    logger.info("[Job %s] Terminal state reached. Cleaning up original media: %s", job.id, m_path)
                    os.remove(m_path)
                    
        except Exception as cleanup_err:
            logger.warning("[Job %s] Failed to clean up media file: %s", job.id, cleanup_err)
            
        CURRENT_JOB_ID = None
        
    return True

def run_loop():
    """Main Publisher loop."""
    global RUNNING
    from app.services.notifier import TelegramNotifier
    import app.config as config
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
    
    logger.info("Publisher Worker started. Press Ctrl+C to stop.")
    
    register_signals()
    
    with SessionLocal() as db:
        check_crash_recovery(db)
        state = WorkerService.get_or_create_state(db)
        state.worker_started_at = int(time.time())
        db.commit()
        
    logger.info("Entering polling loop. Tick=%ss", config.WORKER_TICK_SECONDS)
    # Adaptive idle backoff to reduce DB polling + CPU wakeups when queue is empty
    idle_sleep = config.WORKER_TICK_SECONDS
    idle_sleep_cap = int(os.getenv("PUBLISHER_IDLE_SLEEP_CAP_SEC", "60"))
    
    while RUNNING:
        try:
            with SessionLocal() as db:
                state = WorkerService.get_or_create_state(db)
                
                # Separate Heartbeat for Publisher could be tracked separately in DB later, 
                # for now MVP uses the existing global one
                WorkerService.update_heartbeat(db, CURRENT_JOB_ID)
                
                if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                    logger.warning(f"Received pending command: {state.pending_command}. Graceful exit requested.")
                    # Only one worker should clear the command, but for now we'll just exit.
                    break
                    
                if state.worker_status == "PAUSED":
                    time.sleep(config.WORKER_TICK_SECONDS)
                    continue
                    
                config.SAFE_MODE = state.safe_mode
                
                found_job = process_single_job(db)
                
            if not found_job and RUNNING:
                with SessionLocal() as db_idle:
                    _maybe_idle_engagement(db_idle)
                time.sleep(idle_sleep)
                idle_sleep = min(idle_sleep * 2, idle_sleep_cap)
            else:
                # Reset backoff once we actually do work
                idle_sleep = config.WORKER_TICK_SECONDS
                
        except Exception:
            logger.exception("Publisher encountered a core loop error. Will retry.")
            time.sleep(config.WORKER_TICK_SECONDS)
            
    logger.info("Publisher process completed gracefully.")


# ---------------------------------------------------------------------------
# Idle Engagement (Account Warming)
# ---------------------------------------------------------------------------

# In-memory cooldown tracker: {account_id: last_engagement_unix_ts}
_last_engagement_ts: dict[int, float] = {}
IDLE_COOLDOWN_MINUTES = 45  # Mỗi acc nghỉ tối thiểu 45 phút giữa các phiên dạo


def _maybe_idle_engagement(db: Session):
    """
    When idle (no pending jobs), pick an account that hasn't engaged recently
    and run a short engagement session.  Hard timeout ensures the worker is
    never blocked for long.

    Safety mechanisms:
      - Account is locked via login_status="ENGAGING" to prevent concurrent
        browser sessions from the Publisher claiming the same account.
      - Per-account cooldown (IDLE_COOLDOWN_MINUTES) prevents unnaturally
        frequent engagement that triggers Meta anti-bot detection.
    """
    import random as _rand
    from app.adapters.facebook.engagement import FacebookEngagementTask, parse_niche_topics

    if not config.IDLE_ENGAGEMENT_ENABLED:
        return

    # Auto-disable idle engagement when backlog is high (protect 8GB RAM machines)
    try:
        from app.database.models import Job
        threshold = int(os.getenv("IDLE_ENGAGEMENT_DISABLE_WHEN_PENDING", "10"))
        backlog = db.query(Job).filter(
            Job.status.in_(["PENDING", "RUNNING", "DRAFT", "AI_PROCESSING", "AWAITING_STYLE"])
        ).count()
        if backlog >= threshold:
            logger.info("[IDLE] Backlog=%d >= %d. Skipping idle engagement.", backlog, threshold)
            return
    except Exception:
        # Never block publishing due to idle warmup checks
        pass

    # Pick a random active Facebook account
    from app.database.models import Account
    import time as _time
    now = _time.time()

    accounts = db.query(Account).filter(
        Account.is_active == True,
        Account.login_status == "ACTIVE",
        Account.platform == "facebook",
    ).all()
    
    # Lọc bỏ các tài khoản đang trong giờ ngủ đông
    awake_accounts = [acc for acc in accounts if hasattr(acc, 'is_sleeping') and not acc.is_sleeping]

    # Lọc bỏ các acc vừa dạo xong chưa đủ cooldown (45 phút)
    cooldown_sec = IDLE_COOLDOWN_MINUTES * 60
    eligible_accounts = [
        acc for acc in awake_accounts
        if (now - _last_engagement_ts.get(acc.id, 0)) >= cooldown_sec
    ]

    if not eligible_accounts:
        return

    account = _rand.choice(eligible_accounts)
    niche_keywords = parse_niche_topics(getattr(account, "niche_topics", None))
    competitor_urls = parse_niche_topics(getattr(account, "competitor_urls", None))

    logger.info("[IDLE] Starting engagement session for account '%s' (niche: %s, competitors: %d)",
                account.name, niche_keywords or "general", len(competitor_urls))

    # ── LOCK: Đánh dấu acc đang ENGAGING để Publisher không claim job cho acc này ──
    account.login_status = "ENGAGING"
    db.commit()
    logger.info("[IDLE] Account '%s' locked → ENGAGING", account.name)

    # Notify Telegram — session started
    try:
        c_count_text = f"\n🎯 Đối thủ: {len(competitor_urls)} links" if competitor_urls else ""
        NotifierService._broadcast(
            f"🤖 <b>Idle Engagement</b>\n"
            f"▶️ Bắt đầu nuôi tài khoản: <b>{account.name}</b>\n"
            f"📋 Niche: {', '.join(niche_keywords) if niche_keywords else 'general'}{c_count_text}"
        )
    except Exception:
        pass

    # Open a temporary browser session (reuse adapter's session pattern)
    from app.adapters.facebook.adapter import FacebookAdapter
    adapter = FacebookAdapter()

    try:
        if not adapter.open_session(account.resolved_profile_path):
            logger.warning("[IDLE] Cannot open browser session for '%s'. Skipping.", account.name)
            return

        task = FacebookEngagementTask(adapter.page)

        # Write "ENGAGING" status to DB for Dashboard display
        _update_engagement_status(db, "ENGAGING", f"Đang chọn action... ({account.name})")

        # START DEADLOCK TIMER for Idle Engagement (20 mins hard limit)
        idle_suicide_timer = kill_if_stuck(f"Idle Engagement ({account.name})", timeout=1200)

        try:
            result = task.run_random_action(
                max_duration=config.IDLE_MAX_DURATION_SECONDS,
                niche_keywords=niche_keywords or None,
                competitor_urls=competitor_urls or None,
            )
        finally:
            idle_suicide_timer.cancel()


        # Update detail with actual action chosen
        action_labels = {
            "scroll_news_feed": "📜 Lướt News Feed",
            "watch_reels": "🎬 Xem Reels",
            "search_topic": "🔍 Tìm kiếm chủ đề",
            "spy_competitor": "🕵️ Dạo kênh Đối thủ",
        }
        action_label = action_labels.get(result.get("action"), result.get("action", ""))
        _update_engagement_status(db, "ENGAGING", f"{action_label} — {account.name}")

        if result.get("checkpointed"):
            logger.error("[IDLE] Account '%s' CHECKPOINTED during engagement! Quarantining.", account.name)
            account.login_status = "INVALID"
            account.login_error = "Checkpoint detected during idle engagement"
            account.is_active = False
            db.commit()
            
            # Notify via Telegram — checkpoint
            try:
                NotifierService._broadcast(
                    f"🤖 <b>Idle Engagement</b>\n"
                    f"🚨 <b>CHECKPOINT</b> — Tài khoản <b>{account.name}</b> bị khóa!\n"
                    f"⛔ Action: {action_label}\n"
                    f"🔒 Đã cách ly tài khoản (INVALID)"
                )
                NotifierService.notify_account_invalid(
                    account.name,
                    "Checkpointed during idle engagement session",
                )
            except Exception:
                pass

        elif result.get("ok"):
            logger.info("[IDLE] Engagement completed: action=%s", result.get("action"))
            # Notify Telegram — success
            try:
                urls_list = result.get("urls", [])
                links_text = ""
                if urls_list:
                    # Hiển thị tối đa 3 links tránh quá dài
                    links_text = "\n🔗 " + "\n🔗 ".join(urls_list[:3])
                    if len(urls_list) > 3:
                        links_text += f"\n...và {len(urls_list)-3} link khác"

                NotifierService._broadcast(
                    f"🤖 <b>Idle Engagement</b>\n"
                    f"✅ Hoàn tất: {action_label}\n"
                    f"👤 Account: <b>{account.name}</b>"
                    f"{links_text}"
                )
            except Exception:
                pass
        else:
            logger.warning("[IDLE] Engagement failed: %s", result.get("error"))
            # Notify Telegram — failed
            try:
                NotifierService._broadcast(
                    f"🤖 <b>Idle Engagement</b>\n"
                    f"⚠️ Thất bại: {action_label}\n"
                    f"👤 Account: <b>{account.name}</b>\n"
                    f"❌ Lỗi: {result.get('error', 'Unknown')}"
                )
            except Exception:
                pass

    except Exception as e:
        logger.warning("[IDLE] Unexpected error during engagement: %s", e)

    finally:
        adapter.close_session()
        _update_engagement_status(db, None, None)
        # ── UNLOCK: Trả acc về ACTIVE (trừ khi đã bị checkpoint → INVALID) ──
        try:
            db.refresh(account)
            if account.login_status == "ENGAGING":
                account.login_status = "ACTIVE"
                db.commit()
                logger.info("[IDLE] Account '%s' unlocked → ACTIVE", account.name)
        except Exception:
            pass
        # Ghi nhận thời gian dạo cuối cùng cho cooldown
        _last_engagement_ts[account.id] = _time.time()


def _update_engagement_status(db: Session, status, detail):
    """Update engagement status in SystemState for Dashboard display."""
    try:
        state = WorkerService.get_or_create_state(db)
        state.engagement_status = status
        state.engagement_detail = detail
        db.commit()
    except Exception:
        pass  # Non-critical, don't crash worker


if __name__ == "__main__":
    run_loop()
