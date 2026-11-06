"""Bộ đánh giá ngữ cảnh & Sinh phản hồi A/B bằng AI cho Threads Growth Agent.
"""

from __future__ import annotations

import re

from typing import Optional, Tuple

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.threads.growth.config import (
    load_profiles,
    ABVariant,
    BotGrowthProfile,
    TargetBot,
    VariantConfig,
)


# Tín hiệu phân loại. Tránh từ quá chung (vd "tài khoản" khớp cả "tài khoản ngân hàng").
SHOPEE_SIGNALS = (
    "shopee", "săn sale", "mã giảm giá", "áp mã", "voucher", "hoàn tiền",
    "tiktok shop", "lazada", "đặt đơn", "phí ship", "giỏ hàng", "sale 11/11",
    "sale 12/12", "sale lương về",
)
AI_SIGNALS = (
    "chatgpt", "chat gpt", "claude", "canva", "capcut", "midjourney", "elsa speak",
    "bản quyền", "mua acc", "tool ai", "gpt 4", "gpt-4", "tài khoản ai", "acc ai",
    "mua pro", "gói pro", "tài khoản pro", "acc pro", "pass store", "nâng cấp tài khoản",
)


# Mọi "link" t.me AI viết ra (kể cả dính chữ: "thếtps://t.me/…") → thay bằng đúng link tracking của biến thể.
_TME_TOKEN = re.compile(r"\S*(?:https?://)?t\.me/\S+|\S*tps?://\S+")


def clean_reply(reply: str, tracking_url: str) -> str:
    text = " ".join((reply or "").split()).strip().strip('"').strip("'").strip()
    if _TME_TOKEN.search(text):
        text = _TME_TOKEN.sub("", text, count=0)
        text = " ".join(text.split()).rstrip(" ,") + " " + tracking_url
    return text


def _hits(text: str, signals) -> int:
    return sum(1 for s in signals if s in text)


class GrowthEvaluator:
    @staticmethod
    def classify_target_bot(content: str) -> Optional[TargetBot]:
        """Phân loại nội dung bài viết thuộc tệp Cashbot hay AI Pass Store.

        Không có tín hiệu hoặc hai bên ngang nhau (mơ hồ) → None.
        """
        text = (content or "").lower()
        shopee_score = _hits(text, SHOPEE_SIGNALS)
        ai_score = _hits(text, AI_SIGNALS)
        if shopee_score == ai_score:
            return None
        return TargetBot.CASHBOT if shopee_score > ai_score else TargetBot.AI_STORE

    @staticmethod
    def calculate_relevance(content: str, bot_type: TargetBot) -> int:
        """Điểm phù hợp 0–99: 30 + 15/tín hiệu + 20/từ khóa của bot, trừ 20 nếu bài quá ngắn."""
        text = (content or "").lower()
        profile = load_profiles()[bot_type]
        signals = SHOPEE_SIGNALS if bot_type == TargetBot.CASHBOT else AI_SIGNALS
        score = 30 + 15 * _hits(text, signals) + 20 * _hits(text, profile.keywords)
        if len(text) < 15:
            score -= 20
        return min(max(score, 0), 99)

    @staticmethod
    def get_fallback_reply(bot_type: TargetBot, variant: ABVariant) -> str:
        """Sinh câu trả lời mẫu chất lượng cao khi không có kết nối AI."""
        profile = load_profiles()[bot_type]
        cfg: VariantConfig = profile.variants[variant]
        return cfg.sample_hook

    @classmethod
    async def generate_reply(
        cls,
        content: str,
        bot_type: TargetBot,
        variant: ABVariant,
    ) -> Tuple[str, str]:
        """Sinh câu trả lời thông minh dựa trên biến thể A hoặc B.

        Trả về: (câu_trả_lời, phân_tích_ai)
        """
        profile: BotGrowthProfile = load_profiles()[bot_type]
        cfg: VariantConfig = profile.variants[variant]

        prompt = f"""Bạn là một người dùng Threads Việt Nam bình thường đang lướt feed, thấy bài dưới đây thì để lại một reply.

Bài đăng:
\"\"\"{content}\"\"\"

Thứ bạn muốn giới thiệu khéo: {profile.name} — bot Telegram {profile.handle}
Góc nói (biến thể {variant.value}): {cfg.name}
Ý chính: {cfg.angle}
Link (chỉ chèn nếu thấy tự nhiên): {cfg.tracking_url}

Văn phong — viết y như người thật trên Threads:
- 1–2 câu, tối đa khoảng 200 ký tự. Viết liền một mạch, không gạch đầu dòng, không xuống dòng.
- Giọng nói chuyện, xưng t / mình, gọi b / bà / ông tuỳ bài. Viết thường cũng được, không cần chấm câu cuối.
- Teencode vừa phải như người Việt hay gõ: ko, đc, j, nha, á, nè, ủa, trời ơi, đù, xỉu, thật sự. Tối đa 1 emoji (vd 🥲 😭 🤣), có thể không dùng.
- Trả lời đúng nội dung bài trước (đồng cảm / góp ý / trả lời câu hỏi), rồi mới nhắc {profile.handle} như kinh nghiệm cá nhân.
- KHÔNG viết như quảng cáo: không «hời phết», «tha hồ», «đỉnh chóp», «đừng bỏ lỡ», không liệt kê ưu đãi, không dấu chấm than liên tục.
- KHÔNG dùng chữ «VietQR» — nói tiền hoàn «về tài khoản» / «về thẳng tài khoản ngân hàng»; mua acc thì nói «chuyển khoản».
- KHÔNG hứa bảo hành, giá, % giảm, thời gian giao hay món hàng nào ngoài đúng «Ý chính» ở trên. Không bịa dịp / sự kiện (Tết, sale…) nếu bài không nhắc.
- KHÔNG ký tự lạ, KHÔNG lộ là AI / bot viết.
Chỉ xuất đúng câu reply, không giải thích, không ngoặc kép.
"""
        try:
            reply, meta = await AIUseCases.generate_text_async(
                prompt, purpose=AIPurpose.THREADS_REPLY
            )
            meta = meta or {}
            if reply and len(reply.strip()) > 10:
                cleaned = clean_reply(reply, cfg.tracking_url)
                analysis = f"AI [{variant.value}] - {meta.get('provider', '?')}:{meta.get('model', '?')}"
                return cleaned, analysis
            # Ghi lý do để biết vì sao AI im (router tắt, circuit mở, hết quota…).
            reason = meta.get("fail_reason") or meta.get("primary_fail_reason") or "empty output"
            analysis = f"Fallback rule-based: AI không trả lời ({reason})"
        except Exception as e:
            analysis = f"Fallback rule-based: lỗi AI ({type(e).__name__}: {e})"

        return cls.get_fallback_reply(bot_type, variant), analysis
