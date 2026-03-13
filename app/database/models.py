from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
import time

from .core import Base

def now_ts():
    return int(time.time())

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    platform = Column(String, index=True, default="facebook")
    
    # State flags
    is_active = Column(Boolean, default=True, index=True) # Enables/disables automation matching
    
    # Isolated Profile details
    profile_path = Column(String, unique=True, nullable=True)
    target_page = Column(String, nullable=True) # Page URL or ID to post to (instead of personal profile)
    
    # Login Lifecycle Machine
    login_status = Column(String, default="NEW", index=True) # NEW, LOGGING_IN, ACTIVE, INVALID
    login_started_at = Column(Integer, nullable=True) # unix ts
    login_process_pid = Column(Integer, nullable=True) # OS Process ID of headless start
    last_login_check = Column(Integer, nullable=True) # unix ts session validation
    login_error = Column(String, nullable=True)
    
    # Idle Engagement – Niche/Topic keywords (JSON string, e.g. '["thời trang","decor"]')
    niche_topics = Column(String, nullable=True)

    # Human Rest Cycle (Ngủ đông)
    sleep_start_time = Column(String, nullable=True) # e.g. "23:00"
    sleep_end_time = Column(String, nullable=True)   # e.g. "06:00"

    # Clone Niche (Link đối thủ)
    competitor_urls = Column(String, nullable=True)  # JSON list of URLs

    # Limits & Breakers
    daily_limit = Column(Integer, default=3)
    cooldown_seconds = Column(Integer, default=1800)
    last_post_ts = Column(Integer, nullable=True)
    consecutive_fatal_failures = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)
    # Auto-detected managed pages (JSON list: [{"name": "...", "url": "..."}, ...])
    managed_pages = Column(String, nullable=True)

    jobs = relationship("Job", back_populates="account")

    @property
    def managed_pages_list(self) -> list[dict]:
        """Parse managed_pages JSON string into a list of dicts."""
        import json
        if not self.managed_pages:
            return []
        try:
            data = json.loads(self.managed_pages)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    @managed_pages_list.setter
    def managed_pages_list(self, pages: list[dict]):
        """Set managed_pages from a list of dicts."""
        import json
        self.managed_pages = json.dumps(pages, ensure_ascii=False) if pages else None

    @property
    def niche_topics_list(self) -> str:
        """Helper to convert JSON string back to comma-separated string for UI."""
        import json
        if not self.niche_topics:
            return ""
        if str(self.niche_topics).startswith("["):
            try:
                lst = json.loads(self.niche_topics)
                if isinstance(lst, list):
                    return ", ".join(str(i) for i in lst)
            except Exception:
                pass
        return self.niche_topics

    @property
    def competitor_urls_list(self) -> str:
        """Helper to convert JSON string back to comma-separated string for UI."""
        import json
        if not self.competitor_urls:
            return ""
        if str(self.competitor_urls).startswith("["):
            try:
                lst = json.loads(self.competitor_urls)
                if isinstance(lst, list):
                    return "\n".join(str(i) for i in lst)
            except Exception:
                pass
        return self.competitor_urls

    @property
    def is_sleeping(self) -> bool:
        """Kiểm tra tài khoản có đang trong khung giờ ngủ đông không."""
        if not self.sleep_start_time or not self.sleep_end_time:
            return False
            
        import datetime
        from zoneinfo import ZoneInfo
        import app.config as config
        
        now = datetime.datetime.now(ZoneInfo(config.TIMEZONE)).time()
        try:
            start = datetime.datetime.strptime(self.sleep_start_time.strip(), "%H:%M").time()
            end = datetime.datetime.strptime(self.sleep_end_time.strip(), "%H:%M").time()
            if start < end:
                return start <= now <= end
            else: # Crosses midnight, e.g 23:00 -> 06:00
                return start <= now or now <= end
        except Exception:
            return False

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    media_path = Column(String)
    caption = Column(String)
    schedule_ts = Column(Integer, index=True)
    target_page = Column(String, nullable=True) # Override account-level target_page if set
    
    # State tracking
    status = Column(String, default="PENDING", index=True) # DRAFT, PENDING, RUNNING, DONE, FAILED
    is_approved = Column(Boolean, default=False) # True if user explicitly approved DRAFT
    tries = Column(Integer, default=0)
    max_tries = Column(Integer, default=3)
    
    # Error tracking
    last_error = Column(String, nullable=True)
    error_type = Column(String, nullable=True) # RETRYABLE or FATAL
    
    # Idempotency & Grouping
    external_post_id = Column(String, nullable=True)
    dedupe_key = Column(String, nullable=True, index=True)  # hash(account_id + media_uuid) — prevents double-upload
    batch_id = Column(String, nullable=True, index=True) # UUID grouping bulk uploads
    processed_media_path = Column(String, nullable=True) # FFmpeg output path (preserves original)
    
    # Post-Publish Metrics (Phase 14 & 17)
    post_url = Column(String, nullable=True)          # URL of the published post
    view_24h = Column(Integer, nullable=True)          # View count scraped most recently
    metrics_checked = Column(Boolean, default=False)   # Whether metrics have been scraped at least once
    last_metrics_check_ts = Column(Integer, nullable=True, index=True) # Last time views were updated
    
    # Link Tracking (Phase 15)
    tracking_code = Column(String, nullable=True, index=True)   # uuid[:8] unique per job
    tracking_url = Column(String, nullable=True)                 # https://domain/r/{code}
    affiliate_url = Column(String, nullable=True)                # Real target URL
    click_count = Column(Integer, default=0)                     # Click counter
    
    # Auto Comment (Phase 16)
    job_type = Column(String, default="POST")                    # POST | COMMENT
    parent_job_id = Column(Integer, nullable=True)               # COMMENT → link to parent POST
    scheduled_at = Column(Integer, nullable=True, index=True)    # Delayed execution timestamp
    auto_comment_text = Column(String, nullable=True)            # Comment content (multi-line)
    
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
    level = Column(String) # INFO, WARN, ERROR
    message = Column(String)
    meta_json = Column(String, nullable=True)


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, index=True, default=1)
    worker_status = Column(String, default="RUNNING") # RUNNING / PAUSED
    heartbeat_at = Column(Integer, nullable=True) # unix ts
    current_job_id = Column(Integer, nullable=True)
    safe_mode = Column(Boolean, default=False)
    pending_command = Column(String, nullable=True) # e.g. REQUEST_EXIT
    worker_started_at = Column(Integer, nullable=True)  # Phase C: uptime tracking
    engagement_status = Column(String, nullable=True)    # IDLE / ENGAGING / None
    engagement_detail = Column(String, nullable=True)    # e.g. "scroll_news_feed on Nguyen Ngoc Vi"
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)

class ViralMaterial(Base):
    """
    Bảng lưu trữ thông tin các Video/Post Viral quét được từ Mạng xã hội 
    thông qua quá trình tương tác dạo.
    """
    __tablename__ = "viral_materials"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default="facebook", index=True)
    url = Column(String, unique=True, index=True)
    title = Column(String, nullable=True)
    views = Column(Integer, default=0, index=True)
    scraped_by_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    target_page = Column(String, nullable=True) # Used for manual /reup targeting specific pages
    
    # AI Processing status
    status = Column(String, default="NEW", index=True) # NEW, DOWNLOADED, DRAFTED, FAILED
    last_error = Column(String, nullable=True)
    
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)
