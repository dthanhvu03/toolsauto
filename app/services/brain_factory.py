import logging
from app.services import settings as runtime_settings

logger = logging.getLogger(__name__)

class BrainFactory:
    """
    Factory class to provide specialized AI personas (Brain Personas)
    based on niche and target audience.
    """

    @staticmethod
    def get_persona_prompt(niche: str = "general") -> str:
        """
        Returns a specialized system instruction block based on the niche.
        """
        niche = (niche or "general").lower()
        
        if any(x in niche for x in ["beauty", "mỹ phẩm", "skincare", "làm đẹp"]):
            return runtime_settings.get_str("ai.prompt.beauty")

        if any(x in niche for x in ["fashion", "thời trang", "outfit", "quần áo"]):
            return runtime_settings.get_str("ai.prompt.fashion")

        if any(x in niche for x in ["tech", "công nghệ", "gadget", "điện thoại"]):
            return runtime_settings.get_str("ai.prompt.tech")

        if any(x in niche for x in ["kitchen", "gia dụng", "nhà cửa", "home"]):
            return runtime_settings.get_str("ai.prompt.home")

        if any(x in niche for x in ["funny", "hài hước", "meme", "giải trí"]):
            return runtime_settings.get_str("ai.prompt.funny")

        return runtime_settings.get_str("ai.prompt.general")

    @staticmethod
    def get_visual_hook_instruction() -> str:
        """
        Special instruction for multimodal analysis of the video hook.
        """
        return runtime_settings.get_str("ai.prompt.visual_hook")

    @staticmethod
    def get_engagement_secrets() -> str:
        """
        Specialized 'Algorithm Secrets' to boost engagement.
        """
        return runtime_settings.get_str("ai.prompt.engagement_secrets")

    @staticmethod
    def build_caption_prompt(prompt_content: str, niche: str = "general") -> str:
        """
        Builds the complete mega-prompt for caption generation.
        Enforces consistency between playground (AI Studio) and production workers.
        """
        visual_hook_logic = BrainFactory.get_visual_hook_instruction()
        algo_secrets = BrainFactory.get_engagement_secrets()
        
        return f"""# MEGA PROMPT: CHUYÊN GIA CONTENT TIKTOK/FACEBOOK

[AI BRAIN SPECIALIZATION]
{prompt_content}

[ROLE]
Bạn là chuyên gia phân tích video. Nhiệm vụ của bạn là xem xét nội dung (ảnh chụp) và thông tin cơ bản sau để viết 1 Caption Facebook/TikTok cực kỳ hấp dẫn.

[THÔNG TIN DỮ LIỆU ĐẦU VÀO MẪU]
- Kênh/Niche: {niche}
- Caption Gốc: \"Sản phẩm tốt nhất năm 2026! Đừng bỏ qua!\"

{visual_hook_logic}

{algo_secrets}

[OUTPUT FORMAT]
Trả về dạng JSON:
{{
  \"title\": \"...\",
  \"description\": \"...\",
  \"hashtags\": [\"#tag1\", \"#tag2\"]
}}
"""
