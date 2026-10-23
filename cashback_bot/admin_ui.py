"""Câu chữ và nút /admin. Không tính tiền, số đã tính được truyền vào.

Nguyên tắc UX (PLAN-060):
1. Dòng đầu là breadcrumb "⚙️ Quản trị › Màn".
2. Màn cấp 1 có một nút "◀️ Tổng quan". Bước nhập số có nút Hủy bản nháp.
3. Không có nút kích hoạt chính sách cho khách.
4. Màn có tiền tách rõ "Đang áp dụng", "Bản nháp / Định hướng" và "Mô phỏng".
"""

from __future__ import annotations

import html

from cashback_bot.messages import buyer_name
from cashback_bot.money import format_vnd

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

HOME_TARGET = "c:menu:home"
BACK_HOME = (("◀️ Tổng quan", HOME_TARGET),)

MENU_KEYBOARD: Keyboard = (
    (("📈 Thống kê", "c:st:7d"),),
    (("🔗 Shopee Affiliate", "c:menu:shopee"), ("👛 Ví khách", "c:menu:wallet")),
    (("💰 Chính sách", "c:menu:policy"), ("🎖️ Hạng thành viên", "c:menu:rank")),
    (("🧾 Thuế & phí", "c:menu:fee"), ("🧮 Mô phỏng", "c:menu:sim")),
    (("📊 Lịch sử", "c:menu:hist"), ("📝 Nội dung lệnh", "c:menu:copy")),
)

NAV_KEYBOARD: Keyboard = (BACK_HOME,)

def shopee_connected_keyboard(auto_sync: bool) -> Keyboard:
    toggle = ("⏸️ Tắt tự đồng bộ", "c:shopee:auto:off") if auto_sync else ("🟢 Bật tự đồng bộ 4 giờ", "c:shopee:auto:on")
    return (
        (("🔄 Đồng bộ ngay", "c:shopee:sync"), ("📤 CSV 30 ngày", "c:shopee:csv")),
        (toggle,),
        (("🔑 Cập nhật Cookie", "c:shopee:auth"),),
        BACK_HOME,
    )

SHOPEE_KEYBOARD_DISCONNECTED: Keyboard = (
    (("🔑 Kết nối Cookie", "c:shopee:auth"),),
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


def _title(*path: str) -> str:
    trail = " › ".join(("⚙️ Quản trị",) + path[:-1])
    return f"{trail} › <b>{path[-1]}</b>\n\n"


def _notice(text: str) -> str:
    return f"{text}\n\n" if text else ""


def quote_label(rate_percent: int, v12: bool) -> str:
    if v12:
        return f"V1.2 · {rate_percent}% phần còn lại sau dự phòng phí và thuế"
    return f"V1.1 · {rate_percent}% hoa hồng ước tính"


def home_text(
    *,
    rate_percent: int,
    membership_on: bool,
    calculator: str,
    pending: int | None,
) -> str:
    v12 = calculator == "V1.2"
    quote = quote_label(rate_percent, v12)
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
    reserve: tuple[str, str, int, int] | None = None,
    since: str | None = None,
    upcoming: list[str] | None = None,
    warning: str = "",
    notice: str = "",
) -> str:
    """reserve (V1.2): (% phí, % thuế, tiền phí, tiền thuế) trên 100.000đ. None là V1.1.

    since: mốc tỷ lệ chia admin áp dụng (ADR-048); None là mặc định cấu hình.
    """
    pending_line = "0 bản nháp" if not pending else f"{pending} bản nháp"
    effect = f"• Hiệu lực tỷ lệ: {f'từ {since}' if since else 'mặc định cấu hình'}\n"
    if warning:
        effect += f"⚠️ {warning}\n"
    if upcoming:
        effect += "🗓️ Sắp áp dụng: " + "; ".join(upcoming) + "\n"
    if reserve is None:
        applied = (
            "• Phiên bản: <b>V1.1</b>\n"
            f"• Tỷ lệ: <b>{rate_percent}% hoa hồng ước tính</b>\n"
            "• Chưa trừ thuế và phí dự phòng khi báo giá\n"
        )
        sim = f"• Khách nhận ({rate_percent}%): <b>{format_vnd(customer_vnd)}</b>\n"
    else:
        fee_pct, tax_pct, fee_vnd, tax_vnd = reserve
        applied = (
            "• Phiên bản: <b>V1.2</b>\n"
            f"• Tỷ lệ: <b>{rate_percent}% phần còn lại</b> sau dự phòng phí {fee_pct} và thuế {tax_pct}\n"
        )
        sim = (
            f"• Dự phòng phí ({fee_pct}): -{format_vnd(fee_vnd)}\n"
            f"• Dự phòng thuế ({tax_pct}): -{format_vnd(tax_vnd)}\n"
            f"• Khách nhận ({rate_percent}% phần còn lại): <b>{format_vnd(customer_vnd)}</b>\n"
        )
    return (
        _title("Chính sách")
        + _notice(notice)
        + "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        + applied
        + effect
        + "• Áp dụng cho mọi link tạo mới\n\n"
        "🟡 <b>BẢN NHÁP HẠNG THÀNH VIÊN</b>\n"
        f"• Đang chờ: <b>{pending_line}</b>\n"
        "• Xác nhận hạng chỉ lưu bản ghi, chưa đổi báo giá khách\n"
        "• Trần tỷ lệ chia và hạng V1: <b>70%</b>\n\n"
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ\n"
        + sim
        + f"• Phần còn lại: <b>{format_vnd(remain_vnd)}</b>\n\n"
        "ⓘ Báo giá đã lưu không tự tính lại. Không có cam kết chi trả tự động."
    )


