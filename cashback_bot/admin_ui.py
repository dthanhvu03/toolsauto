"""Câu chữ và nút /admin. Không tính tiền, số đã tính được truyền vào.

Nguyên tắc UX (PLAN-060):
1. Dòng đầu là breadcrumb "⚙️ Quản trị › Màn".
2. Màn cấp 1 có một nút "◀️ Tổng quan". Bước nhập số có nút Hủy bản nháp.
3. Không có nút kích hoạt chính sách cho khách.
4. Màn có tiền tách rõ "Đang áp dụng", "Bản nháp / Định hướng" và "Mô phỏng".
"""

from __future__ import annotations

from cashback_bot.money import format_vnd

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

HOME_TARGET = "c:menu:home"
BACK_HOME = (("◀️ Tổng quan", HOME_TARGET),)

MENU_KEYBOARD: Keyboard = (
    (("💰 Chính sách", "c:menu:policy"), ("🎖️ Hạng thành viên", "c:menu:rank")),
    (("🧾 Thuế & phí", "c:menu:fee"), ("🧮 Mô phỏng", "c:menu:sim")),
    (("📊 Lịch sử", "c:menu:hist"), ("📝 Nội dung lệnh", "c:menu:copy")),
)

NAV_KEYBOARD: Keyboard = (BACK_HOME,)

RANK_KEYBOARD: Keyboard = (
    (("🥉 Đồng", "c:tier:BRONZE"), ("🥈 Bạc", "c:tier:SILVER"), ("🥇 Vàng", "c:tier:GOLD")),
    BACK_HOME,
)

FEE_KEYBOARD: Keyboard = (
    (("🧾 Phí dự phòng", "c:tier:FEE"), ("🏛️ Thuế dự phòng", "c:tier:TAX")),
    BACK_HOME,
)


def collecting_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return ((("✖️ Hủy bản nháp", f"c:no:{draft_id}:{nonce}"),),)


def decision_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return (
        (("✖️ Hủy", f"c:no:{draft_id}:{nonce}"), ("✅ Xác nhận lưu", f"c:ok:{draft_id}:{nonce}")),
    )


def _title(*path: str) -> str:
    trail = " › ".join(("⚙️ Quản trị",) + path[:-1])
    return f"{trail} › <b>{path[-1]}</b>\n\n"


def _notice(text: str) -> str:
    return f"{text}\n\n" if text else ""


def home_text(
    *,
    rate_percent: int,
    membership_on: bool,
    calculator: str,
    pending: int | None,
) -> str:
    v12 = calculator == "V1.2"
    quote = f"V1.2 · {rate_percent}% sau dự phòng phí và thuế" if v12 else f"V1.1 · {rate_percent}% hoa hồng ước tính"
    pending_line = "không đọc được" if pending is None else str(pending)
    return (
        "⚙️ <b>Quản trị</b>\n\n"
        "🟢 <b>Khách đang nhận</b>\n"
        f"• Chính sách báo giá: {quote}\n"
        f"• Calculator V1.2: {'Đã bật' if v12 else 'Chưa bật'}\n"
        f"• Hạng thành viên: {'Đã bật' if membership_on else 'Chưa bật'}\n"
        "• Đối soát &amp; chi trả: Chưa mở\n\n"
        f"🟡 Bản nháp đang chờ: <b>{pending_line}</b>\n\n"
        "ⓘ Sửa cấu hình không đổi báo giá khách cho tới khi kích hoạt. "
        "Báo giá đã lưu không tự tính lại."
    )


