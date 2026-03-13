import os
import time
import json
import logging
import undetected_chromedriver as uc

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

COOKIE_PATH = "/home/vu/toolsauto/gemini_cookies.json"

def main():
    logger.info("Khởi động trình duyệt Chrome (Undetected)...")
    
    options = uc.ChromeOptions()
    # Không chạy headless để user có màn hình login
    options.add_argument("--window-size=1280,720")
    
    # Init driver version 131 or whatever matches their system.
    # The previous conversations mentioned using undetected_chromedriver's auto-management.
    try:
        driver = uc.Chrome(options=options)
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Chrome: {e}")
        return

    try:
        logger.info("Mở trang web Gemini...")
        driver.get("https://gemini.google.com/app")
        
        print("\n" + "="*60)
        print(" CHÚ Ý: TRÌNH DUYỆT ĐÃ ĐƯỢC MỞ!")
        print(" 1. Hãy đăng nhập vào tài khoản Google của bạn trên cửa sổ Chrome vừa hiện ra.")
        print(" 2. Chờ cho đến khi trang Gemini load xong hoàn toàn (thấy ô nhập chat).")
        print(" 3. Sau khi xong, QUAY LẠI CỬA SỔ TERMINAL NÀY BẤM ENTER.")
        print("="*60 + "\n")
        
        input("👉 Bấm Enter TẠI ĐÂY sau khi bạn đã đăng nhập xong trên Chrome... ")
        
        logger.info("Đang trích xuất cookies...")
        cookies = driver.get_cookies()
        
        if not cookies:
            logger.warning("Không lấy được cookie nào, có thể bạn chưa đăng nhập thành công.")
            return
            
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
            
        logger.info(f"✅ Đã lưu {len(cookies)} cookies vào file: {COOKIE_PATH}")
        print("Bạn có thể chạy lại hệ thống Auto Publisher với tính năng AI được rồi!")
        
    finally:
        logger.info("Đóng trình duyệt...")
        driver.quit()

if __name__ == "__main__":
    main()
