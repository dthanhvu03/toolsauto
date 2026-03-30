import time
from dataclasses import dataclass, field
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


def _getattr_default(name: str) -> Callable[[], Any]:
    return lambda: getattr(config, name)


SETTINGS: dict[str, SettingSpec] = {
    "WORKER_TICK_SECONDS": SettingSpec(
        key="WORKER_TICK_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_TICK_SECONDS"),
        title="Tần suất quét Job (Worker)",
        section="Hệ thống Worker",
        description="Khoảng cách giữa mỗi lần worker kiểm tra hàng đợi job (giây). Giá trị nhỏ = phản hồi nhanh hơn nhưng tốn CPU hơn.",
        min=1,
        max=300,
        unit="giây",
    ),
    "WORKER_CRASH_THRESHOLD_SECONDS": SettingSpec(
        key="WORKER_CRASH_THRESHOLD_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_CRASH_THRESHOLD_SECONDS"),
        title="Ngưỡng coi Worker 'chết'",
        section="Hệ thống Worker",
        description="Nếu không nhận heartbeat trong khoảng thời gian này, hệ thống có thể coi worker gặp sự cố (phục vụ cảnh báo / health).",
        min=30,
        max=3600,
        unit="giây",
    ),
    "WORKER_MAX_BATCH_SIZE": SettingSpec(
        key="WORKER_MAX_BATCH_SIZE",
        type="int",
        default_getter=_getattr_default("WORKER_MAX_BATCH_SIZE"),
        title="Số job xử lý tối đa mỗi vòng",
        section="Hệ thống Worker",
        description="Giới hạn số job lấy ra xử lý trong một chu kỳ quét, tránh quá tải khi hàng đợi lớn.",
        min=1,
        max=50,
        unit="job",
    ),
    "MAX_FILES_PER_BATCH": SettingSpec(
        key="MAX_FILES_PER_BATCH",
        type="int",
        default_getter=_getattr_default("MAX_FILES_PER_BATCH"),
        title="Số file tối đa mỗi đợt upload",
        section="Hệ thống Worker",
        description="Giới hạn số file media xử lý trong một batch (upload hàng loạt), giúp ổn định RAM và ổ đĩa.",
        min=1,
        max=500,
        unit="file",
    ),
    "TIMEZONE": SettingSpec(
        key="TIMEZONE",
        type="str",
        default_getter=_getattr_default("TIMEZONE"),
        title="Múi giờ hệ thống",
        section="Hệ thống Worker",
        description="Múi giờ dùng cho lịch đăng, báo cáo ngày và khung giờ ngủ đông tài khoản (vd: Asia/Ho_Chi_Minh).",
    ),
    "viral_min_views": SettingSpec(
        key="viral_min_views",
        type="int",
        default_getter=_getattr_default("VIRAL_MIN_VIEWS"),
        title="Lượt xem tối thiểu (quét TikTok)",
        section="Quét TikTok & Viral",
        description="Video TikTok từ kênh đối thủ phải đạt ít nhất số view này mới được thêm vào kho viral (có thể ghi đè bởi system_state).",
        min=0,
        max=10_000_000,
        unit="view",
    ),
    "viral_max_videos_per_channel": SettingSpec(
        key="viral_max_videos_per_channel",
        type="int",
        default_getter=_getattr_default("VIRAL_MAX_VIDEOS_PER_CHANNEL"),
        title="Tối đa video mỗi kênh mỗi lần quét",
        section="Quét TikTok & Viral",
        description="Giới hạn số video lấy từ mỗi kênh TikTok trong một lần quét (0 = dùng logic mặc định trong code, thường cap 500).",
        min=0,
        max=500,
        unit="video",
    ),
    "POST_DELAY_MIN_SEC": SettingSpec(
        key="POST_DELAY_MIN_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MIN_SEC"),
        title="Delay đăng bài — tối thiểu",
        section="Giới hạn đăng bài",
        description="Khoảng chờ ngẫu nhiên giữa các lần đăng: giới hạn dưới (giây). Giúp giảm hành vi giống bot.",
        min=0,
        max=3600,
        unit="giây",
    ),
    "POST_DELAY_MAX_SEC": SettingSpec(
        key="POST_DELAY_MAX_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MAX_SEC"),
        title="Delay đăng bài — tối đa",
        section="Giới hạn đăng bài",
        description="Khoảng chờ ngẫu nhiên giữa các lần đăng: giới hạn trên (giây).",
        min=0,
        max=3600,
        unit="giây",
    ),
    "POSTS_PER_PAGE_PER_DAY": SettingSpec(
        key="POSTS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("POSTS_PER_PAGE_PER_DAY"),
        title="Giới hạn bài đăng / Page / ngày",
        section="Giới hạn đăng bài",
        description="Số bài tối đa mỗi Fan Page trong một ngày (0 = tắt giới hạn theo cấu hình này).",
        min=0,
        max=200,
        unit="bài",
    ),
    "REUP_VIDEOS_PER_PAGE_PER_DAY": SettingSpec(
        key="REUP_VIDEOS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("REUP_VIDEOS_PER_PAGE_PER_DAY"),
        title="Giới hạn Reup / Page / ngày",
        section="Giới hạn đăng bài",
        description="Số video reup tối đa mỗi Page mỗi ngày (0 = không áp giới hạn qua setting này).",
        min=0,
        max=200,
        unit="video",
    ),
    "MAX_CONCURRENT_ACCOUNTS": SettingSpec(
        key="MAX_CONCURRENT_ACCOUNTS",
        type="int",
        default_getter=_getattr_default("MAX_CONCURRENT_ACCOUNTS"),
        title="Số tài khoản chạy song song",
        section="Giới hạn đăng bài",
        description="Số browser/account có thể hoạt động đồng thời khi đăng (nên giữ thấp để an toàn IP).",
        min=1,
        max=10,
        unit="account",
    ),
    "WHISPER_MODEL_SIZE": SettingSpec(
        key="WHISPER_MODEL_SIZE",
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
    "MAX_CAPTION_LENGTH": SettingSpec(
        key="MAX_CAPTION_LENGTH",
        type="int",
        default_getter=_getattr_default("MAX_CAPTION_LENGTH"),
        title="Độ dài caption tối đa",
        section="AI & Whisper",
        description="Giới hạn ký tự cho caption do AI sinh ra (tránh bài quá dài).",
        min=50,
        max=5000,
        unit="ký tự",
    ),
    "MAX_TRANSCRIPT_LENGTH": SettingSpec(
        key="MAX_TRANSCRIPT_LENGTH",
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
}


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
    overrides = get_overrides(db, use_cache=True)
    if key in overrides:
        return overrides[key]
    return spec.default_getter()


def apply_runtime_overrides_to_config(db: Session) -> dict[str, Any]:
    """
    Apply DB overrides to this process's in-memory config module variables.
    Returns the effective overrides applied.
    """
    overrides = get_overrides(db, use_cache=True)
    for key, value in overrides.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return overrides


def upsert_setting(db: Session, key: str, raw_value: str | None, updated_by: str | None = None) -> Any:
    spec = SETTINGS.get(key)
    if not spec:
        raise ValueError("Unsupported key")
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
