"""Nút /admin (inline keyboard). Chỉ dựng nút, không đọc DB, không tính tiền."""

from __future__ import annotations

from cashback_bot.admin.ui.glossary import STATS_PERIODS, STEP_CODES, STEP_LABELS
from cashback_bot.admin.ui.views import _limit_vnd, _who_short, short_vnd
from cashback_bot.money import format_vnd

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

HOME_TARGET = "c:menu:home"
BACK_HOME = (("◀️ Tổng quan", HOME_TARGET),)

# Rà soát 2026-10-26 (đợt 4): việc hằng ngày ở trang chủ; đơn & hoa hồng và cài đặt gom vào hai menu con.
MENU_KEYBOARD: Keyboard = (
    (("💹 Dòng tiền", "c:in:m:30d"), ("📈 Tăng trưởng", "c:in:g:30d"), ("🎯 Mục tiêu", "c:in:t")),
    (("👥 Khách hàng", "c:in:u:margin:1"), ("🔍 Tìm", "c:in:f"), ("📩 Hỗ trợ", "c:hp:home")),
    (("🧾 Đơn & hoa hồng", "c:menu:orders"),),
    (("🛒 Shopee", "c:menu:shopee"), ("🎵 TikTok", "c:tk:home"), ("👛 Ví khách", "c:menu:wallet")),
    (("🛠 Vận hành", "c:in:o"), ("⚙️ Cài đặt", "c:menu:settings")),
)
ORDERS_MENU_KEYBOARD: Keyboard = (
    (("🧾 Duyệt hoa hồng", "c:cv:home"),),
    (("💳 Đối soát thanh toán", "c:sm:home"), ("🔎 Đơn cần đối soát", "c:rc:home")),
    (("🗓 Thống kê Shopee 7 ngày", "c:st:7d"),),
    BACK_HOME,
)
SETTINGS_MENU_KEYBOARD: Keyboard = (
    (("💰 Chính sách", "c:menu:policy"), ("🧾 Thuế & phí", "c:menu:fee")),
    (("🧪 Mô phỏng", "c:menu:sim"), ("🧮 Hoà vốn", "c:in:b")),
    (("🎖️ Hạng thành viên", "c:menu:rank"), ("📋 Điều khoản", "c:tm:home")),
    (("🔔 Thông báo khách", "c:nt:home"), ("⚖️ Sẵn sàng chi trả", "c:rd:home")),
    (("📊 Lịch sử cấu hình", "c:menu:hist"), ("📝 Nội dung lệnh", "c:menu:copy")),
    (("📣 Nhắc mùa sale", "c:eg:home"), ("📖 Thuật ngữ", "c:menu:glossary")),
    BACK_HOME,
)

NAV_KEYBOARD: Keyboard = (BACK_HOME,)

def shopee_connected_keyboard() -> Keyboard:
    # PLAN-080: bật tự đồng bộ do chủ bot đặt trong .env; ở đây chỉ xem lịch, lịch sử, tạm dừng / tiếp tục.
    return (
        (("🔄 Đồng bộ ngay", "c:shopee:sync"), ("📤 CSV 30 ngày", "c:shopee:csv")),
        (("🧾 Duyệt hoa hồng", "c:cv:home"), ("💳 Đối soát thanh toán", "c:sm:home")),
        (("⏱ Tự động đồng bộ", "c:sy:home"), ("🔎 Đơn cần đối soát", "c:rc:home")),
        (("🔑 Cập nhật Cookie", "c:shopee:auth"),),
        BACK_HOME,
    )

SHOPEE_KEYBOARD_DISCONNECTED: Keyboard = (
    (("🔑 Kết nối Cookie", "c:shopee:auth"),),
    # Duyệt / đối soát / lịch đồng bộ đọc dữ liệu đã có, không cần cookie: vẫn mở được khi cookie hết hạn.
    (("🧾 Duyệt hoa hồng", "c:cv:home"), ("💳 Đối soát thanh toán", "c:sm:home")),
    (("⏱ Tự động đồng bộ", "c:sy:home"), ("🔎 Đơn cần đối soát", "c:rc:home")),
    BACK_HOME,
)

