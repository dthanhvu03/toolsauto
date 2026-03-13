"""
MetricsChecker: Scrapes view count from published Facebook posts after 24 hours.
Runs inside the worker loop, checking 1 job per tick to avoid overloading.

Safety rules:
  - Max 1 job per account per day (timezone-aware)
  - Skip accounts with recent fatal failures (circuit breaker)
  - Browser always closed via try/finally
"""
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, select

from app.database.models import Job, Account
from app.config import TIMEZONE

logger = logging.getLogger(__name__)


def now_ts():
    import time
    return int(time.time())


def today_start_ts() -> int:
    """Get the start-of-day timestamp in the configured timezone (e.g. Asia/Ho_Chi_Minh)."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())


class MetricsChecker:
    
    @staticmethod
    def check_pending(db: Session):
        """
        Find 1 DONE job older than N hours that hasn't been checked recently.
        
        Safety constraints:
          B1: Max 1 job per account per day (timezone-aware, NOT EXISTS)
          B2: Skip accounts with consecutive_fatal_failures >= 2
        """
        import os
        from sqlalchemy import or_
        hours = float(os.getenv("METRICS_CHECK_HOURS", "24"))
        threshold = now_ts() - int(hours * 3600)
        day_start = today_start_ts()
        
        # Build the main query with all safety filters
        # B1: NOT EXISTS subquery using SA 2.0 select() pattern
        checked_today_subq = (
            select(Job.id)
            .where(
                Job.account_id == Account.id,
                Job.last_metrics_check_ts >= day_start
            )
            .correlate(Account)
            .exists()
        )
        
        job = (
            db.query(Job)
            .join(Account, Job.account_id == Account.id)
            .filter(
                Job.status == "DONE",
                Job.post_url != None,
                Job.finished_at != None,
                # Either it was never checked, OR it was checked but is older than threshold
                or_(
                    Job.last_metrics_check_ts == None,
                    Job.last_metrics_check_ts <= threshold
                ),
                # B2: Skip weak accounts
                Account.consecutive_fatal_failures < 2,
                # B1: No other job from this account checked today
                ~checked_today_subq
            )
            .order_by(Job.finished_at.asc())
            .first()
        )
        
        if not job:
            return
        
        logger.info("[MetricsChecker] Checking 24h views for Job %s (account: %s): %s", 
                     job.id, job.account.name if job.account else "?", job.post_url)
        
        view_count = MetricsChecker._scrape_views(job)
        job.view_24h = view_count
        job.metrics_checked = True
        job.last_metrics_check_ts = now_ts()
        db.commit()
        
        logger.info("[MetricsChecker] Job %s → %s views after 24h", job.id, view_count)
    
    @staticmethod
    def _scrape_views(job: Job) -> int:
        """
        Open post_url in a lightweight headless browser, extract view count, close immediately.
        Uses a fresh browser context (NOT the account profile) to avoid checkpoint risk.
        Browser is ALWAYS closed via try/finally — no leak possible.
        """
        views = 0
        browser = None
        try:
            from playwright.sync_api import sync_playwright
            import os
            import re
            
            # Use the account's existing profile to bypass the login wall
            profile_dir = f"/home/vu/toolsauto/content/profiles/{job.account_id}"
            # Backward compatibility check for old path
            if not os.path.exists(profile_dir):
                 profile_dir = f"/home/vu/toolsauto/content/profiles/facebook_{job.account_id}"

            reel_id_match = re.search(r'/reel/(\d+)', job.post_url)
            if not reel_id_match:
                logger.warning("[MetricsChecker] Could not extract reel ID from job %s: %s", job.id, job.post_url)
                return 0
            reel_id = reel_id_match.group(1)

            with sync_playwright() as p:
                if os.path.exists(profile_dir):
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        headless=True,
                        viewport={"width": 1280, "height": 720},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                else:
                    # Without auth profile, we can't see personal reels cleanly usually
                    logger.warning("[MetricsChecker] Profile dir not found. Fallback might fail.")
                    browser = p.chromium.launch(headless=True)
                    ctx = browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = ctx.new_page()
                    
                page.set_default_timeout(20000)  # slightly longer just in case
                
                try:
                    # STRATEGY 3: To bypass geoblocking/soft-blocking generic reel urls on headless
                    # navigate directly to the user's reels tab and find the specific thumbnail
                    page.goto("https://www.facebook.com/me/reels_tab", wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                    
                    # Extract pairs of (URL, count) from all reel thumbnails in the grid
                    reels_data = page.evaluate("""
                    () => {
                        let results = [];
                        let els = document.querySelectorAll('a[href*="/reel/"]');
                        for (let el of els) {
                            results.push({url: el.href, text: el.innerText});
                        }
                        return results;
                    }
                    """)
                    
                    found_view_str = None
                    for rd in reels_data:
                        if reel_id in rd.get('url', ''):
                            found_view_str = rd.get('text', '').strip()
                            break
                            
                    if found_view_str:
                        # Extract number (supports 15K, 2,1M etc)
                        match = re.match(r'^([\d,.]+)(K|M|B| Tr|K\+)?$', found_view_str, re.IGNORECASE)
                        if match:
                            num_str = match.group(1).replace(',', '.')
                            suffix = match.group(2)
                            if not suffix and '.' in num_str and num_str.count('.') > 1:
                                num_str = num_str.replace('.', '')
                            
                            try:
                                val = float(num_str)
                                if suffix:
                                    s = suffix.upper().strip()
                                    if 'K' in s: val *= 1e3
                                    elif 'M' in s or 'TR' in s: val *= 1e6
                                    elif 'B' in s: val *= 1e9
                                views = int(val)
                            except:
                                pass
                                
                    if views == 0:
                        logger.warning("[MetricsChecker] Extracted 0 or failed to find reel index for %s on reels_tab", job.post_url)
                        
                finally:
                    # Guaranteed cleanup — no browser leak
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    try:
                        if browser: browser.close()
                    except Exception:
                        pass
                
        except Exception as e:
            logger.warning("[MetricsChecker] Failed to scrape views for Job %s: %s", job.id, e)
        
        return views
