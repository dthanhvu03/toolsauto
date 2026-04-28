import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

import app.config as config
from app.database.models import RuntimeSetting, RuntimeSettingAudit


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: str  # int|float|bool|str|enum
    default_getter: Callable[[], Any]
    title: str
    section: str
    description: str = ""
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None
    enum_labels: dict[str, str] | None = None
    unit: str | None = None
    # UX / policy (optional)
    is_secret: bool = False
    restart_required: bool = False
    env_only: bool = False  # value from process env only; not persisted to runtime_settings
    pair_with: str | None = None  # render this row as a paired min/max with the other key
    env_var_name: str | None = None  # os.environ key for source badge (default: key.upper() + overrides)


def _getattr_default(name: str) -> Callable[[], Any]:
    return lambda: getattr(config, name)


SETTINGS: dict[str, SettingSpec] = {
    "worker.tick_seconds": SettingSpec(
        key="worker.tick_seconds",
        env_var_name="WORKER_TICK_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_TICK_SECONDS"),
        title="Tần suất quét Job (Worker)",
        section="Hệ thống Worker",
        description="Khoảng cách giữa mỗi lần worker kiểm tra hàng đợi job (giây). Giá trị nhỏ = phản hồi nhanh hơn nhưng tốn CPU hơn.",
        min=1,
        max=300,
        unit="giây",
    ),
    "worker.crash_threshold_seconds": SettingSpec(
        key="worker.crash_threshold_seconds",
        env_var_name="WORKER_CRASH_THRESHOLD_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_CRASH_THRESHOLD_SECONDS"),
        title="Ngưỡng coi Worker 'chết'",
        section="Hệ thống Worker",
        description="Nếu không nhận heartbeat trong khoảng thời gian này, hệ thống có thể coi worker gặp sự cố (phục vụ cảnh báo / health).",
        min=30,
        max=3600,
        unit="giây",
    ),
    "worker.max_batch_size": SettingSpec(
        key="worker.max_batch_size",
        env_var_name="WORKER_MAX_BATCH_SIZE",
        type="int",
        default_getter=_getattr_default("WORKER_MAX_BATCH_SIZE"),
        title="Số job xử lý tối đa mỗi vòng",
        section="Hệ thống Worker",
        description="Giới hạn số job lấy ra xử lý trong một chu kỳ quét, tránh quá tải khi hàng đợi lớn.",
        min=1,
        max=50,
        unit="job",
    ),
    "worker.max_files_per_batch": SettingSpec(
        key="worker.max_files_per_batch",
        env_var_name="MAX_FILES_PER_BATCH",
        type="int",
        default_getter=_getattr_default("MAX_FILES_PER_BATCH"),
        title="Số file tối đa mỗi đợt upload",
        section="Hệ thống Worker",
        description="Giới hạn số file media xử lý trong một batch (upload hàng loạt), giúp ổn định RAM và ổ đĩa.",
        min=1,
        max=500,
        unit="file",
    ),
    "system.timezone": SettingSpec(
        key="system.timezone",
        env_var_name="TIMEZONE",
        type="str",
        default_getter=_getattr_default("TIMEZONE"),
        title="Múi giờ hệ thống",
        section="Hệ thống Worker",
        description="Múi giờ dùng cho lịch đăng, báo cáo ngày và khung giờ ngủ đông tài khoản (vd: Asia/Ho_Chi_Minh).",
    ),
    "viral.min_views": SettingSpec(
        key="viral.min_views",
        env_var_name="VIRAL_MIN_VIEWS",
        type="int",
        default_getter=_getattr_default("VIRAL_MIN_VIEWS"),
        title="Lượt xem tối thiểu (quét TikTok)",
        section="Quét TikTok & Viral",
        description="Video TikTok từ kênh đối thủ phải đạt ít nhất số view này mới được thêm vào kho viral (có thể ghi đè bởi system_state).",
        min=0,
        max=10_000_000,
        unit="view",
    ),
    "viral.max_videos_per_channel": SettingSpec(
        key="viral.max_videos_per_channel",
        env_var_name="VIRAL_MAX_VIDEOS_PER_CHANNEL",
        type="int",
        default_getter=_getattr_default("VIRAL_MAX_VIDEOS_PER_CHANNEL"),
        title="Tối đa video mỗi kênh mỗi lần quét",
        section="Quét TikTok & Viral",
        description="Giới hạn số video lấy từ mỗi kênh TikTok trong một lần quét (0 = dùng logic mặc định trong code, thường cap 500).",
        min=0,
        max=500,
        unit="video",
    ),
    "publish.delay_min_sec": SettingSpec(
        key="publish.delay_min_sec",
        env_var_name="POST_DELAY_MIN_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MIN_SEC"),
        title="Delay đăng bài — tối thiểu",
        section="Giới hạn đăng bài",
        description="Khoảng chờ ngẫu nhiên giữa các lần đăng: giới hạn dưới (giây). Giúp giảm hành vi giống bot.",
        min=0,
        max=3600,
        unit="giây",
    ),
    "publish.delay_max_sec": SettingSpec(
        key="publish.delay_max_sec",
        env_var_name="POST_DELAY_MAX_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MAX_SEC"),
        title="Delay đăng bài — tối đa",
        section="Giới hạn đăng bài",
        description="Khoảng chờ ngẫu nhiên giữa các lần đăng: giới hạn trên (giây).",
        min=0,
        max=3600,
        unit="giây",
    ),
    "publish.posts_per_page_per_day": SettingSpec(
        key="publish.posts_per_page_per_day",
        env_var_name="POSTS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("POSTS_PER_PAGE_PER_DAY"),
        title="Giới hạn bài đăng / Page / ngày",
        section="Giới hạn đăng bài",
        description="Số bài tối đa mỗi Fan Page trong một ngày (0 = tắt giới hạn theo cấu hình này).",
        min=0,
        max=200,
        unit="bài",
    ),
    "publish.reup_videos_per_page_per_day": SettingSpec(
        key="publish.reup_videos_per_page_per_day",
        env_var_name="REUP_VIDEOS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("REUP_VIDEOS_PER_PAGE_PER_DAY"),
        title="Giới hạn Reup / Page / ngày",
        section="Giới hạn đăng bài",
        description="Số video reup tối đa mỗi Page mỗi ngày (0 = không áp giới hạn qua setting này).",
        min=0,
        max=200,
        unit="video",
    ),
    "publish.max_concurrent_accounts": SettingSpec(
        key="publish.max_concurrent_accounts",
        env_var_name="MAX_CONCURRENT_ACCOUNTS",
        type="int",
        default_getter=_getattr_default("MAX_CONCURRENT_ACCOUNTS"),
        title="Số tài khoản chạy song song",
        section="Giới hạn đăng bài",
        description="Số browser/account có thể hoạt động đồng thời khi đăng (nên giữ thấp để an toàn IP).",
        min=1,
        max=10,
        unit="account",
    ),
    "ai.whisper_model_size": SettingSpec(
        key="ai.whisper_model_size",
        env_var_name="WHISPER_MODEL_SIZE",
        type="enum",
        default_getter=_getattr_default("WHISPER_MODEL_SIZE"),
        title="Cỡ model Whisper",
        section="AI & Whisper",
        description="Độ lớn model nhận dạng giọng nói: model lớn hơn thường chính xác hơn nhưng chậm và nặng RAM.",
        choices=["tiny", "base", "small", "medium"],
        enum_labels={
            "tiny": "Tiny — nhanh, nhẹ",
            "base": "Base — cân bằng",
            "small": "Small — chất lượng tốt hơn",
            "medium": "Medium — chi tiết cao nhất",
        },
    ),
    "ai.fallback_caption_pool": SettingSpec(
        key="ai.fallback_caption_pool",
        env_var_name="FALLBACK_CAPTION_POOL",
        type="str",
        default_getter=_getattr_default("FALLBACK_CAPTION_POOL"),
        title="Template Fallback Caption",
        section="AI & Whisper",
        description="Mẫu caption dự phòng. Các mẫu cách nhau bởi dấu |",
    ),
    "ai.fallback_hashtag_pool": SettingSpec(
        key="ai.fallback_hashtag_pool",
        env_var_name="FALLBACK_HASHTAG_POOL",
        type="str",
        default_getter=_getattr_default("FALLBACK_HASHTAG_POOL"),
        title="Template Fallback Hashtag",
        section="AI & Whisper",
        description="Mẫu bộ tag dự phòng. Cụm bộ tag cách nhau bởi dấu |, trong mỗi bộ các tag cách nhau bởi dấu phẩy",
    ),
    "ai.prompt.beauty": SettingSpec(
        key="ai.prompt.beauty",
        env_var_name="PERSONA_PROMPT_BEAUTY", type="text", default_getter=_getattr_default("PERSONA_PROMPT_BEAUTY"),
        title="Prompt: Hệ Beauty/Skincare", section="AI Prompt Personas",
    ),
    "ai.prompt.fashion": SettingSpec(
        key="ai.prompt.fashion",
        env_var_name="PERSONA_PROMPT_FASHION", type="text", default_getter=_getattr_default("PERSONA_PROMPT_FASHION"),
        title="Prompt: Hệ Fashion/Outfit", section="AI Prompt Personas",
    ),
    "ai.prompt.tech": SettingSpec(
        key="ai.prompt.tech",
        env_var_name="PERSONA_PROMPT_TECH", type="text", default_getter=_getattr_default("PERSONA_PROMPT_TECH"),
        title="Prompt: Hệ Tech/Công nghệ", section="AI Prompt Personas",
    ),
    "ai.prompt.home": SettingSpec(
        key="ai.prompt.home",
        env_var_name="PERSONA_PROMPT_HOME", type="text", default_getter=_getattr_default("PERSONA_PROMPT_HOME"),
        title="Prompt: Hệ Gia dụng/Nhà cửa", section="AI Prompt Personas",
    ),
    "ai.prompt.funny": SettingSpec(
        key="ai.prompt.funny",
        env_var_name="PERSONA_PROMPT_FUNNY", type="text", default_getter=_getattr_default("PERSONA_PROMPT_FUNNY"),
        title="Prompt: Hệ Hài hước/Meme", section="AI Prompt Personas",
    ),
    "ai.prompt.general": SettingSpec(
        key="ai.prompt.general",
        env_var_name="PERSONA_PROMPT_GENERAL", type="text", default_getter=_getattr_default("PERSONA_PROMPT_GENERAL"),
        title="Prompt: Khung chuẩn (General)", section="AI Prompt Personas",
    ),
    "ai.prompt.visual_hook": SettingSpec(
        key="ai.prompt.visual_hook",
        env_var_name="VISUAL_HOOK_INSTRUCTION", type="text", default_getter=_getattr_default("VISUAL_HOOK_INSTRUCTION"),
        title="Prompt: Luật phân tích Visual Hook", section="AI Prompt Configs",
        description="Quy tắc phân tích hook hình ảnh 3s đầu.",
    ),
    "ai.prompt.engagement_secrets": SettingSpec(
        key="ai.prompt.engagement_secrets",
        env_var_name="ENGAGEMENT_SECRETS", type="text", default_getter=_getattr_default("ENGAGEMENT_SECRETS"),
        title="Prompt: Bí mật thuật toán (Engagement)", section="AI Prompt Configs",
        description="Luật viết để tăng tương tác (tò mò, hashtag...).",
    ),
    "ai.max_caption_length": SettingSpec(
        key="ai.max_caption_length",
        env_var_name="MAX_CAPTION_LENGTH",
        type="int",
        default_getter=_getattr_default("MAX_CAPTION_LENGTH"),
        title="Độ dài caption tối đa",
        section="AI & Whisper",
        description="Giới hạn ký tự cho caption do AI sinh ra (tránh bài quá dài).",
        min=50,
        max=5000,
        unit="ký tự",
    ),
    "ai.max_transcript_length": SettingSpec(
        key="ai.max_transcript_length",
        env_var_name="MAX_TRANSCRIPT_LENGTH",
        type="int",
        default_getter=_getattr_default("MAX_TRANSCRIPT_LENGTH"),
        title="Độ dài transcript tối đa",
        section="AI & Whisper",
        description="Cắt bớt phần transcript từ Whisper trước khi đưa vào pipeline caption.",
        min=100,
        max=20000,
        unit="ký tự",
    ),
    "MAX_HASHTAGS": SettingSpec(
        key="MAX_HASHTAGS",
        type="int",
        default_getter=_getattr_default("MAX_HASHTAGS"),
        title="Số hashtag tối đa",
        section="AI & Whisper",
        description="Giới hạn số hashtag AI được phép gắn vào caption.",
        min=0,
        max=50,
        unit="hashtag",
    ),
    "MAX_KEYWORDS": SettingSpec(
        key="MAX_KEYWORDS",
        type="int",
        default_getter=_getattr_default("MAX_KEYWORDS"),
        title="Số từ khóa SEO tối đa",
        section="AI & Whisper",
        description="Giới hạn số keyword SEO kèm theo nội dung AI.",
        min=0,
        max=50,
        unit="từ",
    ),
    "SAFE_MODE": SettingSpec(
        key="SAFE_MODE",
        type="bool",
        default_getter=_getattr_default("SAFE_MODE"),
        title="Chế độ an toàn (Safe mode)",
        section="Bật / tắt tính năng",
        description="Khi bật, worker có thể hạn chế hành vi rủi ro (tùy logic worker). Dùng khi cần giảm tốc độ / thử nghiệm.",
    ),
    "IDLE_ENGAGEMENT_ENABLED": SettingSpec(
        key="IDLE_ENGAGEMENT_ENABLED",
        type="bool",
        default_getter=_getattr_default("IDLE_ENGAGEMENT_ENABLED"),
        title="Tương tác khi rảnh (Idle engagement)",
        section="Bật / tắt tính năng",
        description="Cho phép worker thỉnh thoảng tương tác nhẹ (scroll, xem feed) khi không có job, mô phỏng người dùng thật.",
    ),
    "IDLE_ENGAGEMENT_PROBABILITY": SettingSpec(
        key="IDLE_ENGAGEMENT_PROBABILITY",
        type="float",
        default_getter=_getattr_default("IDLE_ENGAGEMENT_PROBABILITY"),
        title="Xác suất bắt đầu phiên tương tác",
        section="Tương tác khi rảnh",
        description="Xác suất (0–1) mỗi lần kiểm tra sẽ khởi động một phiên tương tác khi đang rảnh.",
        min=0.0,
        max=1.0,
        unit="0–1",
    ),
    "IDLE_MAX_DURATION_SECONDS": SettingSpec(
        key="IDLE_MAX_DURATION_SECONDS",
        type="int",
        default_getter=_getattr_default("IDLE_MAX_DURATION_SECONDS"),
        title="Thời lượng tối đa mỗi phiên tương tác",
        section="Tương tác khi rảnh",
        description="Giới hạn thời gian một phiên idle engagement chạy tối đa bao lâu.",
        min=5,
        max=600,
        unit="giây",
    ),
    "FFMPEG_ENABLED": SettingSpec(
        key="FFMPEG_ENABLED",
        type="bool",
        default_getter=_getattr_default("FFMPEG_ENABLED"),
        title="Bật xử lý video FFmpeg",
        section="Bật / tắt tính năng",
        description="Tắt nếu không muốn nén/resize/watermark video trước khi đăng (chỉ dùng file gốc).",
    ),
    "FFMPEG_PROFILE": SettingSpec(
        key="FFMPEG_PROFILE",
        type="enum",
        default_getter=_getattr_default("FFMPEG_PROFILE"),
        title="Kiểu xuất video (profile)",
        section="Xử lý video (FFmpeg)",
        description="reels: dọc 9:16; feed: vuông 1:1; compress_only: chỉ nén, không đổi khung hình.",
        choices=["reels", "feed", "compress_only"],
        enum_labels={
            "reels": "Reels (dọc 9:16)",
            "feed": "Feed (vuông 1:1)",
            "compress_only": "Chỉ nén (giữ tỉ lệ gần gốc)",
        },
    ),
    "FFMPEG_CRF": SettingSpec(
        key="FFMPEG_CRF",
        type="int",
        default_getter=_getattr_default("FFMPEG_CRF"),
        title="Chất lượng nén (CRF)",
        section="Xử lý video (FFmpeg)",
        description="CRF thấp = chất lượng cao, file lớn hơn; CRF cao = file nhỏ hơn, nhiều nén.",
        min=10,
        max=40,
        unit="CRF",
    ),
    "FFMPEG_WATERMARK_PATH": SettingSpec(
        key="FFMPEG_WATERMARK_PATH",
        type="str",
        default_getter=_getattr_default("FFMPEG_WATERMARK_PATH"),
        title="Đường dẫn ảnh logo watermark",
        section="Xử lý video (FFmpeg)",
        description="File PNG logo đè lên video. Để trống hoặc file không tồn tại thì bỏ watermark tĩnh.",
    ),
    "FFMPEG_WATERMARK_POSITION": SettingSpec(
        key="FFMPEG_WATERMARK_POSITION",
        type="enum",
        default_getter=_getattr_default("FFMPEG_WATERMARK_POSITION"),
        title="Vị trí logo watermark",
        section="Xử lý video (FFmpeg)",
        description="Góc đặt logo trên khung hình.",
        choices=["top_left", "top_right", "bottom_left", "bottom_right"],
        enum_labels={
            "top_left": "Trên — trái",
            "top_right": "Trên — phải",
            "bottom_left": "Dưới — trái",
            "bottom_right": "Dưới — phải",
        },
    ),
    "FFMPEG_WATERMARK_OPACITY": SettingSpec(
        key="FFMPEG_WATERMARK_OPACITY",
        type="float",
        default_getter=_getattr_default("FFMPEG_WATERMARK_OPACITY"),
        title="Độ mờ logo watermark",
        section="Xử lý video (FFmpeg)",
        description="Độ trong suốt của logo: 0 = trong suốt hoàn toàn, 1 = đậm hoàn toàn.",
        min=0.0,
        max=1.0,
        unit="0–1",
    ),
    "DRM_ENABLED": SettingSpec(
        key="DRM_ENABLED",
        type="bool",
        default_getter=_getattr_default("DRM_ENABLED"),
        title="Bật watermark động / bảo vệ (DRM nhẹ)",
        section="Bật / tắt tính năng",
        description="Bật lớp watermark động và metadata bảo vệ nội dung (theo VideoProtector).",
    ),
    "DRM_WATERMARK_TEXT": SettingSpec(
        key="DRM_WATERMARK_TEXT",
        type="str",
        default_getter=_getattr_default("DRM_WATERMARK_TEXT"),
        title="Chữ watermark động",
        section="Bảo vệ video (DRM)",
        description="Chuỗi hiển thị trong watermark động trên video (nếu DRM bật).",
    ),
    "VERCEL_REDIRECT_URL": SettingSpec(
        key="VERCEL_REDIRECT_URL",
        type="str",
        default_getter=_getattr_default("VERCEL_REDIRECT_URL"),
        title="URL dịch vụ redirect (tracking)",
        section="Hệ thống & liên kết",
        description="Base URL dịch vụ rút gọn/redirect click (affiliate tracking), nếu dùng.",
    ),
    "PUBLISHER_PUBLISH_DEADLINE_SEC": SettingSpec(
        key="PUBLISHER_PUBLISH_DEADLINE_SEC",
        type="int",
        default_getter=_getattr_default("PUBLISHER_PUBLISH_DEADLINE_SEC"),
        title="Deadline đăng bài (Publish job)",
        section="Publisher & Playwright",
        description="Thời gian tối đa (giây) cho một lần đăng Reels trước khi coi là timeout.",
        min=60,
        max=86400,
        unit="giây",
    ),
    "PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC": SettingSpec(
        key="PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC",
        type="int",
        default_getter=_getattr_default("PUBLISHER_IDLE_ENGAGEMENT_DEADLINE_SEC"),
        title="Deadline phiên idle engagement",
        section="Publisher & Playwright",
        description="Giới hạn thời gian một phiên tương tác khi rảnh trong publisher (giây).",
        min=60,
        max=86400,
        unit="giây",
    ),
    "PLAYWRIGHT_DEFAULT_TIMEOUT_MS": SettingSpec(
        key="PLAYWRIGHT_DEFAULT_TIMEOUT_MS",
        type="int",
        default_getter=_getattr_default("PLAYWRIGHT_DEFAULT_TIMEOUT_MS"),
        title="Playwright default timeout",
        section="Publisher & Playwright",
        description="Timeout mặc định cho thao tác trình duyệt (ms). Tăng nếu máy chậm hoặc mạng lag.",
        min=5000,
        max=600000,
        unit="ms",
        restart_required=True,
    ),
    "COMMENT_JOB_DELAY_MIN_SEC": SettingSpec(
        key="COMMENT_JOB_DELAY_MIN_SEC",
        type="int",
        default_getter=_getattr_default("COMMENT_JOB_DELAY_MIN_SEC"),
        title="Delay job comment — tối thiểu",
        section="Publisher & Playwright",
        description="Khoảng chờ ngẫu nhiên trước khi chạy job comment (giây).",
        min=0,
        max=3600,
        unit="giây",
        pair_with="COMMENT_JOB_DELAY_MAX_SEC",
    ),
    "COMMENT_JOB_DELAY_MAX_SEC": SettingSpec(
        key="COMMENT_JOB_DELAY_MAX_SEC",
        type="int",
        default_getter=_getattr_default("COMMENT_JOB_DELAY_MAX_SEC"),
        title="Delay job comment — tối đa",
        section="Publisher & Playwright",
        description="Giới hạn trên của delay ngẫu nhiên cho job comment (giây).",
        min=0,
        max=7200,
        unit="giây",
    ),
    "MAINT_VIRAL_LIMIT": SettingSpec(
        key="MAINT_VIRAL_LIMIT",
        type="int",
        default_getter=_getattr_default("MAINT_VIRAL_LIMIT"),
        title="Số viral xử lý mỗi chu kỳ bảo trì",
        section="Bảo trì & cảnh báo",
        description="Giới hạn số material viral worker bảo trì xử lý mỗi vòng, tránh một lần tải quá nhiều.",
        min=1,
        max=50,
        unit="video",
    ),
    "cleanup.log_retention_days": SettingSpec(
        key="cleanup.log_retention_days",
        type="int",
        default_getter=lambda: 30,
        title="Số ngày giữ log thô",
        section="Bảo trì & cảnh báo",
        description="Tự động xóa job_events và incident_logs cũ hơn số ngày này. Không xóa incident_groups.",
        min=1,
        max=365,
        unit="ngày",
    ),
    "ALERT_PENDING_THRESHOLD": SettingSpec(
        key="ALERT_PENDING_THRESHOLD",
        type="int",
        default_getter=_getattr_default("ALERT_PENDING_THRESHOLD"),
        title="Cảnh báo: ngưỡng job PENDING",
        section="Bảo trì & cảnh báo",
        description="Khi số job PENDING vượt ngưỡng, gửi cảnh báo Telegram (theo SystemMonitor).",
        min=1,
        max=500,
        unit="job",
    ),
    "ALERT_DRAFT_THRESHOLD": SettingSpec(
        key="ALERT_DRAFT_THRESHOLD",
        type="int",
        default_getter=_getattr_default("ALERT_DRAFT_THRESHOLD"),
        title="Cảnh báo: ngưỡng job DRAFT",
        section="Bảo trì & cảnh báo",
        description="Khi số bản nháp chờ duyệt vượt ngưỡng, cảnh báo để xử lý kịp.",
        min=1,
        max=500,
        unit="job",
    ),
    "ALERT_VIRAL_NEW_THRESHOLD": SettingSpec(
        key="ALERT_VIRAL_NEW_THRESHOLD",
        type="int",
        default_getter=_getattr_default("ALERT_VIRAL_NEW_THRESHOLD"),
        title="Cảnh báo: ngưỡng viral trạng thái NEW",
        section="Bảo trì & cảnh báo",
        description="Khi kho viral NEW quá đầy (vượt ngưỡng), cảnh báo để kịp download/xử lý.",
        min=1,
        max=1000,
        unit="mục",
    ),
    "MAINT_LOOP_SLEEP_SEC": SettingSpec(
        key="MAINT_LOOP_SLEEP_SEC",
        type="int",
        default_getter=_getattr_default("MAINT_LOOP_SLEEP_SEC"),
        title="Chu kỳ nghỉ worker bảo trì",
        section="Bảo trì & cảnh báo",
        description="Khoảng chờ giữa các vòng lặp maintenance (giây).",
        min=30,
        max=86400,
        unit="giây",
    ),
    "STRATEGIC_BOOST_INTERVAL_SEC": SettingSpec(
        key="STRATEGIC_BOOST_INTERVAL_SEC",
        type="int",
        default_getter=_getattr_default("STRATEGIC_BOOST_INTERVAL_SEC"),
        title="Khoảng cách strategic boost",
        section="Bảo trì & cảnh báo",
        description="Tối thiểu thời gian giữa các lần boost chiến lược trong maintenance (giây).",
        min=60,
        max=86400 * 7,
        unit="giây",
    ),
    "IDLE_ENGAGEMENT_COOLDOWN_MINUTES": SettingSpec(
        key="IDLE_ENGAGEMENT_COOLDOWN_MINUTES",
        type="int",
        default_getter=_getattr_default("IDLE_ENGAGEMENT_COOLDOWN_MINUTES"),
        title="Cooldown giữa các phiên idle engagement",
        section="Tương tác khi rảnh",
        description="Sau một phiên tương tác khi rảnh, chờ tối thiểu bao nhiêu phút trước khi có thể chạy lại.",
        min=1,
        max=1440,
        unit="phút",
    ),
    "TIKWM_API_BASE": SettingSpec(
        key="TIKWM_API_BASE",
        type="str",
        default_getter=_getattr_default("TIKWM_API_BASE"),
        title="TikWM API base URL",
        section="Quét TikTok & Viral",
        description="Endpoint API TikWM khi tải TikTok fallback (không dấu / cuối).",
    ),
    "TIKWM_API_TIMEOUT_SEC": SettingSpec(
        key="TIKWM_API_TIMEOUT_SEC",
        type="float",
        default_getter=_getattr_default("TIKWM_API_TIMEOUT_SEC"),
        title="TikWM API timeout",
        section="Quét TikTok & Viral",
        description="Timeout HTTP khi gọi API TikWM (giây).",
        min=1.0,
        max=120.0,
        unit="giây",
    ),
    "TELEGRAM_BOT_TOKEN": SettingSpec(
        key="TELEGRAM_BOT_TOKEN",
        type="str",
        default_getter=_getattr_default("TELEGRAM_BOT_TOKEN"),
        title="Telegram bot token",
        section="Tích hợp (chỉ .env)",
        description="Token BotFather — chỉ cấu hình qua biến môi trường TELEGRAM_BOT_TOKEN, không lưu DB.",
        is_secret=True,
        env_only=True,
        env_var_name="TELEGRAM_BOT_TOKEN",
    ),
    "GOOGLE_API_KEY": SettingSpec(
        key="GOOGLE_API_KEY",
        type="str",
        default_getter=_getattr_default("GOOGLE_API_KEY"),
        title="Google / Gemini API key",
        section="Tích hợp (chỉ .env)",
        description="Dùng GEMINI_API_KEY hoặc GOOGLE_API_KEY trong .env (config gộp qua GOOGLE_API_KEY), không lưu DB.",
        is_secret=True,
        env_only=True,
        env_var_name="GOOGLE_API_KEY",
    ),
    "TELEGRAM_CHAT_ID": SettingSpec(
        key="TELEGRAM_CHAT_ID",
        type="str",
        default_getter=_getattr_default("TELEGRAM_CHAT_ID"),
        title="Telegram chat ID",
        section="Tích hợp (chỉ .env)",
        description="ID chat/channel nhận thông báo — chỉ cấu hình qua TELEGRAM_CHAT_ID trong .env.",
        env_only=True,
        env_var_name="TELEGRAM_CHAT_ID",
    ),
    "THREADS_AUTO_MODE": SettingSpec(
        key="THREADS_AUTO_MODE",
        type="bool",
        default_getter=lambda: False,
        title="Bật Auto Threads News",
        section="Threads Auto",
        description="Tự động thu thập và đăng báo mới lên Threads.",
    ),
    "THREADS_POST_INTERVAL_MIN": SettingSpec(
        key="THREADS_POST_INTERVAL_MIN",
        type="int",
        default_getter=lambda: 180,
        title="Giới hạn thời gian (Cooldown)",
        section="Threads Auto",
        description="Khoảng thời gian tối thiểu (phút) giữa 2 bài đăng tự động trên Threads để tránh spam.",
        min=10,
        max=1440,
        unit="phút",
    ),
    "THREADS_MAX_ARTICLE_AGE_HOURS": SettingSpec(
        key="THREADS_MAX_ARTICLE_AGE_HOURS",
        type="int",
        default_getter=lambda: 6,
        title="Tuổi tối đa của bài tin",
        section="Threads Auto",
        description="Chỉ lấy bài tin còn mới trong số giờ này để tránh đăng lại tin đã nguội.",
        min=1,
        max=72,
        unit="giờ",
    ),
    "THREADS_TOPIC_DEDUP_HOURS": SettingSpec(
        key="THREADS_TOPIC_DEDUP_HOURS",
        type="int",
        default_getter=lambda: 24,
        title="Cửa sổ dedup chủ đề",
        section="Threads Auto",
        description="Nếu đã có bài Threads cùng `topic_key` trong số giờ này thì bỏ qua bài mới.",
        min=1,
        max=168,
        unit="giờ",
    ),
    "THREADS_ACCOUNT_CATEGORY_MAP": SettingSpec(
        key="THREADS_ACCOUNT_CATEGORY_MAP",
        type="text",
        default_getter=lambda: "{}",
        title="Map category theo account",
        section="Threads Auto",
        description="JSON map `account_id -> category` để route từng account Threads theo nhóm tin.",
    ),
    "THREADS_SCRAPE_CYCLE_MIN": SettingSpec(
        key="THREADS_SCRAPE_CYCLE_MIN",
        type="int",
        default_getter=lambda: 30,
        title="Chu kỳ quét tin mới",
        section="Threads Auto",
        description="Worker quét nguồn tin tức mỗi bao nhiêu phút. Giảm = cập nhật nhanh hơn, tăng tải hệ thống.",
        min=5,
        max=360,
        unit="phút",
    ),
    "THREADS_MAX_CHARS_PER_SEGMENT": SettingSpec(
        key="THREADS_MAX_CHARS_PER_SEGMENT",
        type="int",
        default_getter=lambda: 450,
        title="Ký tự tối đa mỗi bài trong thread",
        section="Threads Auto",
        description="Giới hạn ký tự cho mỗi bài đăng trong chuỗi thread (Threads giới hạn ~500 ký tự).",
        min=100,
        max=500,
        unit="ký tự",
    ),
    "THREADS_MAX_CAPTION_LENGTH": SettingSpec(
        key="THREADS_MAX_CAPTION_LENGTH",
        type="int",
        default_getter=lambda: 500,
        title="Ký tự tối đa caption (cắt cuối)",
        section="Threads Auto",
        description="Giới hạn cuối cùng cho caption sau khi thêm nguồn. Bài vượt quá sẽ bị cắt bớt.",
        min=200,
        max=600,
        unit="ký tự",
    ),
    "THREADS_AI_PROMPT": SettingSpec(
        key="THREADS_AI_PROMPT",
        type="text",
        default_getter=lambda: """Hãy đóng vai chuyên gia sáng tạo nội dung cho Threads.
Viết lại tin tức này thành bài đăng Threads cực thu hút.

YÊU CẦU ĐẶC BIỆT (Threading):
- Nếu tin tức dài hoặc có nhiều ý hay, hãy chia thành một chuỗi (thread) gồm 2-4 bài đăng.
- Bài đầu tiên (Head) phải cực kỳ "giật gân" (Hook).
- Các bài sau bổ sung chi tiết.
- Mỗi bài dưới {max_chars} ký tự.

QUY TẮC STYLE:
1. TIÊU ĐỀ VIẾT HOA (Hook), dùng emoji biểu cảm ‼️🔥.
2. Cấu trúc: 2-5 dòng, không hashtag.
3. Cung cấp nội dung cô đọng nhất.

TIN GỐC:
Tiêu đề: {title}
Tóm tắt: {summary}
Nguồn: {source_name}

TRẢ VỀ JSON LIST (Mảng các object):
[
  {{"caption": "Nội dung bài 1...", "reasoning": "..."}},
  {{"caption": "Nội dung bài 2...", "reasoning": "..."}}
]""",
        title="AI Prompt viết bài Threads",
        section="Threads Auto",
        description="Template prompt gửi cho Gemini. Dùng {title}, {summary}, {source_name}, {max_chars} làm biến thay thế.",
    ),
}


