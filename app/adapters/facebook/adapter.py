import logging
import os
from pathlib import Path
import random
import re
import traceback
from typing import Any
from app.config import SAFE_MODE, LOGS_DIR
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page, Locator, TimeoutError
from app.adapters.contracts import AdapterInterface, PublishResult
from app.database.models import Job
from app.utils.human_behavior import human_type, human_scroll, pre_post_delay
import json
import unicodedata
from collections import deque

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
        
        try:
            self.playwright = sync_playwright().start()
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                args=[
                    '--disable-dev-shm-usage',  # Tránh lỗi thiếu RAM share (/dev/shm) trên Linux/WSL
                    '--no-sandbox',
                    '--disable-gpu',            # Tắt Hardware GPU, tiết kiệm RAM
                    '--js-flags=--lite-mode',   # Ép engine V8 JS chạy chế độ tiết kiệm RAM
                    '--disable-features=SitePerProcess', # Tắt Isolation mỗi tab 1 process (tiết kiệm cực nhiều RAM)
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-sync'
                ]
            )
            # persistent context starts with 1 blank page automatically
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            # Set a rigorous timeout to prevent silent worker hangs
            self.page.set_default_timeout(60000)
            return True
            
        except Exception as e:
            logger.error(f"FacebookAdapter: Failed to bootstrap playwright session: {e}")
            self.close_session()
            return False

    PERSONAL_REELS_LABELS = ("Thước phim", "Reels", "Reel", "Video ngắn", "Create reel")
    PAGE_REELS_LABELS = ("Thước phim", "Reels", "Reel", "Video")
    NEXT_BUTTON_LABELS = ("Tiếp", "Next")
    POST_BUTTON_LABELS = ("Đăng", "Post", "Đăng bài", "Publish", "Chia sẻ", "Share", "Đăng Thước phim")

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

    def _find_active_publish_surface(self) -> Page | Locator:
        if not self.page:
            raise RuntimeError("Playwright page is not initialized.")

        dialogs = self.page.locator("div[role='dialog']")
        for idx in range(dialogs.count() - 1, -1, -1):
            dialog = dialogs.nth(idx)
            if self._is_visible(dialog):
                return dialog

        file_inputs = self.page.locator("input[type='file']")
        for idx in range(file_inputs.count() - 1, -1, -1):
            dialog = file_inputs.nth(idx).locator("xpath=ancestor::div[@role='dialog'][1]").first
            if self._is_visible(dialog):
                return dialog

        return self.page

    def _surface_has_upload_input(self, surface: Page | Locator) -> bool:
        try:
            return surface.locator("input[type='file']").count() > 0
        except Exception:
            return False

    def _looks_like_publish_surface(self, surface: Page | Locator | None = None) -> bool:
        if surface is None:
            surface = self._find_active_publish_surface()

        if self._surface_has_upload_input(surface):
            return True
        if self._find_next_button(surface) or self._find_post_button(surface):
            return True

        try:
            return surface.locator('div[contenteditable="true"], textarea').count() > 0
        except Exception:
            return False

    def _log_surface_inventory(self, surface: Page | Locator, stage: str):
        visible_buttons: list[str] = []
        buttons = surface.locator("button, div[role='button'], a[role='button']")
        for idx in range(min(buttons.count(), 20)):
            button = buttons.nth(idx)
            if not self._is_visible(button):
                continue
            try:
                label = (
                    (button.get_attribute("aria-label") or "")
                    or (button.inner_text() or "")
                ).strip()
            except Exception:
                continue
            if label and label not in visible_buttons:
                visible_buttons.append(label)
            if len(visible_buttons) >= 8:
                break

        file_inputs: list[str] = []
        inputs = surface.locator("input[type='file']")
        for idx in range(min(inputs.count(), 10)):
            input_el = inputs.nth(idx)
            try:
                accept = (input_el.get_attribute("accept") or "").strip() or "(no accept)"
            except Exception:
                accept = "(unreadable)"
            file_inputs.append(accept)

        textboxes: list[str] = []
        boxes = surface.locator('div[contenteditable="true"], div[role="textbox"], textarea')
        for idx in range(min(boxes.count(), 10)):
            box = boxes.nth(idx)
            if not self._is_visible(box):
                continue
            try:
                placeholder = (
                    (box.get_attribute("aria-placeholder") or "")
                    or (box.get_attribute("placeholder") or "")
                    or "(no placeholder)"
                ).strip()
            except Exception:
                placeholder = "(unreadable)"
            textboxes.append(placeholder)
            if len(textboxes) >= 5:
                break

        logger.info(
            "FacebookAdapter: [%s] Surface inventory | buttons=%s | file_inputs=%s | textboxes=%s",
            stage,
            visible_buttons or ["(none)"],
            file_inputs or ["(none)"],
            textboxes or ["(none)"],
        )

    def _restore_origin(self, origin_url: str):
        if not self.page:
            return
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(800)
        except Exception:
            pass

        if self.page.url != origin_url:
            try:
                self.page.goto(origin_url, wait_until="domcontentloaded")
                self.page.wait_for_timeout(3000)
            except Exception as e:
                logger.debug("FacebookAdapter: Failed to restore origin URL %s: %s", origin_url, e)

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

    def _attempt_entry_click(self, locator: Locator, description: str, origin_url: str) -> bool:
        if not self._click_locator(locator, description):
            return False

        if self.page:
            self.page.wait_for_timeout(2500)

        surface = self._find_active_publish_surface()
        if self._looks_like_publish_surface(surface):
            return True

        if self.page:
            self.page.wait_for_timeout(1500)
        surface = self._find_active_publish_surface()
        if self._looks_like_publish_surface(surface):
            return True

        logger.info("FacebookAdapter: %s did not open a publish surface. Restoring origin...", description)
        self._restore_origin(origin_url)
        return False

    def _try_entry_labels(self, labels: tuple[str, ...], origin_url: str, flow_name: str) -> bool:
        if not self.page:
            return False

        for label in labels:
            candidates = [
                self.page.get_by_role("button", name=label, exact=False).first,
                self.page.get_by_role("link", name=label, exact=False).first,
                self.page.get_by_text(label, exact=False).first,
            ]
            for candidate in candidates:
                if not self._is_visible(candidate):
                    continue
                if self._attempt_entry_click(candidate, f"{flow_name} entry '{label}'", origin_url):
                    return True
        return False

    def _try_entry_selectors(self, selectors: tuple[str, ...], origin_url: str, flow_name: str) -> bool:
        if not self.page:
            return False

        for selector in selectors:
            candidate = self.page.locator(selector).first
            if not self._is_visible(candidate):
                continue
            if self._attempt_entry_click(candidate, f"{flow_name} selector {selector}", origin_url):
                return True
        return False

    def _open_personal_composer_fallback(self) -> bool:
        if not self.page:
            return False

        logger.info("FacebookAdapter: [PERSONAL MODE] Falling back to generic composer.")
        origin_url = self.page.url
        composer_locators = [
            self.page.locator("div[data-pagelet='FeedComposer'] div[role='button']").first,
            self.page.locator("div[aria-describedby][role='button']").first,
            self.page.get_by_text("on your mind", exact=False).first,
            self.page.get_by_text("đang nghĩ gì", exact=False).first,
            self.page.get_by_text("Chia sẻ suy nghĩ", exact=False).first,
        ]

        for composer in composer_locators:
            if not self._is_visible(composer):
                continue
            if self._click_locator(composer, "personal composer fallback", timeout=10000):
                self.page.wait_for_timeout(3000)
                if self._looks_like_publish_surface():
                    return True
                self._restore_origin(origin_url)
        return False

    def _open_personal_reels_entry(self) -> str | None:
        if not self.page:
            return None

        origin_url = self.page.url
        if self._try_entry_labels(self.PERSONAL_REELS_LABELS, origin_url, "personal"):
            return "direct_reels"

        direct_reels_selectors = (
            'a[href*="/reels/create"]',
            'a[href*="/reel/create"]',
            'a[href*="create"][href*="reel"]',
            'a[href*="create"][href*="video"]',
            'div[role="button"][aria-label*="Reel"]',
            'div[role="button"][aria-label*="reel"]',
        )
        if self._try_entry_selectors(direct_reels_selectors, origin_url, "personal"):
            return "direct_reels"

        self._restore_origin(origin_url)
        if self._open_personal_composer_fallback():
            return "composer_fallback"
        return None

    def _open_page_reels_entry(self) -> str | None:
        if not self.page:
            return None

        origin_url = self.page.url
        if self._try_entry_labels(self.PAGE_REELS_LABELS, origin_url, "page"):
            return "direct_reels"

        page_selectors = (
            'a[href*="/reels/create"]',
            'a[href*="/reel/create"]',
            'a[href*="create"][href*="reel"]',
        )
        if self._try_entry_selectors(page_selectors, origin_url, "page"):
            return "direct_reels"
        return None

    def _select_file_input(self, surface: Page | Locator, media_path: str) -> Locator | None:
        candidates = surface.locator("input[type='file']")
        if candidates.count() == 0 and self.page:
            candidates = self.page.locator("input[type='file']")

        is_video = os.path.splitext(media_path)[1].lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")
        chosen: Locator | None = None

        for idx in range(candidates.count()):
            candidate = candidates.nth(idx)
            accept_attr = (candidate.get_attribute("accept") or "").lower()
            if is_video and "video" in accept_attr:
                logger.info("FacebookAdapter: Selected file input with accept='%s' for video upload.", accept_attr[:80])
                return candidate
            if not is_video and ("image" in accept_attr or accept_attr == "") and chosen is None:
                chosen = candidate

        if chosen:
            logger.info("FacebookAdapter: Selected file input fallback for non-video upload.")
            return chosen

        if candidates.count() > 0:
            logger.info("FacebookAdapter: Using first file input as final fallback.")
            return candidates.first
        return None

    def _find_next_button(self, surface: Page | Locator) -> Locator | None:
        candidates = [
            surface.get_by_role("button", name="Tiếp", exact=True).first,
            surface.get_by_role("button", name="Next", exact=True).first,
            surface.get_by_role("button", name="Tiếp", exact=False).first,
            surface.get_by_role("button", name="Next", exact=False).first,
            surface.locator('button:has-text("Tiếp")').first,
            surface.locator('button:has-text("Next")').first,
            surface.locator('div[role="button"][aria-label="Tiếp"], div[role="button"][aria-label="Next"]').first,
            surface.get_by_text("Tiếp", exact=True).first,
            surface.get_by_text("Next", exact=True).first,
        ]
        return self._find_first_visible(candidates)

    # Schedule-related keywords to EXCLUDE from post button matching
    SCHEDULE_POISON_WORDS = ("lịch đăng", "schedule", "lên lịch", "lịch", "đăng sau")

    def _is_schedule_button(self, locator: Locator) -> bool:
        """Check if a button is actually a schedule toggle, not the Post button."""
        try:
            btn_text = (locator.inner_text() or "").lower()
            return any(word in btn_text for word in self.SCHEDULE_POISON_WORDS)
        except Exception:
            return False

    def _find_post_button(self, surface: Page | Locator) -> Locator | None:
        # ── Strategy 1: EXACT text match (highest priority, avoids schedule confusion) ──
        for label in self.POST_BUTTON_LABELS:
            exact_candidates = [
                surface.get_by_role("button", name=label, exact=True).first,
                surface.locator(f'div[role="button"][aria-label="{label}"]').first,
                surface.locator(f'button[aria-label="{label}"]').first,
            ]
            for candidate in exact_candidates:
                if self._is_visible(candidate) and not self._is_schedule_button(candidate):
                    logger.info("FacebookAdapter: Post button matched via exact label '%s'", label)
                    return candidate

        # ── Strategy 2: Fuzzy match with schedule filter ──
        fuzzy_candidates: list[Locator] = []
        for label in self.POST_BUTTON_LABELS:
            fuzzy_candidates.append(
                surface.get_by_role("button", name=label, exact=False).first,
            )
        fuzzy_candidates.extend(
            [
                surface.locator('div[role="button"]:has-text("Đăng")').first,
                surface.locator('div[role="button"]:has-text("Post")').first,
                surface.locator('button:has-text("Đăng")').first,
                surface.locator('button:has-text("Post")').first,
            ]
        )
        for candidate in fuzzy_candidates:
            if self._is_visible(candidate) and not self._is_schedule_button(candidate):
                logger.info("FacebookAdapter: Post button matched via fuzzy search")
                return candidate

        logger.warning("FacebookAdapter: No post button found (all candidates were schedule buttons or invisible)")
        return None

    def _type_caption_in_surface(self, surface: Page | Locator, caption: str) -> bool:
        if not caption:
            return True

        candidates = [
            surface.locator('div[contenteditable="true"][aria-placeholder*="reel"]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="Describe"]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="thước phim"]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="Mô tả"]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="nghĩ"]').first,
            surface.locator('div[role="textbox"][contenteditable="true"]').first,
            surface.locator('div[role="textbox"]').first,
            surface.locator('div[contenteditable="true"]').first,
            surface.locator("textarea").first,
        ]

        signature = caption[:24].strip()
        for candidate in candidates:
            if not self._is_visible(candidate):
                continue

            try:
                current_text = (candidate.inner_text() or "").strip()
            except Exception:
                current_text = ""

            if signature and current_text and signature in current_text:
                logger.info("FacebookAdapter: Caption already present in active surface.")
                return True

            if current_text and signature and signature not in current_text:
                logger.debug("FacebookAdapter: Skipping non-empty textbox that does not look like caption.")
                continue

            try:
                candidate.click(force=True, timeout=3000)
                if self.page:
                    self.page.wait_for_timeout(500)
                human_type(self.page, caption)
                if self.page:
                    self.page.wait_for_timeout(800)
                logger.info("FacebookAdapter: Caption typed into active publish surface.")
                return True
            except Exception as e:
                logger.debug("FacebookAdapter: Caption typing candidate failed: %s", e)

        return False

    # Error signals that Facebook shows when a post fails silently
    FB_ERROR_SIGNALS = (
        "something went wrong", "đã xảy ra lỗi", "couldn't post",
        "không thể đăng", "try again", "thử lại", "upload failed",
        "tải lên thất bại", "couldn't share", "không thể chia sẻ",
        "an error occurred", "lỗi đã xảy ra",
    )

    def _check_page_for_errors(self) -> str | None:
        """Check if Facebook is showing an error message after post attempt."""
        if not self.page:
            return None
        try:
            body_text = self.page.evaluate("document.body.innerText").lower()
            for signal in self.FB_ERROR_SIGNALS:
                if signal in body_text:
                    return signal
        except Exception:
            pass
        return None

    def _wait_for_post_submission(self) -> str:
        """
        Wait for post submission dialog to close.
        Returns: 'success' | 'error' | 'timeout'
        """
        if not self.page:
            return "error"

        logger.info("FacebookAdapter: Waiting for post submission to complete (dialog to close)...")
        for tick in range(60):
            self.page.wait_for_timeout(5000)

            # --- Handle "Lựa chọn lịch đăng" (Schedule) modal ---
            # Facebook sometimes shows a scheduling upsell modal after clicking Post.
            # We detect it and dismiss it so the post submits immediately.
            try:
                schedule_signals = ["Lựa chọn lịch đăng", "Choose schedule", "Lên lịch đăng sau", "Schedule for later"]
                dialogs = self.page.locator('div[role="dialog"]').all()
                for dlg in dialogs:
                    if dlg.is_visible():
                        dlg_text = dlg.inner_text()
                        if any(sig in dlg_text for sig in schedule_signals):
                            logger.warning("FacebookAdapter: Detected schedule modal! Dismissing...")
                            dismissed = False
                            # Strategy 1: Try clicking the back arrow by aria-label
                            for aria in ["Quay lại", "Back"]:
                                back_btn = dlg.locator(f'div[role="button"][aria-label="{aria}"]').first
                                if self._is_visible(back_btn):
                                    self._click_locator(back_btn, "schedule modal back button")
                                    dismissed = True
                                    break
                            # Strategy 2: Try the X close button
                            if not dismissed:
                                close_btn = dlg.locator('div[aria-label="Đóng"][role="button"], div[aria-label="Close"][role="button"]').first
                                if self._is_visible(close_btn):
                                    self._click_locator(close_btn, "schedule modal close button")
                                    dismissed = True
                            # Strategy 3: Escape key as last resort
                            if not dismissed:
                                logger.info("FacebookAdapter: Using Escape to dismiss schedule modal.")
                                self.page.keyboard.press("Escape")
                            self.page.wait_for_timeout(3000)
                            logger.info("FacebookAdapter: Schedule modal dismissed. Continuing wait...")
                            break
            except Exception as e:
                logger.warning("FacebookAdapter: Error handling schedule modal: %s", e)

            # Check for error signals every few ticks
            if tick > 0 and tick % 3 == 0:
                err_signal = self._check_page_for_errors()
                if err_signal:
                    logger.error("FacebookAdapter: Detected error signal after post: '%s'", err_signal)
                    return "error"

            if self.page.locator('div[role="dialog"]').count() == 0:
                logger.info("FacebookAdapter: Dialog closed and disappeared naturally.")
                # Double-check for errors on the page after dialog closes
                self.page.wait_for_timeout(2000)
                err_signal = self._check_page_for_errors()
                if err_signal:
                    logger.error("FacebookAdapter: Error detected after dialog close: '%s'", err_signal)
                    return "error"
                return "success"

            dismiss_button = self._find_first_visible(
                [
                    self.page.get_by_role("button", name="Đóng", exact=False).first,
                    self.page.get_by_role("button", name="Xong", exact=False).first,
                    self.page.get_by_role("button", name="Lúc khác", exact=False).first,
                    self.page.locator('div[aria-label="Đóng"], div[aria-label="Xong"]').first,
                ]
            )
            if dismiss_button:
                logger.info("FacebookAdapter: Found Success/Dismiss button, clicking it to unblock...")
                self._click_locator(dismiss_button, "publish dismiss button")
                self.page.wait_for_timeout(2000)
                err_signal = self._check_page_for_errors()
                if err_signal:
                    logger.error("FacebookAdapter: Error detected after dismiss: '%s'", err_signal)
                    return "error"
                return "success"

        logger.warning("FacebookAdapter: Post submission wait hit timeout window without a strong completion signal.")
        return "timeout"

    def _neutralize_overlays(self):
        if not self.page:
            return

        logger.info("FacebookAdapter: [Phase 2] Neutralizing overlays...")
        try:
            modal_close = self.page.locator('div[aria-label="Close"], div[aria-label="Đóng"]').filter(has_text="").first
            if self._is_visible(modal_close):
                logger.info("FacebookAdapter: Found intercepting modal close button. Clicking...")
                self._click_locator(modal_close, "overlay close button")
                self.page.wait_for_timeout(1000)

            blocking_dialogs = self.page.locator("div[role='dialog']")
            if blocking_dialogs.count() > 0:
                logger.info("FacebookAdapter: Waiting for dialog overlays to detach...")
                blocking_dialogs.first.wait_for(state="hidden", timeout=5000)
        except Exception as e:
            logger.debug("FacebookAdapter: Modal neutralization step encountered an issue: %s", e)

    def _switch_to_personal_profile(self, account_name: str) -> bool:
        """
        Forces the browser context to switch back to the personal profile matching account_name.
        This prevents the system from being stuck in a Fanpage context from a previous job.
        """
        if not self.page:
            return False

        try:
            # 1. Open the top right account menu
            account_menu_btn = self.page.locator('div[role="banner"] div[role="button"]').last
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
            target_name = account_name.lower().strip()
            # Find all possible profile items across the DOM (popups often render outside the main tree)
            profile_items = self.page.locator('div[role="button"], div[role="menuitem"], div[role="radio"], div[role="menuitemradio"]').all()
            
            found_el = None
            for el in profile_items:
                try:
                    text = el.inner_text().strip()
                    if text and len(text) > 3:
                        # Normalize accents
                        normalized = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
                        normalized = normalized.replace('đ', 'd').replace('Đ', 'D').lower()
                        if target_name in normalized:
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
                logger.info("FacebookAdapter: Target Page specified. Navigating to %s", target_page_url)
                if not target_page_url.startswith("http"):
                    target_page_url = "https://" + target_page_url
                self.page.goto(target_page_url, wait_until="domcontentloaded")
                self.page.wait_for_timeout(4000)

                switch_btn = self.page.locator(
                    'div[role="button"]:has-text("Switch now"), '
                    'div[role="button"]:has-text("Chuyển ngay")'
                ).first
                if self._is_visible(switch_btn):
                    logger.info("FacebookAdapter: Found 'Switch now' button for the Page. Clicking...")
                    self._click_locator(switch_btn, "page switch button", timeout=10000)
                    self.page.wait_for_timeout(5000)
                    logger.info("FacebookAdapter: Switched to Page context successfully.")
                else:
                    logger.info("FacebookAdapter: No 'Switch now' button found on the Page. Assuming already switched or direct post allowed.")
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
            self._neutralize_overlays()

            logger.info("FacebookAdapter: [Phase 3] Locating publish entry...")
            if is_page_post:
                entrypoint_used = self._open_page_reels_entry()
                if not entrypoint_used:
                    surface = self._find_active_publish_surface()
                    self._log_surface_inventory(surface, "page_entrypoint_missing")
                    return self._failure_result(
                        job.id,
                        "page_entrypoint",
                        "Thước phim/Reels entrypoint not found on Page.",
                        flow_mode,
                        entrypoint_used,
                    )
            else:
                entrypoint_used = self._open_personal_reels_entry()
                if not entrypoint_used:
                    surface = self._find_active_publish_surface()
                    self._log_surface_inventory(surface, "personal_entrypoint_missing")
                    return self._failure_result(
                        job.id,
                        "personal_entrypoint",
                        "Could not open direct Reels entry or composer fallback on personal profile.",
                        flow_mode,
                        entrypoint_used,
                    )

            surface = self._find_active_publish_surface()
            self._log_surface_inventory(surface, "entry_opened")

            logger.info("FacebookAdapter: Uploading media from %s", job.media_path)
            if not os.path.exists(job.media_path):
                return self._failure_result(
                    job.id,
                    "upload_media",
                    f"Media path not found: {job.media_path}",
                    flow_mode,
                    entrypoint_used,
                )

            file_input = self._select_file_input(surface, job.media_path)
            if not file_input:
                self._log_surface_inventory(surface, "upload_input_missing")
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
                self._log_surface_inventory(surface, "upload_media_failed")
                return self._failure_result(
                    job.id,
                    "upload_media",
                    f"Media upload failed: {e}",
                    flow_mode,
                    entrypoint_used,
                )

            surface = self._find_active_publish_surface()
            self._log_surface_inventory(surface, "after_upload")

            caption_typed = False
            pre_next_caption = is_page_post or entrypoint_used == "direct_reels"
            if pre_next_caption:
                caption_typed = self._type_caption_in_surface(surface, publish_caption)

            logger.info("FacebookAdapter: Navigating through publish steps...")
            for step in range(6):
                surface = self._find_active_publish_surface()
                post_button = self._find_post_button(surface)
                if post_button:
                    logger.info("FacebookAdapter: Post/Đăng button found at step %d.", step)
                    break

                next_button = self._find_next_button(surface)
                if not next_button:
                    logger.info("FacebookAdapter: No more Next/Tiếp buttons at step %d.", step)
                    break

                logger.info("FacebookAdapter: Clicking Next/Tiếp at step %d...", step + 1)
                if not self._click_locator(next_button, f"next button step {step + 1}", timeout=5000):
                    self._log_surface_inventory(surface, f"next_click_failed_{step + 1}")
                    return self._failure_result(
                        job.id,
                        "navigate_next",
                        "Failed to click the Next/Tiếp button.",
                        flow_mode,
                        entrypoint_used,
                    )
                self.page.wait_for_timeout(3000)

                if pre_next_caption and not caption_typed:
                    surface = self._find_active_publish_surface()
                    caption_typed = self._type_caption_in_surface(surface, publish_caption)

            surface = self._find_active_publish_surface()
            if not caption_typed:
                caption_typed = self._type_caption_in_surface(surface, publish_caption)
                if not caption_typed and publish_caption.strip():
                    logger.warning("FacebookAdapter: Caption area not found in final surface. Proceeding without caption.")

            self._log_surface_inventory(surface, "before_post")
            post_button = self._find_post_button(surface)
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

            submission_status = self._wait_for_post_submission()
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

            self.page.wait_for_timeout(5000)

            # ── Post-publish verification: scan for new reel ──
            profile_url = target_page_url if target_page_url else "https://www.facebook.com/me"
            post_url = None
            try:
                if target_page_url:
                    reels_tab_url = target_page_url.rstrip('/') + '/reels_tab' if '?' not in target_page_url else target_page_url + '&sk=reels_tab'
                else:
                    reels_tab_url = "https://www.facebook.com/me/reels_tab"
                # Use the pre-computed publish_salt (always available since adapter auto-injects)
                salt = publish_salt
                logger.info("FacebookAdapter: Scanning profile for salt '%s' to extract post_url...", salt)

                for attempt in range(4):
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
                                    'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"]'
                                ).all()
                                for link in all_links:
                                    try:
                                        parent = link.locator("xpath=ancestor::div[@data-pagelet or contains(@class,'x1yztbdb') or @role='article']").first
                                        if parent.count() > 0:
                                            parent_text = parent.inner_text()
                                            if salt in parent_text:
                                                href = link.get_attribute("href")
                                                if href:
                                                    post_url = href if href.startswith("http") else "https://www.facebook.com" + href
                                                    logger.info("FacebookAdapter: post_url captured via main feed: %s", post_url)
                                                    break
                                    except Exception:
                                        continue
                            if post_url:
                                break
                        except Exception:
                            pass

                    try:
                        self.page.goto(reels_tab_url, wait_until="domcontentloaded", timeout=15000)
                        self.page.wait_for_timeout(8000)
                    except Exception:
                        pass

                    reel_links = self.page.locator('a').all()
                    unique_reels = []
                    for link in reel_links:
                        try:
                            href = link.get_attribute("href")
                            if href and "/reel/" in href and len(href) > 20:
                                clean_url = href.split("?")[0]
                                if clean_url not in unique_reels:
                                    unique_reels.append(clean_url)
                        except Exception:
                            pass

                    if salt:
                        recent_reels = unique_reels[:3]
                        for href in recent_reels:
                            full_url = href if href.startswith("http") else "https://www.facebook.com" + href
                            try:
                                self.page.goto(full_url, wait_until="commit", timeout=15000)
                                self.page.wait_for_timeout(5000)
                                html_content = self.page.evaluate("document.body.innerHTML")
                                if salt in html_content:
                                    post_url = full_url.split("?")[0]
                                    logger.info("FacebookAdapter: post_url captured via Reels tab deep dive: %s", post_url)
                                    break
                            except Exception:
                                continue

                        if post_url:
                            break
                    else:
                        # No salt — check if a NEW reel appeared (not in pre_existing_reels)
                        for reel_url in unique_reels:
                            clean = reel_url if reel_url.startswith("http") else "https://www.facebook.com" + reel_url
                            if clean not in pre_existing_reels:
                                post_url = clean
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
                    'a[href*="/posts/"], a[href*="/reel/"], a[href*="/videos/"]'
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

    def _switch_to_page_context(self):
        """
        Switch current context to become the Fanpage.
        Uses the top-right avatar menu as proven in test_switch.py.
        """
        if not self.page:
            return False
            
        logger.info("FacebookAdapter: Initiating account switch via avatar menu...")
        try:
            # 1. Click top-right avatar image
            avatar_selectors = [
                'div[role="banner"] image', 
                'div[role="banner"] img',
                'div[aria-label="Tài khoản của bạn"]',
                'div[aria-label="Your profile"]'
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

            avatar_btn.click()
            self.page.wait_for_timeout(2000)

            # 2. Look for "Xem tất cả trang cá nhân" or direct Page name
            see_all = self.page.get_by_text("Xem tất cả trang cá nhân", exact=False).first
            if see_all.count() == 0:
                see_all = self.page.get_by_text("See all profiles", exact=False).first

            if see_all.count() > 0 and see_all.is_visible():
                see_all.click()
                self.page.wait_for_timeout(2000)
                
            # 3. Find the first selectable profile in the list (usually the target page)
            # Find all profile items in the dialog
            profile_items = self.page.locator('div[role="dialog"] div[role="button"]').all()
            if profile_items:
                logger.info("FacebookAdapter: Clicking first available profile in switch menu...")
                profile_items[0].click()
                self.page.wait_for_timeout(8000) # Switch can take time
                logger.info("FacebookAdapter: Switch command sent.")
                return True
            
        except Exception as e:
            logger.error("FacebookAdapter: Switch failed: %s", e)
            
        return False
