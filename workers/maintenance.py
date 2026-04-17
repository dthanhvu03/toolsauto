import os
import time
import logging
import signal
import subprocess
import sys
from pathlib import Path

# Repo root on sys.path so `python workers/maintenance.py` works without PYTHONPATH=.
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Setup Logging before importing app.* modules
from app.utils.logger import setup_shared_logger
setup_shared_logger("app")
logger = setup_shared_logger(__name__ if __name__ != "__main__" else "maintenance")

from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.services.worker import WorkerService
from app.services.cleanup import CleanupService
from app.services.metrics_checker import MetricsChecker
from app.services.notifier_service import NotifierService, TelegramNotifier
from app.services.system_monitor import SystemMonitorService
from app.services.viral_processor import ViralProcessorService
import app.config as config
from app.services import settings as runtime_settings
from app.constants import JobStatus, ViralStatus

RUNNING = True
CURRENT_POLLER = None
DAILY_SUMMARY_HOUR = 23
_last_summary_date = None

MAINT_SKIP_HEAVY_WHEN_PENDING = int(os.getenv("MAINT_SKIP_HEAVY_WHEN_PENDING", "10"))

_last_insights_ts = 0
_last_summary_ts = 0
_last_discovery_ts = 0
_last_boost_ts = 0


def _pending_backlog(db: Session) -> int:
    """Count jobs that indicate backlog; used to decide whether to skip heavy maintenance tasks."""
    from app.database.models import Job
    return db.query(Job).filter(
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DRAFT, JobStatus.AI_PROCESSING, JobStatus.AWAITING_STYLE])
    ).count()


def handle_sigterm(signum, frame):
    """Graceful shutdown handler for SIGTERM/SIGINT."""
    global RUNNING, CURRENT_POLLER
    logger.warning("Received termination signal. Preparing to shut down Maintenance Worker...")
    RUNNING = False
    
    if CURRENT_POLLER:
        logger.info("Stopping TelegramPoller gracefully...")
        CURRENT_POLLER.stop()
        
    sys.exit(0)

def register_signals():
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

_last_orphan_cleanup_ts: float = 0

def _cleanup_orphaned_virals(db: Session):
    """
    Check if any ViralMaterial with target_page is pointing to a deleted page.
    If so, reset target_page to NULL so they get reassigned via round-robin.
    Runs every 1 hour to save performance.
    """
    global _last_orphan_cleanup_ts
    now = time.time()
    if (now - _last_orphan_cleanup_ts) < 3600:
        return
        
    _last_orphan_cleanup_ts = now
    
    try:
        from app.database.models import Account, ViralMaterial
        accounts = db.query(Account).filter(Account.is_active == True).all()
        
        active_pages = set()
        for acc in accounts:
            for p in (acc.managed_pages_list or []):
                if p.get("url"):
                    active_pages.add(p["url"])
            for t in (acc.target_pages_list or []):
                active_pages.add(t)
                
        if not active_pages:
            return  # Safety fallback: don't cleanup if no active pages at all
            
        virals = db.query(ViralMaterial).filter(
            ViralMaterial.status.in_([ViralStatus.NEW, ViralStatus.REUP]),
            ViralMaterial.target_page.isnot(None),
            ViralMaterial.target_page != ""
        ).all()
        
        orphans_fixed = 0
        for v in virals:
            if v.target_page not in active_pages:
                v.target_page = None
                orphans_fixed += 1
                
        if orphans_fixed > 0:
            logger.info("🧹 Auto-Cleaned %d orphaned viral materials (target page deleted).", orphans_fixed)

        # 2. Smart Cleanup: Tự động đào thải video ế
        import os
        stale_threshold = int(time.time()) - (runtime_settings.get_int('worker.maintenance.stale_threshold_hours', 48, db=db) * 3600)
        stale_virals = db.query(ViralMaterial).filter(
            ViralMaterial.status == ViralStatus.NEW,
            ViralMaterial.created_at < stale_threshold
        ).all()
        
        stale_count = 0
        for v in stale_virals:
            # Construction path based on deterministic naming: content/reup/<platform>/viral_<id>_*
            try:
                platform_subdir = os.path.join(str(config.REUP_DIR), v.platform or "unknown")
                if os.path.exists(platform_subdir):
                    import glob
                    pattern = os.path.join(platform_subdir, f"viral_{v.id}_*")
                    for matching_file in glob.glob(pattern):
                        try:
                            os.remove(matching_file)
                        except OSError:
                            pass
            except Exception:
                pass
            db.delete(v)
            stale_count += 1
            
        if stale_count > 0:
            logger.info("🗑️ Smart Cleanup: Đã xóa %d video ế quá hạn để dọn dung lượng.", stale_count)

        if orphans_fixed > 0 or stale_count > 0:
            db.commit()

    except Exception as e:
        db.rollback()
        logger.error("Error cleaning orphaned/stale virals: %s", e)