_ENV_KEY_OVERRIDES: dict[str, str] = {
    "viral_min_views": "VIRAL_MIN_VIEWS",
    "viral_max_videos_per_channel": "VIRAL_MAX_VIDEOS_PER_CHANNEL",
}


def env_var_name_for(spec: SettingSpec) -> str:
    if spec.env_var_name:
        return spec.env_var_name
    return _ENV_KEY_OVERRIDES.get(spec.key, spec.key.upper())


def resolve_setting_source(spec: SettingSpec, has_db_override: bool) -> str:
    """
    Where the UI should describe the effective value as coming from:
    database (runtime override), environment (.env / process env), or default (built-in fallback).
    """
    if spec.env_only:
        if spec.key == "GOOGLE_API_KEY":
            has_env = bool(
                (os.environ.get("GEMINI_API_KEY") or "").strip()
                or (os.environ.get("GOOGLE_API_KEY") or "").strip()
            )
            return "environment" if has_env else "default"
        ev = env_var_name_for(spec)
        val = os.environ.get(ev)
        return "environment" if val not in (None, "") else "default"
    if has_db_override:
        return "database"
    ev = env_var_name_for(spec)
    if os.environ.get(ev) is not None and os.environ.get(ev) != "":
        return "environment"
    return "default"


def pair_secondary_keys() -> frozenset[str]:
    """Keys that are rendered inside their partner row (pair_with)."""
    return frozenset(s.pair_with for s in SETTINGS.values() if s.pair_with)


