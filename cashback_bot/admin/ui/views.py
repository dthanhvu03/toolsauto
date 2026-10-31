"""Câu chữ /admin. Không tính tiền, số đã tính được truyền vào.

Nguyên tắc UX (PLAN-060):
1. Dòng đầu là breadcrumb "⚙️ Quản trị › Màn".
2. Màn cấp 1 có một nút "◀️ Tổng quan". Bước nhập số có nút Hủy bản nháp.
3. Không có nút kích hoạt chính sách cho khách.
4. Màn có tiền tách rõ "Đang áp dụng", "Bản nháp / Định hướng" và "Mô phỏng".
"""

from __future__ import annotations

import html

from cashback_bot.admin.ui.glossary import (
    _BANK_STATE,
    _ENTRY_ADMIN,
    ADMIN_KEEP_NOTE,
    PAYOUT_STATUS,
    PAYOUT_TEXT_MAX,
    STEP_HELP,
    STEP_LABELS,
)
from cashback_bot.db import SCRUB_AFTER_SEND_MARK
from cashback_bot.messages import buyer_name
from cashback_bot.money import format_vnd


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
    calculator: str,
    pending: int | None,
    todo: list[str],
    today: str,
    wallet_on: bool = False,
) -> str:
    """Trang chủ /admin: việc cần làm trước, rồi số hôm nay, rồi báo giá đang chạy."""
    quote = quote_label(rate_percent, calculator == "V1.2")
    lines = ["⚙️ <b>Quản trị</b>", "", "📌 <b>Việc cần làm</b>"]
    lines += [f"• {item}" for item in todo] or ["✅ Không có việc gấp."]
    if today:
        lines += ["", today]
    lines += ["", f"💰 Báo giá đang chạy: {quote}",
              "👛 Ví khách: " + ("đang bật" if wallet_on else "đang tắt (bot chưa chi trả)")]
    if pending:
        lines.append(f"🟡 Bản nháp chính sách chờ kích hoạt: <b>{pending}</b> (⚙️ Cài đặt → 💰 Chính sách)")
    return "\n".join(lines)


def settings_text(*, rate_percent: int, membership_on: bool, calculator: str, pending: int | None) -> str:
    v12 = calculator == "V1.2"
    pending_line = "không đọc được" if pending is None else str(pending)
    return (
        "⚙️ Quản trị › <b>Cài đặt</b>\n\n"
        f"• Báo giá: {quote_label(rate_percent, v12)} · cách tính {'V1.2' if v12 else 'V1.1 (chưa bật V1.2)'}\n"
        f"• Hạng thành viên: {'Đã bật' if membership_on else 'Chưa bật'}\n"
        f"• Bản nháp chính sách đang chờ: <b>{pending_line}</b>\n\n"
        "ⓘ Sửa cấu hình không đổi báo giá khách cho tới khi kích hoạt. Báo giá đã lưu không tự tính lại."
    )


def policy_text(
    *,
    rate_percent: int,
    pending: int | None,
    customer_vnd: int,
    remain_vnd: int,
    reserve: tuple[str, str, int, int],
    v12: bool,
    since: str | None = None,
    upcoming: list[str] | None = None,
    warning: str = "",
    notice: str = "",
) -> str:
    """reserve: (% phí, % thuế, tiền phí, tiền thuế) trên 100.000đ. V1.1: admin chịu, không trừ khi chia.

    since: mốc tỷ lệ chia admin áp dụng (ADR-048); None là mặc định cấu hình.
    """
    pending_line = "0 bản nháp" if not pending else f"{pending} bản nháp"
    effect = f"• Hiệu lực tỷ lệ: {f'từ {since}' if since else 'mặc định cấu hình'}\n"
    if warning:
        effect += f"⚠️ {warning}\n"
    if upcoming:
        effect += "🗓️ Sắp áp dụng: " + "; ".join(upcoming) + "\n"
    fee_pct, tax_pct, fee_vnd, tax_vnd = reserve
    if not v12:
        applied = (
            "• Phiên bản: <b>V1.1</b>\n"
            f"• Tỷ lệ: <b>{rate_percent}% hoa hồng ước tính</b>\n"
            "• Chưa trừ thuế và phí dự phòng khi báo giá\n"
        )
        sim = (
            f"• Phần khách ({rate_percent}%): <b>{format_vnd(customer_vnd)}</b>\n"
            f"• Dự phòng phí ({fee_pct}, admin chịu): -{format_vnd(fee_vnd)}\n"
            f"• Dự phòng thuế ({tax_pct}, admin chịu): -{format_vnd(tax_vnd)}\n"
        )
    else:
        applied = (
            "• Phiên bản: <b>V1.2</b>\n"
            f"• Tỷ lệ: <b>{rate_percent}% phần còn lại</b> sau dự phòng phí {fee_pct} và thuế {tax_pct}\n"
        )
        sim = (
            f"• Dự phòng phí ({fee_pct}): -{format_vnd(fee_vnd)}\n"
            f"• Dự phòng thuế ({tax_pct}): -{format_vnd(tax_vnd)}\n"
            f"• Phần khách ({rate_percent}% phần còn lại): <b>{format_vnd(customer_vnd)}</b>\n"
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
        + f"• Biên (sau dự phòng): <b>{format_vnd(remain_vnd)}</b>\n\n"
        f"ⓘ {ADMIN_KEEP_NOTE} Báo giá đã lưu không tự tính lại. Không có cam kết chi trả tự động."
    )


