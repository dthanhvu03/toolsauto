import asyncio
from playwright.async_api import async_playwright
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

async def debug_ui():
    async with async_playwright() as p:
        profile_path = "/root/toolsauto/content/profiles/facebook_1"
        if not os.path.exists(profile_path):
            print(f"Error: Profile path {profile_path} does not exist.")
            return

        print(f"Opening browser with profile: {profile_path}")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--window-size=1280,720"
            ]
        )
        page = browser.pages[0]
        
        print("Navigating to Facebook Home...")
        await page.goto("https://www.facebook.com", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        print("Capturing state...")
        await page.screenshot(path="logs/debug_vps_home.png", full_page=True)
        with open("logs/debug_vps_home.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
            
        print("Checking for avatar menu...")
        # Try to find the avatar menu button
        selectors = [
            'div[aria-label="Trang cá nhân của bạn"]',
            'div[aria-label="Tài khoản của bạn"]',
            'div[aria-label="Your profile"]',
            'div[aria-label="Account"]',
            'div[role="navigation"] img',
            'div[role="banner"] [role="button"]'
        ]
        for sel in selectors:
            count = await page.locator(sel).count()
            print(f"Selector '{sel}': {count} found")
            if count > 0:
                await page.locator(sel).first.screenshot(path=f"logs/debug_vps_selector_{count}.png")

        await browser.close()
        print("Debug artifacts saved to logs/debug_vps_home.png and .html")

if __name__ == "__main__":
    asyncio.run(debug_ui())
