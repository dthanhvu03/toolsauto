import logging
import time
import os
from pathlib import Path
import random
import re
from urllib.parse import urlparse
import traceback
from typing import Any
from app.config import BASE_DIR, SAFE_MODE, LOGS_DIR, DATA_DIR, FACEBOOK_HOST
from playwright.sync_api import Playwright, BrowserContext, Page, Locator, TimeoutError
from app.adapters.contracts import AdapterInterface, PublishResult
from app.database.models import Job
from app.utils.human_behavior import human_type, human_scroll, pre_post_delay
import json
import unicodedata
from collections import deque
from app.adapters.facebook.selectors import SELECTORS
from app.adapters.facebook.core.session import FacebookSessionManager
from app.adapters.facebook.pages.reels import FacebookReelsPage

logger = logging.getLogger(__name__)
from app.services.runtime_events import emit as rt_emit
from app.services.job_tracer import update_active_node
from app.services.notifier_service import NotifierService

_FB_HOST_NETLOC = urlparse(FACEBOOK_HOST).netloc.lower()
_FB_HOST_NETLOCS = {
    _FB_HOST_NETLOC,
    _FB_HOST_NETLOC[4:] if _FB_HOST_NETLOC.startswith("www.") else _FB_HOST_NETLOC,
}


class JobLoggerAdapter(logging.LoggerAdapter):
    """Automatically prepends [Job ID] to every log message."""
    def process(self, msg, kwargs):
        job_id = self.extra.get('job_id', 'Unknown')
        return f"[Job {job_id}] {msg}", kwargs


class PageMismatchError(Exception):
    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Page mismatch: expected={expected}, actual={actual}")

