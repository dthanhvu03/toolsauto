"""
Threads Verification Worker (Headed / VNC-visible)
====================================================
Background worker that processes VERIFY_THREADS jobs.
Uses Playwright to launch the account's browser profile WITH GUI
on the VNC display (:99), so the user can see and interact with
the browser via VNC.

Flow:
1. Opens browser on VNC display :99 → navigates to threads.net
2. Waits up to USER_INTERACTION_TIMEOUT seconds for user to log in
3. Periodically checks login state every CHECK_INTERVAL seconds
4. If logged in → marks as Connected. If timeout → marks as Failed.

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
POLL_INTERVAL = 15                # seconds between poll cycles
VERIFY_TIMEOUT = 60000            # Playwright navigation timeout (ms)
USER_INTERACTION_TIMEOUT = 120    # seconds to wait for user to log in via VNC
CHECK_INTERVAL = 10               # seconds between login state checks
VNC_DISPLAY = ":99"               # X11 display for VNC (must match start_vps_vnc.py)
MAX_RETRIES_PER_JOB = 2           # retry count before marking FAILED


async def check_login_state(page) -> tuple[bool, str]:
    """
    Check if the current page shows a logged-in Threads session.
    Returns (is_logged_in, detail_message).
    """
    try:
        content = await page.content()

        # Strategy 1: BarcelonaSessionInfo (most reliable)
        if '"is_logged_out":false' in content or '"is_logged_out": false' in content:
            return True, "BarcelonaSessionInfo confirms logged in"

        if '"is_logged_out":true' in content or '"is_logged_out": true' in content:
            return False, "BarcelonaSessionInfo confirms logged out"

        # Strategy 2: Login button detection
        login_btn = page.locator('a[href*="/login"], button:has-text("Log in"), button:has-text("Dang nhap")')
        login_count = await login_btn.count()
        if login_count > 0:
            return False, f"Login button detected ({login_count} found)"

        # Strategy 3: Barcelona page layout
        nav_bar = page.locator('div[id="barcelona-page-layout"]')
        if await nav_bar.count() > 0:
            return True, "Barcelona layout detected"

        # Strategy 4: URL redirect
        final_url = page.url
        if "/login" in final_url.lower():
            return False, f"Redirected to login: {final_url}"

        return False, f"Indeterminate state at {page.url}"

    except Exception as e:
        return False, f"Check error: {str(e)[:200]}"


async def verify_threads_login(account: Account) -> tuple[bool, str]:
    """
    Launch a VISIBLE browser on VNC display, navigate to threads.net,
    and wait for user to log in. Periodically checks login state.

    Returns:
        (is_logged_in: bool, detail: str)
    """
    from playwright.async_api import async_playwright

    profile_path = account.resolved_profile_path
    if not profile_path or not Path(profile_path).exists():
        return False, f"Profile path not found: {profile_path}"

    logger.info("[%s] Launching VISIBLE browser on display %s with profile: %s",
                account.name, VNC_DISPLAY, profile_path)

    # Set DISPLAY so browser appears on VNC
    os.environ["DISPLAY"] = VNC_DISPLAY

    async with async_playwright() as p:
        context = None
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,         # HEADED - visible on VNC!
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    f"--display={VNC_DISPLAY}",
                    "--start-maximized",
                ],
                no_viewport=True,       # Use full window size
                timeout=30000,
            )

            page = await context.new_page()
            logger.info("[%s] Navigating to threads.net (visible on VNC)...", account.name)

            await page.goto(
                "https://www.threads.net/",
                wait_until="domcontentloaded",
                timeout=VERIFY_TIMEOUT,
            )

            # Wait for page to settle
            await asyncio.sleep(5)

            # First quick check - maybe already logged in
            is_logged_in, detail = await check_login_state(page)
            if is_logged_in:
                logger.info("[%s] Already logged in! Detail: %s", account.name, detail)
                # Keep browser open for 3 seconds so user can see on VNC
                await asyncio.sleep(3)
                return True, detail

            # Not logged in yet - wait for user to log in via VNC
            logger.info("[%s] NOT logged in. Waiting %d seconds for user to log in via VNC...",
                        account.name, USER_INTERACTION_TIMEOUT)

            elapsed = 0
            while elapsed < USER_INTERACTION_TIMEOUT:
                await asyncio.sleep(CHECK_INTERVAL)
                elapsed += CHECK_INTERVAL

                # Re-check login state (page may have changed after user interaction)
                try:
                    # Refresh page content after potential navigation
                    current_url = page.url
                    is_logged_in, detail = await check_login_state(page)

                    remaining = USER_INTERACTION_TIMEOUT - elapsed
                    logger.info("[%s] Check %d/%ds: logged_in=%s (URL: %s, remaining: %ds)",
                                account.name, elapsed, USER_INTERACTION_TIMEOUT,
                                is_logged_in, current_url[:60], remaining)

                    if is_logged_in:
                        logger.info("[%s] User logged in successfully! Detail: %s",
                                    account.name, detail)
                        # Keep browser visible briefly so user sees success
                        await asyncio.sleep(3)
                        return True, detail

                except Exception as e:
                    logger.warning("[%s] Check error at %ds: %s", account.name, elapsed, e)

            # Timeout - user didn't log in within the window
            logger.warning("[%s] Timeout after %ds. User did not complete login.",
                            account.name, USER_INTERACTION_TIMEOUT)
            return False, f"Timeout: user did not log in within {USER_INTERACTION_TIMEOUT}s"

        except Exception as e:
            logger.error("[%s] Browser error during verification: %s",
                         account.name, e, exc_info=True)
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

    logger.info("Processing VERIFY_THREADS Job #%s for account '%s' (ID: %s)",
                job.id, account.name, account.id)

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
        logger.info("Job #%s SUCCESS: Account '%s' verified for Threads. Detail: %s",
                     job.id, account.name, detail)
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
    logger.info("Threads Verifier Worker started (HEADED mode)")
    logger.info("VNC Display: %s | Poll: %ds | User timeout: %ds",
                VNC_DISPLAY, POLL_INTERVAL, USER_INTERACTION_TIMEOUT)
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