def _check_daily_summary(db):
    """Gửi báo cáo tổng hợp ngày nếu đến giờ."""
    global _last_summary_date
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
            db.rollback()
            logger.error("Daily summary failed: %s", e)


# Hourly tracker cho TikTok scraping (chạy mỗi 1 giờ, không mỗi 5 phút)
_last_tiktok_scrape_ts: float = 0
TIKTOK_SCRAPE_INTERVAL_SEC = runtime_settings.get_int('worker.maintenance.tiktok_scrape_sec', 3600)  # 1 giờ


def _scrape_tiktok_competitors(db):
    """
    Quét kênh TikTok đối thủ từ Account.competitor_urls.
    Chỉ chạy mỗi 1 giờ để tránh rate limit TikTok.
    """
    global _last_tiktok_scrape_ts
    from app.services.viral_scan import run_tiktok_competitor_scan

    now = time.time()
    if (now - _last_tiktok_scrape_ts) < TIKTOK_SCRAPE_INTERVAL_SEC:
        return

    _last_tiktok_scrape_ts = now
    logger.info("[TIKTOK] Running hourly TikTok competitor scan...")

    total_found, num_channels = run_tiktok_competitor_scan(db)

    try:
        if total_found > 0:
            NotifierService._broadcast(
                f"🎵 <b>TikTok Auto-Discovery</b>\n"
                f"🔍 Quét {num_channels} kênh đối thủ\n"
                f"✅ Tìm thấy <b>{total_found}</b> video viral mới!"
            )
        else:
            from app.services.viral_scan import get_default_min_views
            min_views = get_default_min_views(db)
            NotifierService._broadcast(
                f"🎵 <b>TikTok Auto-Discovery</b>\n"
                f"🔍 Quét {num_channels} kênh đối thủ\n"
                f"📭 0 video đạt ngưỡng <b>{min_views:,}</b> views.\n"
                f"Đổi ngưỡng: Dashboard → Viral hoặc /viral_settings"
            )
    except Exception:
        pass

# Hourly Zombie Purge
_last_purge_ts: float = 0
PURGE_INTERVAL_SEC = runtime_settings.get_int('worker.maintenance.purge_interval_sec', 3600)  # 1 giờ

def _purge_zombies():
    global _last_purge_ts
    import subprocess
    import time
    now = time.time()
    if (now - _last_purge_ts) < PURGE_INTERVAL_SEC:
        return
        
    _last_purge_ts = now
    logger.info("🔪 Càn quét dọn dẹp Zombie Chrome/Xvfb...")
    try:
        subprocess.run("pkill -9 -f 'chrome.*defunct'", shell=True, check=False)
    except OSError as e:
        logger.warning("Failed to purge zombies: %s", e)