def rank_text(
    *,
    tiers: list[tuple[str, str, str, int, int]],
    notice: str = "",
) -> str:
    """tiers: (emoji, tên hạng, %, hoàn trên 100.000đ, admin còn sau dự phòng)."""
    rates = "".join(f"• {emoji} {name}: <b>{percent}</b>\n" for emoji, name, percent, _c, _r in tiers)
    sims = "".join(
        f"• {name} {percent}: hoàn {format_vnd(cash)} · admin còn {format_vnd(rem)}\n"
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
        "🔵 <b>MÔ PHỎNG</b> · hoa hồng 100.000đ, công thức đang báo giá\n"
        + sims
        + f"\nⓘ {ADMIN_KEEP_NOTE} Chưa có dữ liệu đơn thật nên không có nút kích hoạt tự động.\n\n"
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
    sim_dist: int | None,
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
        f"• Quỹ phân chia: {format_vnd(sim_dist)}" if sim_dist is not None else "• V1.1 chia trên hoa hồng gốc, admin chịu dự phòng",
        f"• Phần khách ({rate_percent}%): <b>{format_vnd(sim_customer)}</b>",
        "",
        "ⓘ Dự phòng khi ước tính, không phải thuế phải nộp. Link đã gửi giữ số cũ.",
    ]
    return "\n".join(lines)


def simulation_prompt_text(error: str = "") -> str:
    return (
        _title("Mô phỏng", "Nhập hoa hồng")
        + (f"⚠️ {error}\n\n" if error else "")
        + "Gửi hoa hồng giả định của một đơn, ví dụ <code>150000</code>, <code>150.000</code>, "
        "<code>150k</code> hoặc <code>1,5tr</code>.\n\n"
        "ⓘ Chỉ để tính thử, không lưu số này. Chờ nhập trong 10 phút."
    )


def policy_cancel_text(*, policy_id: int, subject: str, when: str) -> str:
    return (
        _title("Huỷ lịch hẹn")
        + f"Lịch #{policy_id}: <b>{subject}</b>, hiệu lực <b>{when}</b>.\n\n"
        "• Lịch chưa tới giờ nên chưa áp cho link nào.\n"
        "• Huỷ thì từ mốc đó link mới vẫn theo chính sách đang có hiệu lực lúc ấy.\n"
        "• Link đã tạo và khoản ví không đổi. Dòng chính sách vẫn được giữ trong lịch sử, ghi «đã huỷ».\n\n"
        "ⓘ Lịch đã tới giờ thì không huỷ được. Muốn đổi thì áp dụng mức mới."
    )


