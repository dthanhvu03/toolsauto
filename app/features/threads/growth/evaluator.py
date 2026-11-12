"""Bộ đánh giá ngữ cảnh & Sinh phản hồi A/B bằng AI cho Threads Growth Agent.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.threads.growth.config import (
    CASHBOT_ZALO_NAME,
    CASHBOT_ZALO_URL,
    ZALO_SHARE,
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


# Bài chào hàng rõ ràng (người bán / chạy affiliate) — reply vào đó không ra khách. Lọc rẻ trước khi gọi AI (PLAN-163).
SELLER_SIGNALS = (
    "inbox", "ib mình", "ib em", "ib shop", "ib ngay", "link ở bio", "link trong bio", "link bio", "chốt đơn",
    "nhận order", "nhận đơn", "giá sỉ", "giá chỉ", "nhanh tay", "mua ngay", "săn ngay", "freeship",
    "zalo:", "liên hệ zalo", "sẵn hàng", "còn hàng", "lên đơn",
)


@dataclass(frozen=True)
class PostReading:
    """Bản đọc tâm lý / nhu cầu của một bài (AI)."""

    is_seller: bool
    intent: str
    emotion: str
    need: str
    stage: str
    objection: str
    their_words: str
    angle: str
    buy_score: int

    def summary(self) -> str:
        return (
            f"Đọc: {self.intent} · {self.emotion} · cần: {self.need} · {self.stage}"
            + (f" · băn khoăn: {self.objection}" if self.objection else "")
            + f" · điểm {self.buy_score}"
        )


def parse_reading(raw: str) -> Optional[PostReading]:
    """JSON AI trả → PostReading; sai định dạng → None."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        score = int(float(data.get("buy_score", 0)))
    except (ValueError, TypeError):
        return None

    def txt(key: str) -> str:
        return " ".join(str(data.get(key) or "").split())[:160]

    return PostReading(
        is_seller=bool(data.get("is_seller")),
        intent=txt("intent"),
        emotion=txt("emotion"),
        need=txt("need"),
        stage=txt("stage"),
        objection=txt("objection"),
        their_words=txt("their_words"),
        angle=txt("angle"),
        buy_score=min(max(score, 0), 100),
    )


# Mọi "link" t.me AI viết ra (kể cả dính chữ: "thếtps://t.me/…") → thay bằng đúng link tracking của biến thể.
_TME_TOKEN = re.compile(r"\S*(?:https?://)?t\.me/\S+|\S*tps?://\S+")


def clean_reply(reply: str, tracking_url: str) -> str:
    text = " ".join((reply or "").split()).strip().strip('"').strip("'").strip()
    if _TME_TOKEN.search(text):
        text = _TME_TOKEN.sub("", text, count=0)
        text = " ".join(text.split()).rstrip(" ,") + " " + tracking_url
    return text


def with_link(reply: str, tracking_url: str, handle: str) -> str:
    """Reply luôn có link bot đúng mã nguồn (chủ bot 12/11).

    Từ PLAN-163 (08/11) AI chỉ nhắc «@zt_shopee_bot» mà bỏ link: trên Threads «@…» là gắn thẻ một tài khoản Threads,
    khách bấm không vào được bot, và khách tự gõ tên bot thì không mang mã ?start= (đếm thành «tự vào»).
    Có «@handle» → thay lần nhắc đầu bằng link; không có → gắn link cuối câu."""
    raw = " ".join((reply or "").split()).strip().strip('"').strip("'").strip()
    found = list(_TME_TOKEN.finditer(raw))
    if found and found[0].group(0).lower().startswith(("http", "t.me", "zalo.me")):
        # AI đặt link ngay trong câu («dán link qua <link> để…»): giữ đúng chỗ, thay bằng link đúng mã; link khác bỏ.
        # (clean_reply gỡ link rồi gắn cuối câu → câu cụt «qua để», reply #1743 12/11.)
        head, tail = raw[:found[0].start()], raw[found[0].end():]
        tail = _TME_TOKEN.sub("", tail)
        punct = re.match(r"[,.!?;:)]*", found[0].group(0)[::-1]).group(0)[::-1] if found[0].group(0)[-1] in ",.!?;:)" else ""
        return " ".join(f"{head}{tracking_url}{punct}{tail}".split()).rstrip(" ,")
    text = clean_reply(reply, tracking_url)
    if not text or tracking_url in text:
        return text
    mention = re.compile(re.escape(handle) + r"(?![\w.])", re.IGNORECASE)
    if mention.search(text):
        return mention.sub(lambda _m: tracking_url, text, count=1)
    return f"{text.rstrip(' ,.')} {tracking_url}"


def link_for(reply: str, bot: str, variant: str) -> str:
    """with_link theo bot + biến thể của một dòng growth_posts (reply đang chờ đăng)."""
    try:
        profile = load_profiles()[TargetBot(bot)]
        cfg = profile.variants[ABVariant(variant)]
    except (KeyError, ValueError):
        return reply
    return with_link(reply, cfg.tracking_url, profile.handle)


