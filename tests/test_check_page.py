"""
Quick check: Navigate to the Page and screenshot what's on the feed.
"""
import logging
import time
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

def check_page():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)

        target = "https://www.facebook.com/profile.php?id=61564820652101"
        logger.info(f"Navigating to {target}")
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        page.screenshot(path="/tmp/page_feed_check.png", full_page=False)
        logger.info("Screenshot 1 saved")
        
        # Scroll down to see more posts
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/page_feed_check2.png", full_page=False)
        logger.info("Screenshot 2 saved (scrolled)")
        
        # Check for "LỠ VA" or today's caption in the feed
        body_text = page.evaluate("document.body.innerText")
        if "LỠ VA VÀO" in body_text:
            logger.info("✅ Found today's caption on the Page!")
        elif "lầm lỡ" in body_text:
            logger.info("✅ Found today's caption on the Page (partial match)")
        else:
            logger.info("❌ Today's caption NOT found on the Page feed")
            # Show first 500 chars of visible text for context
            logger.info(f"Feed text preview: {body_text[:500]}")
        
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    check_page()
