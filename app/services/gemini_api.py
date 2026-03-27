"""
GeminiAPIService — Fallback service using the official Google Generative AI Python SDK.
Requires GEMINI_API_KEY in app/config.py and .env
"""
import time
import logging
import os
import app.config as config
from PIL import Image

logger = logging.getLogger(__name__)

class GeminiAPIService:
    """
    Stateless API service wrapper for Google's Generative AI.
    Used selectively when the primary RPA mechanism fails.
    """
    def __init__(self):
        try:
            import google.generativeai as genai
            self.genai = genai
            if getattr(config, 'GEMINI_API_KEY', None):
                self.genai.configure(api_key=config.GEMINI_API_KEY)
                # Dùng 1.5 flash vì tốc độ cao và rẻ hơn, cực kỳ phù hợp làm fallback
                self.model = self.genai.GenerativeModel('gemini-1.5-flash-latest')
                self.is_configured = True
            else:
                self.is_configured = False
                logger.warning("GEMINI_API_KEY chư được cài đặt trong .env. Tính năng dự phòng API Fallback bị vô hiệu hoá.")
        except ImportError:
            self.is_configured = False
            logger.warning("Thư viện `google-generativeai` chưa được cài đặt. Tính năng API Fallback bị vô hiệu hoá.")
            
    def ask_with_file(self, prompt: str, file_path: str) -> str | None:
        """Uploads an image/video to Gemini API and generates content based on the prompt."""
        if not self.is_configured:
            logger.error("GeminiAPIService chưa sẵn sàng (thiếu API Key hoặc lỗi thư viện).")
            return None
            
        if not os.path.exists(file_path):
            logger.error("File input không tồn tại: %s", file_path)
            return None
            
        logger.info("🔥 [API Fallback] Đang gửi yêu cầu lên API chính thức trả phí: %s", os.path.basename(file_path))
        t0 = time.time()
        
        try:
            lower_path = file_path.lower()
            if lower_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                # Gửi trực tiếp ảnh không cần upload
                img = Image.open(file_path)
                response = self.model.generate_content([prompt, img])
            else:
                # Video file phải upload qua File API
                logger.info("[API Fallback] Đang upload file video lên Google Cloud...")
                video_file = self.genai.upload_file(path=file_path)
                
                # Đợi processing
                retry_count = 0
                while video_file.state.name == 'PROCESSING' and retry_count < 30: # Max 60s
                    logger.info("[API Fallback] Processing video trên Google server...")
                    time.sleep(2)
                    video_file = self.genai.get_file(video_file.name)
                    retry_count += 1
                
                if video_file.state.name == 'FAILED':
                    raise Exception("Video processing thất bại trên mảy chủ Google API")
                    
                logger.info("[API Fallback] Gọi model phân tích video...")
                response = self.model.generate_content([prompt, video_file])
                
                # Dọn dẹp dung lượng quota của Google Cloud ngay lập tức
                try:
                    self.genai.delete_file(video_file.name)
                except Exception as cleanup_err:
                    logger.warning("[API Fallback] Không dọn được file API (không quan trọng): %s", cleanup_err)
                
            if response and response.text:
                logger.info("🔥 [API Fallback] Trả kết quả thành công (%.1fs)", time.time() - t0)
                return response.text
                
            return None
            
        except Exception as e:
            logger.error("🔥 [API Fallback] Lỗi khi tạo content từ API: %s", e)
            return None
