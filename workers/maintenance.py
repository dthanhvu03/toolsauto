import json
import os
import time
import logging
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from app.database.core import SessionLocal, ensure_runtime_schema
from app.services.worker import WorkerService
from app.services.cleanup import CleanupService
from app.services.metrics_checker import MetricsChecker
from app.services.notifier import NotifierService, TelegramNotifier
import app.config as config

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [MAINTENANCE] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

RUNNING = True
CURRENT_POLLER = None
DAILY_SUMMARY_HOUR = 23
_last_summary_date = None
ALLOWED_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov"}
YT_DLP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

MAINT_SKIP_HEAVY_WHEN_PENDING = int(os.getenv("MAINT_SKIP_HEAVY_WHEN_PENDING", "10"))

ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))  # 10 phút
ALERT_RAM_PCT_THRESHOLD = float(os.getenv("ALERT_RAM_PCT_THRESHOLD", "85"))
ALERT_CHROME_PROC_THRESHOLD = int(os.getenv("ALERT_CHROME_PROC_THRESHOLD", "20"))


def _get_runtime_int(db, key: str, fallback: int) -> int:
    """Read a runtime setting from DB; fallback to config default."""
    try:
        from app.services import settings as runtime_settings
        return int(runtime_settings.get_effective(db, key))
    except Exception:
        return fallback

_last_alert_ts: dict[str, float] = {}
_last_insights_ts = 0
_last_summary_ts = 0
_last_discovery_ts = 0
_last_boost_ts = 0

STRATEGIC_BOOST_INTERVAL_SEC = 7200 # 2 giờ


def _pending_backlog(db: Session) -> int:
    """Count jobs that indicate backlog; used to decide whether to skip heavy maintenance tasks."""
    from app.database.models import Job
    return db.query(Job).filter(
        Job.status.in_(["PENDING", "RUNNING", "DRAFT", "AI_PROCESSING", "AWAITING_STYLE"])
    ).count()


def _should_alert(key: str) -> bool:
    now = time.time()
    last = _last_alert_ts.get(key, 0)
    if (now - last) >= ALERT_COOLDOWN_SEC:
        _last_alert_ts[key] = now
        return True
    return False


def _maybe_alert_queue_and_resources(db: Session) -> None:
    """Send Telegram alerts for queue congestion and system resource pressure (best-effort, cooldown)."""
    try:
        from app.database.models import Job, ViralMaterial

        pending = db.query(Job).filter(Job.status == "PENDING").count()
        drafts = db.query(Job).filter(Job.status == "DRAFT").count()
        ai = db.query(Job).filter(Job.status == "AI_PROCESSING").count()
        running = db.query(Job).filter(Job.status == "RUNNING").count()
        viral_new = db.query(ViralMaterial).filter(ViralMaterial.status == "NEW").count()

        th_pending = _get_runtime_int(db, "ALERT_PENDING_THRESHOLD", config.ALERT_PENDING_THRESHOLD)
        th_drafts = _get_runtime_int(db, "ALERT_DRAFT_THRESHOLD", config.ALERT_DRAFT_THRESHOLD)
        th_viral = _get_runtime_int(db, "ALERT_VIRAL_NEW_THRESHOLD", config.ALERT_VIRAL_NEW_THRESHOLD)

        if (
            pending >= th_pending
            or drafts >= th_drafts
            or viral_new >= th_viral
        ):
            if _should_alert("queue"):
                NotifierService._broadcast(
                    "🚦 <b>Queue đang cao</b>\n"
                    f"• PENDING: <b>{pending}</b>\n"
                    f"• RUNNING: <b>{running}</b>\n"
                    f"• DRAFT: <b>{drafts}</b>\n"
                    f"• AI_PROCESSING: <b>{ai}</b>\n"
                    f"• Viral NEW: <b>{viral_new}</b>\n"
                    "Gợi ý: /queue để xem tổng quan."
                )
    except Exception:
        pass

    # System pressure alerts (RAM/Chrome count)
    try:
        import psutil

        vm = psutil.virtual_memory()
        ram_pct = float(vm.percent)
        chrome_count = 0
        try:
            chrome_count = sum(
                1
                for p in psutil.process_iter(["name"])
                if "chrome" in (p.info.get("name") or "").lower()
                or "playwright" in (p.info.get("name") or "").lower()
            )
        except Exception:
            chrome_count = 0

        if ram_pct >= ALERT_RAM_PCT_THRESHOLD or chrome_count >= ALERT_CHROME_PROC_THRESHOLD:
            if _should_alert("resources"):
                NotifierService._broadcast(
                    "🧠 <b>Áp lực tài nguyên cao</b>\n"
                    f"• RAM: <b>{ram_pct:.1f}%</b>\n"
                    f"• Chrome/Playwright: <b>{chrome_count}</b>\n"
                    "Gợi ý: giảm backlog, hoặc tắt idle engagement khi bận."
                )
    except Exception:
        pass