def policy_text(
    *,
    rate_percent: int,
    pending: int | None,
    customer_vnd: int,
    remain_vnd: int,
) -> str:
    pending_line = "0 bản nháp" if not pending else f"{pending} bản nháp"
    return (
        _title("Chính sách")
        + "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        "• Phiên bản: <b>V1.1</b>\n"
        f"• Tỷ lệ: <b>{rate_percent}% hoa hồng ước tính</b>\n"
        "• Chưa trừ thuế và phí dự phòng khi báo giá\n"
        "• Áp dụng cho mọi link tạo mới\n\n"
        "🟡 <b>BẢN NHÁP</b>\n"
        f"• Đang chờ: <b>{pending_line}</b>\n"
        "• Trần an toàn V1: <b>70%</b>\n"
        "• Xác nhận chỉ lưu bản ghi, chưa đổi báo giá khách\n\n"
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ\n"
        f"• Khách nhận ({rate_percent}%): <b>{format_vnd(customer_vnd)}</b>\n"
        f"• Phần còn lại: <b>{format_vnd(remain_vnd)}</b>\n\n"
        "ⓘ Báo giá đã lưu không tự tính lại. Không có cam kết chi trả tự động."
    )


def rank_text(
    *,
    tiers: list[tuple[str, str, str, int, int]],
    displayed_rate_percent: int,
    notice: str = "",
) -> str:
    """tiers: (emoji, tên hạng, %, hoàn trên 100.000đ, phần còn)."""
    rates = "".join(f"• {emoji} {name}: <b>{percent}</b>\n" for emoji, name, percent, _c, _r in tiers)
    sims = "".join(
        f"• {name} {percent}: hoàn {format_vnd(cash)} · còn {format_vnd(rem)}\n"
        for _e, name, percent, cash, rem in tiers
    )
    return (
        _title("Hạng thành viên")
        + _notice(notice)
        + "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        f"• Chưa bật. Mọi khách dùng chung {displayed_rate_percent}%\n"
        "• Tiến độ lên hạng: chưa tính\n\n"
        "🟡 <b>BẢN NHÁP / ĐỊNH HƯỚNG</b> · chưa áp dụng cho khách\n"
        + rates
        + "Quy tắc: Đồng ≤ Bạc ≤ Vàng. Trần V1 là 70%.\n\n"
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ\n"
        + sims
        + "\nⓘ Chưa có dữ liệu đơn thật nên không có nút kích hoạt tự động.\n\n"
        "Chọn hạng để tạo bản nháp:"
    )


def fee_text(
    *,
    calculator_on: bool,
    applied_fee: str,
    applied_tax: str,
    fee_percent: str,
    fee_source: str,
    tax_percent: str,
    tax_source: str,
    sim_fee: int,
    sim_tax: int,
    sim_dist: int,
    notice: str = "",
) -> str:
    if calculator_on:
        applied = f"• Công thức khách: <b>V1.2</b>, trừ phí {applied_fee} và thuế {applied_tax} dự phòng\n\n"
    else:
        applied = "• Công thức khách: <b>V1.1</b>, chưa trừ phí và thuế dự phòng khi báo giá\n\n"
    return (
        _title("Thuế &amp; phí dự phòng")
        + _notice(notice)
        + "<i>ESTIMATE RESERVE</i>\n\n"
        "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        + applied
        + "🟡 <b>BẢN NHÁP DỰ PHÒNG</b>\n"
        f"• Phí dự phòng: <b>{fee_percent}</b> ({fee_source})\n"
        f"• Thuế dự phòng: <b>{tax_percent}</b> ({tax_source})\n"
        "Chỉ là dự phòng khi ước tính. Không phải thuế phải nộp, không sửa chứng từ đã đối soát.\n\n"
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ\n"
        f"• Phí dự phòng ({fee_percent}): -{format_vnd(sim_fee)}\n"
        f"• Thuế dự phòng ({tax_percent}): -{format_vnd(sim_tax)}\n"
        f"• Quỹ phân chia còn lại: <b>{format_vnd(sim_dist)}</b>\n\n"
        "ⓘ Không sửa số đã thanh toán. Bản nháp chưa đổi công thức khách.\n\n"
        "Chọn mục để tạo bản nháp:"
    )


