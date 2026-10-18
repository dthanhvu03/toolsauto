"""
Thủ công: mở Chrome profile, vào FB, mở menu chuyển profile và (tuỳ chọn) click page thứ 2.

Chạy (từ root repo, trong venv):
  source venv/bin/activate && python3 test_switch_page.py

Profile mặc định (nếu không set FB_TEST_PROFILE): ưu tiên content/profiles/facebook_3, facebook_4, rồi profiles/fb_acc_01_profile, ...
Đổi profile: FB_TEST_PROFILE=/đường/dần/tới/user_data_dir python3 test_switch_page.py

Cần DISPLAY (headless=False). WSL: X server hoặc VNC.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from app.config import BASE_DIR, CONTENT_DIR, PROFILES_DIR
from app.features.facebook.adapter import FacebookAdapter


def _resolve_profile_dir() -> Path:
    override = os.environ.get("FB_TEST_PROFILE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
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
    return (PROFILES_DIR / "fb_acc_01_profile").resolve()


def main() -> None:
    profile_path = _resolve_profile_dir()
    if not profile_path.is_dir():
        print(f"[LỖI] Không thấy thư mục profile: {profile_path}")
        print(f"      Tạo hoặc chỉnh FB_TEST_PROFILE / dùng content/profiles/facebook_3|4")
        raise SystemExit(1)

    print(f"[INFO] BASE_DIR={BASE_DIR}")
    print(f"[INFO] Profile: {profile_path}")

    adapter = FacebookAdapter()
    try:
        if not adapter.open_session(str(profile_path)):
            print("[LỖI] open_session thất bại.")
            return
        print("[OK] Trình duyệt khởi động thành công.")

        page = adapter.page
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        profile_btn = page.locator(
            'div[aria-label="Your profile"], div[aria-label="Trang cá nhân của bạn"], '
            'div[aria-label="Tài khoản của bạn"], div[aria-label="Tài khoản"], div[aria-label="Account"]'
        ).first
        n_menu = profile_btn.count()
        print(f"[INFO] Nút menu profile (locator): count={n_menu}")
        if n_menu == 0:
            print("[CẢNH BÁO] Không thấy nút avatar/menu. Kiểm tra đã login FB trong profile này chưa.")
            time.sleep(5)
            return

        print("[OK] Đã tìm thấy nút menu Profile, đang click...")
        profile_btn.click()
        page.wait_for_timeout(2000)

        see_all_btn = page.locator(
            'div[role="button"]:has-text("See all profiles"), '
            'div[role="button"]:has-text("Xem tất cả trang cá nhân")'
        ).first
        if see_all_btn.count() == 0:
            print(
                "[INFO] Không thấy 'Xem tất cả trang cá nhân' — có thể danh sách đã hiện đủ hoặc chỉ 1 tài khoản."
            )
        else:
            print("[OK] Đã tìm thấy nút 'Xem tất cả trang cá nhân', đang click...")
            see_all_btn.click()
            page.wait_for_timeout(2000)

        profiles = page.evaluate(
            """() => {
                const results = [];
                const elements = document.querySelectorAll('div[role="dialog"] div[role="radio"]');
                for (const el of elements) {
                    const nameEl = el.querySelector('span[dir="auto"]');
                    if (nameEl && nameEl.innerText) {
                        results.push(nameEl.innerText.trim());
                    }
                }
                return results;
            }"""
        )

        print("[INFO] Danh sách profiles/pages (role=radio trong dialog):")
        if not profiles:
            print("  (trống — FB có thể dùng menuitemradio/div khác; xem VNC hoặc chỉnh selector)")
        for i, p in enumerate(profiles):
            print(f"  [{i}] {p}")

        if len(profiles) > 1:
            target = profiles[1]
            print(f"[INFO] Thử chuyển sang: {target!r}")
            esc = target.replace('"', '\\"')
            page_radio = page.locator(
                f'div[role="dialog"] div[role="radio"]:has-text("{esc}")'
            ).first
            if page_radio.count() == 0:
                print("[CẢNH BÁO] Không locate được radio theo tên — thử click tay trên cửa sổ.")
            else:
                page_radio.click()
                page.wait_for_timeout(5000)
                print(f"[OK] Đã click. URL hiện tại: {page.url}")
        else:
            print("[INFO] Không đủ mục để auto-chọn index 1.")

        print("[INFO] Giữ cửa sổ 10s để quan sát...")
        time.sleep(10)
    finally:
        adapter.close_session()
        print("[INFO] Đã đóng session.")


if __name__ == "__main__":
    main()
