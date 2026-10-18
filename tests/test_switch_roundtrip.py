"""
Test đổi context: Target Page -> Profile cá nhân -> lại Target Page.
Verify sau mỗi bước bằng cách goto /me và so URL (giống FacebookAdapter.publish).

Chạy (profile phải là thư mục đã login FB, vd. facebook_4):
  source venv/bin/activate
  export FB_TEST_PROFILE=/home/vu/toolsauto/content/profiles/facebook_4
  export FB_TEST_PAGE_NAME='Mẹ Sún Riviu'
  export FB_TEST_TARGET_URL='https://www.facebook.com/profile.php?id=61575025600591'
  export FB_TEST_PERSONAL_NAME='Hoang Khoa'
  python3 test_switch_roundtrip.py

Production: nếu DB trỏ facebook_1 nhưng session thật ở facebook_4 thì switch sẽ luôn sai
hoặc không thấy menu — cần profile_path trong DB khớp thư mục đã login.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from app.config import CONTENT_DIR, PROFILES_DIR
from app.features.facebook.adapter import FacebookAdapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_profile_dir() -> Path:
    override = os.environ.get("FB_TEST_PROFILE", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        if p.is_dir():
            return p
        logger.warning("FB_TEST_PROFILE không hợp lệ: %s", p)
    _cp = CONTENT_DIR / "profiles"
    for candidate in (
        _cp / "facebook_3",
        _cp / "facebook_4",
        PROFILES_DIR / "fb_acc_01_profile",
        _cp / "facebook_2",
        _cp / "facebook_1",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit("Không tìm thấy profile. Đặt FB_TEST_PROFILE.")


def _normalize_for_compare(u: str) -> str:
    if not u:
        return ""
    base = u.split("?")[0].rstrip("/")
    if "id=" in u:
        pieces = u.split("id=")
        if len(pieces) > 1:
            base += "?id=" + pieces[1].split("&")[0]
    return base


def verify_matches_target(page, target_page_url: str) -> tuple[bool, str, str]:
    """Khớp logic verify trong FacebookAdapter.publish (context /me)."""
    page.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    active_url = page.url
    nt = _normalize_for_compare(target_page_url)
    na = _normalize_for_compare(active_url)

    def _url_has_profile_path(url: str) -> bool:
        try:
            path = urlparse(url).path or ""
            return path not in ("", "/")
        except Exception:
            return True

    target_in_active = nt in na
    active_in_target = na in nt and _url_has_profile_path(active_url)
    ok = bool(nt and na and (target_in_active or active_in_target))
    tid = re.search(r"[?&]id=(\d{5,})", target_page_url or "")
    if tid and tid.group(1) in active_url:
        ok = True
    return ok, na, nt


def main() -> None:
    profile_path = _resolve_profile_dir()
    target_url = os.environ.get(
        "FB_TEST_TARGET_URL",
        "https://www.facebook.com/profile.php?id=61575025600591",
    ).strip()
    page_name = os.environ.get("FB_TEST_PAGE_NAME", "").strip()
    personal = os.environ.get("FB_TEST_PERSONAL_NAME", "").strip()

    if not page_name:
        raise SystemExit("Cần FB_TEST_PAGE_NAME")
    if not personal:
        raise SystemExit("Cần FB_TEST_PERSONAL_NAME (tên hiển thị trên menu chuyển profile)")

    logger.info("Profile: %s", profile_path)
    adapter = FacebookAdapter()
    try:
        if not adapter.open_session(str(profile_path)):
            raise SystemExit("open_session failed")

        p = adapter.page

        def switch_to_target(label: str) -> bool:
            logger.info("=== %s: navigate + switch -> %s ===", label, page_name)
            p.goto(target_url, wait_until="domcontentloaded")
            p.wait_for_timeout(4000)
            from app.features.facebook.selectors import SELECTORS

            sw = p.locator(SELECTORS["switch_menu"]["switch_now_button"]).first
            if sw.count() > 0 and sw.is_visible():
                sw.click()
                p.wait_for_timeout(5000)
                return True
            return adapter._switch_to_page_context(page_name, target_page_url=target_url)

        # 1) -> Page
        ok = switch_to_target("Round 1")
        logger.info("_switch_to_page_context / switch now: %s", ok)
        match, na, nt = verify_matches_target(p, target_url)
        logger.info("Verify /me: active=%s target_norm=%s OK=%s", na, nt, match)
        if not match:
            logger.error("FAIL: context chưa khớp target page sau lần 1.")
            time.sleep(15)
            return

        # 2) -> Personal
        logger.info("=== Switch về profile cá nhân: %s ===", personal)
        adapter._switch_to_personal_profile(personal)
        p.wait_for_timeout(5000)
        p.goto("https://www.facebook.com/me", wait_until="domcontentloaded")
        p.wait_for_timeout(3000)
        logger.info("URL /me sau personal: %s", p.url)

        # 3) -> Page lại
        ok2 = switch_to_target("Round 2")
        logger.info("Second switch: %s", ok2)
        match2, na2, nt2 = verify_matches_target(p, target_url)
        logger.info("Verify /me lần 2: active=%s target_norm=%s OK=%s", na2, nt2, match2)
        if match2:
            logger.info("OK: đổi page qua lại + verify thành công.")
        else:
            logger.error("FAIL: lần 2 không khớp target.")

        time.sleep(8)
    finally:
        adapter.close_session()


if __name__ == "__main__":
    main()
