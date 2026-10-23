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
    rank = "đã bật" if membership_on else "chưa áp dụng"
    pending_line = "không đọc được" if pending is None else str(pending)
    return (
        "<b>CASHBACK BOT — QUẢN TRỊ</b>\n\n"
        "Phiên bản đang phục vụ: V1.1\n"
        f"Cách tính đang hoạt động: {rate_percent}% hoa hồng ước tính\n"
        f"Hạng thành viên: {rank}\n"
        f"Calculator: {calculator}\n"
        "Đối soát và chi trả: chưa mở\n"
        f"Bản nháp đang chờ: {pending_line}\n\n"
        "Sửa cấu hình chỉ tạo phiên bản mới sau khi xem trước và xác nhận. "
        "Link cũ không đổi. Khách vẫn thấy công thức V1.1 cho tới khi có quyết định bật riêng."
    )
