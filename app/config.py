import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (if exists) at the very start
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Database
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "auto_publisher.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Authentication & Security
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    import sys
    print("CRITICAL: ADMIN_USERNAME and ADMIN_PASSWORD must be set in .env for production deployment.", file=sys.stderr)
    sys.exit(1)

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
FFMPEG_WATERMARK_PATH = os.getenv(
    "FFMPEG_WATERMARK_PATH", str(BASE_DIR / "content" / "watermark.png")
)
FFMPEG_WATERMARK_POSITION = os.getenv("FFMPEG_WATERMARK_POSITION", "bottom_right")  # top_left|top_right|bottom_left|bottom_right
FFMPEG_WATERMARK_OPACITY = float(os.getenv("FFMPEG_WATERMARK_OPACITY", "0.4"))  # 0.0 - 1.0

# VideoProtector (DRM)
DRM_ENABLED = os.getenv("DRM_ENABLED", "true").lower() == "true"
DRM_WATERMARK_TEXT = os.getenv("DRM_WATERMARK_TEXT", "z")

# Directory Settings
CONTENT_DIR = BASE_DIR / "content"
DONE_DIR = CONTENT_DIR / "done"
FAILED_DIR = CONTENT_DIR / "failed"
REUP_DIR = BASE_DIR / "reup_videos"
PROFILES_DIR = BASE_DIR / "profiles"
CONTENT_PROFILES_DIR = PROFILES_DIR
LOGS_DIR = BASE_DIR / "logs"
THUMB_DIR = BASE_DIR / "thumbnails"
CONTENT_MEDIA_DIR = CONTENT_DIR / "media"
CONTENT_VIDEO_DIR = CONTENT_DIR / "videos"
CONTENT_PROCESSED_DIR = CONTENT_DIR / "processed"
OUTPUTS_DIR = BASE_DIR / "outputs"

def iter_pm2_log_directories():
    seen = set()
    for p in (
        Path.home() / ".pm2" / "logs",
        Path("/root/.pm2/logs"),
    ):
        s = str(p)
        if s not in seen:
            seen.add(s)
            yield p
    try:
        for entry in os.scandir("/home"):
            if entry.is_dir():
                p = Path(entry.path) / ".pm2" / "logs"
                s = str(p)
                if s not in seen:
                    seen.add(s)
                    yield p
    except Exception:
        pass


