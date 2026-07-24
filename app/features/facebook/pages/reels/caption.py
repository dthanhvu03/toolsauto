from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page

from app.config import LOGS_DIR
from app.utils.human_behavior import human_type


CAPTION_FOCUS_SCRIPT = """
() => {
    // Strategy 1: Find by aria-placeholder (most reliable on FB Reels)
    const placeholderKeywords = ['mô tả', 'describe', 'thước phim', 'reel'];
    const allEditable = document.querySelectorAll(
        '[contenteditable="true"], textarea, [role="textbox"]'
    );
    for (const el of allEditable) {
        const ph = (el.getAttribute('aria-placeholder') || '').toLowerCase();
        const label = (el.getAttribute('aria-label') || '').toLowerCase();
        for (const kw of placeholderKeywords) {
            if (ph.includes(kw) || label.includes(kw)) {
                el.focus();
                el.click();
                return {found: true, method: 'placeholder_match', tag: el.tagName, ph: ph};
            }
        }
    }
    // Strategy 2: Any visible contenteditable inside a dialog
    const dialogs = document.querySelectorAll('[role="dialog"]');
    for (const dlg of dialogs) {
        const eds = dlg.querySelectorAll('[contenteditable="true"]');
        for (const ed of eds) {
            const rect = ed.getBoundingClientRect();
            if (rect.width > 50 && rect.height > 20) {
                ed.focus();
                ed.click();
                return {found: true, method: 'dialog_editable', tag: ed.tagName, w: rect.width, h: rect.height};
            }
        }
    }
    // Strategy 3: Any visible textbox role on the page
    const textboxes = document.querySelectorAll('[role="textbox"]');
    for (const tb of textboxes) {
        const rect = tb.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 20) {
            tb.focus();
            tb.click();
            return {found: true, method: 'textbox_role', tag: tb.tagName, w: rect.width, h: rect.height};
        }
    }
    // Diagnostic: count what we found
    return {
        found: false,
        contenteditable_count: document.querySelectorAll('[contenteditable="true"]').length,
        textbox_count: document.querySelectorAll('[role="textbox"]').length,
        textarea_count: document.querySelectorAll('textarea').length,
        dialog_count: document.querySelectorAll('[role="dialog"]').length,
    };
}
"""


class CaptionMixin:
    def _dump_caption_debug(self) -> None:
        try:
            Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(LOGS_DIR) / "debug_before_caption.png"))
            with open(str(Path(LOGS_DIR) / "debug_before_caption.html"), "w", encoding="utf-8") as f:
                f.write(self.page.content())
            self.logger.info("FacebookAdapter: Saved pre-caption debug artifacts.")
        except Exception:
            pass

    def _fill_caption_via_js(self, caption: str, signature: str) -> bool:
        try:
            js_result = self.page.evaluate(CAPTION_FOCUS_SCRIPT)
            self.logger.info("FacebookAdapter: JS caption scan result: %s", js_result)
            if js_result and js_result.get("found"):
                self.page.wait_for_timeout(300)
                human_type(self.page, caption)
                self.page.wait_for_timeout(800)
                # Verify caption was actually typed
                try:
                    body_text = self.page.evaluate("document.activeElement ? document.activeElement.innerText : ''")
                    if signature in (body_text or ""):
                        self.logger.info("FacebookAdapter: Caption typed+verified via JS (%s).", js_result.get("method"))
                        self._save_caption_debug_screenshot()
                        return True
                    else:
                        self.logger.warning(
                            "FacebookAdapter: JS typed but verification failed. Active text: '%s'",
                            (body_text or "")[:60]
                        )
                except Exception:
                    # Can't verify but JS said it found+focused, optimistic return
                    self.logger.info("FacebookAdapter: Caption typed via JS (%s), verification skipped.", js_result.get("method"))
                    self._save_caption_debug_screenshot()
                    return True
        except Exception as e:
            self.logger.warning("FacebookAdapter: JS caption scan failed: %s", e)

    def _caption_candidate_text(self, candidate: Locator) -> str:
        try:
            return (candidate.inner_text() or "").strip()
        except Exception:
            return ""

    def _try_type_caption_candidate(self, candidate: Locator, caption: str, signature: str) -> bool | None:
        """Return True/False if decided, None to try next candidate."""
        if not self._is_visible(candidate):
            return None
        current_text = self._caption_candidate_text(candidate)
        if signature and current_text and signature in current_text:
            self.logger.info("FacebookAdapter: Caption already present in active surface.")
            return True
        if current_text and signature and signature not in current_text:
            self.logger.debug(
                "FacebookAdapter: Skipping non-empty textbox that does not look like caption."
            )
            return None
        try:
            candidate.click(force=True, timeout=3000)
            self.page.wait_for_timeout(500)
            human_type(self.page, caption)
            self.page.wait_for_timeout(800)
            self._save_caption_debug_screenshot()
            self.logger.info("FacebookAdapter: Caption typed into active publish surface.")
            return True
        except Exception as e:
            self.logger.debug("FacebookAdapter: Caption typing candidate failed: %s", e)
            return None

    def _fill_caption_via_locators(self, surface: Page | Locator, caption: str, signature: str) -> bool:
        candidates = [
            surface.locator('div[contenteditable="true"][data-lexical-editor="true"]').first,
            surface.locator('div[role="textbox"][contenteditable="true"][aria-label*="reel" i]').first,
            surface.locator('div[role="textbox"][contenteditable="true"]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="reel" i]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="Describe" i]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="thước phim" i]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="Mô tả" i]').first,
            surface.locator('div[contenteditable="true"][aria-placeholder*="nghĩ" i]').first,
            surface.locator('div[role="textbox"]').first,
            surface.locator('div[contenteditable="true"]').first,
            surface.locator("textarea").first,
        ]
        for candidate in candidates:
            decided = self._try_type_caption_candidate(candidate, caption, signature)
            if decided is True:
                return True
        return False

    def fill_caption(self, surface: Page | Locator, caption: str) -> bool:
        """Type caption into composer (alias for legacy _type_caption_in_surface)."""
        if not caption:
            return True
        signature = caption[:24].strip()
        self._dump_caption_debug()
        if self._fill_caption_via_js(caption, signature):
            return True
        if self._fill_caption_via_locators(surface, caption, signature):
            return True
        self.logger.error(
            "FacebookAdapter: CAPTION FAILED — could not find any caption input. "
            "Check debug_before_caption.html for DOM analysis."
        )
        return False

    def _save_caption_debug_screenshot(self):
        """Save a debug screenshot after caption is typed."""
        try:
            Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(LOGS_DIR) / "debug_caption_typed.png"))
            self.logger.info("FacebookAdapter: Saved debug screenshot of typed caption.")
        except Exception:
            pass
