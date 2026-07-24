"""
Open a visible Chrome window for Gemini/Google login, then save cookies
to storage/db/config/gemini_cookies.json (via app.config).

Only saves when real Google auth cookies are present (__Secure-1PSID).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path

# Allow `python scripts/login_gemini_bypass.py` from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import app.config as config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

COOKIE_PATH = Path(config.GEMINI_COOKIES_FILE)
INVALID_FLAG = Path(config.GEMINI_COOKIES_INVALID_FLAG)

# HealthService.get_gemini_health() requires this cookie with future expiry.
REQUIRED_AUTH_COOKIE = "__Secure-1PSID"
HELPFUL_AUTH_COOKIES = ("__Secure-1PSID", "__Secure-1PSIDTS", "SID", "HSID", "SSID")


def detect_chrome_major() -> int | None:
    """Detect installed Google Chrome major version (Windows + common binaries)."""
    if os.name == "nt":
        return _detect_chrome_major_windows()
    return _detect_chrome_major_unix()


def _detect_chrome_major_windows() -> int | None:
    import winreg

    for root, path in (
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon"),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "version")
            match = re.match(r"(\d+)\.", str(version))
            if match:
                return int(match.group(1))
        except OSError:
            continue
    for base in (
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
    ):
        app_dir = Path(base) / "Google/Chrome/Application"
        if not app_dir.is_dir():
            continue
        for child in app_dir.iterdir():
            match = re.match(r"^(\d+)\.", child.name)
            if child.is_dir() and match:
                return int(match.group(1))
    return None


def _detect_chrome_major_unix() -> int | None:
    import subprocess

    for bin_name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        try:
            out = subprocess.check_output(
                [bin_name, "--version"], stderr=subprocess.STDOUT, text=True
            ).strip()
            match = re.search(r"(\d+)\.", out)
            if match:
                return int(match.group(1))
        except Exception:
            continue
    return None


def clear_uc_driver_cache() -> None:
    """Drop cached UC chromedriver so version_main can download a matching driver."""
    if os.name == "nt":
        cache_root = Path(os.environ.get("APPDATA", "")) / "undetected_chromedriver"
        cached = cache_root / "undetected_chromedriver.exe"
    else:
        cache_root = Path.home() / ".local/share/undetected_chromedriver"
        cached = cache_root / "undetected_chromedriver"
    if not cached.is_file():
        return
    logger.warning("Xóa UC chromedriver cache để khớp Chrome version: %s", cached)
    try:
        cached.unlink(missing_ok=True)
    except Exception:
        shutil.rmtree(cache_root, ignore_errors=True)


def cookie_names(driver) -> set[str]:
    try:
        return {c.get("name", "") for c in driver.get_cookies()}
    except Exception:
        return set()


def is_logged_in(driver) -> bool:
    """Strict check: must have Google auth cookie used by HealthService."""
    names = cookie_names(driver)
    if REQUIRED_AUTH_COOKIE not in names:
        present = sorted(names & set(HELPFUL_AUTH_COOKIES))
        logger.info(
            "Chưa login (thiếu %s). Auth cookies thấy: %s",
            REQUIRED_AUTH_COOKIE,
            present or "(none)",
        )
        return False
    logger.info("Đã có %s — coi như login OK.", REQUIRED_AUTH_COOKIE)
    return True


def mark_cookies_invalid() -> None:
    INVALID_FLAG.parent.mkdir(parents=True, exist_ok=True)
    INVALID_FLAG.write_text("invalid\n", encoding="utf-8")


def save_cookies(driver) -> int:
    if not is_logged_in(driver):
        logger.error("Từ chối lưu — chưa có cookie auth %s.", REQUIRED_AUTH_COOKIE)
        mark_cookies_invalid()
        return 0

    logger.info("Đang trích xuất cookies từ Gemini...")
    cookies = driver.get_cookies()

    logger.info("Bổ sung cookies từ myaccount.google.com...")
    driver.get("https://myaccount.google.com/")
    time.sleep(3)
    google_cookies = driver.get_cookies()

    cookie_dict = {c["name"]: c for c in cookies}
    for gc in google_cookies:
        cookie_dict[gc["name"]] = gc
    all_cookies = list(cookie_dict.values())

    names = {c.get("name") for c in all_cookies}
    if REQUIRED_AUTH_COOKIE not in names:
        logger.error(
            "Sau khi gom cookie vẫn thiếu %s — không ghi file.",
            REQUIRED_AUTH_COOKIE,
        )
        mark_cookies_invalid()
        return 0

    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        json.dump(all_cookies, f, indent=2)

    try:
        INVALID_FLAG.unlink(missing_ok=True)
    except FileNotFoundError:
        pass

    logger.info("Đã lưu %s cookies vào %s", len(all_cookies), COOKIE_PATH)
    print("\nHOÀN TẤT! Cookie login hợp lệ đã lưu.")
    return len(all_cookies)


def launch_chrome():
    import undetected_chromedriver as uc

    major = detect_chrome_major()
    if major:
        logger.info("Detected Chrome major version: %s", major)
        clear_uc_driver_cache()
    else:
        logger.warning("Không detect được Chrome version — UC có thể tải sai chromedriver.")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1600,900")
    kwargs = {"options": options}
    if major:
        kwargs["version_main"] = major
    return uc.Chrome(**kwargs)


def wait_for_login(driver, timeout_sec: int) -> bool:
    logger.info("Chờ anh đăng nhập Google/Gemini (timeout %ss)...", timeout_sec)
    print("\n" + "=" * 60)
    print(" CHÚ Ý: TRÌNH DUYỆT ĐÃ MỞ — ĐỪNG ĐÓNG CỬA SỔ NÀY")
    print(" 1. Trong Chrome: đăng nhập tài khoản Google.")
    print(" 2. Vào được Gemini chat (không còn nút Sign in).")
    print(" 3. Script chỉ lưu khi thấy cookie __Secure-1PSID.")
    print(" 4. Giữ Chrome mở tới khi terminal báo HOÀN TẤT.")
    print("=" * 60 + "\n")

    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        try:
            # Stay on Gemini so login redirects land correctly.
            if "gemini.google.com" not in (driver.current_url or ""):
                driver.get("https://gemini.google.com/app")
                time.sleep(2)
            if is_logged_in(driver):
                return True
        except Exception as e:
            logger.warning("Kiểm tra login lỗi (retry): %s", e)
        time.sleep(5)

    logger.error("Timeout %ss — vẫn chưa login. Không lưu cookie.", timeout_sec)
    return False


def main() -> None:
    import importlib.util

    if importlib.util.find_spec("undetected_chromedriver") is None:
        logger.error(
            "Thiếu package undetected-chromedriver. "
            "Cài: pip install undetected-chromedriver==3.5.5"
        )
        raise SystemExit(1)

    logger.info("Khởi động Chrome (undetected_chromedriver)...")
    driver = None
    try:
        driver = launch_chrome()
    except Exception as e:
        logger.error("Lỗi khởi tạo Chrome: %s", e)
        raise SystemExit(1)

    exit_code = 1
    try:
        logger.info("Mở Gemini...")
        driver.get("https://gemini.google.com/app")
        time.sleep(2)

        timeout_sec = int(os.environ.get("GEMINI_LOGIN_TIMEOUT_SEC", "600"))
        if not wait_for_login(driver, timeout_sec):
            mark_cookies_invalid()
            print("\nTHẤT BẠI: chưa login kịp. Bấm Cookie trên dashboard rồi thử lại.")
            raise SystemExit(1)

        saved = save_cookies(driver)
        if saved <= 0:
            print("\nTHẤT BẠI: không lưu được cookie auth.")
            raise SystemExit(1)
        exit_code = 0
    finally:
        logger.info("Đóng trình duyệt...")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
            try:
                # Avoid UC __del__ double-quit noise on Windows.
                driver.service = None  # type: ignore[attr-defined]
            except Exception:
                pass

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
