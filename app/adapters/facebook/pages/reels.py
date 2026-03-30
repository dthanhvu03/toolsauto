"""
Facebook Reels composer / upload flow (Playwright page object).
Split from FacebookAdapter (TASK-20260329-03).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from playwright.sync_api import Locator, Page

from app.config import LOGS_DIR
from app.utils.human_behavior import human_type

logger = logging.getLogger(__name__)


class FacebookReelsPage:
    """Reels creation UI: surface detection, upload, Next/Post, caption, overlays."""

    PERSONAL_REELS_LABELS = ("Thước phim", "Reels", "Reel", "Video ngắn", "Create reel")
    PAGE_REELS_LABELS = ("Thước phim", "Reels", "Reel", "Video")
    NEXT_BUTTON_LABELS = ("Tiếp", "Next")
    POST_BUTTON_LABELS = (
        "Đăng",
        "Post",
        "Đăng bài",
        "Publish",
        "Chia sẻ",
        "Share",
        "Đăng Thước phim",
    )
    SCHEDULE_POISON_WORDS = ("lịch đăng", "schedule", "lên lịch", "lịch", "đăng sau")
    FB_ERROR_SIGNALS = (
        "something went wrong",
        "đã xảy ra lỗi",
        "couldn't post",
        "không thể đăng",
        "try again",
        "thử lại",
        "upload failed",
        "tải lên thất bại",
        "couldn't share",
        "không thể chia sẻ",
        "an error occurred",
        "lỗi đã xảy ra",
    )

    def __init__(self, page: Page):
        self.page = page

    # ── Visibility / clicks (local copies; adapter keeps its own for non-Reels flows) ─────────

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

    def click_locator(self, locator: Locator, description: str, timeout: int = 5000) -> bool:
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

    def find_active_publish_surface(self) -> Page | Locator:
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

    def surface_has_upload_input(self, surface: Page | Locator) -> bool:
        try:
            return surface.locator("input[type='file']").count() > 0
        except Exception:
            return False

    def find_next_button(self, surface: Page | Locator) -> Locator | None:
        candidates = [
            surface.get_by_role("button", name="Tiếp", exact=True).first,
            surface.get_by_role("button", name="Next", exact=True).first,
            surface.get_by_role("button", name="Next", exact=False).first,
            surface.locator('button:has-text("Tiếp")').first,
            surface.locator('button:has-text("Next")').first,
            surface.locator(
                'div[role="button"][aria-label="Tiếp"], div[role="button"][aria-label="Next"]'
            ).first,
            surface.locator(
                'span[role="button"][aria-label="Tiếp"], span[role="button"][aria-label="Next"]'
            ).first,
            surface.get_by_text("Tiếp", exact=True).first,
            surface.get_by_text("Next", exact=True).first,
        ]
        return self._find_first_visible(candidates)

    def is_schedule_button(self, locator: Locator) -> bool:
        try:
            btn_text = (locator.inner_text() or "").lower()
            return any(word in btn_text for word in self.SCHEDULE_POISON_WORDS)
        except Exception:
            return False

    def find_post_button(self, surface: Page | Locator) -> Locator | None:
        for label in self.POST_BUTTON_LABELS:
            exact_candidates = [
                surface.get_by_role("button", name=label, exact=True).first,
                surface.locator(f'div[role="button"][aria-label="{label}"]').first,
                surface.locator(f'button[aria-label="{label}"]').first,
            ]
            for candidate in exact_candidates:
                if self._is_visible(candidate) and not self.is_schedule_button(candidate):
                    logger.info("FacebookAdapter: Post button matched via exact label '%s'", label)
                    return candidate
        fuzzy_candidates: list[Locator] = []
        for label in self.POST_BUTTON_LABELS:
            fuzzy_candidates.append(surface.get_by_role("button", name=label, exact=False).first)
        fuzzy_candidates.extend(
            [
                surface.locator('div[role="button"]:has-text("Đăng")').first,
                surface.locator('div[role="button"]:has-text("Post")').first,
                surface.locator('span[role="button"]:has-text("Đăng")').first,
                surface.locator('span[role="button"]:has-text("Post")').first,
                surface.locator('button:has-text("Đăng")').first,
                surface.locator('button:has-text("Post")').first,
            ]
        )
        for candidate in fuzzy_candidates:
            if self._is_visible(candidate) and not self.is_schedule_button(candidate):
                logger.info("FacebookAdapter: Post button matched via fuzzy search")
                return candidate
        logger.warning(
            "FacebookAdapter: No post button found (all candidates were schedule buttons or invisible)"
        )
        return None

    def looks_like_publish_surface(self, surface: Page | Locator | None = None) -> bool:
        if surface is None:
            surface = self.find_active_publish_surface()
        if self.surface_has_upload_input(surface):
            return True
        if self.find_next_button(surface) or self.find_post_button(surface):
            return True
        try:
            return surface.locator('div[contenteditable="true"], textarea').count() > 0
        except Exception:
            return False

    def log_surface_inventory(self, surface: Page | Locator, stage: str):
        visible_buttons: list[str] = []
        buttons = surface.locator("button, div[role='button'], a[role='button']")
        for idx in range(min(buttons.count(), 20)):
            button = buttons.nth(idx)
            if not self._is_visible(button):
                continue
            try:
                label = (
                    (button.get_attribute("aria-label") or "") or (button.inner_text() or "")
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

    def restore_origin(self, origin_url: str):
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

    def attempt_entry_click(self, locator: Locator, description: str, origin_url: str) -> bool:
        if not self.click_locator(locator, description):
            return False
        self.page.wait_for_timeout(2500)
        surface = self.find_active_publish_surface()
        if self.looks_like_publish_surface(surface):
            return True
        self.page.wait_for_timeout(1500)
        surface = self.find_active_publish_surface()
        if self.looks_like_publish_surface(surface):
            return True
        logger.info(
            "FacebookAdapter: %s did not open a publish surface. Restoring origin...", description
        )
        self.restore_origin(origin_url)
        return False

    def try_entry_labels(self, labels: tuple[str, ...], origin_url: str, flow_name: str) -> bool:
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
                if self.attempt_entry_click(candidate, f"{flow_name} entry '{label}'", origin_url):
                    return True
        return False

    def try_entry_selectors(self, selectors: tuple[str, ...], origin_url: str, flow_name: str) -> bool:
        if not self.page:
            return False
        for selector in selectors:
            candidate = self.page.locator(selector).first
            if not self._is_visible(candidate):
                continue
            if self.attempt_entry_click(candidate, f"{flow_name} selector {selector}", origin_url):
                return True
        return False

    def open_personal_composer_fallback(self) -> bool:
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
            if self.click_locator(composer, "personal composer fallback", timeout=10000):
                self.page.wait_for_timeout(3000)
                if self.looks_like_publish_surface():
                    return True
                self.restore_origin(origin_url)
        return False

    def open_personal_reels_entry(self) -> str | None:
        if not self.page:
            return None
        origin_url = self.page.url
        if self.try_entry_labels(self.PERSONAL_REELS_LABELS, origin_url, "personal"):
            return "direct_reels"
        direct_reels_selectors = (
            'a[href*="/reels/create"]',
            'a[href*="/reel/create"]',
            'a[href*="create"][href*="reel"]',
            'a[href*="create"][href*="video"]',
            'div[role="button"][aria-label*="Reel"]',
            'div[role="button"][aria-label*="reel"]',
        )
        if self.try_entry_selectors(direct_reels_selectors, origin_url, "personal"):
            return "direct_reels"
        self.restore_origin(origin_url)
        if self.open_personal_composer_fallback():
            return "composer_fallback"
        return None

    def open_page_reels_entry(self) -> str | None:
        if not self.page:
            return None
        origin_url = self.page.url
        logger.info("FacebookAdapter: Navigating to page reels entry from %s", origin_url)
        create_url = "https://www.facebook.com/reels/create"
        logger.info("FacebookAdapter: Trying direct navigation to Fanpage create reel url: %s", create_url)
        try:
            self.page.goto(create_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(5000)
            if self.looks_like_publish_surface(self.page):
                return "direct_reels"
        except Exception as e:
            logger.warning("FacebookAdapter: Direct navigation to reels/create failed: %s", e)
        page_selectors = (
            'a[href*="/reels/create"]',
            'a[href*="/reel/create"]',
            'a[href*="create"][href*="reel"]',
        )
        if self.try_entry_selectors(page_selectors, origin_url, "page"):
            return "direct_reels"
        if self.try_entry_labels(self.PAGE_REELS_LABELS, origin_url, "page"):
            return "direct_reels"
        return None

    def select_file_input(self, surface: Page | Locator, media_path: str) -> Locator | None:
        candidates = surface.locator("input[type='file']")
        if candidates.count() == 0 and self.page:
            candidates = self.page.locator("input[type='file']")
        is_video = os.path.splitext(media_path)[1].lower() in (
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".webm",
        )
        chosen: Locator | None = None
        for idx in range(candidates.count()):
            candidate = candidates.nth(idx)
            accept_attr = (candidate.get_attribute("accept") or "").lower()
            if is_video and "video" in accept_attr:
                logger.info(
                    "FacebookAdapter: Selected file input with accept='%s' for video upload.",
                    accept_attr[:80],
                )
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

    def upload_video(self, surface: Page | Locator, media_path: str) -> bool:
        """Pick file input and call set_input_files. Returns False if input missing or upload throws."""
        inp = self.select_file_input(surface, media_path)
        if not inp:
            return False
        try:
            inp.set_input_files(media_path)
            logger.info("FacebookAdapter: Media attached. Waiting for preview...")
            self.page.wait_for_timeout(8000)
            return True
        except Exception as e:
            logger.warning("FacebookAdapter: upload_video failed: %s", e)
            return False

    def click_next(self, surface: Page | Locator, step_label: str = "next") -> bool:
        btn = self.find_next_button(surface)
        if not btn:
            return False
        return self.click_locator(btn, step_label, timeout=5000)

    def click_post(self, surface: Page | Locator) -> bool:
        btn = self.find_post_button(surface)
        if not btn:
            return False
        return self.click_locator(btn, "post button", timeout=10000)

    def fill_caption(self, surface: Page | Locator, caption: str) -> bool:
        """Type caption into composer (alias for legacy _type_caption_in_surface)."""
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
                logger.debug(
                    "FacebookAdapter: Skipping non-empty textbox that does not look like caption."
                )
                continue
            try:
                candidate.click(force=True, timeout=3000)
                self.page.wait_for_timeout(500)
                human_type(self.page, caption)
                self.page.wait_for_timeout(800)
                try:
                    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
                    self.page.screenshot(path=str(Path(LOGS_DIR) / "debug_caption_typed.png"))
                    logger.info("FacebookAdapter: Saved debug screenshot of typed caption.")
                except Exception:
                    pass
                logger.info("FacebookAdapter: Caption typed into active publish surface.")
                return True
            except Exception as e:
                logger.debug("FacebookAdapter: Caption typing candidate failed: %s", e)
        return False

    def check_page_for_errors(self) -> str | None:
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

    def wait_for_post_submission(self) -> str:
        if not self.page:
            return "error"
        logger.info("FacebookAdapter: Waiting for post submission to complete (dialog to close)...")
        for tick in range(60):
            self.page.wait_for_timeout(5000)
            try:
                schedule_signals = [
                    "Lựa chọn lịch đăng",
                    "Choose schedule",
                    "Lên lịch đăng sau",
                    "Schedule for later",
                ]
                dialogs = self.page.locator('div[role="dialog"]').all()
                for dlg in dialogs:
                    if dlg.is_visible():
                        dlg_text = dlg.inner_text()
                        if any(sig in dlg_text for sig in schedule_signals):
                            logger.warning("FacebookAdapter: Detected schedule modal! Dismissing...")
                            dismissed = False
                            for aria in ["Quay lại", "Back"]:
                                back_btn = dlg.locator(f'div[role="button"][aria-label="{aria}"]').first
                                if self._is_visible(back_btn):
                                    self.click_locator(back_btn, "schedule modal back button")
                                    dismissed = True
                                    break
                            if not dismissed:
                                close_btn = dlg.locator(
                                    'div[aria-label="Đóng"][role="button"], div[aria-label="Close"][role="button"]'
                                ).first
                                if self._is_visible(close_btn):
                                    self.click_locator(close_btn, "schedule modal close button")
                                    dismissed = True
                            if not dismissed:
                                logger.info("FacebookAdapter: Using Escape to dismiss schedule modal.")
                                self.page.keyboard.press("Escape")
                            self.page.wait_for_timeout(3000)
                            logger.info("FacebookAdapter: Schedule modal dismissed. Continuing wait...")
                            break
            except Exception as e:
                logger.warning("FacebookAdapter: Error handling schedule modal: %s", e)
            if tick > 0 and tick % 3 == 0:
                err_signal = self.check_page_for_errors()
                if err_signal:
                    logger.error("FacebookAdapter: Detected error signal after post: '%s'", err_signal)
                    return "error"
            if self.page.locator('div[role="dialog"]').count() == 0:
                logger.info("FacebookAdapter: Dialog closed and disappeared naturally.")
                self.page.wait_for_timeout(2000)
                err_signal = self.check_page_for_errors()
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
                self.click_locator(dismiss_button, "publish dismiss button")
                self.page.wait_for_timeout(2000)
                err_signal = self.check_page_for_errors()
                if err_signal:
                    logger.error("FacebookAdapter: Error detected after dismiss: '%s'", err_signal)
                    return "error"
                return "success"
        logger.warning(
            "FacebookAdapter: Post submission wait hit timeout window without a strong completion signal."
        )
        return "timeout"

    def neutralize_overlays(self):
        if not self.page:
            return
        logger.info("FacebookAdapter: [Phase 2] Neutralizing overlays...")
        try:
            modal_close = (
                self.page.locator('div[aria-label="Close"], div[aria-label="Đóng"]')
                .filter(has_text="")
                .first
            )
            if self._is_visible(modal_close):
                logger.info("FacebookAdapter: Found intercepting modal close button. Clicking...")
                self.click_locator(modal_close, "overlay close button")
                self.page.wait_for_timeout(1000)
            blocking_dialogs = self.page.locator("div[role='dialog']")
            if blocking_dialogs.count() > 0:
                logger.info("FacebookAdapter: Waiting for dialog overlays to detach...")
                blocking_dialogs.first.wait_for(state="hidden", timeout=5000)
        except Exception as e:
            logger.debug("FacebookAdapter: Modal neutralization step encountered an issue: %s", e)
