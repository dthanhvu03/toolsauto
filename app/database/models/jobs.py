from pathlib import Path

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database.models.base import Base, now_ts


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    media_path = Column(String)

    @property
    def resolved_media_path(self) -> str:
        if not self.media_path:
            return ""
        from app.config import REUP_DIR, CONTENT_DIR
        p = Path(self.media_path)
        if p.exists():
            return str(p.absolute())
        # Rebase relative to CONTENT_DIR or REUP_DIR if missing
        try:
            if "reup_videos/" in self.media_path:
                suffix = self.media_path.split("reup_videos/", 1)[1]
                rebased = REUP_DIR / suffix
                if rebased.exists():
                    return str(rebased.absolute())
            elif "content/" in self.media_path:
                suffix = self.media_path.split("content/", 1)[1]
                rebased = CONTENT_DIR / suffix
                if rebased.exists():
                    return str(rebased.absolute())
        except Exception:
            pass
        return self.media_path

    caption = Column(String)
    schedule_ts = Column(Integer, index=True)
    target_page = Column(String, nullable=True)  # Override account-level target_page if set
    ai_style = Column(String, default="short", nullable=True)  # Style of caption AI should generate
    brain_used = Column(String, nullable=True)  # Specialized persona used (e.g., BeautyExpert)
    ai_reasoning = Column(String, nullable=True)  # Strategic reasoning behind this specific caption

    # State tracking
    status = Column(String, default="PENDING", index=True)  # AWAITING_STYLE, DRAFT, PENDING, RUNNING, DONE, FAILED
    is_approved = Column(Boolean, default=False)  # True if user explicitly approved DRAFT
    tries = Column(Integer, default=0)
    max_tries = Column(Integer, default=3)

    # Error tracking
    last_error = Column(String, nullable=True)
    error_type = Column(String, nullable=True)  # RETRYABLE or FATAL

    # Idempotency & Grouping
    external_post_id = Column(String, nullable=True)
    dedupe_key = Column(String, nullable=True, index=True)  # hash(account_id + media_uuid) — prevents double-upload
    batch_id = Column(String, nullable=True, index=True)  # UUID grouping bulk uploads
    processed_media_path = Column(String, nullable=True)  # FFmpeg output path (preserves original)

    @property
    def resolved_processed_media_path(self) -> str:
        if not self.processed_media_path:
            return ""
        from app.config import REUP_DIR, CONTENT_DIR
        p = Path(self.processed_media_path)
        if p.exists():
            return str(p.absolute())
        # Rebase relative to CONTENT_DIR or REUP_DIR if missing
        try:
            if "reup_videos/" in self.processed_media_path:
                suffix = self.processed_media_path.split("reup_videos/", 1)[1]
                rebased = REUP_DIR / suffix
                if rebased.exists():
                    return str(rebased.absolute())
            elif "content/" in self.processed_media_path:
                suffix = self.processed_media_path.split("content/", 1)[1]
                rebased = CONTENT_DIR / suffix
                if rebased.exists():
                    return str(rebased.absolute())
        except Exception:
            pass
        return self.processed_media_path

    # Post-Publish Metrics (Phase 14 & 17)
    post_url = Column(String, nullable=True)  # URL of the published post
    view_24h = Column(Integer, nullable=True)  # View count scraped most recently
    metrics_checked = Column(Boolean, default=False)  # Whether metrics have been scraped at least once
    last_metrics_check_ts = Column(Integer, nullable=True, index=True)  # Last time views were updated

    # Link Tracking (Phase 15)
    tracking_code = Column(String, nullable=True, index=True)  # uuid[:8] unique per job
    tracking_url = Column(String, nullable=True)  # https://domain/r/{code}
    affiliate_url = Column(String, nullable=True)  # Real target URL
    click_count = Column(Integer, default=0)  # Click counter

    # Auto Comment (Phase 16)
    job_type = Column(String, default="POST")  # POST | COMMENT
    parent_job_id = Column(Integer, nullable=True)  # COMMENT → link to parent POST
    scheduled_at = Column(Integer, nullable=True, index=True)  # Delayed execution timestamp
    auto_comment_text = Column(String, nullable=True)  # Comment content (multi-line)

    # Timestamps for locking and lifecycle
    locked_at = Column(Integer, nullable=True)
    last_heartbeat_at = Column(Integer, nullable=True, index=True)
    started_at = Column(Integer, nullable=True)
    finished_at = Column(Integer, nullable=True, index=True)

    created_at = Column(Integer, default=now_ts)

    account = relationship("Account", back_populates="jobs")

    __table_args__ = (
        Index('idx_jobs_status_schedule', 'status', 'schedule_ts'),
        Index('idx_jobs_account_status', 'account_id', 'status'),
        Index('idx_jobs_metrics', 'status', 'metrics_checked', 'finished_at'),
        # Partial unique indexes (WHERE ... IS NOT NULL handled at SQL level)
        Index('idx_jobs_dedupe_unique', 'account_id', 'dedupe_key', unique=True),
        Index('idx_jobs_tracking_unique', 'tracking_code', unique=True),
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True)
    ts = Column(Integer, default=now_ts)
    level = Column(String)  # INFO, WARN, ERROR
    message = Column(String)
    meta_json = Column(String, nullable=True)
