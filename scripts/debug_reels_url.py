import asyncio
from playwright.async_api import async_playwright
import os
import sys
import re

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
        
        print(f"Current Page URL: {page.url}")
        
        # Method 1: Get from playing video data-id?
        # Many times the video element has no ID, but let's check links on screen
        links = await page.evaluate('''() => {
            let anchors = document.querySelectorAll('a[href*="/reel/"], a[role="link"]');
            let res = [];
            for(let a of anchors) {
               if(a.href && a.href.includes('/reel/')) {
                   res.push(a.href);
               }
            }
            return res;
        }''')
        
        print("Found Links starting with /reel/:")
        for idx, l in enumerate(list(set(links))):
             print(f"{idx}: {l}")

        # Method 2: Try to get URL from share button or similar?
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(ss_reel())