SHOPEE_PROMPT_KEYBOARD: Keyboard = (
    (("✖️ Hủy", "c:menu:shopee"),),
)

RANK_KEYBOARD: Keyboard = (
    (("🥉 Đồng", "c:tier:BRONZE"), ("🥈 Bạc", "c:tier:SILVER"), ("🥇 Vàng", "c:tier:GOLD")),
    BACK_HOME,
)

POLICY_KEYBOARD: Keyboard = (
    (("✏️ Đổi tỷ lệ chia", "c:sh:new"),),
    BACK_HOME,
)

FEE_KEYBOARD: Keyboard = (
    (("✏️ Đổi mức áp dụng", "c:rs:new"),),
    BACK_HOME,
)


def collecting_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return ((("✖️ Hủy bản nháp", f"c:no:{draft_id}:{nonce}"),),)


def decision_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return (
        (("✖️ Hủy", f"c:no:{draft_id}:{nonce}"), ("✅ Xác nhận lưu", f"c:ok:{draft_id}:{nonce}")),
    )


def simulation_keyboard(amounts: tuple[int, ...], current: int) -> Keyboard:
    row = tuple((f"{'• ' if amount == current else ''}{short_vnd(amount)}", f"c:sim:{amount}") for amount in amounts)
    return (row, (("✏️ Nhập số khác", "c:sim:input"),), BACK_HOME)


SIM_PROMPT_KEYBOARD: Keyboard = ((("✖️ Hủy", "c:menu:sim"),),)


def with_rows(base: Keyboard, buttons: list[tuple[str, str]]) -> Keyboard:
    """Chèn mỗi nút một hàng, ngay trên hàng ◀️ cuối của bàn phím có sẵn."""
    if not buttons:
        return base
    return base[:-1] + tuple(((label, data),) for label, data in buttons) + base[-1:]


def _rs(draft_id: int, nonce: str, action: str, prefix: str = "rs") -> str:
    return f"c:{prefix}:{draft_id}:{nonce}:{action}"


def reserve_kind_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return (
        (("👤 Cá nhân", _rs(draft_id, nonce, "k:P")),),
        (("🧾 Cá nhân kinh doanh", _rs(draft_id, nonce, "k:I")),),
        (("🏪 Hộ kinh doanh", _rs(draft_id, nonce, "k:H")),),
        (("✖️ Hủy", _rs(draft_id, nonce, "no")),),
    )


def reserve_keep_keyboard(draft_id: int, nonce: str, current: str) -> Keyboard:
    return (
        ((f"Giữ {current}", _rs(draft_id, nonce, "keep")),),
        (("✖️ Hủy", _rs(draft_id, nonce, "no")),),
    )


def reserve_when_keyboard(draft_id: int, nonce: str, prefix: str = "rs") -> Keyboard:
    return (
        (
            ("⚡ Ngay bây giờ", _rs(draft_id, nonce, "w:now", prefix)),
            ("🌙 00:00 ngày mai", _rs(draft_id, nonce, "w:tmr", prefix)),
        ),
        (("✖️ Hủy", _rs(draft_id, nonce, "no", prefix)),),
    )


def reserve_decision_keyboard(draft_id: int, nonce: str, prefix: str = "rs") -> Keyboard:
    return (
        (
            ("✖️ Hủy", _rs(draft_id, nonce, "no", prefix)),
            ("✅ Áp dụng cho khách", _rs(draft_id, nonce, "ok", prefix)),
        ),
    )


def share_cancel_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return ((("✖️ Hủy", _rs(draft_id, nonce, "no", "sh")),),)