def section_visible_count(specs: list[SettingSpec]) -> int:
    """Card count after collapsing pair_with secondaries."""
    sec = pair_secondary_keys()
    return len(specs) - sum(1 for s in specs if s.key in sec)


_CACHE_TTL_SEC = 3.0
_cache_ts: float = 0.0
_cache_values: dict[str, Any] = {}


def _cast_value(spec: SettingSpec, raw: str | None) -> Any:
    if raw is None:
        return None
    s = str(raw).strip()
    if spec.type == "int":
        return int(float(s))  # support "10.0" submissions
    if spec.type == "float":
        return float(s)
    if spec.type == "bool":
        return s.lower() in ("1", "true", "yes", "on")
    if spec.type == "enum":
        if spec.choices and s not in spec.choices:
            raise ValueError(f"Invalid choice for {spec.key}")
        return s
    return s


def _validate(spec: SettingSpec, value: Any) -> Any:
    if value is None:
        return value
    if spec.type in ("int", "float"):
        if spec.min is not None and float(value) < float(spec.min):
            raise ValueError(f"{spec.key} must be >= {spec.min}")
        if spec.max is not None and float(value) > float(spec.max):
            raise ValueError(f"{spec.key} must be <= {spec.max}")
    if spec.type == "enum":
        if spec.choices and value not in spec.choices:
            raise ValueError(f"{spec.key} must be one of: {', '.join(spec.choices)}")
    return value


