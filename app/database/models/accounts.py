from pathlib import Path

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.config import PROFILES_DIR
from app.database.models.base import Base, now_ts


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    platform = Column(String, index=True, default="facebook")

    # State flags
    is_active = Column(Boolean, default=True, index=True)  # Enables/disables automation matching

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

    target_page = Column(String, nullable=True)  # Legacy single page (kept for backward compat)
    target_pages = Column(String, nullable=True)  # JSON array of page URLs for multi-target round-robin

    # Login Lifecycle Machine
    login_status = Column(String, default="NEW", index=True)  # NEW, LOGGING_IN, ACTIVE, INVALID
    login_started_at = Column(Integer, nullable=True)  # unix ts
    login_process_pid = Column(Integer, nullable=True)  # OS Process ID of headless start
    last_login_check = Column(Integer, nullable=True)  # unix ts session validation
    login_error = Column(String, nullable=True)

    # Idle Engagement – Niche/Topic keywords (JSON string, e.g. '["thời trang","decor"]')
    niche_topics = Column(String, nullable=True)
    page_niches = Column(String, nullable=True)  # JSON mapping page_url -> [niches]

    # Human Rest Cycle (Ngủ đông)
    sleep_start_time = Column(String, nullable=True)  # e.g. "23:00"
    sleep_end_time = Column(String, nullable=True)  # e.g. "06:00"

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

        # Lazy import to avoid circular dependency between accounts.py and jobs.py.
        from sqlalchemy import desc
        from app.database.models.jobs import Job

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
            else:  # Crosses midnight, e.g 23:00 -> 06:00
                return start <= now or now <= end
        except Exception:
            return False
