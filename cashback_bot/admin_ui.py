"""Câu chữ và nút /admin. Không tính tiền."""

from __future__ import annotations

Keyboard = tuple[tuple[tuple[str, str], ...], ...]

MENU_KEYBOARD: Keyboard = (
    (("Chính sách cashback", "c:menu:policy"),),
    (("Hạng thành viên", "c:menu:rank"),),
    (("Thuế và phí dự phòng", "c:menu:fee"),),
    (("Mô phỏng tiền", "c:menu:sim"),),
    (("Lịch sử cấu hình", "c:menu:hist"),),
    (("Nội dung lệnh", "c:menu:copy"),),
    (("Quay lại", "c:menu:home"),),
)

RANK_KEYBOARD: Keyboard = (
    (("Đồng", "c:tier:BRONZE"), ("Bạc", "c:tier:SILVER"), ("Vàng", "c:tier:GOLD")),
    (("Quay lại", "c:menu:home"),),
)

FEE_KEYBOARD: Keyboard = (
    (("Phí dự phòng ước tính", "c:tier:FEE"),),
    (("Thuế dự phòng ước tính", "c:tier:TAX"),),
    (("Quay lại", "c:menu:home"),),
)


def decision_keyboard(draft_id: int, nonce: str) -> Keyboard:
    return (
        (("Hủy", f"c:no:{draft_id}:{nonce}"), ("Xác nhận", f"c:ok:{draft_id}:{nonce}")),
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
        "<b>CASHBACK BOT — QUẢN TRỊ</b>\n\n"
        "<b>TRẠNG THÁI HỆ THỐNG</b>\n\n"
        "Chính sách báo giá: V1.1\n"
        f"Tỷ lệ đang áp dụng: {rate_percent}%\n"
        f"Calculator V1.2: {calculator_state}\n"
        f"Hạng thành viên: {rank}\n"
        "Đối soát &amp; chi trả: Chưa mở\n"
        f"Bản nháp đang chờ: {pending_line}\n\n"
        "<b>Thông tin áp dụng</b>\n"
        f"Khách hiện nhận báo giá bằng {rate_percent}% hoa hồng ước tính, chưa khấu trừ thuế và phí.\n"
        "Thay đổi cấu hình không ảnh hưởng đến khách cho đến khi chính sách mới được kích hoạt. "
        "Báo giá đã lưu không tự tính lại."
    )