def rank_text(
    *,
    tiers: list[tuple[str, str, str, int, int]],
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
        "• Chưa bật. Mọi khách dùng chung cách tính hiện hành\n"
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
    kind: str | None,
    fee: str,
    tax: str,
    since: str | None,
    upcoming: list[str],
    rate_percent: int,
    sim_fee: int,
    sim_tax: int,
    sim_dist: int,
    sim_customer: int,
    notice: str = "",
) -> str:
    """Mức dự phòng khách đang nhận (ADR-047). since None: mặc định cấu hình."""
    source = f"từ {since}" if since else "mặc định cấu hình"
    lines = [
        _title("Thuế &amp; phí dự phòng") + _notice(notice) + "<i>ESTIMATE RESERVE</i>",
        "",
        "🟢 <b>ĐANG ÁP DỤNG CHO KHÁCH</b>",
        f"• Loại hình: <b>{kind or 'Chưa khai báo'}</b>",
        f"• Phí dự phòng: <b>{fee}</b> · Thuế dự phòng: <b>{tax}</b>",
        f"• Hiệu lực: {source}",
    ]
    if not calculator_on:
        lines.append("⚠️ Đang chạy V1.1: báo giá chưa trừ dự phòng. Mức này có tác dụng khi bật V1.2.")
    if upcoming:
        lines += ["", "🗓️ <b>SẮP ÁP DỤNG</b>"] + [f"• {item}" for item in upcoming]
    lines += [
        "",
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ",
        f"• Phí dự phòng ({fee}): -{format_vnd(sim_fee)}",
        f"• Thuế dự phòng ({tax}): -{format_vnd(sim_tax)}",
        f"• Quỹ phân chia: {format_vnd(sim_dist)}",
        f"• Khách nhận ({rate_percent}%): <b>{format_vnd(sim_customer)}</b>",
        "",
        "ⓘ Dự phòng khi ước tính, không phải thuế phải nộp. Link đã gửi giữ số cũ.",
    ]
    return "\n".join(lines)


