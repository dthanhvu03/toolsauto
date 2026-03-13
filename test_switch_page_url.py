from app.adapters.facebook.adapter import FacebookAdapter
import time

adapter = FacebookAdapter()
try:
    if adapter.open_session("profiles/fb_acc_01_profile"):
        print("Trình duyệt khởi động thành công.")
        page = adapter.page
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # In Facebook, you can switch page directly by visiting the URL: 
        # https://www.facebook.com/profile.php?id=[PAGE_ID]&sk=about&section=page_transparency 
        # but the safest way the user might have pages is passing the exact page NAME.
        
        print("Đang thử lấy context pages qua GraphQL hoặc data-pagelet...")

        # Get list of accounts from the DOM
        page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        
        # Click on "Trang của bạn" if needed
        # Just grab any h1 or h2 to see where we are
        print(page.title())
        
        time.sleep(5)
finally:
    adapter.close_session()