def simulation_text(
    *,
    displayed_rate_percent: int,
    table: list[tuple[int, list[tuple[str, str, int, int]]]],
) -> str:
    """table: (quỹ, [(tên hạng, %, hoàn, phần còn)])."""
    lines = [
        _title("Mô phỏng").rstrip("\n"),
        "",
        "🟢 <b>ĐANG ÁP DỤNG CHO KHÁCH</b>",
        f"• Báo giá cố định: <b>{displayed_rate_percent}%</b> hoa hồng ước tính",
        "",
        "🔵 <b>MÔ PHỎNG THEO HẠNG</b>",
        "Thử trên quỹ giả định, không phải lợi nhuận và không phát sinh tiền phải trả.",
    ]
    for amount, rows in table:
        lines.append(f"\n<b>Quỹ {format_vnd(amount)}</b>")
        for name, percent, cash, rem in rows:
            lines.append(f"• {name} {percent}: hoàn {format_vnd(cash)} · còn {format_vnd(rem)}")
    lines.append("\nⓘ Mô phỏng không đổi số dư và không phát sinh nghĩa vụ.")
    return "\n".join(lines)


def history_text(rows: list[str] | None) -> str:
    """rows None: không đọc được database."""
    head = _title("Lịch sử cấu hình")
    if rows is None:
        return head + "Chưa đọc được lịch sử trên database đang chạy."
    if not rows:
        return head + "Chưa có thay đổi nào. Tạo bản nháp ở màn Hạng thành viên hoặc Thuế &amp; phí."
    return head + "\n".join(rows) + "\n\nⓘ 8 thao tác gần nhất, giờ Việt Nam."


def command_copy_text() -> str:
    return (
        _title("Nội dung lệnh")
        + "V1 chỉ cho xem danh sách lệnh. Chưa sửa câu chữ /huongdan hay /dieukien tại đây.\n\n"
        "<b>Lệnh khách đang thấy trong menu:</b>\n"
        "• <b>/start</b>, <b>/help</b> — Trang chủ có nút Cách dùng, Để được ghi nhận, Cách tính\n"
        "• <b>/huongdan</b> — Cách dùng 4 bước\n"
        "• <b>/dieukien</b> — Để đơn được ghi nhận\n"
        "• <b>/cachtinh</b> — Cách tính tiền hoàn dự kiến\n\n"
        "<b>Không có trong menu:</b>\n"
        "• <b>/hang</b> — Ẩn khi chưa bật hạng thành viên, gõ tay vẫn trả lời\n"
        "• <b>/admin</b> — Chỉ hiện trong menu của admin\n\n"
        "ⓘ Nội dung lệnh cố định trong mã nguồn, không chứa link thô hoặc cam kết chi trả."
    )


def collecting_text(*, draft_id: int, screen: str, subject: str, current: str, ask: str, note: str = "") -> str:
    return (
        _title(screen, f"Bản nháp #{draft_id}")
        + f"{subject} · đang lưu <b>{current}</b>\n"
        + f"{ask}\n\n"
        + _notice(note)
        + "Bản nháp tự hết hạn sau 10 phút."
    )


def rank_preview_text(
    *,
    tier_name: str,
    before: str,
    after: str,
    before_split: tuple[int, int],
    after_split: tuple[int, int],
) -> str:
    return (
        _title("Hạng thành viên", "Xem trước")
        + f"Hạng {tier_name}: {before} → <b>{after}</b>\n\n"
        "🔵 Mô phỏng quỹ phân chia 100.000đ. Không phải lợi nhuận.\n"
        f"• Trước: hoàn {format_vnd(before_split[0])}, phần còn {format_vnd(before_split[1])}\n"
        f"• Sau: hoàn {format_vnd(after_split[0])}, phần còn {format_vnd(after_split[1])}\n\n"
        "ⓘ Xác nhận chỉ lưu phiên bản, chưa kích hoạt cho khách. Báo giá đã lưu không tự tính lại."
    )


def reserve_preview_text(*, name: str, before: str, after: str) -> str:
    return (
        _title("Thuế &amp; phí dự phòng", "Xem trước")
        + f"{name}: {before} → <b>{after}</b>\n\n"
        "Nhãn: ESTIMATE RESERVE. Không phải thuế hoặc phí đã đối soát.\n\n"
        "ⓘ Không sửa số đã thanh toán. Xác nhận chưa đổi công thức khách."
    )
