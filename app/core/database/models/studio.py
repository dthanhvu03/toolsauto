"""
ADR-061 — Studio: kho nguyên liệu, cache phân tích, mẫu, kênh, dự án và hàng việc.

Không FK sang ``accounts`` / ``jobs``: Studio không biết Facebook. ``viral_material_id`` chỉ để
đối chiếu với hệ cũ trong giai đoạn chạy song song (cầu nối Buffer, PLAN-106 P3).
"""
from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database.models.base import Base, now_ts


class StudioAsset(Base):
    """Một file nguyên liệu: video / audio / ảnh. Mọi bước sau chỉ trỏ tới id này."""

    __tablename__ = "studio_assets"

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False, default="video")  # video | audio | image
    origin = Column(String(16), nullable=False, default="upload")  # reup | upload | ai | brand
    source_url = Column(Text, nullable=True)
    credit = Column(String(255), nullable=True)  # kênh / tác giả gốc, để ghi nguồn (ADR-061 §6)
    title = Column(String(500), nullable=True)
    path = Column(Text, nullable=False)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    has_audio = Column(Boolean, nullable=True)
    sha256 = Column(String(64), nullable=True, unique=True)
    viral_material_id = Column(Integer, nullable=True, index=True)
    created_at = Column(Integer, nullable=False, default=now_ts)


class StudioAnalysis(Base):
    """Kết quả phân tích một asset (probe / transcript / silences / scenes) — tính 1 lần, dùng nhiều lần."""

    __tablename__ = "studio_analysis"
    __table_args__ = (UniqueConstraint("asset_id", "kind", name="uq_studio_analysis_asset_kind"),)

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("studio_assets.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(Integer, nullable=False, default=now_ts)


class StudioTemplate(Base):
    """Một mẫu edit: ``kind`` là mã hàm trong ``compose/templates``, ``params`` là tham số anh chỉnh."""

    __tablename__ = "studio_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(40), nullable=False)
    params = Column(JSON, nullable=True)
    created_at = Column(Integer, nullable=False, default=now_ts)
    updated_at = Column(Integer, nullable=False, default=now_ts, onupdate=now_ts)


class StudioChannel(Base):
    """Một kênh Buffer đã chuyển sang Studio: mẫu mặc định, duyệt, giờ đăng, nhận diện thương hiệu."""

    __tablename__ = "studio_channels"

    id = Column(Integer, primary_key=True)
    buffer_channel_id = Column(String(64), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    template_id = Column(Integer, ForeignKey("studio_templates.id"), nullable=True)
    auto_approve = Column(Boolean, nullable=False, default=False)
    show_credit = Column(Boolean, nullable=False, default=True)
    slot_hours = Column(JSON, nullable=True)
    intro_asset_id = Column(Integer, ForeignKey("studio_assets.id"), nullable=True)
    outro_asset_id = Column(Integer, ForeignKey("studio_assets.id"), nullable=True)
    logo_asset_id = Column(Integer, ForeignKey("studio_assets.id"), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    # Bật thì video reup hệ cũ tải cho kênh này đi vào Studio thay vì ReupProcessor (PLAN-106 P2).
    take_reup = Column(Boolean, nullable=False, default=False)
    created_at = Column(Integer, nullable=False, default=now_ts)


class StudioProject(Base):
    """Một video ra: spec (bản mô tả edit) + trạng thái + file đã render."""

    __tablename__ = "studio_projects"
    __table_args__ = (Index("ix_studio_projects_status", "status"),)

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("studio_channels.id"), nullable=True)
    template_id = Column(Integer, ForeignKey("studio_templates.id"), nullable=True)
    asset_id = Column(Integer, ForeignKey("studio_assets.id"), nullable=True)
    spec = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    caption = Column(Text, nullable=True)
    hashtags = Column(JSON, nullable=True)
    output_path = Column(Text, nullable=True)
    duration = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False, default=now_ts)
    updated_at = Column(Integer, nullable=False, default=now_ts, onupdate=now_ts)
    rendered_at = Column(Integer, nullable=True)
    approved_at = Column(Integer, nullable=True)
    # PLAN-106 P3: dòng viral_materials READY mà Buffer đọc (cầu nối, bỏ ở P6).
    viral_material_id = Column(Integer, nullable=True, index=True)


class StudioTask(Base):
    """Một lần chuyển bước trong quy trình. Worker nhận dòng QUEUED, chạy bước, pipeline xếp bước sau."""

    __tablename__ = "studio_tasks"
    __table_args__ = (Index("ix_studio_tasks_claim", "status", "lane", "run_after"),)

    id = Column(Integer, primary_key=True)
    flow = Column(String(32), nullable=False)
    stage = Column(String(32), nullable=False)
    lane = Column(String(16), nullable=False, default="light")
    status = Column(String(16), nullable=False, default="QUEUED")
    asset_id = Column(Integer, ForeignKey("studio_assets.id", ondelete="CASCADE"), nullable=True)
    project_id = Column(Integer, ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=True)
    parent_id = Column(Integer, nullable=True, index=True)  # việc của bước trước — lần theo cả quy trình
    payload = Column(JSON, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    run_after = Column(Integer, nullable=False, default=now_ts)
    claimed_by = Column(String(64), nullable=True)
    claimed_at = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False, default=now_ts)
    finished_at = Column(Integer, nullable=True)
