"""
GeminiRPAService — Giao tiếp với Gemini Web UI qua UC Chrome + Selenium.
Không cần API key. Dùng cookies từ login_gemini_bypass.py.

Yêu cầu: chạy qua xvfb-run (Google chặn headless)

Dùng:
    from app.services.gemini_rpa import GeminiRPAService
    svc = GeminiRPAService()
    response = svc.ask("Phân tích video này...")
"""
import json
import time
import os
import logging
import functools
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)

COOKIE_PATH = "/home/vu/toolsauto/gemini_cookies.json"
DEBUG_DIR = "/home/vu/toolsauto/debug_steps"

class GeminiMaxRetriesExceeded(Exception):
    """Exception ném ra khi Gemini RPA retry thất bại cả 3 lần."""
    pass

def with_retry(max_retries=3, delay_sec=30):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"==> Gemini RPA Attempt {attempt}/{max_retries}...")
                    result = func(*args, **kwargs)
                    if result:
                        return result
                    else:
                        raise Exception("Gemini returned empty response")
                except Exception as e:
                    last_err = e
                    logger.error(f"Attempt {attempt}/{max_retries} failed: {e}")
                    if attempt < max_retries:
                        logger.info(f"Waiting {delay_sec}s before next retry...")
                        time.sleep(delay_sec)
            logger.error("All 3 attempts failed. Tự động đánh dấu FAILED.")
            raise GeminiMaxRetriesExceeded(f"Failed after {max_retries} attempts. Last error: {last_err}")
        return wrapper
    return decorator

