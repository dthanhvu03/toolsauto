"""Câu chữ và nút /admin. Không tính tiền.

Tuân thủ nghiêm ngặt 3 nguyên tắc UX:
1. Giữ nút ◀️ Quay lại và 🏠 Tổng quan trên mọi trang con.
2. Không để nút chưa sử dụng được dẫn đến màn hình vô nghĩa (không có nút kích hoạt tự động).
3. Hiển thị ranh giới rõ ràng: "Đang áp dụng", "Bản nháp / Định hướng" và "Mô phỏng".
"""

from __future__ import annotations

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

MENU_KEYBOARD: Keyboard = (
    (("💰 Chính sách cashback >", "c:menu:policy"),),
    (("🎖️ Hạng thành viên >", "c:menu:rank"),),
    (("🧾 Thuế & phí dự phòng >", "c:menu:fee"),),
    (("🧮 Mô phỏng tiền hoàn >", "c:menu:sim"),),
    (("📊 Lịch sử cấu hình >", "c:menu:hist"),),
    (("📝 Nội dung lệnh >", "c:menu:copy"),),
)

NAV_KEYBOARD: Keyboard = (
    (("◀️ Quay lại", "c:menu:home"), ("🏠 Tổng quan", "c:menu:home")),
)

RANK_KEYBOARD: Keyboard = (
    (("🥉 Đồng", "c:tier:BRONZE"), ("🥈 Bạc", "c:tier:SILVER"), ("🥇 Vàng", "c:tier:GOLD")),
    (("◀️ Quay lại", "c:menu:home"), ("🏠 Tổng quan", "c:menu:home")),
)

FEE_KEYBOARD: Keyboard = (
    (("🧾 Phí dự phòng", "c:tier:FEE"), ("🏛️ Thuế dự phòng", "c:tier:TAX")),
    (("◀️ Quay lại", "c:menu:home"), ("🏠 Tổng quan", "c:menu:home")),
)


def decision_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return (
        (("Hủy", f"c:no:{draft_id}:{nonce}"), ("Xác nhận", f"c:ok:{draft_id}:{nonce}")),
    )


def nav_keyboard(back_target: str = "c:menu:home") -> Keyboard:
    return (
        (("◀️ Quay lại", back_target), ("🏠 Tổng quan", "c:menu:home")),
    )


def home_text(
    *,
    rate_percent: int,
    membership_on: bool,
    calculator: str,
    pending: int | None,
) -> str:
    rank = "Đã bật" if membership_on else "Chưa bật"
    calculator_state = "Đã bật" if calculator == "V1.2" else "Chưa bật"
    pending_line = "không đọc được" if pending is None else str(pending)
    return (
        "⚙️ <b>CASHBACK BOT — QUẢN TRỊ</b>\n\n"
        "<b>Trạng thái đang phục vụ</b>\n\n"
        "Chính sách báo giá: V1.1\n"
        f"Tỷ lệ đang áp dụng: {rate_percent}%\n"
        f"Tỷ lệ ước tính hiện tại: {rate_percent}%\n"
        f"Calculator V1.2: {calculator_state}\n"
        f"Hạng thành viên: {rank}\n"
        "Đối soát &amp; chi trả: Chưa mở\n"
        "Đối soát và chi trả:\nChưa mở\n\n"
        f"Bản nháp đang chờ: {pending_line}\n\n"
        "<b>Thông tin áp dụng</b>\n"
        f"Khách hiện nhận báo giá bằng {rate_percent}% hoa hồng ước tính, chưa khấu trừ thuế và phí.\n"
        "Thay đổi cấu hình không ảnh hưởng đến khách cho đến khi chính sách mới được kích hoạt. "
        "Báo giá đã lưu không tự tính lại.\n\n"
        "Chọn mục cần quản lý:"
    )


