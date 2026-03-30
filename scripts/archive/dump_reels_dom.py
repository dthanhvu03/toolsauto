import asyncio
from playwright.async_api import async_playwright
import os
import sys
import json

sys.path.insert(0, os.path.abspath('.'))

async def dump_reels_dom():
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
        await page.wait_for_timeout(10000) # wait long enough for video to load
        
        # Scrape all innertexts of span and div that are short and have numbers
        texts = await page.evaluate('''() => {
            const elements = document.querySelectorAll('span, div');
            const results = new Set();
            for(let el of elements) {
                const t = (el.innerText || "").trim();
                const aria = (el.getAttribute('aria-label') || "").trim();
                
                if(t.length > 0 && t.length < 30 && t.match(/\\d/)) {
                    results.add("TEXT: " + t);
                }
                if(aria.length > 0 && aria.match(/\\d/)) {
                    results.add("ARIA: " + aria);
                }
            }
            return Array.from(results);
        }''')
        
        with open("reels_texts.json", "w", encoding="utf-8") as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)
            
        print(f"Dumped {len(texts)} lines to reels_texts.json")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(dump_reels_dom())