# ── Competitor Discovery (chạy 24h/lần, ban đêm) ──────────────────────
_last_discovery_ts: float = 0
DISCOVERY_INTERVAL_SEC = runtime_settings.get_int('worker.maintenance.discovery_interval_sec', 86400)  # 24 giờ
DISCOVERY_NIGHT_START = 2   # 2 AM
DISCOVERY_NIGHT_END = 5     # 5 AM
DISCOVERY_MAX_KEYWORDS = 3
DISCOVERY_DELAY_BETWEEN_SEC = 600  # 10 phút giữa mỗi keyword

# ── DRAFT Sweeper: chuyển DRAFT (caption done) → PENDING ──────────────
def _sweep_orphaned_drafts(db):
    """Move DRAFT jobs without [AI_GENERATE] marker to PENDING.
    These are jobs where AI already finished caption but status wasn't transitioned."""
    from sqlalchemy import text as _sql_text
    try:
        result = db.execute(_sql_text("""
            UPDATE jobs
            SET status = 'PENDING'
            WHERE status = 'DRAFT'
              AND (caption IS NULL OR caption NOT LIKE '%[AI_GENERATE]%')
              AND tries < max_tries
              AND (last_error IS NULL OR last_error = '')
        """))
        db.commit()
        count = result.rowcount
        if count > 0:
            logger.info("[MAINT] Swept %d orphaned DRAFT jobs -> PENDING", count)
        return count
    except Exception as e:
        db.rollback()
        logger.error("[MAINT] DRAFT sweep failed: %s", e)
        return 0


# ── Zombie Cleanup: DRAFT/PENDING exhausted tries → FAILED ────────────
def _sweep_zombie_jobs(db):
    """Move exhausted-tries DRAFT/PENDING jobs to FAILED."""
    from sqlalchemy import text as _sql_text
    try:
        result = db.execute(_sql_text("""
            UPDATE jobs
            SET status = 'FAILED',
                last_error = COALESCE(NULLIF(last_error, ''), 'Exhausted max tries without success')
            WHERE status IN ('DRAFT', 'PENDING')
              AND tries >= max_tries
              AND max_tries > 0
        """))
        db.commit()
        count = result.rowcount
        if count > 0:
            logger.info("[MAINT] Moved %d zombie jobs (exhausted tries) -> FAILED", count)
        return count
    except Exception as e:
        db.rollback()
        logger.error("[MAINT] Zombie sweep failed: %s", e)
        return 0


# ── Page Insights Scraper (chạy 12h/lần, managed subprocess) ──────────
_last_insights_ts: float = 0
INSIGHTS_INTERVAL_SEC = 43200  # 12 giờ
_insights_process = None  # Track subprocess PID
INSIGHTS_TIMEOUT_SEC = 1800  # 30 phút max

def _scrape_page_insights():
    global _last_insights_ts, _insights_process
    now = time.time()

    # Check if previous process is still running
    if _insights_process is not None:
        poll = _insights_process.poll()
        if poll is None:
            # Still running — check timeout
            start_time = getattr(_insights_process, '_start_time', now)
            if (now - start_time) > INSIGHTS_TIMEOUT_SEC:
                logger.warning("[INSIGHTS] Subprocess timed out after %ds. Killing.", INSIGHTS_TIMEOUT_SEC)
                try:
                    _insights_process.kill()
                except Exception:
                    pass
                _insights_process = None
            else:
                return  # Still running within timeout
        else:
            if poll != 0:
                logger.warning("[INSIGHTS] Subprocess exited with code %d", poll)
            else:
                logger.info("[INSIGHTS] Subprocess completed successfully")
            _insights_process = None

    if (now - _last_insights_ts) < INSIGHTS_INTERVAL_SEC:
        return
    _last_insights_ts = now
    logger.info("Starting Page Insights Scraper (managed subprocess)...")
    try:
        proc = subprocess.Popen([sys.executable, "scripts/archive/scrape_insights.py"])
        proc._start_time = now  # Track start time for timeout
        _insights_process = proc
        logger.info("[INSIGHTS] Started subprocess PID=%d", proc.pid)
    except Exception as e:
        logger.error("Failed to start scrape_insights.py: %s", e)


