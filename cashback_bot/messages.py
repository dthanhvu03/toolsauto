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
DIEUKIEN = (
    "🛡️ <b>LƯU Ý QUAN TRỌNG</b>\n"
    "<i>Để đơn hàng được ghi nhận chính xác</i>\n\n"
    "<b>1.</b> Xóa sản phẩm định mua khỏi giỏ hàng nếu đã thêm trước đó, "
    "sau đó mở link do bot cung cấp để mua.\n\n"
    "<b>2.</b> Sau khi mở link, không xem livestream, video hoặc nhấp vào các link quảng cáo khác "
    "trước khi hoàn tất thanh toán.\n\n"
    "<b>3.</b> Nên tạo link mới cho mỗi lần thanh toán để dễ ghi nhận và đối soát đơn hàng.\n\n"
    "<b>4.</b> Việc ghi nhận đơn hàng và hoa hồng do <b>Shopee quyết định</b>. "
    "Bot không thể can thiệp hoặc bảo đảm mọi đơn đều được hoàn tiền.\n\n"
    "<b>5.</b> Hãy thao tác mua hàng tự nhiên, tránh nhấp link hoặc đặt hàng liên tục bất thường "
    "khiến đơn có nguy cơ bị đánh giá không hợp lệ.\n\n"
    "💡 <b>Mẹo:</b> Chọn sản phẩm trước → Gửi link cho bot → Mở link bot cung cấp → Hoàn tất mua hàng."
)
HANG_NOTE = (
    "Chương trình hạng Đồng, Bạc và Vàng đang được phát triển, chưa có hiệu lực. "
    "Chưa có đơn đã xác nhận nên không có tiến độ lên hạng."
)
BOT_COMMANDS = (
    ("start", "Bắt đầu"),
    ("huongdan", "Hướng dẫn sử dụng"),
    ("dieukien", "Điều kiện nhận thưởng"),
    ("cachtinh", "Cách tính cashback"),
    ("hang", "Hạng thành viên"),
    ("help", "Trợ giúp"),
)


def _percent_label(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def how_to_calc_v11(rate_percent: int) -> str:
    example = (10_000 * rate_percent) // 100
    return (
        "<b>Cách tính hoàn tiền</b>\n\n"
        "<b>Đang áp dụng</b>\n"
        f"Bot đang tính: hoàn = {rate_percent}% hoa hồng ước tính.\n"
        f"Ví dụ hoa hồng 10.000đ thì hoàn dự kiến {format_vnd(example)}.\n"
        "Đây là số dự kiến từ hoa hồng ước tính. Công thức đang chạy chưa trừ thuế hay phí.\n"
        "Hạng Đồng, Bạc, Vàng chưa áp dụng vào cách tính này.\n\n"
        "<b>Công thức đề xuất, chưa bật</b>\n"
        "Khi được duyệt, hoàn = tỷ lệ chia × phần hoa hồng còn lại sau thuế, phí, điều chỉnh và dự phòng hợp lệ.\n"
        "Một khoản không bị trừ hai lần.\n"
        "Số dự kiến có thể khác số cuối. Hoa hồng có thể thay đổi.\n"
        "Số cuối chỉ chốt khi đối soát đủ.\n"
        "Bot không công bố số được rút hay ngày trả thưởng.\n"
        "Hiện chưa theo dõi đơn và chưa chi trả."
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
        f"{HANG_NOTE}\n\n"
        f"Hiện tỷ lệ cashback dự kiến của chương trình là {rate_percent}% hoa hồng ước tính, theo công thức đang áp dụng. "
        "Mức này chưa phải hạng Vàng trên quỹ sau phí và thuế."
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
