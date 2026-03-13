from app.adapters.facebook.adapter import FacebookAdapter
import time
import sqlalchemy
from app.database.core import engine, SessionLocal
from app.database.models import Account

adapter = FacebookAdapter()
try:
    if adapter.open_session("profiles/fb_acc_01_profile"):
        print("Trình duyệt khởi động thành công.")
        page = adapter.page
        page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        # In ra các trang tìm thấy
        print("Đang quét DOM để tìm các Page...")
        pages = page.evaluate("""() => {
            const results = [];
            // In the "Your Pages" view, pages are usually inside typical list items or cards
            const elements = document.querySelectorAll('a[href*="/"]');
            
            for(const el of elements) {
                const text = el.innerText.trim();
                const href = el.getAttribute('href');
                const ariaLabel = el.getAttribute('aria-label');
                
                // Usually pages have clean URLs and specific texts
                if(text.length > 0 && text.length < 50 && href && href.length > 5 && !href.includes('groups') && !href.includes('friends') && !href.includes('marketplace')) {
                    results.push({text: text, href: href, ariaLabel: ariaLabel});
                }
            }
            return results;
        }""")
        
        for p in pages:
            print(f"- {p['text']} (href: {p['href']}, aria: {p['ariaLabel']})")
            
        # Optional: Test switching to a specific page if there is one
        
finally:
    adapter.close_session()

