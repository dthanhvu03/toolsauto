from __future__ import annotations

import os

from playwright.sync_api import Locator, Page

from app.config import FB_REELS_CREATE_URL


class SurfaceMixin:
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

    def _surface_button_labels(self, surface: Page | Locator) -> list[str]:
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
        return visible_buttons

    def _surface_file_input_labels(self, surface: Page | Locator) -> list[str]:
        file_inputs: list[str] = []
        inputs = surface.locator("input[type='file']")
        for idx in range(min(inputs.count(), 10)):
            input_el = inputs.nth(idx)
            try:
                accept = (input_el.get_attribute("accept") or "").strip() or "(no accept)"
            except Exception:
                accept = "(unreadable)"
            file_inputs.append(accept)
        return file_inputs

    def _surface_textbox_labels(self, surface: Page | Locator) -> list[str]:
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
        return textboxes

    def log_surface_inventory(self, surface: Page | Locator, stage: str):
        visible_buttons = self._surface_button_labels(surface)
        file_inputs = self._surface_file_input_labels(surface)
        textboxes = self._surface_textbox_labels(surface)
        self.logger.debug(
            "FacebookAdapter: [%s] Surface inventory | buttons=%s | file_inputs=%s | textboxes=%s",
            stage, visible_buttons or ["(none)"], file_inputs or ["(none)"], textboxes or ["(none)"],
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
                self.logger.debug("FacebookAdapter: Failed to restore origin URL %s: %s", origin_url, e)

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
        self.logger.info(
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
        self.logger.info("FacebookAdapter: [PERSONAL MODE] Falling back to generic composer.")
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
        self.logger.debug("FacebookAdapter: Navigating to page reels entry from %s", origin_url)
        create_url = FB_REELS_CREATE_URL
        self.logger.debug("FacebookAdapter: Trying direct navigation to Fanpage create reel url: %s", create_url)
        try:
            self.page.goto(create_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(5000)
            if self.looks_like_publish_surface(self.page):
                return "direct_reels"
        except Exception as e:
            self.logger.warning("FacebookAdapter: Direct navigation to reels/create failed: %s", e)
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

    def _file_input_candidates(self, surface: Page | Locator):
        candidates = surface.locator("input[type='file']")
        if candidates.count() == 0 and self.page:
            return self.page.locator("input[type='file']")
        return candidates

    def _is_video_media(self, media_path: str) -> bool:
        return os.path.splitext(media_path)[1].lower() in (
            ".mp4", ".mov", ".avi", ".mkv", ".webm",
        )

    def _pick_video_file_input(self, candidates: Locator) -> Locator | None:
        for idx in range(candidates.count()):
            candidate = candidates.nth(idx)
            accept_attr = (candidate.get_attribute("accept") or "").lower()
            if "video" in accept_attr:
                self.logger.debug(
                    "FacebookAdapter: Selected file input with accept='%s' for video upload.",
                    accept_attr[:80],
                )
                return candidate
        return None

    def _pick_image_file_input(self, candidates: Locator) -> Locator | None:
        for idx in range(candidates.count()):
            candidate = candidates.nth(idx)
            accept_attr = (candidate.get_attribute("accept") or "").lower()
            if "image" in accept_attr or accept_attr == "":
                self.logger.debug("FacebookAdapter: Selected file input fallback for non-video upload.")
                return candidate
        return None

    def select_file_input(self, surface: Page | Locator, media_path: str) -> Locator | None:
        candidates = self._file_input_candidates(surface)
        if self._is_video_media(media_path):
            chosen = self._pick_video_file_input(candidates)
        else:
            chosen = self._pick_image_file_input(candidates)
        if chosen:
            return chosen
        if candidates.count() > 0:
            self.logger.debug("FacebookAdapter: Using first file input as final fallback.")
            return candidates.first
        return None

    def upload_video(self, surface: Page | Locator, media_path: str) -> bool:
        """Pick file input and call set_input_files. Returns False if input missing or upload throws."""
        inp = self.select_file_input(surface, media_path)
        if not inp:
            return False
        try:
            inp.set_input_files(media_path)
            self.logger.info("FacebookAdapter: Media attached. Waiting for preview...")
            self.page.wait_for_timeout(8000)
            return True
        except Exception as e:
            self.logger.warning("FacebookAdapter: upload_video failed: %s", e)
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

    def navigate_to_reels_tab(self, target_page_url: str | None = None) -> bool:
        """Navigates directly to the Reels tab for faster verification / pre_scan."""
        if not self.page:
            return False
        try:
            reels_url = self.reels_tab_url(target_page_url)
            self.logger.info("FacebookAdapter: Navigating to Reels tab: %s", reels_url)
            self.page.goto(reels_url, wait_until="domcontentloaded", timeout=15000)
            self.page.wait_for_timeout(3000)  # Wait for React content
            return True
        except Exception as e:
            self.logger.warning("FacebookAdapter: Navigation to Reels tab failed: %s", e)
            return False
