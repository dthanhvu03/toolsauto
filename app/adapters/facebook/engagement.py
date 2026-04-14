"""
FacebookEngagementTask – Idle Engagement module for Account Warming.

When workers are idle (no pending jobs), this module performs human-like
interactions on Facebook to maintain account trust & build niche relevance.

Actions:
  1. scroll_news_feed()          – casual feed browsing
  2. watch_reels_randomly()      – watch short videos on Watch tab
  3. search_and_explore_topic()  – search niche keywords, browse results

All actions are wrapped with hard timeout & checkpoint detection.
"""
import json
import logging
import random
import time
import traceback

from playwright.sync_api import Page

from app.utils.human_behavior import (
    casual_scroll_feed,
    human_scroll,
    human_search,
    stealth_click,
)

logger = logging.getLogger(__name__)

# URLs that indicate the account has been checkpointed / logged out
_CHECKPOINT_INDICATORS = [
    "/login/",
    "/checkpoint/",
    "login_attempt",
    "account_locked",
]


def _is_checkpointed(page: Page) -> bool:
    """Return True if the current page looks like a login/checkpoint page."""
    url = page.url.lower()
    for indicator in _CHECKPOINT_INDICATORS:
        if indicator in url:
            return True

    # Also check DOM for login form
    try:
        login_btn = page.locator('button[name="login"]').count() > 0
        email_in = page.locator('input[name="email"]').count() > 0
        if login_btn and email_in:
            return True
    except Exception:
        pass

    return False