def simulation_text(
    *,
    quote: str,
    amount: int,
    settings: tuple[str, str, str],
    columns: tuple[tuple[str, object], tuple[str, object]],
    scheduled: list[str],
    ranks: list[tuple[str, str, int, int]],
) -> str:
    """columns: ((nhãn, CashbackQuote) đang báo giá, (nhãn, CashbackQuote) so sánh). ranks: (hạng, %, hoàn, admin còn)."""
    share, fee, tax = settings
    (live_name, live), (other_name, other) = columns

    def cell(value: int | None, minus: bool = False) -> str:
        if value is None:
            return "—"
        return ("-" if minus and value else "") + format_vnd(value).removesuffix("đ")

    rows = [
        ("Hoa hồng", cell(live.commission_vnd), cell(other.commission_vnd)),
        ("Dự phòng phí", cell(live.fee_reserve_vnd, True), cell(other.fee_reserve_vnd, True)),
        ("Dự phòng thuế", cell(live.tax_reserve_vnd, True), cell(other.tax_reserve_vnd, True)),
    ]
    if live.other_reserve_vnd or other.other_reserve_vnd:
        rows.append(("Dự phòng khác", cell(live.other_reserve_vnd, True), cell(other.other_reserve_vnd, True)))
    rows += [
        ("Quỹ chia", cell(live.distributable_vnd), cell(other.distributable_vnd)),
        ("Phần khách", cell(live.cashback_vnd), cell(other.cashback_vnd)),
        ("Biên", cell(live.remainder_vnd), cell(other.remainder_vnd)),
    ]
    first = max(len(name) for name, _a, _b in rows)
    widths = [max(len(live_name), *(len(a) for _n, a, _b in rows)), max(len(other_name), *(len(b) for _n, _a, b in rows))]
    table = [f"{'':<{first}} {live_name:>{widths[0]}} {other_name:>{widths[1]}}"]
    table += [f"{name:<{first}} {a:>{widths[0]}} {b:>{widths[1]}}" for name, a, b in rows]
    diff = live.cashback_vnd - other.cashback_vnd
    sign = "+" if diff > 0 else ("-" if diff < 0 else "")
    lines = [
        _title("Mô phỏng").rstrip("\n"),
        "",
        "🟢 <b>ĐANG ÁP DỤNG CHO LINK MỚI</b>",
        f"• Báo giá: <b>{quote}</b>",
        f"• Tỷ lệ chia {share} · Phí dự phòng {fee} · Thuế dự phòng {tax}",
        "",
        f"🔵 <b>MÔ PHỎNG</b> · hoa hồng giả định {format_vnd(amount)}",
        "<pre>" + html.escape("\n".join(table)) + "</pre>",
        f"• Phần khách {live_name} so với {other_name}: {sign}{format_vnd(abs(diff))}",
        f"• Cột {live_name} là công thức đang báo giá. Cột {other_name} chỉ để so sánh, không bật công thức nào.",
    ]
    if scheduled:
        lines += ["", "🗓️ <b>ĐÃ HẸN GIỜ</b> · cho link tạo sau mốc"] + [f"• {item}" for item in scheduled]
    lines += ["", "🟡 <b>HẠNG THÀNH VIÊN</b> · bản nháp, chưa bật"]
    lines += [f"• {name} {percent}: hoàn {format_vnd(cash)} · admin còn {format_vnd(rem)}" for name, percent, cash, rem in ranks]
    lines += [
        "",
        "ⓘ Phép tính trên hoa hồng giả định, không phải lợi nhuận và không phát sinh tiền phải trả. "
        "Hoa hồng thật, phí và thuế cuối cùng cần chứng từ. "
        f"{ADMIN_KEEP_NOTE} Mô phỏng không đổi số dư, không lưu gì.",
    ]
    return "\n".join(lines)


def history_text(rows: list[str] | None, versions: list[str] | None = None) -> str:
    """rows None: không đọc được database. versions: phiên bản chính sách (PLAN-076)."""
    head = _title("Lịch sử cấu hình")
    policy = ""
    if versions:
        policy = (
            "🧾 <b>PHIÊN BẢN CHÍNH SÁCH</b>\n"
            + "\n".join(versions)
            + "\nⓘ Mỗi link giữ chính sách lúc tạo. Phiên bản mới chỉ áp cho link tạo sau mốc hiệu lực.\n\n"
        )
    if rows is None:
        return head + policy + "Chưa đọc được lịch sử trên database đang chạy."
    if not rows:
        return head + policy + "Chưa có thay đổi nào. Đổi cấu hình ở Hạng thành viên, Thuế &amp; phí, Chính sách hoặc Ví khách."
    return head + policy + "🕘 <b>THAO TÁC GẦN NHẤT</b>\n" + "\n".join(rows) + "\n\nⓘ 8 thao tác gần nhất, giờ Việt Nam."


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
        "🔵 Mô phỏng hoa hồng 100.000đ theo công thức đang báo giá. Không phải lợi nhuận.\n"
        f"• Trước: hoàn {format_vnd(before_split[0])}, admin còn {format_vnd(before_split[1])}\n"
        f"• Sau: hoàn {format_vnd(after_split[0])}, admin còn {format_vnd(after_split[1])}\n\n"
        "ⓘ Xác nhận chỉ lưu phiên bản, chưa kích hoạt cho khách. Báo giá đã lưu không tự tính lại."
    )


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
    """sample: (khách trước, khách sau, admin còn trước, admin còn sau) trên 100.000đ hoa hồng."""
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
            f"• Phần khách: {format_vnd(before)} → <b>{format_vnd(after)}</b>",
            f"• Biên (sau dự phòng): {format_vnd(kept_before)} → <b>{format_vnd(kept_after)}</b>",
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


