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
    - status='NEW' (từ scraper): đã qua filter views >= 10K, tải + tạo DRAFT.
    - status='REUP' (từ lệnh /reup): manual input, luôn xử lý bất kể views.
    Tải video vào content/reup/<platform>/ để phân loại rõ ràng.
    """
    from app.database.models import ViralMaterial, Job, Account

    materials = db.query(ViralMaterial).filter(
        ViralMaterial.status.in_(["NEW", "REUP"])
    ).order_by(ViralMaterial.views.desc()).limit(3).all()

    if not materials:
        return

    logger.info("[VIRAL] Found %d materials to process.", len(materials))

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
                reason = f"Downloaded media is not a video file ({ext.lower() or 'unknown'}); likely slideshow/audio-only."
                logger.error("[VIRAL] %s path=%s", reason, media_path)
                try:
                    os.remove(media_path)
                except OSError:
                    pass
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

            new_job = Job(
                platform="facebook",
                account_id=target_account.id,
                media_path=media_path,
                caption=caption_metadata,
                status="AWAITING_STYLE",
                schedule_ts=int(time.time()) + random.randint(300, 3600),
                target_page=mat.target_page
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
    import json as _json
    from app.database.models import Account, ViralMaterial
    from app.services.tiktok_scraper import TikTokScraper

    now = time.time()
    if (now - _last_tiktok_scrape_ts) < TIKTOK_SCRAPE_INTERVAL_SEC:
        return  # Chưa đến giờ

    _last_tiktok_scrape_ts = now
    logger.info("[TIKTOK] Running hourly TikTok competitor scan...")

    # Lấy tất cả competitor_urls có chứa tiktok.com
    accounts = db.query(Account).filter(
        Account.is_active == True,
        Account.competitor_urls != None,
    ).all()

    tiktok_channels = []
    for acc in accounts:
        try:
            urls = _json.loads(acc.competitor_urls) if acc.competitor_urls else []
            if not isinstance(urls, list):
                urls = [str(urls)]
        except (_json.JSONDecodeError, TypeError):
            urls = [u.strip() for u in (acc.competitor_urls or "").split(",") if u.strip()]

        for url in urls:
            if "tiktok.com/@" in url.lower():
                tiktok_channels.append((acc.id, url))

    if not tiktok_channels:
        logger.info("[TIKTOK] No TikTok competitor URLs found in any account.")
        return

    logger.info("[TIKTOK] Found %d TikTok channels to scan.", len(tiktok_channels))

    scraper = TikTokScraper()
    total_found = 0

    for account_id, channel_url in tiktok_channels:
        # Hỗ trợ truyền threshold vào URL (ví dụ: https://www.tiktok.com/@channel?min_views=50000)
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(channel_url)
        q_params = parse_qs(parsed.query)
        custom_min_views = int(q_params.get("min_views", [10000])[0])
        clean_url = channel_url.split("?")[0]

        videos = scraper.scrape_channel(clean_url, max_videos=10, min_views=custom_min_views)

        for vid in videos:
            # Check trùng
            existing = db.query(ViralMaterial).filter(
                ViralMaterial.url == vid["url"]
            ).first()
            if existing:
                continue

            mat = ViralMaterial(
                url=vid["url"],
                platform="tiktok",
                title=vid.get("title", "")[:200],
                views=vid.get("view_count", 0),
                scraped_by_account_id=account_id,
                status="NEW",
            )
            db.add(mat)
            total_found += 1

        db.commit()

    if total_found > 0:
        logger.info("[TIKTOK] Added %d new viral TikTok videos to pipeline.", total_found)
        try:
            NotifierService._broadcast(
                f"🎵 *TikTok Auto-Discovery*\n"
                f"🔍 Quét {len(tiktok_channels)} kênh đối thủ\n"
                f"✅ Tìm thấy {total_found} video viral mới!"
            )
        except Exception:
            pass
    else:
        logger.info("[TIKTOK] Scan complete. 0 videos above 10K views threshold.")
        try:
            NotifierService._broadcast(
                f"🎵 *TikTok Auto-Discovery*\n"
                f"🔍 Quét {len(tiktok_channels)} kênh đối thủ\n"
                f"📭 0 video đạt ngưỡng 10K views."
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
                
                # 3. Daily Summary Report
                _check_daily_summary(db)
                
                # 4. Process viral materials → DRAFT jobs
                _process_viral_materials(db)
                
                # 5. Auto-discover TikTok competitor videos (hourly)
                _scrape_tiktok_competitors(db)
                
                # 6. Purge Zombie Chrome processes (hourly)
                _purge_zombies()
                
            if RUNNING:
                # Sleep for 5 minutes between maintenance sweeps
                time.sleep(300)
                
        except Exception:
            logger.exception("Maintenance Worker encountered a core loop error. Will retry.")
            time.sleep(300)
            
    logger.info("Maintenance Worker process completed gracefully.")

if __name__ == "__main__":
    run_loop()
