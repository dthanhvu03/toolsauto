"""Tin nhắn người mua đọc được. Không đưa hoa hồng, tỷ lệ chiết hay URL thô."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from cashback_bot.money import format_vnd

CLOSED = "Bot đang mở thử cho một số tài khoản. Tài khoản này chưa được mở."
START_MESSAGE = (
    "🎁 <b>MÓN BẠN ĐỊNH MUA CÓ THỂ ĐƯỢC HOÀN BAO NHIÊU?</b>\n\n"
    "Bạn đã tìm được món yêu thích trên Shopee? Thử kiểm tra xem đơn hàng đó có thể có thêm khoản hoàn tiền nào nhé! 💸\n\n"
    "✨ Chỉ cần gửi link sản phẩm, bot sẽ giúp bạn xem:\n\n"
    "💰 Số tiền hoàn dự kiến\n"
    "🛍️ Thông tin và giá tham khảo của sản phẩm\n\n"
    "Cách thực hiện cực đơn giản:\n\n"
    "1️⃣ Sao chép link sản phẩm trên Shopee.\n"
    "2️⃣ Dán link vào cuộc trò chuyện này.\n\n"
    "👇 Thử gửi link món bạn đang muốn mua nhé!\n\n"
    "🧪 Bot đang trong giai đoạn thử nghiệm. Tiền hoàn chỉ là ước tính; hiện chưa hỗ trợ theo dõi đơn hoặc chi trả tiền hoàn."
)
GUIDE = (
    "🎁 <b>CÁCH SỬ DỤNG</b>\n\n"
    "1️⃣ Copy link sản phẩm Shopee.\n"
    "2️⃣ Gửi link vào cuộc trò chuyện này.\n"
    "3️⃣ Xem khoản hoàn dự kiến.\n"
    "4️⃣ Bấm \"🛒 Mua trên Shopee\" để đặt hàng.\n\n"
    "💡 Bạn mua hàng trên Shopee như bình thường,\n"
    "không mất phí sử dụng bot.\n\n"
    "ℹ️ Khoản hoàn phụ thuộc vào việc Shopee\n"
    "ghi nhận và xác nhận đơn hợp lệ.\n\n"
    "Hiện bot chưa hỗ trợ theo dõi đơn,\n"
    "quản lý số dư hoặc rút tiền."
)
HOW_TO_CALC = (
    "<b>Cách tính hoàn tiền</b>\n\n"
    "Bot đang tính: hoàn = 70% hoa hồng ước tính.\n"
    "Ví dụ hoa hồng 10.000đ thì hoàn dự kiến 7.000đ.\n\n"
    "Đây là số ước tính, chưa phải số tiền đã xác nhận."
)
HOW_TO_CALC_V12 = (
    "<b>Cách tính hoàn tiền</b>\n\n"
    "Cashback dự kiến trừ trước một khoản dự phòng phí và một khoản dự phòng rủi ro thuế, "
    "rồi mới nhân tỷ lệ chia.\n"
    "10% trong cấu hình thử là dự phòng, không phải mức thuế luật định cho mọi đơn.\n\n"
    "Số tiền được ước tính sau các khoản dự phòng phí và thuế. "
    "Hoàn tiền thực tế phụ thuộc vào hoa hồng Shopee xác nhận, các khoản khấu trừ và điều kiện chương trình. "
    "Hiện hệ thống chưa theo dõi hoặc chi trả đơn hàng."
)
INVALID_LINK = (
    "Mình cần link sản phẩm Shopee. "
    "Gửi link shopee.vn hoặc link rút gọn s.shopee.vn.\n\n"
    "Gõ /huongdan nếu cần xem cách làm."
)
STALE = (
    "⏳ Chưa lấy được thông tin hoàn tiền mới nhất.\n\n"
    "Dữ liệu sản phẩm hiện chưa sẵn sàng.\n"
    "Bạn vui lòng thử lại sau nhé."
)
NOT_FOUND = "Không thấy sản phẩm từ link này. Gửi lại link giúp mình."
GENERIC_FAIL = "Mình chưa tạo được link. Thử lại sau ít phút."
BUY_BUTTON = "🛒 Mua trên Shopee"


@dataclass(frozen=True)
class BotReply:
    text: str
    button_url: str | None = None

    def markup(self) -> dict | None:
        if not self.button_url:
            return None
        return {"inline_keyboard": [[{"text": BUY_BUTTON, "url": self.button_url}]]}


def rate_limited_reply(cooldown_sec: int) -> BotReply:
    minutes = max(1, (max(0, cooldown_sec) + 59) // 60)
    return BotReply(
        "Bạn vừa gửi hơi nhiều link.\n\n"
        f"Mình tạm dừng nhận link mới khoảng {minutes} phút để bot không bị quá tải.\n"
        "Link đã tạo trước đó vẫn dùng được.\n\n"
        "Gõ /huongdan nếu cần xem lại cách dùng."
    )


def buyer_name(name: str) -> str:
    text = " ".join((name or "").split())
    head = re.split(r"[,|]", text, maxsplit=1)[0].strip(" .-")
    if 8 <= len(head) <= 52:
        return head
    if len(text) <= 52:
        return text
    cut = text[:51].rsplit(" ", 1)[0]
    return (cut or text[:51]).rstrip(" ,.-") + "…"


def render_success(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    safe_name = html.escape(buyer_name(name))
    text = (
        "🎁 <b>MÓN NÀY CÓ THỂ ĐƯỢC HOÀN TIỀN</b>\n\n"
        "💰 Bạn có thể được hoàn thêm\n"
        f"<b>{format_vnd(cashback_vnd)}</b>\n\n"
        f"{safe_name}\n"
        f"Giá tham khảo: {format_vnd(price_vnd)}\n\n"
        "ℹ️ Tiền hoàn chỉ là ước tính, phụ thuộc vào việc Shopee xác nhận đơn hợp lệ.\n"
        "Chưa phải tiền có thể rút."
    )
    return BotReply(text=text, button_url=affiliate_url)


def render_success_v12(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    safe_name = html.escape(buyer_name(name))
    text = (
        "🎁 <b>MÓN NÀY CÓ THỂ ĐƯỢC HOÀN TIỀN</b>\n\n"
        "Cashback dự kiến: "
        f"<b>{format_vnd(cashback_vnd)}</b>\n\n"
        f"{safe_name}\n"
        f"Giá tham khảo: {format_vnd(price_vnd)}\n\n"
        "Số tiền được ước tính sau các khoản dự phòng phí và thuế. "
        "Hoàn tiền thực tế phụ thuộc vào hoa hồng Shopee xác nhận, các khoản khấu trừ và điều kiện chương trình. "
        "Hiện hệ thống chưa theo dõi hoặc chi trả đơn hàng."
    )
    return BotReply(text=text, button_url=affiliate_url)