def _aligned(rows: list[tuple[str, int, str]]) -> str:
    """Bảng chữ đều: nhãn | số canh phải | ghi chú."""
    label_w = max(len(label) for label, _value, _note in rows)
    nums = [f"{value:,}".replace(",", ".") for _label, value, _note in rows]
    num_w = max(len(num) for num in nums)
    lines = [
        f"{label.ljust(label_w)} {num.rjust(num_w)}" + (f"  {note}" if note else "")
        for (label, _value, note), num in zip(rows, nums)
    ]
    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def _money_lines(shopee) -> list[str]:
    """Tiền tạm tính từ báo cáo Shopee (đơn chưa huỷ, chưa phải tiền Shopee đã trả). Khách, phí, dự phòng thuế lấy từ
    sổ đơn qua bot. Tiền thực (đã trả, đối soát khớp) xem ở 💹 Dòng tiền."""
    if shopee is None or (shopee.total_clicks == 0 and shopee.orders_total == 0):
        return ["💰 <b>Tạm tính</b>", "ⓘ Chưa có dữ liệu. Vào 🛒 Shopee → 🔄 Đồng bộ ngay."]
    costs = shopee.bot_fee_vnd + shopee.bot_tax_vnd
    keep = shopee.real_commission_vnd - shopee.bot_cashback_vnd - costs
    lines = [
        "💰 <b>Tạm tính</b> · Shopee, đơn chưa huỷ (tiền thực xem ở 💹 Dòng tiền)",
        f"Đơn <b>{shopee.orders_total}</b>: chờ {shopee.orders_pending} · xong {shopee.orders_completed} "
        f"· huỷ {shopee.orders_cancelled}",
        _aligned([
            ("Doanh số", shopee.gmv_vnd, ""),
            ("HH ròng", shopee.real_commission_vnd, "sau phí MCN"),
            ("− Phần khách", shopee.bot_cashback_vnd, ""),
            ("− Dự phòng", costs, "phí + thuế"),
            ("= Biên", keep, "anh giữ"),
        ]),
    ]
    outside = shopee.real_commission_vnd - shopee.bot_commission_vnd
    if outside > 0:
        lines.append(f"<i>HH có {format_vnd(outside)} từ đơn ngoài bot (không hoàn khách).</i>")
    return lines


def _funnel_lines(stats) -> list[str]:
    errors = sum(count for _label, count in stats.rejected)
    rows = [
        ("Người dùng", stats.users_total, f"mới {stats.users_new} · gửi link {stats.users_active}"),
        ("Link", stats.links_created, f"gửi {stats.links_total} · lỗi {errors}"),
    ]
    shopee = stats.shopee
    if shopee is not None and (shopee.total_clicks or shopee.orders_total):
        cr = shopee.conversion_rate_percent
        cr_text = f" · CR {str(cr).replace('.', ',')}%" if cr is not None else ""
        rows += [
            ("Click", shopee.total_clicks, f"qua bot {shopee.clicks_with_bot_sub_id}"),
            ("Đơn", shopee.orders_total, f"qua bot {shopee.orders_matched_bot}{cr_text}"),
        ]
    return ["🔗 <b>Phễu</b>", _aligned(rows)]


def _week_lines(stats) -> list[str]:
    """Một bảng 7 ngày: link tạo được, click, đơn, HH. Bỏ ngày không có gì."""
    days = {day.label: day for day in (stats.shopee.daily if stats.shopee else [])}
    rows = []
    for label, links in stats.trend:
        day = days.get(label)
        clicks, orders, commission = (day.clicks, day.orders, day.net_commission_vnd) if day else (0, 0, 0)
        if links or clicks or orders or commission:
            rows.append(f"{label} {links:>4} {clicks:>5} {orders:>3} {short_vnd(commission):>5}")
    if not rows:
        return ["📅 <b>7 ngày gần nhất</b>", "Chưa có hoạt động."]
    table = ["Ngày  Link Click Đơn    HH", *rows]
    return ["📅 <b>7 ngày gần nhất</b> · bỏ ngày trống", "<pre>" + "\n".join(table) + "</pre>"]