class GeminiRPAService:
    """Gửi prompt cho Gemini qua Web UI, nhận text response."""
    
    RESPONSE_SELECTORS = [
        '.model-response-text message-content',     # Custom Gem UI (MỚI)
        'message-content',                          # Custom Gem UI (Chung)
        'model-response .message-content',          # Cấu trúc mới ngoặc class
        'model-response message-content',           # Cấu trúc tag
        'div[data-test-id="model-response"]',       # Data test ID
        'div.model-response-text'                   # Fallback class
    ]

    def __init__(self, cookie_path=COOKIE_PATH, max_retries=3):
        self.cookie_path = cookie_path
        self.max_retries = max_retries

    def ask(self, prompt: str) -> str | None:
        """Gửi prompt text → nhận response. Trả None nếu thất bại."""
        return self._run_session(prompt, image_path=None)

    def ask_with_file(self, prompt: str, file_path: str) -> str | None:
        """Upload file (ảnh/video) + gửi prompt → Gemini phân tích rồi trả response."""
        if not os.path.exists(file_path):
            logger.error("File không tồn tại: %s", file_path)
            return None
        return self._run_session(prompt, image_path=file_path)

    @with_retry(max_retries=3, delay_sec=30)
    def _run_session(self, prompt: str, image_path: str | None = None) -> str | None:
        """Mở browser, bơm cookies, gửi prompt (có hoặc không có ảnh)."""
        import subprocess

        os.makedirs(DEBUG_DIR, exist_ok=True)

        if not os.path.exists(self.cookie_path):
            logger.error("Chưa có cookies. Chạy: python scripts/login_gemini_bypass.py")
            return None

        cookies = json.load(open(self.cookie_path))

        # Bỏ `--user-data-dir` để undetected_chromedriver tự tạo profile tạm trong /tmp (rất nhẹ, tự xoá khi quit)
        import undetected_chromedriver as uc
        opts = uc.ChromeOptions()
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        
        try:
            # Let undetected_chromedriver automatically manage the driver executable
            driver = uc.Chrome(
                options=opts,
                keep_alive=True,
                use_subprocess=True,
                version_main=145
            )
            logger.info("Chrome started successfully (PID: %s)", os.getpid())
        except Exception as e:
            logger.error("Failed to initialize Chrome: %s", e)
            return None

        try:
            return self._execute(driver, cookies, prompt, image_path)
        except Exception as e:
            logger.error("Gemini session crashed/failed: %s", e)
            raise e
        finally:
            if 'driver' in locals() and driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.debug("Lỗi khi quit driver: %s", e)

    def _execute(self, driver, cookies, prompt, image_path=None) -> str | None:
        # 1. Bơm cookies
        driver.get("https://gemini.google.com")
        time.sleep(2)
        for c in cookies:
            try:
                driver.add_cookie({
                    "name": c["name"], "value": c["value"],
                    "domain": c.get("domain", ".google.com"),
                    "path": c.get("path", "/"),
                    **({"expiry": int(c["expiry"])} if "expiry" in c else {}),
                })
            except Exception as e:
                logger.warning("Lỗi thêm cookie %s: %s", c.get("name"), e)

        # URL mặc định của Gemini (New Chat)
        driver.get("https://gemini.google.com/app")
        time.sleep(12)

        if "signin" in driver.current_url.lower() or driver.find_elements(By.CSS_SELECTOR, ".sign-in-button, a[href*='ServiceLogin']"):
            logger.error("Cookie hết hạn! Vui lòng đăng nhập lại.")
            raise Exception("Gemini cookies expired. Vui lòng đăng nhập lại (Chạy: python scripts/login_gemini_bypass.py)")

        # 2. Gửi prompt
        for attempt in range(1, self.max_retries + 1):
            logger.info("Thử lần %d/%d (URL: %s)", attempt, self.max_retries, driver.current_url)

            # Upload ảnh/video nếu có
            if image_path and attempt == 1:
                self._upload_file(driver, image_path)

            # Lấy response cuối cùng hiện tại (để tránh lấy nhầm text cũ)
            old_response_text = None
            for selector in getattr(self, "RESPONSE_SELECTORS", []):
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elems:
                        old_response_text = elems[-1].text.strip()
                        break
                except Exception:
                    pass

            # Lọc bỏ các ký tự ngoài BMP (như emoji phức tạp) vì ChromeDriver báo lỗi
            safe_prompt = "".join(c for c in prompt if ord(c) <= 0xFFFF)
            
            box = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, '[role="textbox"], div[contenteditable="true"]')))
            box.click()
            time.sleep(0.3)
            box.send_keys(safe_prompt)
            time.sleep(1)
            
            try:
                proof = "/home/vu/.gemini/antigravity/brain/2623c4e2-efc2-4973-873e-689d91eb1587/video_upload_proof.png"
                driver.save_screenshot(proof)
                logger.info("Saved upload proof: %s", proof)
            except:
                pass

            # === GỬI PROMPT ===
            # CRITICAL: Gemini dùng chung class 'send-button' cho cả nút Send VÀ nút Stop.
            # Nếu click button.send-button SAU KHI prompt gửi → sẽ HỦY response Gemini!
            # → Giải pháp: chỉ dùng Enter key để submit, KHÔNG click bất kỳ button nào.
            box.send_keys(Keys.RETURN)
            logger.info("Prompt submitted via Enter key")
                
            time.sleep(4)

            # 3. Đợi response (max 120s)
            result = self._wait_response(driver, prompt, old_response_text)
            if result:
                out_path = '/home/vu/.gemini/antigravity/brain/23eb6f02-4801-4635-8d17-491d2229b9ad/0301_final_gemini_ui.png'
                try: 
                    driver.save_screenshot(out_path)
                    logger.info("Screenshot saved to %s", out_path)
                except Exception as e: 
                    logger.error("Lỗi save_screenshot: %s", e)
                return result

            # Retry: reload rồi gửi lại
            logger.warning("Retry — reload trang...")
            try:
                debug_path = os.path.join(DEBUG_DIR, f"timeout_attempt_{attempt}.png")
                driver.save_screenshot(debug_path)
                logger.info("Saved timeout UI screenshot to %s", debug_path)
            except Exception:
                pass
            driver.get("https://gemini.google.com/app")
            time.sleep(5)

        logger.error("Thất bại sau %d lần thử", self.max_retries)
        return None


    def _upload_file(self, driver, file_path: str):
        """Upload file bằng cách giả lập Clipboard Paste thẳng vào thanh chat contenteditable.
           Hỗ trợ ảnh, video, PDF (những định dạng Gemini hỗ trợ)."""
        logger.info("Upload file (Clipboard Paste): %s", os.path.basename(file_path))
        try:
            import base64
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
                
            mime_type = "application/octet-stream"
            lower_path = file_path.lower()
            if lower_path.endswith((".jpg", ".jpeg")):
                mime_type = "image/jpeg"
            elif lower_path.endswith(".png"):
                mime_type = "image/png"
            elif lower_path.endswith(".webp"):
                mime_type = "image/webp"
            elif lower_path.endswith(".mp4"):
                mime_type = "video/mp4"
            elif lower_path.endswith(".mov"):
                mime_type = "video/quicktime"
            elif lower_path.endswith(".pdf"):
                mime_type = "application/pdf"

            paste_script = """
            var callback = arguments[arguments.length - 1]; // callback cho execute_async_script
            var b64Data = arguments[0];
            var mimeType = arguments[1];
            var filename = arguments[2];

            // Dùng fetch api tối ưu để chuyển base64 thành Blob cực nhanh, không làm đơ trình duyệt với file to (10MB+)
            var dataUrl = "data:" + mimeType + ";base64," + b64Data;
            
            fetch(dataUrl)
                .then(res => res.blob())
                .then(blob => {
                    var file = new File([blob], filename, {type: mimeType});
                    var dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);

                    // Tìm thanh chat
                    var chatBox = document.querySelector('div[contenteditable="true"]') || document.querySelector('[role="textbox"]');
                    if(chatBox){
                        chatBox.focus();
                        var pasteEvent = new ClipboardEvent('paste', {
                            clipboardData: dataTransfer,
                            bubbles: true,
                            cancelable: true
                        });
                        chatBox.dispatchEvent(pasteEvent);
                        callback(true);
                    } else {
                        callback(false);
                    }
                })
                .catch(err => {
                    console.error("Lỗi parse blob:", err);
                    callback(false);
                });
            """
            
            logger.info("Đang bơm file vào clipboard trình duyệt qua Data URL (Fetch)...")
            # Cần set timeout lâu hơn chút khi buffer file vài chục MB
            driver.set_script_timeout(30)
            success = driver.execute_async_script(paste_script, b64_data, mime_type, os.path.basename(file_path))

            if not success:
                logger.warning("Không tìm thấy chat box để paste file!")
                raise Exception("Không thể inject file qua JS ClipboardEvent")

            logger.info("Đợi Gemini nhận diện file dán vào (upload processing)...")
            # Với video đôi khi mất nhiều thời gian upload hơn
            time.sleep(15) 
            logger.info("Hoàn tất dán ảo. File đã hook vào Gemini.")

        except Exception as e:
            logger.error("Upload (Paste) lỗi: %s. Ngừng gửi prompt vì thiếu file!", e)
            raise e

    def _wait_response(self, driver, prompt, old_response_text=None) -> str | None:
        return GeminiResponseParser.extract_new_response(driver, prompt, old_response_text)