EXAMPLE_DAYS = 7
EXAMPLE_MIN_VND = 3_000


def real_example(db_path: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """Một món khách thật vừa tạo link 7 ngày qua (chỉ đọc DB Cashbot) → «Áo len 179k, bot báo hoàn khoảng 15k».

    Chủ bot 12/11: reply Cashbot đều một công thức chung chung → cho AI số thật cụ thể. Không có / lỗi DB → "".
    """
    from cashback_bot.all_users import cashback_db
    from cashback_bot.messages import buyer_name

    since = ((now or datetime.now(timezone.utc)) - timedelta(days=EXAMPLE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with closing(sqlite3.connect(f"file:{db_path or cashback_db()}?mode=ro", uri=True, timeout=3)) as conn:
            row = conn.execute(
                "SELECT product_name, price_vnd, estimated_cashback FROM link_requests WHERE link_status = 'created' "
                "AND estimated_cashback >= ? AND price_vnd > 0 AND created_at >= ? ORDER BY random() LIMIT 1",
                (EXAMPLE_MIN_VND, since),
            ).fetchone()
    except sqlite3.Error:
        return ""
    if not row:
        return ""
    name = " ".join(buyer_name(unicodedata.normalize("NFKC", row[0] or "")).split()[:5])

    def k(n: int) -> str:
        return f"{round(n / 1000)}k" if n >= 1000 else f"{n}đ"

    return f"{name} giá {k(int(row[1]))}, bot báo hoàn khoảng {k(int(row[2]))}"


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
    def looks_like_seller(content: str) -> bool:
        text = (content or "").lower()
        return any(s in text for s in SELLER_SIGNALS)

    @staticmethod
    async def read_post(content: str, bot_type: TargetBot) -> Tuple[Optional[PostReading], str]:
        """AI đọc tâm lý, cảm xúc, nhu cầu, câu chữ của người viết → (bản đọc | None, lý do khi None)."""
        profile: BotGrowthProfile = load_profiles()[bot_type]
        prompt = f"""PHÂN TÍCH BÀI THREADS. Đọc thật kỹ từng câu chữ, cảm xúc và hành vi của người viết bài dưới đây.

Bài đăng:
\"\"\"{content}\"\"\"

Sản phẩm mình có: {profile.name} (bot Telegram {profile.handle}).

Trả về DUY NHẤT một JSON (tiếng Việt, ngắn gọn), không giải thích:
{{"is_seller": true/false,      // người viết đang BÁN / chào hàng / chạy affiliate / quảng cáo
 "intent": "...",               // một trong: hỏi xin tư vấn | than phiền / gặp khó | chia sẻ kinh nghiệm | khoe đơn | chào hàng | khác
 "emotion": "...",              // cảm xúc thật: lo, tiếc tiền, bực, hào hứng, tò mò, mệt…
 "need": "...",                 // họ thật sự cần gì (một câu)
 "stage": "...",                // một trong: chưa có nhu cầu | đang tìm hiểu | sắp mua | vừa mua xong
 "objection": "...",            // điều họ băn khoăn / sợ (rỗng nếu không có)
 "their_words": "...",          // 2–5 chữ đắt nhất của chính họ, chép nguyên văn
 "angle": "...",                // nên nói gì để giúp đúng nhu cầu đó (một câu)
 "buy_score": 0-100}}           // khả năng người này bấm thử {profile.handle} vì nó giải quyết đúng nhu cầu của họ

Chấm buy_score khắt khe: người bán / quảng cáo ≤ 10; khoe đơn hoặc chia sẻ chung chung 20–40; đang hỏi hoặc đang gặp đúng
vấn đề mà {profile.name} giải quyết 70–100. Không đoán bừa: bài không liên quan → dưới 20.
"""
        try:
            raw, meta = await AIUseCases.generate_text_async(prompt, purpose=AIPurpose.THREADS_REPLY)
        except Exception as e:
            return None, f"lỗi AI ({type(e).__name__})"
        reading = parse_reading(raw or "")
        if reading is None:
            meta = meta or {}
            return None, meta.get("fail_reason") or meta.get("primary_fail_reason") or "AI không trả JSON"
        return reading, ""

    @staticmethod
    def get_fallback_reply(bot_type: TargetBot, variant: ABVariant) -> str:
        """Sinh câu trả lời mẫu chất lượng cao khi không có kết nối AI."""
        profile = load_profiles()[bot_type]
        cfg: VariantConfig = profile.variants[variant]
        return with_link(cfg.sample_hook, cfg.tracking_url, profile.handle)

    @classmethod
    async def generate_reply(
        cls,
        content: str,
        bot_type: TargetBot,
        variant: ABVariant,
        reading: Optional[PostReading] = None,
        channel: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Sinh câu trả lời thông minh dựa trên biến thể A hoặc B.

        Trả về: (câu_trả_lời, phân_tích_ai)
        """
        profile: BotGrowthProfile = load_profiles()[bot_type]
        cfg: VariantConfig = profile.variants[variant]
        # Cashbot: nửa reply dẫn về bot Zalo (12/11). channel: "zalo" | "telegram"; None = bốc ngẫu nhiên theo ZALO_SHARE.
        if channel is None:
            channel = "zalo" if bot_type == TargetBot.CASHBOT and random.random() < ZALO_SHARE else "telegram"
        zalo = channel == "zalo" and bot_type == TargetBot.CASHBOT
        link = CASHBOT_ZALO_URL if zalo else cfg.tracking_url
        where = CASHBOT_ZALO_NAME if zalo else f"bot Telegram {profile.handle}"
        example = real_example() if bot_type == TargetBot.CASHBOT else ""
        example_line = (f"Ví dụ thật gần đây (dùng nếu hợp bài, nói «bot báo hoàn khoảng», không nói chắc chắn): {example}\n"
                        if example else "")
        insight = ""
        if reading is not None:
            insight = f"""
Người viết đang (đã đọc kỹ bài):
- Ý định: {reading.intent} · giai đoạn: {reading.stage}
- Cảm xúc: {reading.emotion}
- Thật sự cần: {reading.need}
- Băn khoăn: {reading.objection or "không rõ"}
- Chữ của chính họ: {reading.their_words or "không có"}
- Nên nói: {reading.angle}
Cách viết: mở đầu bắt đúng cảm xúc đó (đồng cảm, không phán xét), dùng lại 1 chữ của chính họ cho tự nhiên, giải quyết đúng
cái họ cần / gỡ đúng băn khoăn trước, rồi mới nhắc bot (bằng link) như cách chính mình đã làm và thấy được việc.
"""

        prompt = f"""Bạn là một người dùng Threads Việt Nam bình thường đang lướt feed, thấy bài dưới đây thì để lại một reply.

Bài đăng:
\"\"\"{content}\"\"\"

Thứ bạn muốn giới thiệu khéo: {profile.name} — {where}
Góc nói (biến thể {variant.value}): {cfg.name}
Ý chính: {cfg.angle}
Link bot (bắt buộc, viết đúng nguyên văn một lần, thay cho tên bot — trên Threads «@tên» không bấm vào bot được): {link}
{example_line}{insight}
Văn phong — viết y như người thật trên Threads:
- 1–2 câu, tối đa khoảng 200 ký tự. Viết liền một mạch, không gạch đầu dòng, không xuống dòng.
- Giọng nói chuyện, xưng t / mình, gọi b / bà / ông tuỳ bài. Viết thường cũng được, không cần chấm câu cuối.
- Teencode vừa phải như người Việt hay gõ: ko, đc, j, nha, á, nè, ủa, trời ơi, đù, xỉu, thật sự. Tối đa 1 emoji (vd 🥲 😭 🤣), có thể không dùng.
- Trả lời đúng nội dung bài trước (đồng cảm / góp ý / trả lời câu hỏi), rồi mới nhắc {"bot bên Zalo" if zalo else "bot bên tele"} (bằng link) như kinh nghiệm cá nhân.
- KHÔNG viết như quảng cáo: không «hời phết», «tha hồ», «đỉnh chóp», «đừng bỏ lỡ», không liệt kê ưu đãi, không dấu chấm than liên tục.
- KHÔNG dùng chữ «VietQR» — nói tiền hoàn «về tài khoản» / «về thẳng tài khoản ngân hàng»; mua acc thì nói «chuyển khoản».
- KHÔNG hứa bảo hành, giá, % giảm, thời gian giao hay món hàng nào ngoài đúng «Ý chính» ở trên. Không bịa dịp / sự kiện (Tết, sale…) nếu bài không nhắc.
- Đổi cách nói mỗi lần, đừng lặp khuôn «dán link → hoàn tiền về thẳng tài khoản ngân hàng»; nói cụ thể (số thật, món thật)
  thay vì chung chung.
- KHÔNG ký tự lạ, KHÔNG lộ là AI / bot viết.
Chỉ xuất đúng câu reply, không giải thích, không ngoặc kép.
"""
        try:
            reply, meta = await AIUseCases.generate_text_async(
                prompt, purpose=AIPurpose.THREADS_REPLY
            )
            meta = meta or {}
            if reply and len(reply.strip()) > 10:
                cleaned = with_link(reply, link, profile.handle)
                analysis = (f"AI [{variant.value}{' · Zalo' if zalo else ''}] - "
                            f"{meta.get('provider', '?')}:{meta.get('model', '?')}")
                return cleaned, analysis
            # Ghi lý do để biết vì sao AI im (router tắt, circuit mở, hết quota…).
            reason = meta.get("fail_reason") or meta.get("primary_fail_reason") or "empty output"
            analysis = f"Fallback rule-based: AI không trả lời ({reason})"
        except Exception as e:
            analysis = f"Fallback rule-based: lỗi AI ({type(e).__name__}: {e})"

        return cls.get_fallback_reply(bot_type, variant), analysis