def stats_text(stats, *, period_label: str, since: str | None) -> str:
    """Tổng quan (stats: admin_stats.Stats). Số dự kiến, top, ngành hàng ở stats_detail_text."""
    lines = [
        _title(f"Thống kê · {period_label}").rstrip("\n"),
        f"<i>Từ {since}</i>" if since else "<i>Toàn bộ dữ liệu</i>",
        "",
        *_money_lines(stats.shopee),
        "",
        *_funnel_lines(stats),
        "",
        *_week_lines(stats),
    ]
    if stats.delivery_pending or stats.errors or stats.quarantined_updates:
        health = f"🩺 Tin gửi khách chưa xong: <b>{stats.delivery_pending}</b> · Lỗi hệ thống: <b>{stats.errors}</b>"
        if stats.quarantined_updates:
            health += f" · Update cách ly: <b>{stats.quarantined_updates}</b>"
        lines += ["", health]
    return "\n".join(lines)


def _stats_who(user_id: int, name: str | None) -> str:
    """Telegram: @username hoặc ID. Khách Zalo (ID âm, PLAN-082): Zalo · tên hiển thị, chưa có tên thì Zalo #N."""
    if user_id < 0:
        return f"Zalo · {html.escape(name[:24])}" if name else f"Zalo #{-user_id}"
    return f"@{html.escape(name)}" if name else f"<code>{user_id}</code>"


def stats_detail_text(stats, *, period_label: str, since: str | None) -> str:
    created_rate = f" ({stats.links_created * 100 // stats.links_total}%)" if stats.links_total else ""
    errors = " · ".join(f"{label} {count}" for label, count in stats.rejected) or "không có"
    lines = [
        _title(f"Thống kê · {period_label} › Chi tiết").rstrip("\n"),
        f"<i>Từ {since}</i>" if since else "<i>Toàn bộ dữ liệu</i>",
        "",
        "🔗 <b>Link</b>",
        f"• Gửi: <b>{stats.links_total}</b> · Tạo được: <b>{stats.links_created}</b>{created_rate}",
        f"• Lỗi: {errors}",
        "",
        "🔮 <b>Số dự kiến</b> · lúc tạo link, chưa phải doanh thu",
        f"• Hoa hồng ước tính: <b>{format_vnd(stats.commission_vnd)}</b>",
        f"• Đã báo khách: <b>{format_vnd(stats.cashback_vnd)}</b>",
        f"• Chênh lệch trước phí, thuế: <b>{format_vnd(stats.commission_vnd - stats.cashback_vnd)}</b>",
    ]
    shopee = stats.shopee
    if shopee is not None and (shopee.total_clicks or shopee.orders_total):
        lines += [
            "",
            "🛒 <b>Đối soát Shopee</b>",
            f"• <b>{shopee.item_qty}</b> món · Doanh số <b>{format_vnd(shopee.gmv_vnd)}</b>",
            f"• HH gốc {format_vnd(shopee.gross_commission_vnd)} − phí MCN {format_vnd(shopee.mcn_fee_vnd)} "
            f"→ <b>HH ròng {format_vnd(shopee.real_commission_vnd)}</b>",
        ]
        if shopee.bot_commission_vnd:
            lines.append(
                f"• Qua bot: HH ròng {format_vnd(shopee.bot_commission_vnd)} − phần khách {format_vnd(shopee.bot_cashback_vnd)} "
                f"− dự phòng phí {format_vnd(shopee.bot_fee_vnd)} − dự phòng thuế {format_vnd(shopee.bot_tax_vnd)} "
                f"→ <b>Biên {format_vnd(shopee.admin_keep_vnd)}</b>"
            )
        if shopee.orders_cancelled:
            lines.append(
                f"• Huỷ: doanh số {format_vnd(shopee.cancelled_gmv_vnd)} · HH mất {format_vnd(shopee.lost_commission_vnd)}"
            )
    lines += _insight_lines(stats.insight, stats.links_created)
    if stats.top_users:
        lines += ["", "🏆 <b>Gửi nhiều nhất</b>"]
        for rank, top in enumerate(stats.top_users, start=1):
            lines.append(f"{rank}. {_stats_who(top.user_id, top.name)} · {top.links} link · {top.clicks} click")
    if stats.recent_links:
        lines += ["", "🖱️ <b>Link gần nhất</b> · click tới lần đồng bộ Shopee gần nhất"]
        for link in stats.recent_links:
            lines.append(
                f"• <code>{html.escape(link.sub_id or '-')}</code> {link.when} · "
                f"{_stats_who(link.user_id, link.name)} · {link.clicks} click"
            )
    if stats.top_products:
        lines += ["", "🛍️ <b>Món được hỏi nhiều</b>"]
        for rank, (name, count) in enumerate(stats.top_products, start=1):
            lines.append(f"{rank}. {html.escape(name)} · {count} lần")
    return "\n".join(lines)