def get_overrides(db: Session, use_cache: bool = True) -> dict[str, Any]:
    global _cache_ts, _cache_values
    now = time.time()
    if use_cache and _cache_values and (now - _cache_ts) < _CACHE_TTL_SEC:
        return dict(_cache_values)

    rows = db.query(RuntimeSetting).all()
    values: dict[str, Any] = {}
    for r in rows:
        spec = SETTINGS.get(r.key)
        if not spec:
            continue
        try:
            values[r.key] = _validate(spec, _cast_value(spec, r.value))
        except Exception:
            # ignore invalid stored values (do not break runtime)
            continue
    _cache_values = dict(values)
    _cache_ts = now
    return dict(values)


def get_effective(db: Session, key: str) -> Any:
    spec = SETTINGS.get(key)
    if not spec:
        raise KeyError(key)
    if spec.env_only:
        return spec.default_getter()
    overrides = get_overrides(db, use_cache=True)
    if key in overrides:
        return overrides[key]
    return spec.default_getter()


def get(key: str, db: Session = None, default: Any = None) -> Any:
    """Safe getter that can instantiate its own DB session if needed, avoiding boilerplate in workers."""
    spec = SETTINGS.get(key)
    if not spec:
        return default
        
    def _fetch(session: Session):
        if spec.env_only:
            return spec.default_getter()
        overrides = get_overrides(session, use_cache=True)
        return overrides.get(key, spec.default_getter())

    from app.database.core import SessionLocal
    if db is not None:
        return _fetch(db)
    else:
        with SessionLocal() as new_db:
            return _fetch(new_db)