# Facebook / Playwright Settings
FACEBOOK_PLAYWRIGHT_HEADLESS = os.getenv('FACEBOOK_PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
PLAYWRIGHT_DEFAULT_TIMEOUT_MS = int(os.getenv('PLAYWRIGHT_DEFAULT_TIMEOUT_MS', '60000'))

# AI / Google AI Studio (Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEY = GEMINI_API_KEY  # alias

# AI / Fallback (Poorman)
FALLBACK_CAPTION_POOL = os.getenv("FALLBACK_CAPTION_POOL", "Góc nhìn thú vị cho mọi người tham khảo nhé! Đừng bỏ lỡ 🔥 | Video này đảm bảo sẽ không làm cả nhà thất vọng đâu! Xem ngay 🎬 | Chút năng lượng cho một ngày làm việc đây, thư giãn nhé 👇 | Cùng tham khảo video tuyệt vời này nha! Nhớ follow kênh nhé 💯")
FALLBACK_HASHTAG_POOL = os.getenv("FALLBACK_HASHTAG_POOL", "#viral, #trending, #xuhuong | #video, #daily, #relax, #giaitri | #thugiangi, #khampha, #haynhat")

# AI / Prompts (BrainFactory)
PERSONA_PROMPT_BEAUTY = os.getenv("PERSONA_PROMPT_BEAUTY", """Bạn là Chuyên gia Tư vấn Chăm sóc Da & Làm đẹp (Beauty Expert). 
Giọng văn: Tận tâm, am hiểu kiến thức chuyên môn nhưng dễ hiểu, tập trung vào sự tự tin và vẻ đẹp tự nhiên.
Ưu tiên: Phân tích thành phần, công dụng và cảm giác khi sử dụng trên da.""")

PERSONA_PROMPT_FASHION = os.getenv("PERSONA_PROMPT_FASHION", """Bạn là Stylist/Fashion Blogger nổi tiếng. 
Giọng văn: Gu thẩm mỹ cao, cập nhật xu hướng, năng động, gợi cảm hứng về phong cách cá nhân.
Ưu tiên: Cách phối đồ, chất liệu, tính ứng dụng và sự tự tin khi diện trang phục.""")

PERSONA_PROMPT_TECH = os.getenv("PERSONA_PROMPT_TECH", """Bạn là Reviewer Công nghệ (Tech Geek). 
Giọng văn: Khách quan, tập trung vào tính năng thực tế, thông số nổi bật và trải nghiệm người dùng.
Ưu tiên: Giải quyết vấn đề (pain-point), sự tiện lợi và tính đột phá của sản phẩm.""")

PERSONA_PROMPT_HOME = os.getenv("PERSONA_PROMPT_HOME", """Bạn là Chuyên gia Chăm sóc Nhà cửa & Đời sống (Home Expert). 
Giọng văn: Ấm áp, ngăn nắp, tập trung vào sự tiện nghi và niềm vui khi chăm sóc tổ ấm.
Ưu tiên: Tính năng tiết kiệm thời gian, sự bền bỉ và vẻ đẹp của không gian sống.""")

PERSONA_PROMPT_FUNNY = os.getenv("PERSONA_PROMPT_FUNNY", """Bạn là Content Creator mảng Giải trí (Gen-Z Creative). 
Giọng văn: Lầy lội, hài hước, dùng nhiều tiếng lóng trending, bắt trend cực nhanh.
Ưu tiên: Sự bất ngờ (punchline), khả năng gây tranh luận hoặc chia sẻ mạnh (viral factor).""")

PERSONA_PROMPT_GENERAL = os.getenv("PERSONA_PROMPT_GENERAL", """Bạn là Chuyên gia Marketing & Copywriter thực chiến with 10 years experience.
Giọng văn: Chuyên nghiệp, thu hút, tối ưu tỷ lệ chuyển đổi.
Ưu tiên: Sự rõ ràng, hook mạnh và thông điệp súc tích.
Yêu cầu bổ sung: Luôn giải thích ngắn gọn lý do tại sao chọn hướng tiếp cận này (reasoning).""")

VISUAL_HOOK_INSTRUCTION = os.getenv("VISUAL_HOOK_INSTRUCTION", """[VISUAL HOOK ANALYSIS]
Hãy soi kỹ 2 khung hình đầu tiên trong ảnh Collage (tương ứng với 3 giây đầu của video). 
1. Visual Hook là gì? (Ví dụ: Một hành động bất ngờ, một gương mặt đẹp, một hiệu ứng lạ).
2. Hãy viết 1 câu HOOK (Tiêu đề) cực mạnh để CỘNG HƯỞNG với visual hook đó. Mục tiêu: Người dùng không thể lướt qua.
3. Giải thích tại sao visual hook này lại hiệu quả (reasoning).""")

ENGAGEMENT_SECRETS = os.getenv("ENGAGEMENT_SECRETS", """[ALGORITHM SECRETS - TĂNG TƯƠNG TÁC]
- Không bao giờ bắt đầu bằng lời chào. Vào thẳng vấn đề (The Hook).
- Sử dụng các kỹ thuật Curiosity Gap (Khoảng trống tò mò). Thách thức người xem bằng một câu hỏi hoặc khẳng định gây sốc.
- Hashtag tối ưu: Sử dụng công thức [Niche] + [Keyword] + [Trending] để lọt vào đúng tệp khách hàng.""")

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

# Telegram Notifications (set via env — no secrets in repo)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Redirect Service (Vercel) — no unsafe default; set VERCEL_REDIRECT_URL in .env when using hosted redirect
VERCEL_REDIRECT_URL = (os.getenv("VERCEL_REDIRECT_URL") or "").strip().rstrip("/")

# TikWM fallback API (viral_processor when yt-dlp fails on TikTok); defaults preserve prior behavior
TIKWM_API_BASE = (os.getenv("TIKWM_API_BASE") or "https://www.tikwm.com/api").strip().rstrip("/")
TIKWM_API_TIMEOUT_SEC = float(os.getenv("TIKWM_API_TIMEOUT_SEC", "15"))
TIKWM_VIDEO_DOWNLOAD_TIMEOUT_SEC = float(os.getenv("TIKWM_VIDEO_DOWNLOAD_TIMEOUT_SEC", "60"))

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

# Runtime timing (defaults match prior hardcoded literals in workers / Playwright / job service)
PUBLISHER_PUBLISH_DEADLINE_SEC = int(os.getenv("PUBLISHER_PUBLISH_DEADLINE_SEC", "900"))
PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC = int(
    os.getenv("PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC", "1200")
)
PLAYWRIGHT_DEFAULT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_DEFAULT_TIMEOUT_MS", "60000"))
MAINT_LOOP_SLEEP_SEC = int(os.getenv("MAINT_LOOP_SLEEP_SEC", "300"))
STRATEGIC_BOOST_INTERVAL_SEC = int(os.getenv("STRATEGIC_BOOST_INTERVAL_SEC", "7200"))
COMMENT_JOB_DELAY_MIN_SEC = int(os.getenv("COMMENT_JOB_DELAY_MIN_SEC", "120"))
COMMENT_JOB_DELAY_MAX_SEC = int(os.getenv("COMMENT_JOB_DELAY_MAX_SEC", "300"))
IDLE_ENGAGEMENT_COOLDOWN_MINUTES = int(os.getenv("IDLE_ENGAGEMENT_COOLDOWN_MINUTES", "45"))

# Ensure directories exist
for d in [
    CONTENT_DIR,
    DONE_DIR,
    FAILED_DIR,
    REUP_DIR,
    PROFILES_DIR,
    LOGS_DIR,
    THUMB_DIR,
    CONTENT_MEDIA_DIR,
    CONTENT_VIDEO_DIR,
    CONTENT_PROCESSED_DIR,
    OUTPUTS_DIR,
    DATA_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)