def short_vnd(amount: int) -> str:
    """Số gọn cho bảng chữ đều: 950, 12k, 1,2tr."""
    if amount < 1_000:
        return str(amount)
    if amount < 1_000_000:
        return f"{amount // 1_000}k"
    return f"{amount / 1_000_000:.1f}tr".replace(".", ",")


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
    auto_sync: str = "⏸️ <b>tắt</b> · bấm 🔄 khi cần",
    crosscheck: str | None = None,
) -> str:
    title = _title("Shopee Affiliate")
    if status == "connected":
        st_badge = "🟢 <b>ĐÃ KẾT NỐI</b>"
        account_line = f"• Tài khoản: <b>{html.escape(account_name or 'N/A')}</b>\n"
        sync_line = (
            f"• Lần đồng bộ gần nhất: <b>{html.escape(last_sync or 'Chưa đồng bộ')}</b>\n"
            f"• Tự đồng bộ: {auto_sync}\n"
        )
        if crosscheck:
            sync_line += f"• {crosscheck}\n"
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


def _who_short(user_id: int, username: str | None) -> str:
    return f"@{username}" if username else str(user_id)


def wallet_admin_text(settings, totals, requests, notice: str = "", fund=None, groups=None, problems=None) -> str:
    """fund: payouts.FundPosition; groups: {nhãn: số yêu cầu}; problems: vi phạm bất biến (PLAN-078)."""
    state = "🟢 <b>ĐANG BẬT</b>" if settings.enabled else "⚪ <b>ĐANG TẮT</b> · khách chưa thấy ví"
    lines = [
        _title("Ví khách").rstrip("\n"),
        "",
    ]
    if notice:
        lines += [notice, ""]
    lines += [f"Trạng thái: {state}"]
    if settings.locked_reasons:
        lines += [
            "",
            "🔒 <b>KHOÁ TÀI CHÍNH</b> · không bật ví, không tạo yêu cầu rút, không duyệt chi hay xác nhận chuyển khoản",
            *(f"• {html.escape(reason)}" for reason in settings.locked_reasons if not reason.startswith("Chưa đạt:")),
            *([f"• Còn {sum(r.startswith('Chưa đạt:') for r in settings.locked_reasons)} điều kiện chi trả PLAN-078 "
               "chưa đạt (xem ⚖️ Sẵn sàng chi trả)"] if any(r.startswith("Chưa đạt:") for r in settings.locked_reasons) else []),
            "ⓘ Bot vẫn tạo link, đồng bộ đơn và ghi tiền chờ duyệt bình thường.",
        ]
    lines += [
        f"• Giữ tiền {settings.hold_days} ngày sau khi đơn hoàn thành, và chỉ vào ví khi Shopee đã duyệt, kỳ đã đối soát "
        f"khớp · Rút tối thiểu {format_vnd(settings.min_withdraw_vnd)}",
        "",
        f"⏳ Chờ duyệt: <b>{format_vnd(totals.pending_vnd)}</b>"
        + (f" (trong đó đang giữ {format_vnd(totals.held_vnd)})" if getattr(totals, "held_vnd", 0) else ""),
        f"✅ Trong ví chưa rút: <b>{format_vnd(max(0, totals.withdrawable_vnd))}</b>",
        f"📤 Đang giữ cho yêu cầu rút: <b>{format_vnd(totals.requested_vnd)}</b> ({len(requests)} yêu cầu)",
        f"💸 Đã trả (có chứng từ): <b>{format_vnd(totals.paid_vnd)}</b>",
    ]
    if fund is not None:
        lines.append(
            f"🏦 Quỹ có chứng từ còn: <b>{format_vnd(fund.headroom_vnd)}</b>" if fund.verified
            else "🏦 Quỹ có chứng từ: <b>Chưa xác minh</b> (chưa có kỳ Shopee đối soát khớp)"
        )
    if groups:
        lines += ["", "📋 " + " · ".join(f"{label} {count}" for label, count in groups.items())]
    if problems:
        lines += ["", "⚠️ <b>Cảnh báo sổ</b>"] + [f"• {html.escape(p)}" for p in problems[:5]]
    if requests:
        lines += ["", "Bấm từng yêu cầu bên dưới để xem nguồn tiền, điều kiện và bước tiếp theo."]
    return "\n".join(lines)