def policy_text(
    *,
    rate_percent: int,
    pending: int | None,
) -> str:
    pending_line = "0 bản nháp" if not pending else f"{pending} bản nháp đang chờ"
    return (
        "💰 <b>CHÍNH SÁCH CASHBACK</b>\n\n"
        "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        f"• Phiên bản chính sách: <b>V1.1</b>\n"
        f"• Tỷ lệ ước tính hiện tại: <b>{rate_percent}% hoa hồng ước tính</b>\n"
        "• Khấu trừ: Chưa trừ thuế và phí dự phòng khi báo giá khách\n"
        "• Phạm vi: Áp dụng chung cho tất cả link tạo mới\n\n"
        "🟡 <b>BẢN NHÁP CẤU HÌNH</b>\n"
        f"• Bản nháp đang chờ: <b>{pending_line}</b>\n"
        "• Giới hạn an toàn V1: Tối đa <b>70%</b> (không vượt trần 7.000 bps)\n"
        "• Hiệu lực: Chỉ lưu bản ghi bất biến (customer_effect=none), chưa đổi báo giá khách\n\n"
        "🔵 <b>MÔ PHỎNG PHÂN CHIA (ĐƠN 100.000đ HOA HỒNG)</b>\n"
        f"• Khách nhận ({rate_percent}%): <b>{rate_percent * 1_000:,}đ</b>\n"
        f"• Phần còn lại: <b>{(100 - rate_percent) * 1_000:,}đ</b>\n\n"
        "⚠️ <i>Báo giá đã lưu không tự tính lại. Không có cam kết chi trả tự động.</i>".replace(",", ".")
    )


def rank_text(
    *,
    bronze_percent: str,
    silver_percent: str,
    gold_percent: str,
    displayed_rate_percent: int,
    b_cash: int,
    b_rem: int,
    s_cash: int,
    s_rem: int,
    g_cash: int,
    g_rem: int,
) -> str:
    return (
        "🎖️ <b>QUẢN LÝ HẠNG THÀNH VIÊN</b>\n\n"
        "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        f"• Trạng thái: <b>Chưa bật</b> (Tất cả khách dùng chung tỷ lệ {displayed_rate_percent}%)\n"
        "• Tiến độ lên hạng: Chưa tính\n\n"
        "🟡 <b>BẢN NHÁP / MỨC ĐỊNH HƯỚNG</b>\n"
        "Hạng Đồng, Bạc, Vàng đang là mức định hướng, chưa áp dụng cho khách.\n"
        f"• 🥉 Hạng Đồng: <b>{bronze_percent}</b>\n"
        f"• 🥈 Hạng Bạc: <b>{silver_percent}</b>\n"
        f"• 🥇 Hạng Vàng: <b>{gold_percent}</b>\n"
        "<i>Chọn hạng để tạo bản nháp. Trần V1 là 70%.</i>\n"
        "<i>Quy tắc bắt buộc: Đồng ≤ Bạc ≤ Vàng.</i>\n\n"
        "🔵 <b>MÔ PHỎNG VỚI HOA HỒNG 100.000đ</b>\n"
        f"• Đồng ({bronze_percent}): Hoàn {b_cash:,}đ · Phần còn {b_rem:,}đ\n"
        f"• Bạc ({silver_percent}): Hoàn {s_cash:,}đ · Phần còn {s_rem:,}đ\n"
        f"• Vàng ({gold_percent}): Hoàn {g_cash:,}đ · Phần còn {g_rem:,}đ\n\n"
        "⚠️ <i>Chưa có dữ liệu đơn thật, trang Hạng thành viên hiển thị tỷ lệ và quy tắc dự kiến, "
        "nhưng không có nút kích hoạt tự động.</i>\n\n"
        "Chọn hạng để tạo bản nháp mới:".replace(",", ".")
    )


