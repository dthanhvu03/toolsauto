"""Trạng thái duyệt hoa hồng Shopee từ báo cáo conversion (PLAN-074).

Ba trạng thái độc lập, không gộp cột:
- order_status (đã có): trạng thái mua hàng Shopee trả về.
- validation_status (ở đây): hoa hồng affiliate đang ở đâu.
- settlement_status: tiền Shopee đã trả chưa. PLAN-074 luôn để NOT_VERIFIED (PLAN-075 mới xác nhận).

Bằng chứng (khảo sát 3 response thật đã lưu, 2026-10-24):
- Gian lận: `is_fraud=1` + `fraud_reason="Rejected due to fraudulent activity detected"`, hoa hồng 0
  (đơn 23/09). Có bằng chứng chữ rõ ràng nên dùng được.
- Duyệt hoa hồng: KHÔNG có field nào chứng minh. `estimated_validation_month` rỗng,
  `report_payment_validation_info.validation_cycle=0` ở cả 3 đơn; chưa thấy mẫu đơn đã duyệt.
  Ý nghĩa `conversion_status`, `affiliate_item_status`, `fraud_status` chỉ là suy luận.
  Vì vậy hàm này KHÔNG BAO GIỜ trả APPROVED.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

UNKNOWN = "UNKNOWN"
PENDING = "PENDING"
APPROVED = "APPROVED"  # chỉ khai báo; chưa có nguồn xác minh nên không đường nào gán (xem module doc)
REJECTED = "REJECTED"
FRAUD = "FRAUD"
NEEDS_REVIEW = "NEEDS_REVIEW"
VALIDATION_STATES = (UNKNOWN, PENDING, APPROVED, REJECTED, FRAUD, NEEDS_REVIEW)

SETTLEMENT_NOT_VERIFIED = "NOT_VERIFIED"
SOURCE_REPORT = "shopee_report_v3"
CONFIDENCE_INFERRED = "INFERRED"

# Giá trị đã thấy trong response thật. Giá trị lạ → NEEDS_REVIEW, không đoán nghĩa.
KNOWN_ITEM_STATUSES = {1, 3}  # 1: "Pending", 3: "Completed" (display_item_status)
KNOWN_CONVERSION_STATUSES = {1, 3}

# Thay đổi hoa hồng đáng báo admin: giảm từ 1.000đ hoặc từ 10%, hoặc về 0.
SIGNIFICANT_DROP_VND = 1_000
SIGNIFICANT_DROP_RATIO = 0.10


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str
    fraud_flag: int | None  # 1 gian lận, 0 không, None không đọc được
    item_statuses: str | None  # vd "1" hoặc "1,3"
    checkout_status: str | None
    complete: bool  # đủ field để đánh giá; False thì không ghi đè dữ liệu cũ


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def assess(top: dict, order: dict, commission_vnd: int | None) -> Assessment:
    """Đánh giá một đơn từ một lần đồng bộ. Không đọc DB, không suy ra APPROVED hay SETTLED."""
    items = order.get("items") if isinstance(order, dict) else None
    checkout = top.get("checkout_status") if isinstance(top, dict) else None
    checkout = str(checkout) if checkout not in (None, "") else None
    if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
        return Assessment(UNKNOWN, "missing_fields", None, None, checkout, False)
    if any("is_fraud" not in item for item in items):
        return Assessment(UNKNOWN, "missing_fields", None, None, checkout, False)

    fraud = any(_int_or_none(item.get("is_fraud")) == 1 or bool(item.get("fraud_reason")) for item in items)
    item_codes = sorted({code for code in (_int_or_none(item.get("affiliate_item_status")) for item in items) if code is not None})
    item_statuses = ",".join(str(code) for code in item_codes) or None
    fraud_flag = 1 if fraud else 0
    order_status = str(order.get("order_status") or "").upper()

    if fraud:
        return Assessment(FRAUD, "fraud_flag", fraud_flag, item_statuses, checkout, True)
    if "CANCEL" in order_status or order.get("cancel_reason"):
        return Assessment(REJECTED, "order_cancelled", fraud_flag, item_statuses, checkout, True)
    if any(_int_or_none(item.get("fraud_status")) == 3 for item in items):
        # fraud_status=3 chỉ thấy đi kèm is_fraud=1; đứng một mình là mâu thuẫn.
        return Assessment(NEEDS_REVIEW, "fraud_status_conflict", fraud_flag, item_statuses, checkout, True)
    unknown = [code for code in item_codes if code not in KNOWN_ITEM_STATUSES]
    conversion = _int_or_none(top.get("conversion_status"))
    if unknown or (conversion is not None and conversion not in KNOWN_CONVERSION_STATUSES):
        return Assessment(NEEDS_REVIEW, "unmapped_status", fraud_flag, item_statuses, checkout, True)
    if commission_vnd == 0:
        return Assessment(NEEDS_REVIEW, "commission_zero_unexplained", fraud_flag, item_statuses, checkout, True)
    if commission_vnd is None:
        return Assessment(UNKNOWN, "missing_commission", fraud_flag, item_statuses, checkout, False)
    reason = "completed_awaiting_validation" if "COMPLETED" in order_status else "awaiting_shopee_validation"
    return Assessment(PENDING, reason, fraud_flag, item_statuses, checkout, True)


def assess_raw(raw_json: str | None, commission_vnd: int | None) -> Assessment:
    """Đánh giá lại từ raw_json đã lưu (dùng khi backfill dòng cũ)."""
    try:
        data = json.loads(raw_json or "")
    except ValueError:
        return Assessment(UNKNOWN, "missing_fields", None, None, None, False)
    if not isinstance(data, dict):
        return Assessment(UNKNOWN, "missing_fields", None, None, None, False)
    return assess(data.get("top") or {}, data.get("order") or {}, commission_vnd)


def is_significant_drop(old: int | None, new: int | None) -> bool:
    if old is None or new is None or new >= old:
        return False
    if new == 0:
        return True
    return (old - new) >= SIGNIFICANT_DROP_VND or (old - new) >= old * SIGNIFICANT_DROP_RATIO


def is_regression(old_status: str | None, new_status: str) -> bool:
    """Đơn đã bị kết luận gian lận/từ chối mà lần sau lại 'chờ': dữ liệu cũ đến muộn hoặc Shopee sửa."""
    return old_status in (FRAUD, REJECTED) and new_status in (PENDING, UNKNOWN)
