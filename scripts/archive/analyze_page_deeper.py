from playwright.sync_api import sync_playwright

def analyze_deep():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_3",
            headless=True,
            viewport={"width": 1280, "height": 1080},
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-notifications"]
        )
        page = browser.new_page()
        
        print("--- ĐANG TÌM KIẾM TOÀN BỘ REELS VIEWS ---")
        try:
            page.goto("https://www.facebook.com/kids0810/reels/", timeout=60000)
            page.wait_for_timeout(5000)
            
            # Scroll deeper to load many more reels
            for _ in range(15):
                page.evaluate("window.scrollBy(0, 2000)")
                page.wait_for_timeout(1500)
                
            reels_data = page.evaluate("""() => {
                const reels = [];
                const links = document.querySelectorAll('a[href*="/reel/"]');
                links.forEach(l => {
                    const text = l.innerText;
                    const href = l.href;
                    if(text && text.trim().length > 0) {
                        reels.push({href: href, text: text.replace(/\\n/g, ' ')});
                    }
                });
                return reels;
            }""")
            
            seen = set()
            count = 0
            # Collect and sort/filter
            valid_reels = []
            for r in reels_data:
                href = r['href'].split('?')[0]
                if "/reel/" in href and href not in seen:
                    seen.add(href)
                    text = r['text'].strip()
                    # FB might format views like "1,2K", "1.5K", or "1200"
                    valid_reels.append({"url": href, "text": text})
            
            for item in valid_reels:
                print(f"- Lượt xem: {item['text']} (URL: {item['url']})")
                
        except Exception as e:
            print(f"Lỗi khi quét Reels: {e}")

        browser.close()

if __name__ == "__main__":
    analyze_deep()
