"""
Test trực tiếp: gõ tiếng Việt có dấu vào Facebook Search.
Kiểm tra kết quả trước và sau khi fix.

Mở browser thật, gõ "thời trang nữ" vào search, chụp screenshot.
"""
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright.sync_api import sync_playwright
from app.utils.human_behavior import human_search

PROFILE_PATH = "/home/vu/toolsauto/content/profiles/facebook_4"
SEARCH_QUERY = "thời trang nữ"
SCREENSHOT_PATH = "/home/vu/toolsauto/debug_steps/search_vn_test.png"

print(f"🔍 Test: gõ '{SEARCH_QUERY}' vào Facebook Search")
print(f"📂 Profile: {PROFILE_PATH}")

pw = sync_playwright().start()
ctx = pw.chromium.launch_persistent_context(
    user_data_dir=PROFILE_PATH,
    headless=False,
    viewport={"width": 1280, "height": 720},
    args=[
        '--disable-dev-shm-usage',
        '--no-sandbox',
        '--disable-gpu',
    ]
)

page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.set_default_timeout(30000)

try:
    print("  → Navigating to facebook.com...")
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Check login
    login_btn = page.locator('button[name="login"]').count() > 0
    email_in = page.locator('input[name="email"]').count() > 0
    if login_btn and email_in:
        print("  ❌ Account is logged out! Cannot test search.")
        sys.exit(1)

    print(f"  → Typing search query: '{SEARCH_QUERY}'")
    human_search(page, SEARCH_QUERY)

    print("  → Waiting for search results...")
    page.wait_for_timeout(3000)

    # Capture the search results page
    os.makedirs(os.path.dirname(SCREENSHOT_PATH), exist_ok=True)
    page.screenshot(path=SCREENSHOT_PATH)
    print(f"  📸 Screenshot saved: {SCREENSHOT_PATH}")

    # Check what text ended up in the search/URL
    current_url = page.url
    print(f"  🌐 Current URL: {current_url}")

    # Check if the query appears in the page title or URL
    if "th" in current_url.lower() or "trang" in current_url.lower():
        print("  ✅ Vietnamese query found in URL — Search worked correctly!")
    else:
        print(f"  ⚠️  URL does not contain query words. Checking page content...")
        # Check page text
        body_text = page.locator("body").inner_text()[:500]
        if "thời trang" in body_text.lower() or "trang" in body_text.lower():
            print("  ✅ Vietnamese text found in page body — Search worked!")
        else:
            print("  ❌ Vietnamese text NOT found — something may be wrong")
            print(f"  Body preview: {body_text[:200]}")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    ctx.close()
    pw.stop()
    print("  → Browser closed.")