def _resolve_yt_dlp_binary() -> str:
    """Prefer PATH, fallback to the project's venv binary."""
    binary = shutil.which("yt-dlp")
    if binary:
        return binary

    bundled = Path(__file__).resolve().parents[1] / "venv" / "bin" / "yt-dlp"
    if bundled.exists():
        return str(bundled)

    return "yt-dlp"


def _entry_has_video_stream(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False

    vcodec = str(entry.get("vcodec") or "").lower()
    if vcodec and vcodec != "none":
        return True

    ext = str(entry.get("ext") or "").lower()
    if ext and f".{ext}" in ALLOWED_VIDEO_EXTS and entry.get("width") and entry.get("height"):
        return True

    return False


def _metadata_has_video_stream(info_data: dict) -> bool:
    """Detect whether yt-dlp metadata contains at least one video stream."""
    if not isinstance(info_data, dict):
        return False

    for key in ("requested_downloads", "requested_formats", "formats"):
        entries = info_data.get(key) or []
        if any(_entry_has_video_stream(entry) for entry in entries):
            return True

    if _entry_has_video_stream(info_data):
        return True

    ext = str(info_data.get("ext") or "").lower()
    if (
        info_data.get("_type") in {"video", "multi_video"}
        and ext
        and f".{ext}" in ALLOWED_VIDEO_EXTS
    ):
        return True

    return False


def _extract_view_count(info_data: dict) -> int:
    if not isinstance(info_data, dict):
        return 0

    candidates = [
        info_data.get("view_count"),
        info_data.get("play_count"),
    ]

    entries = info_data.get("entries") or []
    if entries and isinstance(entries[0], dict):
        candidates.extend([
            entries[0].get("view_count"),
            entries[0].get("play_count"),
        ])

    for value in candidates:
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed

    return 0


def _apply_material_metadata(mat, info_data: dict) -> None:
    """Fill missing material metadata from yt-dlp info."""
    if not isinstance(info_data, dict):
        return

    if mat.views == 0:
        view_count = _extract_view_count(info_data)
        if view_count > 0:
            mat.views = view_count
    if mat.title == "Manual reup via Telegram" and info_data.get("title"):
        mat.title = info_data.get("title")


def _mark_material_failed(db, mat, reason: str) -> None:
    is_manual_reup = (mat.status == "REUP")
    mat.status = "FAILED"
    mat.last_error = (reason or "Unknown error")[:255]
    db.commit()

    # Nhắn Telegram ngay nếu đây là job manual reup do user gửi
    if is_manual_reup:
        from app.services.notifier import NotifierService
        error_vi = reason
        if "no downloadable video stream" in reason.lower() or "slideshow" in reason.lower():
            error_vi = "Link này là dạng Ảnh trượt (Slideshow) hoặc Audio-only, bot chỉ hỗ trợ tải Video Mp4 tiêu chuẩn."
        elif "private" in reason.lower():
            error_vi = "Video này bị riêng tư (Private) hoặc cần follow mới xem được."

        try:
            import html
            error_escaped = html.escape(error_vi)
            NotifierService._broadcast(
                f"❌ <b>Reup Thất Bại!</b>\n"
                f"🔗 Link: {mat.url}\n"
                f"Lý do: {error_escaped}"
            )
        except Exception as e:
            logger.error("Failed to notify user about reup error: %s", e)


def _clear_material_error(mat) -> None:
    mat.last_error = None


def _get_download_source_account(db, mat):
    """Pick an active account whose browser profile can provide source cookies."""
    from app.database.models import Account

    if mat.platform not in {"instagram", "facebook"}:
        return None

    preferred = None
    if mat.scraped_by_account_id:
        preferred = db.query(Account).filter(
            Account.id == mat.scraped_by_account_id,
            Account.is_active == True,
            Account.login_status == "ACTIVE",
            Account.platform == mat.platform,
        ).first()
    if preferred:
        return preferred

    return db.query(Account).filter(
        Account.is_active == True,
        Account.login_status == "ACTIVE",
        Account.platform == mat.platform,
    ).first()


def _extend_yt_dlp_with_cookies(cmd: list[str], account) -> list[str]:
    if not account or not getattr(account, "profile_path", None):
        return cmd
    return [
        *cmd,
        "--cookies-from-browser",
        f"chromium:{account.profile_path}",
    ]


def _humanize_yt_dlp_error(platform: str, stderr: str, source_account) -> str:
    stderr = (stderr or "Unknown error").strip()
    lowered = stderr.lower()

    if platform == "instagram":
        if "unavailable for certain audiences" in lowered or "login" in lowered:
            if source_account:
                return (
                    "Instagram blocked access to this reel even with the current session. "
                    "Re-login the Instagram account or verify the reel is viewable in browser."
                )
            return (
                "Instagram reel requires a logged-in Instagram session or is age/audience restricted. "
                "Create an ACTIVE instagram account and login first."
            )
        if "private" in lowered:
            return "Instagram reel is private; only a logged-in authorized account can access it."

    return f"yt-dlp failed: {stderr[:180]}"

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
            ViralMaterial.status.in_(["NEW", "REUP"]),
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

        # 2. Smart Cleanup: Tự động đào thải video ế (NEW > 48h)
        import os
        stale_threshold = int(time.time()) - (48 * 3600)
        stale_virals = db.query(ViralMaterial).filter(
            ViralMaterial.status == "NEW",
            ViralMaterial.created_at < stale_threshold
        ).all()
        
        stale_count = 0
        for v in stale_virals:
            if v.media_path and os.path.exists(v.media_path):
                try:
                    os.remove(v.media_path)
                except Exception:
                    pass
            db.delete(v)
            stale_count += 1
            
        if stale_count > 0:
            logger.info("🗑️ Smart Cleanup: Đã xóa %d video ế (nằm kho quá 48h) để dọn dung lượng.", stale_count)

        if orphans_fixed > 0 or stale_count > 0:
            db.commit()

    except Exception as e:
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
            logger.error("Daily summary failed: %s", e)

def _process_viral_materials(db):
    """
    Downstream consumer cho bảng viral_materials.
    - status='NEW' (từ scraper): đã qua filter views >= ngưỡng (cài đặt Viral), tải + tạo DRAFT.
    - status='REUP' (từ lệnh /reup): manual input, luôn xử lý bất kể views.
    Tải video vào content/reup/<platform>/ để phân loại rõ ràng.
    """
    from app.database.models import ViralMaterial, Job, Account

    # Use a fair per-account distribution rather than a global limit
    # This prevents an account with 1M+ view videos from starving other accounts
    active_accounts = db.query(Account.id).filter(Account.is_active == True).all()
    active_acc_ids = [acc.id for acc in active_accounts]
    
    limit_per_acc = max(1, _get_runtime_int(db, "MAINT_VIRAL_LIMIT", config.MAINT_VIRAL_LIMIT)) // max(1, len(active_acc_ids))
    if limit_per_acc < 2:
        limit_per_acc = 2

    materials = []
    # First, always grab REUP materials (manual/boosted) since they are high priority
    reups = db.query(ViralMaterial).filter(ViralMaterial.status == "REUP").all()
    materials.extend(reups)
    
    # Then, fairly grab NEW materials per account and per target_page to prevent starvation
    for acc_id in active_acc_ids:
        acc = db.query(Account).filter(Account.id == acc_id).first()
        if not acc:
            continue
            
        # Determine all target pages this account is responsible for
        pages = set()
        if acc.target_pages_list:
            pages.update(acc.target_pages_list)
        if acc.target_page:
            pages.add(acc.target_page)
            
        if not pages:
            # Fallback for accounts without explicit target pages
            acc_materials = db.query(ViralMaterial).filter(
                ViralMaterial.status == "NEW",
                ViralMaterial.scraped_by_account_id == acc_id
            ).order_by(ViralMaterial.views.desc()).limit(limit_per_acc).all()
            materials.extend(acc_materials)
        else:
            limit_per_page = max(1, limit_per_acc // len(pages))
            for page_url in pages:
                # Fetch top materials specifically for this page
                page_materials = db.query(ViralMaterial).filter(
                    ViralMaterial.status == "NEW",
                    ViralMaterial.scraped_by_account_id == acc_id,
                    ViralMaterial.target_page == page_url
                ).order_by(ViralMaterial.views.desc()).limit(limit_per_page).all()
                materials.extend(page_materials)
                
            # Allow fallback for videos scraped without a specific target_page
            general_materials = db.query(ViralMaterial).filter(
                ViralMaterial.status == "NEW",
                ViralMaterial.scraped_by_account_id == acc_id,
                ViralMaterial.target_page.is_(None)
            ).order_by(ViralMaterial.views.desc()).limit(limit_per_acc).all()
            materials.extend(general_materials)

    # Sort the final combined list by views so the highest views across the picked batch get processed first
    materials.sort(key=lambda m: (m.status != "REUP", -m.views))

    if not materials:
        return

    logger.info("[VIRAL] Found %d materials to process (fair distribution).", len(materials))

    # Lấy account mặc định (fallback nếu material không chỉ định acc)
    default_account = db.query(Account).filter(
        Account.is_active == True,
        Account.login_status == "ACTIVE",
        Account.platform == "facebook",
    ).first()

    if not default_account:
        logger.warning("[VIRAL] No active Facebook account found. Skipping viral ingestion.")
        return

    reup_base = str(config.REUP_DIR)
    yt_dlp_bin = _resolve_yt_dlp_binary()

    for mat in materials:
        try:
            # Tạo thư mục theo platform: reup/tiktok/, reup/facebook/, reup/youtube/...
            platform_dir = os.path.join(reup_base, mat.platform or "unknown")
            os.makedirs(platform_dir, exist_ok=True)
            source_account = _get_download_source_account(db, mat)

            # If this sweep is processing REUP materials, optionally cap intake per target_page/day.
            # This prevents lag spikes by limiting how many REUP-derived jobs can enter the pipeline.
            if (
                mat.status == "REUP"
                and int(getattr(config, "REUP_VIDEOS_PER_PAGE_PER_DAY", 0) or 0) > 0
            ):
                from datetime import datetime, time as time_obj
                from zoneinfo import ZoneInfo
                from app.database.models import Job, Account

                # Resolve target account/page *without* downloading media
                target_account = default_account
                if mat.scraped_by_account_id:
                    specified_acc = db.query(Account).filter(
                        Account.id == mat.scraped_by_account_id,
                        Account.is_active == True,
                    ).first()
                    if specified_acc:
                        target_account = specified_acc

                resolved_target = mat.target_page
                if not resolved_target and target_account.target_pages_list:
                    resolved_target = target_account.pick_next_target_page(db)

                if resolved_target:
                    today_start = int(
                        datetime.combine(
                            datetime.now(ZoneInfo(config.TIMEZONE)).date(),
                            time_obj.min,
                        ).timestamp()
                    )

                    cap = int(config.REUP_VIDEOS_PER_PAGE_PER_DAY)
                    active_statuses = ["AWAITING_STYLE", "AI_PROCESSING", "DRAFT", "PENDING", "RUNNING"]

                    active_today = db.query(Job).filter(
                        Job.target_page == resolved_target,
                        Job.status.in_(active_statuses),
                        Job.created_at >= today_start,
                    ).count()

                    posted_today = db.query(Job).filter(
                        Job.target_page == resolved_target,
                        Job.status == "DONE",
                        Job.finished_at >= today_start,
                    ).count()

                    if (active_today + posted_today) >= cap:
                        logger.info(
                            "[REUP CAP] Skip material #%s (%s) for page '%s': active+posted today=%s >= cap=%s",
                            mat.id,
                            mat.url,
                            resolved_target,
                            active_today + posted_today,
                            cap,
                        )
                        continue

            preflight_cmd = _extend_yt_dlp_with_cookies([
                yt_dlp_bin,
                "--no-playlist",
                "--skip-download",
                "--dump-single-json",
                "--no-warnings",
                "--add-header", f"User-Agent: {YT_DLP_USER_AGENT}",
                mat.url,
            ], source_account)
            logger.info("[VIRAL] Preflight metadata [%s]: %s", mat.platform, mat.url)
            preflight = subprocess.run(preflight_cmd, capture_output=True, text=True, timeout=60)

            download_success = False
            media_path = None
            fallback_used_successfully = False

            if preflight.returncode != 0:
                # Nếu preflight yt-dlp thất bại hoàn toàn (vd: HTTP Error 403 của TikTok)
                if mat.platform == "tiktok":
                    logger.warning("[VIRAL] yt-dlp preflight failed for TikTok. Attempting TikWM fallback...")
                    fallback_filename = f"viral_{mat.id}_tikwm.mp4"
                    fallback_path = os.path.join(platform_dir, fallback_filename)
                    if _download_tiktok_fallback(mat.url, fallback_path):
                        download_success = True
                        fallback_used_successfully = True
                        media_path = fallback_path
                        logger.info("[VIRAL] Downloaded (tikwm fallback after preflight fail): %s", media_path)
                        
                if not fallback_used_successfully:
                    reason = _humanize_yt_dlp_error(mat.platform or "", preflight.stderr or "", source_account)
                    logger.error("[VIRAL] %s", reason)
                    _mark_material_failed(db, mat, reason)
                    continue
            else:
                try:
                    preflight_info = json.loads(preflight.stdout)
                except json.JSONDecodeError as exc:
                    reason = f"Invalid yt-dlp metadata: {exc}"
                    logger.error("[VIRAL] %s", reason)
                    _mark_material_failed(db, mat, reason)
                    continue

                _apply_material_metadata(mat, preflight_info)
                if mat.platform == "instagram" and mat.views == 0:
                    logger.warning(
                        "[VIRAL] Instagram metadata has no usable view_count/play_count for %s",
                        mat.url,
                    )
                
                if not _metadata_has_video_stream(preflight_info):
                    # preflight thành công nhưng báo là slideshow/audio-only
                    if mat.platform == "tiktok":
                        logger.warning("[VIRAL] yt-dlp missed video stream for TikTok. Attempting TikWM fallback...")
                        fallback_filename = f"viral_{mat.id}_tikwm.mp4"
                        fallback_path = os.path.join(platform_dir, fallback_filename)
                        if _download_tiktok_fallback(mat.url, fallback_path):
                            download_success = True
                            fallback_used_successfully = True
                            media_path = fallback_path
                            logger.info("[VIRAL] Downloaded (tikwm fallback after missing stream): %s", media_path)
                    
                    if not fallback_used_successfully:
                        reason = "Source has no downloadable video stream; likely TikTok slideshow or audio-only."
                        logger.error("[VIRAL] %s url=%s", reason, mat.url)
                        _mark_material_failed(db, mat, reason)
                        continue

            if not download_success and not fallback_used_successfully:
                # Tải video bằng yt-dlp vào thư mục platform riêng
                output_template = os.path.join(platform_dir, f"viral_{mat.id}_%(id)s.%(ext)s")
                cmd = _extend_yt_dlp_with_cookies([
                    yt_dlp_bin,
                    "--no-playlist",
                    "--max-filesize", "100M",
                    "--write-info-json",
                    "--add-header", f"User-Agent: {YT_DLP_USER_AGENT}",
                    "-o", output_template,
                    mat.url,
                ], source_account)
                logger.info("[VIRAL] Downloading [%s]: %s", mat.platform, mat.url)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

                if result.returncode != 0:
                    reason = _humanize_yt_dlp_error(mat.platform or "", result.stderr or "", source_account)
                    logger.error("[VIRAL] %s", reason)
                    _mark_material_failed(db, mat, reason)
                    continue
                    
                # --- Extract Metadata from .info.json ---
                import glob
                info_files = glob.glob(os.path.join(platform_dir, f"viral_{mat.id}_*.info.json"))
                if info_files:
                    try:
                        with open(info_files[0], 'r', encoding='utf-8') as f:
                            info_data = json.load(f)
                        _apply_material_metadata(mat, info_data)
                            
                        # Clean up json file
                        os.remove(info_files[0])
                        db.commit()
                    except Exception as e:
                        logger.warning("[VIRAL] Could not read info json for %s: %s", mat.url, e)

                # Tìm file vừa tải
                downloaded_files = [
                    f for f in os.listdir(platform_dir)
                    if f.startswith(f"viral_{mat.id}_") and not f.endswith(".info.json")
                ]
                if not downloaded_files:
                    reason = "yt-dlp reported success but no media file was found."
                    logger.error("[VIRAL] %s url=%s", reason, mat.url)
                    _mark_material_failed(db, mat, reason)
                    continue

                media_path = os.path.join(platform_dir, downloaded_files[0])
                logger.info("[VIRAL] Downloaded: %s", media_path)

            # --- Check if downloaded file is actually a video ---
            _, ext = os.path.splitext(media_path)
            if ext.lower() not in ALLOWED_VIDEO_EXTS:
                logger.warning("[VIRAL] Downloaded media is not a video file (%s). Path: %s", ext.lower(), media_path)
                try:
                    os.remove(media_path)
                except OSError:
                    pass
                
                # Try TikWM fallback for TikTok if it hasn't been used yet
                if mat.platform == "tiktok" and not fallback_used_successfully:
                    logger.warning("[VIRAL] Attempting TikWM fallback because yt-dlp downloaded a non-video file...")
                    fallback_filename = f"viral_{mat.id}_tikwm.mp4"
                    fallback_path = os.path.join(platform_dir, fallback_filename)
                    if _download_tiktok_fallback(mat.url, fallback_path):
                        fallback_used_successfully = True
                        media_path = fallback_path
                        logger.info("[VIRAL] Downloaded (tikwm fallback after non-video dl): %s", media_path)

                if not fallback_used_successfully:
                    reason = f"Downloaded media is not a video file ({ext.lower() or 'unknown'}); likely slideshow/audio-only."
                    logger.error("[VIRAL] %s path=%s", reason, media_path)
                    _mark_material_failed(db, mat, reason)
                    continue

            # === Post-processing: watermark removal + anti-duplicate ===
            from app.services.reup_processor import ReupProcessor
            reup_result = ReupProcessor.process(
                input_path=media_path,
                platform=mat.platform or "unknown",
            )
            if reup_result.success and reup_result.output_path:
                logger.info("[VIRAL] Post-processed: %s", reup_result.output_path)
                # Xóa file gốc, dùng file đã xử lý
                try:
                    os.remove(media_path)
                except OSError:
                    pass
                media_path = reup_result.output_path
            else:
                logger.warning("[VIRAL] Post-processing failed (%s), dùng file gốc.", reup_result.error)

            # Chọn account: ưu tiên acc do user chỉ định, fallback acc mặc định
            target_account = default_account
            if mat.scraped_by_account_id:
                specified_acc = db.query(Account).filter(
                    Account.id == mat.scraped_by_account_id,
                    Account.is_active == True,
                ).first()
                if specified_acc:
                    target_account = specified_acc

            # Tạo Job DRAFT với AI_GENERATE và cắm cờ ORIGINAL_VIRAL_TITLE để truyền context
            import random
            
            # Xử lý dấu ngoặc kép hoặc ký tự đặc biệt trong title để an toàn
            safe_title = (mat.title or "").replace('"', "'").strip()
            caption_metadata = f"[AI_GENERATE] ### ORIGINAL_VIRAL_TITLE: {safe_title} ###" if safe_title else f"[AI_GENERATE] Context: Video {mat.platform} {mat.views} views."

            # Inject BOOST_CONTEXT nếu material có target_page (từ Smart Boost hoặc manual reup)
            resolved_target = mat.target_page
            if resolved_target and target_account:
                try:
                    from app.services.strategic import PageStrategicService
                    page_niches = PageStrategicService._lookup_page_niches(db, target_account.id, resolved_target)
                    top_posts_summary = PageStrategicService._get_top_posts_summary(db, resolved_target)
                    if page_niches or top_posts_summary:
                        niches_str = ",".join(page_niches) if page_niches else "general"
                        boost_ctx = f"niche={niches_str}"
                        if top_posts_summary:
                            boost_ctx += f", top_posts=[{top_posts_summary}]"
                        caption_metadata += f" ### BOOST_CONTEXT: {boost_ctx} ###"
                except Exception as bc_err:
                    logger.warning("[VIRAL] Could not build BOOST_CONTEXT: %s", bc_err)

            # Resolve target page: always prioritize mat.target_page to prevent mixing niches
            if mat.target_page:
                resolved_target = mat.target_page
            elif target_account.target_pages_list and len(target_account.target_pages_list) > 1:
                # Check if all pages have the identical niches. If not, do NOT round-robin generic videos!
                pages = target_account.target_pages_list
                niche_map = target_account.page_niches_map or {}
                
                can_round_robin = True
                if niche_map and pages:
                    first_niche = set(niche_map.get(pages[0], []))
                    for p in pages[1:]:
                        if set(niche_map.get(p, [])) != first_niche:
                            can_round_robin = False
                            break
                            
                if can_round_robin:
                    # Safe to distribute jobs evenly
                    resolved_target = target_account.pick_next_target_page(db)
                    logger.info("[VIRAL] Safe round-robin → page '%s' for acc '%s'", resolved_target, target_account.name)
                else:
                    # UNSAFE! Niches differ. Use Keyword Matching.
                    title_lower = (mat.title or "").lower()
                    best_page = pages[0]
                    best_score = -1
                    
                    if title_lower and niche_map:
                        for p in pages:
                            niches = niche_map.get(p, [])
                            score = 0
                            for n in niches:
                                n_lower = n.lower()
                                if n_lower in title_lower:
                                    score += 3
                                words = n_lower.split()
                                for w in words:
                                    if len(w) > 3 and w in title_lower:
                                        score += 1
                            if score > best_score:
                                best_score = score
                                best_page = p
                    
                    if best_score > 0:
                        resolved_target = best_page
                        logger.info("[VIRAL] Keyword Match (score %d) → page '%s' for acc '%s'", best_score, resolved_target, target_account.name)
                    else:
                        resolved_target = pages[0]
                        logger.info("[VIRAL] No keyword match. Locked generic video to primary page '%s' for acc '%s'", resolved_target, target_account.name)
            elif target_account.target_pages_list:
                resolved_target = target_account.target_pages_list[0]
            else:
                resolved_target = target_account.target_page

            # Accelerated Freshness Pipeline (2026 Algo Upgrade)
            # Nếu là Auto-Boost (có BOOST_CONTEXT) -> Đăng gần như ngay lập tức để bắt sóng
            # Chú ý: Cần cộng thêm jitter (1-5 phút) để tránh bị Meta đánh cờ 'Spam/Bot' vì đăng quá chính xác.
            if "BOOST_CONTEXT" in caption_metadata:
                jitter = random.randint(60, 300)
                calc_schedule = int(time.time()) + jitter
                logger.info(f"[VIRAL] Using Accelerated Freshness scheduling for BOOST job (+{jitter}s)")
            else:
                calc_schedule = int(time.time()) + random.randint(300, 3600)

            new_job = Job(
                platform="facebook",
                account_id=target_account.id,
                media_path=media_path,
                caption=caption_metadata,
                status="AWAITING_STYLE",
                schedule_ts=calc_schedule,
                target_page=resolved_target
            )
            db.add(new_job)
            mat.status = "DRAFTED"
            _clear_material_error(mat)
            db.commit()

            logger.info("[VIRAL] Created AWAITING_STYLE Job #%s from %s material #%s → acc '%s'",
                        new_job.id, mat.platform, mat.id, target_account.name)
            
            from app.services.notifier import NotifierService
            NotifierService.notify_style_selection(new_job)

        except subprocess.TimeoutExpired:
            reason = "yt-dlp timed out while fetching media."
            logger.error("[VIRAL] %s url=%s", reason, mat.url)
            _mark_material_failed(db, mat, reason)
        except Exception as e:
            reason = f"Processing error: {str(e).strip()[:200]}"
            logger.error("[VIRAL] Error processing material #%s: %s", mat.id, e)
            _mark_material_failed(db, mat, reason)


# Hourly tracker cho TikTok scraping (chạy mỗi 1 giờ, không mỗi 5 phút)
_last_tiktok_scrape_ts: float = 0
TIKTOK_SCRAPE_INTERVAL_SEC = 3600  # 1 giờ


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

def _download_tiktok_fallback(url: str, output_path: str) -> bool:
    """Fallback handler for TikTok using TikWM API when yt-dlp fails due to cookies/JS challenge."""
    import requests
    try:
        api_url = f"https://www.tikwm.com/api/?url={url}"
        resp = requests.get(api_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 and "data" in data:
                video_data = data["data"]
                
                # Check if it's actually an image slideshow
                if "images" in video_data and isinstance(video_data["images"], list) and len(video_data["images"]) > 0:
                    logger.warning("[VIRAL] TikWM confirmed this is an image slideshow, not a video.")
                    return False
                    
                play_url = video_data.get("play") or video_data.get("wmplay")
                if play_url:
                    logger.info("[VIRAL] TikWM returned a valid video URL, downloading...")
                    video_resp = requests.get(play_url, stream=True, timeout=60)
                    if video_resp.status_code == 200:
                        with open(output_path, 'wb') as f:
                            for chunk in video_resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                        return True
        logger.warning("[VIRAL] TikWM API did not return a valid video URL for %s", url)
    except Exception as e:
        logger.error("[VIRAL] TikWM fallback failed: %s", e)
    return False

# Hourly Zombie Purge
_last_purge_ts: float = 0
PURGE_INTERVAL_SEC = 3600  # 1 giờ

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
DISCOVERY_INTERVAL_SEC = 86400  # 24 giờ
DISCOVERY_NIGHT_START = 2   # 2 AM
DISCOVERY_NIGHT_END = 5     # 5 AM
DISCOVERY_MAX_KEYWORDS = 3
DISCOVERY_DELAY_BETWEEN_SEC = 600  # 10 phút giữa mỗi keyword

# ── Page Insights Scraper (chạy 12h/lần) ──────────────────────────────
_last_insights_ts: float = 0
INSIGHTS_INTERVAL_SEC = 43200  # 12 giờ

def _scrape_page_insights():
    global _last_insights_ts
    now = time.time()
    if (now - _last_insights_ts) < INSIGHTS_INTERVAL_SEC:
        return
    _last_insights_ts = now
    logger.info("🕒 Starting Page Insights Scraper...")
    try:
        subprocess.Popen([sys.executable, "scripts/scrape_insights.py"])
    except Exception as e:
        logger.error(f"Failed to start scrape_insights.py: {e}")


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
    if (now - _last_boost_ts) < STRATEGIC_BOOST_INTERVAL_SEC:
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
    ensure_runtime_schema()
    
    register_signals()
    
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
        logger.info("Telegram notifier registered.")
        
        # Start polling thread cho inline button callbacks
        from app.services.telegram_poller import TelegramPoller
        CURRENT_POLLER = TelegramPoller(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        CURRENT_POLLER.start()
        
    logger.info("Entering Maintenance polling loop. Tick=300s (5 minutes)")
    
    while RUNNING:
        try:
            with SessionLocal() as db:
                state = WorkerService.get_or_create_state(db)

                # Apply runtime overrides from DB (app/settings) so cap values take effect immediately.
                try:
                    from app.services.settings import apply_runtime_overrides_to_config
                    apply_runtime_overrides_to_config(db)
                except Exception:
                    pass
                
                if state.pending_command in ("REQUEST_EXIT", "RESTART_REQUESTED"):
                    logger.warning(f"Received pending command: {state.pending_command}. Graceful exit requested.")
                    break
                    
                if state.worker_status == "PAUSED":
                    time.sleep(300)
                    continue
                
                logger.info("Running routine maintenance tasks...")
                
                # 1. Cleanup old media files and temp files
                CleanupService.run(db)
                
                # 2. Check 24h Metrics for published posts
                MetricsChecker.check_pending(db)
                
                # 2b. Cleanup orphaned virals (hourly)
                _cleanup_orphaned_virals(db)
                
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
                _maybe_alert_queue_and_resources(db)

                backlog = _pending_backlog(db)
                if backlog >= MAINT_SKIP_HEAVY_WHEN_PENDING:
                    logger.info(
                        "[MAINT] Backlog=%d >= %d. Skipping heavy tasks (viral ingest/tiktok scan/discovery) this sweep.",
                        backlog,
                        MAINT_SKIP_HEAVY_WHEN_PENDING,
                    )
                else:
                    # 4. Process viral materials → DRAFT jobs (yt-dlp heavy)
                    _process_viral_materials(db)
                    
                    # 5. Auto-discover TikTok competitor videos (hourly)
                    _scrape_tiktok_competitors(db)
                    
                    # 7. Competitor Discovery (nightly, 24h interval)
                    _run_competitor_discovery(db)

                # 6. Purge Zombie Chrome processes (hourly) — keep, but cheap
                _purge_zombies()
                
                # 8. Run Page Insights Scraper (12h interval)
                _scrape_page_insights()
                
            if RUNNING:
                # Sleep for 5 minutes between maintenance sweeps
                time.sleep(300)
                
        except Exception:
            logger.exception("Maintenance Worker encountered a core loop error. Will retry.")
            time.sleep(300)
            
    logger.info("Maintenance Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()