class FacebookAdapter(AdapterInterface):
    """
    Scaffolding for the Facebook playright adapter.
    """
    def __init__(self):
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.logger: logging.Logger = logger
        
    def open_session(self, profile_path: str) -> bool:
        if self.playwright or self.context or self.page:
            self.logger.warning("FacebookAdapter: Session already open, closing previous before opening new one.")
            self.close_session()

        self.logger.info("FacebookAdapter: Opening persistent context at profile: %s", profile_path)
        bundle = FacebookSessionManager.launch_persistent(profile_path)
        if not bundle:
            self.close_session()
            return False
        self.playwright, self.context, self.page = bundle
        return True

    def _is_session_alive(self) -> bool:
        """Check if the Playwright page/context is still alive before using it."""
        if not self.page or not self.context:
            return False
        try:
            # Accessing page.url will throw if the page/context/browser is closed
            _ = self.page.url
            return True
        except Exception:
            return False

    def _try_recover_session(self, profile_path: str) -> bool:
        """Attempt to close dead session and relaunch a fresh one."""
        self.logger.warning("FacebookAdapter: Session is dead. Attempting recovery...")
        self.close_session()
        return self.open_session(profile_path)

    _REEL_ID_RE = re.compile(r"/reel/([a-zA-Z0-9_-]+)", re.IGNORECASE)
    _SHARE_RE = re.compile(r"/share/[rv]/([a-zA-Z0-9_-]+)", re.IGNORECASE)

    def _normalize_post_url(self, url: str | None) -> str | None:
        """Return a stable, valid FB post URL (prefer reel with id), else None."""
        if not url:
            return None
        u = str(url).strip()
        if not u:
            return None
        # make absolute
        if u.startswith("/"):
            u = f"{FACEBOOK_HOST}{u}"
        # drop query/fragments
        u = u.split("#")[0].split("?")[0].rstrip("/")
        # reject ambiguous reel root (e.g. /reel root without specific post id)
        if u.endswith("/reel") or u.endswith("/reel/"):
            return None
        # accept reel with numeric or alphanumeric id
        if self._REEL_ID_RE.search(u):
            return u
        # accept share links
        if self._SHARE_RE.search(u):
            return u
        # accept videos/posts if they look non-trivial
        if ("/videos/" in u or "/posts/" in u) and len(u) > 30:
            return u
        return None

    def _build_publish_details(self, flow_mode: str, entrypoint_used: str | None, **extra: Any) -> dict[str, Any]:
        details: dict[str, Any] = {
            "flow_mode": flow_mode,
            "entrypoint_used": entrypoint_used,
        }
        details.update(extra)
        return details

    def _scan_reels_for_new_post(
        self,
        reels: FacebookReelsPage,
        target_page_url: str | None,
        pre_existing_reels: list[str],
        salt: str | None,
        *,
        attempt: int = 0,
    ) -> str | None:
        if not self.page:
            return None

        # A. Direct Reels Tab (fastest path)
        if reels.navigate_to_reels_tab(target_page_url):
            found_href = self.page.evaluate("""
                ([salt, pre_reels]) => {
                    const links = document.querySelectorAll('a[href*="/reel/"], a[href*="/share/r/"], a[href*="/share/v/"]');
                    // Priority 1: Salt in ancestor
                    for (const a of links) {
                        let el = a;
                        for (let i = 0; i < 15 && el; i++) {
                            if (el.textContent && el.textContent.indexOf(salt) >= 0) {
                                return a.getAttribute('href');
                            }
                            el = el.parentElement;
                        }
                    }
                    // Priority 2: Newest item not in pre_reels
                    if (!salt && links.length > 0) {
                        const firstHref = links[0].getAttribute('href');
                        if (firstHref && !pre_reels.includes(firstHref)) return firstHref;
                    }
                    return null;
                }
            """, [salt, pre_existing_reels])

            if found_href:
                post_url = self._normalize_post_url(found_href)
                if post_url:
                    self.logger.info("FacebookAdapter: Post URL captured via Reels tab scan: %s", post_url)
                    return post_url

        # B. Deep-dive only on later attempts
        if attempt >= 1 and salt:
            self.logger.info("FacebookAdapter: Deep-diving into latest reels to find salt...")
            latest_links = self.page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href*="/reel/"]'))
                    .map(a => a.getAttribute('href'))
                    .slice(0, 5)
            """) or []

            for href in latest_links:
                if not href:
                    continue
                try:
                    full_u = href if href.startswith("http") else f"{FACEBOOK_HOST}{href}"
                    self.page.goto(full_u, wait_until="commit", timeout=10000)
                    self.page.wait_for_timeout(3000)
                    if salt in (self.page.evaluate("document.body.innerText") or ""):
                        post_url = self._normalize_post_url(full_u)
                        if post_url:
                            return post_url
                except Exception:
                    continue

        return None

    def _capture_failure_artifacts(self, job_id: int, stage: str) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        if not self.page:
            return artifacts

        safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage).strip("_") or "unknown"
        artifact_dir = Path(LOGS_DIR) / "fb"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        base_path = artifact_dir / f"job_{job_id}_{safe_stage}"

        screenshot_path = base_path.with_suffix(".png")
        html_path = base_path.with_suffix(".html")

        try:
            self.page.screenshot(path=str(screenshot_path), full_page=False)
            artifacts["screenshot"] = str(screenshot_path)
        except Exception as e:
            self.logger.warning("FacebookAdapter: Failed to save screenshot artifact: %s", e)

        try:
            html_path.write_text(self.page.content(), encoding="utf-8")
            artifacts["html"] = str(html_path)
        except Exception as e:
            self.logger.warning("FacebookAdapter: Failed to save HTML artifact: %s", e)

        return artifacts

    def _failure_result(
        self,
        job_id: int,
        stage: str,
        error: str,
        flow_mode: str,
        entrypoint_used: str | None,
        *,
        is_fatal: bool = False,
        extra_details: dict[str, Any] | None = None,
    ) -> PublishResult:
        artifacts = self._capture_failure_artifacts(job_id, stage)
        details = self._build_publish_details(
            flow_mode,
            entrypoint_used,
            failed_stage=stage,
            artifacts=artifacts,
        )
        if extra_details:
            details.update(extra_details)
        return PublishResult(
            ok=False,
            error=error,
            is_fatal=is_fatal,
            details=details,
            artifacts=artifacts,
        )

    def _is_visible(self, locator: Locator | None) -> bool:
        if locator is None:
            return False
        try:
            return locator.count() > 0 and locator.is_visible()
        except Exception:
            return False

    def _find_first_visible(self, locators: list[Locator]) -> Locator | None:
        for locator in locators:
            if self._is_visible(locator):
                return locator
        return None

    def _get_dynamic_selectors(self, category: str, key: str, fallback_static: str) -> list[str]:
        """Fetch DB selectors first, mix with static fallback."""
        from app.services.workflow_registry import WorkflowRegistry
        db_selectors = []
        try:
            db_selectors = WorkflowRegistry.get_selector_values("facebook", f"{category}:{key}")
        except Exception as e:
            self.logger.warning("FacebookAdapter: [n8n-lite] Error fetching DB selectors for %s:%s - %s", category, key, e)
            
        fallback_list = [s.strip() for s in fallback_static.split(",") if s.strip()]
        
        combined = []
        for sel in db_selectors:
            if sel not in combined: combined.append(sel)
        for sel in fallback_list:
            if sel not in combined: combined.append(sel)
            
        source = "db" if db_selectors else "static_fallback"
        self._last_selector_meta = (category, key, source)
        rt_emit("selector_resolved", platform="facebook",
                category=category, selector_key=key,
                source=source, db_count=len(db_selectors),
                static_count=len(fallback_list), total=len(combined))
        return combined

    def _wait_and_locate_array(self, selectors: list[str]) -> Locator | None:
        """Evaluate array of selectors and return first visible locator"""
        if not self.page: return None
        for idx, sel in enumerate(selectors):
            loc = self.page.locator(sel)
            if self._is_visible(loc.first):
                self._report_selector_outcome(True, idx, len(selectors))
                return loc.first
            if self._is_visible(loc.last):
                self._report_selector_outcome(True, idx, len(selectors))
                return loc.last
        self._report_selector_outcome(False, None, len(selectors))
        return None

    def _report_selector_outcome(self, matched: bool, idx: int | None, total: int) -> None:
        """Report selector match outcome using stashed metadata from _get_dynamic_selectors."""
        meta = getattr(self, "_last_selector_meta", None)
        if not meta:
            return
        from app.services.runtime_events import record_selector_outcome
        record_selector_outcome(meta[0], meta[1], meta[2],
                                matched=matched, matched_index=idx,
                                total_tried=total)

    def _get_dynamic_timing(self, key: str, default: int) -> int:
        from app.services.workflow_registry import WorkflowRegistry
        val = default
        try:
            val = WorkflowRegistry.get_timing("facebook", "POST", key, default)
            source = "db" if val != default else "default"
            rt_emit("timing_resolved", platform="facebook",
                    timing_key=key, value_ms=int(val), source=source,
                    default_ms=default)
        except Exception as e:
            self.logger.warning("FacebookAdapter: [n8n-lite] Error fetching DB timing for %s - %s", key, e)
        return int(val)

    def _click_locator(self, locator: Locator, description: str, timeout: int = 5000) -> bool:
        try:
            locator.scroll_into_view_if_needed()
        except Exception as e:
            self.logger.warning("FacebookAdapter: Swallowed exception at line 219: %s", e)

        try:
            locator.click(timeout=timeout)
            self.logger.info("FacebookAdapter: Clicked %s", description)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Standard click failed for %s: %s", description, e)

        try:
            locator.evaluate("el => el.click()")
            self.logger.info("FacebookAdapter: JS-clicked %s", description)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: JS click failed for %s: %s", description, e)

        try:
            locator.click(force=True, timeout=timeout)
            self.logger.info("FacebookAdapter: Force-clicked %s", description)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Force click failed for %s: %s", description, e)
            return False

    def _normalize_fb_text(self, text: str) -> str:
        """Standardize Vietnamese and case for reliable matching (NFD, lowercase, d/đ)."""
        if not text:
            return ""
        # Normalize to NFD and strip marks (accents), but keep 'd' vs 'đ' mapping if desirable.
        # Here we just do a simple NFD + lower to fix combined vs decomposed characters.
        n = unicodedata.normalize("NFD", text).lower().strip()
        # Common Vietnamese 'đ' handling if we want to be very broad
        n = n.replace("đ", "d").replace("Đ", "d")
        return n

    def _ensure_authenticated_context(self) -> bool:
        """Checks for 'Continue as' barriers and bypasses them to return to a standard nav context."""
        if not self.page:
            return False
            
        # 1. If navigation is already present, we are likely fine
        # We check for several common nav markers to be sure
        nav_present = self.page.locator('div[role="navigation"], div[role="banner"], a[aria-label="Facebook"]').count() > 0
        if nav_present:
            return True
            
        # 2. Check for 'Continue as' / 'Tiếp tục'
        # We try both exact and non-exact, and different roles.
        self.logger.info("FacebookAdapter: Navigation missing, checking for session recovery screen...")
        recovery_btn = None
        
        # [n8n-lite Phase 1]: Dynamic Session Recovery Button
        dyn_selectors = self._get_dynamic_selectors("recovery", "session_recovery_button", 'div[role="button"]:has-text("Tiếp tục"), div[role="button"]:has-text("Continue")')
        recovery_btn = self._wait_and_locate_array(dyn_selectors)
        
        if not recovery_btn:
            # Priority: Exact match role=button or text
            # Fallback: Non-exact match anything clickable
            search_terms = ["Tiếp tục", "Continue", "Log In", "Đăng nhập"]
        
        for term in search_terms:
            # Try specific roles first
            for role in ["button", "link"]:
                loc = self.page.get_by_role(role, name=term, exact=False).first
                if self._is_visible(loc):
                    recovery_btn = loc
                    break
            if recovery_btn: break
            
            # Try generic text
            loc = self.page.get_by_text(term, exact=False).first
            if self._is_visible(loc):
                recovery_btn = loc
                break
            if recovery_btn: break

        # Extra fallback: Find the dominant blue button if we see the account name (Hoang Khoa)
        if not recovery_btn:
            # Look for elements that LOOK like the blue continue button from the screenshot
            blue_btn = self.page.locator('div[role="button"]:has-text("Tiếp tục"), div[role="button"][style*="background-color"]')
            if self._is_visible(blue_btn.first):
                return self._click_locator(blue_btn.first, "blue continue button")
        
        return False

    def _verify_page_identity(self, expected_target: str, context: str = "pre-post") -> None:
        """
        Verify the current browser state matches the intended target page.
        Raises PageMismatchError if identity cannot be confirmed.
        """
        if not self.page or not expected_target:
            return

        actual_url = self.page.url
        
        # 1. URL Substring check (Slug or ID)
        identifier = ""
        if "id=" in expected_target:
            # Handle profile.php?id=123
            match = re.search(r"id=(\d+)", expected_target)
            if match:
                identifier = match.group(1)
        else:
            # Handle facebook.com/SlugName
            parts = expected_target.rstrip("/").split("/")
            if parts:
                identifier = parts[-1].split("?")[0]

        if identifier and identifier in actual_url:
            self.logger.debug("FacebookAdapter: [Identity] URL verification passed for '%s' (%s)", identifier, context)
            return

        # 2. Page Title / Header check (Fallback)
        try:
            page_title = self.page.title()
            # If slug is in title (common for pages)
            if identifier.lower() in page_title.lower():
                 self.logger.debug("FacebookAdapter: [Identity] Title verification passed for '%s' (%s)", identifier, context)
                 return
        except Exception:
            pass

        # If we reach here, identity is suspicious
        self.logger.error("FacebookAdapter: [Identity] Verification FAILED for '%s'. Actual URL: %s", expected_target, actual_url)
        raise PageMismatchError(expected_target, actual_url)


    def _switch_to_personal_profile(self, account_name: str) -> bool:
        """
        Forces the browser context to switch back to the personal profile matching account_name.
        This prevents the system from being stuck in a Fanpage context from a previous job.
        """
        if not self.page:
            return False

        try:
            # 0. Ensure we are in an authenticated context (bypass Continue as)
            self._ensure_authenticated_context()

            # 1. Open the top right account menu
            account_dyn = self._get_dynamic_selectors("switch_menu", "account_menu_button", SELECTORS["switch_menu"]["account_menu_button"])
            account_menu_btn = self._wait_and_locate_array(account_dyn)
            if not account_menu_btn:
                self.logger.warning("FacebookAdapter: Account menu button not visible.")
                return False

            self._click_locator(account_menu_btn, "account menu", timeout=5000)
            self.page.wait_for_timeout(2000)

            # 2. Click "Xem tất cả trang cá nhân" (See all profiles)
            see_all = self._find_first_visible([
                self.page.locator('text=Xem tất cả trang cá nhân'),
                self.page.locator('text=See all profiles'),
                self.page.locator('span[dir="auto"]:has-text("Xem tất cả trang cá nhân")')
            ])
            if see_all:
                if not self._activate_profile_switcher_row(see_all, "see all profiles"):
                    self._click_locator(account_menu_btn, "account menu", timeout=5000)
                    self.page.wait_for_timeout(1500)
                    see_all = self._find_first_visible([
                        self.page.locator('text=Xem tất cả trang cá nhân'),
                        self.page.locator('text=See all profiles'),
                        self.page.locator('span[dir="auto"]:has-text("Xem tất cả trang cá nhân")'),
                    ])
                    if see_all:
                        self._activate_profile_switcher_row(see_all, "see all profiles (retry)")
                self.page.wait_for_timeout(2000)
            
            # 3. Look for the exact personal profile name (accent-insensitive)
            target_name = self._normalize_fb_text(account_name)
            # Find all possible profile items across the DOM (popups often render outside the main tree)
            profile_items = self.page.locator('div[role="button"], div[role="menuitem"], div[role="radio"], div[role="menuitemradio"]').all()
            
            found_el = None
            for el in profile_items:
                try:
                    text = el.inner_text().strip()
                    if text and len(text) > 3:
                        if target_name in self._normalize_fb_text(text):
                            found_el = el
                            break
                except Exception as e:
                    self.logger.warning("FacebookAdapter: Swallowed exception at line 369: %s", e)

            if found_el:
                self.logger.debug("FacebookAdapter: Found personal profile '%s' in switcher. Clicking...", account_name)
                # Find the closest clickable container
                clickable = found_el.locator("xpath=ancestor::div[@role='button' or @role='menuitemradio' or @role='radio' or @role='menuitem']").first
                if self._is_visible(clickable):
                    self._click_locator(clickable, f"profile {account_name}", timeout=5000)
                else:
                    self._click_locator(found_el, f"profile {account_name}", timeout=5000)
                
                self.page.wait_for_timeout(5000) # Wait for page reload context switch
                return True
            else:
                self.logger.debug("FacebookAdapter: Personal profile '%s' not explicitly found in switcher. Might already be active.", account_name)
                # Close the menu if we opened it by clicking off banner
                try:
                    self.page.keyboard.press("Escape")
                except:
                    self.logger.warning("FacebookAdapter: Swallowed unknown exception at line 388")
                
        except Exception as e:
            self.logger.warning("FacebookAdapter: Failed during profile switch attempt: %s", e)
            
        return False

    def publish(self, job: Job) -> PublishResult:
        self.logger = JobLoggerAdapter(logger, {'job_id': job.id})
        self.logger.info("FacebookAdapter: Attempting to publish job %s", job.id)

        if not self.page:
            return PublishResult(ok=False, error="Playwright page is not initialized.", is_fatal=True)

        # Bug #2 fix: Detect dead browser session early before attempting navigation
        if not self._is_session_alive():
            self.logger.error("FacebookAdapter: Browser session is dead (page/context closed). Cannot publish.")
            return PublishResult(
                ok=False,
                error="Browser session is dead (page/context closed). Will retry with fresh session.",
                is_fatal=False,
            )

        target_page_url = (getattr(job, "target_page", None) or "").strip() or None
        is_page_post = bool(target_page_url)
        flow_mode = "page" if is_page_post else "personal"
        entrypoint_used: str | None = None
        
        # ── INITIALIZE GRAPHQL CAPTURE (Phase C) ──
        captured_post_ids = []
        captured_graphql_events = []

        def intercept_graphql(response):
            if "/api/graphql/" in response.url:
                try:
                    req_post = response.request.post_data or ""
                    # Mutations we care about for publishing
                    mutations = [
                        "ComposerStoryCreateMutation",
                        "VideoPublishMutation",
                        "ReelCreateMutation",
                        "useReelCreationMutation",
                        "CometVideoUploadMutation",
                    ]
                    if any(m in req_post for m in mutations):
                        body = response.json()
                        captured_graphql_events.append({
                            "ts": time.time(),
                            "status": response.status,
                            "mutation": next((m for m in mutations if m in req_post), "unknown"),
                        })
                        
                        data = body.get("data", {})
                        # Try to extract IDs from all common response structures
                        for key in ("story_create", "video_publish", "reel_create", "video_upload", "composer_story_create"):
                            res = data.get(key, {})
                            if isinstance(res, dict):
                                p_id = res.get("post_id") or res.get("video_id") or res.get("id")
                                if p_id:
                                    self.logger.info("FacebookAdapter: [GRAPHQL] Bắt được ID từ %s: %s", key, p_id)
                                    captured_post_ids.append(str(p_id))
                                    break
                        
                        # Errors
                        if body.get("errors"):
                            self.logger.warning("FacebookAdapter: [GRAPHQL] Server-side error payload: %s", body.get("errors")[:1])
                except Exception:
                    pass

        self.page.on("response", intercept_graphql)

        try:
            # Check for account access
            if not getattr(job, "account", None):
                # We need the account loaded to get the real name for context switching
                with SessionLocal() as db:
                    db.add(job)
                    job.account  # Trigger lazy load
        except Exception as e:
            self.logger.warning("FacebookAdapter: Could not load job account: %s", e)

        try:
            # 1. Navigation & Page Context Switch
            update_active_node(job.id, "switch_profile")
            if target_page_url:
                target_page_name = None
                if job.account and getattr(job.account, 'managed_pages_list', None):
                    for p in job.account.managed_pages_list:
                        p_url = p.get("url", "")
                        if p_url and (p_url in target_page_url or target_page_url in p_url):
                            target_page_name = p.get("name")
                            break
                        if "?id=" in target_page_url and "?id=" in p_url:
                            if target_page_url.split("?id=")[1].split("&")[0] == p_url.split("?id=")[1].split("&")[0]:
                                target_page_name = p.get("name")
                                break
                                
                self.logger.info("FacebookAdapter: Target Page specified. Navigating to %s (Name: %s)", target_page_url, target_page_name)
                if not target_page_url.startswith("http"):
                    target_page_url = "https://" + target_page_url
                self.page.goto(target_page_url, wait_until="domcontentloaded")
                
                active_steps = getattr(job, "active_steps", None)
                if active_steps is not None and "feed_browse" not in active_steps:
                    rt_emit("step_skipped", platform="facebook", step_name="feed_browse",
                            job_id=job.id, reason="not in active_steps")
                else:
                    self.page.wait_for_timeout(self._get_dynamic_timing("feed_browse_pause", 4000))

                switch_dyn = self._get_dynamic_selectors("switch_menu", "switch_now_button", SELECTORS["switch_menu"]["switch_now_button"])
                switch_btn = self._wait_and_locate_array(switch_dyn)
                if switch_btn:
                    self.logger.info("FacebookAdapter: Found 'Switch now' button for the Page. Clicking...")
                    self._click_locator(switch_btn, "page switch button", timeout=10000)
                    self.page.wait_for_timeout(5000)
                    self.logger.info("FacebookAdapter: Switched to Page context successfully.")
                else:
                    self.logger.info("FacebookAdapter: No 'Switch now' button found on the Page. Attempting context switch via avatar menu...")
                    switched = self._switch_to_page_context(
                        target_page_name, target_page_url=target_page_url
                    )
                    if not switched:
                        self.logger.warning("FacebookAdapter: Avatar menu switch failed or unnecessary. Verifying active context...")

                # Reload target page after switch so Facebook applies identity (slow VPS / delayed UI).
                try:
                    self.page.goto(target_page_url, wait_until="domcontentloaded")
                    self.page.wait_for_timeout(5000)
                except Exception as e:
                    self.logger.warning("FacebookAdapter: Post-switch reload of target page failed: %s", e)

                # ── Bulletproof Context Verification ──
                # Ensure we don't accidentally post to the wrong page if the switch failed.
                self.logger.info("FacebookAdapter: Verifying active context matches target page...")
                verified_ok, norm_active, norm_target = (
                    self._verify_posting_context_matches_target(target_page_url or "")
                )

                if not verified_ok:
                    if not norm_active:
                        # /me check threw an exception (browser closed, timeout, etc.)
                        # Cannot verify context → MUST abort to prevent wrong-page post
                        error_msg = "/me check failed — cannot verify context safety. Aborting to prevent wrong-page post."
                        self.logger.error("FacebookAdapter: %s", error_msg)
                        return self._failure_result(
                            job.id,
                            "context_verification_exception",
                            error_msg,
                            flow_mode,
                            entrypoint_used,
                            is_fatal=False
                        )
                    else:
                        # /me resolved but doesn't match target page
                        error_msg = f"Security abort: Active context ({norm_active}) does not match target page ({norm_target}). Preventing wrong-page post."
                        self.logger.error("FacebookAdapter: %s", error_msg)
                        return self._failure_result(
                            job.id,
                            "context_verification",
                            error_msg,
                            flow_mode,
                            entrypoint_used,
                            is_fatal=False
                        )
                else:
                    self.logger.info("FacebookAdapter: Context verified successfully. Safe to proceed.")
                    # Explicit identity verification (Slug/ID check)
                    self._verify_page_identity(target_page_url, context="pre-post")
            else:
                self.logger.info("FacebookAdapter: Navigating to %s (Personal Profile)", FACEBOOK_HOST)
                self.page.goto(f"{FACEBOOK_HOST}/", wait_until="domcontentloaded")
                
                active_steps = getattr(job, "active_steps", None)
                if active_steps is not None and "feed_browse" not in active_steps:
                    rt_emit("step_skipped", platform="facebook", step_name="feed_browse",
                            job_id=job.id, reason="not in active_steps")
                else:
                    self.page.wait_for_timeout(self._get_dynamic_timing("feed_browse_pause", 4000)) # Give React time to render DOM

                # Explicitly switch back to Personal Profile if stuck on a Fanpage
                account_name = job.account.name if job.account else None
                if account_name:
                    self.logger.info("FacebookAdapter: Ensuring context is Personal Profile (%s)...", account_name)
                    # Use the explicit switch helper
                    self._switch_to_personal_profile(account_name)
                else:
                    self.logger.warning("FacebookAdapter: No account name found in job. Cannot explicitly switch to Personal Profile.")

            # 2. Login Check
            login_btn = self.page.locator('button[name="login"]').count() > 0
            email_in = self.page.locator('input[name="email"]').count() > 0
            nav_present = self.page.locator('div[role="navigation"]').count() > 0

            recovery_btn = None
            # Session Recovery: "Continue as XYZ" screen
            if not nav_present and not (login_btn and email_in):
                self.logger.info("FacebookAdapter: Navigation missing, checking for 'Continue as' session recovery screen...")
                
                # [n8n-lite Phase 1]: Dynamic Session Recovery
                dyn_selectors = self._get_dynamic_selectors("recovery", "session_recovery_button", "")
                recovery_btn = self._wait_and_locate_array(dyn_selectors)

                if not recovery_btn:
                    # Use exact text matching to avoid clicking invisible parent divs
                    try:
                        candidates = [
                            self.page.get_by_text("Tiếp tục", exact=True).first,
                            self.page.get_by_text("Continue", exact=True).first,
                            self.page.get_by_role("button", name="Tiếp tục", exact=True).first,
                            self.page.get_by_role("button", name="Continue", exact=True).first,
                            self.page.locator('div[role="button"]:text-is("Tiếp tục")').first,
                            self.page.locator('div[role="button"]:text-is("Continue")').first,
                        ]
                        for candidate in candidates:
                            if self._is_visible(candidate):
                                recovery_btn = candidate
                                break
                                
                    except Exception as e:
                        self.logger.warning("FacebookAdapter: Error during manual session recovery candidate checks: %s", e)

            if recovery_btn:
                self.logger.info("FacebookAdapter: Found 'Continue/Tiếp tục' recovery button. Clicking...")
                # Force click on the exact text node
                try:
                    recovery_btn.click(force=True, timeout=5000)
                except Exception:
                    self._click_locator(recovery_btn, "session recovery button", timeout=5000)
                    
                self.page.wait_for_timeout(8000)
                
                # Sometimes we need to explicitly reload or wait for redirect
                if "login" in self.page.url or "checkpoint" in self.page.url:
                    self.page.goto(f"{FACEBOOK_HOST}/", wait_until="domcontentloaded")
                    self.page.wait_for_timeout(5000)
                    
                # Re-check navigation after clicking
                nav_present = self.page.locator('div[role="navigation"]').count() > 0
                if nav_present:
                    self.logger.info("FacebookAdapter: Session successfully recovered!")
                else:
                    self.logger.warning("FacebookAdapter: Clicked recovery but navigation still missing.")

            if (login_btn and email_in) or not nav_present:
                self.logger.error("FacebookAdapter: Account is logged out or requires verification.")
                return self._failure_result(
                    job.id,
                    "login_check",
                    "Account logged out or checkpointed.",
                    flow_mode,
                    entrypoint_used,
                    is_fatal=True,
                    extra_details={"invalidate_account": True},
                )

            # ── Auto-inject verification salt into caption (adapter-level, never modifies job.caption) ──
            import hashlib as _hashlib
            publish_caption = (job.caption or "").strip()
            publish_salt_match = re.search(r'\[ref:[a-zA-Z0-9]+\]|#v\d{4}', publish_caption)
            if publish_salt_match:
                publish_salt = publish_salt_match.group(0)
                self.logger.debug("FacebookAdapter: Existing salt found in caption: %s", publish_salt)
            else:
                raw = f"{job.id}-{job.account_id}-{getattr(job, 'created_at', job.id)}"
                publish_salt = f"[ref:{_hashlib.sha256(raw.encode()).hexdigest()[:8]}]"
                publish_caption = f"{publish_caption}\n\n{publish_salt}" if publish_caption else publish_salt
                self.logger.debug("FacebookAdapter: Auto-injected verification salt: %s", publish_salt)

            # ── Pre-scan existing reels to detect NEW ones after posting ──
            update_active_node(job.id, "pre_scan")
            pre_existing_reels: list[str] = []
            active_steps = getattr(job, "active_steps", None)
            
            if active_steps is not None and "pre_scan" not in active_steps:
                rt_emit("step_skipped", platform="facebook", step_name="pre_scan",
                        job_id=job.id, reason="not in active_steps")
            else:
                try:
                    if target_page_url:
                        pre_reels_url = target_page_url.rstrip('/') + '/reels_tab' if '?' not in target_page_url else target_page_url + '&sk=reels_tab'
                    else:
                        pre_reels_url = f"{FACEBOOK_HOST}/me/reels_tab"
                    self.page.goto(pre_reels_url, wait_until="domcontentloaded", timeout=15000)
                    self.page.wait_for_timeout(6000)
                    for link in self.page.locator('a').all():
                        try:
                            href = link.get_attribute("href")
                            if href and "/reel/" in href and len(href) > 20:
                                clean = href.split("?")[0]
                                full = clean if clean.startswith("http") else f"{FACEBOOK_HOST}{clean}"
                                if full not in pre_existing_reels:
                                    pre_existing_reels.append(full)
                        except Exception as e:
                            self.logger.warning("FacebookAdapter: Swallowed exception at line 610: %s", e)
                    self.logger.info("FacebookAdapter: Pre-scanned %d existing reels before posting.", len(pre_existing_reels))
                except Exception as e:
                    self.logger.warning("FacebookAdapter: Pre-scan reels failed: %s. Proceeding without.", e)

            # Navigate back to profile/home for composer entry
            if target_page_url:
                self.page.goto(target_page_url, wait_until="domcontentloaded")
            else:
                self.page.goto(f"{FACEBOOK_HOST}/", wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)

            update_active_node(job.id, "feed_browse")
            self.logger.info("FacebookAdapter: Simulating feed browsing before compose...")
            human_scroll(self.page)
            reels = FacebookReelsPage(self.page, self.logger)
            reels.neutralize_overlays()

            self.logger.info("FacebookAdapter: [Phase 1] Bước 1/5: Tìm nơi đăng bài...")
            if is_page_post:
                entrypoint_used = reels.open_page_reels_entry()
                if not entrypoint_used:
                    surface = reels.find_active_publish_surface()
                    reels.log_surface_inventory(surface, "page_entrypoint_missing")
                    return self._failure_result(
                        job.id,
                        "page_entrypoint",
                        "Thước phim/Reels entrypoint not found on Page.",
                        flow_mode,
                        entrypoint_used,
                    )
            else:
                entrypoint_used = reels.open_personal_reels_entry()
                if not entrypoint_used:
                    surface = reels.find_active_publish_surface()
                    reels.log_surface_inventory(surface, "personal_entrypoint_missing")
                    return self._failure_result(
                        job.id,
                        "personal_entrypoint",
                        "Could not open direct Reels entry or composer fallback on personal profile.",
                        flow_mode,
                        entrypoint_used,
                    )

            surface = reels.find_active_publish_surface()
            reels.log_surface_inventory(surface, "entry_opened")

            self.logger.info("FacebookAdapter: [Phase 2] Bước 2/5: Tải video lên từ %s", job.media_path)
            if not os.path.exists(job.media_path):
                return self._failure_result(
                    job.id,
                    "upload_media",
                    f"Media path not found: {job.media_path}",
                    flow_mode,
                    entrypoint_used,
                )

            file_input = reels.select_file_input(surface, job.media_path)
            if not file_input:
                reels.log_surface_inventory(surface, "upload_input_missing")
                return self._failure_result(
                    job.id,
                    "upload_media",
                    "No file input found in the active publish surface.",
                    flow_mode,
                    entrypoint_used,
                )

            try:
                file_input.set_input_files(job.media_path)
                self.logger.info("FacebookAdapter: Media attached. Waiting for preview...")
                self.page.wait_for_timeout(self._get_dynamic_timing("upload_settle_wait", 8000))
            except Exception as e:
                reels.log_surface_inventory(surface, "upload_media_failed")
                return self._failure_result(
                    job.id,
                    "upload_media",
                    f"Media upload failed: {e}",
                    flow_mode,
                    entrypoint_used,
                )

            surface = reels.find_active_publish_surface()
            reels.log_surface_inventory(surface, "after_upload")

            caption_typed = False

            self.logger.info("FacebookAdapter: [Phase 3] Bước 3/5: Nhập nội dung bài viết và chuẩn bị các bước tiếp theo...")
            self.logger.info("FacebookAdapter: [Reels Dialog - Step 1] Chờ nút Tiếp hiện ra rồi click (max 60s chờ video upload)...")
            try:
                next_btn_1_loc = self.page.locator('div[aria-label="Tiếp"], div[aria-label="Next"]').first
                next_btn_1_loc.wait_for(state="visible", timeout=60000)
                next_btn_1_loc.click(timeout=5000, force=True)
                self.logger.info("FacebookAdapter: Đã click nút Tiếp ở Bước 1")
                self.page.wait_for_timeout(2000) # Chờ animation chuyển bước
            except Exception as e:
                self.logger.warning("FacebookAdapter: Lỗi click nút Tiếp ở Bước 1: %s", e)

            self.logger.info("FacebookAdapter: [Reels Dialog - Step 2] Giao diện Chỉnh sửa, click Tiếp...")
            self.page.wait_for_timeout(1000)
            try:
                next_btn_2_loc = self.page.locator('div[aria-label="Tiếp"], div[aria-label="Next"]').first
                next_btn_2_loc.wait_for(state="visible", timeout=30000)
                next_btn_2_loc.click(timeout=5000, force=True)
                self.logger.info("FacebookAdapter: Đã click nút Tiếp ở Bước 2")
                self.page.wait_for_timeout(2000) # Chờ animation chuyển bước
            except Exception as e:
                self.logger.warning("FacebookAdapter: Lỗi click nút Tiếp ở Bước 2: %s", e)

            self.logger.info("FacebookAdapter: [Reels Dialog - Step 3] Giao diện Cài đặt, chuẩn bị điền caption và Đăng...")
            try:
                # Wait for any contenteditable area with fallback selectors (Phase B)
                caption_selectors = [
                    'div[role="textbox"][contenteditable="true"]',
                    'div[contenteditable="true"][data-lexical-editor="true"]',
                    'div[contenteditable="true"][aria-label*="reel" i]',
                    'div[contenteditable="true"][aria-label*="Mô tả" i]',
                    'div[contenteditable="true"][aria-label*="Describe" i]',
                    'div[contenteditable="true"][aria-placeholder]',
                    'div[contenteditable="true"]',
                ]
                found_caption = False
                for sel in caption_selectors:
                    try:
                        self.page.locator(sel).first.wait_for(state="visible", timeout=3000)
                        self.logger.debug("FacebookAdapter: Caption area found via selector: %s", sel)
                        found_caption = True
                        break
                    except:
                        continue
                        
                if not found_caption:
                    self.logger.warning("FacebookAdapter: Chờ khu vực caption quá lâu hoặc không thấy qua list selectors.")
                else:
                    self.logger.info("FacebookAdapter: Đã thấy khu vực nhập caption.")
            except Exception as e:
                self.logger.warning("FacebookAdapter: Exception searching for caption: %s", e)

            surface = reels.find_active_publish_surface()
            caption_typed = reels.fill_caption(surface, publish_caption)
            if not caption_typed and publish_caption.strip():
                self.logger.warning("FacebookAdapter: Caption area not found in final surface. Proceeding without caption.")
            
            # Đợi thêm một chút để Facebook cập nhật trạng thái nút Đăng sau khi nhập liệu
            self.logger.info("FacebookAdapter: Đã nhập xong Caption, đợi 3s để giao diện ổn định...")
            self.page.wait_for_timeout(3000)

            reels.log_surface_inventory(surface, "before_post")
            post_button = reels.find_post_button(surface)
            if not post_button:
                return self._failure_result(
                    job.id,
                    "post_button",
                    "Post button not found in the active publish surface.",
                    flow_mode,
                    entrypoint_used,
                )

            if SAFE_MODE:
                self.logger.info("FacebookAdapter: SAFE_MODE is enabled. Skipping final publish click.")
                return PublishResult(
                    ok=True,
                    external_post_id="safe_mode_dry_run_id",
                    details=self._build_publish_details(
                        flow_mode,
                        entrypoint_used,
                        post_url="safe_mode",
                        msg="Dry run successful",
                    ),
                )


            update_active_node(job.id, "post_content")
            self.logger.info("FacebookAdapter: [Phase 4] Bước 4/5: Đang thực hiện đăng bài lên Facebook...")
            self.logger.info("FacebookAdapter: Waiting for Post button to become enabled...")
            try:
                post_handle = post_button.element_handle()
                if post_handle:
                    self.page.wait_for_function(
                        'el => el.getAttribute("aria-disabled") !== "true"',
                        arg=post_handle,
                        timeout=120000,
                    )
            except Exception as e:
                self.logger.warning("FacebookAdapter: Wait for button enabled timed out or failed: %s", e)

            # ── REMOVED: GraphQL listener moved to start of publish() ──

            self.logger.info("FacebookAdapter: Simulating pre-post hesitation...")
            pre_post_delay(self.page)

            if not self._click_locator(post_button, "post button", timeout=10000):
                return self._failure_result(
                    job.id,
                    "post_click",
                    "Failed to click the Post button.",
                    flow_mode,
                    entrypoint_used,
                )

            self.logger.info("FacebookAdapter: Post button clicked.")

            # ── Screenshot immediately after clicking Post ──
            self._capture_failure_artifacts(job.id, "post_clicked")

            self.logger.info("FacebookAdapter: [Phase 4] Đang đợi tín hiệu GraphQL từ Facebook (tối đa 120s)...")
            deadline = time.time() + 120
            post_id_from_graphql = None
            
            # Fast-track: if we already have it, don't wait
            if captured_post_ids:
                post_id_from_graphql = captured_post_ids[0]
                self.logger.info("FacebookAdapter: GraphQL ID already captured, skipping busy-wait.")
            else:
                while time.time() < deadline:
                    if captured_post_ids:
                        post_id_from_graphql = captured_post_ids[0]
                        break
                    self.page.wait_for_timeout(2000)
                
            try:
                self.page.remove_listener("response", intercept_graphql)
            except Exception:
                pass
                
            submission_status = "success" if post_id_from_graphql else reels.wait_for_post_submission()
            self.logger.info("FacebookAdapter: Trạng thái submission (DOM): %s", submission_status)

            # ── Screenshot after submission wait ──
            self._capture_failure_artifacts(job.id, "after_submission_wait")

            if submission_status == "error":
                return self._failure_result(
                    job.id,
                    "post_submission_error",
                    "Facebook displayed an error after clicking Post. Post likely NOT published.",
                    flow_mode,
                    entrypoint_used,
                )

            # ── Post-publish verification: FAST TRACK ──
            self.logger.info("FacebookAdapter: [Phase 5] Bước 5/5: Kiểm tra và lấy link bài viết vừa đăng...")
            update_active_node(job.id, "post_verify")
            post_url = None
            salt = publish_salt
            
            # 0. The Ultimate Fast-Track: GraphQL ID
            if post_id_from_graphql:
                post_url = f"{FACEBOOK_HOST}/{post_id_from_graphql}"
                self.logger.info("FacebookAdapter: 🎯 [Thành công] Xác minh bài viết qua GraphQL ID: %s", post_url)
            
            # 1. Immediate catch: Success Toast
            if not post_url:
                self.logger.info("FacebookAdapter: [Fast-Track] Kiểm tra thông báo Success Toast...")
                toast_link = reels.find_success_toast_link()
                if toast_link:
                    post_url = self._normalize_post_url(toast_link)
                    if post_url:
                        self.logger.info("FacebookAdapter: 🎯 [Thành công] Lấy URL qua Toast: %s", post_url)

            # 2. Immediate catch: Redirect URL
            if not post_url:
                try:
                    current_url = self.page.url or ""
                    normalized = self._normalize_post_url(current_url)
                    if normalized:
                        post_url = normalized
                        self.logger.info("FacebookAdapter: Post URL captured via current URL redirect: %s", post_url)
                except Exception:
                    pass

            if not post_url:
                self.logger.info("FacebookAdapter: Fast-track immediate capture missed. Starting profiling scan...")
                # Reduce post-click cooldown if we already waited in reels.wait_for_post_submission
                self.page.wait_for_timeout(4000) 

                # Try up to 3 attempts with increasing depth
                for attempt in range(3):
                    if post_url: break
                    
                    self.logger.info("FacebookAdapter: Verification attempt %d/3...", attempt + 1)
                    post_url = self._scan_reels_for_new_post(
                        reels=reels,
                        target_page_url=target_page_url,
                        pre_existing_reels=pre_existing_reels,
                        salt=salt,
                        attempt=attempt,
                    )
                    if post_url:
                        break

                    # C. Profile Refresh (Final fallback)
                    if not post_url and attempt == 2:
                        profile_url = target_page_url if target_page_url else f"{FACEBOOK_HOST}/me"
                        self.logger.info("FacebookAdapter: Final fallback: refreshing main profile %s", profile_url)
                        try:
                            self.page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
                            self.page.wait_for_timeout(5000)
                            # Expand just a bit
                            more = self.page.locator('div[role="button"]:has-text("See more"), div[role="button"]:has-text("Xem thêm")').first
                            if self._is_visible(more): more.click(timeout=2000)
                            
                            # Final JS sweep
                            found_href = self.page.evaluate("""
                                (salt) => {
                                    const links = document.querySelectorAll('a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"]');
                                    for (const a of links) {
                                        let el = a;
                                        for (let i = 0; i < 20 && el; i++) {
                                            if (el.textContent && el.textContent.indexOf(salt) >= 0) {
                                                return a.getAttribute('href');
                                            }
                                            el = el.parentElement;
                                        }
                                    }
                                    return null;
                                }
                            """, salt)
                            if found_href:
                                post_url = self._normalize_post_url(found_href)
                                if post_url:
                                    self.logger.info("FacebookAdapter: Post URL captured via final profile refresh sweep: %s", post_url)
                        except Exception: pass

                    if not post_url and attempt < 2:
                        wait_sec = 8 if attempt == 0 else 15
                        self.logger.info("FacebookAdapter: No new reel found yet. Waiting %ds before retry...", wait_sec)
                        self.page.wait_for_timeout(wait_sec * 1000)

            if not post_url and submission_status == "success":
                self.logger.warning("[Job %s] Post URL not found. Waiting 3 min then retrying scan...", job.id)
                self.page.wait_for_timeout(180_000)
                try:
                    post_url = self._scan_reels_for_new_post(
                        reels=reels,
                        target_page_url=target_page_url,
                        pre_existing_reels=pre_existing_reels,
                        salt=salt,
                        attempt=2,
                    )
                except Exception as e:
                    self.logger.debug("FacebookAdapter: Delayed scan raised error: %s", e)
                if post_url:
                    self.logger.info("[Job %s] Post verified on delayed scan: %s", job.id, post_url)
                else:
                    self.logger.warning("[Job %s] Still unverified after delayed scan.", job.id)

            # ── Final report ──
            if not post_url:
                if submission_status == "success":
                    self.logger.warning("[Job %s] Post URL not found. Submission seemed OK but post is UNVERIFIED.", job.id)
                elif submission_status == "timeout":
                    return self._failure_result(
                        job.id, "post_verification_failed",
                        "Post submission timed out AND post could not be verified. Likely NOT published.",
                        flow_mode, entrypoint_used
                    )
            else:
                self.logger.info("[Job %s] Post verified: %s", job.id, post_url)

            self._capture_failure_artifacts(job.id, "post_verification_final")

            return PublishResult(
                ok=True,
                external_post_id=f"fb_post_{job.id}",
                details=self._build_publish_details(
                    flow_mode,
                    entrypoint_used,
                    post_url=post_url,
                    msg="Post submitted." if post_url else "Post submitted but URL unverified.",
                    verified=bool(post_url),
                ),
            )

        except PageMismatchError as e:
            if getattr(e, "context", "pre-post") == "post-post":
                # Critical alert for post-post mismatch
                alert_msg = (
                    "⛔ WRONG PAGE DETECTED\n"
                    f"Job ID: {job.id}\n"
                    f"Expected: {e.expected}\n"
                    f"Actual URL: {e.actual}\n"
                    "Action: Job marked FAILED, media file preserved\n"
                    "Manual review required."
                )
                try:
                    NotifierService._broadcast(alert_msg)
                except Exception as notify_err:
                    self.logger.error("FacebookAdapter: Failed to send mismatch alert: %s", notify_err)
            raise e

        except Exception as e:
            self.logger.error("FacebookAdapter: Playwright encounter an error during publish: %s", e)
            self.logger.debug(traceback.format_exc())

            if "Timeout" in str(e):
                error_msg = "Playwright Timeout waiting for element or network."
            else:
                error_msg = f"Unexpected Playwright Error: {e}"

            return self._failure_result(
                job.id,
                "unexpected",
                error_msg,
                flow_mode,
                entrypoint_used,
            )
        
    def check_published_state(self, job: Job) -> PublishResult:
        """
        Verify if a post exists on the remote timeline using the deterministic SHA256 salt.
        """
        self.logger.info("FacebookAdapter: Checking timeline for unique footprint of job %s...", job.id)
        
        if not self.page:
            return PublishResult(ok=False, error="Playwright page is not initialized.", is_fatal=True)
            
        # Extract salt from caption if it exists `[ref:salt]` or `#v1234`
        match = re.search(r'\[ref:[a-zA-Z0-9]+\]|#v\d{4}', job.caption)
        if not match:
            self.logger.info("FacebookAdapter: No salt found in caption for idempotency check.")
            return PublishResult(ok=False, error="No salt for idempotency")
            
        salt = match.group(0)
        self.logger.info("FacebookAdapter: Scanning timeline for salt footprint: %s", salt)
        
        try:
            # Navigate to the user's own profile page
            self.page.goto(f"{FACEBOOK_HOST}/me", wait_until="domcontentloaded")
            
            # Wait a few seconds for viewport content or lazy loaders
            self.page.wait_for_timeout(5000)
            
            # Extract all visible text from body
            body_text = self.page.locator("body").inner_text()
            
            if salt in body_text:
                self.logger.info("FacebookAdapter: Footprint %s found on timeline! Attempting to extract post_url...", salt)
                
                post_url = None
                all_links = self.page.locator(
                    'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"], a[href*="/share/r/"], a[href*="/share/v/"]'
                ).all()
                
                for link in all_links:
                    try:
                        parent_text = link.locator("xpath=ancestor::div[contains(@class,'x1yztbdb')]").first.inner_text()
                        if salt in parent_text:
                            href = link.get_attribute("href")
                            post_url = href if href.startswith("http") else f"{FACEBOOK_HOST}{href}"
                            self.logger.info("FacebookAdapter: Recovered post_url via idempotency scan: %s", post_url)
                            break
                    except Exception:
                        continue
                        
                return PublishResult(
                    ok=True,
                    external_post_id=f"fb_post_{job.id}_recovered",
                    details={"msg": f"Recovered via Timeline Scan. Salt: {salt}", "post_url": post_url}
                )
            else:
                self.logger.info("FacebookAdapter: Footprint not found on timeline.")
                return PublishResult(ok=False, error="Footprint not found")
                
        except Exception as e:
            self.logger.error("FacebookAdapter: Playwright error during check_published_state: %s", e)
            return PublishResult(ok=False, error=f"Playwright error: {e}", is_fatal=False)
        
    def close_session(self):
        self.logger.info("FacebookAdapter: Closing browser context securely.")
        
        # Safely shut down all Playwright resources in order
        if self.page:
            try:
                self.page.close()
            except Exception as e:
                self.logger.warning("Failed to close page: %s", e)
            finally:
                self.page = None
                
        if self.context:
            try:
                self.context.close()
            except Exception as e:
                self.logger.warning("Failed to close context: %s", e)
            finally:
                self.context = None
                
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                self.logger.warning("Failed to stop playwright engine: %s", e)
            finally:
                self.playwright = None

    # ─── Auto Comment (Phase 16) ───────────────────────────
    
    CTA_POOL = [
        "Link mình để ở đây nè:\n{link}",
        "Ai cần thì vào link này nhé\n{link}",
        "Xem chi tiết sản phẩm tại đây: {link}",
        "Link đây mọi người ơi\n{link}",
        "Mình share link ở đây nha\n{link}",
        "Link bên dưới nhé\n{link}",
    ]
    
    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        """
        Navigate to a published post and add a comment.
        Non-fatal: failure returns ok=False but should NOT crash the parent job.
        """
        
        self.logger.info("FacebookAdapter: Posting comment on %s", post_url)
        
        if not self.page:
            return PublishResult(ok=False, error="Page not initialized", is_fatal=False)
        
        try:
            # 1. Navigate to the post
            self.page.goto(post_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(random.randint(3000, 5000))
            
            # 1b. Debug: screenshot after page load to diagnose login walls
            try:
                _debug_path = DATA_DIR / f"debug_comment_{int(time.time())}.png"
                self.page.screenshot(path=_debug_path)
                self.logger.info("FacebookAdapter: Debug screenshot saved: %s", _debug_path)
            except Exception as e:
                self.logger.warning("FacebookAdapter: Swallowed exception at line 1149: %s", e)
            
            # 1c. Dismiss login wall if present (common on Reels when session expired)
            try:
                _close_btn = self.page.locator("[aria-label='Close'], [aria-label='Đóng']").first
                if _close_btn.count() > 0 and _close_btn.is_visible(timeout=2000):
                    _close_btn.click()
                    self.page.wait_for_timeout(1000)
                    self.logger.info("FacebookAdapter: Dismissed login/popup overlay")
            except Exception as e:
                self.logger.warning("FacebookAdapter: Swallowed exception at line 1159: %s", e)
            
            # 1d. Check if we're actually logged in
            _is_logged_in = False
            try:
                # If there's a login form visible, session is expired
                _login_form = self.page.locator("input[name='email'], input[name='pass']").first
                if _login_form.count() > 0 and _login_form.is_visible(timeout=1500):
                    self.logger.warning("FacebookAdapter: Login wall detected — session may be expired for this account")
                else:
                    _is_logged_in = True
            except Exception:
                _is_logged_in = True  # assume logged in if check fails
            
            # 2. Casual scroll (human behavior)
            human_scroll(self.page)
            self.page.wait_for_timeout(random.randint(1000, 2000))

            # 2b. Reels / watch often hide the composer until "Comment" / "Bình luận" is clicked
            # On Reels, the comment icon may NOT be a <button> — it can be a div/span/link
            _opened_comment_section = False
            
            # Strategy 1: Try get_by_role("button") for standard posts
            for _open_name in ("Bình luận", "Comment", "Comments"):
                if _opened_comment_section:
                    break
                try:
                    _bl = self.page.get_by_role("button", name=_open_name)
                    if _bl.count() == 0:
                        continue
                    _cand = _bl.first
                    if _cand.is_visible(timeout=1200):
                        _cand.scroll_into_view_if_needed()
                        self.page.wait_for_timeout(random.randint(200, 500))
                        _cand.click(timeout=15000)
                        self.page.wait_for_timeout(random.randint(3000, 5000))
                        self.logger.info("FacebookAdapter: Opened comment section via button %r", _open_name)
                        _opened_comment_section = True
                except Exception:
                    continue
            
            # Strategy 2: Reels uses aria-label on div/span for the comment icon
            if not _opened_comment_section:
                _reel_comment_selectors = [
                    "[aria-label='Bình luận']",
                    "[aria-label='Comment']",
                    "[aria-label='Comments']",
                    "[aria-label='Để lại bình luận']",
                    "[aria-label='Leave a comment']",
                ]
                for _sel in _reel_comment_selectors:
                    if _opened_comment_section:
                        break
                    try:
                        _loc = self.page.locator(_sel).first
                        if _loc.count() > 0 and _loc.is_visible(timeout=1500):
                            _loc.scroll_into_view_if_needed()
                            self.page.wait_for_timeout(random.randint(200, 500))
                            _loc.click(timeout=15000)
                            self.page.wait_for_timeout(random.randint(3000, 5000))
                            self.logger.info("FacebookAdapter: Opened comment section via selector %r", _sel)
                            _opened_comment_section = True
                    except Exception:
                        continue
            
            # Strategy 3: Try link role
            if not _opened_comment_section:
                for _open_name in ("Bình luận", "Comment"):
                    if _opened_comment_section:
                        break
                    try:
                        _bl = self.page.get_by_role("link", name=_open_name)
                        if _bl.count() == 0:
                            continue
                        _cand = _bl.first
                        if _cand.is_visible(timeout=1200):
                            _cand.click(timeout=15000)
                            self.page.wait_for_timeout(random.randint(3000, 5000))
                            self.logger.info("FacebookAdapter: Opened comment section via link %r", _open_name)
                            _opened_comment_section = True
                    except Exception:
                        continue
            
            if not _opened_comment_section:
                self.logger.warning("FacebookAdapter: Could not find/open comment section button")
            
            # 2c. Debug: screenshot after opening comment section
            try:
                _debug_path2 = DATA_DIR / f"debug_comment_after_{int(time.time())}.png"
                self.page.screenshot(path=_debug_path2)
                self.logger.info("FacebookAdapter: Debug screenshot (after comment click) saved: %s", _debug_path2)
            except Exception as e:
                self.logger.warning("FacebookAdapter: Swallowed exception at line 1251: %s", e)
            
            # 3. Find comment box (multiple selectors for i18n + Reels robustness)
            comment_selectors = [
                # New variants (Comment as...)
                "div[aria-label^='Bình luận dưới tên']",
                "div[aria-label^='Comment as']",
                "div[aria-label*='bình luận dưới tên' i]",
                "div[role='textbox'][aria-label*='bình luận' i]",
                "div[role='textbox'][aria-label*='comment' i]",
                # Standard post layout (exact match)
                "div[aria-label='Write a comment']",
                "div[aria-label='Write a comment…']",
                "div[aria-label='Write a comment...']",
                "div[aria-label='Viết bình luận']",
                "div[aria-label='Viết bình luận…']",
                "div[aria-label='Viết bình luận...']",
                # Reels / public comment variants
                "div[aria-label='Viết bình luận công khai...']",
                "div[aria-label='Viết bình luận công khai…']",
                "div[aria-label='Write a public comment...']",
                "div[aria-label='Write a public comment…']",
                # Partial match fallbacks (CSS *=)
                "div[contenteditable='true'][aria-label*='bình luận' i]",
                "div[contenteditable='true'][aria-label*='comment' i]",
                "div[contenteditable='true'][aria-label*='Comment']",
            ]
            
            comment_box = None
            
            # Allow DOM to settle before checking for textboxes
            self.page.wait_for_timeout(1500)
            
            for sel in comment_selectors:
                if comment_box: break
                try:
                    loc = self.page.locator(sel)
                    for i in range(loc.count()):
                        nth_loc = loc.nth(i)
                        if nth_loc.is_visible():
                            comment_box = nth_loc
                            self.logger.info("FacebookAdapter: Found comment box via: %s (idx %d)", sel, i)
                            break
                except Exception:
                    continue
            
            # Secondary generic fallback (last visible textbox avoids chat tabs)
            if not comment_box:
                try:
                    loc = self.page.locator("div[contenteditable='true'][role='textbox']")
                    for i in reversed(range(loc.count())):
                        nth_loc = loc.nth(i)
                        if nth_loc.is_visible():
                            comment_box = nth_loc
                            self.logger.info("FacebookAdapter: Found comment box via generic fallback (idx %d)", i)
                            break
                except Exception as e:
                    self.logger.warning("FacebookAdapter: Swallowed exception at line 1308: %s", e)
            
            # Fallback: use Playwright's get_by_placeholder for Lexical editor
            if not comment_box:
                for _ph in ("Viết bình luận", "Write a comment", "Viết bình luận công khai"):
                    try:
                        _loc = self.page.get_by_placeholder(_ph).first
                        if _loc.count() > 0 and _loc.is_visible(timeout=1500):
                            comment_box = _loc
                            self.logger.info("FacebookAdapter: Found comment box via placeholder: %r", _ph)
                            break
                    except Exception:
                        continue
            
            # Diagnostic: if still not found, dump all textbox aria-labels for debugging
            if not comment_box:
                try:
                    all_labels = self.page.eval_on_selector_all(
                        "div[contenteditable='true'], [role='textbox']",
                        "els => els.map(e => ({tag: e.tagName, role: e.getAttribute('role'), label: e.getAttribute('aria-label'), placeholder: e.getAttribute('aria-placeholder'), editable: e.contentEditable})).slice(0, 10)"
                    )
                    self.logger.warning("FacebookAdapter: Comment box not found. Available textboxes: %s", all_labels)
                except Exception:
                    self.logger.warning("FacebookAdapter: Comment box not found and diagnostic failed.")
                return PublishResult(ok=False, error="Comment box not found", is_fatal=False)
            
            # 4. Click to focus comment box
            comment_box.scroll_into_view_if_needed()
            self.page.wait_for_timeout(500)
            comment_box.click()
            self.page.wait_for_timeout(random.randint(500, 1000))
            
            # 5. Type comment (Check workflow config if available, otherwise default to typing)
            final_comment = comment_text
            adapter_steps = getattr(self, 'active_steps', None)
            if adapter_steps is None or "type_comment" in adapter_steps:
                human_type(self.page, final_comment)
            else:
                rt_emit("step_skipped", platform="facebook", step_name="type_comment",
                        reason="not in active_steps")
            
            # 6. Random pause before submit (1–3 seconds)
            self.page.wait_for_timeout(random.randint(1000, 3000))
            
            # 7. Submit via Enter
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(random.randint(2000, 4000))
            
            # 8. Post-comment human behavior: scroll a bit
            human_scroll(self.page)
            
            self.logger.info("FacebookAdapter: Comment posted successfully on %s", post_url)
            return PublishResult(ok=True, details={"comment": final_comment})
            
        except Exception as e:
            self.logger.warning("FacebookAdapter: Failed to post comment: %s", e)
            return PublishResult(ok=False, error=f"Comment failed: {e}", is_fatal=False)

    @staticmethod
    def _facebook_numeric_id_from_url(url: str) -> str | None:
        """Extract profile/page numeric id from facebook URLs (profile.php?id=…)."""
        if not url:
            return None
        m = re.search(r"[?&]id=(\d{5,})", url)
        return m.group(1) if m else None

    @staticmethod
    def _normalize_fb_profile_url_for_compare(u: str) -> str:
        if not u:
            return ""
        base = u.split("?")[0].rstrip("/")
        if "id=" in u:
            pieces = u.split("id=")
            if len(pieces) > 1:
                base += "?id=" + pieces[1].split("&")[0]
        return base

    @staticmethod
    def _is_fb_homepage_url(url: str) -> bool:
        """Return True if URL is bare FB host root with no meaningful path or query.
        This happens when /me is resolved while in Facebook Page context."""
        try:
            parsed = urlparse(url)
            path = parsed.path or "/"
            return (
                parsed.netloc.lower() in _FB_HOST_NETLOCS
                and path in ("", "/")
                and not parsed.query
            )
        except Exception:
            return False

    def _verify_page_context_via_switch_banner(self, target_page_url: str) -> bool:
        """Fallback check when /me resolves to root (Facebook Page context).
        Navigate to target page and verify the 'Switch now' banner is absent.
        Banner appears only when visiting a managed page while NOT in that page's identity.
        Its absence confirms we are already operating as the target page.
        """
        if not self.page or not target_page_url:
            return False
        try:
            self.page.goto(target_page_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(4000)
            switch_sel = SELECTORS["switch_menu"]["switch_now_button"]
            switch_visible = self.page.locator(switch_sel).count() > 0
            if switch_visible:
                self.logger.info(
                    "FacebookAdapter: Fallback check — 'Switch now' banner visible on target page → NOT in page context."
                )
                return False
            self.logger.info(
                "FacebookAdapter: Fallback check — 'Switch now' banner absent → confirmed Page context."
            )
            return True
        except Exception as e:
            self.logger.warning("FacebookAdapter: Fallback page-context banner check failed: %s", e)
            return False

    def _urls_indicate_same_fb_page_context(self, target_page_url: str, active_url: str) -> bool:
        norm_target = self._normalize_fb_profile_url_for_compare(target_page_url or "")
        norm_active = self._normalize_fb_profile_url_for_compare(active_url or "")

        def _url_has_profile_path(url: str) -> bool:
            try:
                path = urlparse(url).path or ""
                return path not in ("", "/")
            except Exception:
                return True

        target_in_active = norm_target in norm_active
        active_in_target = (
            norm_active in norm_target and _url_has_profile_path(active_url)
        )
        verified_ok = bool(
            norm_target and norm_active and (target_in_active or active_in_target)
        )
        page_tid = self._facebook_numeric_id_from_url(target_page_url or "")
        if page_tid and page_tid in active_url:
            verified_ok = True
        return verified_ok

    def _verify_posting_context_matches_target(self, target_page_url: str) -> tuple[bool, str, str]:
        """
        Open /me and compare resolved profile URL to target page.
        Returns (ok, norm_active, norm_target) for logging / error messages.
        """
        if not self.page or not self._is_session_alive():
            return (
                False,
                "",
                self._normalize_fb_profile_url_for_compare(target_page_url or ""),
            )
        try:
            self.page.goto(f"{FACEBOOK_HOST}/me", wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)
            active_url = self.page.url
        except Exception as e:
            self.logger.warning("FacebookAdapter: /me check failed: %s", e)
            return (
                False,
                "",
                self._normalize_fb_profile_url_for_compare(target_page_url or ""),
            )
        nt = self._normalize_fb_profile_url_for_compare(target_page_url or "")
        na = self._normalize_fb_profile_url_for_compare(active_url)
        ok = self._urls_indicate_same_fb_page_context(target_page_url or "", active_url)

        # Fallback: /me resolves to facebook.com root when browser is in Page context.
        # Pages have no personal /me redirect; FB returns the homepage instead.
        # In that case use the Switch-now banner absence as a reliable secondary check.
        if not ok and self._is_fb_homepage_url(active_url):
            self.logger.info(
                "FacebookAdapter: /me resolved to FB homepage — likely Page context. "
                "Running Switch-now banner fallback check..."
            )
            ok = self._verify_page_context_via_switch_banner(target_page_url or "")
            if ok:
                na = self._normalize_fb_profile_url_for_compare(self.page.url)

        return (ok, na, nt)

    def _switcher_row_has_page_id(self, row: Locator, page_id: str) -> bool:
        """True if row subtree has href with id or FB inlined the numeric id in markup."""
        if not page_id:
            return False
        try:
            if row.locator(f'[href*="{page_id}"]').count() > 0:
                return True
            outer = row.evaluate("e => (e && e.outerHTML) ? e.outerHTML : ''")
            return page_id in (outer or "")
        except Exception:
            return False

    def _resolve_switcher_clickable(self, el: Locator) -> Locator:
        clickable = el.locator(
            'xpath=ancestor::div[@role="button" or @role="menuitemradio" or @role="radio" or @role="menuitem" or @role="link"][1]'
        ).first
        if self._is_visible(clickable):
            return clickable
        return el

    @staticmethod
    def _fb_aria_switch_label_is_carousel_noise(al: str) -> bool:
        """FB page cards use long labels starting with photo carousel verbs — not the real switch CTA."""
        s = al.strip().lower()
        noise_prefixes = (
            "ảnh trước",
            "ảnh sau",
            "previous photo",
            "previous image",
            "next photo",
            "next image",
        )
        return any(s.startswith(p) for p in noise_prefixes)

    @staticmethod
    def _fb_aria_switch_label_is_primary_switch_cta(al: str) -> bool:
        """Prefer buttons whose accessible name starts with the real switch phrase."""
        s = al.strip().lower()
        return (
            s.startswith("chuyển sang")
            or s.startswith("switch to")
            or s.startswith("switching to")
        )

    def _try_click_switcher_aria_label(self, dialog: Locator, target_page_name: str) -> bool:
        """
        FB exposes 'Chuyển sang <Page>' / 'Switch to <Page>' on role=button — more reliable
        than has-text on duplicate rows (cover photo can intercept the first match).
        Skips carousel-style labels; tries primary CTA first, then DOM-last within each tier.
        """
        if not self.page or not target_page_name:
            return False
        tn_norm = self._normalize_fb_text(target_page_name)
        if not tn_norm:
            return False
        try:
            candidates = dialog.locator('[role="button"]').all()
        except Exception:
            return False
        primary: list[Locator] = []
        secondary: list[Locator] = []
        for el in candidates:
            try:
                al = (el.get_attribute("aria-label") or "").strip()
                if not al:
                    continue
                al_norm = self._normalize_fb_text(al)
                if tn_norm not in al_norm:
                    continue
                if (
                    "chuyển sang" not in al_lower
                    and "switch to" not in al_lower
                    and "switching to" not in al_lower
                ):
                    continue
                if self._fb_aria_switch_label_is_carousel_noise(al):
                    continue
                if self._fb_aria_switch_label_is_primary_switch_cta(al):
                    primary.append(el)
                else:
                    secondary.append(el)
            except Exception:
                continue
        for tier_name, tier in (
            ("primary-cta", primary),
            ("secondary", secondary),
        ):
            for el in reversed(tier):
                try:
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(force=True, timeout=5000)
                    full_al = (el.get_attribute("aria-label") or "").strip()
                    self.logger.info(
                        "FacebookAdapter: Switch via aria-label [%s] (%s)",
                        tier_name,
                        full_al[:120],
                    )
                    return True
                except Exception:
                    continue
        return False

    def _activate_profile_switcher_row(self, row: Locator, label: str) -> bool:
        """
        FB switcher rows often ignore Playwright hit-tests; try several input paths.
        """
        if not self.page:
            return False
        try:
            row.scroll_into_view_if_needed(timeout=5000)
        except Exception as e:
            self.logger.warning("FacebookAdapter: Swallowed exception at line 1546: %s", e)
        try:
            if not row.is_visible(timeout=3000):
                self.logger.debug("FacebookAdapter: Switcher row not visible (%s)", label)
                return False
        except Exception:
            return False
        # Cover images often intercept normal click — force first to avoid 8s timeout.
        try:
            row.click(force=True, timeout=5000)
            self.logger.debug("FacebookAdapter: Switcher row force click OK (%s)", label)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Switcher row force click failed (%s): %s", label, e)
        try:
            row.click(timeout=8000)
            self.logger.debug("FacebookAdapter: Switcher row normal click OK (%s)", label)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Switcher row normal click failed (%s): %s", label, e)
        try:
            row.evaluate("el => el.click()")
            self.logger.debug("FacebookAdapter: Switcher row evaluate click OK (%s)", label)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Switcher row evaluate click failed (%s): %s", label, e)
        try:
            row.focus(timeout=5000)
            self.page.wait_for_timeout(200)
            self.page.keyboard.press("Enter")
            self.logger.debug("FacebookAdapter: Switcher row Enter OK (%s)", label)
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Switcher row Enter failed (%s): %s", label, e)
        return False

    def _reopen_profile_switch_dialog(self, avatar_btn: Locator) -> Locator:
        """Re-open avatar menu → optional See all → return the profile switcher dialog."""
        self._click_locator(avatar_btn, "avatar menu", timeout=5000)
        self.page.wait_for_timeout(2000)
        see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first
        if see_all.count() > 0 and see_all.is_visible():
            if not self._activate_profile_switcher_row(see_all, "see all profiles"):
                self.logger.warning(
                    "FacebookAdapter: See-all click failed in reopen dialog; retrying avatar menu once."
                )
                self._click_locator(avatar_btn, "avatar menu", timeout=5000)
                self.page.wait_for_timeout(1500)
                see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first
                if see_all.count() > 0 and see_all.is_visible():
                    self._activate_profile_switcher_row(see_all, "see all profiles (retry)")
            self.page.wait_for_timeout(2000)
        return self.page.locator('div[role="dialog"]').last

    def _switch_to_page_context(
        self,
        target_page_name: str | None = None,
        *,
        target_page_url: str | None = None,
    ) -> bool:
        """
        Switch current context to become the Fanpage.
        Uses the top-right avatar menu as proven in test_switch.py.
        """
        if not self.page:
            return False
            
        # 0. Ensure we are in an authenticated context (bypass Continue as)
        self._ensure_authenticated_context()

        self.logger.info("FacebookAdapter: Initiating account switch via avatar menu...")
        try:
            # 1. Click top-right avatar image
            avatar_selectors = [
                SELECTORS["switch_menu"]["account_menu_button"]
            ]
            
            avatar_btn = None
            for sel in avatar_selectors:
                els = self.page.locator(sel).all()
                if els:
                    avatar_btn = els[-1]
                    if avatar_btn.is_visible():
                        break
            
            if not avatar_btn:
                self.logger.warning("FacebookAdapter: Could not find avatar menu icon.")
                return False

            self._click_locator(avatar_btn, "avatar menu", timeout=5000)
            self.page.wait_for_timeout(2000)

            # 2. Look for "Xem tất cả trang cá nhân" or direct Page name
            see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first

            if see_all.count() > 0 and see_all.is_visible():
                if not self._activate_profile_switcher_row(see_all, "see all profiles"):
                    self.logger.warning(
                        "FacebookAdapter: See-all blocked by overlay; reopening avatar menu and retrying."
                    )
                    self._click_locator(avatar_btn, "avatar menu", timeout=5000)
                    self.page.wait_for_timeout(1500)
                    see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first
                    if see_all.count() > 0 and see_all.is_visible():
                        self._activate_profile_switcher_row(see_all, "see all profiles (retry)")
                self.page.wait_for_timeout(2000)

            dialog = self.page.locator('div[role="dialog"]').last

            # 3a. Prefer href match (numeric id) — FB often uses role=link or bare href, not only <a>.
            page_id = self._facebook_numeric_id_from_url(target_page_url or "")
            id_had_visible_link = False
            if page_id:
                id_patterns = [
                    f'a[href*="profile.php?id={page_id}"]',
                    f'a[href*="id={page_id}"]',
                    f'[role="link"][href*="id={page_id}"]',
                    f'[href*="profile.php?id={page_id}"]',
                    f'[href*="id={page_id}"]',
                    f'[href*="{page_id}"]',
                ]
                for pattern in id_patterns:
                    link = dialog.locator(pattern).first
                    try:
                        if link.count() > 0 and link.is_visible(timeout=2500):
                            id_had_visible_link = True
                            self.logger.info(
                                "FacebookAdapter: Switching via menu link for page id %s (%s)...",
                                page_id,
                                pattern.split("[")[0],
                            )
                            link.scroll_into_view_if_needed()
                            try:
                                link.click(timeout=8000)
                            except Exception:
                                self.logger.info(
                                    "FacebookAdapter: Link click timed out, trying force..."
                                )
                                link.click(force=True)
                            try:
                                dialog.wait_for(state="hidden", timeout=15000)
                            except Exception:
                                self.logger.warning(
                                    "FacebookAdapter: Switcher dialog still visible after id link click."
                                )
                            self.page.wait_for_timeout(3000)
                            if not target_page_url or self._verify_posting_context_matches_target(
                                target_page_url
                            )[0]:
                                self.logger.info("FacebookAdapter: Switch command sent (id link).")
                                return True
                            self.logger.warning(
                                "FacebookAdapter: Id link click did not verify posting context; "
                                "reopening switcher for fallbacks."
                            )
                            dialog = self._reopen_profile_switch_dialog(avatar_btn)
                            break
                    except Exception:
                        continue
                if not id_had_visible_link:
                    self.logger.debug(
                        "FacebookAdapter: No visible href control for page id %s inside switcher dialog.",
                        page_id,
                    )

            if target_page_name:
                if self._try_click_switcher_aria_label(dialog, target_page_name):
                    try:
                        # Short wait: wrong clicks (carousel) often leave dialog open; verify + 3a2b follow.
                        dialog.wait_for(state="hidden", timeout=6000)
                    except Exception:
                        self.logger.warning(
                            "FacebookAdapter: Switcher dialog still visible after aria-label click."
                        )
                    self.page.wait_for_timeout(2500)
                    if not target_page_url:
                        self.logger.info(
                            "FacebookAdapter: Switch command sent (aria-label switch button)."
                        )
                        return True
                    ok_ctx, _, _ = self._verify_posting_context_matches_target(target_page_url)
                    if ok_ctx:
                        self.logger.info(
                            "FacebookAdapter: Switch command sent (aria-label switch button)."
                        )
                        return True
                    self.logger.warning(
                        "FacebookAdapter: Aria-label switch did not verify posting context; "
                        "reopening switcher for fallbacks."
                    )
                    dialog = self._reopen_profile_switch_dialog(avatar_btn)

            # 3a2b. Text-filtered rows — FB may use menuitemradio, radio, or role=button rows.
            if target_page_name:
                tn_norm = self._normalize_fb_text(target_page_name)
                for row_sel in (
                    '[role="menuitemradio"]',
                    '[role="radio"]',
                    'div[role="button"]',
                ):
                    # We can't use Playwright's filter(has_text=...) with normalization easily,
                    # so we manually filter for precision across NFD/NFC.
                    all_rows = dialog.locator(row_sel).all()
                    rows_with_match: list[Locator] = []
                    for r in all_rows:
                        try:
                            t = r.inner_text()
                            if tn_norm in self._normalize_fb_text(t):
                                rows_with_match.append(r)
                        except Exception:
                            continue
                    
                    cnt = len(rows_with_match)
                    if cnt == 0:
                        self.logger.debug(
                            "FacebookAdapter: 3a2b zero %s rows matching '%s' (norm: %s).",
                            row_sel,
                            target_page_name,
                            tn_norm,
                        )
                        continue
                    if cnt > 12:
                        self.logger.debug(
                            "FacebookAdapter: 3a2b skip %s (count=%s too many, likely false positives).",
                            row_sel,
                            cnt,
                        )
                        continue
                    self.logger.debug(
                        "FacebookAdapter: Switcher %s rows with normalized text match for '%s': count=%s",
                        row_sel,
                        target_page_name,
                        cnt,
                    )
                    activated = False
                    if page_id:
                        for r in rows_with_match:
                            try:
                                if self._switcher_row_has_page_id(r, page_id):
                                    if self._activate_profile_switcher_row(
                                        r, f"id-{row_sel}"
                                    ):
                                        activated = True
                                        break
                            except Exception as e:
                                self.logger.warning("FacebookAdapter: Swallowed exception at line 1791: %s", e)
                    if not activated:
                        indices = list(range(cnt))
                        if row_sel == "div[role=\"button\"]" and cnt >= 2:
                            indices = list(range(cnt - 1, -1, -1))
                            self.logger.debug(
                                "FacebookAdapter: 3a2b trying button row indices reversed (count=%s).",
                                cnt,
                            )
                        for i in indices:
                            r = rows_with_match[i]
                            try:
                                if r.get_attribute("aria-checked") == "true":
                                    self.logger.debug(
                                        "FacebookAdapter: Skip switcher row %s (already selected).",
                                        i,
                                    )
                                    continue
                            except Exception as e:
                                self.logger.warning("FacebookAdapter: Swallowed exception at line 1810: %s", e)
                            if self._activate_profile_switcher_row(r, f"{row_sel}-{i}"):
                                activated = True
                                break
                    if activated:
                        try:
                            dialog.wait_for(state="hidden", timeout=15000)
                        except Exception:
                            self.logger.warning(
                                "FacebookAdapter: Switcher dialog still visible after 3a2b."
                            )
                        self.page.wait_for_timeout(3000)
                        self.logger.info(
                            "FacebookAdapter: Switch command sent (text-filtered %s).",
                            row_sel,
                        )
                        return True

            # 3a2. Role-based rows (dialog + full page — some builds render list outside dialog subtree).
            name_re = (
                re.compile(re.escape(target_page_name.strip()), re.IGNORECASE)
                if target_page_name
                else None
            )
            if target_page_name and name_re:
                for role in ("menuitemradio", "radio", "menuitem"):
                    # menuitem only inside dialog — page-wide would hit unrelated FB menus.
                    scopes: list[tuple[str, Any]] = [("dialog", dialog)]
                    if role in ("menuitemradio", "radio"):
                        scopes.append(("page", self.page))
                    for scope_name, scope in scopes:
                        try:
                            loc = scope.get_by_role(role, name=name_re)
                            n = loc.count()
                            if n == 0:
                                continue
                            pick = loc.first
                            if not pick.is_visible(timeout=3000):
                                self.logger.info(
                                    "FacebookAdapter: %s %s match count=%s but first not visible; skipping.",
                                    scope_name,
                                    role,
                                    n,
                                )
                                continue
                            self.logger.info(
                                "FacebookAdapter: Clicking %s (scope=%s, count=%s) for '%s'...",
                                role,
                                scope_name,
                                n,
                                target_page_name,
                            )
                            pick.scroll_into_view_if_needed()
                            try:
                                pick.click(timeout=8000)
                            except Exception:
                                pick.click(force=True)
                            try:
                                dialog.wait_for(state="hidden", timeout=15000)
                            except Exception:
                                self.logger.warning(
                                    "FacebookAdapter: Switcher dialog still visible after "
                                    "%s click (scope=%s).",
                                    role,
                                    scope_name,
                                )
                            self.page.wait_for_timeout(3000)
                            self.logger.info(
                                "FacebookAdapter: Switch command sent (%s/%s).",
                                role,
                                scope_name,
                            )
                            return True
                        except Exception as e:
                            self.logger.debug(
                                "FacebookAdapter: role=%s scope=%s skipped: %s",
                                role,
                                scope_name,
                                e,
                            )

            # 3b. Find the target profile in the list (name match); prefer row that contains page id in href.
            if target_page_name:
                self.logger.info("FacebookAdapter: Looking for exact profile name '%s' in switch menu...", target_page_name)
                
                target_name_lower = target_page_name.lower().strip()
                profile_items = self.page.locator('div[role="button"], div[role="menuitem"], div[role="radio"], div[role="menuitemradio"], div[role="link"]').all()
                
                name_candidates: list = []
                for el in profile_items:
                    if not el.is_visible():
                        continue
                    try:
                        text = el.inner_text().strip()
                        if text and len(text) >= 2:
                            normalized = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
                            normalized = normalized.replace('đ', 'd').replace('Đ', 'D').lower()
                            
                            target_norm = unicodedata.normalize('NFD', target_name_lower).encode('ascii', 'ignore').decode('utf-8')
                            target_norm = target_norm.replace('đ', 'd').replace('Đ', 'D')
                            
                            if target_norm in normalized:
                                name_candidates.append(el)
                    except Exception as e:
                        self.logger.warning("FacebookAdapter: Swallowed exception at line 1914: %s", e)

                found_el = None
                if page_id and name_candidates:
                    for el in name_candidates:
                        try:
                            if self._switcher_row_has_page_id(el, page_id):
                                found_el = el
                                self.logger.info(
                                    "FacebookAdapter: Using name match row containing page id %s (href or markup).",
                                    page_id,
                                )
                                break
                        except Exception as e:
                            self.logger.warning("FacebookAdapter: Swallowed exception at line 1928: %s", e)
                    if not found_el:
                        self.logger.warning(
                            "FacebookAdapter: %s name matches, page id %s not in href/markup; "
                            "trying activate inner candidates (reverse order)...",
                            len(name_candidates),
                            page_id,
                        )
                        for rev_i, el in enumerate(reversed(name_candidates)):
                            c = self._resolve_switcher_clickable(el)
                            if self._activate_profile_switcher_row(
                                c, f"name-cand-rev-{rev_i}"
                            ):
                                try:
                                    dialog.wait_for(state="hidden", timeout=15000)
                                except Exception:
                                    self.logger.warning(
                                        "FacebookAdapter: Switcher dialog still visible after "
                                        "multi-candidate activate."
                                    )
                                self.page.wait_for_timeout(3000)
                                self.logger.info(
                                    "FacebookAdapter: Switch command sent (multi-candidate %s).",
                                    rev_i,
                                )
                                return True
                        found_el = name_candidates[-1]
                        self.logger.info(
                            "FacebookAdapter: Using last name match as fallback click target "
                            "(inner-most / list order)."
                        )
                elif name_candidates:
                    found_el = name_candidates[-1]
                    self.logger.info(
                        "FacebookAdapter: No page id filter; using last of %s name matches.",
                        len(name_candidates),
                    )
                
                if found_el:
                    self.logger.info("FacebookAdapter: Clicking explicit profile match for '%s'...", target_page_name)
                    # Nearest interactive ancestor — avoid outer dialog-sized role=button.
                    clickable = found_el.locator(
                        'xpath=ancestor::div[@role="button" or @role="menuitemradio" or @role="radio" or @role="menuitem" or @role="link"][1]'
                    ).first

                    if self._is_visible(clickable):
                        btn_to_click = clickable
                    else:
                        btn_to_click = found_el
                        
                    btn_to_click.scroll_into_view_if_needed()
                    try:
                        btn_to_click.click(timeout=5000)
                    except Exception:
                        self.logger.info("FacebookAdapter: Normal click timed out, attempting force click...")
                        btn_to_click.click(force=True)
                    try:
                        dialog.wait_for(state="hidden", timeout=15000)
                    except Exception:
                        self.logger.warning(
                            "FacebookAdapter: Switcher dialog still visible after row click."
                        )
                    self.page.wait_for_timeout(3000)
                    self.logger.info("FacebookAdapter: Switch command sent.")
                    return True
                else:
                    self.logger.warning("FacebookAdapter: Target profile '%s' not found. Dumping HTML for debugging...", target_page_name)
                    try:
                        body_html = self.page.evaluate("document.body.innerHTML")
                        safe_name = target_page_name.replace(' ', '_').lower()
                        dump_dir = BASE_DIR / "tests"
                        dump_dir.mkdir(parents=True, exist_ok=True)
                        with open(dump_dir / f"fb_switch_menu_{safe_name}.html", "w", encoding="utf-8") as f:
                            f.write(body_html)
                    except Exception as e:
                        self.logger.error("Failed to dump HTML: %s", e)
                    
                    self.logger.error("FacebookAdapter: Could not find explicitly requested profile '%s'. Aborting switch.", target_page_name)
                    return False
                    
            # Fallback ONLY if no target_page_name was specified (e.g. just switch to ANY page)
            profile_items = self.page.locator(SELECTORS["switch_menu"]["any_profile_btn"]).all()
            if profile_items:
                self.logger.info("FacebookAdapter: Clicking first available profile in switch menu...")
                try:
                    profile_items[0].click(timeout=5000)
                except Exception:
                    self.logger.info("FacebookAdapter: Normal click timed out, attempting force click...")
                    profile_items[0].click(force=True)
                self.page.wait_for_timeout(12000)  # Switch can take time (VPS / slow FB)
                self.logger.info("FacebookAdapter: Switch command sent.")
                return True
            
        except Exception as e:
            self.logger.error("FacebookAdapter: Switch failed: %s", e)
            
        return False
