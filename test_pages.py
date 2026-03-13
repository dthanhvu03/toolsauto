from app.adapters.facebook.adapter import FacebookAdapter
import time

adapter = FacebookAdapter()
try:
    if adapter.open_session("profiles/fb_acc_01_profile"):
        print("Trình duyệt khởi động thành công.")
        page = adapter.page
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Method 3: Direct navigation to the page URL to post
        # "May Mặc Entertainment"
        page.goto("https://www.facebook.com/profile.php?id=61563821868341", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        
        # Check if we can post directly on the page without switching profile!
        # Sometimes Facebook allows posting directly from the page's home URL if you are an admin.
        # But usually, it forces you to "Switch Now" to interact as the page.
        switch_btn = page.locator('div[role="button"]:has-text("Switch now"), div[role="button"]:has-text("Chuyển ngay")').first
        if switch_btn.count() > 0:
            print("Tìm thấy nút 'Chuyển ngay' (Switch now), đang click...")
            switch_btn.click()
            page.wait_for_timeout(5000)
            print("Đã chuyển profile thành công. Sẵn sàng đăng bài.")
        else:
            print("Không thấy nút Switch, thử tìm nút Đăng bài (Compose)...")
            
        time.sleep(5)
finally:
    adapter.close_session()

