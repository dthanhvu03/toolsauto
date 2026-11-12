"""Lệnh admin ``/tamly`` (PLAN-170): hỏi cố vấn tâm lý khách, dựa trên kho tâm lý học đã chắt lọc.

``/tamly`` → danh sách chủ đề trong kho. ``/tamly <câu hỏi>`` → AI trả lời dựa trên các mục kho khớp nhất, kèm mục đã dùng;
hỏi «soạn tin …» thì AI soạn bản nháp — chủ bot tự duyệt, bot KHÔNG tự đổi tin nào.

Gọi AI mất vài giây tới vài chục giây nên chạy ở luồng nền (``CashbackService`` lo), trả lời đi qua hàng đợi tin.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.psych_kb.prompting import advisor_context
from app.features.psych_kb.store import default_kb
from cashback_bot.messages import BotReply, fit_html

logger = logging.getLogger(__name__)

TAMLY_COMMAND = re.compile(r"^/tamly(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
WORKING = "🧠 Đang tra kho tâm lý và hỏi AI… (khoảng 10–30 giây)"
AI_DOWN = "🧠 AI đang lỗi, chưa trả lời được. Anh thử lại sau ít phút."
NO_MATCH_NOTE = "(Kho chưa có mục khớp — AI trả lời theo hiểu biết chung, nên kiểm lại.)"

Generate = Callable[[str], tuple]


def topics_reply() -> BotReply:
    lines = ["🧠 <b>Kho tâm lý khách</b>", ""]
    for topic, entries in default_kb.topics().items():
        lines.append(f"• <b>{html.escape(topic)}</b> — {len(entries)} mục")
    lines += ["", "Hỏi: <code>/tamly khách sợ bấm link lạ thì nói sao</code>",
              "Soạn tin: <code>/tamly soạn tin nhắc khách chưa tạo link</code>",
              "Nguồn từng học thuyết: app/features/psych_kb/kb/_nguon.md"]
    return BotReply("\n".join(lines))


def build_prompt(question: str, context: str) -> str:
    kb = context or "(không có mục khớp)"
    return f"""Bạn là cố vấn tâm lý khách hàng cho chủ hai bot Telegram/Zalo:
- Cashbot (Telegram: zt_shopee_bot; Zalo: «Bot Săn Hoàn Tiền»): khách dán link món Shopee / TikTok Shop, bot báo tiền hoàn (ước tính) và đưa link mua; tiền về ví trong bot rồi rút
  về ngân hàng. Lưu ý mua: món có sẵn trong giỏ thì xoá đi, mở lại bằng link bot rồi mới thêm giỏ.
- AI Pass Store (Telegram: aipass_shop_bot): bán tài khoản AI / phần mềm (Canva Pro, ChatGPT…), nạp bằng chuyển khoản, bot giao tự động.

Kiến thức tâm lý học đã chắt lọc (chỉ dựa vào đây; ngoài kho thì nói rõ là ý chung):
\"\"\"
{kb}
\"\"\"

Câu hỏi của chủ bot:
\"\"\"{question}\"\"\"

Trả lời tiếng Việt, gọn (tối đa ~1.200 ký tự), thực tế, xưng «em» gọi «anh»:
1. Khách đang nghĩ / cảm thấy gì (1–2 câu).
2. Nên làm gì — gạch đầu dòng ngắn.
3. Nếu hỏi soạn tin / câu trả lời: đưa 1–2 bản nháp sẵn dùng (Threads: 1–2 câu teencode vừa phải; tin bot: rõ, lịch sự).
4. Dòng cuối: «Dựa vào: <mã mục>» (mã trong ngoặc vuông ở trên).
Không bịa số liệu, không gợi ý dọa / thúc ép / giả làm khách. Văn bản thường, không dùng markdown (*, #)."""


def answer(question: str, generate: Generate | None = None) -> str:
    """HTML Telegram trả lời ``/tamly <câu hỏi>``. AI lỗi → ``AI_DOWN``."""
    ctx = advisor_context(question)
    call = generate or (lambda p: AIUseCases.generate_text(p, purpose=AIPurpose.STRATEGIC_ADVICE))
    try:
        text, _meta = call(build_prompt(question, ctx.text))
    except Exception:
        logger.exception("[Cashback] /tamly gọi AI lỗi")
        text = None
    if not text or not text.strip():
        return AI_DOWN
    body = html.escape(text.strip().replace("**", ""))
    used = ", ".join(ctx.ids) if ctx.ids else NO_MATCH_NOTE
    out = f"🧠 <b>Tâm lý khách</b> — <i>{html.escape(question[:120])}</i>\n\n{body}\n\n<i>Mục kho: {html.escape(used)}</i>"
    return fit_html(out)
