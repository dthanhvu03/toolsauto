import re
import time
from playwright.sync_api import sync_playwright

def parse_views(text):
    text = text.upper().replace(',', '.')
    match = re.search(r'([\d\.]+)\s*K', text)
    if match:
        return float(match.group(1)) * 1000
    match = re.search(r'([\d\.]+)\s*M', text)
    if match:
        return float(match.group(1)) * 1000000
    match = re.search(r'(\d+)', text)
    if match:
        return float(match.group(1))
    return 0

def analyze_insights():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_3",
            headless=True,
            viewport={"width": 1280, "height": 1080},
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-notifications"]
        )
        page = browser.new_page()
        
        print("--- ĐANG QUÉT TOÀN BỘ REELS ĐỂ TÌM TOP VIEWS ---")
        try:
            page.goto("https://www.facebook.com/kids0810/reels/", timeout=60000)
            page.wait_for_timeout(5000)
            
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
            
            valid_reels = []
            seen = set()
            for r in reels_data:
                href = r['href'].split('?')[0]
                if "/reel/" in href and href not in seen:
                    seen.add(href)
                    text = r['text'].strip()
                    if "K" in text.upper() or "M" in text.upper() or any(c.isdigit() for c in text):
                        valid_reels.append({"url": href, "views_text": text, "views_num": parse_views(text)})
            
            # Sort by views descending
            valid_reels.sort(key=lambda x: x["views_num"], reverse=True)
            top_reels = valid_reels[:5]
            
            print(f"\\n--- TÌM THẤY {len(valid_reels)} REELS. ĐANG PHÂN TÍCH TOP {len(top_reels)} ---")
            
            for i, reel in enumerate(top_reels):
                print(f"\\n[{i+1}] Đang phân tích Reel: {reel['views_text']} views (URL: {reel['url']})")
                try:
                    page.goto(reel['url'], timeout=60000)
                    page.wait_for_timeout(4000)
                    
                    # Extract caption and engagement from the reel page
                    details = page.evaluate("""() => {
                        let caption = "";
                        let likes = "0";
                        let comments = "0";
                        
                        // Try to find caption
                        let msgNode = document.querySelector('div[data-ad-preview="message"]');
                        if(!msgNode) msgNode = document.querySelector('span[dir="auto"]'); // reel caption fallback
                        if(msgNode) caption = msgNode.innerText.replace(/\\n/g, ' ');

                        // Try to find likes (aria-label usually has "Like: 123 people")
                        let likeNode = document.querySelector('div[aria-label*="Like"]');
                        if(!likeNode) likeNode = document.querySelector('div[aria-label*="Thích"]');
                        if(!likeNode) likeNode = document.querySelector('.x1n2onr6.x1ja2u2z.xa2298j');
                        if(likeNode) likes = likeNode.innerText || likeNode.getAttribute('aria-label') || "0";
                        
                        return {caption: caption, likes: likes};
                    }""")
                    
                    print(f"   => Lượt xem: {reel['views_text']}")
                    print(f"   => Tương tác (Likes/Reactions): {details['likes'].strip()}")
                    print(f"   => Nội dung: {details['caption'][:250]}...")
                except Exception as e:
                    print(f"   => Lỗi khi truy cập reel này: {e}")
                    
        except Exception as e:
            print(f"Lỗi chung: {e}")

        browser.close()

if __name__ == "__main__":
    analyze_insights()