def _run_competitor_discovery(db):
    """Scan TikTok hashtags to discover new competitor channels.

    Runs once per 24h, during nighttime hours (02:00-05:00).
    Picks 2-3 random keywords per account, delays 10min between searches.
    """
    global _last_discovery_ts
    import random
    import datetime
    from zoneinfo import ZoneInfo

    now = time.time()
    if (now - _last_discovery_ts) < DISCOVERY_INTERVAL_SEC:
        return

    try:
        tz = ZoneInfo(config.TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
    current_hour = datetime.datetime.now(tz).hour
    if not (DISCOVERY_NIGHT_START <= current_hour < DISCOVERY_NIGHT_END):
        return

    _last_discovery_ts = now
    logger.info("[DISCOVERY] Starting nightly competitor discovery scan...")

    from app.database.models import Account
    from app.services.discovery_scraper import DiscoveryScraper
    from app.services.account import get_discovery_keywords

    accounts = db.query(Account).filter(Account.is_active == True).all()

    if not accounts:
        logger.info("[DISCOVERY] No active accounts.")
        return

    scraper = DiscoveryScraper()
    total_found = 0

    for acc in accounts:
        keywords = get_discovery_keywords(acc)
        if not keywords:
            continue

        selected = random.sample(keywords, min(DISCOVERY_MAX_KEYWORDS, len(keywords)))
        logger.info("[DISCOVERY] Account '%s': scanning %d/%d keywords: %s",
                    acc.name, len(selected), len(keywords), selected)

        for kw in selected:
            if not RUNNING:
                return
            try:
                found = scraper.discover_for_keyword(kw, acc.id, db)
                total_found += found
                logger.info("[DISCOVERY] Keyword '%s' for '%s': %d new channels", kw, acc.name, found)
            except Exception as e:
                logger.error("[DISCOVERY] Error scanning keyword '%s': %s", kw, str(e)[:200])

            if DISCOVERY_DELAY_BETWEEN_SEC > 0 and RUNNING:
                logger.info("[DISCOVERY] Sleeping %ds before next keyword...", DISCOVERY_DELAY_BETWEEN_SEC)
                time.sleep(DISCOVERY_DELAY_BETWEEN_SEC)

    if total_found > 0:
        logger.info("[DISCOVERY] Nightly scan complete. %d new channels discovered.", total_found)
        try:
            NotifierService._broadcast(
                f"🔍 <b>Competitor Discovery</b>\n"
                f"🌙 Quét đêm hoàn tất\n"
                f"✅ Phát hiện <b>{total_found}</b> kênh đối thủ mới!\n"
                f"📋 Vào Dashboard → Kênh Đối Thủ Mới Khám Phá để duyệt."
            )
        except Exception:
            pass
    else:
        logger.info("[DISCOVERY] Nightly scan complete. No new channels above threshold.")


def _run_strategic_boost(db):
    """
    Autonomous Boosting: Detect exploding pages and trigger reups.
    Runs every 2 hours.
    """
    global _last_boost_ts
    now = time.time()
    if (now - _last_boost_ts) < config.STRATEGIC_BOOST_INTERVAL_SEC:
        return
    _last_boost_ts = now
    logger.info("🕒 Starting Autonomous Strategic Boosting Scan...")
    try:
        from app.services.strategic import PageStrategicService
        PageStrategicService.run_auto_boost(db)
    except Exception as e:
        logger.error(f"[STRATEGIC] Auto-boost failed: {e}")


def run_loop():
    """Main Maintenance loop."""
    global RUNNING, CURRENT_POLLER
    logger.info("Maintenance Worker started. Press Ctrl+C to stop.")

    register_signals()
    
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
        logger.info("Telegram notifier registered.")
        
        # Start polling thread cho inline button callbacks
        from app.services.telegram_poller import TelegramPoller
        CURRENT_POLLER = TelegramPoller(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        CURRENT_POLLER.start()
        
    logger.info(
        "Entering Maintenance polling loop. Tick=%ss (%.1f minutes)",
        config.MAINT_LOOP_SLEEP_SEC,
        config.MAINT_LOOP_SLEEP_SEC / 60.0,
    )
    
    while RUNNING:
        try:
            with SessionLocal() as db:
                state = WorkerService.get_or_create_state(db)

                try:
                    # Apply runtime overrides from DB (app/settings) so cap values take effect immediately.
                    try:
                        from app.services.settings import apply_runtime_overrides_to_config
                        apply_runtime_overrides_to_config(db)
                    except Exception:
                        db.rollback()

                    if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                        logger.warning(f"Received pending command: {state.pending_command}. Graceful exit requested.")
                        break

                    if state.worker_status == "PAUSED":
                        time.sleep(config.MAINT_LOOP_SLEEP_SEC)
                        continue

                    logger.info("Running routine maintenance tasks...")

                    # 1. Cleanup old media files and temp files
                    CleanupService.run(db)
                    SystemMonitorService().cleanup_temp_files()

                    # 2. Check 24h Metrics for published posts
                    MetricsChecker.check_pending(db)

                    # 2b. Cleanup orphaned virals (hourly)
                    _cleanup_orphaned_virals(db)

                    # 2c. Sweep orphaned DRAFTs → PENDING (every tick)
                    _sweep_orphaned_drafts(db)

                    # 2d. Sweep zombie jobs (exhausted tries) → FAILED
                    _sweep_zombie_jobs(db)

                    # 3. Recover crashed/stale jobs (Self-healing)
                    logger.info("Checking for crashed/stale jobs to recover...")
                    from app.services.queue import QueueService
                    recovered = QueueService.recover_crashed_jobs(db, config.WORKER_CRASH_THRESHOLD_SECONDS)
                    if recovered > 0:
                        logger.warning(f"Self-healing: Recovered {recovered} stale jobs.")

                    # 4. Daily Summary Report
                    _check_daily_summary(db)

                    # 5. Autonomous Strategic Boosting (Auto-Push)
                    _run_strategic_boost(db)

                    # Alerts (queue pressure + resources) with cooldown
                    SystemMonitorService().maybe_alert_queue_and_resources(db)

                    backlog = _pending_backlog(db)
                    if backlog >= MAINT_SKIP_HEAVY_WHEN_PENDING:
                        logger.info(
                            "[MAINT] Backlog=%d >= %d. Skipping heavy tasks (viral ingest/tiktok scan/discovery) this sweep.",
                            backlog,
                            MAINT_SKIP_HEAVY_WHEN_PENDING,
                        )
                    else:
                        # 4. Process viral materials → AWAITING_STYLE jobs (yt-dlp heavy)
                        ViralProcessorService().process_all(db)

                        # 5. Auto-discover TikTok competitor videos (hourly)
                        _scrape_tiktok_competitors(db)

                        # 7. Competitor Discovery (nightly, 24h interval)
                        _run_competitor_discovery(db)

                    # 6. Purge Zombie Chrome processes (hourly) — keep, but cheap
                    _purge_zombies()

                    # 8. Run Page Insights Scraper (12h interval)
                    _scrape_page_insights()

                    logger.info("Hoan tat mot vong maintenance dinh ky.")
                except Exception:
                    db.rollback()
                    raise
                
            if RUNNING:
                # Sleep between maintenance sweeps
                time.sleep(config.MAINT_LOOP_SLEEP_SEC)
                
        except Exception:
            logger.exception("Maintenance Worker encountered a core loop error. Will retry.")
            time.sleep(config.MAINT_LOOP_SLEEP_SEC)
            
    logger.info("Maintenance Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()
