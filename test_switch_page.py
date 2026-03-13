from app.adapters.facebook.adapter import FacebookAdapter
import time

adapter = FacebookAdapter()
try:
    if adapter.open_session("profiles/fb_acc_01_profile"):
        print("Trình duyệt khởi động thành công.")
        page = adapter.page
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Click the profile picture at top right to open account switcher
        profile_btn = page.locator('div[aria-label="Your profile"], div[aria-label="Trang cá nhân của bạn"], div[aria-label="Tài khoản"], div[aria-label="Account"]').first
        if profile_btn.count() > 0:
            print("Đã tìm thấy nút menu Profile, đang click...")
            profile_btn.click()
            page.wait_for_timeout(2000)
            
            # Click the "See all profiles" button
            see_all_btn = page.locator('div[role="button"]:has-text("See all profiles"), div[role="button"]:has-text("Xem tất cả trang cá nhân")').first
            if see_all_btn.count() > 0:
                print("Đã tìm thấy nút 'Xem tất cả trang cá nhân', đang click...")
                see_all_btn.click()
                page.wait_for_timeout(2000)
                
                # Retrieve all profiles in the list
                profiles = page.evaluate("""() => {
                    const results = [];
                    const elements = document.querySelectorAll('div[role="dialog"] div[role="radio"]');
                    for(const el of elements) {
                        const nameEl = el.querySelector('span[dir="auto"]');
                        if (nameEl && nameEl.innerText) {
                            results.push(nameEl.innerText);
                        }
                    }
                    return results;
                }""")
                
                print("Danh sách các Profiles/Pages tìm thấy trong menu chuyển đổi:")
                for i, p in enumerate(profiles):
                    print(f"[{i}] {p}")
                    
                # To switch to a specific page (e.g. index 1)
                if len(profiles) > 1:
                    print(f"Thử chuyển sang Page: {profiles[1]}")
                    page_radio = page.locator(f'div[role="dialog"] div[role="radio"]:has-text("{profiles[1]}")').first
                    if page_radio.count() > 0:
                        page_radio.click()
                        page.wait_for_timeout(5000)
                        print(f"Đã chuyển sang {profiles[1]}, URL hiện tại: {page.url}")
            else:
                print("Không tìm thấy nút 'Xem tất cả trang cá nhân'. Có thể bạn chỉ có 1 profile chính.")

        time.sleep(10)
finally:
    adapter.close_session()

