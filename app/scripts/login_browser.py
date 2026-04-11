import argparse
import time
import sys
import os

# Ensure app package is accessible for database imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from playwright.sync_api import sync_playwright
from app.constants import AccountStatus


def update_account_status(account_id: int, status: str, error: str = None):
    try:
        from app.database.core import SessionLocal
        from app.database.models import Account
        
        db = SessionLocal()
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.login_status = status
            if error:
                account.login_error = error
            else:
                account.login_error = None
            account.login_process_pid = None
            db.commit()
        db.close()
    except Exception as e:
        print(f"Failed to update db: {e}")


def has_instagram_session(page) -> bool:
    cookies = page.context.cookies(["https://www.instagram.com/"])
    cookie_names = {cookie.get("name") for cookie in cookies}
    return "sessionid" in cookie_names and "ds_user_id" in cookie_names

def main():
    parser = argparse.ArgumentParser(description="Multi-account Login Bootstrapper")
    parser.add_argument("--profile-dir", required=True, help="Absolute path to the isolated profile directory")
    parser.add_argument("--account-id", type=int, required=True, help="Database ID of the account")
    parser.add_argument("--platform", default="facebook", help="Platform name: facebook or instagram")
    args = parser.parse_args()

    max_wait_seconds = 15 * 60 # 15 minutes failsafe
    poll_interval_seconds = 3
    elapsed = 0

    print(f"Launching headed browser for profile: {args.profile_dir}")

    login_url = "https://www.instagram.com/" if args.platform == "instagram" else "https://www.facebook.com/"
    
    with sync_playwright() as p:
        try:
            # Launch in headed mode so the user can actually type their password
            browser = p.chromium.launch_persistent_context(
                user_data_dir=args.profile_dir,
                headless=False,
                args=["--window-size=1200,800"]
            )
        except Exception as e:
            print(f"LOGIN_ERROR: Failed to launch browser context. Is it already open? {e}")
            update_account_status(args.account_id, AccountStatus.INVALID, f"Failed to launch browser: {e}")
            sys.exit(1)

        page = browser.pages[0] if browser.pages else browser.new_page()
        
        try:
            page.goto(login_url)
        except Exception as e:
            print(f"LOGIN_ERROR: Failed to load {args.platform}: {e}")
            browser.close()
            update_account_status(args.account_id, AccountStatus.INVALID, f"Failed to load {args.platform}: {e}")
            sys.exit(1)

        print("Browser loaded. Please log in. Waiting for authentication...")

        while elapsed < max_wait_seconds:
            try:
                if args.platform == "instagram":
                    username_input = page.query_selector('input[name="username"]')
                    password_input = page.query_selector('input[name="password"]')
                    current_url = (page.url or "").lower()
                    login_ok = (
                        "accounts/login" not in current_url
                        and not username_input
                        and not password_input
                        and has_instagram_session(page)
                    )
                else:
                    nav_bar = page.query_selector('div[role="navigation"]')
                    login_input = page.query_selector('input[name="email"]')
                    login_ok = bool(nav_bar and not login_input)

                if login_ok:
                    print("LOGIN_OK")
                    update_account_status(args.account_id, AccountStatus.ACTIVE, None)
                    time.sleep(2)
                    browser.close()
                    sys.exit(0)
                    
            except Exception as e:
                # Catching generic closed page exceptions if user closes it manually
                if "Target page, context or browser has been closed" in str(e):
                    print("LOGIN_CLOSED_BY_USER")
                    update_account_status(args.account_id, AccountStatus.INVALID, "Browser closed by user before login completion.")
                    sys.exit(0)
            
            time.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        print("LOGIN_TIMEOUT")
        browser.close()
        update_account_status(args.account_id, AccountStatus.INVALID, "Authentication timed out after 15 minutes.")
        sys.exit(1)

if __name__ == "__main__":
    main()
