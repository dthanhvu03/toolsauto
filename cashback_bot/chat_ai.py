"""Trả lời tin chữ của khách bằng AI (PLAN-172 T2).

Trước đây tin không phải link (khách hỏi «hoàn bao nhiêu», «có lừa không», «lấy link sao»…) chỉ nhận câu mẫu «bot chỉ đọc
được link»: 25 lần trong DB, khách đi luôn. Giờ AI (9Router) trả lời ngắn đúng câu hỏi rồi dẫn khách dán link.

- Tin cảm ơn / ok / quá ngắn: vẫn câu mẫu, không gọi AI.
- Mỗi khách tối đa 1 câu AI trong ``COOLDOWN``; tắt nhanh bằng bot_state ``chat_ai:off`` (không cần restart).
- Không lưu nội dung tin (PLAN-077): chỉ gửi qua AI rồi bỏ. AI lỗi / trả rỗng → câu mẫu cũ.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from datetime import timedelta

from app.core.ai.use_cases import AIPurpose, AIUseCases
from cashback_bot.messages import _LOOKS_LIKE_LINK, BUY_RULE, CART_RULE, ITEM_RULE, VOUCHER_RULE, WALLET_RULE

logger = logging.getLogger(__name__)

OFF_KEY = "chat_ai:off"
LAST_PREFIX = "chat_ai:last:"
COOLDOWN = timedelta(seconds=45)
MAX_INPUT = 400
MAX_REPLY = 450
WORKING = "💬 Mình đọc tin bạn rồi, trả lời ngay đây…"
SKIP = "SKIP"

_ACK = re.compile(r"^(ok[ea]?y?|oki|okie|dạ|da|vâng|vang|ừ|uh|ừm|cảm ơn|cam on|cám ơn|thanks?|thank you|tks|ty|"
                  r"hi|hello|alo|chào|chao|👍|❤️|🙏)[\s!.…]*$", re.IGNORECASE)
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

Generate = Callable[[str], tuple]


def worth_asking(text: str) -> bool:
    """Tin có nội dung để AI trả lời: không dáng link (link sai sàn giữ cảnh báo cũ), không «ok» / «cảm ơn» / 1–3 ký tự."""
    stripped = (text or "").strip()
    return len(stripped) >= 4 and not _ACK.fullmatch(stripped) and not _LOOKS_LIKE_LINK.search(stripped)


def _plain(rule: str) -> str:
    return _TAG.sub("", rule).replace("•", "-").strip()


def build_prompt(text: str, wallet_open: bool) -> str:
    payout = ("Khách rút về tài khoản ngân hàng trong mục Ví của bot." if wallet_open else
              "Bot CHƯA mở rút tiền: tiền hoàn đang tạm tính, đơn vẫn được ghi lại. Không hứa ngày rút.")
    return f"""Bạn là trợ lý trong bot Telegram/Zalo hoàn tiền Shopee (Cashbot). Khách vừa nhắn một tin chữ, không phải link.
Trả lời đúng câu khách hỏi, rồi rủ khách dán link sản phẩm Shopee để xem số hoàn.

Tin khách:
\"\"\"{text[:MAX_INPUT]}\"\"\"

SỰ THẬT VỀ BOT (chỉ được nói trong phạm vi này)
- Cách dùng: mở món trên app Shopee → Chia sẻ → Sao chép liên kết → dán vào bot → bot gửi số tiền hoàn dự kiến + nút 🛒 Mua.
- Bot không thu phí. Tiền hoàn đến từ hoa hồng Shopee trả cho link của bot, bot chia lại cho khách.
- {_plain(BUY_RULE)}
- {_plain(CART_RULE)}
- {_plain(ITEM_RULE)}
- {_plain(VOUCHER_RULE)}
- {WALLET_RULE}. {payout}
- Số hoàn chỉ biết khi dán link (mỗi món một mức). ShopeeFood chưa được hoàn.
- Lệnh: /huongdan (cách lấy link), /donhang (đơn đã ghi nhận).

QUY TẮC
- 1–3 câu, tối đa khoảng 300 ký tự, xưng mình / bạn, thân thiện, tối đa 1 emoji. Không gửi link nào.
- Không bịa số tiền, phần trăm, ngày tiền về. Không hỏi mật khẩu, OTP, số thẻ.
- Khiếu nại, đơn thiếu tiền, muốn gặp người thật → nói khách gõ /hotro để gửi yêu cầu cho admin.
- Tin rác, quảng cáo, chỉ chào / cảm ơn, không liên quan → trả về đúng một chữ: {SKIP}
Chỉ trả về câu gửi khách, không giải thích."""


def answer(text: str, wallet_open: bool, generate: Generate | None = None) -> str | None:
    """Câu trả lời (HTML đã escape) hoặc None (AI lỗi / bỏ qua) → bên gọi dùng câu mẫu."""
    call = generate or (lambda p: AIUseCases.generate_text(p, purpose=AIPurpose.GENERIC))
    try:
        raw, _meta = call(build_prompt(text, wallet_open))
    except Exception:
        logger.exception("[Cashback] chat_ai: gọi AI lỗi")
        return None
    reply = " ".join(_URL.sub("", _TAG.sub("", raw or "")).split())
    if len(reply) < 2 or reply.strip(" .").upper() == SKIP:
        return None
    if len(reply) > MAX_REPLY:
        reply = reply[:MAX_REPLY].rsplit(" ", 1)[0] + "…"
    return html.escape(reply, quote=False)