def get_int(key: str, default: int = 0, db: Session = None) -> int:
    try:
        val = get(key, db=db, default=default)
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def get_bool(key: str, default: bool = False, db: Session = None) -> bool:
    val = get(key, db=db, default=default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 't', 'y', 'yes')
    return default

def get_str(key: str, default: str = "", db: Session = None) -> str:
    val = get(key, db=db, default=default)
    return str(val) if val is not None else default
    
def get_json(key: str, default: Any = None, db: Session = None) -> Any:
    import json
    val = get(key, db=db, default=None)
    if not val:
        return default
    try:
        if isinstance(val, str):
            return json.loads(val)
        return val
    except Exception:
        return default

def apply_runtime_overrides_to_config(db: Session) -> dict[str, Any]:
    """
    Apply DB overrides to this process's in-memory config module variables.
    Returns the effective overrides applied.
    """
    overrides = get_overrides(db, use_cache=True)
    for key, value in overrides.items():
        sp = SETTINGS.get(key)
        if sp and sp.env_only:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
    return overrides


def upsert_setting(db: Session, key: str, raw_value: str | None, updated_by: str | None = None) -> Any:
    spec = SETTINGS.get(key)
    if not spec:
        raise ValueError("Unsupported key")
    if spec.env_only:
        raise ValueError("This setting is environment-only and cannot be changed from the dashboard")
    value = _validate(spec, _cast_value(spec, raw_value))
    stored_value = str(value) if value is not None else None

    row = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    old_value = row.value if row else None
    if row:
        row.value = stored_value
        row.type = spec.type
        row.updated_by = updated_by
    else:
        row = RuntimeSetting(key=key, value=stored_value, type=spec.type, updated_by=updated_by)
        db.add(row)

    db.add(
        RuntimeSettingAudit(
            key=key,
            old_value=old_value,
            new_value=stored_value,
            action="UPSERT",
            updated_by=updated_by,
        )
    )
    db.commit()
    # bust cache
    global _cache_ts, _cache_values
    _cache_ts = 0.0
    _cache_values = {}
    return value


