from __future__ import annotations

import time

from playwright.sync_api import Locator, Page

from app.config import FACEBOOK_HOST


class WaitsMixin:
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

    def _click_schedule_modal_back(self, dlg: Locator) -> bool:
        for aria in ("Quay lại", "Back"):
            back_btn = dlg.locator(f'div[role="button"][aria-label="{aria}"]').first
            if self._is_visible(back_btn):
                self.click_locator(back_btn, "schedule modal back button")
                return True
        return False

    def _click_schedule_modal_close(self, dlg: Locator) -> bool:
        close_btn = dlg.locator(
            'div[aria-label="Đóng"][role="button"], div[aria-label="Close"][role="button"]'
        ).first
        if self._is_visible(close_btn):
            self.click_locator(close_btn, "schedule modal close button")
            return True
        return False

    def _retry_post_after_schedule_dismiss(self) -> None:
        retry_post_btn = self.find_post_button(self.find_active_publish_surface())
        if not retry_post_btn:
            return
        self.logger.info("FacebookAdapter: Found Post button after schedule dismiss. Clicking...")
        self.click_locator(retry_post_btn, "post button (after schedule dismiss)")
        self.page.wait_for_timeout(3000)

    def _dismiss_schedule_modal(self) -> None:
        schedule_signals = [
            "Lựa chọn lịch đăng",
            "Choose schedule",
            "Lên lịch đăng sau",
            "Schedule for later",
        ]
        for dlg in self.page.locator('div[role="dialog"]').all():
            if not dlg.is_visible():
                continue
            if not any(signal in dlg.inner_text() for signal in schedule_signals):
                continue
            self.logger.warning("FacebookAdapter: Detected schedule modal! Dismissing...")
            if not self._click_schedule_modal_back(dlg) and not self._click_schedule_modal_close(dlg):
                self.logger.info("FacebookAdapter: Using Escape to dismiss schedule modal.")
                self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(3000)
            self.logger.info("FacebookAdapter: Schedule modal dismissed. Re-scanning for Post button...")
            self._retry_post_after_schedule_dismiss()
            break

    def _post_submission_error(self) -> bool:
        err_signal = self.check_page_for_errors()
        if err_signal:
            self.logger.error("FacebookAdapter: Detected error signal after post: '%s'", err_signal)
            return True
        return False

    def _dismiss_publish_success(self) -> bool:
        dismiss_button = self._find_first_visible([
            self.page.get_by_role("button", name="Đóng", exact=False).first,
            self.page.get_by_role("button", name="Xong", exact=False).first,
            self.page.get_by_role("button", name="Lúc khác", exact=False).first,
            self.page.locator('div[aria-label="Đóng"], div[aria-label="Xong"]').first,
        ])
        if not dismiss_button:
            return False
        self.logger.info("FacebookAdapter: Found Success/Dismiss button, clicking it to unblock...")
        self.click_locator(dismiss_button, "publish dismiss button")
        self.page.wait_for_timeout(2000)
        return not self._post_submission_error()

    def wait_for_post_submission(self) -> str:
        if not self.page:
            return "error"
        self.logger.info("FacebookAdapter: Waiting for post submission to complete (dialog to close)...")
        for tick in range(24):
            self.page.wait_for_timeout(5000)
            try:
                self._dismiss_schedule_modal()
            except Exception as e:
                self.logger.warning("FacebookAdapter: Error handling schedule modal: %s", e)
            if tick > 0 and tick % 3 == 0 and self._post_submission_error():
                return "error"
            if self.page.locator('div[role="dialog"]').count() == 0:
                self.logger.info("FacebookAdapter: Dialog closed and disappeared naturally.")
                self.page.wait_for_timeout(2000)
                if self._post_submission_error():
                    return "error"
                return "success"
            if self._dismiss_publish_success():
                return "success"
        self.logger.warning("FacebookAdapter: Post submission wait hit timeout window without a strong completion signal.")
        return "timeout"

    def neutralize_overlays(self):
        if not self.page:
            return
        self.logger.info("FacebookAdapter: [Phase 2] Neutralizing overlays...")
        try:
            modal_close = (
                self.page.locator('div[aria-label="Close"], div[aria-label="Đóng"]')
                .filter(has_text="")
                .first
            )
            if self._is_visible(modal_close):
                self.logger.info("FacebookAdapter: Found intercepting modal close button. Clicking...")
                self.click_locator(modal_close, "overlay close button")
                self.page.wait_for_timeout(1000)
            blocking_dialogs = self.page.locator("div[role='dialog']")
            if blocking_dialogs.count() > 0:
                self.logger.info("FacebookAdapter: Waiting for dialog overlays to detach...")
                blocking_dialogs.first.wait_for(state="hidden", timeout=5000)
        except Exception as e:
            self.logger.debug("FacebookAdapter: Modal neutralization step encountered an issue: %s", e)

    @staticmethod
    def reels_tab_url(target_page_url: str | None = None) -> str:
        """Single URL scheme for pre_scan + post_verify (avoid reels_tab vs /reels/ drift)."""
        if target_page_url:
            base = target_page_url.split("?")[0].rstrip("/")
            return f"{base}/reels/"
        return f"{FACEBOOK_HOST}/me/reels/"

    def wait_until_next_enabled(
        self,
        surface: Page | Locator,
        *,
        timeout_ms: int = 45000,
        poll_ms: int = 1000,
    ) -> Locator | None:
        """Poll until Next is visible and not aria-disabled; return locator or None."""
        if not self.page:
            return None
        deadline = time.time() + max(1, timeout_ms) / 1000.0
        while time.time() < deadline:
            surface = self.find_active_publish_surface()
            btn = self._next_button_enabled(surface)
            if btn:
                return btn
            self.page.wait_for_timeout(poll_ms)
        return self.find_next_button(self.find_active_publish_surface())

    def _upload_preview_hint(self) -> str:
        try:
            return self.page.evaluate(
                """() => {
                    const t = (document.body && document.body.innerText || '').toLowerCase();
                    if (t.includes('đang xử lý') || t.includes('processing') || t.includes('uploading')) {
                        return 'busy';
                    }
                    const video = document.querySelector('[role="dialog"] video, video');
                    if (video) return 'video';
                    const imgs = document.querySelectorAll('[role="dialog"] img');
                    for (const img of imgs) {
                        const r = img.getBoundingClientRect();
                        if (r.width > 80 && r.height > 80) return 'preview_img';
                    }
                    return '';
                }"""
            )
        except Exception:
            return ""

    def _is_aria_disabled(self, locator: Locator, *, default: bool = False) -> bool:
        try:
            return (locator.get_attribute("aria-disabled") or "").lower() == "true"
        except Exception:
            return default

    def _next_button_enabled(self, surface: Page | Locator) -> Locator | None:
        next_btn = self.find_next_button(surface)
        if next_btn and self._is_visible(next_btn) and not self._is_aria_disabled(next_btn):
            return next_btn
        return None

    def _upload_ready_now(self, surface: Page | Locator) -> str | None:
        next_btn = self.find_next_button(surface)
        if next_btn and self._is_visible(next_btn) and not self._is_aria_disabled(next_btn):
            return "next"
        post_btn = self.find_post_button(surface)
        if post_btn and self._is_visible(post_btn):
            return "post"
        ready_hint = self._upload_preview_hint()
        if (
            ready_hint in ("video", "preview_img")
            and next_btn
            and self._is_visible(next_btn)
            and not self._is_aria_disabled(next_btn, default=True)
        ):
            return f"preview:{ready_hint}"
        return None

    def wait_until_upload_ready(self, surface: Page | Locator, *, timeout_ms: int = 60000, poll_ms: int = 1000, min_wait_ms: int = 1500) -> bool:
        """Wait until the uploaded composer exposes an enabled action or preview."""
        if not self.page:
            return False
        if min_wait_ms > 0:
            self.page.wait_for_timeout(min_wait_ms)
        deadline = time.time() + max(1, timeout_ms) / 1000.0
        while time.time() < deadline:
            surface = self.find_active_publish_surface()
            reason = self._upload_ready_now(surface)
            if reason == "next":
                self.logger.info("FacebookAdapter: Upload ready — Next enabled.")
                return True
            if reason == "post":
                self.logger.info("FacebookAdapter: Upload ready — Post already visible.")
                return True
            if reason and reason.startswith("preview:"):
                self.logger.info(
                    "FacebookAdapter: Upload ready — preview + Next (%s).",
                    reason.split(":", 1)[1],
                )
                return True
            self.page.wait_for_timeout(poll_ms)
        self.logger.warning("FacebookAdapter: Upload ready wait timed out after %sms.", timeout_ms)
        return False

    def _reel_url(self, href: str) -> str | None:
        if "/reel/" not in href and "/v/" not in href and "/watch/" not in href:
            return None
        return href if href.startswith("http") else f"{FACEBOOK_HOST}{href}"

    def _toast_url_from_link(self, link: Locator, *, label: str | None = None) -> str | None:
        if not self._is_visible(link):
            return None
        full_url = self._reel_url(link.get_attribute("href") or "")
        if not full_url:
            return None
        if label:
            self.logger.info(
                "FacebookAdapter: Success toast link captured via label '%s': %s", label, full_url
            )
        else:
            self.logger.info("FacebookAdapter: Success toast link captured: %s", full_url)
        return full_url

    def find_success_toast_link(self) -> str | None:
        try:
            toast_selectors = [
                'div[role="alert"] a',
                'div.xs83m0k a',
                'span:has-text("Xem") >> xpath=ancestor::a',
                'span:has-text("View") >> xpath=ancestor::a',
            ]
            for selector in toast_selectors:
                for link in self.page.locator(selector).all():
                    url = self._toast_url_from_link(link)
                    if url:
                        return url
            for label in ("Xem", "View", "Xem bài viết", "View post"):
                url = self._toast_url_from_link(
                    self.page.get_by_role("link", name=label, exact=False).first,
                    label=label,
                )
                if url:
                    return url
        except Exception as e:
            self.logger.debug("FacebookAdapter: Error scanning toast: %s", e)
        return None