def stats_keyboard(current: str, detail: bool = False) -> Keyboard:
    """Tổng quan ↔ 🔎 Chi tiết; đổi kỳ thì ở nguyên màn đang xem."""
    suffix = ":more" if detail else ""
    row = tuple((f"• {label}" if key == current else label, f"c:st:{key}{suffix}") for key, label in STATS_PERIODS)
    switch = ("◀️ Về thống kê", f"c:st:{current}") if detail else ("🔎 Chi tiết", f"c:st:{current}:more")
    return (row, (switch, ("🖼 Ảnh đăng bài", "c:pb:home")), BACK_HOME)


# --- 👛 Ví khách (PLAN-066) ---------------------------------------------------

WALLET_ADMIN_BACK = (("◀️ Ví khách", "c:menu:wallet"),)


def wallet_admin_keyboard(settings, requests) -> Keyboard:
    rows: list[tuple[tuple[str, str], ...]] = [
        ((f"📤 {row['transfer_note'] or row['id']} · {format_vnd(int(row['amount_vnd']))} · "
          f"{_who_short(int(row['telegram_user_id']), row['username'])}", f"c:wl:rq:{row['id']}"),)
        for row in requests
    ]
    rows.append((("👥 Thành viên", "c:wl:members"), ("⚙️ Cài đặt", "c:wl:cfg")))
    if settings.enabled:
        rows.append((("⏸️ Tắt ví", "c:wl:off"),))
    elif settings.locked_reasons:
        rows.append((("🔒 Bật ví (đang khoá)", "c:wl:on"),))
    else:
        rows.append((("🟢 Bật ví cho khách", "c:wl:on"),))
    rows.append(BACK_HOME)
    return tuple(rows)
WALLET_ENABLE_KEYBOARD: Keyboard = ((("✅ Bật ví", "c:wl:on:ok"),), WALLET_ADMIN_BACK)


def wallet_settings_keyboard(settings, hold_choices, min_choices, limits=None, limit_choices=None) -> Keyboard:
    hold = tuple((("• " if d == settings.hold_days else "") + f"{d} ngày", f"c:wl:hold:{d}") for d in hold_choices)
    low = tuple(
        (("• " if v == settings.min_withdraw_vnd else "") + short_vnd(v), f"c:wl:min:{v}") for v in min_choices
    )
    rows = [hold, low]
    if limits is not None and limit_choices:
        for key, unit, current in (
            ("req", "lần", limits.max_per_request_vnd),
            ("day", "ngày", limits.daily_total_vnd),
            ("month", "tháng", limits.monthly_total_vnd),
        ):
            rows.append(tuple(
                (("• " if v == current else "") + f"{_limit_vnd(v)}/{unit}", f"c:wl:lim:{key}:{v}")
                for v in limit_choices[key]
            ))
    return (*rows, WALLET_ADMIN_BACK)


def wallet_members_keyboard(members) -> Keyboard:
    buttons = [
        (_who_short(m["telegram_user_id"], m["username"])[:30], f"c:wl:u:{m['telegram_user_id']}") for m in members
    ]
    rows = [tuple(buttons[i : i + 2]) for i in range(0, len(buttons), 2)]
    return (*rows, WALLET_ADMIN_BACK)


def payout_keyboard(payout, targets: list[str], locked: bool) -> Keyboard:
    """Nút theo máy trạng thái. Bước đưa tiền ra bị ẩn khi còn khoá tài chính."""
    pid, version = payout["id"], payout["version"] or 1
    codes = {target: code for code, target in STEP_CODES.items()}
    money = {"approved_for_payment", "processing", "sent_unconfirmed", "paid_confirmed"}
    rows = [
        ((STEP_LABELS[target], f"c:wl:mv:{pid}:{version}:{codes[target]}"),)
        for target in targets
        if not (locked and target in money)
    ]
    if locked and any(target in money for target in targets):
        rows.append((("🔒 Bước chi tiền đang khoá", f"c:wl:rq:{pid}"),))
    rows.append((("✅ Xác minh tài khoản người nhận", f"c:wl:vb:{pid}"),))
    rows.append(WALLET_ADMIN_BACK)
    return tuple(rows)
