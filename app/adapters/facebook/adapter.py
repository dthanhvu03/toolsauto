import logging
import os
from pathlib import Path
import random
import re
from urllib.parse import urlparse
import traceback
from typing import Any
from app.config import BASE_DIR, SAFE_MODE, LOGS_DIR
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

class FacebookAdapter(AdapterInterface):
    """
    Scaffolding for the Facebook playright adapter.
    """
    def __init__(self):
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        
    def open_session(self, profile_path: str) -> bool:
        if self.playwright or self.context or self.page:
            logger.warning("FacebookAdapter: Session already open, closing previous before opening new one.")
            self.close_session()

        logger.info("FacebookAdapter: Opening persistent context at profile: %s", profile_path)
        bundle = FacebookSessionManager.launch_persistent(profile_path)
        if not bundle:
            self.close_session()
            return False
        self.playwright, self.context, self.page = bundle
        return True

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
            u = "https://www.facebook.com" + u
        # drop query/fragments
        u = u.split("#")[0].split("?")[0].rstrip("/")
        # reject ambiguous reel root (e.g. https://www.facebook.com/reel/)
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
            logger.warning("FacebookAdapter: Failed to save screenshot artifact: %s", e)

        try:
            html_path.write_text(self.page.content(), encoding="utf-8")
            artifacts["html"] = str(html_path)
        except Exception as e:
            logger.warning("FacebookAdapter: Failed to save HTML artifact: %s", e)

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

    def _click_locator(self, locator: Locator, description: str, timeout: int = 5000) -> bool:
        try:
            locator.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            locator.click(timeout=timeout)
            logger.info("FacebookAdapter: Clicked %s", description)
            return True
        except Exception as e:
            logger.debug("FacebookAdapter: Standard click failed for %s: %s", description, e)

        try:
            locator.evaluate("el => el.click()")
            logger.info("FacebookAdapter: JS-clicked %s", description)
            return True
        except Exception as e:
            logger.debug("FacebookAdapter: JS click failed for %s: %s", description, e)

        try:
            locator.click(force=True, timeout=timeout)
            logger.info("FacebookAdapter: Force-clicked %s", description)
            return True
        except Exception as e:
            logger.debug("FacebookAdapter: Force click failed for %s: %s", description, e)
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
        logger.info("FacebookAdapter: Navigation missing, checking for session recovery screen...")
        recovery_btn = None
        
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
                recovery_btn = blue_btn.first

        if recovery_btn:
            logger.info("FacebookAdapter: Found 'Continue/Tiếp tục' recovery button. Bypassing...")
            try:
                self._click_locator(recovery_btn, "session recovery button", timeout=5000)
                self.page.wait_for_timeout(5000)
                # Verify navigation again
                return self.page.locator('div[role="navigation"], a[aria-label="Facebook"]').count() > 0
            except Exception as e:
                logger.warning("FacebookAdapter: Failed to click recovery button: %s", e)
            
        return False

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
            account_menu_btn = self.page.locator(SELECTORS["switch_menu"]["account_menu_button"]).last
            if not self._is_visible(account_menu_btn):
                logger.warning("FacebookAdapter: Account menu button not visible.")
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
                self._click_locator(see_all, "see all profiles", timeout=3000)
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
                except Exception:
                    pass

            if found_el:
                logger.info("FacebookAdapter: Found personal profile '%s' in switcher. Clicking...", account_name)
                # Find the closest clickable container
                clickable = found_el.locator("xpath=ancestor::div[@role='button' or @role='menuitemradio' or @role='radio' or @role='menuitem']").first
                if self._is_visible(clickable):
                    self._click_locator(clickable, f"profile {account_name}", timeout=5000)
                else:
                    self._click_locator(found_el, f"profile {account_name}", timeout=5000)
                
                self.page.wait_for_timeout(5000) # Wait for page reload context switch
                return True
            else:
                logger.info("FacebookAdapter: Personal profile '%s' not explicitly found in switcher. Might already be active.", account_name)
                # Close the menu if we opened it by clicking off banner
                try:
                    self.page.keyboard.press("Escape")
                except: pass
                
        except Exception as e:
            logger.warning("FacebookAdapter: Failed during profile switch attempt: %s", e)
            
        return False

    def publish(self, job: Job) -> PublishResult:
        logger.info("FacebookAdapter: Attempting to publish job %s", job.id)

        if not self.page:
            return PublishResult(ok=False, error="Playwright page is not initialized.", is_fatal=True)

        target_page_url = (getattr(job, "target_page", None) or "").strip() or None
        is_page_post = bool(target_page_url)
        flow_mode = "page" if is_page_post else "personal"
        entrypoint_used: str | None = None

        try:
            # Check for account access
            if not getattr(job, "account", None):
                # We need the account loaded to get the real name for context switching
                with SessionLocal() as db:
                    db.add(job)
                    job.account  # Trigger lazy load
        except Exception as e:
            logger.warning("FacebookAdapter: Could not load job account: %s", e)

        try:
            # 1. Navigation & Page Context Switch
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
                                
                logger.info("FacebookAdapter: Target Page specified. Navigating to %s (Name: %s)", target_page_url, target_page_name)
                if not target_page_url.startswith("http"):
                    target_page_url = "https://" + target_page_url
                self.page.goto(target_page_url, wait_until="domcontentloaded")
                self.page.wait_for_timeout(4000)

                switch_btn = self.page.locator(SELECTORS["switch_menu"]["switch_now_button"]).first
                if self._is_visible(switch_btn):
                    logger.info("FacebookAdapter: Found 'Switch now' button for the Page. Clicking...")
                    self._click_locator(switch_btn, "page switch button", timeout=10000)
                    self.page.wait_for_timeout(5000)
                    logger.info("FacebookAdapter: Switched to Page context successfully.")
                else:
                    logger.info("FacebookAdapter: No 'Switch now' button found on the Page. Attempting context switch via avatar menu...")
                    switched = self._switch_to_page_context(
                        target_page_name, target_page_url=target_page_url
                    )
                    if not switched:
                        logger.warning("FacebookAdapter: Avatar menu switch failed or unnecessary. Verifying active context...")

                # Reload target page after switch so Facebook applies identity (slow VPS / delayed UI).
                try:
                    self.page.goto(target_page_url, wait_until="domcontentloaded")
                    self.page.wait_for_timeout(5000)
                except Exception as e:
                    logger.warning("FacebookAdapter: Post-switch reload of target page failed: %s", e)

                # ── Bulletproof Context Verification ──
                # Ensure we don't accidentally post to the wrong page if the switch failed.
                logger.info("FacebookAdapter: Verifying active context matches target page...")
                verified_ok, norm_active, norm_target = (
                    self._verify_posting_context_matches_target(target_page_url or "")
                )

                if norm_target and norm_active and not verified_ok:
                    error_msg = f"Security abort: Active context ({norm_active}) does not match target page ({norm_target}). Preventing wrong-page post."
                    logger.error("FacebookAdapter: %s", error_msg)
                    return self._failure_result(
                        job.id,
                        "context_verification",
                        error_msg,
                        flow_mode,
                        entrypoint_used,
                        is_fatal=False
                    )
                else:
                    logger.info("FacebookAdapter: Context verified successfully. Safe to proceed.")
            else:
                logger.info("FacebookAdapter: Navigating to www.facebook.com (Personal Profile)")
                self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                self.page.wait_for_timeout(4000) # Give React time to render DOM

                # Explicitly switch back to Personal Profile if stuck on a Fanpage
                account_name = job.account.name if job.account else None
                if account_name:
                    logger.info("FacebookAdapter: Ensuring context is Personal Profile (%s)...", account_name)
                    # Use the explicit switch helper
                    self._switch_to_personal_profile(account_name)
                else:
                    logger.warning("FacebookAdapter: No account name found in job. Cannot explicitly switch to Personal Profile.")

            # 2. Login Check
            login_btn = self.page.locator('button[name="login"]').count() > 0
            email_in = self.page.locator('input[name="email"]').count() > 0
            nav_present = self.page.locator('div[role="navigation"]').count() > 0

            # Session Recovery: "Continue as XYZ" screen
            if not nav_present and not (login_btn and email_in):
                logger.info("FacebookAdapter: Navigation missing, checking for 'Continue as' session recovery screen...")
                # Use exact text matching to avoid clicking invisible parent divs
                recovery_btn = None
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
                            
                    if recovery_btn:
                        logger.info("FacebookAdapter: Found 'Continue/Tiếp tục' recovery button. Clicking...")
                        # Force click on the exact text node
                        try:
                            recovery_btn.click(force=True, timeout=5000)
                        except Exception:
                            self._click_locator(recovery_btn, "session recovery button", timeout=5000)
                            
                        self.page.wait_for_timeout(8000)
                        
                        # Sometimes we need to explicitly reload or wait for redirect
                        if "login" in self.page.url or "checkpoint" in self.page.url:
                            self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                            self.page.wait_for_timeout(5000)
                            
                        # Re-check navigation after clicking
                        nav_present = self.page.locator('div[role="navigation"]').count() > 0
                        if nav_present:
                            logger.info("FacebookAdapter: Session successfully recovered!")
                        else:
                            logger.warning("FacebookAdapter: Clicked recovery but navigation still missing.")
                except Exception as e:
                    logger.warning("FacebookAdapter: Error during session recovery click: %s", e)

            if (login_btn and email_in) or not nav_present:
                logger.error("FacebookAdapter: Account is logged out or requires verification.")
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
                logger.info("FacebookAdapter: Existing salt found in caption: %s", publish_salt)
            else:
                raw = f"{job.id}-{job.account_id}-{getattr(job, 'created_at', job.id)}"
                publish_salt = f"[ref:{_hashlib.sha256(raw.encode()).hexdigest()[:8]}]"
                publish_caption = f"{publish_caption}\n\n{publish_salt}" if publish_caption else publish_salt
                logger.info("FacebookAdapter: Auto-injected verification salt: %s", publish_salt)

            # ── Pre-scan existing reels to detect NEW ones after posting ──
            pre_existing_reels: list[str] = []
            try:
                if target_page_url:
                    pre_reels_url = target_page_url.rstrip('/') + '/reels_tab' if '?' not in target_page_url else target_page_url + '&sk=reels_tab'
                else:
                    pre_reels_url = "https://www.facebook.com/me/reels_tab"
                self.page.goto(pre_reels_url, wait_until="domcontentloaded", timeout=15000)
                self.page.wait_for_timeout(6000)
                for link in self.page.locator('a').all():
                    try:
                        href = link.get_attribute("href")
                        if href and "/reel/" in href and len(href) > 20:
                            clean = href.split("?")[0]
                            full = clean if clean.startswith("http") else "https://www.facebook.com" + clean
                            if full not in pre_existing_reels:
                                pre_existing_reels.append(full)
                    except Exception:
                        pass
                logger.info("FacebookAdapter: Pre-scanned %d existing reels before posting.", len(pre_existing_reels))
            except Exception as e:
                logger.warning("FacebookAdapter: Pre-scan reels failed: %s. Proceeding without.", e)

            # Navigate back to profile/home for composer entry
            if target_page_url:
                self.page.goto(target_page_url, wait_until="domcontentloaded")
            else:
                self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)

            logger.info("FacebookAdapter: Simulating feed browsing before compose...")
            human_scroll(self.page)
            reels = FacebookReelsPage(self.page)
            reels.neutralize_overlays()

            logger.info("FacebookAdapter: [Phase 3] Locating publish entry...")
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

            logger.info("FacebookAdapter: Uploading media from %s", job.media_path)
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
                logger.info("FacebookAdapter: Media attached. Waiting for preview...")
                self.page.wait_for_timeout(8000)
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
            pre_next_caption = is_page_post or entrypoint_used == "direct_reels"
            if pre_next_caption:
                caption_typed = reels.fill_caption(surface, publish_caption)

            logger.info("FacebookAdapter: Navigating through publish steps...")
            for step in range(6):
                surface = reels.find_active_publish_surface()
                post_button = reels.find_post_button(surface)
                if post_button:
                    logger.info("FacebookAdapter: Post/Đăng button found at step %d.", step)
                    break

                next_button = reels.find_next_button(surface)
                if not next_button:
                    logger.info("FacebookAdapter: No more Next/Tiếp buttons at step %d.", step)
                    break

                logger.info("FacebookAdapter: Clicking Next/Tiếp at step %d...", step + 1)
                if not self._click_locator(next_button, f"next button step {step + 1}", timeout=5000):
                    reels.log_surface_inventory(surface, f"next_click_failed_{step + 1}")
                    logger.warning("FacebookAdapter: Failed to click Next/Tiếp button but continuing. It might be a false positive (e.g. unclickable carousel arrow).")
                    break
                self.page.wait_for_timeout(3000)

                if pre_next_caption and not caption_typed:
                    surface = reels.find_active_publish_surface()
                    caption_typed = reels.fill_caption(surface, publish_caption)

            surface = reels.find_active_publish_surface()
            if not caption_typed:
                caption_typed = reels.fill_caption(surface, publish_caption)
                if not caption_typed and publish_caption.strip():
                    logger.warning("FacebookAdapter: Caption area not found in final surface. Proceeding without caption.")

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
                logger.info("FacebookAdapter: SAFE_MODE is enabled. Skipping final publish click.")
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


            logger.info("FacebookAdapter: Clicking POST button...")
            logger.info("FacebookAdapter: Waiting for Post button to become enabled...")
            try:
                post_handle = post_button.element_handle()
                if post_handle:
                    self.page.wait_for_function(
                        'el => el.getAttribute("aria-disabled") !== "true"',
                        arg=post_handle,
                        timeout=120000,
                    )
            except Exception as e:
                logger.warning("FacebookAdapter: Wait for button enabled timed out or failed: %s", e)

            logger.info("FacebookAdapter: Simulating pre-post hesitation...")
            pre_post_delay(self.page)

            if not self._click_locator(post_button, "post button", timeout=10000):
                return self._failure_result(
                    job.id,
                    "post_click",
                    "Failed to click the Post button.",
                    flow_mode,
                    entrypoint_used,
                )

            logger.info("FacebookAdapter: Post button clicked.")

            # ── Screenshot immediately after clicking Post ──
            self._capture_failure_artifacts(job.id, "post_clicked")

            submission_status = reels.wait_for_post_submission()
            logger.info("FacebookAdapter: Post submission result: %s", submission_status)

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

            self.page.wait_for_timeout(10000)

            # ── Post-publish verification: scan for new reel ──
            profile_url = target_page_url if target_page_url else "https://www.facebook.com/me"
            post_url = None
            try:
                # Nhanh: nếu FB redirect sang trang reel mới thì dùng luôn URL hiện tại
                try:
                    current_url = self.page.url or ""
                    normalized = self._normalize_post_url(current_url)
                    if normalized:
                        post_url = normalized
                        logger.info("FacebookAdapter: post_url captured from current URL after post: %s", post_url)
                except Exception:
                    pass

                if not post_url:
                    if target_page_url:
                        base_page = target_page_url.split("?")[0].rstrip("/")
                        reels_tab_urls = [
                            base_page + "/reels_tab",
                            base_page + "/reels",
                            base_page + "/videos",
                        ]
                    else:
                        reels_tab_urls = [
                            "https://www.facebook.com/me/reels_tab",
                            "https://www.facebook.com/me/reels",
                            "https://www.facebook.com/reel",
                        ]
                    salt = publish_salt
                    logger.info("FacebookAdapter: Scanning profile for salt '%s' to extract post_url...", salt)

                for attempt in range(4):
                    if post_url:
                        break
                    try:
                        self.page.goto(profile_url, wait_until="commit", timeout=15000)
                        self.page.wait_for_timeout(5000)
                    except Exception:
                        pass

                    try:
                        see_more_buttons = self.page.locator(
                            'div[role="button"]:has-text("See more"), '
                            'div[role="button"]:has-text("Xem thêm")'
                        ).all()
                        for btn in see_more_buttons[:5]:
                            try:
                                btn.click(timeout=2000)
                                self.page.wait_for_timeout(500)
                            except Exception:
                                pass
                        if see_more_buttons:
                            logger.info("FacebookAdapter: Expanded %d 'See more' buttons.", min(len(see_more_buttons), 5))
                    except Exception:
                        pass

                    if salt:
                        try:
                            full_text = self.page.evaluate("document.body.innerText")
                            if salt in full_text:
                                all_links = self.page.locator(
                                    'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"], a[href*="/share/r/"], a[href*="/share/v/"]'
                                ).all()
                                for link in all_links:
                                    try:
                                        parent = link.locator("xpath=ancestor::div[@data-pagelet or contains(@class,'x1yztbdb') or @role='article']").first
                                        if parent.count() > 0:
                                            parent_text = parent.inner_text()
                                            if salt in parent_text:
                                                href = link.get_attribute("href")
                                                normalized = self._normalize_post_url(href)
                                                if normalized:
                                                    post_url = normalized
                                                    logger.info("FacebookAdapter: post_url captured via main feed: %s", post_url)
                                                    break
                                    except Exception:
                                        continue
                                # Fallback: dùng JS tìm link /reel/ hoặc /share/ mà có ancestor chứa salt
                                if not post_url and full_text and salt in full_text:
                                    found_href = self.page.evaluate("""
                                        (salt) => {
                                            const links = document.querySelectorAll('a[href*="/reel/"], a[href*="/share/r/"], a[href*="/share/v/"]');
                                            for (const a of links) {
                                                let el = a;
                                                for (let i = 0; i < 20 && el; i++) {
                                                    if (el.textContent && el.textContent.indexOf(salt) >= 0) {
                                                        let h = a.getAttribute('href');
                                                        return h ? (h.startsWith('http') ? h : 'https://www.facebook.com' + h) : null;
                                                    }
                                                    el = el.parentElement;
                                                }
                                            }
                                            return null;
                                        }
                                    """, salt)
                                    if found_href:
                                        normalized = self._normalize_post_url(found_href)
                                        if normalized:
                                            post_url = normalized
                                            logger.info("FacebookAdapter: post_url captured via main feed (JS fallback): %s", post_url)
                            if post_url:
                                break
                        except Exception:
                            pass

                    unique_reels = []
                    for reels_tab_url in reels_tab_urls:
                        try:
                            self.page.goto(reels_tab_url, wait_until="domcontentloaded", timeout=15000)
                            self.page.wait_for_timeout(8000)
                        except Exception:
                            continue
                        reel_links = self.page.locator('a').all()
                        for link in reel_links:
                            try:
                                href = link.get_attribute("href")
                                if not href or len(href) < 20:
                                    continue
                                clean_url = href.split("?")[0]
                                if "/reel/" in clean_url or "/videos/" in clean_url:
                                    full = (clean_url if clean_url.startswith("http") else "https://www.facebook.com" + clean_url).rstrip("/")
                                    normalized = self._normalize_post_url(full)
                                    if normalized and normalized not in unique_reels:
                                        unique_reels.append(normalized)
                            except Exception:
                                pass
                        if unique_reels:
                            logger.info("FacebookAdapter: Found %d reel/video links on %s", len(unique_reels), reels_tab_url)
                            break

                    if salt:
                        recent_reels = unique_reels[:10]
                        for href in recent_reels:
                            full_url = href if href.startswith("http") else "https://www.facebook.com" + href
                            try:
                                self.page.goto(full_url, wait_until="commit", timeout=15000)
                                self.page.wait_for_timeout(5000)
                                html_content = self.page.evaluate("document.body.innerHTML")
                                text_content = self.page.evaluate("document.body.innerText")
                                if salt in html_content or salt in (text_content or ""):
                                    normalized = self._normalize_post_url(full_url)
                                    if normalized:
                                        post_url = normalized
                                        logger.info("FacebookAdapter: post_url captured via Reels tab deep dive: %s", post_url)
                                    break
                            except Exception:
                                continue

                        if post_url:
                            break
                    else:
                        # No salt — check if a NEW reel appeared (not in pre_existing_reels)
                        for reel_url in unique_reels:
                            normalized = self._normalize_post_url(reel_url)
                            if not normalized:
                                continue
                            if normalized not in pre_existing_reels:
                                post_url = normalized
                                logger.info("FacebookAdapter: NEW reel detected (not in pre-existing set): %s", post_url)
                                break
                        if post_url:
                            break
                        # If no new reel yet, wait and retry
                        if attempt < 3:
                            logger.info("FacebookAdapter: No new reel found on attempt %d/4. Waiting 10s before retry...", attempt + 1)
                            self.page.wait_for_timeout(10000)
                            continue
                        break

                    logger.info("FacebookAdapter: Salt not found on attempt %d/4. Waiting 10s before retry...", attempt + 1)
                    self.page.wait_for_timeout(10000)

                if not post_url:
                    logger.warning("FacebookAdapter: Could not verify post_url — post may not have been published.")

            except Exception as e:
                logger.warning("FacebookAdapter: Failed to capture post_url: %s", e)

            # ── Final screenshot for evidence ──
            self._capture_failure_artifacts(job.id, "post_verification_final")

            # If we couldn't find the new reel AND submission was ambiguous (timeout), treat as failure
            if not post_url and submission_status == "timeout":
                return self._failure_result(
                    job.id,
                    "post_verification_failed",
                    "Post submission timed out AND post could not be verified on profile. Likely NOT published.",
                    flow_mode,
                    entrypoint_used,
                )

            # If we found nothing but submission seemed ok, log warning but allow (FB processing delay)
            if not post_url:
                logger.warning("FacebookAdapter: Post URL not found but submission appeared successful. May be processing delay.")

            return PublishResult(
                ok=True,
                external_post_id=f"fb_post_{job.id}",
                details=self._build_publish_details(
                    flow_mode,
                    entrypoint_used,
                    post_url=post_url,
                    msg="Post submitted." if post_url else "Post submitted but URL not yet verified.",
                    verified=bool(post_url),
                ),
            )

        except Exception as e:
            logger.error("FacebookAdapter: Playwright encounter an error during publish: %s", e)
            logger.debug(traceback.format_exc())

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
        logger.info("FacebookAdapter: Checking timeline for unique footprint of job %s...", job.id)
        
        if not self.page:
            return PublishResult(ok=False, error="Playwright page is not initialized.", is_fatal=True)
            
        # Extract salt from caption if it exists `[ref:salt]` or `#v1234`
        match = re.search(r'\[ref:[a-zA-Z0-9]+\]|#v\d{4}', job.caption)
        if not match:
            logger.info("FacebookAdapter: No salt found in caption for idempotency check.")
            return PublishResult(ok=False, error="No salt for idempotency")
            
        salt = match.group(0)
        logger.info("FacebookAdapter: Scanning timeline for salt footprint: %s", salt)
        
        try:
            # Navigate to the user's own profile page
            self.page.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
            
            # Wait a few seconds for viewport content or lazy loaders
            self.page.wait_for_timeout(5000)
            
            # Extract all visible text from body
            body_text = self.page.locator("body").inner_text()
            
            if salt in body_text:
                logger.info("FacebookAdapter: Footprint %s found on timeline! Attempting to extract post_url...", salt)
                
                post_url = None
                all_links = self.page.locator(
                    'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"], a[href*="/share/r/"], a[href*="/share/v/"]'
                ).all()
                
                for link in all_links:
                    try:
                        parent_text = link.locator("xpath=ancestor::div[contains(@class,'x1yztbdb')]").first.inner_text()
                        if salt in parent_text:
                            href = link.get_attribute("href")
                            post_url = href if href.startswith("http") else "https://www.facebook.com" + href
                            logger.info("FacebookAdapter: Recovered post_url via idempotency scan: %s", post_url)
                            break
                    except Exception:
                        continue
                        
                return PublishResult(
                    ok=True,
                    external_post_id=f"fb_post_{job.id}_recovered",
                    details={"msg": f"Recovered via Timeline Scan. Salt: {salt}", "post_url": post_url}
                )
            else:
                logger.info("FacebookAdapter: Footprint not found on timeline.")
                return PublishResult(ok=False, error="Footprint not found")
                
        except Exception as e:
            logger.error("FacebookAdapter: Playwright error during check_published_state: %s", e)
            return PublishResult(ok=False, error=f"Playwright error: {e}", is_fatal=False)
        
    def close_session(self):
        logger.info("FacebookAdapter: Closing browser context securely.")
        
        # Safely shut down all Playwright resources in order
        if self.page:
            try:
                self.page.close()
            except Exception as e:
                logger.warning("Failed to close page: %s", e)
            finally:
                self.page = None
                
        if self.context:
            try:
                self.context.close()
            except Exception as e:
                logger.warning("Failed to close context: %s", e)
            finally:
                self.context = None
                
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                logger.warning("Failed to stop playwright engine: %s", e)
            finally:
                self.playwright = None

    # ─── Auto Comment (Phase 16) ───────────────────────────
    
    CTA_POOL = [
        "🔗 Link mình để ở đây nè 👇\n{link}",
        "Ai cần thì vào link này nhé\n{link}",
        "Xem chi tiết sản phẩm 👉 {link}",
        "Link đây mọi người ơi\n{link}",
        "Mình share link ở đây nha\n{link}",
        "👇 Link bên dưới nhé\n{link}",
    ]
    
    @staticmethod
    def _wrap_with_cta(raw_comment: str) -> str:
        """Wrap the comment text with a random CTA template for anti-detection."""
        
        # If user already wrote a full comment (has letters/emoji), use as-is
        lines = [l.strip() for l in raw_comment.strip().split('\n') if l.strip()]
        
        # Check if it's just raw links
        all_links = all(l.startswith('http') for l in lines)
        
        if all_links and lines:
            # Wrap with random CTA
            link_text = '\n'.join(lines)
            template = random.choice(FacebookAdapter.CTA_POOL)
            return template.replace('{link}', link_text)
        else:
            # User wrote custom comment text, use as-is
            return raw_comment.strip()
    
    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        """
        Navigate to a published post and add a comment.
        Non-fatal: failure returns ok=False but should NOT crash the parent job.
        """
        
        logger.info("FacebookAdapter: Posting comment on %s", post_url)
        
        if not self.page:
            return PublishResult(ok=False, error="Page not initialized", is_fatal=False)
        
        try:
            # 1. Navigate to the post
            self.page.goto(post_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(random.randint(3000, 5000))
            
            # 2. Casual scroll (human behavior)
            human_scroll(self.page)
            self.page.wait_for_timeout(random.randint(1000, 2000))
            
            # 3. Find comment box (multiple selectors for i18n robustness)
            comment_selectors = [
                "div[aria-label='Write a comment']",
                "div[aria-label='Write a comment…']",
                "div[aria-label='Viết bình luận']",
                "div[aria-label='Viết bình luận…']",
                "div[aria-label='Viết bình luận...']",
                "div[contenteditable='true'][role='textbox']",
            ]
            
            comment_box = None
            for sel in comment_selectors:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    comment_box = loc
                    logger.info("FacebookAdapter: Found comment box via: %s", sel)
                    break
            
            if not comment_box:
                logger.warning("FacebookAdapter: Comment box not found on post page.")
                return PublishResult(ok=False, error="Comment box not found", is_fatal=False)
            
            # 4. Click to focus comment box
            comment_box.scroll_into_view_if_needed()
            self.page.wait_for_timeout(500)
            comment_box.click()
            self.page.wait_for_timeout(random.randint(500, 1000))
            
            # 5. Wrap with random CTA and type
            final_comment = self._wrap_with_cta(comment_text)
            human_type(self.page, final_comment)
            
            # 6. Random pause before submit (1–3 seconds)
            self.page.wait_for_timeout(random.randint(1000, 3000))
            
            # 7. Submit via Enter
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(random.randint(2000, 4000))
            
            # 8. Post-comment human behavior: scroll a bit
            human_scroll(self.page)
            
            logger.info("FacebookAdapter: Comment posted successfully on %s", post_url)
            return PublishResult(ok=True, details={"comment": final_comment})
            
        except Exception as e:
            logger.warning("FacebookAdapter: Failed to post comment: %s", e)
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
        if not self.page:
            return (
                False,
                "",
                self._normalize_fb_profile_url_for_compare(target_page_url or ""),
            )
        try:
            self.page.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)
            active_url = self.page.url
        except Exception as e:
            logger.warning("FacebookAdapter: /me check failed: %s", e)
            return (
                False,
                "",
                self._normalize_fb_profile_url_for_compare(target_page_url or ""),
            )
        nt = self._normalize_fb_profile_url_for_compare(target_page_url or "")
        na = self._normalize_fb_profile_url_for_compare(active_url)
        ok = self._urls_indicate_same_fb_page_context(target_page_url or "", active_url)
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
                    logger.info(
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
        except Exception:
            pass
        try:
            if not row.is_visible(timeout=3000):
                logger.info("FacebookAdapter: Switcher row not visible (%s)", label)
                return False
        except Exception:
            return False
        # Cover images often intercept normal click — force first to avoid 8s timeout.
        try:
            row.click(force=True, timeout=5000)
            logger.info("FacebookAdapter: Switcher row force click OK (%s)", label)
            return True
        except Exception as e:
            logger.info("FacebookAdapter: Switcher row force click failed (%s): %s", label, e)
        try:
            row.click(timeout=8000)
            logger.info("FacebookAdapter: Switcher row normal click OK (%s)", label)
            return True
        except Exception as e:
            logger.info("FacebookAdapter: Switcher row normal click failed (%s): %s", label, e)
        try:
            row.evaluate("el => el.click()")
            logger.info("FacebookAdapter: Switcher row evaluate click OK (%s)", label)
            return True
        except Exception as e:
            logger.info("FacebookAdapter: Switcher row evaluate click failed (%s): %s", label, e)
        try:
            row.focus(timeout=5000)
            self.page.wait_for_timeout(200)
            self.page.keyboard.press("Enter")
            logger.info("FacebookAdapter: Switcher row Enter OK (%s)", label)
            return True
        except Exception as e:
            logger.info("FacebookAdapter: Switcher row Enter failed (%s): %s", label, e)
        return False

    def _reopen_profile_switch_dialog(self, avatar_btn: Locator) -> Locator:
        """Re-open avatar menu → optional See all → return the profile switcher dialog."""
        self._click_locator(avatar_btn, "avatar menu", timeout=5000)
        self.page.wait_for_timeout(2000)
        see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first
        if see_all.count() > 0 and see_all.is_visible():
            see_all.click()
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

        logger.info("FacebookAdapter: Initiating account switch via avatar menu...")
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
                logger.warning("FacebookAdapter: Could not find avatar menu icon.")
                return False

            self._click_locator(avatar_btn, "avatar menu", timeout=5000)
            self.page.wait_for_timeout(2000)

            # 2. Look for "Xem tất cả trang cá nhân" or direct Page name
            see_all = self.page.locator(SELECTORS["switch_menu"]["see_all_profiles"]).first

            if see_all.count() > 0 and see_all.is_visible():
                see_all.click()
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
                            logger.info(
                                "FacebookAdapter: Switching via menu link for page id %s (%s)...",
                                page_id,
                                pattern.split("[")[0],
                            )
                            link.scroll_into_view_if_needed()
                            try:
                                link.click(timeout=8000)
                            except Exception:
                                logger.info(
                                    "FacebookAdapter: Link click timed out, trying force..."
                                )
                                link.click(force=True)
                            try:
                                dialog.wait_for(state="hidden", timeout=15000)
                            except Exception:
                                logger.warning(
                                    "FacebookAdapter: Switcher dialog still visible after id link click."
                                )
                            self.page.wait_for_timeout(3000)
                            if not target_page_url or self._verify_posting_context_matches_target(
                                target_page_url
                            )[0]:
                                logger.info("FacebookAdapter: Switch command sent (id link).")
                                return True
                            logger.warning(
                                "FacebookAdapter: Id link click did not verify posting context; "
                                "reopening switcher for fallbacks."
                            )
                            dialog = self._reopen_profile_switch_dialog(avatar_btn)
                            break
                    except Exception:
                        continue
                if not id_had_visible_link:
                    logger.info(
                        "FacebookAdapter: No visible href control for page id %s inside switcher dialog.",
                        page_id,
                    )

            if target_page_name:
                if self._try_click_switcher_aria_label(dialog, target_page_name):
                    try:
                        # Short wait: wrong clicks (carousel) often leave dialog open; verify + 3a2b follow.
                        dialog.wait_for(state="hidden", timeout=6000)
                    except Exception:
                        logger.warning(
                            "FacebookAdapter: Switcher dialog still visible after aria-label click."
                        )
                    self.page.wait_for_timeout(2500)
                    if not target_page_url:
                        logger.info(
                            "FacebookAdapter: Switch command sent (aria-label switch button)."
                        )
                        return True
                    ok_ctx, _, _ = self._verify_posting_context_matches_target(target_page_url)
                    if ok_ctx:
                        logger.info(
                            "FacebookAdapter: Switch command sent (aria-label switch button)."
                        )
                        return True
                    logger.warning(
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
                        logger.info(
                            "FacebookAdapter: 3a2b zero %s rows matching '%s' (norm: %s).",
                            row_sel,
                            target_page_name,
                            tn_norm,
                        )
                        continue
                    if cnt > 12:
                        logger.info(
                            "FacebookAdapter: 3a2b skip %s (count=%s too many, likely false positives).",
                            row_sel,
                            cnt,
                        )
                        continue
                    logger.info(
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
                            except Exception:
                                pass
                    if not activated:
                        indices = list(range(cnt))
                        if row_sel == "div[role=\"button\"]" and cnt >= 2:
                            indices = list(range(cnt - 1, -1, -1))
                            logger.info(
                                "FacebookAdapter: 3a2b trying button row indices reversed (count=%s).",
                                cnt,
                            )
                        for i in indices:
                            r = rows_with_match[i]
                            try:
                                if r.get_attribute("aria-checked") == "true":
                                    logger.info(
                                        "FacebookAdapter: Skip switcher row %s (already selected).",
                                        i,
                                    )
                                    continue
                            except Exception:
                                pass
                            if self._activate_profile_switcher_row(r, f"{row_sel}-{i}"):
                                activated = True
                                break
                    if activated:
                        try:
                            dialog.wait_for(state="hidden", timeout=15000)
                        except Exception:
                            logger.warning(
                                "FacebookAdapter: Switcher dialog still visible after 3a2b."
                            )
                        self.page.wait_for_timeout(3000)
                        logger.info(
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
                                logger.info(
                                    "FacebookAdapter: %s %s match count=%s but first not visible; skipping.",
                                    scope_name,
                                    role,
                                    n,
                                )
                                continue
                            logger.info(
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
                                logger.warning(
                                    "FacebookAdapter: Switcher dialog still visible after "
                                    "%s click (scope=%s).",
                                    role,
                                    scope_name,
                                )
                            self.page.wait_for_timeout(3000)
                            logger.info(
                                "FacebookAdapter: Switch command sent (%s/%s).",
                                role,
                                scope_name,
                            )
                            return True
                        except Exception as e:
                            logger.debug(
                                "FacebookAdapter: role=%s scope=%s skipped: %s",
                                role,
                                scope_name,
                                e,
                            )

            # 3b. Find the target profile in the list (name match); prefer row that contains page id in href.
            if target_page_name:
                logger.info("FacebookAdapter: Looking for exact profile name '%s' in switch menu...", target_page_name)
                
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
                    except Exception:
                        pass

                found_el = None
                if page_id and name_candidates:
                    for el in name_candidates:
                        try:
                            if self._switcher_row_has_page_id(el, page_id):
                                found_el = el
                                logger.info(
                                    "FacebookAdapter: Using name match row containing page id %s (href or markup).",
                                    page_id,
                                )
                                break
                        except Exception:
                            pass
                    if not found_el:
                        logger.warning(
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
                                    logger.warning(
                                        "FacebookAdapter: Switcher dialog still visible after "
                                        "multi-candidate activate."
                                    )
                                self.page.wait_for_timeout(3000)
                                logger.info(
                                    "FacebookAdapter: Switch command sent (multi-candidate %s).",
                                    rev_i,
                                )
                                return True
                        found_el = name_candidates[-1]
                        logger.info(
                            "FacebookAdapter: Using last name match as fallback click target "
                            "(inner-most / list order)."
                        )
                elif name_candidates:
                    found_el = name_candidates[-1]
                    logger.info(
                        "FacebookAdapter: No page id filter; using last of %s name matches.",
                        len(name_candidates),
                    )
                
                if found_el:
                    logger.info("FacebookAdapter: Clicking explicit profile match for '%s'...", target_page_name)
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
                        logger.info("FacebookAdapter: Normal click timed out, attempting force click...")
                        btn_to_click.click(force=True)
                    try:
                        dialog.wait_for(state="hidden", timeout=15000)
                    except Exception:
                        logger.warning(
                            "FacebookAdapter: Switcher dialog still visible after row click."
                        )
                    self.page.wait_for_timeout(3000)
                    logger.info("FacebookAdapter: Switch command sent.")
                    return True
                else:
                    logger.warning("FacebookAdapter: Target profile '%s' not found. Dumping HTML for debugging...", target_page_name)
                    try:
                        body_html = self.page.evaluate("document.body.innerHTML")
                        safe_name = target_page_name.replace(' ', '_').lower()
                        dump_dir = BASE_DIR / "tests"
                        dump_dir.mkdir(parents=True, exist_ok=True)
                        with open(dump_dir / f"fb_switch_menu_{safe_name}.html", "w", encoding="utf-8") as f:
                            f.write(body_html)
                    except Exception as e:
                        logger.error("Failed to dump HTML: %s", e)
                    
                    logger.error("FacebookAdapter: Could not find explicitly requested profile '%s'. Aborting switch.", target_page_name)
                    return False
                    
            # Fallback ONLY if no target_page_name was specified (e.g. just switch to ANY page)
            profile_items = self.page.locator(SELECTORS["switch_menu"]["any_profile_btn"]).all()
            if profile_items:
                logger.info("FacebookAdapter: Clicking first available profile in switch menu...")
                try:
                    profile_items[0].click(timeout=5000)
                except Exception:
                    logger.info("FacebookAdapter: Normal click timed out, attempting force click...")
                    profile_items[0].click(force=True)
                self.page.wait_for_timeout(12000)  # Switch can take time (VPS / slow FB)
                logger.info("FacebookAdapter: Switch command sent.")
                return True
            
        except Exception as e:
            logger.error("FacebookAdapter: Switch failed: %s", e)
            
        return False
