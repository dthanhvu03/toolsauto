"""Quy đổi tiền đã đối chiếu với dashboard ngày 22/10/2026.

Hệ số 100000 khớp một đơn thật: giá ₫82.000 và hoa hồng ₫2.050 / ₫2.460 / ₫4.510.
Không dùng kết quả này để tính số tiền được chi trả.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

LIVE_VERIFIED_VND_DIVISOR = Decimal("100000")

# Các field này mô tả cùng một khoản theo từng phần. Không được cộng chồng.
SAME_COMMISSION_COMPONENTS = (
    "gross_commission",
    "capped_commission",
    "item_commission",
    "total_brand_commission",
    "eligible_seller_commission",
    "estimated_total_commission",
    "affiliate_net_commission",
)


def live_raw_to_vnd(raw: Any) -> Decimal | None:
    """Đổi số nguyên API sang VND. Mẫu đã khớp dashboard chia hết cho 100000."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise InvalidOperation("bool is not money")
    amount = Decimal(str(raw))
    if amount != amount.to_integral_value():
        raise InvalidOperation("non-integral raw money is not verified")
    return amount / LIVE_VERIFIED_VND_DIVISOR


def vnd_text(raw: Any) -> str | None:
    """Chuỗi Decimal chính xác, không làm tròn thêm."""
    try:
        value = live_raw_to_vnd(raw)
    except (InvalidOperation, ValueError):
        return None
    if value is None:
        return None
    return format(value, "f")


def payable_vnd() -> None:
    """Chưa có trạng thái hoa hồng đã duyệt hoặc đã trả."""
    return None
