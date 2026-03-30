from playwright.sync_api import sync_playwright

def check_ss():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_3",
            headless=True,
            viewport={"width": 1280, "height": 1080},
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = browser.new_page()
        page.goto("https://www.facebook.com/kids0810", timeout=60000)
        page.wait_for_timeout(5000)
        page.screenshot(path="dadep_screenshot.png", full_page=True)
        browser.close()
        print("Screenshot saved to /home/vu/toolsauto/dadep_screenshot.png")

check_ss()
