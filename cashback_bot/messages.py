"""Tin nhắn người mua đọc được. Không đưa hoa hồng, tỷ lệ chiết hay URL thô.

Khuôn chung (PLAN-060): tiêu đề `<emoji> <b>Viết hoa đầu câu</b>`, câu ngắn,
tối đa một dòng cảnh báo `ⓘ` ở cuối. Khách đọc "hoàn dự kiến", không đọc "cashback".
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from cashback_bot.money import estimated_cashback, format_vnd

HOME = (
    "🎁 <b>Xem món Shopee được hoàn bao nhiêu</b>\n\n"
    "Dán link sản phẩm Shopee vào đây. "
    "Bot gửi lại link mua và số tiền hoàn dự kiến.\n\n"
    "📖 /huongdan — Cách dùng\n"
    "🛡️ /dieukien — Để đơn được ghi nhận\n"
    "💰 /cachtinh — Cách tính tiền hoàn\n\n"
    "ⓘ Bot đang thử nghiệm. Số hoàn là ước tính, chưa theo dõi đơn và chưa chi trả."
)
START_MESSAGE = HOME
HELP = HOME
CLOSED = (
    "🔒 <b>Tài khoản này chưa được mở</b>\n"
    "Bot đang mở thử cho một số tài khoản."
)
HUONGDAN = (
    "📖 <b>Cách dùng</b>\n\n"
    "1. Mở sản phẩm trên Shopee, bấm Chia sẻ rồi Sao chép liên kết.\n"
    "2. Dán link vào đây.\n"
    "3. Bot gửi lại số tiền hoàn dự kiến và nút <b>🛒 Mua trên Shopee</b>.\n"
    "4. Bấm nút đó để mở sản phẩm và đặt hàng như bình thường.\n\n"
    "Bot không thu phí sử dụng. Bạn thanh toán trực tiếp trên Shopee.\n\n"
    "ⓘ Số hoàn là ước tính, không bảo đảm đơn hàng được ghi nhận hay được hoàn tiền."
)
DIEUKIEN = (
    "🛡️ <b>Để đơn được ghi nhận</b>\n\n"
    "1. Sản phẩm đã có sẵn trong giỏ: xóa đi, rồi mở lại bằng link của bot.\n"
    "2. Sau khi mở link của bot, đừng bấm sang quảng cáo, livestream "
    "hay link giới thiệu khác trước khi đặt hàng.\n"
    "3. Mỗi lần mua, lấy link mới từ bot.\n"
    "4. Mua tự nhiên. Không bấm link hay đặt hàng lặp lại bất thường.\n"
    "5. Đơn bị hủy, trả hàng hoặc không phát sinh hoa hồng thì không được xét hoàn.\n\n"
    "ⓘ Các bước trên giảm rủi ro mất ghi nhận, "
    "<b>không bảo đảm Shopee sẽ ghi nhận hoa hồng</b>."
)
BOT_COMMANDS = (
    ("start", "Trang chủ"),
    ("huongdan", "Cách dùng"),
    ("dieukien", "Để đơn được ghi nhận"),
    ("cachtinh", "Cách tính tiền hoàn"),
    ("help", "Trợ giúp"),
)


def _percent_label(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def how_to_calc_v11(rate_percent: int) -> str:
    example = estimated_cashback(10_000, rate_percent)
    return (
        "💰 <b>Cách tính tiền hoàn</b>\n\n"
        f"Hoàn dự kiến = <b>{rate_percent}% hoa hồng ước tính</b> của sản phẩm.\n\n"
        f"Ví dụ: hoa hồng ước tính 10.000đ → hoàn dự kiến <b>{format_vnd(example)}</b>.\n\n"
        "• Số dự kiến chưa trừ thuế và phí.\n"
        "• Hoa hồng thực tế có thể thay đổi hoặc bằng 0 nếu đơn không đủ điều kiện.\n"
        "• Số dự kiến chưa phải tiền đã duyệt hay có thể rút.\n\n"
        "ⓘ Bot chưa theo dõi đơn, chưa xác nhận tiền hoàn thực tế và chưa chi trả."
    )


def how_to_calc_v12(rate_percent: int, fee_bps: int, tax_reserve_bps: int) -> str:
    return (
        "💰 <b>Cách tính tiền hoàn</b>\n\n"
        f"Từ hoa hồng ước tính, bot trừ dự phòng phí {_percent_label(fee_bps)} "
        f"và dự phòng thuế {_percent_label(tax_reserve_bps)}, rồi tính {rate_percent}% phần còn lại.\n\n"
        "• Dự phòng thuế là khoản để riêng khi ước tính, không phải mức thuế luật định.\n"
        "• Một khoản không bị trừ hai lần.\n"
        "• Hoa hồng có thể thay đổi, nên số dự kiến có thể khác số cuối.\n"
        "• Số cuối chỉ được xác nhận khi đối soát đủ.\n"
        "• Bot không công bố số được rút hay ngày trả thưởng.\n\n"
        "ⓘ Bot chưa theo dõi đơn và chưa chi trả."
    )


def hang_message(rate_percent: int) -> str:
    return (
        "🏅 <b>Hạng thành viên</b>\n\n"
        "Chương trình <b>Đồng · Bạc · Vàng</b> đang được phát triển, chưa chính thức áp dụng.\n\n"
        f"Hiện mọi báo giá dùng chung tỷ lệ {rate_percent}% hoa hồng ước tính. "
        "Bạn chưa cần đăng ký gì.\n\n"
        "ⓘ Khi ra mắt, bot sẽ báo rõ điều kiện lên hạng, quyền lợi và thời điểm áp dụng."
    )


INVALID_LINK = (
    "⚠️ <b>Chưa nhận ra link</b>\n"
    "Mình cần link sản phẩm Shopee: shopee.vn hoặc link rút gọn s.shopee.vn.\n"
    "Gõ /huongdan để xem cách lấy link."
)
STALE = (
    "⏳ <b>Chưa lấy được dữ liệu sản phẩm</b>\n"
    "Thông tin hoàn tiền của món này chưa sẵn sàng.\n"
    "Bạn thử gửi lại sau ít phút nhé."
)
NOT_FOUND = (
    "⚠️ <b>Không tìm thấy sản phẩm</b>\n"
    "Mình không thấy sản phẩm nào từ link này.\n"
    "Bạn mở lại sản phẩm trên Shopee, sao chép link mới rồi gửi lại."
)
GENERIC_FAIL = (
    "⚠️ <b>Chưa tạo được link</b>\n"
    "Hệ thống gặp lỗi khi tạo link mua.\n"
    "Bạn thử lại sau ít phút nhé."
)
BUY_BUTTON = "🛒 Mua trên Shopee"
_NOTE_V11 = "Số ước tính, chỉ được hoàn khi Shopee xác nhận đơn hợp lệ. Chưa phải tiền có thể rút."
_NOTE_V12 = (
    "Số ước tính sau dự phòng phí và thuế, có thể khác số cuối. "
    "Chỉ được hoàn khi Shopee xác nhận đơn hợp lệ. Chưa phải tiền có thể rút."
)


@dataclass(frozen=True)
class BotReply:
    text: str
    button_url: str | None = None
    inline_keyboard: tuple[tuple[tuple[str, str], ...], ...] | None = None
    callback_query_id: str | None = None
    edit_message_id: int | None = None

    def markup(self) -> dict | None:
        if self.inline_keyboard:
            return {
                "inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in row]
                    for row in self.inline_keyboard
                ]
            }
        if not self.button_url:
            return None
        return {"inline_keyboard": [[{"text": BUY_BUTTON, "url": self.button_url}]]}


def rate_limited_reply(cooldown_sec: int) -> BotReply:
    minutes = max(1, (max(0, cooldown_sec) + 59) // 60)
    return BotReply(
        "⏳ <b>Bạn gửi hơi nhiều link</b>\n"
        f"Mình tạm dừng nhận link mới khoảng {minutes} phút để bot không bị quá tải.\n"
        "Link đã tạo trước đó vẫn dùng được."
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


def _render_card(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str, note: str) -> BotReply:
    safe_name = html.escape(buyer_name(name))
    title = "✅ <b>Đã tạo link hoàn tiền</b>" if cashback_vnd > 0 else "✅ <b>Đã tạo link mua</b>"
    text = (
        f"{title}\n\n"
        f"💰 Hoàn dự kiến: <b>{format_vnd(cashback_vnd)}</b>\n\n"
        f"🛍️ {safe_name}\n"
        f"Giá tham khảo: {format_vnd(price_vnd)}\n\n"
        f"ⓘ {note}"
    )
    return BotReply(text=text, button_url=affiliate_url)


def render_success(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V11)


def render_success_v12(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V12)
