import os
import time
import subprocess
import signal
from typing import List, Optional

from sqlalchemy.orm import Session
from app.database.models import Account, Job
import logging

logger = logging.getLogger(__name__)

def now_ts():
    return int(time.time())

class AccountService:
    BASE_PROFILE_DIR = os.path.abspath("content/profiles")

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
        return (login_button == 0 and email_input == 0) or nav_present

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
            login_status="NEW",
            daily_limit=daily_limit,
            cooldown_seconds=cooldown_seconds
        )
        db.add(new_acc)
        db.commit()
        db.refresh(new_acc)
        
        # Now set exact profile path
        profile_path = os.path.join(cls.BASE_PROFILE_DIR, f"{platform}_{new_acc.id}")
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
    def update_limits(db: Session, account_id: int, daily_limit: int, cooldown_seconds: int, niche_topics: str = "", sleep_start_time: str = "", sleep_end_time: str = "", competitor_urls: str = "", target_page: str = "") -> Account:
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
        account.target_page = target_page.strip() if target_page else None
        
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
            
        # Process competitor_urls: convert newline or comma-separated to JSON array
        raw_urls = (competitor_urls or "").strip()
        if raw_urls:
            if not raw_urls.startswith("["):
                urls = [u.strip() for u in raw_urls.replace('\n', ',').split(",") if u.strip()]
                raw_urls = _json.dumps(urls, ensure_ascii=False)
            account.competitor_urls = raw_urls
        else:
            account.competitor_urls = None
        
        db.commit()
        db.refresh(account)
        logger.info(f"Updated limits for account {account_id}: daily_limit={daily_limit}, cooldown={cooldown_seconds}, niche={account.niche_topics}, sleep={account.sleep_start_time}-{account.sleep_end_time}, competitors={account.competitor_urls}")
        return account

    @staticmethod
    def reset_failures(db: Session, account_id: int) -> Account:
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
            
        account.consecutive_fatal_failures = 0
        db.commit()
        db.refresh(account)
        logger.info(f"Reset consecutive_fatal_failures for account {account_id}")
        return account

    @staticmethod
    def delete_account(db: Session, account_id: int):
        account = AccountService.get_account(db, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found.")
            
        pending_running = db.query(Job).filter(
            Job.account_id == account_id,
            Job.status.in_(["PENDING", "RUNNING"])
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

        # Non-blocking spawn using the exact same python executable (venv) as the running FastAPI app
        import sys
        process = subprocess.Popen(
            [
                sys.executable,
                script_path,
                "--profile-dir",
                account.profile_path,
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
                    user_data_dir=account.profile_path,
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
                account.login_status = "ACTIVE"
                account.login_error = None
            else:
                account.login_status = "INVALID"
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
            account.login_status = "INVALID"
            account.login_error = reason
            db.commit()
        return account
