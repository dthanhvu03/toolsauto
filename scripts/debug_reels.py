import asyncio
from playwright.async_api import async_playwright
import os
import sys

sys.path.insert(0, os.path.abspath('.'))

async def debug_reel_scrape():
    profile_path = "/home/vu/toolsauto/content/profiles/facebook_3"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        print("Navigating to Facebook Reels...")
        await page.goto("https://www.facebook.com/reels/", wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)
        
        print("--- Body Inner Text ---")
        text = await page.evaluate("document.body.innerText")
        print("\n".join(text.split("\n")[:100]))
        
        print("--- Extract Reel Links via XPATH/CSS ---")
        links = await page.evaluate('''() => {
            const list = [];
            // Many times reel links are in a tags
            for (let a of document.querySelectorAll('a')) {
                 if (a.href && a.href.includes('/reel/')) list.push(a.href);
            }
            return Array.from(new Set(list));
        }''')
        print("Links found:", links)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_reel_scrape())
