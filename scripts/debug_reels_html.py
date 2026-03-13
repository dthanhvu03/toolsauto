import asyncio
from playwright.async_api import async_playwright
import os
import sys

sys.path.insert(0, os.path.abspath('.'))

async def ss_reel():
    profile_path = "/home/vu/toolsauto/content/profiles/facebook_3"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        print("Navigating to Facebook Reel...")
        await page.goto("https://www.facebook.com/reel", wait_until="domcontentloaded")
        await page.wait_for_timeout(10000)
        
        html = await page.content()
        with open("reels_body.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("Saved HTML to reels_body.html")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(ss_reel())