def _limit_vnd(amount: int) -> str:
    """Nhãn nút gọn: 500k, 2tr (không «2,0tr»)."""
    return short_vnd(amount).replace(",0tr", "tr")


def wallet_settings_text(settings, limits=None, notice: str = "") -> str:
    """limits: payouts.LimitPolicy đang dùng, hoặc None (chưa duyệt bảng hạn mức)."""
    if limits is None:
        limit_line = "• Hạn mức rút: <b>chưa duyệt</b>\n"
    else:
        limit_line = (
            f"• Hạn mức rút mỗi khách: tối đa <b>{format_vnd(limits.max_per_request_vnd)}</b>/lần · "
            f"<b>{format_vnd(limits.daily_total_vnd)}</b>/ngày · <b>{format_vnd(limits.monthly_total_vnd)}</b>/tháng\n"
        )
    return (
        _title("Ví khách", "Cài đặt")
        + (f"{notice}\n\n" if notice else "")
        + f"• Giữ tiền: <b>{settings.hold_days} ngày</b> sau khi đơn hoàn thành\n"
        f"• Rút tối thiểu: <b>{format_vnd(settings.min_withdraw_vnd)}</b>\n"
        + limit_line
        + "\n"
        "ⓘ Shopee còn đối soát theo tháng; trả hàng hay gian lận có thể bị trừ lại. "
        "Giữ ngắn thì khách nhận sớm nhưng anh chịu rủi ro ứng trước. "
        "Đổi số ngày áp dụng cho đơn chưa vào ví; đơn đã vào ví giữ nguyên."
    )


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


def wallet_member_text(user_id: int, username: str | None, balance, entries, bank) -> str:
    lines = [
        _title("Ví khách", _who_short(user_id, username)).rstrip("\n"),
        "",
        f"✅ Rút được: <b>{format_vnd(balance.withdrawable_vnd)}</b> · ⏳ Chờ: {format_vnd(balance.pending_vnd)}",
        f"📤 Chờ chuyển: {format_vnd(balance.requested_vnd)} · 💸 Đã nhận: {format_vnd(balance.paid_vnd)}",
        # Che số tài khoản ở màn xem khách (PLAN-077). Số đầy đủ chỉ hiện ở màn yêu cầu rút, nơi cần để chuyển khoản.
        "🏦 " + (f"{html.escape(bank.masked)} · {html.escape(bank.account_name)}" if bank else "Chưa khai"),
        "",
        "🧾 <b>Đơn</b>",
    ]
    lines += [
        f"• {html.escape(buyer_name(e['item_name'] or '-'))} · HH {format_vnd(int(e['commission_vnd']))} → "
        f"<b>{format_vnd(int(e['cashback_vnd']))}</b> · {_ENTRY_ADMIN.get(e['status'], e['status'])}"
        for e in entries
    ] or ["Chưa có đơn."]
    return "\n".join(lines)