def fee_text(
    *,
    fee_percent: str,
    fee_bps: int,
    tax_percent: str,
    tax_bps: int,
    sim_fee: int,
    sim_tax: int,
    sim_dist: int,
) -> str:
    return (
        "🧾 <b>THUẾ & PHÍ DỰ PHÒNG</b>\n"
        "<b>ESTIMATE RESERVE</b>\n\n"
        "🟢 <b>ĐANG ÁP DỤNG</b>\n"
        "• Công thức khách: <b>V1.1</b> (Chưa trừ phí & thuế dự phòng khi báo giá)\n\n"
        "🟡 <b>BẢN NHÁP DỰ PHÒNG CẤU HÌNH</b>\n"
        f"• Phí dự phòng ước tính: <b>{fee_percent}</b> ({fee_bps} phần vạn)\n"
        f"• Thuế dự phòng ước tính: <b>{tax_percent}</b> ({tax_bps} phần vạn)\n"
        "Phí và thuế ở đây chỉ là dự phòng khi ước tính.\n"
        "Không phải thuế phải nộp và không sửa chứng từ đã đối soát.\n\n"
        "🔵 <b>MÔ PHỎNG DỰ PHÒNG TRÊN 100.000đ HOA HỒNG</b>\n"
        f"• Hoa hồng ước tính: 100.000đ\n"
        f"• Phí dự phòng ({fee_percent}): -{sim_fee:,}đ\n"
        f"• Thuế TNCN dự phòng ({tax_percent}): -{sim_tax:,}đ\n"
        f"• Quỹ phân chia còn lại: <b>{sim_dist:,}đ</b>\n\n"
        "⚠️ <i>Không sửa số đã thanh toán. Khách chưa đổi công thức V1.1.</i>\n\n"
        "Chọn mục để tạo bản nháp điều chỉnh:".replace(",", ".")
    )


def simulation_text(
    *,
    displayed_rate_percent: int,
    rates: dict[str, int],
) -> str:
    lines = [
        "🧮 <b>MÔ PHỎNG TIỀN HOÀN</b>\n",
        "<b>MÔ PHỎNG</b>",
        "Số dưới đây là thử trên quỹ giả định, không phải lợi nhuận và không phát sinh tiền phải trả.",
        f"Khách đang thấy: {displayed_rate_percent}% hoa hồng ước tính.\n",
        "🟢 <b>ĐANG ÁP DỤNG CHO KHÁCH</b>",
        f"• Báo giá cố định: <b>{displayed_rate_percent}%</b> hoa hồng gộp\n",
        "🔵 <b>BẢNG MÔ PHỎNG THEO CÁC MỨC QUỸ</b>",
    ]
    for amount in (10_000, 100_000):
        lines.append(f"\nQuỹ {amount:,}đ".replace(",", "."))
        for code in ("BRONZE", "SILVER", "GOLD"):
            label = {"BRONZE": "Đồng", "SILVER": "Bạc", "GOLD": "Vàng"}[code]
            bps = rates[code]
            whole, frac = divmod(bps, 100)
            if frac == 0:
                p_str = f"{whole}%"
            else:
                p_str = f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"
            cashback = (amount * bps) // 10_000
            remain = amount - cashback
            lines.append(f"{label} {p_str}: hoàn {cashback:,}đ, phần còn {remain:,}đ".replace(",", "."))
    lines.append("\n⚠️ <i>Mô phỏng chỉ dùng để tính thử phương án, không làm thay đổi số dư hay phát sinh nghĩa vụ.</i>")
    return "\n".join(lines)


def command_copy_text() -> str:
    return (
        "📝 <b>NỘI DUNG LỆNH HỆ THỐNG</b>\n\n"
        "V1 chỉ cho xem danh sách lệnh. Chưa sửa câu chữ /huongdan hay /dieukien tại đây.\n\n"
        "<b>Danh sách lệnh khách hàng đang phục vụ:</b>\n"
        "• <b>/start</b> — Khởi động & giới thiệu chương trình hoàn tiền\n"
        "• <b>/huongdan</b> — Hướng dẫn 4 bước sao chép link & mua hàng\n"
        "• <b>/dieukien</b> — Lưu ý quan trọng để đơn được ghi nhận hợp lệ\n"
        "• <b>/cachtinh</b> — Cách tính tiền hoàn dự kiến cho khách\n"
        "• <b>/hang</b> — Thông tin chương trình thành viên Đồng · Bạc · Vàng\n"
        "• <b>/help</b> — Trung tâm trợ giúp & danh mục lệnh\n\n"
        "💡 <i>Nội dung lệnh được cố định an toàn trong mã nguồn, không chứa link thô hoặc cam kết chi trả.</i>"
    )