def reset_setting(db: Session, key: str, updated_by: str | None = None) -> None:
    spec = SETTINGS.get(key)
    if not spec:
        raise ValueError("Unsupported key")
    if spec.env_only:
        raise ValueError("This setting is environment-only and cannot be reset from the dashboard")
    row = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    old_value = row.value if row else None
    if row:
        db.delete(row)
    db.add(
        RuntimeSettingAudit(
            key=key,
            old_value=old_value,
            new_value=None,
            action="RESET",
            updated_by=updated_by,
        )
    )
    db.commit()
    global _cache_ts, _cache_values
    _cache_ts = 0.0
    _cache_values = {}


def list_sections() -> list[str]:
    return sorted({spec.section for spec in SETTINGS.values()})


def list_specs_by_section() -> dict[str, list[SettingSpec]]:
    grouped: dict[str, list[SettingSpec]] = {}
    for spec in SETTINGS.values():
        grouped.setdefault(spec.section, []).append(spec)
    for sec in grouped:
        grouped[sec].sort(key=lambda s: s.title.lower())
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def normalize_for_compare(key: str, raw_value: str | None) -> Any:
    """Cast+validate a raw form value to python type for stable comparisons."""
    spec = SETTINGS.get(key)
    if not spec:
        raise ValueError("Unsupported key")
    return _validate(spec, _cast_value(spec, raw_value))


def default_value(key: str) -> Any:
    spec = SETTINGS.get(key)
    if not spec:
        raise ValueError("Unsupported key")
    return spec.default_getter()