def simulation_text(
    *,
    quote: str,
    table: list[tuple[int, list[tuple[str, str, int, int]]]],
) -> str:
    """table: (quỹ, [(tên hạng, %, hoàn, phần còn)])."""
    lines = [
        _title("Mô phỏng").rstrip("\n"),
        "",
        "🟢 <b>ĐANG ÁP DỤNG CHO KHÁCH</b>",
        f"• Báo giá: <b>{quote}</b>",
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
        return head + "Chưa có thay đổi nào. Đổi cấu hình ở Hạng thành viên, Thuế &amp; phí, Chính sách hoặc Ví khách."
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


def _share_title(step: str) -> str:
    return _title("Chính sách", "Tỷ lệ chia", step)


def share_value_text(*, current: str, error: str = "") -> str:
    return (
        _share_title("Bước 1/2")
        + _notice(f"⚠️ {error}" if error else "")
        + f"Tỷ lệ chia đang áp dụng: <b>{current}</b> phần còn lại sau phí và thuế dự phòng.\n\n"
        "Gửi tỷ lệ mới, số nguyên từ 0 đến 70. Ví dụ: <code>65</code>\n"
        "Tỷ lệ thấp hơn: khách nhận ít hơn, phần giữ lại nhiều hơn."
    )


def share_when_text(*, share: str, error: str = "") -> str:
    return (
        _share_title("Bước 2/2")
        + _notice(f"⚠️ {error}" if error else "")
        + f"Tỷ lệ chia mới: <b>{share}</b>\n\n"
        "Áp dụng từ khi nào?\n"
        "Bấm nút, hoặc gửi ngày giờ Việt Nam: <code>01/11</code> hoặc <code>01/11 08:00</code>."
    )


def share_preview_text(
    *,
    calculator_on: bool,
    share: tuple[str, str],
    when: str,
    sample: tuple[int, int, int, int] | None,
    recent: tuple[int, int, int] | None,
) -> str:
    """sample: (khách trước, khách sau, giữ lại trước, giữ lại sau) trên 100.000đ hoa hồng."""
    lines = [
        _share_title("Xem trước").rstrip("\n"),
        "",
        f"• Tỷ lệ chia: {share[0]} → <b>{share[1]}</b>",
        f"• Hiệu lực: <b>{when}</b>",
    ]
    if sample is not None:
        before, after, kept_before, kept_after = sample
        lines += [
            "",
            "🔵 Hoa hồng 100.000đ, sau phí và thuế dự phòng:",
            f"• Khách nhận: {format_vnd(before)} → <b>{format_vnd(after)}</b>",
            f"• Phần giữ lại: {format_vnd(kept_before)} → <b>{format_vnd(kept_after)}</b>",
        ]
    if recent is not None:
        count, total_before, total_after = recent
        lines.append(f"🔵 {count} link gần nhất: khách tổng {format_vnd(total_before)} → <b>{format_vnd(total_after)}</b>")
    if not calculator_on:
        lines += ["", "⚠️ Đang chạy V1.1: lưu được nhưng chưa đổi số khách cho tới khi bật V1.2."]
    lines += ["", "ⓘ Link đã gửi giữ số cũ. Tỷ lệ chia thấp quá làm số hoàn kém hấp dẫn."]
    return "\n".join(lines)


def _reserve_title(step: str) -> str:
    return _title("Thuế &amp; phí dự phòng", step)


def reserve_kind_text(*, current: str | None) -> str:
    return (
        _reserve_title("Bước 1/4")
        + f"Loại hình đang khai báo: <b>{current or 'Chưa khai báo'}</b>\n"
        "Chọn loại hình tài khoản Shopee Affiliate.\n\n"
        "ⓘ Loại hình chỉ là nhãn để tra lại sau này, không tự đổi thuế suất. "
        "Bước sau nhập mức dự phòng."
    )


def reserve_value_text(*, step: str, kind: str, subject: str, current: str, example: str, error: str = "") -> str:
    return (
        _reserve_title(step)
        + _notice(f"⚠️ {error}" if error else "")
        + f"Loại hình: <b>{kind}</b>\n"
        f"{subject} đang áp dụng: <b>{current}</b>\n\n"
        f"Gửi {subject.lower()} mới theo %, từ 0 đến 50. Ví dụ: {example}\n"
        "Hoặc bấm Giữ để không đổi."
    )


def reserve_when_text(*, kind: str, fee: str, tax: str, error: str = "") -> str:
    return (
        _reserve_title("Bước 4/4")
        + _notice(f"⚠️ {error}" if error else "")
        + f"{kind} · phí {fee} · thuế {tax}\n\n"
        "Áp dụng từ khi nào?\n"
        "Bấm nút, hoặc gửi ngày giờ Việt Nam: <code>01/11</code> hoặc <code>01/11 08:00</code>."
    )


def reserve_preview_text(
    *,
    calculator_on: bool,
    kind: tuple[str, str],
    fee: tuple[str, str],
    tax: tuple[str, str],
    when: str,
    sample: tuple[int, int] | None,
    recent: tuple[int, int, int] | None,
) -> str:
    """Mỗi cặp là (đang áp dụng, sau khi đổi). recent: (số link, tổng trước, tổng sau)."""
    lines = [
        _reserve_title("Xem trước").rstrip("\n"),
        "",
        f"• Loại hình: {kind[0]} → <b>{kind[1]}</b>",
        f"• Phí dự phòng: {fee[0]} → <b>{fee[1]}</b>",
        f"• Thuế dự phòng: {tax[0]} → <b>{tax[1]}</b>",
        f"• Hiệu lực: <b>{when}</b>",
    ]
    if sample is not None:
        lines += ["", f"🔵 Hoa hồng 100.000đ: khách nhận {format_vnd(sample[0])} → <b>{format_vnd(sample[1])}</b>"]
    if recent is not None:
        count, before, after = recent
        lines.append(f"🔵 {count} link gần nhất: tổng {format_vnd(before)} → <b>{format_vnd(after)}</b>")
    if not calculator_on:
        lines += ["", "⚠️ Đang chạy V1.1: lưu được nhưng chưa đổi số khách cho tới khi bật V1.2."]
    lines += [
        "",
        "ⓘ Link đã gửi giữ số cũ. Dự phòng không phải thuế luật định.",
    ]
    return "\n".join(lines)


STATS_PERIODS = (("today", "Hôm nay"), ("7d", "7 ngày"), ("30d", "30 ngày"), ("all", "Tất cả"))


def stats_keyboard(current: str) -> Keyboard:
    row = tuple((f"• {label}" if key == current else label, f"c:st:{key}") for key, label in STATS_PERIODS)
    return (row, BACK_HOME)


def _bar(value: int, peak: int, width: int = 10) -> str:
    if value <= 0 or peak <= 0:
        return "▏"
    return "█" * max(1, round(value * width / peak))


def _pct(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    return f"{whole}%" if frac == 0 else f"{whole},{frac:02d}".rstrip("0") + "%"


def _insight_lines(insight, created: int) -> list[str]:
    """insight: admin_stats.Insight hoặc None (DB chưa có cột)."""
    if insight is None:
        return []
    head = f"🏷️ <b>Hoa hồng theo nguồn</b> · {insight.detailed}/{created} link có dữ liệu"
    if insight.detailed == 0:
        return ["", head, "• Link tạo từ bản này trở đi mới có ngành hàng, shop và tách hoa hồng."]
    lines = [
        "",
        head,
        f"• Người bán: <b>{format_vnd(insight.seller_commission_vnd)}</b> · "
        f"Shopee/Xtra: <b>{format_vnd(insight.shopee_commission_vnd)}</b>",
    ]
    rate = _pct(insight.avg_rate_bps) if insight.avg_rate_bps is not None else "-"
    lines.append(f"• Tỷ lệ trung bình: <b>{rate}</b> · Xtra: {insight.xtra} link · Chạm trần: {insight.capped} link")
    if insight.top_categories:
        lines.append("• Ngành hỏi nhiều: " + ", ".join(f"{html.escape(n)} ({c})" for n, c in insight.top_categories))
    if insight.top_shops:
        lines.append("• Shop hỏi nhiều: " + ", ".join(f"{html.escape(n)} ({c})" for n, c in insight.top_shops))
    return lines


def stats_text(stats, *, period_label: str, since: str | None) -> str:
    """stats: admin_stats.Stats."""
    created_rate = f" ({stats.links_created * 100 // stats.links_total}%)" if stats.links_total else ""
    errors = " · ".join(f"{label} {count}" for label, count in stats.rejected) or "không có"
    lines = [
        _title(f"Thống kê · {period_label}").rstrip("\n"),
        f"<i>Từ {since}</i>" if since else "<i>Toàn bộ dữ liệu</i>",
        "",
        "👥 <b>Người dùng</b>",
        f"• Tổng: <b>{stats.users_total}</b> · Mới: <b>{stats.users_new}</b> · Có gửi link: <b>{stats.users_active}</b>",
        "",
        "🔗 <b>Link</b>",
        f"• Gửi: <b>{stats.links_total}</b> · Tạo được: <b>{stats.links_created}</b>{created_rate}",
        f"• Lỗi: {errors}",
        "",
        "💰 <b>Số dự kiến</b> · chưa phải doanh thu",
        f"• Hoa hồng ước tính: <b>{format_vnd(stats.commission_vnd)}</b>",
        f"• Đã báo khách: <b>{format_vnd(stats.cashback_vnd)}</b>",
        f"• Chênh lệch trước phí, thuế: <b>{format_vnd(stats.commission_vnd - stats.cashback_vnd)}</b>",
    ]
    lines += _insight_lines(stats.insight, stats.links_created)
    lines += [
        "",
        "📅 <b>Link tạo được, 7 ngày gần nhất</b>",
    ]
    peak = max((count for _day, count in stats.trend), default=0)
    lines.append("<pre>" + "\n".join(f"{day} {_bar(count, peak)} {count}" for day, count in stats.trend) + "</pre>")
    if stats.top_users:
        lines += ["", "🏆 <b>Gửi nhiều nhất</b>"]
        for rank, (user_id, username, count) in enumerate(stats.top_users, start=1):
            who = f"@{html.escape(username)}" if username else f"<code>{user_id}</code>"
            lines.append(f"{rank}. {who} · {count} link")
    if stats.top_products:
        lines += ["", "🛍️ <b>Món được hỏi nhiều</b>"]
        for rank, (name, count) in enumerate(stats.top_products, start=1):
            lines.append(f"{rank}. {html.escape(name)} · {count} lần")
    lines += [
        "",
        f"🩺 Tin gửi khách chưa xong: <b>{stats.delivery_pending}</b> · Lỗi hệ thống: <b>{stats.errors}</b>",
    ]
    if stats.shopee and (stats.shopee.total_clicks > 0 or stats.shopee.orders_total > 0):
        lines += ["", *shopee_stats_lines(stats.shopee)]
    else:
        lines += [
            "",
            "ⓘ Chưa có dữ liệu đối soát đơn Shopee. Vào 🔗 Shopee Affiliate để đồng bộ.",
        ]
    return "\n".join(lines)


def short_vnd(amount: int) -> str:
    """Số gọn cho bảng chữ đều: 950, 12k, 1,2tr."""
    if amount < 1_000:
        return str(amount)
    if amount < 1_000_000:
        return f"{amount // 1_000}k"
    return f"{amount / 1_000_000:.1f}tr".replace(".", ",")


def shopee_stats_lines(shopee) -> list[str]:
    """shopee: admin_stats.ShopeeStats. Tiền không tính đơn huỷ (PLAN-066)."""
    cr = shopee.conversion_rate_percent
    cr_text = f" · CR qua bot <b>{str(cr).replace('.', ',')}%</b>" if cr is not None else ""
    lines = [
        "🛒 <b>Đối soát Shopee</b>",
        f"• Đơn <b>{shopee.orders_total}</b> (qua bot <b>{shopee.orders_matched_bot}</b>) · "
        f"<b>{shopee.item_qty}</b> món · Doanh số <b>{format_vnd(shopee.gmv_vnd)}</b>",
        f"• Chờ duyệt {shopee.orders_pending} · Hoàn thành {shopee.orders_completed} · Huỷ {shopee.orders_cancelled}",
        f"• HH gốc {format_vnd(shopee.gross_commission_vnd)} − phí MCN {format_vnd(shopee.mcn_fee_vnd)} "
        f"→ <b>HH sau cùng {format_vnd(shopee.real_commission_vnd)}</b>",
        f"• Click <b>{shopee.total_clicks}</b> (qua bot <b>{shopee.clicks_with_bot_sub_id}</b>){cr_text}",
    ]
    if shopee.orders_cancelled:
        lines.append(
            f"• Huỷ: doanh số {format_vnd(shopee.cancelled_gmv_vnd)} · HH mất {format_vnd(shopee.lost_commission_vnd)}"
        )
    if shopee.daily:
        rows = ["Ngày   Đơn Huỷ  D.số    HH Click"]
        rows += [
            f"{day.label} {day.orders:>4} {day.cancelled:>4} {short_vnd(day.gmv_vnd):>6} {short_vnd(day.net_commission_vnd):>5} {day.clicks:>5}"
            for day in shopee.daily
        ]
        lines += ["", "📅 <b>7 ngày qua</b> (HH sau cùng, không tính đơn huỷ)", "<pre>" + "\n".join(rows) + "</pre>"]
    return lines


def shopee_text(
    *,
    status: str,
    account_name: str | None,
    last_sync: str | None,
    total_clicks: int,
    total_orders: int,
    matched_orders: int,
    last_error: str | None = None,
    notice: str = "",
    auto_sync: bool = False,
) -> str:
    title = _title("Shopee Affiliate")
    if status == "connected":
        st_badge = "🟢 <b>ĐÃ KẾT NỐI</b>"
        account_line = f"• Tài khoản: <b>{html.escape(account_name or 'N/A')}</b>\n"
        sync_line = (
            f"• Lần đồng bộ gần nhất: <b>{html.escape(last_sync or 'Chưa đồng bộ')}</b>\n"
            f"• Tự đồng bộ: {'🟢 <b>mỗi 4 giờ</b>' if auto_sync else '⏸️ <b>tắt</b> · bấm 🔄 khi cần'}\n"
        )
    elif status == "expired":
        st_badge = "🔴 <b>COOKIE HẾT HẠN</b>"
        account_line = f"• Tài khoản trước đó: <b>{html.escape(account_name or 'N/A')}</b>\n"
        sync_line = f"• Lỗi: <i>{html.escape(last_error or 'Phiên Shopee hết hạn')}</i>\n"
    else:
        st_badge = "⚪ <b>CHƯA KẾT NỐI</b>"
        account_line = ""
        sync_line = ""
    hint = (
        ""
        if status == "connected"
        else "\n\nⓘ Dán JSON từ extension <b>J2TEAM Cookies</b> hoặc chuỗi <code>name=value;</code>. "
        "Bot tự xoá tin nhắn chứa cookie khỏi chat."
    )

    body = (
        f"{title}"
        f"{_notice(notice)}"
        f"Trạng thái: {st_badge}\n"
        f"{account_line}"
        f"{sync_line}"
        f"• Click Shopee ghi nhận: <b>{total_clicks}</b>\n"
        f"• Đơn Shopee đối soát: <b>{total_orders}</b> (Khớp bot: <b>{matched_orders}</b>)"
        f"{hint}"
    )
    return body


def shopee_prompt_cookie_text() -> str:
    return (
        "🔗 <b>Cập nhật Cookie Shopee Affiliate</b>\n\n"
        "1. Mở trang <b>affiliate.shopee.vn</b> trên trình duyệt đã đăng nhập.\n"
        "2. Bấm icon extension <b>J2TEAM Cookies</b> → <b>Export</b> (sao chép JSON).\n"
        "3. Dán JSON hoặc chuỗi <code>name=value;</code> vào ô chat này. "
        "JSON dài bị Telegram tách nhiều tin thì cứ để nguyên, bot tự ghép.\n\n"
        "🛡️ <i>Bot sẽ kiểm tra phiên, lưu phân quyền riêng 0600 và xoá ngay tin nhắn chứa cookie khỏi chat.</i>"
    )


# --- 👛 Ví khách (PLAN-066) ---------------------------------------------------

WALLET_ADMIN_BACK = (("◀️ Ví khách", "c:menu:wallet"),)


def _who_short(user_id: int, username: str | None) -> str:
    return f"@{username}" if username else str(user_id)


def wallet_admin_text(settings, totals, requests, notice: str = "") -> str:
    state = "🟢 <b>ĐANG BẬT</b>" if settings.enabled else "⚪ <b>ĐANG TẮT</b> · khách chưa thấy ví"
    lines = [
        _title("Ví khách").rstrip("\n"),
        "",
    ]
    if notice:
        lines += [notice, ""]
    lines += [
        f"Trạng thái: {state}",
        f"• Giữ tiền {settings.hold_days} ngày sau khi đơn hoàn thành · Rút tối thiểu {format_vnd(settings.min_withdraw_vnd)}",
        "",
        f"⏳ Chờ duyệt: <b>{format_vnd(totals.pending_vnd)}</b>",
        f"✅ Trong ví chưa rút: <b>{format_vnd(max(0, totals.withdrawable_vnd))}</b>",
        f"📤 Đang chờ chuyển: <b>{format_vnd(totals.requested_vnd)}</b> ({len(requests)} yêu cầu)",
        f"💸 Đã trả: <b>{format_vnd(totals.paid_vnd)}</b>",
    ]
    if requests:
        lines += ["", "Bấm từng yêu cầu bên dưới để xem số tài khoản và xác nhận đã chuyển."]
    return "\n".join(lines)


def wallet_admin_keyboard(settings, requests) -> Keyboard:
    rows: list[tuple[tuple[str, str], ...]] = [
        ((f"📤 {row['transfer_note'] or row['id']} · {format_vnd(int(row['amount_vnd']))} · "
          f"{_who_short(int(row['telegram_user_id']), row['username'])}", f"c:wl:rq:{row['id']}"),)
        for row in requests[:5]
    ]
    rows.append((("👥 Thành viên", "c:wl:members"), ("⚙️ Cài đặt", "c:wl:cfg")))
    rows.append((("⏸️ Tắt ví", "c:wl:off"),) if settings.enabled else (("🟢 Bật ví cho khách", "c:wl:on"),))
    rows.append(BACK_HOME)
    return tuple(rows)


WALLET_ENABLE_CONFIRM = (
    "🟢 <b>Bật ví cho khách?</b>\n\n"
    "Sau khi bật:\n"
    "• Trang chủ có nút <b>👛 Ví của tôi</b>, lệnh /vi dùng được.\n"
    "• Câu \"chưa theo dõi đơn và chưa chi trả\" đổi thành lời hứa chi trả.\n"
    "• Khách nhận tin khi có đơn, đơn hoàn thành, tiền vào ví, đơn huỷ.\n"
    "• Khách khai ngân hàng và bấm Rút; anh chuyển khoản tay rồi bấm ✅.\n\n"
    "ⓘ Mô tả bot (màn trước khi bấm Start) và menu lệnh chỉ đổi sau lần restart kế tiếp."
)
WALLET_ENABLE_KEYBOARD: Keyboard = ((("✅ Bật ví", "c:wl:on:ok"),), WALLET_ADMIN_BACK)


def wallet_settings_text(settings) -> str:
    return (
        _title("Ví khách", "Cài đặt")
        + f"• Giữ tiền: <b>{settings.hold_days} ngày</b> sau khi đơn hoàn thành\n"
        f"• Rút tối thiểu: <b>{format_vnd(settings.min_withdraw_vnd)}</b>\n\n"
        "ⓘ Shopee còn đối soát theo tháng; trả hàng hay gian lận có thể bị trừ lại. "
        "Giữ ngắn thì khách nhận sớm nhưng anh chịu rủi ro ứng trước. "
        "Đổi số ngày áp dụng cho đơn chưa vào ví; đơn đã vào ví giữ nguyên."
    )


def wallet_settings_keyboard(settings, hold_choices, min_choices) -> Keyboard:
    hold = tuple((("• " if d == settings.hold_days else "") + f"{d} ngày", f"c:wl:hold:{d}") for d in hold_choices)
    low = tuple(
        (("• " if v == settings.min_withdraw_vnd else "") + short_vnd(v), f"c:wl:min:{v}") for v in min_choices
    )
    return (hold, low, WALLET_ADMIN_BACK)


def wallet_members_text(members) -> str:
    lines = [_title("Ví khách", "Thành viên").rstrip("\n"), ""]
    if not members:
        return "\n".join(lines + ["Chưa có khách nào có đơn khớp link bot."])
    for rank, member in enumerate(members, start=1):
        balance = member["balance"]
        lines.append(
            f"{rank}. {html.escape(_who_short(member['telegram_user_id'], member['username']))} · "
            f"rút được <b>{format_vnd(balance.withdrawable_vnd)}</b> · chờ {format_vnd(balance.pending_vnd)} · "
            f"đã nhận {format_vnd(balance.paid_vnd)} · {member['orders']} đơn"
        )
    return "\n".join(lines)


def wallet_members_keyboard(members) -> Keyboard:
    buttons = [
        (_who_short(m["telegram_user_id"], m["username"])[:30], f"c:wl:u:{m['telegram_user_id']}") for m in members
    ]
    rows = [tuple(buttons[i : i + 2]) for i in range(0, len(buttons), 2)]
    return (*rows, WALLET_ADMIN_BACK)


_ENTRY_ADMIN = {"pending": "đang xử lý", "holding": "chờ duyệt", "available": "đã vào ví", "cancelled": "huỷ"}


def wallet_member_text(user_id: int, username: str | None, balance, entries, bank) -> str:
    lines = [
        _title("Ví khách", _who_short(user_id, username)).rstrip("\n"),
        "",
        f"✅ Rút được: <b>{format_vnd(balance.withdrawable_vnd)}</b> · ⏳ Chờ: {format_vnd(balance.pending_vnd)}",
        f"📤 Chờ chuyển: {format_vnd(balance.requested_vnd)} · 💸 Đã nhận: {format_vnd(balance.paid_vnd)}",
        "🏦 " + (f"{html.escape(bank.bank_name)} <code>{bank.account_no}</code> · {html.escape(bank.account_name)}" if bank else "Chưa khai"),
        "",
        "🧾 <b>Đơn</b>",
    ]
    lines += [
        f"• {html.escape(buyer_name(e['item_name'] or '-'))} · HH {format_vnd(int(e['commission_vnd']))} → "
        f"<b>{format_vnd(int(e['cashback_vnd']))}</b> · {_ENTRY_ADMIN.get(e['status'], e['status'])}"
        for e in entries
    ] or ["Chưa có đơn."]
    return "\n".join(lines)


def payout_text(
    payout,
    username: str | None,
    balance,
    bank_name: str,
    notice: str = "",
    *,
    qr_sent: bool = False,
    qr_problem: str | None = None,
) -> str:
    status = {"requested": "⏳ chờ chuyển", "paid": "✅ đã chuyển", "rejected": "✖️ đã từ chối"}.get(
        payout["status"], payout["status"]
    )
    lines = [_title("Ví khách", payout["transfer_note"] or f"#{payout['id']}").rstrip("\n"), ""]
    if notice:
        lines += [notice, ""]
    lines += [
        f"👤 {html.escape(_who_short(int(payout['telegram_user_id']), username))} · <code>{payout['telegram_user_id']}</code>",
        f"Trạng thái: <b>{status}</b>",
        "",
        f"Số tiền: <code>{int(payout['amount_vnd'])}</code> ({format_vnd(int(payout['amount_vnd']))})",
        f"Ngân hàng: <b>{html.escape(bank_name)}</b>",
        f"Số TK: <code>{html.escape(payout['account_no'])}</code>",
        f"Chủ TK: <code>{html.escape(payout['account_name'])}</code>",
        f"Nội dung: <code>{html.escape(payout['transfer_note'] or '')}</code>",
    ]
    if payout["status"] == "requested":
        lines.append("")
        if qr_sent:
            lines.append("📷 Ảnh mã QR gửi ngay dưới tin này: app ngân hàng → Quét QR → chọn ảnh.")
        if qr_problem:
            lines.append(f"⚠️ {html.escape(qr_problem)} Chuyển tay theo các số ở trên.")
        lines.append("ⓘ Trước khi chuyển, kiểm tra tên người nhận app ngân hàng hiện ra trùng với Chủ TK.")
    if balance.withdrawable_vnd < 0:
        lines.append(f"⚠️ Ví khách đang âm {format_vnd(-balance.withdrawable_vnd)} do có đơn bị huỷ sau khi vào ví.")
    return "\n".join(lines)


def payout_keyboard(payout) -> Keyboard:
    if payout["status"] != "requested":
        return (WALLET_ADMIN_BACK,)
    pid = payout["id"]
    return ((("✅ Đã chuyển", f"c:wl:paid:{pid}"), ("✖️ Từ chối", f"c:wl:rej:{pid}")), WALLET_ADMIN_BACK)


def payout_confirm_text(payout, paid: bool) -> str:
    amount = format_vnd(int(payout["amount_vnd"]))
    if paid:
        return (
            f"✅ <b>Xác nhận đã chuyển {amount}</b>\n\n"
            f"Nội dung <code>{html.escape(payout['transfer_note'] or '')}</code>. "
            "Bot sẽ báo khách là đã nhận tiền. Không hoàn tác được."
        )
    return f"✖️ <b>Từ chối yêu cầu rút {amount}?</b>\n\nSố tiền trở lại ví khách, khách được báo."


def payout_confirm_keyboard(payout, paid: bool) -> Keyboard:
    pid = payout["id"]
    action = "paid" if paid else "rej"
    label = "✅ Đúng, đã chuyển" if paid else "✖️ Từ chối"
    return (((label, f"c:wl:{action}:{pid}:ok"),), (("◀️ Quay lại", f"c:wl:rq:{pid}"),))