class GeminiResponseParser:
    """Xử lý việc bóc tách Response từ DOM của Gemini, có chống trùng text cũ."""
    
    RESPONSE_SELECTORS = [
        '.model-response-text message-content',
        'message-content',
        'model-response .message-content',
        'model-response message-content',
        'div[data-test-id="model-response"]',
        'div.model-response-text'
    ]
    
    NOISE_PATTERNS = [
        "gemini is ai", "can make mistakes", "google terms",
        "google privacy", "show thinking", "gemini said",
        "submit", "settings", "ask gemini", "tools", "pro",
        "double-check", "learn more", "report a legal issue",
        "share & export", "modify response", "more options",
        "mở trong cửa sổ mới", "có thể mắc sai sót", "điều khoản", "quyền riêng tư"
    ]

    @classmethod
    def extract_new_response(cls, driver, prompt: str, old_response_text: str | None, timeout_sec: int = 120) -> str | None:
        """Chờ Gemini rặn ra text, quét các HTML node cụ thể, tránh dùng body_text."""
        end_time = time.time() + timeout_sec
        last_length = 0
        stable_count = 0  # Đếm số chu kỳ polling mà text không đổi để xác định Gemini viết xong
        
        while time.time() < end_time:
            time.sleep(0.5)  # Polling nhanh thay vì 5s mỗi block
            
            # Check error từ server
            # Check error từ server - chỉ check các element lỗi THỰC SỰ HIỂN THỊ
            try:
                err_elems = driver.find_elements(By.CSS_SELECTOR, 'message-error, .error-text, div[role="alert"]')
                for el in err_elems:
                    if el.is_displayed() and "Something went wrong" in el.text:
                        logger.warning("Gemini server error (Something went wrong) visible detected.")
                        return None
            except Exception:
                pass

            response_text = None
            for selector in cls.RESPONSE_SELECTORS:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if not elements:
                        continue
                        
                    raw = elements[-1].text.strip()
                    if not raw or len(raw) < 10:
                        continue
                        
                    # Phớt lờ nếu chưa có gì mới so với lúc submit prompt
                    if old_response_text and raw == old_response_text:
                        continue
                        
                    # Bỏ qua nếu selector bắt gọn cả user prompt
                    if prompt[:30] in raw:
                        continue
                        
                    response_text = raw
                    break
                except Exception:
                    pass
            
            if not response_text:
                continue

            # Lọc Noise & Chặn rỗng
            lines = []
            for line in response_text.split("\n"):
                cleaned = line.strip()
                if not cleaned:
                    continue
                lower = cleaned.lower()
                if any(p in lower for p in cls.NOISE_PATTERNS):
                    continue
                if prompt[:30] in cleaned:
                    continue
                lines.append(cleaned)

            clean_response = "\n".join(lines).strip()
            if len(clean_response) < 10:
                continue

            # Kiểm định sự ổn định của Streaming Text
            if len(clean_response) == last_length:
                stable_count += 1
            else:
                last_length = len(clean_response)
                stable_count = 0
                
            # Tuỳ chỉnh: nếu nó ra text dài và không tăng ký tự nữa trong 3 chu kỳ rưỡi (~1.5 giây), coi như nó viết xong
            if stable_count >= 3:
                logger.info("Response OK (%d chars - Stable)", len(clean_response))
                return clean_response

        logger.warning("Timeout %ds waiting for Gemini Response", timeout_sec)
        return None
