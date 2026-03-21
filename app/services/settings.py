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
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None


def _getattr_default(name: str) -> Callable[[], Any]:
    return lambda: getattr(config, name)


SETTINGS: dict[str, SettingSpec] = {
    # Worker / system
    "WORKER_TICK_SECONDS": SettingSpec(
        key="WORKER_TICK_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_TICK_SECONDS"),
        title="Worker tick seconds",
        section="Worker",
        min=1,
        max=300,
    ),
    "WORKER_CRASH_THRESHOLD_SECONDS": SettingSpec(
        key="WORKER_CRASH_THRESHOLD_SECONDS",
        type="int",
        default_getter=_getattr_default("WORKER_CRASH_THRESHOLD_SECONDS"),
        title="Crash threshold seconds",
        section="Worker",
        min=30,
        max=3600,
    ),
    "WORKER_MAX_BATCH_SIZE": SettingSpec(
        key="WORKER_MAX_BATCH_SIZE",
        type="int",
        default_getter=_getattr_default("WORKER_MAX_BATCH_SIZE"),
        title="Worker max batch size",
        section="Worker",
        min=1,
        max=50,
    ),
    "MAX_FILES_PER_BATCH": SettingSpec(
        key="MAX_FILES_PER_BATCH",
        type="int",
        default_getter=_getattr_default("MAX_FILES_PER_BATCH"),
        title="Max files per batch",
        section="Worker",
        min=1,
        max=500,
    ),
    "TIMEZONE": SettingSpec(
        key="TIMEZONE",
        type="str",
        default_getter=_getattr_default("TIMEZONE"),
        title="Timezone",
        section="Worker",
    ),
    # TikTok scan (some are already in system_state but we also allow override here)
    "viral_min_views": SettingSpec(
        key="viral_min_views",
        type="int",
        default_getter=_getattr_default("VIRAL_MIN_VIEWS"),
        title="Viral min views (TikTok scan)",
        section="TikTok scan",
        min=0,
        max=10_000_000,
    ),
    "viral_max_videos_per_channel": SettingSpec(
        key="viral_max_videos_per_channel",
        type="int",
        default_getter=_getattr_default("VIRAL_MAX_VIDEOS_PER_CHANNEL"),
        title="Max videos per channel (TikTok scan)",
        section="TikTok scan",
        min=0,
        max=500,
    ),
    # Posting limits
    "POST_DELAY_MIN_SEC": SettingSpec(
        key="POST_DELAY_MIN_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MIN_SEC"),
        title="Post delay min (sec)",
        section="Posting limits",
        min=0,
        max=3600,
    ),
    "POST_DELAY_MAX_SEC": SettingSpec(
        key="POST_DELAY_MAX_SEC",
        type="int",
        default_getter=_getattr_default("POST_DELAY_MAX_SEC"),
        title="Post delay max (sec)",
        section="Posting limits",
        min=0,
        max=3600,
    ),
    "POSTS_PER_PAGE_PER_DAY": SettingSpec(
        key="POSTS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("POSTS_PER_PAGE_PER_DAY"),
        title="Posts per page per day cap",
        section="Posting limits",
        min=0,
        max=200,
    ),
    "REUP_VIDEOS_PER_PAGE_PER_DAY": SettingSpec(
        key="REUP_VIDEOS_PER_PAGE_PER_DAY",
        type="int",
        default_getter=_getattr_default("REUP_VIDEOS_PER_PAGE_PER_DAY"),
        title="Reup videos per page per day cap",
        section="Reup & Posting limits",
        min=0,
        max=200,
    ),
    "MAX_CONCURRENT_ACCOUNTS": SettingSpec(
        key="MAX_CONCURRENT_ACCOUNTS",
        type="int",
        default_getter=_getattr_default("MAX_CONCURRENT_ACCOUNTS"),
        title="Max concurrent accounts",
        section="Posting limits",
        min=1,
        max=10,
    ),
    # AI/Whisper
    "WHISPER_MODEL_SIZE": SettingSpec(
        key="WHISPER_MODEL_SIZE",
        type="enum",
        default_getter=_getattr_default("WHISPER_MODEL_SIZE"),
        title="Whisper model size",
        section="AI/Whisper",
        choices=["tiny", "base", "small", "medium"],
    ),
    "MAX_CAPTION_LENGTH": SettingSpec(
        key="MAX_CAPTION_LENGTH",
        type="int",
        default_getter=_getattr_default("MAX_CAPTION_LENGTH"),
        title="Max caption length",
        section="AI/Whisper",
        min=50,
        max=5000,
    ),
    "MAX_TRANSCRIPT_LENGTH": SettingSpec(
        key="MAX_TRANSCRIPT_LENGTH",
        type="int",
        default_getter=_getattr_default("MAX_TRANSCRIPT_LENGTH"),
        title="Max transcript length",
        section="AI/Whisper",
        min=100,
        max=20000,
    ),
    "MAX_HASHTAGS": SettingSpec(
        key="MAX_HASHTAGS",
        type="int",
        default_getter=_getattr_default("MAX_HASHTAGS"),
        title="Max hashtags",
        section="AI/Whisper",
        min=0,
        max=50,
    ),
    "MAX_KEYWORDS": SettingSpec(
        key="MAX_KEYWORDS",
        type="int",
        default_getter=_getattr_default("MAX_KEYWORDS"),
        title="Max keywords",
        section="AI/Whisper",
        min=0,
        max=50,
    ),
    # Feature toggles
    "SAFE_MODE": SettingSpec(
        key="SAFE_MODE",
        type="bool",
        default_getter=_getattr_default("SAFE_MODE"),
        title="Safe mode",
        section="Feature toggles",
    ),
    "IDLE_ENGAGEMENT_ENABLED": SettingSpec(
        key="IDLE_ENGAGEMENT_ENABLED",
        type="bool",
        default_getter=_getattr_default("IDLE_ENGAGEMENT_ENABLED"),
        title="Idle engagement enabled",
        section="Feature toggles",
    ),
    "IDLE_ENGAGEMENT_PROBABILITY": SettingSpec(
        key="IDLE_ENGAGEMENT_PROBABILITY",
        type="float",
        default_getter=_getattr_default("IDLE_ENGAGEMENT_PROBABILITY"),
        title="Idle engagement probability",
        section="Idle engagement",
        min=0.0,
        max=1.0,
    ),
    "IDLE_MAX_DURATION_SECONDS": SettingSpec(
        key="IDLE_MAX_DURATION_SECONDS",
        type="int",
        default_getter=_getattr_default("IDLE_MAX_DURATION_SECONDS"),
        title="Idle max duration (sec)",
        section="Idle engagement",
        min=5,
        max=600,
    ),
    "FFMPEG_ENABLED": SettingSpec(
        key="FFMPEG_ENABLED",
        type="bool",
        default_getter=_getattr_default("FFMPEG_ENABLED"),
        title="FFmpeg enabled",
        section="Feature toggles",
    ),
    "FFMPEG_PROFILE": SettingSpec(
        key="FFMPEG_PROFILE",
        type="enum",
        default_getter=_getattr_default("FFMPEG_PROFILE"),
        title="FFmpeg profile",
        section="FFmpeg",
        choices=["reels", "feed", "compress_only"],
    ),
    "FFMPEG_CRF": SettingSpec(
        key="FFMPEG_CRF",
        type="int",
        default_getter=_getattr_default("FFMPEG_CRF"),
        title="FFmpeg CRF",
        section="FFmpeg",
        min=10,
        max=40,
    ),
    "FFMPEG_WATERMARK_PATH": SettingSpec(
        key="FFMPEG_WATERMARK_PATH",
        type="str",
        default_getter=_getattr_default("FFMPEG_WATERMARK_PATH"),
        title="Watermark path",
        section="FFmpeg",
    ),
    "FFMPEG_WATERMARK_POSITION": SettingSpec(
        key="FFMPEG_WATERMARK_POSITION",
        type="enum",
        default_getter=_getattr_default("FFMPEG_WATERMARK_POSITION"),
        title="Watermark position",
        section="FFmpeg",
        choices=["top_left", "top_right", "bottom_left", "bottom_right"],
    ),
    "FFMPEG_WATERMARK_OPACITY": SettingSpec(
        key="FFMPEG_WATERMARK_OPACITY",
        type="float",
        default_getter=_getattr_default("FFMPEG_WATERMARK_OPACITY"),
        title="Watermark opacity",
        section="FFmpeg",
        min=0.0,
        max=1.0,
    ),
    "DRM_ENABLED": SettingSpec(
        key="DRM_ENABLED",
        type="bool",
        default_getter=_getattr_default("DRM_ENABLED"),
        title="DRM enabled",
        section="Feature toggles",
    ),
    "DRM_WATERMARK_TEXT": SettingSpec(
        key="DRM_WATERMARK_TEXT",
        type="str",
        default_getter=_getattr_default("DRM_WATERMARK_TEXT"),
        title="DRM watermark text",
        section="DRM",
    ),
    "VERCEL_REDIRECT_URL": SettingSpec(
        key="VERCEL_REDIRECT_URL",
        type="str",
        default_getter=_getattr_default("VERCEL_REDIRECT_URL"),
        title="Redirect service URL",
        section="System",
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

