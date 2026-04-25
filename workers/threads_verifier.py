"""
Threads Verification Worker
============================
Background worker that processes VERIFY_THREADS jobs.
Uses Playwright to launch the account's browser profile,
navigates to threads.net, and checks if the session is logged in
by inspecting BarcelonaSessionInfo in the page source.

Run with: python workers/threads_verifier.py
Manage with PM2: pm2 start workers/threads_verifier.py --name threads-verifier --interpreter python3
"""
import time
import sys
import os
import asyncio
from pathlib import Path

# Repo root on sys.path so `python workers/threads_verifier.py` works without PYTHONPATH=.
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.utils.logger import setup_shared_logger
setup_shared_logger("app")
logger = setup_shared_logger("threads_verifier")

from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import Account, Job
from app.constants import JobType, JobStatus

# ---------- Configuration ----------
POLL_INTERVAL = 15          # seconds between poll cycles
VERIFY_TIMEOUT = 60000      # Playwright navigation timeout (ms)
PAGE_SETTLE_WAIT = 6        # seconds to wait for page JS to settle
MAX_RETRIES_PER_JOB = 2     # retry count before marking FAILED


async def verify_threads_login(account: Account) -> tuple[bool, str]:
    """
    Launch Playwright with the account's persistent browser profile,
    navigate to https://www.threads.net/, and determine login state.

    Returns:
        (is_logged_in: bool, detail: str)
    """
    from playwright.async_api import async_playwright

    profile_path = account.resolved_profile_path
    if not profile_path or not Path(profile_path).exists():
        return False, f"Profile path not found: {profile_path}"

    logger.info("[%s] Launching browser with profile: %s", account.name, profile_path)

    async with async_playwright() as p:
        context = None
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
                timeout=30000,
            )

            page = await context.new_page()
            logger.info("[%s] Navigating to threads.net...", account.name)

            response = await page.goto(
                "https://www.threads.net/",
                wait_until="domcontentloaded",
                timeout=VERIFY_TIMEOUT,
            )

            # Wait for React/SPA to hydrate
            await asyncio.sleep(PAGE_SETTLE_WAIT)

            # Strategy 1: Parse BarcelonaSessionInfo from page source
            # Threads embeds session info as JSON in a <script> tag:
            #   "BarcelonaSessionInfo",[],{"is_th_session":true,"is_logged_out":false}
            content = await page.content()

            if '"is_logged_out":false' in content or '"is_logged_out": false' in content:
                logger.info("[%s] BarcelonaSessionInfo: logged IN", account.name)
                return True, "BarcelonaSessionInfo confirms logged in"

            if '"is_logged_out":true' in content or '"is_logged_out": true' in content:
                logger.warning("[%s] BarcelonaSessionInfo: logged OUT", account.name)
                return False, "BarcelonaSessionInfo confirms logged out"

            # Strategy 2: Check for login-related DOM elements
            # If logged out, Threads shows a "Log in" button prominently
            login_btn = page.locator('a[href*="/login"], button:has-text("Log in"), button:has-text("Dang nhap")')
            login_count = await login_btn.count()
            if login_count > 0:
                logger.warning("[%s] Found %d login button(s) - NOT logged in", account.name, login_count)
                return False, f"Login button detected ({login_count} found)"

            # Strategy 3: Check for logged-in indicators
            # When logged in, Threads shows navigation with home/search/profile icons
            nav_bar = page.locator('div[id="barcelona-page-layout"]')
            if await nav_bar.count() > 0:
                # Check if it's a 404/error page vs actual feed
                error_indicators = page.locator('text="Not all who wander are lost"')
                if await error_indicators.count() > 0:
                    # This is a 404 page - still logged in though
                    logger.info("[%s] Got 404 page but user IS authenticated", account.name)
                    return True, "Authenticated (404 page but session valid)"

                logger.info("[%s] Barcelona page layout found - likely logged in", account.name)
                return True, "Barcelona layout detected"

            # Fallback: Check HTTP response status
            final_url = page.url
            if "/login" in final_url.lower():
                logger.warning("[%s] Redirected to login page: %s", account.name, final_url)
                return False, f"Redirected to login: {final_url}"

            # Unable to determine - log warning and assume not verified
            logger.warning("[%s] Could not determine login state. URL: %s", account.name, final_url)
            return False, f"Indeterminate state at {final_url}"

        except Exception as e:
            logger.error("[%s] Browser error during verification: %s", account.name, e, exc_info=True)
            return False, f"Browser error: {str(e)[:200]}"

        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass


def process_verify_job(db: Session, job: Job):
    """Process a single VERIFY_THREADS job."""
    account = db.query(Account).filter(Account.id == job.account_id).first()
    if not account:
        job.status = JobStatus.FAILED
        job.last_error = "Account not found"
        db.commit()
        logger.error("Job #%s: Account ID %s not found", job.id, job.account_id)
        return

    logger.info("Processing VERIFY_THREADS Job #%s for account '%s' (ID: %s)", job.id, account.name, account.id)

    # Mark as running
    job.status = JobStatus.RUNNING
    job.started_at = int(time.time())
    job.last_heartbeat_at = int(time.time())
    db.commit()

    # Run the async verification
    try:
        is_logged_in, detail = asyncio.run(verify_threads_login(account))
    except Exception as e:
        is_logged_in = False
        detail = f"Unexpected error: {str(e)[:200]}"
        logger.error("Job #%s unexpected error: %s", job.id, e, exc_info=True)

    if is_logged_in:
        # Success! Add "threads" to platform
        platforms = {t.strip().lower() for t in (account.platform or "").split(",") if t.strip()}
        platforms.add("threads")
        account.platform = ",".join(sorted(platforms))
        job.status = JobStatus.DONE
        job.last_error = None
        job.finished_at = int(time.time())
        db.commit()
        logger.info("Job #%s SUCCESS: Account '%s' verified for Threads. Detail: %s", job.id, account.name, detail)
    else:
        # Failure
        tries = (job.tries or 0) + 1
        job.tries = tries

        if tries < MAX_RETRIES_PER_JOB:
            # Send back to PENDING for retry
            job.status = JobStatus.PENDING
            job.last_error = detail
            db.commit()
            logger.warning("Job #%s RETRY (%d/%d): %s", job.id, tries, MAX_RETRIES_PER_JOB, detail)
        else:
            job.status = JobStatus.FAILED
            job.last_error = detail
            job.finished_at = int(time.time())
            db.commit()
            logger.error(
                "Job #%s FAILED after %d tries: Account '%s' not logged into Threads. Error: %s",
                job.id, tries, account.name, detail
            )


def claim_next_verify_job(db: Session):
    """Find and return the next PENDING VERIFY_THREADS job, or None."""
    return db.query(Job).filter(
        Job.job_type == JobType.VERIFY_THREADS,
        Job.status == JobStatus.PENDING,
    ).order_by(Job.id.asc()).first()


def run():
    """Main polling loop."""
    logger.info("=" * 60)
    logger.info("Threads Verifier Worker started")
    logger.info("Poll interval: %ds | Verify timeout: %dms", POLL_INTERVAL, VERIFY_TIMEOUT)
    logger.info("=" * 60)

    while True:
        db = SessionLocal()
        try:
            job = claim_next_verify_job(db)
            if job:
                process_verify_job(db, job)
            else:
                logger.debug("No pending VERIFY_THREADS jobs. Sleeping %ds...", POLL_INTERVAL)
        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
        finally:
            db.close()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
