import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "auto_publisher.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Worker Settings
WORKER_TICK_SECONDS = int(os.getenv("WORKER_TICK_SECONDS", "20"))
WORKER_CRASH_THRESHOLD_SECONDS = int(os.getenv("WORKER_CRASH_THRESHOLD_SECONDS", "300")) # 5 minutes
WORKER_MAX_BATCH_SIZE = int(os.getenv("WORKER_MAX_BATCH_SIZE", "3"))
MAX_FILES_PER_BATCH = int(os.getenv("MAX_FILES_PER_BATCH", "50"))
SAFE_MODE = os.getenv("SAFE_MODE", "false").lower() == "true"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")

# FFmpeg Media Processing
FFMPEG_ENABLED = os.getenv("FFMPEG_ENABLED", "true").lower() == "true"
FFMPEG_PROFILE = os.getenv("FFMPEG_PROFILE", "reels")  # reels | feed | compress_only
FFMPEG_CRF = int(os.getenv("FFMPEG_CRF", "28"))

# FFmpeg Watermark (auto-enabled when file exists)
FFMPEG_WATERMARK_PATH = os.getenv("FFMPEG_WATERMARK_PATH", "/home/vu/toolsauto/content/watermark.png")  # Path to PNG logo
FFMPEG_WATERMARK_POSITION = os.getenv("FFMPEG_WATERMARK_POSITION", "bottom_right")  # top_left|top_right|bottom_left|bottom_right
FFMPEG_WATERMARK_OPACITY = float(os.getenv("FFMPEG_WATERMARK_OPACITY", "0.4"))  # 0.0 - 1.0

# VideoProtector (DRM)
DRM_ENABLED = os.getenv("DRM_ENABLED", "true").lower() == "true"
DRM_WATERMARK_TEXT = os.getenv("DRM_WATERMARK_TEXT", "z")

# Directory Settings
CONTENT_DIR = BASE_DIR / "content"
# Chromium persistent contexts (FacebookAdapter, login bootstrap). NOT cwd-relative.
CONTENT_PROFILES_DIR = Path(
    os.getenv("CONTENT_PROFILES_DIR", str(CONTENT_DIR / "profiles"))
).expanduser().resolve()
DONE_DIR = CONTENT_DIR / "done"
FAILED_DIR = CONTENT_DIR / "failed"
REUP_DIR = CONTENT_DIR / "reup"
THUMB_DIR = Path(os.getenv("THUMB_DIR", str(CONTENT_DIR / "thumbnails")))
PROFILES_DIR = BASE_DIR / "profiles"
LOGS_DIR = BASE_DIR / "logs"

# AI / Whisper Settings
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium")  # tiny|base|small|medium

# Content Length Limits (production-optimized)
MAX_CAPTION_LENGTH = int(os.getenv("MAX_CAPTION_LENGTH", "600"))
MAX_TRANSCRIPT_LENGTH = int(os.getenv("MAX_TRANSCRIPT_LENGTH", "1500"))
MAX_HASHTAGS = int(os.getenv("MAX_HASHTAGS", "6"))
MAX_KEYWORDS = int(os.getenv("MAX_KEYWORDS", "6"))

# Idle Engagement (Account Warming)
IDLE_ENGAGEMENT_ENABLED = os.getenv("IDLE_ENGAGEMENT_ENABLED", "true").lower() == "true"
IDLE_ENGAGEMENT_PROBABILITY = float(os.getenv("IDLE_ENGAGEMENT_PROBABILITY", "0.30"))  # 30% chance when idle
IDLE_MAX_DURATION_SECONDS = int(os.getenv("IDLE_MAX_DURATION_SECONDS", "90"))  # Hard timeout per session

# Telegram Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8709664581:AAHElOvpVf7u7xzC-8sSbg7cUUa6_K7VKTk")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5967314745")

# Redirect Service (Vercel)
VERCEL_REDIRECT_URL = os.getenv("VERCEL_REDIRECT_URL", "https://vercel-redirect-rho-three.vercel.app")

# Viral scan (TikTok competitor)
VIRAL_MIN_VIEWS = int(os.getenv("VIRAL_MIN_VIEWS", "10000"))  # Ngưỡng view tối thiểu
VIRAL_MAX_VIDEOS_PER_CHANNEL = int(os.getenv("VIRAL_MAX_VIDEOS_PER_CHANNEL", "50"))  # Số video tối đa mỗi kênh (0 = lấy hết, nên ≤ 200)

# Rate Limiting & Safety
MAX_CONCURRENT_ACCOUNTS = int(os.getenv("MAX_CONCURRENT_ACCOUNTS", "2"))
POST_DELAY_MIN_SEC = int(os.getenv("POST_DELAY_MIN_SEC", "30"))
POST_DELAY_MAX_SEC = int(os.getenv("POST_DELAY_MAX_SEC", "90"))

# Per-page daily throughput caps (runtime-overridable via app/settings)
# 0 = disable cap (use account.daily_limit / no intake limit)
POSTS_PER_PAGE_PER_DAY = int(os.getenv("POSTS_PER_PAGE_PER_DAY", "0"))
REUP_VIDEOS_PER_PAGE_PER_DAY = int(os.getenv("REUP_VIDEOS_PER_PAGE_PER_DAY", "0"))

# Maintenance: viral processing & alert thresholds
MAINT_VIRAL_LIMIT = int(os.getenv("MAINT_VIRAL_LIMIT", "10"))           # Số video viral xử lý mỗi cycle
ALERT_PENDING_THRESHOLD = int(os.getenv("ALERT_PENDING_THRESHOLD", "30"))
ALERT_DRAFT_THRESHOLD = int(os.getenv("ALERT_DRAFT_THRESHOLD", "50"))
ALERT_VIRAL_NEW_THRESHOLD = int(os.getenv("ALERT_VIRAL_NEW_THRESHOLD", "500"))

# Ensure directories exist
for d in [CONTENT_DIR, DONE_DIR, FAILED_DIR, REUP_DIR, PROFILES_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

