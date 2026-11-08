"""Nạp cookie Threads / Instagram từ Chrome thật (Windows) vào profile bot kéo khách.

Dùng khi cửa sổ đăng nhập trên WSL không hiện được: chủ bot đăng nhập @us28qt trên Chrome Windows, xuất cookie
bằng J2TEAM Cookies hoặc Cookie-Editor (JSON mảng), lưu ra file rồi chạy:

    venv/bin/python app/scripts/import_threads_cookies.py <file.json> [--delete]

Script chỉ thêm cookie vào profile rồi mở Threads chạy ngầm để kiểm phiên (gặp checkpoint thì báo, không thử vượt).
Không in giá trị cookie. ``--delete`` xoá file cookie sau khi nạp.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from playwright.sync_api import sync_playwright  # noqa: E402

from app.scripts.login_browser import THREADS_HOST, threads_login_ok  # noqa: E402

PROFILE_DIR = Path(__file__).resolve().parents[2] / "storage" / "profiles" / "instagram_5"
ALLOWED_DOMAINS = ("threads.com", "threads.net", "instagram.com")
_SAME_SITE = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict"}


def parse_cookie_export(raw: str) -> list[dict]:
    """JSON J2TEAM / Cookie-Editor → cookie Playwright. Bỏ cookie ngoài Threads / Instagram."""
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cookies") or []
    out: list[dict] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("name") or item.get("value") is None:
            continue
        domain = str(item.get("domain") or "").strip()
        if not any(domain.lstrip(".").endswith(d) for d in ALLOWED_DOMAINS):
            continue
        cookie = {
            "name": str(item["name"]),
            "value": str(item["value"]),
            "domain": domain,
            "path": str(item.get("path") or "/"),
            "secure": bool(item.get("secure", True)),
            "httpOnly": bool(item.get("httpOnly", False)),
            "sameSite": _SAME_SITE.get(str(item.get("sameSite") or "").lower(), "Lax"),
        }
        expires = item.get("expirationDate", item.get("expires"))
        if isinstance(expires, (int, float)) and expires > 0 and not item.get("session"):
            cookie["expires"] = float(expires)
        if cookie["sameSite"] == "None":
            cookie["secure"] = True
        out.append(cookie)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cookie_file")
    parser.add_argument("--profile-dir", default=str(PROFILE_DIR))
    parser.add_argument("--delete", action="store_true", help="xoá file cookie sau khi nạp")
    args = parser.parse_args()

    path = Path(args.cookie_file)
    cookies = parse_cookie_export(path.read_text(encoding="utf-8-sig"))  # PowerShell ghi kèm BOM
    names = {c["name"] for c in cookies if "threads" in c["domain"]}
    print(f"Đọc được {len(cookies)} cookie Threads/Instagram (Threads: {len(names)}).")
    if "sessionid" not in names:
        print("THIẾU cookie sessionid của threads.com — xuất cookie khi đang mở trang threads.com đã đăng nhập.")
        return 2

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir, headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            ctx.add_cookies(cookies)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(f"{THREADS_HOST}/", timeout=45000)
            page.wait_for_timeout(5000)
            has_session = any(
                c.get("name") == "sessionid" and c.get("value") for c in ctx.cookies([f"{THREADS_HOST}/"])
            )
            ok = threads_login_ok(page.url, has_session)
            handle = page.query_selector('a[href^="/@"]')
            print("URL sau khi mở:", page.url.split("?")[0])
            print("KẾT QUẢ:", "ĐĂNG NHẬP OK" if ok and handle else "CHƯA OK (checkpoint / chưa đăng nhập)")
        finally:
            ctx.close()

    if args.delete:
        path.unlink(missing_ok=True)
        print("Đã xoá file cookie.")
    return 0 if ok and handle else 1


if __name__ == "__main__":
    sys.exit(main())
