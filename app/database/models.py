from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Integer, String, Boolean, Float, ForeignKey, Index, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import time
from pathlib import Path
from app.config import PROFILES_DIR, CONTENT_DIR

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

    @property
    def resolved_profile_path(self) -> str:
        """
        Dynamically resolves the absolute path to the profile.
        If the stored path doesn't exist (e.g., moved to VPS), 
        tries to find the same profile folder inside the current PROFILES_DIR.
        """
        if not self.profile_path:
            return ""
            
        p = Path(self.profile_path)
        if p.exists() and p.is_dir():
            return str(p.absolute())
            
        # Rebase if missing
        if p.is_absolute():
            rebased = PROFILES_DIR / p.name
            if rebased.exists() and rebased.is_dir():
                return str(rebased.absolute())
                
        return self.profile_path

    target_page = Column(String, nullable=True) # Legacy single page (kept for backward compat)
    target_pages = Column(String, nullable=True) # JSON array of page URLs for multi-target round-robin
    
    # Login Lifecycle Machine
    login_status = Column(String, default="NEW", index=True) # NEW, LOGGING_IN, ACTIVE, INVALID
    login_started_at = Column(Integer, nullable=True) # unix ts
    login_process_pid = Column(Integer, nullable=True) # OS Process ID of headless start
    last_login_check = Column(Integer, nullable=True) # unix ts session validation
    login_error = Column(String, nullable=True)
    
    # Idle Engagement – Niche/Topic keywords (JSON string, e.g. '["thời trang","decor"]')
    niche_topics = Column(String, nullable=True)
    page_niches = Column(String, nullable=True)  # JSON mapping page_url -> [niches]

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
        """Format competitor_urls JSON for UI textarea (legacy flat display)."""
        import json
        if not self.competitor_urls:
            return ""
        try:
            data = json.loads(self.competitor_urls)
            if not isinstance(data, list):
                return str(self.competitor_urls)
        except Exception:
            return self.competitor_urls

        lines = []
        for item in data:
            if isinstance(item, dict):
                url = item.get("url", "")
                tp = item.get("target_page")
                lines.append(f"{url} → {tp}" if tp else url)
            else:
                lines.append(str(item))
        return "\n".join(lines)

    @property
    def competitor_urls_grouped(self) -> dict:
        """Group competitor URLs by target_page for per-page UI textareas.

        Returns dict: {page_url: "url1\\nurl2", "_unassigned": "url3\\nurl4"}
        """
        import json
        result: dict[str, list[str]] = {}
        if not self.competitor_urls:
            return {}
        try:
            data = json.loads(self.competitor_urls)
            if not isinstance(data, list):
                return {}
        except Exception:
            return {}

        for item in data:
            if isinstance(item, dict):
                url = item.get("url", "")
                tp = item.get("target_page") or "_unassigned"
                result.setdefault(tp, []).append(url)
            else:
                result.setdefault("_unassigned", []).append(str(item))

        return {k: "\n".join(v) for k, v in result.items()}

    @property
    def page_niches_map(self) -> dict[str, list[str]]:
        """Return mapping page_url -> [niche1, niche2,...]."""
        import json
        if not self.page_niches:
            return {}
        try:
            data = json.loads(self.page_niches)
        except Exception:
            return {}

        result: dict[str, list[str]] = {}
        # Support both dict {url: [..]} and list[{'page_url':..., 'niches':[...]}]
        if isinstance(data, dict):
            for url, niches in data.items():
                if not url:
                    continue
                if isinstance(niches, list):
                    cleaned = [str(n).strip() for n in niches if str(n).strip()]
                else:
                    cleaned = [str(n).strip() for n in str(niches).split(",") if str(n).strip()]
                if cleaned:
                    result[str(url)] = cleaned
        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("page_url") or "").strip()
                if not url:
                    continue
                niches = item.get("niches") or []
                if not isinstance(niches, list):
                    niches = [niches]
                cleaned = [str(n).strip() for n in niches if str(n).strip()]
                if cleaned:
                    result[url] = cleaned
        return result

    @page_niches_map.setter
    def page_niches_map(self, data: dict[str, list[str]]):
        """Set page_niches from mapping; normalizes to list[{page_url, niches}]."""
        import json
        normalized = []
        for url, niches in (data or {}).items():
            url = str(url).strip()
            if not url:
                continue
            if not isinstance(niches, list):
                niches = [niches]
            cleaned = [str(n).strip() for n in niches if str(n).strip()]
            if cleaned:
                normalized.append({"page_url": url, "niches": cleaned})
        self.page_niches = json.dumps(normalized, ensure_ascii=False) if normalized else None

    @property
    def target_pages_list(self) -> list[str]:
        """Parse target_pages JSON string into a list of page URLs."""
        import json
        if not self.target_pages:
            return [self.target_page] if self.target_page else []
        try:
            data = json.loads(self.target_pages)
            if isinstance(data, list):
                return [str(u) for u in data if u]
        except Exception:
            pass
        return [self.target_page] if self.target_page else []

    @target_pages_list.setter
    def target_pages_list(self, pages: list[str]):
        """Set target_pages from a list of URLs."""
        import json
        cleaned = [p.strip() for p in pages if p and p.strip()]
        self.target_pages = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        self.target_page = cleaned[0] if cleaned else None

    def pick_next_target_page(self, db) -> str | None:
        """Round-robin: pick the target page that was posted to least recently."""
        pages = self.target_pages_list
        if not pages:
            return self.target_page
        if len(pages) == 1:
            return pages[0]

        from sqlalchemy import desc
        last_job = db.query(Job).filter(
            Job.account_id == self.id,
            Job.target_page.in_(pages),
            Job.status.in_(["DONE", "PENDING", "RUNNING", "AWAITING_STYLE", "DRAFT"]),
        ).order_by(desc(Job.id)).first()

        if not last_job or not last_job.target_page:
            return pages[0]

        try:
            last_idx = pages.index(last_job.target_page)
            return pages[(last_idx + 1) % len(pages)]
        except ValueError:
            return pages[0]

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
    target_page = Column(String, nullable=True) # Override account-level target_page if set
    ai_style = Column(String, default="short", nullable=True) # Style of caption AI should generate
    brain_used = Column(String, nullable=True) # Specialized persona used (e.g., BeautyExpert)
    ai_reasoning = Column(String, nullable=True) # Strategic reasoning behind this specific caption
    
    # State tracking
    status = Column(String, default="PENDING", index=True) # AWAITING_STYLE, DRAFT, PENDING, RUNNING, DONE, FAILED
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
    viral_min_views = Column(Integer, nullable=True)    # Ngưỡng view tối thiểu khi quét TikTok (None = dùng config)
    viral_max_videos_per_channel = Column(Integer, nullable=True)  # Số video tối đa mỗi kênh (None = dùng config)
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
    
    @property
    def thumbnail_url(self) -> str:
        """Returns the relative path to the generated thumbnail collage, or empty string if not downloaded."""
        if self.status in ("NEW", "FAILED") or not self.url:
            return ""
        import hashlib
        fhash = hashlib.md5(self.url.encode()).hexdigest()
        return f"/thumbnails/{fhash}_collage.jpg"

    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class DiscoveredChannel(Base):
    """Kênh TikTok đối thủ phát hiện tự động qua hashtag search."""
    __tablename__ = "discovered_channels"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    channel_url = Column(String, nullable=False)
    channel_name = Column(String, nullable=True)
    keyword_used = Column(String, nullable=True)
    follower_count = Column(Integer, default=0)
    video_count = Column(Integer, default=0)
    avg_views = Column(Integer, default=0)
    post_frequency = Column(Float, default=0.0)  # videos per week
    score = Column(Float, default=0.0, index=True)  # avg_views * post_frequency / 1000
    status = Column(String, default="NEW", index=True)  # NEW, APPROVED, IGNORED

    discovered_at = Column(Integer, default=now_ts)
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)

    account = relationship("Account")


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

