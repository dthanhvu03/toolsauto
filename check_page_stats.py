import sys
from playwright.sync_api import sync_playwright
import time

def check_page():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_3",
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = browser.new_page()
        try:
            print("1. Opening Da Dep Li Tu page...")
            page.goto("https://www.facebook.com/kids0810", timeout=60000)
            page.wait_for_timeout(5000)
            
            # Khởi động cuộn chuột xuống một chút để load các bài đăng
            print("2. Scrolling to load posts...")
            for _ in range(3):
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
            
            print("3. Extracting post contents...")
            posts = page.locator('div[data-ad-preview="message"], div[dir="auto"].html-div').all_inner_texts()
            
            print("\n=== NHỮNG BÀI ĐĂNG GẦN NHẤT ===")
            seen = set()
            count = 0
            for text in posts:
                text = text.strip()
                if len(text) > 20 and text not in seen and "Da Đẹp Lì Tu" not in text:
                    seen.add(text)
                    count += 1
                    print(f"--- BÀI {count} ---")
                    print(text[:200] + "..." if len(text) > 200 else text)
                    if count >= 3:
                        break
                        
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    check_page()
