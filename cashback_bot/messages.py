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
    "ⓘ Bot đang thử nghiệm. Số hoàn là ước tính, chưa theo dõi đơn và chưa chi trả."
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
    "Bot đang thử nghiệm: số hoàn là ước tính, chưa theo dõi đơn và chưa chi trả. "
    "Bot không thu phí sử dụng."
)
SHORT_DESCRIPTION = "Dán link Shopee, xem số tiền hoàn dự kiến. Bot đang thử nghiệm."


def home_keyboard(show_rank: bool = False, show_wallet: bool = False) -> Keyboard:
    second: tuple[tuple[str, str], ...] = (("💰 Cách tính", "u:p:calc"),)
    if show_rank:
        second += (("🏅 Hạng thành viên", "u:p:rank"),)
    rows: Keyboard = (
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
    ("help", "Trợ giúp"),
)
# Chỉ đăng ký với scope chat của từng admin.
ADMIN_COMMANDS = BOT_COMMANDS + (("admin", "Quản trị"),)
# Thêm vào menu lệnh lúc khởi động nếu ví đang bật (PLAN-066).
WALLET_COMMAND = ("vi", "Ví hoàn tiền")


def how_to_calc(v12: bool, wallet_hold_days: int | None = None, wallet_min_vnd: int | None = None) -> str:
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
        + "• Số trên link tính theo giá tham khảo. Shopee tính trên số tiền bạn thực trả "
        "(sau voucher, xu, giảm giá), nên số thật thường thấp hơn.\n"
        "• Hoa hồng có thể thay đổi, hoặc bằng 0 nếu đơn bị hủy, trả hàng hay không đủ điều kiện.\n"
        "• Số cuối chỉ được xác nhận khi Shopee đối soát xong.\n"
        "• Số dự kiến chưa phải tiền đã duyệt hay có thể rút.\n\n"
        + (
            "ⓘ Bot chưa theo dõi đơn và chưa chi trả."
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
WALLET_CLOSED = "👛 <b>Ví hoàn tiền chưa mở</b>\nBot sẽ báo khi bắt đầu theo dõi đơn và chi trả."
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
        f"⏳ Chờ duyệt: <b>{format_vnd(balance.pending_vnd)}</b>",
        f"💸 Đã nhận: <b>{format_vnd(balance.paid_vnd)}</b>",
    ]
    if open_request is not None:
        lines.append(f"📤 Đang chờ chuyển: <b>{format_vnd(int(open_request['amount_vnd']))}</b>")
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
        "ⓘ Admin chuyển khoản tay, bot báo khi chuyển xong."
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
            f"🛍️ {item}\n💰 Hoàn: <b>{format_vnd(cashback_vnd)}</b>\n"
            f"📅 Vào ví ngày: <b>{vn_date(available_at)}</b>\n\n"
            f"ⓘ Bot giữ {hold_days} ngày để Shopee đối soát xong."
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
