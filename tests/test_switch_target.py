"""
Test chuyển context sang đúng Facebook Page (URL profile.php?id=...).

1) Thử nút "Switch now" / "Chuyển ngay" trên trang Page.
2) Nếu không có: gọi FacebookAdapter._switch_to_page_context (giống publisher).

Chạy (venv, có DISPLAY vì headless=False):
  source venv/bin/activate && python3 test_switch_target.py

Biến môi trường (tuỳ chọn):
  FB_TEST_PROFILE=/path/to/chrome/user_data
  FB_TEST_TARGET_URL=https://www.facebook.com/profile.php?id=61564820652101
  FB_TEST_PAGE_NAME=Tên Page trên menu   # phải là Page thuộc đúng Chrome profile / account (xem DB managed_pages)
  # Ví dụ DB local: Mẹ Sún Riviu (id=61575025600591) thuộc Hoang Khoa → content/profiles/facebook_3;
  # Thu Uyên / maymacenter thuộc Nguyen Ngoc Vi → facebook_4.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from app.config import BASE_DIR, CONTENT_DIR, PROFILES_DIR
from app.features.facebook.adapter import FacebookAdapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SHOT_DIR = BASE_DIR / "logs" / "screenshots"
SELECTORS_SWITCH_NOW = (
    'div[role="button"]:has-text("Switch now"), '
    'div[role="button"]:has-text("Chuyển ngay")'
)


def _resolve_profile_dir() -> Path:
    override = os.environ.get("FB_TEST_PROFILE", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        if p.is_dir():
            return p
        logger.warning("FB_TEST_PROFILE không phải thư mục: %s", p)
    # Thứ tự ưu tiên: acc đăng nhập thường nằm content/profiles/facebook_3|4 (account_id trong DB).
    _cp = CONTENT_DIR / "profiles"
    for candidate in (
        _cp / "facebook_3",
        _cp / "facebook_4",
        PROFILES_DIR / "fb_acc_01_profile",
        _cp / "facebook_2",
        _cp / "facebook_1",
    ):
        if candidate.is_dir():
            logger.info("Dùng profile: %s", candidate)
            return candidate.resolve()
    raise SystemExit(
        "Không tìm thấy thư mục Chrome profile. "
        "Đặt FB_TEST_PROFILE hoặc tạo content/profiles/facebook_3|4 (hoặc profiles/fb_acc_01_profile)."
    )


def main() -> None:
    profile_path = _resolve_profile_dir()
    target_page_url = os.environ.get(
        "FB_TEST_TARGET_URL",
        "https://www.facebook.com/profile.php?id=61564820652101",
    ).strip()
    target_page_name = os.environ.get("FB_TEST_PAGE_NAME", "").strip() or None

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    before_png = SHOT_DIR / "test_switch_target_before.png"
    after_png = SHOT_DIR / "test_switch_target_after.png"

    adapter = FacebookAdapter()
    try:
        if not adapter.open_session(str(profile_path)):
            logger.error("open_session thất bại")
            return

        page = adapter.page
        logger.info("Goto %s", target_page_url)
        page.goto(target_page_url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        try:
            page.screenshot(path=str(before_png), full_page=True)
            logger.info("Screenshot: %s", before_png)
        except Exception as e:
            logger.warning("Screenshot before: %s", e)

        switch_btn = page.locator(SELECTORS_SWITCH_NOW).first
        if switch_btn.count() > 0 and switch_btn.is_visible():
            logger.info("Có nút Switch now — đang click...")
            switch_btn.click()
            page.wait_for_timeout(5000)
            logger.info("Đã click Switch now.")
        else:
            logger.info("Không thấy Switch now — thử avatar menu (adapter)...")
            if not target_page_name:
                logger.error(
                    "Thiếu FB_TEST_PAGE_NAME; export FB_TEST_PAGE_NAME='Tên Page' để test fallback."
                )
            else:
                ok = adapter._switch_to_page_context(
                    target_page_name,
                    target_page_url=target_page_url,
                )
                logger.info("_switch_to_page_context -> %s", ok)

        try:
            page.screenshot(path=str(after_png), full_page=False)
            logger.info("Screenshot: %s", after_png)
        except Exception as e:
            logger.warning("Screenshot after: %s", e)

        logger.info("URL hiện tại: %s", page.url)
        logger.info("Giữ browser 10s...")
        time.sleep(10)
    finally:
        adapter.close_session()
        logger.info("Đã đóng session.")


if __name__ == "__main__":
    main()