class PageInsight(Base):
    """
    Theo dõi tăng trưởng của Page theo thời gian (Time-series data).
    Data này dùng để vẽ biểu đồ và bảng xếp hạng trên Dashboard Insights.
    """
    __tablename__ = "page_insights"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True, nullable=True)
    platform = Column(String, default="facebook", index=True)
    page_url = Column(String, index=True, nullable=False)
    page_name = Column(String, nullable=True)
    
    post_url = Column(String, index=True, nullable=False)
    caption = Column(String, nullable=True)
    published_date = Column(String, nullable=True)
    
    views = Column(Integer, default=0, index=True)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    
    recorded_at = Column(Integer, default=now_ts, index=True) # Thời điểm cào data

class CompetitorReel(Base):
    """
    Reel đối thủ được thu thập tự động từ GQL suggested-reels stream.
    Dedup theo (reel_url, scrape_date).
    """
    __tablename__ = "competitor_reels"

    id = Column(Integer, primary_key=True, index=True)
    reel_url = Column(String, nullable=False, index=True)
    scrape_date = Column(String, nullable=False, index=True) # YYYY-MM-DD
    page_url = Column(String, nullable=True, index=True)
    
    views = Column(Integer, default=0, index=True)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    caption = Column(String, nullable=True)
    
    recorded_at = Column(Integer, default=now_ts, index=True)

    __table_args__ = (
        Index('idx_competitor_dedup', 'reel_url', 'scrape_date', unique=True),
    )


