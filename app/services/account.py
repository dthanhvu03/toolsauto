import json
import os
import time
import subprocess
import signal
from typing import Any, List, Optional

from sqlalchemy.orm import Session
from app.database.models import Account, Job
from app.config import CONTENT_PROFILES_DIR
import logging
from app.constants import AccountStatus, JobStatus, ViralStatus


logger = logging.getLogger(__name__)


def get_discovery_keywords(account: Account) -> List[str]:
    """Lấy keywords cho discovery: ưu tiên niche theo Page, không có thì dùng niche cấp tài khoản."""
    import json as _json
    page_map = getattr(account, "page_niches_map", None) or {}
    keywords = []
    for _url, niches in (page_map or {}).items():
        if isinstance(niches, list):
            keywords.extend(n.strip() for n in niches if str(n).strip())
        else:
            keywords.extend(n.strip() for n in str(niches).split(",") if n and n.strip())
    keywords = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
    if keywords:
        return keywords
    raw = getattr(account, "niche_topics", None) or ""
    if not raw:
        return []
    try:
        if raw.strip().startswith("["):
            keywords = _json.loads(raw)
        else:
            keywords = [k.strip() for k in raw.split(",") if k.strip()]
        return [k for k in keywords if k]
    except Exception:
        return [k.strip() for k in raw.split(",") if k.strip()]


def now_ts():
    return int(time.time())

