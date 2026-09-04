"""
Facebook story composer — đăng tin (story) ảnh hoặc video dưới danh nghĩa Page.

Khác feed: tin không có ô soạn thảo sẵn trên tường. Phải vào từ mục "Tạo tin" trên
bề mặt Page, chọn ảnh/video, rồi bấm "Chia sẻ lên tin". Chữ là lớp phủ tuỳ chọn,
thêm qua nút "Thêm văn bản".

Vì sao không vào thẳng /stories/create: danh tính người đăng lấy theo bề mặt đang
đứng. Vào thẳng URL rất dễ đăng tin dưới tài khoản cá nhân thay vì Page — sự cố nặng
nhất của hệ này. Nên luôn đi từ Page ra.

Selector theo kỷ luật dự án: dùng role/label, không XPath, không nth-child. Mọi nhãn
đều có cả tiếng Việt lẫn tiếng Anh vì profile có thể ở locale nào.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from playwright.sync_api import Locator, Page

logger = logging.getLogger(__name__)

# Lối vào tạo tin trên bề mặt Page / trang chủ.
STORY_ENTRY_LABELS: tuple[str, ...] = (
    "Tạo tin",
    "Tạo tin mới",
    "Create story",
    "Create a story",
    "Thêm vào tin",
    "Add to story",
)

# Trong hộp tạo tin, chọn kiểu tin ảnh/video.
PHOTO_STORY_LABELS: tuple[str, ...] = (
    "Tạo tin ảnh",
    "Tin ảnh",
    "Create photo story",
    "Photo story",
    "Ảnh",
    "Photo",
)

FILE_INPUT_SELECTORS: tuple[str, ...] = (
    'input[type="file"][accept*="image"]',
    'input[type="file"][accept*="video"]',
    'div[role="dialog"] input[type="file"]',
    'input[type="file"]',
)

# Nút thêm chữ lên tin.
ADD_TEXT_LABELS: tuple[str, ...] = (
    "Thêm văn bản",
    "Thêm chữ",
    "Add text",
    "Text",
    "Văn bản",
)

TEXT_BOX_SELECTORS: tuple[str, ...] = (
    'div[role="dialog"] div[role="textbox"][contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
    'div[role="dialog"] textarea',
)

# Nút chốt đăng tin.
SHARE_BUTTON_LABELS: tuple[str, ...] = (
    "Chia sẻ lên tin",
    "Chia sẻ",
    "Đăng tin",
    "Share to story",
    "Share to Story",
    "Share",
    "Post story",
)

# Nhãn dễ nhầm với nút chia sẻ tin.
SHARE_BUTTON_DENY: tuple[str, ...] = (
    "chia sẻ lên bảng feed",
    "chia sẻ lên trang",
    "share to feed",
    "share to news feed",
    "huỷ",
    "hủy",
    "cancel",
    "bỏ",
    "discard",
)

# Chip hiển thị "đang đăng dưới tên ai" trong hộp tạo tin.
AUTHOR_CHIP_SELECTORS: tuple[str, ...] = (
    'div[role="dialog"] [aria-label*="Chia sẻ dưới tên" i]',
    'div[role="dialog"] [aria-label*="Sharing as" i]',
    'div[role="dialog"] [aria-label*="Đăng dưới tên" i]',
    'div[role="dialog"] [aria-label*="Posting as" i]',
)

IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".webm", ".mkv")


class FacebookStoryComposer:
    """Điều khiển hộp tạo tin của Facebook."""

    def __init__(self, page: Page, job_logger: logging.Logger | None = None):
        self.page = page
        self.logger = job_logger or logger

    # ── tiện ích ──────────────────────────────────────────────────────────

    @staticmethod
    def is_image(media_path: str | None) -> bool:
        if not media_path:
            return False
        return os.path.splitext(str(media_path))[1].lower() in IMAGE_EXTENSIONS

    @staticmethod
    def is_video(media_path: str | None) -> bool:
        if not media_path:
            return False
        return os.path.splitext(str(media_path))[1].lower() in VIDEO_EXTENSIONS

    def _visible(self, locator: Locator | None) -> bool:
        if locator is None:
            return False
        try:
            return locator.is_visible(timeout=2000)
        except Exception:
            return False

    def _first_visible(self, locators: Iterable[Locator]) -> Locator | None:
        for loc in locators:
            try:
                if loc.count() == 0:
                    continue
                candidate = loc.first
                if self._visible(candidate):
                    return candidate
            except Exception:
                continue
        return None

    def _click(self, locator: Locator, description: str, timeout: int = 8000) -> bool:
        try:
            locator.click(timeout=timeout)
            self.logger.info("StoryComposer: đã bấm %s", description)
            return True
        except Exception as e:
            self.logger.warning("StoryComposer: bấm %s thất bại: %s", description, e)
            try:
                locator.click(timeout=timeout, force=True)
                self.logger.info("StoryComposer: đã bấm %s (force)", description)
                return True
            except Exception as e2:
                self.logger.warning(
                    "StoryComposer: bấm %s (force) cũng thất bại: %s", description, e2
                )
                return False

    def dialog(self) -> Locator | None:
        try:
            dlg = self.page.locator('div[role="dialog"]').first
            return dlg if self._visible(dlg) else None
        except Exception:
            return None

    # ── các bước ──────────────────────────────────────────────────────────

    def open_composer(self) -> bool:
        """Mở luồng tạo tin từ bề mặt đang đứng (Page hoặc trang chủ)."""
        candidates = []
        for label in STORY_ENTRY_LABELS:
            candidates.append(self.page.get_by_role("button", name=label, exact=False))
            candidates.append(self.page.get_by_role("link", name=label, exact=False))
            candidates.append(self.page.get_by_text(label, exact=False))

        entry = self._first_visible(candidates)
        if entry is None:
            self.logger.error(
                "StoryComposer: không tìm thấy lối vào Tạo tin trên bề mặt hiện tại"
            )
            return False

        if not self._click(entry, "lối vào Tạo tin"):
            return False

        self.page.wait_for_timeout(3000)
        return True

    def choose_photo_story(self) -> bool:
        """
        Chọn kiểu tin ảnh/video nếu Facebook hỏi.

        Nhiều phiên bản mở thẳng hộp chọn file, nên không tìm thấy nút cũng không
        coi là hỏng — chỉ ghi log rồi đi tiếp tới bước tìm input file.
        """
        button = self._first_visible(
            self.page.get_by_role("button", name=label, exact=False)
            for label in PHOTO_STORY_LABELS
        )
        if button is None:
            self.logger.info(
                "StoryComposer: không thấy bước chọn kiểu tin — đi thẳng tới chọn file"
            )
            return True
        self._click(button, "kiểu tin ảnh/video")
        self.page.wait_for_timeout(2000)
        return True

    def attach_media(self, media_path: str) -> bool:
        """Nạp ảnh hoặc video vào tin."""
        if not media_path or not os.path.exists(media_path):
            self.logger.error("StoryComposer: file tin không tồn tại: %s", media_path)
            return False

        file_input = None
        for selector in FILE_INPUT_SELECTORS:
            try:
                loc = self.page.locator(selector).first
                if loc.count() > 0:
                    file_input = loc
                    break
            except Exception:
                continue

        if file_input is None:
            self.logger.error("StoryComposer: không tìm thấy input file của hộp tạo tin")
            return False

        try:
            file_input.set_input_files(media_path, timeout=60000)
        except Exception as e:
            self.logger.error("StoryComposer: nạp media vào tin thất bại: %s", e)
            return False

        # Video cần lâu hơn để Facebook dựng preview.
        self.page.wait_for_timeout(25000 if self.is_video(media_path) else 8000)
        self.logger.info("StoryComposer: đã nạp media vào tin")
        return True

    def add_text(self, text: str) -> bool:
        """
        Phủ chữ lên tin (thường là link affiliate).

        Không thêm được chữ thì tin vẫn đăng được — nên trả False để bên gọi ghi
        log, chứ không coi là hỏng cả job.
        """
        if not text:
            return True

        button = self._first_visible(
            self.page.get_by_role("button", name=label, exact=False) for label in ADD_TEXT_LABELS
        )
        if button is not None:
            self._click(button, "nút Thêm văn bản")
            self.page.wait_for_timeout(1500)

        box = self._first_visible(self.page.locator(sel) for sel in TEXT_BOX_SELECTORS)
        if box is None:
            self.logger.warning("StoryComposer: không tìm thấy ô nhập chữ cho tin")
            return False

        try:
            box.click(timeout=8000)
            self.page.wait_for_timeout(400)
            box.type(text, delay=15)
            self.page.wait_for_timeout(800)
            self.logger.info("StoryComposer: đã phủ chữ lên tin (%d ký tự)", len(text))
            return True
        except Exception as e:
            self.logger.warning("StoryComposer: gõ chữ lên tin thất bại: %s", e)
            return False

    def read_author_name(self) -> str | None:
        """Đọc tên đang được dùng để đăng tin. None = không đọc được."""
        for selector in AUTHOR_CHIP_SELECTORS:
            try:
                loc = self.page.locator(selector).first
                if loc.count() == 0 or not self._visible(loc):
                    continue
                label = loc.get_attribute("aria-label") or loc.inner_text(timeout=2000) or ""
                label = label.strip()
                if label:
                    return label
            except Exception:
                continue
        return None

    def find_share_button(self) -> Locator | None:
        """Nút chia sẻ tin, loại trừ các nhãn dễ nhầm (chia sẻ lên feed, huỷ...)."""
        dlg = self.dialog()
        scope = dlg if dlg is not None else self.page

        for label in SHARE_BUTTON_LABELS:
            try:
                candidates = scope.get_by_role("button", name=label, exact=False)
                count = candidates.count()
            except Exception:
                continue
            for index in range(min(count, 5)):
                candidate = candidates.nth(index)
                try:
                    text = (candidate.inner_text(timeout=2000) or "").strip().lower()
                except Exception:
                    text = ""
                if any(bad in text for bad in SHARE_BUTTON_DENY):
                    continue
                if self._visible(candidate):
                    return candidate
        return None

    def submit(self) -> bool:
        """Bấm chia sẻ rồi chờ hộp tạo tin đóng."""
        button = self.find_share_button()
        if button is None:
            self.logger.error("StoryComposer: không tìm thấy nút chia sẻ tin")
            return False

        try:
            if button.is_disabled(timeout=2000):
                self.logger.error(
                    "StoryComposer: nút chia sẻ đang bị khoá (media chưa tải xong?)"
                )
                return False
        except Exception:
            pass

        if not self._click(button, "nút chia sẻ tin"):
            return False

        try:
            self.page.wait_for_selector('div[role="dialog"]', state="detached", timeout=120000)
            self.logger.info("StoryComposer: hộp tạo tin đã đóng — tin đã được gửi")
            return True
        except Exception:
            self.logger.warning(
                "StoryComposer: hộp tạo tin chưa đóng sau 120s — không chắc tin đã lên"
            )
            return False

    def close(self) -> None:
        """Đóng hộp tạo tin nếu còn mở (dùng trong finally)."""
        if self.dialog() is None:
            return
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(800)
            for label in ("Bỏ", "Discard", "Xoá", "Delete"):
                btn = self.page.get_by_role("button", name=label, exact=True)
                if btn.count() > 0 and self._visible(btn.first):
                    btn.first.click(timeout=5000)
                    break
        except Exception as e:
            self.logger.debug("StoryComposer: đóng hộp tạo tin thất bại: %s", e)
