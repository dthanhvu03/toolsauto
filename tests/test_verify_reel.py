"""
Quick check if the newly posted Reel exists.
URL: https://www.facebook.com/reel/380840374853165/
"""
import logging
import os
import time
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

def test():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30000)

        # Go to the Reel URL returned by fallback
        reel_url = "https://www.facebook.com/reel/380840374853165/"
        logger.info(f"Checking URL: {reel_url}")
        page.goto(reel_url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        page.screenshot(path="/home/vu/.gemini/antigravity/brain/d0c27c4e-d543-4727-8211-95446000a188/final_reel_verify.png")
        logger.info("📸 Saved screenshot of the Reel page")
        
        # Check text
        body_text = page.evaluate("document.body.innerText")
        logger.info(f"Page text excerpt: {body_text[:200].replace(chr(10), ' ')}")
        
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    test()