class AccountService:
    # Same root publisher uses; override with env CONTENT_PROFILES_DIR on VPS if needed.
    BASE_PROFILE_DIR = str(CONTENT_PROFILES_DIR)

    @staticmethod
    def get_login_url(platform: str) -> str:
        if platform == "instagram":
            return "https://www.instagram.com/"
        return "https://www.facebook.com/"

    @staticmethod
    def _has_instagram_session(page) -> bool:
        cookies = page.context.cookies(["https://www.instagram.com/"])
        cookie_names = {cookie.get("name") for cookie in cookies}
        return "sessionid" in cookie_names and "ds_user_id" in cookie_names

    @staticmethod
    def is_logged_in(page, platform: str) -> bool:
        current_url = (page.url or "").lower()
        if platform == "instagram":
            username_input = page.locator('input[name="username"]').count()
            password_input = page.locator('input[name="password"]').count()
            return (
                "accounts/login" not in current_url
                and username_input == 0
                and password_input == 0
                and AccountService._has_instagram_session(page)
            )

        login_button = page.locator('button[name="login"]').count()
        email_input = page.locator('input[name="email"]').count()
        nav_present = page.locator('div[role="navigation"]').count() > 0
        # Must see main nav — (no login fields) alone was false-positive on blank/guest shells.
        if login_button > 0 or email_input > 0:
            return False
        return nav_present

    @classmethod
    def ensure_base_dir(cls):
        if not os.path.exists(cls.BASE_PROFILE_DIR):
            os.makedirs(cls.BASE_PROFILE_DIR, exist_ok=True)
            
    @staticmethod
    def get_account(db: Session, account_id: int) -> Optional[Account]:
        return db.query(Account).filter(Account.id == account_id).first()
        
    @staticmethod
    def list_accounts(db: Session, skip: int = 0, limit: int = 100) -> List[Account]:
        return db.query(Account).order_by(Account.id.asc()).offset(skip).limit(limit).all()

    @classmethod
    def create_account(cls, db: Session, platform: str, name: str, daily_limit: int = 3, cooldown_seconds: int = 1800) -> Account:
        """Creates a new account in state NEW."""
        cls.ensure_base_dir()
        
        new_acc = Account(
            name=name,
            platform=platform,
            is_active=True,
            login_status=ViralStatus.NEW,
            daily_limit=daily_limit,
            cooldown_seconds=cooldown_seconds
        )
        db.add(new_acc)
        db.commit()
        db.refresh(new_acc)
        
        # Now set exact profile path
        profile_path = os.path.join(cls.BASE_PROFILE_DIR, f"{platform}_{new_acc.id}")
        profile_path = os.path.abspath(os.path.normpath(profile_path))
        os.makedirs(profile_path, exist_ok=True) # CRITICAL FIX: Physically provision directory
        
        new_acc.profile_path = profile_path
        db.commit()
        db.refresh(new_acc)
        
        return new_acc
        
    @staticmethod
    def toggle_account(db: Session, account_id: int) -> Optional[Account]:
        """Atomically flips the is_active state of an account."""
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
        
        new_status = not account.is_active
        db.query(Account).filter(Account.id == account_id).update({"is_active": new_status})
        db.commit()
        db.refresh(account)
        logger.info(f"Toggled account {account_id} is_active to {new_status}")
        return account

    @staticmethod
    def update_limits(
        db: Session,
        account_id: int,
        daily_limit: int,
        cooldown_seconds: int,
        niche_topics: str = "",
        sleep_start_time: str = "",
        sleep_end_time: str = "",
        competitor_urls: str = "",
        target_pages: list[str] | None = None,
        page_niches: str = "",
    ) -> Account:
        import json as _json
        if not (0 <= daily_limit <= 200):
            raise ValueError("daily_limit must be between 0 and 200.")
        if not (0 <= cooldown_seconds <= 86400):
            raise ValueError("cooldown_seconds must be between 0 and 86400.")
            
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
            
        account.daily_limit = daily_limit
        account.cooldown_seconds = cooldown_seconds

        # Multi-target pages
        pages = [p.strip() for p in (target_pages or []) if p and p.strip()]
        account.target_pages_list = pages
        
        account.sleep_start_time = sleep_start_time.strip() if sleep_start_time else None
        account.sleep_end_time = sleep_end_time.strip() if sleep_end_time else None
        
        # Process niche_topics: convert comma-separated to JSON array
        raw_niche = (niche_topics or "").strip()
        if raw_niche:
            if not raw_niche.startswith("["):
                keywords = [k.strip() for k in raw_niche.split(",") if k.strip()]
                raw_niche = _json.dumps(keywords, ensure_ascii=False)
            account.niche_topics = raw_niche
        else:
            account.niche_topics = None
            
        # Process competitor_urls: parse "url → target_page" lines into JSON objects
        raw_urls = (competitor_urls or "").strip()
        if raw_urls:
            if raw_urls.startswith("["):
                account.competitor_urls = raw_urls
            else:
                entries = []
                for line in raw_urls.replace('\r', '').split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    if ' → ' in line:
                        url_part, tp_part = line.split(' → ', 1)
                        url_part = url_part.strip()
                        tp_part = tp_part.strip() or None
                        if tp_part == "None":
                            tp_part = None
                        entries.append({"url": url_part, "target_page": tp_part})
                    else:
                        entries.append({"url": line, "target_page": None})
                account.competitor_urls = _json.dumps(entries, ensure_ascii=False) if entries else None
        else:
            account.competitor_urls = None

        # Process page_niches: JSON mapping page_url -> [niches]
        raw_page_niches = (page_niches or "").strip()
        if raw_page_niches:
            try:
                data = _json.loads(raw_page_niches)
            except Exception:
                data = {}
            # Normalize to dict[str, list[str]] before assigning
            mapping: dict[str, list[str]] = {}
            if isinstance(data, dict):
                for url, niches in data.items():
                    if not url:
                        continue
                    if not isinstance(niches, list):
                        niches = [niches]
                    cleaned = [str(n).strip() for n in niches if str(n).strip()]
                    if cleaned:
                        mapping[str(url).strip()] = cleaned
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
                        mapping[url] = cleaned
            account.page_niches_map = mapping
        else:
            account.page_niches = None

        db.commit()
        db.refresh(account)
        logger.info(
            "Updated limits for account %s: daily_limit=%s, cooldown=%s, niche=%s, sleep=%s-%s, competitors=%s, page_niches=%s",
            account_id,
            daily_limit,
            cooldown_seconds,
            account.niche_topics,
            account.sleep_start_time,
            account.sleep_end_time,
            account.competitor_urls,
            account.page_niches,
        )
        return account

    @staticmethod
    def reset_failures(db: Session, account_id: int) -> Account:
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
            
        account.consecutive_fatal_failures = 0
        account.login_status = AccountStatus.ACTIVE
        account.login_error = None
        account.is_active = True
        
        db.commit()
        db.refresh(account)
        logger.info(f"Full Rescue Reset performed for account {account_id}")
        return account

    @staticmethod
    def delete_account(db: Session, account_id: int):
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
            
        pending_running = db.query(Job).filter(
            Job.account_id == account_id,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        ).count()
        
        if pending_running > 0:
            raise ValueError(f"Cannot delete account {account_id} because it has {pending_running} active jobs.")
            
        db.delete(account)
        db.commit()
        logger.info(f"Deleted account {account_id} from database. Profile path '{account.profile_path}' retained safely.")
        return True

    @classmethod
    def start_login(cls, db: Session, account_id: int):
        """Spawns the headed browser process to allow user authentication."""
        # 1. Atomic Check
        updated_rows = db.query(Account).filter(
            Account.id == account_id,
            Account.login_status != "LOGGING_IN"
        ).update({"login_status": "LOGGING_IN", "login_started_at": now_ts()})
        db.commit()
        
        if updated_rows == 0:
            raise ValueError(f"Account {account_id} is already logging in or locking failed.")
            
        account = cls.get_account(db, account_id)
        
        # 2. Spawn Subprocess
        # We assume main.py is in root, so `app/scripts/login_browser.py` is relative
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "login_browser.py"))
        
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env["DISPLAY"] = ":99"

        # Non-blocking spawn using the exact same python executable (venv) as the running FastAPI app
        import sys
        process = subprocess.Popen(
            [
                sys.executable,
                script_path,
                "--profile-dir",
                account.resolved_profile_path,
                "--account-id",
                str(account.id),
                "--platform",
                account.platform,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
        
        # 3. Store PID
        account.login_process_pid = process.pid
        db.commit()
        
        return account

    @classmethod
    def kill_login_process(cls, db: Session, account: Account):
        if account.login_process_pid:
            try:
                os.kill(account.login_process_pid, signal.SIGTERM)
                time.sleep(2) # Give OS and Playwright time to release profile dir locks
            except OSError:
                pass # Already dead or missing
            
            account.login_process_pid = None
            db.commit()

    @classmethod
    def confirm_login(cls, db: Session, account_id: int):
        """Kills the active bootstrapper process and switches state if valid."""
        account = cls.get_account(db, account_id)
        if not account:
            raise ValueError("Account not found")
            
        cls.kill_login_process(db, account)
        
        # Actually verify the session headfully (minimal) or headlessly
        # We'll delegate the actual verification to a helper or simply mock it for now
        # For Personal-Grade, we assume if the user clicks "Confirm", they did it right,
        # but the prompt asked to check it. We can do a quick check here.
        
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=account.resolved_profile_path,
                    headless=True,
                    args=["--window-size=1280,720"]
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.set_default_timeout(30000)
                
                page.goto(cls.get_login_url(account.platform), wait_until="domcontentloaded")
                page.wait_for_timeout(3000) # Give it time to render the login page or feed

                is_logged_in = cls.is_logged_in(page, account.platform)
                
                browser.close()
                
            if is_logged_in:
                account.login_status = AccountStatus.ACTIVE
                account.login_error = None
            else:
                account.login_status = AccountStatus.INVALID
                account.login_error = f"Session expired or account requires re-login on {account.platform}."
                
            db.commit()
            return account
            
        except Exception as e:
            # Infrastructure/browser crashes are not proof that the session itself is invalid.
            account.login_error = f"Session verification crashed: {str(e)[:200]}"
            db.commit()
            return account

    @classmethod
    def validate_session(cls, db: Session, account_id: int):
        """Re-runs the confirm logic to validate cookies."""
        return cls.confirm_login(db, account_id)

    @classmethod
    def invalidate_account(cls, db: Session, account_id: int, reason: str):
        """Transitions an account state directly to INVALID."""
        account = cls.get_account(db, account_id)
        if account:
            account.login_status = AccountStatus.INVALID
            account.login_error = reason
            db.commit()
        return account

    # ── Dashboard / meta JSON helpers (pages, competitors) ─────────────────

    @staticmethod
    def normalize_page_url(url: str | None) -> str:
        if not url:
            return ""
        u = str(url).strip()
        if not u:
            return ""
        return u.rstrip("/")

    @staticmethod
    def extract_tiktok_competitors(account: Account) -> list[dict[str, Any]]:
        """Return list of {url, target_page} filtered to TikTok competitor URLs for an account."""
        out: list[dict[str, Any]] = []
        raw = account.competitor_urls
        if not raw:
            return out
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [{"url": str(data), "target_page": None}]
        except Exception:
            data = [{"url": u.strip(), "target_page": None} for u in str(raw).split(",") if u.strip()]

        for item in data:
            if isinstance(item, dict):
                url = str(item.get("url") or "").strip()
                tp = item.get("target_page") or None
            else:
                url = str(item).strip()
                tp = None
            if not url:
                continue
            if "tiktok.com/@" not in url.lower():
                continue
            out.append({"url": url, "target_page": tp})
        return out

    @staticmethod
    def build_tiktok_links_context_data(db: Session, query_params: Any) -> dict[str, Any]:
        """Data for TikTok Links templates (no Request object)."""
        import math

        from app.database.models import ViralMaterial

        tab = (query_params.get("tab") or "viral").strip()
        q = (query_params.get("q") or "").strip().lower()
        status = (query_params.get("status") or "").strip().upper()
        try:
            min_views = int(query_params.get("min_views") or 0)
        except Exception:
            min_views = 0
        try:
            page = max(1, int(query_params.get("page") or 1))
        except Exception:
            page = 1
        try:
            per_page = int(query_params.get("per_page") or 200)
        except Exception:
            per_page = 200
        per_page = max(50, min(500, per_page))

        accounts = db.query(Account).order_by(Account.name.asc()).all()
        competitor_groups: dict[str, dict[str, list[str]]] = {}
        competitor_total = 0

        page_index: dict[str, dict] = {}
        for acc in accounts:
            try:
                for p in (acc.managed_pages_list or []):
                    p_url = AccountService.normalize_page_url(p.get("url"))
                    if not p_url:
                        continue
                    entry = page_index.setdefault(p_url, {"name": None, "niches": set()})
                    if not entry.get("name") and p.get("name"):
                        entry["name"] = p.get("name")
            except Exception:
                pass
            try:
                for p_url, niches in (acc.page_niches_map or {}).items():
                    n_url = AccountService.normalize_page_url(p_url)
                    if not n_url:
                        continue
                    entry = page_index.setdefault(n_url, {"name": None, "niches": set()})
                    for n in (niches or []):
                        if n and str(n).strip():
                            entry["niches"].add(str(n).strip())
            except Exception:
                pass

        for acc in accounts:
            links = AccountService.extract_tiktok_competitors(acc)
            for link in links:
                url = link["url"]
                tp_raw = link["target_page"] or "_unassigned"
                tp = AccountService.normalize_page_url(tp_raw) if tp_raw != "_unassigned" else "_unassigned"
                tp_meta = page_index.get(tp, {}) if tp != "_unassigned" else {}
                tp_name = (tp_meta.get("name") or "")
                tp_niches = " ".join(sorted(tp_meta.get("niches") or []))
                if q and (q not in (acc.name or "").lower()) and (q not in (tp or "").lower()) and (q not in (url or "").lower()) and (q not in tp_name.lower()) and (q not in tp_niches.lower()):
                    continue
                competitor_groups.setdefault(tp, {}).setdefault(acc.name, []).append(url)
                competitor_total += 1

        viral_query = db.query(ViralMaterial).filter(ViralMaterial.platform == "tiktok")
        if status:
            viral_query = viral_query.filter(ViralMaterial.status == status)
        if min_views > 0:
            viral_query = viral_query.filter(ViralMaterial.views >= min_views)
        if q:
            viral_query = viral_query.filter(ViralMaterial.url.ilike(f"%{q}%"))

        viral_total = viral_query.count()
        total_pages = max(1, int(math.ceil(viral_total / per_page))) if viral_total else 1
        if page > total_pages:
            page = total_pages
        viral_rows = (
            viral_query.order_by(ViralMaterial.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return {
            "tab": tab,
            "q": q,
            "status": status,
            "min_views": min_views,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "competitor_total": competitor_total,
            "competitor_groups": competitor_groups,
            "viral_rows": viral_rows,
            "viral_total": viral_total,
            "page_index": {
                k: {"name": v.get("name"), "niches": sorted(list(v.get("niches") or []))}
                for k, v in page_index.items()
            },
        }

    @staticmethod
    def append_competitor_url_if_missing(
        account: Account,
        channel_url: str,
        target_page: Optional[str],
    ) -> None:
        """Append a competitor URL to account.competitor_urls JSON if not already present."""
        urls: list[Any] = []
        if account.competitor_urls:
            try:
                data = json.loads(account.competitor_urls)
                if isinstance(data, list):
                    urls = data
            except Exception:
                pass
        exists = any(u.get("url") == channel_url for u in urls if isinstance(u, dict))
        if not exists:
            urls.append({"url": channel_url, "target_page": target_page if target_page else None})
            account.competitor_urls = json.dumps(urls, ensure_ascii=False)
