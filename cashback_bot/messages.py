"""Tin nhắn người mua đọc được. Không đưa hoa hồng, tỷ lệ chiết hay URL thô."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from cashback_bot.money import estimated_cashback, format_vnd

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
HUONGDAN = (
    "🎁 <b>HƯỚNG DẪN SỬ DỤNG</b>\n\n"
    "<b>1️⃣</b> Sao chép link sản phẩm bạn muốn mua trên Shopee.\n\n"
    "<b>2️⃣</b> Gửi link đó vào cuộc trò chuyện với bot.\n\n"
    "<b>3️⃣</b> Bot sẽ tạo link mua hàng và hiển thị số tiền hoàn dự kiến (nếu có dữ liệu).\n\n"
    "<b>4️⃣</b> Nhấn <b>🛒 Mua trên Shopee</b> để mở sản phẩm và đặt hàng.\n\n"
    "💡 <b>Lưu ý:</b> Bot không thu phí sử dụng. Việc mua hàng và thanh toán được thực hiện trực tiếp trên Shopee.\n\n"
    "⚠️ Tiền hoàn hiển thị chỉ là ước tính, không bảo đảm đơn hàng được ghi nhận hay được hoàn tiền. "
    "Hiện bot đang thử nghiệm, chưa hỗ trợ tra cứu đơn và chi trả."
)
DIEUKIEN = (
    "🛡️ <b>LƯU Ý QUAN TRỌNG</b>\n"
    "<i>Để tăng khả năng đơn hàng được ghi nhận</i>\n\n"
    "<b>1.</b> Nếu sản phẩm đã có sẵn trong giỏ hàng, bạn nên xóa sản phẩm đó "
    "và mở lại link do bot cung cấp trước khi mua.\n\n"
    "<b>2.</b> Sau khi mở link từ bot, hạn chế nhấp sang link quảng cáo, livestream "
    "hoặc link giới thiệu khác trước khi đặt hàng.\n\n"
    "<b>3.</b> Mỗi lần mua hàng, bạn nên lấy và mở link mới từ bot "
    "để thuận tiện cho việc ghi nhận và đối soát.\n\n"
    "<b>4.</b> Hãy mua hàng tự nhiên. Tránh nhấp link hoặc thực hiện giao dịch lặp lại bất thường.\n\n"
    "<b>5.</b> Đơn hàng và hoa hồng phải được Shopee ghi nhận hợp lệ. "
    "Đơn bị hủy, trả hàng hoặc không phát sinh hoa hồng sẽ không đủ điều kiện xét thưởng.\n\n"
    "💡 <b>Mẹo:</b> Chọn sản phẩm → Gửi link cho bot → Mở link được tạo → Đặt hàng trên Shopee.\n\n"
    "ℹ️ Các bước trên chỉ giúp hạn chế rủi ro mất ghi nhận, "
    "<b>không bảo đảm Shopee sẽ ghi nhận hoa hồng</b>."
)
HELP = (
    "🤖 <b>TRUNG TÂM TRỢ GIÚP</b>\n\n"
    "Bạn có thể gửi trực tiếp link sản phẩm Shopee vào đây để tạo link mua hàng "
    "và xem khoản hoàn dự kiến.\n\n"
    "<b>Các lệnh có thể sử dụng:</b>\n\n"
    "🎁 /huongdan — Cách sử dụng bot\n\n"
    "🛡️ /dieukien — Lưu ý để đơn được ghi nhận\n\n"
    "💰 /cachtinh — Cách tính tiền hoàn dự kiến\n\n"
    "🏅 /hang — Thông tin hạng thành viên\n\n"
    "🏠 /start — Bắt đầu sử dụng\n\n"
    "ℹ️ Bot đang trong giai đoạn thử nghiệm, chưa hỗ trợ theo dõi đơn, quản lý số dư hoặc rút tiền."
)
BOT_COMMANDS = (
    ("start", "Bắt đầu"),
    ("huongdan", "Hướng dẫn sử dụng"),
    ("dieukien", "Lưu ý khi mua hàng"),
    ("cachtinh", "Cách tính hoàn tiền"),
    ("hang", "Hạng thành viên"),
    ("help", "Danh sách lệnh"),
)


def _percent_label(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def how_to_calc_v11(rate_percent: int) -> str:
    example = estimated_cashback(10_000, rate_percent)
    return (
        "💰 <b>CÁCH TÍNH HOÀN TIỀN</b>\n\n"
        f"<b>Tỷ lệ tính số dự kiến: {rate_percent}%</b>\n\n"
        f"Số tiền hoàn dự kiến được tính bằng <b>{rate_percent}% hoa hồng ước tính</b> từ sản phẩm.\n\n"
        "📌 <b>Ví dụ:</b>\n\n"
        "• Hoa hồng ước tính: 10.000đ\n"
        f"• Tiền hoàn dự kiến: <b>{format_vnd(example)}</b>\n\n"
        "<b>Lưu ý:</b>\n\n"
        "• Đây chỉ là số tiền tham khảo, chưa trừ thuế và phí.\n"
        "• Hoa hồng thực tế có thể thay đổi hoặc bằng 0 nếu đơn không đủ điều kiện.\n"
        "• Số dự kiến không phải tiền đã được duyệt hoặc số dư có thể rút.\n\n"
        "⏳ Hiện bot chưa hỗ trợ theo dõi đơn hàng, xác nhận tiền hoàn thực tế hoặc chi trả."
    )


def how_to_calc_v12(rate_percent: int, fee_bps: int, tax_reserve_bps: int) -> str:
    return (
        "<b>Cách tính hoàn tiền</b>\n\n"
        "<b>Đang áp dụng cho ước tính</b>\n"
        f"Bot trừ dự phòng phí {_percent_label(fee_bps)} và dự phòng thuế {_percent_label(tax_reserve_bps)} "
        f"trên hoa hồng ước tính, rồi nhân {rate_percent}%.\n"
        "Dự phòng thuế trong cấu hình không phải mức thuế luật định.\n"
        "Một khoản không bị trừ hai lần.\n\n"
        "Số dự kiến có thể khác số cuối. Hoa hồng có thể thay đổi.\n"
        "Số cuối chỉ được xác nhận khi đối soát đủ.\n"
        "Bot không công bố số được rút hay ngày trả thưởng.\n"
        "Hiện chưa theo dõi đơn và chưa chi trả."
    )


def hang_message(rate_percent: int) -> str:
    return (
        "🏅 <b>HẠNG THÀNH VIÊN</b>\n\n"
        "Chương trình thành viên <b>Đồng · Bạc · Vàng</b> đang được phát triển "
        "và chưa chính thức áp dụng.\n\n"
        "Hiện tại:\n\n"
        "• Chưa có xếp hạng thành viên.\n"
        "• Chưa tính tiến độ lên hạng.\n"
        f"• Các báo giá hiện tại đang sử dụng tỷ lệ {rate_percent}% hoa hồng ước tính.\n\n"
        "✨ Khi chương trình ra mắt, bot sẽ thông báo rõ điều kiện lên hạng, "
        "quyền lợi và thời điểm áp dụng.\n\n"
        "💡 Bạn chưa cần thực hiện thao tác nào để đăng ký hạng thành viên."
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
    inline_keyboard: tuple[tuple[tuple[str, str], ...], ...] | None = None
    callback_query_id: str | None = None

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
