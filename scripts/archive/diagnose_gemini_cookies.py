import json
import time
import os
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

COOKIE_PATH = "/home/vu/toolsauto/gemini_cookies.json"
DEBUG_FILE = "/home/vu/toolsauto/debug_steps/diagnosis_login.png"

def diagnose():
    if not os.path.exists(COOKIE_PATH):
        logger.error("No cookies found!")
        return

    with open(COOKIE_PATH, "r") as f:
        cookies = json.load(f)

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    
    # We use a virtual display if available, but for diagnosis we want a screenshot
    driver = uc.Chrome(options=options)
    
    try:
        logger.info("Navigating to Gemini...")
        driver.get("https://gemini.google.com")
        time.sleep(2)
        
        logger.info("Adding cookies...")
        for c in cookies:
            try:
                driver.add_cookie({
                    "name": c["name"], "value": c["value"],
                    "domain": c.get("domain", ".google.com"),
                    "path": c.get("path", "/"),
                })
            except Exception as e:
                logger.warning(f"Error adding cookie {c['name']}: {e}")
                
        logger.info("Navigating to Gemini App...")
        driver.get("https://gemini.google.com/app")
        time.sleep(10)
        
        logger.info(f"Current URL: {driver.current_url}")
        
        os.makedirs(os.path.dirname(DEBUG_FILE), exist_ok=True)
        driver.save_screenshot(DEBUG_FILE)
        logger.info(f"Screenshot saved to {DEBUG_FILE}")
        
        # Check for sign-in elements
        signin_elements = driver.find_elements(By.CSS_SELECTOR, ".sign-in-button, a[href*='ServiceLogin']")
        logger.info(f"Found {len(signin_elements)} sign-in elements.")
        for i, el in enumerate(signin_elements):
            logger.info(f"Element {i} visible: {el.is_displayed()}, text: {el.text}")

    finally:
        driver.quit()

if __name__ == "__main__":
    diagnose()
