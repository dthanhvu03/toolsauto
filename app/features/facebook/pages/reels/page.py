from __future__ import annotations

import logging

from playwright.sync_api import Locator, Page

from .buttons import FindButtonsMixin
from .caption import CaptionMixin
from .surface import SurfaceMixin
from .waits import WaitsMixin

logger = logging.getLogger(__name__)


class FacebookReelsPage(FindButtonsMixin, CaptionMixin, WaitsMixin, SurfaceMixin):
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
    SCHEDULE_ARIA_LABELS = ("Schedule", "Lên lịch", "Lịch đăng", "Schedule post")

    def __init__(self, page: Page, job_logger: logging.Logger | None = None):
        self.page = page
        self.logger = job_logger if job_logger is not None else logger

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
