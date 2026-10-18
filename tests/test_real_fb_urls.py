import time
import re
from playwright.sync_api import sync_playwright

_REEL_ID_RE = re.compile(r"/reel/(\d+)", re.IGNORECASE)

def _normalize_post_url(url: str | None) -> str | None:
    if not url: return None
    u = str(url).strip()
    if not u: return None
    if u.startswith("/"): u = "https://www.facebook.com" + u
    u = u.split("#")[0].split("?")[0].rstrip("/")
    if u.endswith("/reel") or u.endswith("/reel/"): return None
    if _REEL_ID_RE.search(u): return u
    if ("/videos/" in u or "/posts/" in u) and len(u) > 30: return u
    return None

def test():
    print("Starting Playwright to check Facebook Reel URLs format...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=True,
            viewport={"width": 1280, "height": 900},
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)

        print("Navigating to https://www.facebook.com/me/reels_tab ...")
        page.goto("https://www.facebook.com/me/reels_tab", wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        # Click "See more" or scroll to ensure reels load
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        links = page.locator('a').all()
        hrefs = []
        for l in links:
            h = l.get_attribute("href")
            if h and ("/reel/" in h or "/share/r/" in h or "/share/v/" in h):
                hrefs.append(h)
        
        unique_hrefs = list(set(hrefs))
        print(f"Found {len(unique_hrefs)} potential reel links.")
        print("-" * 50)
        
        for h in unique_hrefs[:15]:
            norm = _normalize_post_url(h)
            print(f"RAW URL: {h}")
            print(f"NORMALIZED: {norm}")
            print("-" * 50)
            
        print("Done capturing evidence.")
        context.close()

if __name__ == "__main__":
    test()
