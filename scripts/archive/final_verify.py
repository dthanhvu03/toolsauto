"""
Final verification script: Go to Page and confirm the Reel is there.
"""
import os, time, logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

OUT = "/home/vu/.gemini/antigravity/brain/d0c27c4e-d543-4727-8211-95446000a188"
os.makedirs(OUT, exist_ok=True)

def ss(page, name):
    path = f"{OUT}/{name}.png"
    page.screenshot(path=path, full_page=True)
    logger.info(f"📸 {path}")

def verify():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=True,
            viewport={"width": 1280, "height": 1000}
        )
        page = context.pages[0]
        
        target = "https://www.facebook.com/profile.php?id=61564820652101"
        logger.info(f"Verifying posts on {target}")
        page.goto(target, wait_until="networkidle")
        page.wait_for_timeout(5000)
        
        # Scroll a bit to ensure feed loads
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(2000)
        
        ss(page, "final_verify_page_feed")
        
        context.close()

if __name__ == "__main__":
    verify()
