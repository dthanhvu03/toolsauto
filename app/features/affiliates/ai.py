import logging
import json
import re
from typing import Optional, Dict, Any

from app.services.gemini_rpa import GeminiRPAService
from app.services.gemini_api import GeminiAPIService

logger = logging.getLogger(__name__)

class AffiliateAIService:
    @staticmethod
    def generate_comment(keyword: str, url: str) -> Optional[str]:
        """
        Generates a persuasive affiliate comment template using Gemini.
        Priority: RPA (Free) -> API (Rotation Fallback).
        """
        # Note: We use a simplified prompt since we only have keyword and URL
        prompt = (
            f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm có từ khóa nhận diện là: '{keyword}'. "
            f"URL sản phẩm: {url}. "
            "Hãy tạo 1 mẫu bình luận cực kỳ hấp dẫn, tự nhiên để chèn vào bài viết. "
            "Bình luận PHẢI có chứa chính xác chuỗi '[LINK]' để hệ thống thay bằng URL sau này. "
            "Trả về kết quả dưới dạng JSON (không markdown): "
            '{"comment": "Nội dung bình luận ở đây [LINK]"}'
        )

        raw_response = None
        source = "rpa"

        # 1. Try RPA
        try:
            rpa = GeminiRPAService(max_retries=1)
            raw_response = rpa.ask(prompt)
        except Exception as e:
            logger.error(f"[AffiliateAI] RPA Error: {e}")

        # 2. Fallback to API (Rotation enabled)
        if not raw_response:
            source = "api"
            logger.info("[AffiliateAI] RPA failed, trying API fallback...")
            try:
                api = GeminiAPIService()
                raw_response = api.ask(prompt)
            except Exception as e:
                logger.error(f"[AffiliateAI] API Error: {e}")

        if not raw_response:
            return None

        # 3. Parse JSON
        try:
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(raw_response)
            
            comment = data.get("comment")
            if comment:
                # Remove all existing [LINK] and replace/append one at the end if missing
                # But actually, the prompt asks for it. Let's just normalize.
                clean_comment = comment.replace("[LINK]", "").strip()
                return f"{clean_comment} [LINK]"
            return None
        except Exception as e:
            logger.error(f"[AffiliateAI] Parse Error: {e} | Raw: {raw_response}")
            return None
