import os
import time
import json
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

COOKIE_PATH = "/home/vu/toolsauto/gemini_cookies.json"

def verify_cookies(driver):
    """Kiểm tra xem cookies đã thực sự giúp login vào Gemini chưa."""
    if "gemini.google.com" not in driver.current_url:
        return False
        
    logger.info("Đang kiểm tra session trên trang Gemini...")
    signin_elements = driver.find_elements(By.CSS_SELECTOR, ".sign-in-button, a[href*='ServiceLogin']")
    saw_signin = False
    for el in signin_elements:
        try:
            if el.is_displayed():
                saw_signin = True
                break
        except Exception:
            continue

    # Nếu có ô chat (textarea hoặc contenteditable) thì gần như chắc đã đăng nhập/đã vào UI.
    chat_input_candidates = driver.find_elements(
        By.CSS_SELECTOR,
        "textarea, [contenteditable='true']"
    )
    has_chat_input = False
    for el in chat_input_candidates:
        try:
            if el.is_displayed():
                has_chat_input = True
                break
        except Exception:
            continue

    # Heuristic:
    # - Nếu thấy Sign in => CHƯA login!
    is_logged_in = (not saw_signin) and has_chat_input
            
    if is_logged_in:
        logger.info("✅ Xác thực thành công! Gemini đã nhận diện session.")
        return True
    else:
        logger.warning("❌ Xác thực thất bại! Vẫn thấy nút 'Sign in'.")
        return False

def main():
    logger.info("Khởi động trình duyệt Chrome (Undetected)...")
    
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1600,900")
    
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
        print(" 1. Hãy đăng nhập vào tài khoản Google của bạn.")
        print(" 2. Chờ cho đến khi thấy giao diện chat của Gemini (có chữ 'Hi ...').")
        print(" 3. QUAN TRỌNG: Hãy thử gõ 1 câu hỏi bất kỳ và gửi đi để đảm bảo session hoạt động.")
        print(" 4. Sau khi xong, QUAY LẠI CỬA SỔ TERMINAL NÀY BẤM ENTER.")
        print("="*60 + "\n")
        
        # Auto-wait for the user to log in and load the chat UI.
        # This removes the need to press Enter manually.
        logger.info("Chờ login Gemini... (tự động lưu cookies khi đã đăng nhập)")
        timeout_sec = int(os.environ.get("GEMINI_LOGIN_TIMEOUT_SEC", "300"))
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            try:
                if verify_cookies(driver):
                    break
            except Exception as e:
                logger.warning("Verify cookies failed (will retry): %s", e)
            time.sleep(5)
        else:
            logger.warning("Timeout waiting for Gemini login after %ss", timeout_sec)
        
        logger.info("Đang trích xuất cookies...")
        cookies = driver.get_cookies()
        
        logger.info("Đang lấy thêm cookies từ myaccount.google.com để tránh sót auth cookies...")
        driver.get("https://myaccount.google.com/")
        time.sleep(3)
        google_cookies = driver.get_cookies()
        
        # Gộp cookies từ gemini và google account
        cookie_dict = {c['name']: c for c in cookies}
        for gc in google_cookies:
            cookie_dict[gc['name']] = gc
        all_cookies = list(cookie_dict.values())
        
        if not all_cookies:
            logger.warning("Không lấy được cookie nào.")
            return
        
        # Quay lại gemini để verify
        driver.get("https://gemini.google.com/app")
        time.sleep(3)

        # Thử verify ngay lập tức bằng chính driver đang mở
        if verify_cookies(driver):
            with open(COOKIE_PATH, "w", encoding="utf-8") as f:
                json.dump(all_cookies, f, indent=2)
            logger.info("✅ Đã lưu %s cookies vào file: %s", len(all_cookies), COOKIE_PATH)
            print("\nHOÀN TẤT! Bạn có thể đóng trình duyệt và chạy lại Tool.")
        else:
            print("\n❌ CẢNH BÁO: Cookies lấy được có vẻ không hoạt động.")
            print("Hãy đảm bảo bạn đã đăng nhập thành công và nhìn thấy khung chat trước khi bấm Enter.")
            retry = input("Bạn có muốn lưu đại không? (y/n): ")
            if retry.lower() == 'y':
                with open(COOKIE_PATH, "w", encoding="utf-8") as f:
                    json.dump(all_cookies, f, indent=2)
                logger.info("Đã lưu cookies theo yêu cầu (có thể không chạy được).")

    finally:
        logger.info("Đóng trình duyệt...")
        driver.quit()

if __name__ == "__main__":
    main()