def payout_text(payout, username, bank_name: str, *, allocations, conditions, events, bank_state: str,
                shared_users: int, fund, notice: str = "", show_account: bool = False, qr_problem: str | None = None,
                qr_sent: bool = False) -> str:
    """Chi tiết một yêu cầu rút. Số tài khoản đầy đủ chỉ hiện ở bước Đang chuyển (show_account)."""
    amount = int(payout["amount_vnd"])
    account = payout["account_no"] if show_account else f"••••{payout['account_no'][-4:]}"
    lines = [_title("Ví khách", payout["transfer_note"] or f"#{payout['id']}").rstrip("\n"), ""]
    if notice:
        lines += [notice, ""]
    lines += [
        f"👤 {html.escape(_who_short(int(payout['telegram_user_id']), username))} · <code>{payout['telegram_user_id']}</code>",
        f"Trạng thái: <b>{PAYOUT_STATUS.get(payout['status'], payout['status'])}</b> · phiên bản {payout['version'] or 1}",
        f"Số tiền: <code>{amount}</code> ({format_vnd(amount)})",
        f"Người nhận (chụp lúc gửi yêu cầu): {html.escape(bank_name)} <code>{html.escape(account)}</code> · "
        f"{html.escape(payout['account_name'])}",
        f"Tài khoản: <b>{_BANK_STATE.get(bank_state, '⚪ chưa xác minh')}</b>"
        + (f" · ⚠️ dùng chung với {shared_users - 1} khách khác" if shared_users > 1 else ""),
        f"Nội dung chuyển: <code>{html.escape(payout['transfer_note'] or '')}</code>",
        "",
        "🧾 <b>Nguồn từng đồng</b>",
    ]
    sources = [
        f"• {format_vnd(int(a['amount_vnd']))} ← đơn …{html.escape((a['order_sn'] or a['conversion_id'])[-6:])} · "
        f"link <code>{html.escape(a['sub_id'] or '-')}</code> · {html.escape(a['policy_label'] or 'chưa có snapshot')} · "
        f"duyệt {a['validation_status'] or '-'} · đối soát {a['settlement_status'] or '-'} (kỳ {a['batches'] or '-'})"
        + ("" if a["entry_status"] in (None, "available") else f" · ⚠️ khoản {a['entry_status']}")
        for a in allocations
    ] or ["• Yêu cầu cũ, không có phân bổ theo đơn."]
    head, lines = lines, []
    lines += ["", "🔐 <b>Điều kiện</b>"] + [f"{'✅' if c.ok else '❌'} {html.escape(c.label)}" for c in conditions]
    if fund.verified:
        lines.append(f"Quỹ có chứng từ còn: {format_vnd(fund.headroom_vnd)}")
    else:
        lines.append("Quỹ có chứng từ: <b>Chưa xác minh</b> (chưa có kỳ đối soát khớp)")
    if show_account:
        lines += ["", f"{SCRUB_AFTER_SEND_MARK}: đúng số tiền, đúng nội dung. Kiểm tên người nhận app hiện ra trùng Chủ TK."]
        if qr_sent:
            lines.append("📷 Ảnh mã QR gửi ngay dưới tin này. Mã QR không chứng minh đã chuyển tiền.")
        if qr_problem:
            lines.append(f"⚠️ {html.escape(qr_problem)}")
    lines += ["", "🕘 <b>Lịch sử</b>"] + [
        f"• {e['created_at'][5:16].replace('T', ' ')} {html.escape(e['actor'])}: {e['from_status'] or '—'} → {e['to_status']}"
        + (f" · {html.escape(e['note'][:80])}" if e["note"] else "")
        + (f" · chứng từ {html.escape(e['evidence_ref'][:40])}" if e["evidence_ref"] else "")
        for e in events[-8:]
    ]
    # B12: tin tối đa ~4096 ký tự. Không cắt giữa thẻ HTML; bớt dòng nguồn để giữ phần Điều kiện và Lịch sử.
    budget = PAYOUT_TEXT_MAX - len("\n".join(head + lines)) - 80
    shown: list[str] = []
    for line in sources:
        if sum(len(item) + 1 for item in shown) + len(line) + 1 > budget:
            break
        shown.append(line)
    if len(shown) < len(sources):
        rest = allocations[len(shown):]
        shown.append(f"• … và {len(rest)} khoản khác ({format_vnd(sum(int(a['amount_vnd']) for a in rest))})")
    return "\n".join(head + shown + lines)


def payout_step_text(payout, target: str, needs_text: str | None) -> str:
    amount = format_vnd(int(payout["amount_vnd"]))
    text = (
        f"{STEP_LABELS[target]} · <b>{html.escape(payout['transfer_note'] or '')}</b> ({amount})\n\n"
        f"{STEP_HELP[target]}\n"
    )
    if needs_text:
        text += f"\n✍️ Sau khi bấm xác nhận, gõ {needs_text} trong một tin. Chờ 10 phút."
    return text
