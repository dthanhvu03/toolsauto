"""Tin nhắn người mua đọc được. Không đưa hoa hồng, tỷ lệ chiết hay URL thô.

Khuôn chung (PLAN-060): tiêu đề `<emoji> <b>Viết hoa đầu câu</b>`, câu ngắn,
tối đa một dòng cảnh báo `ⓘ` ở cuối. Khách đọc "hoàn dự kiến", không đọc "cashback".
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.money import format_vnd

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

HOME = (
    "🎁 <b>Xem món Shopee được hoàn bao nhiêu</b>\n\n"
    "Dán link sản phẩm Shopee vào đây. "
    "Bot gửi lại link mua và số tiền hoàn dự kiến.\n\n"
    "ⓘ Bot đang thử nghiệm. Số hoàn là ước tính. Ví hoàn tiền chưa mở, bot chưa chi trả."
)
# Khi admin bật ví (PLAN-066) thì bot đã theo dõi đơn và chi trả; câu ⓘ phải đổi theo.
HOME_WALLET = (
    "🎁 <b>Xem món Shopee được hoàn bao nhiêu</b>\n\n"
    "Dán link sản phẩm Shopee vào đây. "
    "Bot gửi lại link mua và số tiền hoàn dự kiến.\n\n"
    "Mua qua link của bot, bot tự theo dõi đơn và báo khi tiền hoàn vào ví."
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
    "Bot đang thử nghiệm: số hoàn là ước tính, ví hoàn tiền chưa mở và bot chưa chi trả. "
    "Bot không thu phí sử dụng."
)
SHORT_DESCRIPTION = "Dán link Shopee, xem số tiền hoàn dự kiến. Bot đang thử nghiệm."


def home_keyboard(show_rank: bool = False, show_wallet: bool = False) -> Keyboard:
    second: tuple[tuple[str, str], ...] = (("💰 Cách tính", "u:p:calc"), ("📩 Hỗ trợ", "u:p:support"))
    if show_rank:
        second += (("🏅 Hạng thành viên", "u:p:rank"),)
    rows: Keyboard = (
        (("📦 Đơn hàng của tôi", "u:p:orders"),),
        (("📖 Cách dùng", "u:p:guide"), ("🛡️ Để được ghi nhận", "u:p:rules")),
        second,
    )
    if show_wallet:
        rows = ((("👛 Ví của tôi", "u:p:wallet"),),) + rows
    return rows
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
    ("donhang", "Đơn hàng của tôi"),
    ("hotro", "Hỗ trợ & khiếu nại"),
    ("thongbao", "Cài đặt thông báo"),
    ("help", "Trợ giúp"),
)
# Chỉ đăng ký với scope chat của từng admin.
ADMIN_COMMANDS = BOT_COMMANDS + (("admin", "Quản trị"),)
# Thêm vào menu lệnh lúc khởi động nếu ví đang bật (PLAN-066).
WALLET_COMMAND = ("vi", "Ví hoàn tiền")


def how_to_calc(v12: bool, wallet_hold_days: int | None = None, wallet_min_vnd: int | None = None) -> str:
    """Giải thích cho khách, không đưa tỷ lệ chia, phí hay thuế (đó là số nội bộ).

    v12: cách tính đang báo giá cho link mới. Link cũ giữ cách tính lúc tạo (PLAN-076).
    """
    deduction = (
        "• Số dự kiến đã trừ trước dự phòng phí và thuế. Đây là mức bot tự đặt để ước tính, "
        "không phải số thuế bạn phải nộp.\n"
        if v12
        else "• Số dự kiến chưa trừ thuế và phí.\n"
    )
    return (
        "💰 <b>Cách tính tiền hoàn</b>\n\n"
        "Khi bạn mua qua link của bot, Shopee trả cho chương trình một khoản hoa hồng. "
        "Bot chia lại một phần khoản đó cho bạn. Số tiền hiện trên mỗi link là phần bạn dự kiến nhận.\n\n"
        + deduction
        + "• Số trên link tính theo giá tham khảo. Shopee tính trên số tiền bạn thực trả "
        "(sau voucher, xu, giảm giá), nên số thật thường thấp hơn.\n"
        "• Hoa hồng có thể thay đổi, hoặc bằng 0 nếu đơn bị hủy, trả hàng hay không đủ điều kiện.\n"
        "• Số cuối chỉ được xác nhận khi Shopee đối soát xong.\n"
        "• Số dự kiến chưa phải tiền đã duyệt hay có thể rút.\n"
        "• Mỗi link giữ cách tính lúc bot tạo link. Bot đổi cách tính thì chỉ áp dụng cho link tạo sau đó.\n\n"
        + (
            "ⓘ Ví hoàn tiền chưa mở, bot chưa chi trả."
            if wallet_hold_days is None
            else f"ⓘ Tiền hoàn vào ví {wallet_hold_days} ngày sau khi đơn hoàn thành. "
            f"Rút từ {format_vnd(wallet_min_vnd or 0)}, chuyển khoản về tài khoản bạn khai."
        )
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
# Shopee tính hoa hồng trên số tiền khách thực trả, bot chỉ biết giá tham khảo (đơn thật 24/10: báo 21.357đ, thật 12.157đ).
_PAID_BASIS = (
    "Shopee tính trên số tiền bạn thực trả, nên dùng voucher, xu hoặc mua lúc giảm giá thì tiền hoàn giảm theo."
)
_NOTE_V11 = (
    f"Số hoàn tính theo giá tham khảo. {_PAID_BASIS}\n"
    "Chỉ được hoàn khi Shopee xác nhận đơn hợp lệ. Chưa phải tiền có thể rút."
)
_NOTE_V12 = (
    f"Số hoàn tính theo giá tham khảo, sau dự phòng phí và thuế. {_PAID_BASIS}\n"
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
    # (tên file, nội dung): gửi kèm một file, ví dụ CSV đơn hàng cho admin.
    document: tuple[str, bytes] | None = None
    # (tên file, ảnh PNG, chú thích): gửi kèm một ảnh, ví dụ mã QR chuyển khoản.
    photo: tuple[str, bytes, str] | None = None

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
        f"💰 Hoàn dự kiến: khoảng <b>{format_vnd(cashback_vnd)}</b>\n\n"
        f"🛍️ {safe_name}\n"
        f"Giá tham khảo: {format_vnd(price_vnd)}\n\n"
        f"ⓘ {note}"
    )
    return BotReply(text=text, button_url=affiliate_url, inline_keyboard=TIP_KEYBOARD)


def home_reply(show_rank: bool = False, show_wallet: bool = False) -> BotReply:
    return BotReply(HOME_WALLET if show_wallet else HOME, inline_keyboard=home_keyboard(show_rank, show_wallet))


def page_reply(text: str) -> BotReply:
    return BotReply(text, inline_keyboard=PAGE_KEYBOARD)


def invalid_link_reply() -> BotReply:
    return BotReply(INVALID_LINK, inline_keyboard=GUIDE_KEYBOARD)


def render_success(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V11)


def render_success_v12(name: str, price_vnd: int, cashback_vnd: int, affiliate_url: str) -> BotReply:
    return _render_card(name, price_vnd, cashback_vnd, affiliate_url, _NOTE_V12)


# --- Ví hoàn tiền (PLAN-066) -------------------------------------------------

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
WALLET_CLOSED = (
    "👛 <b>Ví hoàn tiền chưa mở</b>\n"
    "Các khoản được ghi nhận đang chờ Shopee xác minh và đối soát; chưa thể yêu cầu rút."
)
WALLET_CLOSED_ALERT = "Ví hoàn tiền chưa mở."
WALLET_BACK: Keyboard = ((("◀️ Ví của tôi", "u:p:wallet"),),)
ENTRY_LABELS = {
    "pending": "Shopee đang xử lý",
    "holding": "Chờ duyệt",
    "available": "Đã vào ví",
    "cancelled": "Không được hoàn",
}
BANK_PICK = (
    "🏦 <b>Tài khoản nhận tiền</b>\n\n"
    "Bấm chọn ngân hàng của bạn.\n\n"
    "ⓘ Không thấy ngân hàng của bạn thì chưa hỗ trợ; bạn dùng một tài khoản ngân hàng khác nhé."
)
BANK_ERRORS = {
    "format": "Thiếu thông tin. Gửi số tài khoản rồi tới tên chủ tài khoản.",
    "bank": "Bạn bấm chọn ngân hàng trước, rồi gửi số tài khoản và tên.",
    "account": "Số tài khoản chỉ gồm 6–19 chữ số, đặt trước tên.",
    "name": "Tên chủ tài khoản chỉ gồm chữ cái và khoảng trắng, không có số.",
}
WITHDRAW_ERRORS = {
    "disabled": WALLET_CLOSED,
    "no_bank": "🏦 <b>Chưa có tài khoản nhận tiền</b>\nBấm Tài khoản nhận tiền để khai trước khi rút.",
    "pending_exists": "📤 <b>Bạn đang có một yêu cầu rút chờ chuyển</b>\nBot sẽ báo khi admin chuyển xong.",
    "below_min": "⏳ <b>Chưa đủ số tối thiểu để rút</b>\nTiền hoàn sẽ cộng dần khi đơn được duyệt.",
    # Khoá tài chính (hardening V1): chưa có bằng chứng Shopee đã trả hoặc vượt số Shopee đã trả.
    "locked": "⏳ <b>Chưa mở rút tiền</b>\nBot chỉ chi khi Shopee đã duyệt và thanh toán hoa hồng. Tiền hoàn của bạn vẫn được ghi lại.",
    "fund": "⏳ <b>Chưa rút được lúc này</b>\nKỳ thanh toán Shopee chưa về đủ. Bot sẽ báo khi rút được.",
    # PLAN-078
    "terms": "📋 <b>Cần đồng ý điều khoản chi trả</b>\nMở /dieukien, đọc và bấm đồng ý bản hiện hành rồi rút lại.",
    "insufficient": "⏳ <b>Số tiền vượt số đang rút được</b>\nMở lại ví để xem số rút được.",
    "limits_missing": "⏳ <b>Chưa mở rút tiền</b>\nHạn mức rút chưa được duyệt.",
    "over_request_limit": "⏳ <b>Vượt hạn mức một lần rút</b>\nThử rút số nhỏ hơn hoặc nhắn /hotro.",
    "over_daily_limit": "⏳ <b>Hôm nay đã hết hạn mức chi của bot</b>\nBạn thử lại vào ngày mai nhé.",
    "over_monthly_limit": "⏳ <b>Tháng này đã hết hạn mức chi của bot</b>\nBot sẽ báo khi rút được.",
}
PAYOUT_CUSTOMER_STATUS = {
    "requested": "đã gửi, chờ kiểm tra",
    "under_review": "đang kiểm tra",
    "approved_for_payment": "đã duyệt, chờ chuyển",
    "processing": "đang chuyển",
    "sent_unconfirmed": "đã chuyển, chờ ngân hàng xác nhận",
    "needs_review": "cần kiểm tra thêm",
}


def vn_date(stamp: str | None) -> str:
    if not stamp:
        return "-"
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return stamp
    return moment.astimezone(ICT).strftime("%d/%m/%Y")


def _entry_line(entry) -> str:
    label = ENTRY_LABELS.get(entry["status"], entry["status"])
    if entry["status"] == "holding" and entry["available_at"]:
        label = f"Chờ duyệt tới {vn_date(entry['available_at'])}"
    return f"• {html.escape(buyer_name(entry['item_name'] or '-'))} · <b>{format_vnd(int(entry['cashback_vnd']))}</b> · {label}"


def wallet_reply(settings, balance, entries, bank, open_request, notice: str = "") -> BotReply:
    """settings, balance, bank: kiểu trong wallet.py; entries, open_request: dòng SQLite."""
    withdrawable = max(0, balance.withdrawable_vnd)
    lines = ["👛 <b>Ví hoàn tiền</b>", ""]
    if notice:
        lines += [notice, ""]
    lines += [
        f"✅ Có thể rút: <b>{format_vnd(withdrawable)}</b>",
        f"⏳ Đang chờ Shopee xác minh: <b>{format_vnd(balance.pending_vnd - balance.held_vnd)}</b>",
        f"🔒 Đang giữ, chờ đủ điều kiện: <b>{format_vnd(balance.held_vnd)}</b>",
        f"💸 Đã nhận: <b>{format_vnd(balance.paid_vnd)}</b>",
    ]
    if open_request is not None:
        label = PAYOUT_CUSTOMER_STATUS.get(open_request["status"], open_request["status"])
        lines.append(f"📤 Đang xử lý rút: <b>{format_vnd(int(open_request['amount_vnd']))}</b> · {label}")
    lines += ["", "🧾 <b>Đơn gần đây</b>"]
    lines += [_entry_line(entry) for entry in entries] or ["Chưa có đơn nào qua link của bạn."]
    lines += ["", f"🏦 Nhận tiền: {html.escape(bank.masked)}" if bank else "🏦 Chưa khai tài khoản nhận tiền."]
    lines += [
        "",
        f"ⓘ Tiền vào ví {settings.hold_days} ngày sau khi đơn hoàn thành. Rút từ {format_vnd(settings.min_withdraw_vnd)}.",
    ]
    rows: list[tuple[tuple[str, str], ...]] = []
    if open_request is None and bank and withdrawable >= settings.min_withdraw_vnd:
        rows.append(((f"💸 Rút {format_vnd(withdrawable)}", "u:w:out"),))
    rows.append((("🏦 Tài khoản nhận tiền", "u:w:bank"),))
    rows.append((("◀️ Trang chủ", "u:p:home"),))
    return BotReply("\n".join(lines), inline_keyboard=tuple(rows))


def bank_pick_reply(banks: dict[str, tuple[str, str]], notice: str = "") -> BotReply:
    """banks: wallet.BANKS. Ba ngân hàng một hàng."""
    buttons = [(name, f"u:w:bk:{code}") for code, (_bin, name) in banks.items()]
    rows = [tuple(buttons[i : i + 3]) for i in range(0, len(buttons), 3)]
    text = f"⚠️ {notice}\n\n{BANK_PICK}" if notice else BANK_PICK
    return BotReply(text, inline_keyboard=(*rows, (("✖️ Hủy", "u:p:wallet"),)))


def bank_prompt_reply(bank_name: str, error: str | None = None) -> BotReply:
    text = (
        f"🏦 <b>{html.escape(bank_name)}</b>\n\n"
        "Gửi số tài khoản rồi tới tên chủ tài khoản, ví dụ:\n"
        "<code>0123456789 Nguyen Van A</code>\n\n"
        "ⓘ Tên phải đúng tên chủ tài khoản, nếu không ngân hàng sẽ trả tiền về."
    )
    if error is not None:
        text = f"⚠️ {BANK_ERRORS.get(error, BANK_ERRORS['format'])}\n\n{text}"
    return BotReply(text, inline_keyboard=((("🔁 Chọn ngân hàng khác", "u:w:bank"),), (("✖️ Hủy", "u:p:wallet"),)))


def withdraw_confirm_reply(amount_vnd: int, bank) -> BotReply:
    text = (
        "💸 <b>Xác nhận rút tiền</b>\n\n"
        f"Số tiền: <b>{format_vnd(amount_vnd)}</b>\n"
        f"Về: {html.escape(bank.masked)}\n"
        f"Chủ tài khoản: {html.escape(bank.account_name)}\n\n"
        "ⓘ Admin kiểm tra và chuyển khoản tay, bot báo khi ngân hàng xác nhận. Tài khoản cần được xác minh "
        "trước khi chuyển."
    )
    return BotReply(text, inline_keyboard=((("✅ Xác nhận rút", "u:w:out:ok"),), (("◀️ Ví của tôi", "u:p:wallet"),)))


def withdraw_done_reply(payout) -> BotReply:
    text = (
        "📤 <b>Đã gửi yêu cầu rút</b>\n\n"
        f"Số tiền: <b>{format_vnd(int(payout['amount_vnd']))}</b>\n"
        f"Mã yêu cầu: <code>{html.escape(payout['transfer_note'] or '')}</code>\n\n"
        "Bot sẽ báo khi admin chuyển xong."
    )
    return BotReply(text, inline_keyboard=WALLET_BACK)


def withdraw_error_reply(code: str) -> BotReply:
    return BotReply(WITHDRAW_ERRORS.get(code, WITHDRAW_ERRORS["below_min"]), inline_keyboard=WALLET_BACK)


def entry_notice(
    status: str,
    item_name: str,
    cashback_vnd: int,
    available_at: str | None,
    hold_days: int,
    estimated_vnd: int | None = None,
) -> str:
    """Tin báo khách khi đơn đổi trạng thái. estimated_vnd: số đã báo lúc tạo link."""
    item = html.escape(buyer_name(item_name or "-"))
    if status == "pending":
        lower = ""
        if estimated_vnd and cashback_vnd < estimated_vnd:
            lower = (
                f"Lúc tạo link bot báo khoảng {format_vnd(estimated_vnd)} theo giá tham khảo. "
                f"Shopee tính lại trên số tiền bạn thực trả (sau voucher, xu, giảm giá) nên còn {format_vnd(cashback_vnd)}.\n\n"
            )
        return (
            "🛒 <b>Có đơn mới qua link của bạn</b>\n\n"
            f"🛍️ {item}\n💰 Hoàn tạm tính: <b>{format_vnd(cashback_vnd)}</b>\n\n"
            + lower
            + "ⓘ Shopee đang xử lý đơn. Số hoàn chốt khi đơn hoàn thành, bot sẽ báo tiếp."
        )
    if status == "holding":
        return (
            "✅ <b>Đơn đã hoàn thành</b>\n\n"
            f"🛍️ {item}\n💰 Hoàn: <b>{format_vnd(cashback_vnd)}</b>\n\n"
            "ⓘ Tiền vào ví khi Shopee duyệt và thanh toán hoa hồng cho đơn này. Bot sẽ báo khi vào ví."
        )
    if status == "available":
        return (
            "💰 <b>Tiền hoàn đã vào ví</b>\n\n"
            f"🛍️ {item}\n+<b>{format_vnd(cashback_vnd)}</b>\n\n"
            "Gõ /vi để xem số dư và rút tiền."
        )
    return (
        "❌ <b>Đơn không được hoàn</b>\n\n"
        f"🛍️ {item}\n"
        "Đơn bị huỷ hoặc trả hàng nên Shopee không trả hoa hồng."
    )


def payout_notice(payout, paid: bool) -> str:
    amount = format_vnd(int(payout["amount_vnd"]))
    if paid:
        return (
            "💸 <b>Đã chuyển tiền hoàn</b>\n\n"
            f"Số tiền: <b>{amount}</b>\n"
            f"Nội dung: <code>{html.escape(payout['transfer_note'] or '')}</code>\n\n"
            "Bạn kiểm tra tài khoản giúp mình nhé."
        )
    return (
        "⚠️ <b>Yêu cầu rút chưa được duyệt</b>\n\n"
        f"Số tiền {amount} đã trở lại ví. Bạn kiểm tra lại tài khoản nhận tiền rồi rút lại, "
        "hoặc nhắn admin để biết lý do."
    )


# --- Điều khoản theo phiên bản (PLAN-077) ---------------------------------------------------------

def _vn_stamp(stamp: str | None) -> str:
    if not stamp:
        return "-"
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return moment.astimezone(ICT).strftime("%d/%m/%Y")


def terms_home_reply(version, accepted_at: str | None) -> BotReply:
    """/dieukien khi có bản điều khoản đang công bố. Xem không phải đồng ý: nút đồng ý tách riêng."""
    lines = [
        f"📋 <b>{html.escape(version.title)}</b>",
        f"Phiên bản <b>{html.escape(version.version)}</b> · hiệu lực từ {_vn_stamp(version.effective_from)}",
        "",
        "Bấm từng mục để đọc. " + (
            f"✅ Bạn đã đồng ý phiên bản này ngày {_vn_stamp(accepted_at)}."
            if accepted_at
            else "Bạn chưa xác nhận phiên bản này. Đọc xong, nếu đồng ý thì bấm nút cuối."
        ),
        "",
        "ⓘ Ví hoàn tiền và chi trả chưa mở. Số hoàn trên link là dự kiến.",
    ]
    rows: list[tuple[tuple[str, str], ...]] = [((label, f"u:t:s:{key}"),) for key, label, _body in version.sections]
    if not accepted_at:
        rows.append((("✅ Tôi đã đọc và đồng ý", f"u:t:ok:{version.id}"),))
    rows.append((("📩 Hỗ trợ", "u:p:support"), ("◀️ Trang chủ", "u:p:home")))
    return BotReply("\n".join(lines), inline_keyboard=tuple(rows))


def terms_section_reply(version, key: str) -> BotReply | None:
    found = version.section(key)
    if found is None:
        return None
    _key, label, body = found
    text = f"<b>{html.escape(label)}</b> · phiên bản {html.escape(version.version)}\n\n{body}"
    return BotReply(text, inline_keyboard=((("◀️ Điều khoản", "u:p:rules"),),))


TERMS_REQUIRED = (
    "📋 <b>Cần xác nhận điều khoản</b>\n"
    "Trước khi tạo link mới, bạn đọc điều khoản hiện hành và bấm đồng ý.\n"
    "Đơn và yêu cầu hỗ trợ cũ của bạn vẫn xem được bình thường."
)


# --- Hỗ trợ và khiếu nại (PLAN-077) ---------------------------------------------------------------

SUPPORT_HOME = (
    "📩 <b>Hỗ trợ và khiếu nại</b>\n\n"
    "Chọn vấn đề, rồi mô tả ngắn gọn. Nếu có, ghi kèm mã đơn Shopee hoặc mã theo dõi của link "
    "(8 ký tự, ví dụ trong tin bot gửi).\n\n"
    "ⓘ Bot không bao giờ hỏi mật khẩu, OTP, cookie Shopee hay thông tin thẻ. Đừng gửi những thông tin này."
)
SUPPORT_ASK = (
    "✍️ <b>{category}</b>\n\n"
    "Gửi một tin mô tả vấn đề (tối đa 1.000 ký tự): bạn mua gì, khoảng ngày nào, mã đơn nếu có.\n"
    "Bot chờ trong 15 phút."
)
SUPPORT_REPLY_ASK = "✍️ <b>Bổ sung cho yêu cầu #{ticket}</b>\nGửi một tin (tối đa 1.000 ký tự). Bot chờ trong 15 phút."
SUPPORT_EMPTY = "Chưa đọc được nội dung. Gửi lại một tin bằng chữ nhé."
SUPPORT_CLOSED = "Yêu cầu này đã kết thúc. Nếu cần, bạn mở yêu cầu mới trong /hotro."


def support_home_reply(categories: dict[str, str], has_tickets: bool, notice: str = "") -> BotReply:
    rows = [((label, f"u:h:c:{code}"),) for code, label in categories.items()]
    if has_tickets:
        rows.append((("🗂 Yêu cầu của tôi", "u:h:mine"),))
    rows.append((("◀️ Trang chủ", "u:p:home"),))
    text = (f"{notice}\n\n" if notice else "") + SUPPORT_HOME
    return BotReply(text, inline_keyboard=tuple(rows))


def support_prompt_reply(text: str) -> BotReply:
    return BotReply(text, inline_keyboard=((("✖️ Hủy", "u:p:support"),),))


def support_created_reply(ticket, status_label: str, is_new: bool) -> BotReply:
    head = "✅ <b>Đã nhận yêu cầu</b>" if is_new else "ℹ️ <b>Yêu cầu này đã được ghi trước đó</b>"
    text = (
        f"{head} #{ticket.id}\n"
        f"Trạng thái: {status_label}\n\n"
        "Người vận hành sẽ kiểm tra và trả lời qua bot. Việc phụ thuộc Shopee có thể mất thời gian; "
        "bot chưa cam kết thời hạn cụ thể."
    )
    return BotReply(text, inline_keyboard=((("🗂 Yêu cầu của tôi", "u:h:mine"), ("◀️ Trang chủ", "u:p:home")),))


def support_list_reply(tickets, categories: dict[str, str], statuses: dict[str, str]) -> BotReply:
    if not tickets:
        return BotReply("🗂 Bạn chưa có yêu cầu nào.", inline_keyboard=((("◀️ Hỗ trợ", "u:p:support"),),))
    lines = ["🗂 <b>Yêu cầu của tôi</b> (5 gần nhất)", ""]
    rows = []
    for ticket in tickets:
        lines.append(f"#{ticket.id} · {categories.get(ticket.category, ticket.category)} · {statuses.get(ticket.status, ticket.status)}")
        rows.append(((f"#{ticket.id} · {statuses.get(ticket.status, ticket.status)}", f"u:h:t:{ticket.id}"),))
    rows.append((("◀️ Hỗ trợ", "u:p:support"),))
    return BotReply("\n".join(lines), inline_keyboard=tuple(rows))


def support_ticket_reply(ticket, categories, statuses, replies: list[tuple[str, str]], can_reply: bool) -> BotReply:
    """replies: (người nói, nội dung) đã làm sạch; chỉ gồm trao đổi với chính khách này."""
    lines = [
        f"🎫 <b>Yêu cầu #{ticket.id}</b>",
        f"{categories.get(ticket.category, ticket.category)} · {statuses.get(ticket.status, ticket.status)}",
        f"Gửi ngày {_vn_stamp(ticket.created_at)}",
        "",
        f"<i>{html.escape(ticket.message[:400])}</i>",
    ]
    if ticket.resolution:
        lines += ["", f"Kết luận: {html.escape(ticket.resolution)}"]
    for who, text in replies[-4:]:
        lines += ["", f"<b>{who}:</b> {html.escape(text[:400])}"]
    rows = []
    if can_reply:
        rows.append((("✍️ Bổ sung thông tin", f"u:h:r:{ticket.id}"),))
    rows.append((("🗂 Yêu cầu của tôi", "u:h:mine"), ("◀️ Trang chủ", "u:p:home")))
    return BotReply("\n".join(lines), inline_keyboard=tuple(rows))


# --- Đơn hàng và thông báo đơn (PLAN-079) ------------------------------------------------------
# Tách bạch: người mua thanh toán đơn ≠ Shopee duyệt hoa hồng ≠ Shopee thanh toán hoa hồng ≠ bot chuyển tiền hoàn.

ORDER_STATUS_LABELS = {
    "UNPAID": "Người mua chưa thanh toán đơn",
    "PENDING": "Đơn đang được xử lý",
    "PAID": "Người mua đã thanh toán đơn",
    "COMPLETED": "Đơn hàng đã hoàn thành",
    "CANCELLED": "Đơn đã huỷ",
    "CANCELED": "Đơn đã huỷ",
}
COMMISSION_LABELS = {
    "APPROVED": "Hoa hồng đã được Shopee duyệt",
    "REJECTED": "Không đủ điều kiện hoa hồng",
    "FRAUD": "Không đủ điều kiện hoa hồng",
    "NEEDS_REVIEW": "Đang được kiểm tra thêm",
}
COMMISSION_WAITING = "Hoa hồng đang chờ Shopee xác minh"
SETTLED_LABEL = "Shopee đã thanh toán hoa hồng cho chương trình"
NOT_SETTLED_LABEL = "Chưa có xác nhận Shopee thanh toán hoa hồng"
NOT_WITHDRAWABLE = "Chưa phải tiền có thể rút: ví hoàn tiền chưa mở."
ORDERS_EMPTY = (
    "📦 <b>Đơn hàng của tôi</b>\n\n"
    "Hiện Shopee chưa ghi nhận giao dịch nào khớp với các link bạn đã tạo.\n\n"
    "Dữ liệu đơn có thể cập nhật muộn. Nếu cần kiểm tra, hãy gửi yêu cầu tại /hotro."
)


def order_status_label(status: str | None) -> str:
    return ORDER_STATUS_LABELS.get((status or "").upper(), "Chưa rõ tình trạng đơn")


def commission_label(validation: str | None, order_status: str | None = None) -> str:
    if (order_status or "").upper() in ("CANCELLED", "CANCELED"):
        return "Không đủ điều kiện hoa hồng"
    return COMMISSION_LABELS.get(validation or "", COMMISSION_WAITING)


def _cashback_line(amount: int | None) -> str:
    return f"Hoàn tạm tính: <b>{format_vnd(amount)}</b>" if amount is not None else "Hoàn tạm tính: chưa xác định được"


def order_new_notice(order: str, cashback: int | None, order_status: str | None, validation: str | None) -> str:
    return (
        "📦 <b>Đã ghi nhận giao dịch</b>\n\n"
        "Shopee vừa ghi nhận một giao dịch qua link bạn đã tạo.\n\n"
        f"Mã đơn: {order}\n"
        f"Tình trạng đơn: {order_status_label(order_status)}\n"
        f"{_cashback_line(cashback)}\n"
        f"{commission_label(validation, order_status)}.\n\n"
        "ⓘ Đây là số tạm tính, có thể thay đổi. Chưa phải tiền có thể rút."
    )


def order_update_notice(order: str, *, statuses: list[str], ineligible: bool, approved: bool,
                        old_cashback: int | None, new_cashback: int | None) -> str:
    """Một tin cho mọi thay đổi có ý nghĩa của một đơn trong một lần đồng bộ, tiêu đề theo việc quan trọng nhất."""
    cancelled = any(s in ("CANCELLED", "CANCELED") for s in statuses)
    if ineligible:
        title = "⚠️ <b>Giao dịch không đủ điều kiện</b>"
        body = "Shopee đã ghi nhận trạng thái không đủ điều kiện hoa hồng. Hoàn của đơn này hiện không được tính để chi trả."
    elif cancelled:
        title = "⚠️ <b>Đơn đã huỷ</b>"
        body = "Shopee ghi nhận đơn đã huỷ, nên hoàn của đơn này không được tính."
    elif approved:
        title = "✅ <b>Hoa hồng đã được Shopee duyệt</b>"
        body = "Shopee chưa thanh toán hoa hồng này cho chương trình; bot sẽ báo tiếp."
    elif new_cashback is not None:
        title = "💰 <b>Hoàn dự kiến được cập nhật</b>"
        body = "Shopee đã điều chỉnh hoa hồng ghi nhận. Khoản hoàn vẫn đang chờ xác minh."
    else:
        title = "📦 <b>Cập nhật đơn hàng</b>"
        body = COMMISSION_WAITING + "."
    lines = [title, "", f"Mã đơn: {order}"]
    lines += [f"• {order_status_label(s)}" for s in statuses]
    if new_cashback is not None and old_cashback is not None:
        lines.append(f"• Hoàn tạm tính: {format_vnd(old_cashback)} → <b>{format_vnd(new_cashback)}</b>")
    lines += ["", body]
    if ineligible or cancelled:
        lines.append("Nếu bạn cần kiểm tra thêm, hãy dùng /hotro.")
    lines += ["", "ⓘ " + NOT_WITHDRAWABLE]
    return "\n".join(lines)


ORDERS_KEYBOARD_BACK = (("◀️ Trang chủ", "u:p:home"),)


def orders_summary_reply(stats: dict, rows, page: int, pages: int) -> BotReply:
    """stats: tổng, chờ, duyệt, không đủ điều kiện, hoàn tạm tính. rows: đơn của trang (mới trước)."""
    lines = [
        "📦 <b>Đơn hàng của tôi</b>",
        "",
        f"Shopee đã ghi nhận: <b>{stats['total']}</b> đơn",
        f"⏳ Chờ xác minh: {stats['waiting']} · ✅ Đã được duyệt: {stats['approved']} · ❌ Không đủ điều kiện: {stats['ineligible']}",
        f"Hoàn tạm tính (đơn còn chờ): <b>{format_vnd(stats['estimated'])}</b>" if stats["estimated"] else "Hoàn tạm tính: chưa có",
        "Chưa có khoản nào đủ điều kiện rút." if not stats.get("available") else "",
        "",
    ]
    for row in rows:
        lines.append(
            f"• {row['order']} · {row['date']} · {order_status_label(row['order_status'])} · "
            f"{commission_label(row['validation_status'], row['order_status'])}"
            + (f" · {format_vnd(row['cashback'])}" if row["cashback"] is not None else "")
        )
    if pages > 1:
        lines += ["", f"Trang {page}/{pages}"]
    keyboard: list[tuple[tuple[str, str], ...]] = [((f"🔎 {row['order']}", f"u:o:d:{row['conversion_id']}"),) for row in rows]
    nav = []
    if page > 1:
        nav.append(("◀️ Mới hơn", f"u:o:l:{page - 1}"))
    if page < pages:
        nav.append(("Cũ hơn ▶️", f"u:o:l:{page + 1}"))
    if nav:
        keyboard.append(tuple(nav))
    keyboard.append((("🔔 Thông báo", "u:p:notify"), ("◀️ Trang chủ", "u:p:home")))
    return BotReply("\n".join(line for line in lines if line is not None), inline_keyboard=tuple(keyboard))


def order_detail_reply(row: dict) -> BotReply:
    """row đã chỉ gồm dữ liệu của chính khách. Không có raw Shopee, không có thông tin người mua."""
    lines = [
        f"📦 <b>Đơn {row['order']}</b>",
        "",
        f"Bot ghi nhận: {row['date']}",
        f"Link của bạn: <code>{html.escape(row['sub_id'] or '-')}</code> · cách tính {html.escape(row['policy'])}",
        f"Tình trạng đơn: {order_status_label(row['order_status'])}",
        f"{commission_label(row['validation_status'], row['order_status'])}",
        SETTLED_LABEL if row["settlement_status"] == "SETTLED" else NOT_SETTLED_LABEL,
        _cashback_line(row["cashback"]),
        "",
        "ⓘ " + NOT_WITHDRAWABLE + " Số tạm tính có thể đổi khi Shopee điều chỉnh hoa hồng hoặc đơn bị huỷ, trả hàng.",
    ]
    keyboard = (
        (("📩 Yêu cầu kiểm tra", "u:h:c:amount"),),
        (("◀️ Đơn hàng của tôi", "u:o:l:1"), ("◀️ Trang chủ", "u:p:home")),
    )
    return BotReply("\n".join(lines), inline_keyboard=keyboard)


NOTIFY_OPTIONS = (
    ("orders", "📦 Đơn mới được ghi nhận"),
    ("updates", "🔄 Trạng thái đơn / hoa hồng thay đổi"),
    ("support", "📩 Trả lời yêu cầu hỗ trợ"),
    ("wallet", "👛 Ví và chi trả (khi ví mở)"),
)


def notify_settings_reply(prefs: dict, orders_live: bool, notice: str = "") -> BotReply:
    lines = ["🔔 <b>Cài đặt thông báo</b>", ""]
    if notice:
        lines += [notice, ""]
    lines += [f"{'✅' if prefs[key] else '⬜'} {label}" for key, label in NOTIFY_OPTIONS]
    lines += [
        "",
        "Bấm để bật / tắt. Chỉ áp dụng cho tài khoản của bạn.",
        "" if orders_live else "ⓘ Bot chưa bật gửi thông báo đơn hàng tự động. Bạn vẫn xem đơn ở /donhang.",
    ]
    keyboard = tuple(((f"{'✅' if prefs[key] else '⬜'} {label}", f"u:n:t:{key}"),) for key, label in NOTIFY_OPTIONS)
    keyboard += ((("📦 Đơn hàng của tôi", "u:o:l:1"), ("◀️ Trang chủ", "u:p:home")),)
    return BotReply("\n".join(lines).rstrip(), inline_keyboard=keyboard)
