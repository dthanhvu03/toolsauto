"""Trả lời tin chữ của khách Store bằng AI (Xingchi → 9Router fallback).

Trước đây tin không phải lệnh/menu chỉ mở trang chủ — khách hỏi «có ChatGPT không», «bảo hành sao»
không được trả lời. Giờ AI trả lời ngắn đúng câu hỏi rồi dẫn bấm 🛒 Mua sản phẩm.

- Tin cảm ơn / ok / quá ngắn: không gọi AI → trang chủ như cũ.
- Mỗi khách tối đa 1 câu AI trong ``COOLDOWN``; tắt bằng state ``chat_ai:off``.
- Không lưu nội dung tin: chỉ gửi qua AI rồi bỏ. AI lỗi / SKIP → trang chủ.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable, Sequence
from datetime import timedelta

from app.core.ai.use_cases import AIPurpose, AIUseCases

logger = logging.getLogger(__name__)

OFF_KEY = "chat_ai:off"
LAST_PREFIX = "chat_ai:last:"
COOLDOWN = timedelta(seconds=45)
MAX_INPUT = 400
MAX_REPLY = 450
WORKING = "💬 Mình đọc tin bạn rồi, trả lời ngay đây…"
SKIP = "SKIP"

_ACK = re.compile(
    r"^(ok[ea]?y?|oki|okie|dạ|da|vâng|vang|ừ|uh|ừm|cảm ơn|cam on|cám ơn|thanks?|thank you|tks|ty|"
    r"hi|hello|alo|chào|chao|👍|❤️|🙏)[\s!.…]*$",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

Generate = Callable[[str], tuple]


def worth_asking(text: str) -> bool:
    """Tin có nội dung để AI trả lời: không «ok» / «cảm ơn» / 1–3 ký tự."""
    stripped = (text or "").strip()
    return len(stripped) >= 4 and not _ACK.fullmatch(stripped)


def build_prompt(text: str, shop_name: str, catalog: Sequence[str], closed_note: str | None) -> str:
    names = ", ".join(catalog[:12]) if catalog else "(đang cập nhật — bảo khách bấm 🛒 Mua sản phẩm để xem)"
    closed = (
        f"- Shop đang tạm nghỉ: {closed_note}. Khách vẫn xem món / nạp ví; đặt mua khi mở lại.\n"
        if closed_note else
        "- Shop đang mở, khách đặt mua được.\n"
    )
    return f"""Bạn là trợ lý trong bot Telegram bán tài khoản số / tool AI (Store shop «{shop_name}»).
Khách vừa nhắn một tin chữ. Trả lời đúng câu họ hỏi, rồi rủ họ bấm 🛒 Mua sản phẩm trên menu.

Tin khách:
\"\"\"{text[:MAX_INPUT]}\"\"\"

SỰ THẬT VỀ SHOP (chỉ được nói trong phạm vi này)
- Cách mua: chọn món → chọn số lượng → quét VietQR (hoặc trừ số dư ví) → bot gửi hàng (link/acc) trong chat.
- Không cần nạp trước: chọn món, quét QR là bot gửi hàng ngay.
- Có thể nạp ví sẵn (🎁 Ví) rồi mua bằng số dư.
- Một số món lấy từ nhà cung cấp; hết hàng / bảo hành xem mô tả từng món (ký hiệu BH… trong tên).
- Món đang bán (tên, có thể rút gọn): {names}
{closed}- Khiếu nại / cần người thật: bảo khách bấm ☎️ Hỗ trợ hoặc /supportadmin (1 lần/ngày).
- Lệnh: /menu (menu), /support (liên hệ), /huy (huỷ thao tác đang làm).

QUY TẮC
- 1–3 câu, tối đa khoảng 300 ký tự, xưng mình / bạn, thân thiện, tối đa 1 emoji. Không gửi link ngoài.
- Không bịa giá cụ thể, % giảm, thời gian bảo hành, tồn kho số — bảo khách mở 🛒 xem giá / mô tả đúng món.
- Không hỏi mật khẩu, OTP, số thẻ. Không nhận chuyển khoản ngoài QR của bot.
- Tin rác, quảng cáo, chỉ chào / cảm ơn, không liên quan shop → trả về đúng một chữ: {SKIP}
Chỉ trả về câu gửi khách, không giải thích."""


def answer(
    text: str,
    *,
    shop_name: str,
    catalog: Sequence[str] = (),
    closed_note: str | None = None,
    generate: Generate | None = None,
) -> str | None:
    """Câu trả lời (HTML đã escape) hoặc None (AI lỗi / bỏ qua) → bên gọi mở trang chủ."""
    call = generate or (lambda p: AIUseCases.generate_text(p, purpose=AIPurpose.GENERIC))
    try:
        raw, _meta = call(build_prompt(text, shop_name, catalog, closed_note))
    except Exception:
        logger.exception("[Store] chat_ai: gọi AI lỗi")
        return None
    reply = " ".join(_URL.sub("", _TAG.sub("", raw or "")).split())
    if len(reply) < 2 or reply.strip(" .").upper() == SKIP:
        return None
    if len(reply) > MAX_REPLY:
        reply = reply[:MAX_REPLY].rsplit(" ", 1)[0] + "…"
    return html.escape(reply, quote=False)
