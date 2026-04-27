"""Runtime settings, system state, platform configs, audit logs.

Grouped here because they are all "system-level config / observability" rather
than domain entities.
"""
from sqlalchemy import Boolean, Column, Integer, JSON, String, Text

from app.database.models.base import Base, now_ts


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, index=True, default=1)
    worker_status = Column(String, default="RUNNING")  # RUNNING / PAUSED
    heartbeat_at = Column(Integer, nullable=True)  # unix ts
    current_job_id = Column(Integer, nullable=True)
    safe_mode = Column(Boolean, default=False)
    pending_command = Column(String, nullable=True)  # e.g. REQUEST_EXIT
    worker_started_at = Column(Integer, nullable=True)  # Phase C: uptime tracking
    engagement_status = Column(String, nullable=True)  # IDLE / ENGAGING / None
    engagement_detail = Column(String, nullable=True)  # e.g. "scroll_news_feed on Nguyen Ngoc Vi"
    viral_min_views = Column(Integer, nullable=True)  # Ngưỡng view tối thiểu khi quét TikTok (None = dùng config)
    viral_max_videos_per_channel = Column(Integer, nullable=True)  # Số video tối đa mỗi kênh (None = dùng config)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class RuntimeSetting(Base):
    """
    Runtime config overrides stored in DB.

    - key: setting identifier (whitelisted by app/services/settings.py)
    - value: stored as string, cast using type on read
    """

    __tablename__ = "runtime_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(String, nullable=True)
    type = Column(String, nullable=False)  # int|float|bool|str|enum
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)
    updated_by = Column(String, nullable=True)


class RuntimeSettingAudit(Base):
    """Append-only audit log for runtime settings changes."""

    __tablename__ = "runtime_settings_audit"

    id = Column(Integer, primary_key=True, index=True)
    ts = Column(Integer, default=now_ts, index=True)
    key = Column(String, index=True, nullable=False)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    action = Column(String, nullable=False)  # UPSERT|RESET
    updated_by = Column(String, nullable=True)


class AuditLog(Base):
    """
    Nhật ký hoạt động của hệ thống (phục vụ Database Explorer và Audit Trail).
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(Integer, default=now_ts, index=True)


class PlatformConfig(Base):
    __tablename__ = "platform_configs"
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False, unique=True)
    adapter_class = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    display_emoji = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    base_urls = Column(Text, nullable=True)
    viewport = Column(Text, nullable=True)
    user_agents = Column(Text, nullable=True)
    browser_args = Column(Text, nullable=True)
    media_extensions = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=True)
    updated_at = Column(Integer, nullable=True)


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    platform = Column(String, nullable=False)
    job_type = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    steps = Column(Text, nullable=True)
    timing_config = Column(Text, nullable=True)
    retry_config = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=True)
    updated_at = Column(Integer, nullable=True)


class PlatformSelector(Base):
    __tablename__ = "platform_selectors"
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False)
    category = Column(String, nullable=False)
    selector_name = Column(String, nullable=False)
    selector_type = Column(String, default="css")
    selector_value = Column(Text, nullable=False)
    locale = Column(String, default="*")
    priority = Column(Integer, default=0)
    version = Column(Integer, default=1)
    valid_from = Column(Integer, nullable=True)
    valid_until = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=True)
    updated_at = Column(Integer, nullable=True)


class CtaTemplate(Base):
    __tablename__ = "cta_templates"
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False)
    template = Column(Text, nullable=False)
    locale = Column(String, default="vi")
    page_url = Column(String, nullable=True)
    niche = Column(String, nullable=True)
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, nullable=True)
