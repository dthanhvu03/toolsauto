"""Affiliate comment generation — always via AICaptionPipeline (ADR-006)."""
import logging
import json
import re
from typing import Optional

from app.core.ai.runtime import pipeline

logger = logging.getLogger(__name__)


class AffiliateAIService:
    @staticmethod
    def generate_comment(keyword: str, url: str) -> Optional[str]:
        """
        Persuasive affiliate comment template.
        Uses pipeline (9Router → native Gemini fallback), not direct RPA/API.
        """
        prompt = (
            f"Hãy đóng vai chuyên gia Affiliate Marketing. Sản phẩm có từ khóa nhận diện là: '{keyword}'. "
            f"URL sản phẩm: {url}. "
            "Hãy tạo 1 mẫu bình luận cực kỳ hấp dẫn, tự nhiên để chèn vào bài viết. "
            "Bình luận PHẢI có chứa chính xác chuỗi '[LINK]' để hệ thống thay bằng URL sau này. "
            "Trả về kết quả dưới dạng JSON (không markdown): "
            '{"comment": "Nội dung bình luận ở đây [LINK]"}'
        )

        try:
            raw_response, meta = pipeline.generate_text(prompt)
            logger.info("[AffiliateAI] pipeline meta=%s", meta)
        except Exception as e:
            logger.error("[AffiliateAI] pipeline error: %s", e)
            return None

        if not raw_response:
            return None

        try:
            match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(raw_response)

            comment = data.get("comment")
            if comment:
                clean_comment = comment.replace("[LINK]", "").strip()
                return f"{clean_comment} [LINK]"
            return None
        except Exception as e:
            logger.error("[AffiliateAI] Parse Error: %s | Raw: %s", e, raw_response)
            return None
