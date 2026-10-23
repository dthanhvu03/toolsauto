"""Tin nhắn người mua đọc được. Không đưa hoa hồng, tỷ lệ chiết hay URL thô.

Khuôn chung (PLAN-060): tiêu đề `<emoji> <b>Viết hoa đầu câu</b>`, câu ngắn,
tối đa một dòng cảnh báo `ⓘ` ở cuối. Khách đọc "hoàn dự kiến", không đọc "cashback".
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from cashback_bot.money import format_vnd

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

HOME = (
    "🎁 <b>Xem món Shopee được hoàn bao nhiêu</b>\n\n"
    "Dán link sản phẩm Shopee vào đây. "
    "Bot gửi lại link mua và số tiền hoàn dự kiến.\n\n"
    "ⓘ Bot đang thử nghiệm. Số hoàn là ước tính, chưa theo dõi đơn và chưa chi trả."
)
START_MESSAGE = HOME
HELP = HOME
PAGE_KEYBOARD: Keyboard = ((("◀️ Trang chủ", "u:p:home"),),)
TIP_KEYBOARD: Keyboard = ((("🛡️ Lưu ý trước khi mua", "u:tip"),),)
GUIDE_KEYBOARD: Keyboard = ((("📖 Cách lấy link", "u:p:guide"),),)
# Popup answerCallbackQuery tối đa 200 ký tự.
TIP_ALERT = (
    "Trước khi đặt hàng:\n"
    "1. Món đã có trong giỏ thì xóa đi.\n"
    "2. Mở đúng link bot vừa gửi.\n"
    "3. Không bấm sang quảng cáo, livestream hay link khác.\n"
    "Không bảo đảm Shopee sẽ ghi nhận."
)
CLOSED_ALERT = "Tài khoản này chưa được mở. Bot đang mở thử cho một số tài khoản."
# Hiện ở màn "What can this bot do?" trước khi bấm Start. Tối đa 512 và 120 ký tự.
DESCRIPTION = (
    "Dán link sản phẩm Shopee, bot gửi lại link mua và số tiền hoàn dự kiến.\n\n"
    "Bot đang thử nghiệm: số hoàn là ước tính, chưa theo dõi đơn và chưa chi trả. "
    "Bot không thu phí sử dụng."
)
SHORT_DESCRIPTION = "Dán link Shopee, xem số tiền hoàn dự kiến. Bot đang thử nghiệm."


def home_keyboard(show_rank: bool = False) -> Keyboard:
    second: tuple[tuple[str, str], ...] = (("💰 Cách tính", "u:p:calc"),)
    if show_rank:
        second += (("🏅 Hạng thành viên", "u:p:rank"),)
    return (
        (("📖 Cách dùng", "u:p:guide"), ("🛡️ Để được ghi nhận", "u:p:rules")),
        second,
    )
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
# Chỉ đăng ký với scope chat của từng admin.
ADMIN_COMMANDS = BOT_COMMANDS + (("admin", "Quản trị"),)


def how_to_calc(v12: bool) -> str:
    """Giải thích cho khách, không đưa tỷ lệ chia, phí hay thuế (đó là số nội bộ)."""
    deduction = (
        "• Số dự kiến đã trừ phí và thuế liên quan.\n"
        if v12
        else "• Số dự kiến chưa trừ thuế và phí.\n"
    )
    return (
        "💰 <b>Cách tính tiền hoàn</b>\n\n"
        "Khi bạn mua qua link của bot, Shopee trả cho chương trình một khoản hoa hồng. "
        "Bot chia lại một phần khoản đó cho bạn. Số tiền hiện trên mỗi link là phần bạn dự kiến nhận.\n\n"
        + deduction
        + "• Hoa hồng có thể thay đổi, hoặc bằng 0 nếu đơn bị hủy, trả hàng hay không đủ điều kiện.\n"
        "• Số cuối chỉ được xác nhận khi Shopee đối soát xong.\n"
        "• Số dự kiến chưa phải tiền đã duyệt hay có thể rút.\n\n"
        "ⓘ Bot chưa theo dõi đơn và chưa chi trả."
    )


def hang_message() -> str:
    return (
        "🏅 <b>Hạng thành viên</b>\n\n"
        "Chương trình <b>Đồng · Bạc · Vàng</b> đang được phát triển, chưa chính thức áp dụng.\n\n"
        "Hiện mọi khách dùng chung một cách tính, xem /cachtinh. "
        "Bạn chưa cần đăng ký gì.\n\n"
        "ⓘ Khi ra mắt, bot sẽ báo rõ điều kiện lên hạng, quyền lợi và thời điểm áp dụng."
    )


INVALID_LINK = (
    "⚠️ <b>Chưa nhận ra link</b>\n"
    "Mình cần link sản phẩm Shopee: shopee.vn hoặc link rút gọn s.shopee.vn.\n"
    "Bấm nút dưới hoặc gõ /huongdan để xem cách lấy link."
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
    """text rỗng: chỉ trả lời callback (toast/popup), không gửi hay sửa tin."""

    text: str
    button_url: str | None = None
    inline_keyboard: Keyboard | None = None
    callback_query_id: str | None = None
    edit_message_id: int | None = None
    delete_message_id: int | None = None
    toast: str | None = None
    show_alert: bool = False

    def markup(self) -> dict | None:
        rows: list[list[dict]] = []
        if self.button_url:
            rows.append([{"text": BUY_BUTTON, "url": self.button_url}])
        for row in self.inline_keyboard or ():
            rows.append([{"text": label, "callback_data": data} for label, data in row])
        return {"inline_keyboard": rows} if rows else None


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
    return BotReply(text=text, button_url=affiliate_url, inline_keyboard=TIP_KEYBOARD)


def home_reply(show_rank: bool = False) -> BotReply:
    return BotReply(HOME, inline_keyboard=home_keyboard(show_rank))


def page_reply(text: str) -> BotReply:
    return BotReply(text, inline_keyboard=PAGE_KEYBOARD)


def invalid_link_reply() -> BotReply:
    return BotReply(INVALID_LINK, inline_keyboard=GUIDE_KEYBOARD)


def render_success(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V11)


def render_success_v12(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V12)
