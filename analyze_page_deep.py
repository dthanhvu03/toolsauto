from playwright.sync_api import sync_playwright

def analyze():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_3",
            headless=True,
            viewport={"width": 1280, "height": 1080},
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-notifications"]
        )
        page = browser.new_page()
        
        print("--- 1. TÌM KIẾM REELS VIEWS ---")
        try:
            page.goto("https://www.facebook.com/kids0810/reels/", timeout=60000)
            page.wait_for_timeout(5000)
            
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 1500)")
                page.wait_for_timeout(2000)
                
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
            for r in reels_data:
                # filter out links that don't look like single reels
                if "/reel/" in r['href'] and r['href'] not in seen:
                    print(f"[{count+1}] Lượt xem: {r['text']} (URL: {r['href'].split('?')[0]})")
                    seen.add(r['href'])
                    count += 1
                    if count >= 10: break
        except Exception as e:
            print(f"Lỗi khi quét Reels: {e}")
            
        print("\n--- 2. TÌM KIẾM BÀI ĐĂNG GẦN NHẤT ---")
        try:
            page.goto("https://www.facebook.com/kids0810", timeout=60000)
            page.wait_for_timeout(5000)
            
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 3000)")
                page.wait_for_timeout(3000)
                
            feed_text = page.evaluate("""() => {
                let texts = [];
                // Facebook posts text container
                const blocks = document.querySelectorAll('div[data-ad-comet-preview="message"], div[dir="auto"].html-div');
                blocks.forEach(b => {
                    const t = b.innerText.trim();
                    if(t.length > 20) {
                        texts.push(t.replace(/\\n/g, ' '));
                    }
                });
                return texts;
            }""")
            
            seen_texts = set()
            count2 = 0
            for t in feed_text:
                if t not in seen_texts and "Da Đẹp Lì Tu" not in t:
                    print(f"[{count2+1}] Nội dung: {t[:250]}...")
                    seen_texts.add(t)
                    count2 += 1
                    if count2 >= 5: break
        except Exception as e:
            print(f"Lỗi khi quét Feed: {e}")

        browser.close()

if __name__ == "__main__":
    analyze()
