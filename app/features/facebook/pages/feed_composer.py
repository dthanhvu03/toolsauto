"""
Facebook feed composer — đăng bài chữ và bài ảnh lên tường cá nhân hoặc Page.

Khác Reels: composer feed là một hộp thoại duy nhất, media là tùy chọn, và
không có chuỗi Next → Next → Đăng. Nên tách riêng khỏi FacebookReelsPage.

Selector theo kỷ luật dự án: dùng role/label, không XPath, không nth-child.
Mọi nhãn đều có cả bản tiếng Việt lẫn tiếng Anh vì profile có thể ở locale nào.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

from playwright.sync_api import Locator, Page

logger = logging.getLogger(__name__)

# Ô "Bạn đang nghĩ gì?" trên tường — bấm vào để mở hộp thoại soạn bài.
COMPOSER_ENTRY_LABELS: tuple[str, ...] = (
    "Bạn đang nghĩ gì",
    "What's on your mind",
    "Tạo bài viết",
    "Create post",
    "Viết bài viết công khai",
)

# Ô nhập nội dung bên trong hộp thoại.
COMPOSER_TEXTBOX_SELECTORS: tuple[str, ...] = (
    'div[role="dialog"] div[role="textbox"][contenteditable="true"]',
    'div[role="dialog"] div[contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
)

# Nút mở khay đính kèm ảnh/video.
PHOTO_BUTTON_LABELS: tuple[str, ...] = (
    "Ảnh/video",
    "Ảnh/Video",
    "Photo/video",
    "Photo/Video",
    "Thêm ảnh hoặc video",
    "Add photos or videos",
)

# Input file ẩn của composer.
FILE_INPUT_SELECTORS: tuple[str, ...] = (
    'div[role="dialog"] input[type="file"][accept*="image"]',
    'div[role="dialog"] input[type="file"]',
    'input[type="file"][accept*="image"]',
)

# Nút đăng cuối cùng.
POST_BUTTON_LABELS: tuple[str, ...] = ("Đăng", "Post")

# Composer của Page có thêm bước trung gian: Tiếp → (chọn nơi đăng) → Đăng.
# Composer tường cá nhân thì hiện Đăng ngay.
NEXT_BUTTON_LABELS: tuple[str, ...] = ("Tiếp", "Tiếp theo", "Next")

# Nhãn KHÔNG phải nút đăng, tránh bấm nhầm.
POST_BUTTON_DENY: tuple[str, ...] = (
    "đăng ký",
    "đăng nhập",
    "đăng xuất",
    "lên lịch",
    "schedule",
    "log in",
    "sign up",
    "log out",
)

IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".webm", ".mkv")

# Dấu hiệu media đã lên tới composer (thẻ video, hoặc ảnh preview dạng blob).
MEDIA_PREVIEW_SELECTORS: tuple[str, ...] = (
    'div[role="dialog"] video',
    'div[role="dialog"] img[src^="blob:"]',
    'div[role="dialog"] img[src^="data:"]',
)

# Ngân sách chờ upload (PLAN-056). Ảnh nhanh; video tính theo dung lượng.
IMAGE_UPLOAD_WAIT_MS = 6_000
VIDEO_UPLOAD_BASE_MS = 30_000
VIDEO_UPLOAD_MS_PER_MB = 400
VIDEO_UPLOAD_MAX_MS = 420_000  # 7 phút — trần để một file hỏng không treo job
UNKNOWN_SIZE_FALLBACK_MB = 50
MEDIA_POLL_MS = 1_000
MEDIA_SETTLE_MS = 1_500


class FacebookFeedComposer:
    """Điều khiển hộp thoại soạn bài feed của Facebook."""

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
            self.logger.info("FeedComposer: đã bấm %s", description)
            return True
        except Exception as e:
            self.logger.warning("FeedComposer: bấm %s thất bại: %s", description, e)
            try:
                locator.click(timeout=timeout, force=True)
                self.logger.info("FeedComposer: đã bấm %s (force)", description)
                return True
            except Exception as e2:
                self.logger.warning("FeedComposer: bấm %s (force) cũng thất bại: %s", description, e2)
                return False

    # ── các bước ──────────────────────────────────────────────────────────

    def open_composer(self) -> bool:
        """Mở hộp thoại soạn bài từ ô 'Bạn đang nghĩ gì?'."""
        if self.dialog() is not None:
            self.logger.info("FeedComposer: hộp thoại đã mở sẵn")
            return True

        candidates = []
        for label in COMPOSER_ENTRY_LABELS:
            candidates.append(self.page.get_by_role("button", name=label, exact=False))
            candidates.append(self.page.get_by_text(label, exact=False))

        entry = self._first_visible(candidates)
        if entry is None:
            self.logger.error("FeedComposer: không tìm thấy ô soạn bài trên tường")
            return False

        if not self._click(entry, "ô soạn bài"):
            return False

        try:
            self.page.wait_for_selector('div[role="dialog"]', timeout=15000)
        except Exception:
            self.logger.error("FeedComposer: hộp thoại soạn bài không mở ra")
            return False
        self.page.wait_for_timeout(1200)
        return True

    def dialog(self) -> Locator | None:
        try:
            dlg = self.page.locator('div[role="dialog"]').first
            return dlg if self._visible(dlg) else None
        except Exception:
            return None

    def fill_text(self, text: str) -> bool:
        """Nhập nội dung vào ô soạn thảo. Bài chỉ có ảnh thì text có thể rỗng."""
        if not text:
            return True

        box = self._first_visible(self.page.locator(sel) for sel in COMPOSER_TEXTBOX_SELECTORS)
        if box is None:
            self.logger.error("FeedComposer: không tìm thấy ô nhập nội dung")
            return False

        try:
            box.click(timeout=8000)
            self.page.wait_for_timeout(400)
            # type() gõ từng ký tự nên xuống dòng và emoji vào đúng như soạn tay.
            box.type(text, delay=12)
            self.page.wait_for_timeout(600)
            return True
        except Exception as e:
            self.logger.warning("FeedComposer: gõ nội dung thất bại (%s), thử fill()", e)
            try:
                box.fill(text, timeout=8000)
                return True
            except Exception as e2:
                self.logger.error("FeedComposer: fill() cũng thất bại: %s", e2)
                return False

    @staticmethod
    def upload_budget_ms(media_paths: list[str]) -> int:
        """
        Thời gian tối đa chờ Facebook nuốt xong media, tính theo dung lượng thật.

        Trước đây chờ cứng 20s cho mọi video: clip 15 giây thì phí, video 10 phút thì
        chưa upload xong đã bấm Đăng. Có trần để một file hỏng không treo job vô hạn.
        """
        if not any(FacebookFeedComposer.is_video(p) for p in media_paths):
            return IMAGE_UPLOAD_WAIT_MS

        total_mb = 0.0
        for path in media_paths:
            try:
                total_mb += os.path.getsize(path) / (1024 * 1024)
            except OSError:
                # Không đọc được dung lượng thì cứ coi như video cỡ trung bình,
                # thà chờ dư còn hơn bấm Đăng lúc chưa upload xong.
                total_mb += UNKNOWN_SIZE_FALLBACK_MB

        budget = VIDEO_UPLOAD_BASE_MS + int(total_mb * VIDEO_UPLOAD_MS_PER_MB)
        return min(budget, VIDEO_UPLOAD_MAX_MS)

    def media_preview_ready(self) -> bool:
        """Đã thấy preview của media trong hộp thoại chưa."""
        dlg = self.dialog()
        scope = dlg if dlg is not None else self.page
        for selector in MEDIA_PREVIEW_SELECTORS:
            try:
                if scope.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def wait_for_media_ready(self, media_paths: list[str]) -> bool:
        """
        Chờ tới khi có preview thật, tối đa bằng ngân sách theo dung lượng.

        Trả False khi hết ngân sách mà vẫn chưa thấy gì — bên gọi vẫn thử bấm Đăng,
        vì `submit()` còn một lớp bảo vệ nữa (nút Đăng bị khoá thì dừng).
        """
        budget_ms = self.upload_budget_ms(media_paths)
        waited = 0
        while waited < budget_ms:
            if self.media_preview_ready():
                # Cho preview ổn định một nhịp rồi mới đi tiếp.
                self.page.wait_for_timeout(MEDIA_SETTLE_MS)
                self.logger.info("FeedComposer: media đã có preview sau %.1fs", waited / 1000)
                return True
            self.page.wait_for_timeout(MEDIA_POLL_MS)
            waited += MEDIA_POLL_MS

        self.logger.warning(
            "FeedComposer: hết %.0fs ngân sách mà chưa thấy preview media", budget_ms / 1000
        )
        return False

    def attach_media(self, media_paths: list[str]) -> bool:
        """Đính kèm ảnh (hoặc video) vào bài. Trả False nếu không đính được."""
        existing = [p for p in media_paths if p and os.path.exists(p)]
        if not existing:
            self.logger.error("FeedComposer: không có file media nào tồn tại: %s", media_paths)
            return False

        # Khay ảnh có thể chưa mở — bấm nút Ảnh/video trước, bỏ qua nếu không có.
        photo_btn = self._first_visible(
            self.page.get_by_role("button", name=label, exact=False) for label in PHOTO_BUTTON_LABELS
        )
        if photo_btn is not None:
            self._click(photo_btn, "nút Ảnh/video")
            self.page.wait_for_timeout(1000)

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
            self.logger.error("FeedComposer: không tìm thấy input file trong hộp thoại")
            return False

        try:
            file_input.set_input_files(existing, timeout=60000)
        except Exception as e:
            self.logger.error("FeedComposer: đính kèm media thất bại: %s", e)
            return False

        # Chờ theo dung lượng thật, và dừng sớm ngay khi thấy preview.
        self.wait_for_media_ready(existing)
        self.logger.info("FeedComposer: đã đính %d file", len(existing))
        return True

    def find_post_button(self) -> Locator | None:
        """Nút Đăng trong hộp thoại, loại trừ các nhãn dễ nhầm."""
        dlg = self.dialog()
        scope = dlg if dlg is not None else self.page

        for label in POST_BUTTON_LABELS:
            try:
                candidates = scope.get_by_role("button", name=label, exact=True)
                count = candidates.count()
            except Exception:
                continue
            for index in range(min(count, 5)):
                candidate = candidates.nth(index)
                try:
                    text = (candidate.inner_text(timeout=2000) or "").strip().lower()
                except Exception:
                    text = ""
                if any(bad in text for bad in POST_BUTTON_DENY):
                    continue
                if self._visible(candidate):
                    return candidate
        return None

    def find_next_button(self) -> Locator | None:
        """Nút 'Tiếp' của composer Page."""
        dlg = self.dialog()
        scope = dlg if dlg is not None else self.page
        for label in NEXT_BUTTON_LABELS:
            try:
                candidate = scope.get_by_role("button", name=label, exact=True).first
            except Exception:
                continue
            if self._visible(candidate):
                return candidate
        return None

    def advance_to_post_button(self, max_hops: int = 3) -> Locator | None:
        """
        Đi tới nút Đăng.

        Tường cá nhân hiện Đăng ngay. Page thì phải qua 'Tiếp' (chọn nơi đăng)
        rồi mới tới Đăng — nên nhảy tối đa vài bước thay vì bỏ cuộc ngay.
        """
        for hop in range(max_hops):
            button = self.find_post_button()
            if button is not None:
                if hop:
                    self.logger.info("FeedComposer: tới nút Đăng sau %d bước Tiếp", hop)
                return button

            nxt = self.find_next_button()
            if nxt is None:
                return None
            if not self._click(nxt, f"nút Tiếp (bước {hop + 1})"):
                return None
            self.page.wait_for_timeout(2500)

        return self.find_post_button()

    def submit(self) -> bool:
        """Đi qua các bước trung gian, bấm Đăng, rồi chờ hộp thoại đóng."""
        button = self.advance_to_post_button()
        if button is None:
            self.logger.error("FeedComposer: không tìm thấy nút Đăng (kể cả sau bước Tiếp)")
            return False

        try:
            if button.is_disabled(timeout=2000):
                self.logger.error("FeedComposer: nút Đăng đang bị khoá (thiếu nội dung?)")
                return False
        except Exception:
            pass

        if not self._click(button, "nút Đăng"):
            return False

        # Hộp thoại đóng = Facebook đã nhận bài.
        try:
            self.page.wait_for_selector('div[role="dialog"]', state="detached", timeout=90000)
            self.logger.info("FeedComposer: hộp thoại đã đóng — bài đã được gửi")
            return True
        except Exception:
            self.logger.warning(
                "FeedComposer: hộp thoại chưa đóng sau 90s — không chắc bài đã lên"
            )
            return False

    def close(self) -> None:
        """Đóng hộp thoại nếu còn mở (dùng trong finally)."""
        if self.dialog() is None:
            return
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(800)
            # Facebook hỏi 'Bỏ bài viết?' — xác nhận bỏ để không kẹt nháp.
            for label in ("Bỏ", "Discard"):
                btn = self.page.get_by_role("button", name=label, exact=True)
                if btn.count() > 0 and self._visible(btn.first):
                    btn.first.click(timeout=5000)
                    break
        except Exception as e:
            self.logger.debug("FeedComposer: đóng hộp thoại thất bại: %s", e)