class AffiliateLink(Base):
    """
    Kho Link Affiliate cho tính năng "Máy Bơm Affiliate" (Auto-Injector).
    Khi AI nhận diện được keyword trùng khớp trong video, bot sẽ tự bốc url & comment_template
    để auto comment vào post.
    """
    __tablename__ = "affiliate_links"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, index=True, nullable=False) # e.g. "áo thun", "giày sneaker"
    url = Column(String, nullable=False) # e.g. "https://shope.ee/..."
    comment_template = Column(String, nullable=True) # e.g. "Đang sale mua ở đây nè: [LINK]"
    commission_rate = Column(Float, nullable=True) # e.g. 15.5 cho 15.5%
    ai_status = Column(String, nullable=True, index=True) # None, PENDING, PROCESSING, DONE, FAILED
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class KeywordBlacklist(Base):
    """Configurable FB compliance keywords (seeded + maintainable)."""
    __tablename__ = "keyword_blacklist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    keyword = Column(String, nullable=False, unique=True, index=True)
    category = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False)
    source = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, nullable=True, onupdate=now_ts)


class ComplianceAllowlist(Base):
    """Cụm từ được bỏ qua khi quét keyword (vd: trị giá)."""
    __tablename__ = "compliance_allowlist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phrase = Column(String, unique=True, nullable=False, index=True)
    reason = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    source = Column(String, nullable=True)
    created_at = Column(Integer, default=now_ts)


class ComplianceRegexRule(Base):
    """Quy tắc định dạng spam (regex) — mức độ thường là WARNING."""
    __tablename__ = "compliance_regex_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pattern = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="WARNING")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(Integer, default=now_ts)


class ViolationLog(Base):
    """Audit trail for FB compliance checks (publisher + optional UI)."""
    __tablename__ = "violation_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    affiliate_id = Column(Integer, nullable=True, index=True)
    job_id = Column(Integer, nullable=True, index=True)
    content_type = Column(String, nullable=True)
    original_content = Column(Text, nullable=True)
    rewritten_content = Column(Text, nullable=True)
    violations_found = Column(Text, nullable=True)
    action_taken = Column(String, nullable=True, index=True)
    checked_at = Column(Integer, default=now_ts, index=True)


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

class NewsArticle(Base):
    """
    Lưu trữ tin tức cào được từ RSS/Web để AI xử lý đăng Threads/Facebook.
    """
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String, unique=True, index=True, nullable=False)
    source_name = Column(String, nullable=True) # e.g. "VnExpress"
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    category = Column(String, nullable=True, index=True)
    published_at = Column(Integer, nullable=True, index=True) # Unix TS từ RSS
    
    # Processing status
    status = Column(String, default="NEW", index=True) # NEW, DRAFTED, POSTED, SKIPPED
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class ThreadsInteraction(Base):
    """
    Theo dõi các lượt tương tác (reply) trên Threads để tránh trả lời lặp lại.
    """
    __tablename__ = "threads_interactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    thread_id = Column(String, index=True) # ID của bài viết/bình luận gốc
    username = Column(String) # Người mình tương tác cùng
    content = Column(Text) # Nội dung mình đã reply
    status = Column(String, default="DONE") # DONE, FAILED
    
    created_at = Column(Integer, default=now_ts)

    __table_args__ = (
        Index('idx_threads_interaction_dedup', 'account_id', 'thread_id', unique=True),
    )


class IncidentLog(Base):
    """Append-only structured incident events for AI health reporting."""

    __tablename__ = "incident_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    platform = Column(String, nullable=False)
    feature = Column(String, nullable=True)
    category = Column(String, nullable=False, default="unknown", server_default="unknown")
    worker_name = Column(String, nullable=True)
    job_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)

    severity = Column(String, nullable=False)
    error_type = Column(String, nullable=False)
    error_signature = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    stacktrace = Column(Text, nullable=True)

    context_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict, server_default="{}")
    source_log_ref = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        CheckConstraint(
            "category IN ('ui_drift','auth','proxy','db','network','rate_limit','worker_crash','resource','unknown')",
            name="ck_incident_logs_category",
        ),
        CheckConstraint(
            "severity IN ('warning','error','critical')",
            name="ck_incident_logs_severity",
        ),
        Index("idx_incident_signature_time", "error_signature", "occurred_at"),
        Index("idx_incident_platform_time", "platform", "occurred_at"),
        Index("idx_incident_account_time", "account_id", "occurred_at"),
        Index("idx_incident_severity_time", "severity", "occurred_at"),
        Index("idx_incident_category_time", "category", "occurred_at"),
        Index("idx_incident_occurred_at", "occurred_at"),
        Index("idx_incident_job_id", "job_id"),
    )


class IncidentGroup(Base):
    """Denormalized incident aggregate used by reports and burst alerts."""

    __tablename__ = "incident_groups"

    error_signature = Column(String, primary_key=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    occurrence_count = Column(BigInteger, nullable=False, default=1, server_default="1")

    last_job_id = Column(String, nullable=True)
    last_account_id = Column(String, nullable=True)
    last_platform = Column(String, nullable=True)
    last_worker_name = Column(String, nullable=True)
    last_sample_message = Column(Text, nullable=True)
    severity_max = Column(String, nullable=False)

    status = Column(String, nullable=False, default="open", server_default="open")
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','acknowledged','resolved','ignored')",
            name="ck_incident_groups_status",
        ),
        Index("idx_groups_status_lastseen", "status", "last_seen_at"),
        Index("idx_groups_count", "occurrence_count"),
    )
