import logging
from app.core import settings as runtime_settings

logger = logging.getLogger(__name__)

class BrainFactory:
    """
    Factory class to provide specialized AI personas (Brain Personas)
    based on niche and target audience.
    """

    @staticmethod
    def clean_json_blocks(raw: str) -> str:
        """Remove a surrounding Markdown code fence without altering plain JSON."""
        text = str(raw or "").strip()
        if not text.startswith(chr(96) * 3):
            return text

        lines = text.splitlines()
        if lines and lines[0].strip().startswith(chr(96) * 3):
            lines = lines[1:]
        if lines and lines[-1].strip() == chr(96) * 3:
            lines = lines[:-1]
        return "\n".join(lines).strip()

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
        """Build an AI Studio sandbox prompt with separate synthetic test data."""
        visual_hook_logic = BrainFactory.get_visual_hook_instruction()
        algo_secrets = BrainFactory.get_engagement_secrets()
        selected_persona = (prompt_content or "").strip() or "No custom persona selected."
        selected_niche = (niche or "general").strip()

        return f"""# AI STUDIO SANDBOX

[SELECTED PERSONA]
{selected_persona}

[SELECTED NICHE]
{selected_niche}

[SYNTHETIC TEST DATA — NOT PRODUCTION SOURCE]
For this sandbox only, imagine a short everyday scene related to the selected niche.
No real image, transcript, product name, brand, price, promotion, personal experience,
or verified claim was provided. Treat this as hypothetical test data and do not invent
specific product facts or pretend the scene came from a real video.

[TEST PURPOSE]
This request checks the selected persona and JSON output shape. It is not a simulation
of the production video/transcript pipeline.

[VISUAL GUIDANCE]
{visual_hook_logic}

[ENGAGEMENT GUIDANCE]
{algo_secrets}

[OUTPUT FORMAT]
Return only valid JSON with these keys:
{{
  "title": "test caption title",
  "description": "short description grounded in the synthetic test data",
  "hashtags": ["#tag1", "#tag2"]
}}
"""
