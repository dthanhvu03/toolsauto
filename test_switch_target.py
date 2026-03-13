import logging
from playwright.sync_api import sync_playwright
import time
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_switch():
    with sync_playwright() as p:
        profile_path = "/home/vu/toolsauto/content/profiles/facebook_4"
        logger.info(f"Opening {profile_path}")
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=[
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        target_page_url = "https://www.facebook.com/profile.php?id=61564820652101"
        logger.info(f"Navigating to {target_page_url}")
        page.goto(target_page_url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        
        # Take a screenshot before switching
        page.screenshot(path="before_switch.png", full_page=True)
        
        # Original switch logic
        switch_btn = page.locator(
            'div[role="button"]:has-text("Switch now"), '
            'div[role="button"]:has-text("Chuyển ngay")'
        ).first
        
        if switch_btn.count() > 0:
            logger.info("Found 'Switch now' button. Clicking...")
            switch_btn.click()
            page.wait_for_timeout(5000)
            logger.info("Switched to Page context successfully.")
        else:
            logger.error("No 'Switch now' button found on the Page.")
            
        page.screenshot(path="after_switch.png")
            
        time.sleep(10)
        context.close()

if __name__ == "__main__":
    test_switch()