class FacebookEngagementTask:
    """
    Stateless engagement helper.  Requires an already-opened Playwright Page
    that is logged in to Facebook (reuses the adapter's browser session).

    Usage:
        task = FacebookEngagementTask(page)
        task.run_random_action(
            max_duration=90,
            niche_keywords=["thời trang", "decor"],
        )
    """

    def __init__(self, page: Page):
        self.page = page
        self.interacted_urls = set()
        self.scraped_materials = []
        self._already_scraped_urls = set()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_random_action(
        self,
        max_duration: int = 90,
        niche_keywords: list[str] | None = None,
        competitor_urls: list[str] | None = None,
    ) -> dict:
        """
        Pick a random engagement action and execute it with a hard timeout.

        Returns a dict with keys:
            action  – name of the action performed
            ok      – True if completed without fatal error
            error   – error description (if any)
            checkpointed – True if account was detected as logged-out
            urls    – list of URLs interacted with/watched
        """
        # Build weighted action pool
        actions = []
        
        if competitor_urls:
            actions.append(("spy_competitor", 0.40))
            
        actions.append(("scroll_news_feed", 0.30 if competitor_urls else 0.40))
        actions.append(("watch_reels", 0.15 if competitor_urls else 0.35))
        
        if niche_keywords:
            actions.append(("search_topic", 0.15 if competitor_urls else 0.25))

        # Normalise weights
        total = sum(w for _, w in actions)
        roll = random.uniform(0, total)
        cumulative = 0.0
        chosen = actions[0][0]
        for name, weight in actions:
            cumulative += weight
            if roll <= cumulative:
                chosen = name
                break

        logger.info("[ENGAGEMENT] Action chosen: %s (timeout=%ds)", chosen, max_duration)

        result = {
            "action": chosen,
            "ok": False,
            "error": None,
            "checkpointed": False,
            "urls": []
        }

        try:
            if chosen == "scroll_news_feed":
                self._action_scroll_feed(max_duration)
            elif chosen == "watch_reels":
                keyword = random.choice(niche_keywords) if niche_keywords else None
                self._action_watch_reels(max_duration, keyword)
            elif chosen == "search_topic":
                keyword = random.choice(niche_keywords)
                self._action_search_topic(keyword, max_duration)
            elif chosen == "spy_competitor":
                target_url = random.choice(competitor_urls)
                self._action_spy_competitor(target_url, max_duration)

            result["ok"] = True
            result["urls"] = list(self.interacted_urls)
            result["scraped_materials"] = self.scraped_materials
            logger.info("[ENGAGEMENT] Action '%s' completed successfully. URLs: %s, Scraped: %d", 
                        chosen, len(self.interacted_urls), len(self.scraped_materials))

        except _CheckpointDetected:
            result["checkpointed"] = True
            result["error"] = "Account checkpoint/login detected during engagement"
            logger.warning("[ENGAGEMENT] CHECKPOINT detected! Aborting engagement.")

        except Exception as e:
            result["error"] = str(e)
            logger.warning("[ENGAGEMENT] Action '%s' failed: %s", chosen, e)
            logger.debug(traceback.format_exc())

        return result

    # ------------------------------------------------------------------
    # Action 1: Scroll News Feed
    # ------------------------------------------------------------------

    def _action_scroll_feed(self, max_duration: int):
        """Navigate to News Feed and scroll casually."""
        logger.info("[ENGAGEMENT] Scrolling News Feed...")

        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(random.randint(2000, 4000))

        self._checkpoint_guard()

        # Scroll with casual pauses
        casual_scroll_feed(self.page, duration_seconds=max_duration)

        # Occasionally click "See more" on a random post
        self._maybe_expand_post()

    # ------------------------------------------------------------------
    # Action 2: Watch Reels / Watch Tab
    # ------------------------------------------------------------------

    def _action_watch_reels(self, max_duration: int, keyword: str | None = None):
        """Navigate to Watch/Reels tab and passively consume videos."""
        import re
        if keyword:
            # 70% chance to append a generic content modifier that works across most niches
            if random.random() < 0.7:
                modifiers = [
                    "review", "tips", "hướng dẫn", "chia sẻ", "mẹo", 
                    "kinh nghiệm", "đánh giá", "tổng hợp", "xu hướng",
                    "mới nhất", "phân tích", "thực tế", "chi tiết"
                ]
                enhanced_keyword = f"{keyword} {random.choice(modifiers)}"
            else:
                enhanced_keyword = keyword
            
            logger.info("[ENGAGEMENT] Watching Reels for niche: '%s'", enhanced_keyword)
            import urllib.parse
            q = urllib.parse.quote(enhanced_keyword)
            # Try to search for niche videos
            search_url = f"https://www.facebook.com/search/videos/?q={q}"
            try:
                self.page.goto(search_url, wait_until="domcontentloaded")
                self.page.wait_for_timeout(random.randint(3000, 5000))
                
                # Try to click the first reel/video in the search results
                vids = self.page.locator("a[href*='/reel/'], a[href*='/watch/']").all()
                clicked = False
                for vid in vids:
                    try:
                        href = vid.get_attribute("href", timeout=1000)
                        if href and (re.search(r'/reel/(\d+)', href) or re.search(r'v=(\d+)', href)):
                            if href.startswith("/"):
                                href = "https://www.facebook.com" + href
                            self.interacted_urls.add(href.split("&")[0])
                            stealth_click(self.page, vid)
                            self.page.wait_for_timeout(random.randint(3000, 5000))
                            clicked = True
                            break
                    except Exception:
                        continue
                
                if not clicked:
                    logger.warning("[ENGAGEMENT] Search page had no specific video links.")
            except Exception:
                pass
        else:
            logger.info("[ENGAGEMENT] Watching random Reels...")
            # Try Reels first, fall back to Watch
            for url in ["https://www.facebook.com/reel", "https://www.facebook.com/watch"]:
                try:
                    self.page.goto(url, wait_until="domcontentloaded")
                    self.page.wait_for_timeout(random.randint(3000, 5000))
                    break
                except Exception:
                    continue

        self._checkpoint_guard()

        deadline = time.time() + max_duration
        videos_watched = 0

        while time.time() < deadline:
            # Record current URL if it actually contains an ID
            current_url = self.page.url
            if re.search(r'/reel/(\d+)', current_url) or re.search(r'v=(\d+)', current_url):
                clean_url = current_url.split("&")[0]
                self.interacted_urls.add(clean_url)

            # "Watch" a video for 15-45 seconds
            watch_time = random.randint(15, 45)
            remaining = deadline - time.time()
            actual_wait = min(watch_time, max(1, int(remaining)))
            self.page.wait_for_timeout(actual_wait * 1000)

            videos_watched += 1
            logger.info("[ENGAGEMENT] Watched video %d (~%ds)", videos_watched, actual_wait)

            if time.time() >= deadline:
                break

            # Scroll to next video
            human_scroll(self.page, direction="down")
            self.page.wait_for_timeout(random.randint(500, 1500))

            # Attempt to scrape view count of current video
            self._try_scraping_current_view()

            # Checkpoint guard between videos
            self._checkpoint_guard()

        logger.info("[ENGAGEMENT] Finished watching %d videos.", videos_watched)

    # ------------------------------------------------------------------
    # Action 3: Search & Explore Topic (Targeted Engagement)
    # ------------------------------------------------------------------

    def _action_search_topic(self, keyword: str, max_duration: int):
        """
        Search for a niche keyword on Facebook and browse the results.
        This builds topic affinity in the account's profile.
        """
        # 70% chance to append a generic content modifier that works across most niches
        if random.random() < 0.7:
            modifiers = [
                "review", "tips", "hướng dẫn", "chia sẻ", "mẹo", 
                "kinh nghiệm", "đánh giá", "tổng hợp", "xu hướng",
                "mới nhất", "phân tích", "thực tế", "chi tiết"
            ]
            enhanced_keyword = f"{keyword} {random.choice(modifiers)}"
        else:
            enhanced_keyword = keyword
            
        logger.info("[ENGAGEMENT] Searching topic: '%s'", enhanced_keyword)

        # Navigate to Facebook home first
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        self.page.wait_for_timeout(random.randint(2000, 3000))

        self._checkpoint_guard()

        # Use the human_search helper to type & submit the query
        human_search(self.page, enhanced_keyword)
        self.page.wait_for_timeout(random.randint(2000, 4000))

        # Try to click on "Posts" / "Bài viết" tab to see relevant content
        tabs_to_try = [
            "Bài viết",
            "Posts",
            "Hội nhóm",
            "Groups",
            "Video",
        ]
        tab_clicked = False
        for tab_name in tabs_to_try:
            try:
                tab_loc = self.page.get_by_role("tab", name=tab_name).first
                if tab_loc.count() == 0:
                    tab_loc = self.page.locator(f"a:has-text('{tab_name}')").first
                if tab_loc.count() > 0 and tab_loc.is_visible():
                    stealth_click(self.page, tab_loc)
                    self.page.wait_for_timeout(random.randint(2000, 3000))
                    tab_clicked = True
                    logger.info("[ENGAGEMENT] Clicked tab: %s", tab_name)
                    break
            except Exception:
                continue

        if not tab_clicked:
            logger.info("[ENGAGEMENT] No specific tab found, browsing default search results.")

        # Record URL we are browsing
        self.interacted_urls.add(self.page.url.split("&")[0])

        # Now scroll through the results casually
        casual_scroll_feed(self.page, duration_seconds=max_duration)

    # ------------------------------------------------------------------
    # Action 4: Spy on Competitor (Clone Niche)
    # ------------------------------------------------------------------

    def _action_spy_competitor(self, target_url: str, max_duration: int):
        """
        Visit a competitor's Page, Profile, or Group and passively consume content.
        This builds affinity with the audience of that specific entity.
        """
        logger.info("[ENGAGEMENT] Spying on competitor: '%s'", target_url)

        try:
            # Ensure URL is absolute
            if not target_url.startswith("http"):
                target_url = "https://" + target_url
                
            self.page.goto(target_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(random.randint(3000, 5000))
        except Exception as e:
            logger.warning("[ENGAGEMENT] Failed to visit competitor URL %s: %s", target_url, e)
            return

        self._checkpoint_guard()
        self.interacted_urls.add(self.page.url.split("?")[0])

        deadline = time.time() + max_duration

        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
                
            # Randomly click "Comments" to simulate reading them
            if random.random() < 0.2:
                try:
                    comments = self.page.locator(
                        'div[role="button"]:has-text("bình luận"), '
                        'div[role="button"]:has-text("comments"), '
                        'div[role="button"]:has-text("Bình luận"), '
                        'div[role="button"]:has-text("Comments")'
                    ).all()
                    if comments:
                        target_comment = random.choice(comments[:3])
                        stealth_click(self.page, target_comment)
                        self.page.wait_for_timeout(random.randint(3000, 6000))
                        logger.info("[ENGAGEMENT] Expanded post comments to read.")
                except Exception:
                    pass

            # Randomly click a picture or video on their page
            if random.random() < 0.15:
                try:
                    media_links = self.page.locator('a[href*="/photos/"], a[href*="/videos/"]').all()
                    if media_links:
                        media = random.choice(media_links[:5])
                        media_href = media.get_attribute("href")
                        if media_href:
                            self.interacted_urls.add(media_href.split("?")[0])
                        stealth_click(self.page, media)
                        self.page.wait_for_timeout(random.randint(5000, 10000))
                        
                        # Use escape to close modal if it opened as overlay
                        self.page.keyboard.press("Escape")
                        self.page.wait_for_timeout(random.randint(1000, 2000))
                        logger.info("[ENGAGEMENT] Clicked competitor media and closed it.")
                except Exception:
                    pass

            self._maybe_expand_post()

            # Attempt to scrape viral posts while scrolling competitor
            self._try_scraping_current_view()

            human_scroll(self.page, direction="down")
            
            # Wait a few seconds to simulate reading
            wait_time = random.randint(3, 8)
            actual_wait = min(wait_time, max(1, int(deadline - time.time())))
            self.page.wait_for_timeout(actual_wait * 1000)

            self._checkpoint_guard()

        logger.info("[ENGAGEMENT] Finished visiting competitor page.")

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _checkpoint_guard(self):
        """Raise _CheckpointDetected if the page looks like a login screen."""
        if _is_checkpointed(self.page):
            raise _CheckpointDetected()

    def _maybe_expand_post(self):
        """Randomly click a 'See more' / 'Xem thêm' button (simulates reading)."""
        if random.random() > 0.3:
            return  # 70% of the time, skip

        try:
            see_more = self.page.locator(
                'div[role="button"]:has-text("See more"), '
                'div[role="button"]:has-text("Xem thêm")'
            ).all()
            if see_more:
                target = random.choice(see_more[:3])

                # Try to capture post URL before click
                try:
                    box = target.locator("xpath=ancestor::div[@data-ad-comet-preview='message'] | ancestor::div[contains(@class, 'x1y1aw1k')]").first
                    if box:
                        post_link = box.locator("a[href*='/posts/'], a[href*='/permalink/'], a[href*='/videos/']").first
                        if post_link.count() > 0:
                            href = post_link.get_attribute("href")
                            if href:
                                if href.startswith("/"): href = "https://www.facebook.com" + href
                                self.interacted_urls.add(href.split("?")[0])
                except Exception:
                    pass

                stealth_click(self.page, target)
                self.page.wait_for_timeout(random.randint(2000, 5000))
                logger.info("[ENGAGEMENT] Expanded a 'See more' post.")
        except Exception:
            pass  # Non-critical

    def _try_scraping_current_view(self):
        """Passively detect if current page/post being viewed has high interaction/views.
        
        Enhanced to handle Vietnamese locale formats:
          - "1,5 Tr lượt xem"  (comma decimal, suffix, label)
          - "120K views"        (English)
          - aria-label="150 N lượt xem"
        """
        current_url = self.page.url.split("?")[0].split("&")[0]
        if current_url in self._already_scraped_urls:
            return
            
        is_video = "/reel/" in current_url or "/videos/" in current_url or "v=" in current_url
        if not is_video:
            return
            
        try:
            import re
            
            # Pattern matching "1.5M", "120K", "5 Tr", "150 N", "1,5 Tr lượt xem" etc.
            pattern = r'([\d\.,]+)\s*(K|M|B|Tr|N|k|m|b|tr|n)\b'
            
            # Use javascript evaluation to find text from both innerText AND aria-label
            texts = self.page.evaluate(r'''() => {
                const elements = document.querySelectorAll('span, div');
                const results = new Set();
                for(let el of elements) {
                    // Check innerText
                    const t = (el.innerText || "").trim();
                    if(t.length > 0 && t.length < 30 && t.match(/[\d\.,]+\s*[KMBTrNkmb]/i)) {
                        results.add(t);
                    }
                    // Check aria-label (Facebook often hides real counts here)
                    const aria = (el.getAttribute("aria-label") || "").trim();
                    if(aria.length > 0 && aria.length < 50 && aria.match(/[\d\.,]+\s*[KMBTrNkmb]/i)) {
                        results.add(aria);
                    }
                }
                return Array.from(results);
            }''')
            
            # Extract video URL since facebook.com/reel doesn't have ID in address bar
            html = self.page.content()
            url_pattern = r'(https:[\\/]+www\.facebook\.com[\\/]+reel[\\/]+\d+)'
            url_matches = re.findall(url_pattern, html)
            actual_url = current_url
            if url_matches:
                # Get the most recently found valid URL that we haven't scraped yet
                for match in reversed(url_matches):
                    clean_match = match.replace('\\/', '/')
                    if clean_match not in self._already_scraped_urls:
                        actual_url = clean_match
                        break

            if actual_url in self._already_scraped_urls:
                return
            
            for text in texts:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Handle both "1.5" and "1,5" (Vietnamese uses comma as decimal)
                    num_str = match.group(1).replace(',', '.').strip()
                    # Handle edge case: "1.500" (thousands separator) vs "1.5" (decimal)
                    # If there are multiple dots, treat all but last as thousands separators
                    parts = num_str.split('.')
                    if len(parts) > 2:
                        # e.g. "1.500.000" → "1500000"
                        num_str = ''.join(parts)
                    
                    multiplier = match.group(2)
                    
                    try:
                        base_val = float(num_str)
                        if multiplier:
                            m = multiplier.upper()
                            if m in ['K', 'N']: # Ngàn / Kilo
                                base_val *= 1000
                            elif m in ['M', 'TR']: # Triệu / Mega
                                base_val *= 1000000
                            elif m == 'B': # Tỷ / Billion
                                base_val *= 1000000000
                                
                        views = int(base_val)
                        if views >= 10000: # Threshold for "Viral" (10K+)
                            title = self.page.title()
                            self.scraped_materials.append({
                                "url": actual_url,
                                "views": views,
                                "title": title
                            })
                            self._already_scraped_urls.add(actual_url)
                            logger.info("[SCRAPER] Found VIRAL content: %s views at %s", views, actual_url)
                            break
                    except ValueError:
                        pass
        except Exception:
            pass # Silent fail to not interrupt engagement


class _CheckpointDetected(Exception):
    """Internal signal: account is checkpointed/logged out."""
    pass


# ------------------------------------------------------------------
# Utility: parse niche_topics JSON from Account model
# ------------------------------------------------------------------

def parse_niche_topics(raw: str | None) -> list[str]:
    """
    Parse the niche_topics column value into a list of keyword strings.
    Supports JSON array string or comma-separated fallback.

    Examples:
        '["thời trang","decor"]' → ["thời trang", "decor"]
        'thời trang, decor'     → ["thời trang", "decor"]
        None                    → []
    """
    if not raw:
        return []

    raw = raw.strip()

    # Try JSON first
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: comma-separated
    return [k.strip() for k in raw.split(",") if k.strip()]
