"""Schema mapping: raw Shopee API fields → canonical fields.

VỀ TRẠNG THÁI XÁC MINH:
    - VERIFIED:   Đã quan sát trực tiếp trong response thật của POC.
    - INFERRED:   Suy ra từ cấu trúc API tương tự, chưa xác minh 100%.
    - SYNTHETIC:  Tạo cho mục đích phát triển/test, chưa có mẫu thật.

VỀ ĐƠN VỊ:
    - Hoa hồng: chưa xác minh đơn vị. Prototype lưu nguyên số từ API.
    - Thời gian: chuẩn hóa về ISO 8601 UTC khi nguồn có timezone.
      Thiếu timezone thì giữ hậu tố _NO_TZ, không tự gán UTC+7.

Envelope `{"code","message","data":{"list":[...]}}` là SYNTHETIC cho fixture.
POC đã thấy list nằm trong `data.list`, nhưng cấu trúc lồng nhau đầy đủ
chưa được lưu raw response.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldVerification(Enum):
    """Mức độ xác minh của một field mapping."""

    VERIFIED = "verified"
    INFERRED = "inferred"
    SYNTHETIC = "synthetic"


@dataclass
class FieldMapping:
    """Ánh xạ một raw field → canonical field."""

    raw_path: str
    canonical: str
    dtype: str
    required: bool
    verification: FieldVerification
    notes: str = ""


CONVERSION_FIELDS: list[FieldMapping] = [
    FieldMapping("conversion_id", "conversion_id", "str", True, FieldVerification.VERIFIED, "ID giao dịch conversion"),
    FieldMapping("checkout_id", "checkout_id", "str", False, FieldVerification.VERIFIED, "ID checkout, có thể khác conversion_id"),
    FieldMapping("order_id", "order_id", "str", False, FieldVerification.VERIFIED, "Không chắc là duy nhất — cần kiểm tra trùng"),
    FieldMapping("order_sn", "order_sn", "str", False, FieldVerification.INFERRED, "Mã đơn hàng Shopee, chưa xác minh có trong v3 report"),
    FieldMapping("affiliate_transaction_id", "affiliate_transaction_id", "str", False, FieldVerification.INFERRED, "Transaction ID riêng cho affiliate"),
    FieldMapping("sub_id", "sub_id", "str", False, FieldVerification.VERIFIED, "Sub ID do bot tạo — key đối chiếu chính"),
    FieldMapping("click_id", "click_id", "str", False, FieldVerification.INFERRED, "Chưa xác minh có trong conversion report"),
    FieldMapping("purchase_time", "purchase_time", "timestamp", False, FieldVerification.VERIFIED, "Thời điểm mua — Unix epoch hoặc ISO string"),
    FieldMapping("click_time", "click_time", "timestamp", False, FieldVerification.INFERRED, "Thời điểm click — có thể không có trong conversion report"),
    FieldMapping("conversion_status", "conversion_status", "str", True, FieldVerification.VERIFIED, "Mã trạng thái conversion — giữ nguyên, không tự dịch"),
    FieldMapping("checkout_status", "checkout_status", "str", False, FieldVerification.VERIFIED, "Mã trạng thái checkout — giữ nguyên"),
    FieldMapping("order_status", "order_status", "str", False, FieldVerification.VERIFIED, "Mã trạng thái đơn hàng — giữ nguyên"),
    FieldMapping("gross_commission", "gross_commission", "float", False, FieldVerification.VERIFIED, "Hoa hồng gộp trước cắt"),
    FieldMapping("capped_commission", "capped_commission", "float", False, FieldVerification.VERIFIED, "Hoa hồng sau áp trần"),
    FieldMapping("estimated_total_commission", "estimated_total_commission", "float", False, FieldVerification.VERIFIED, "Hoa hồng ước tính tổng"),
    FieldMapping("affiliate_net_commission", "affiliate_net_commission", "float", False, FieldVerification.VERIFIED, "Hoa hồng ròng affiliate — KHÔNG tự coi là đã thanh toán"),
    FieldMapping("item_commission", "item_commission", "float", False, FieldVerification.VERIFIED, "Hoa hồng cấp sản phẩm — có thể không có ở cấp order"),
    FieldMapping("item_id", "item_id", "str", False, FieldVerification.INFERRED),
    FieldMapping("shop_id", "shop_id", "str", False, FieldVerification.INFERRED),
    FieldMapping("item_name", "item_name", "str", False, FieldVerification.INFERRED),
    FieldMapping("item_price", "item_price", "float", False, FieldVerification.INFERRED),
    FieldMapping("source_updated_at", "source_updated_at", "timestamp", False, FieldVerification.INFERRED, "Chưa thấy trong POC response"),
]

# Top-level keys observed on GET /api/v3/report/list data.list[] during POC 04.
# Presence is live-verified. Meaning of most keys is not.
OBSERVED_LIVE_CONVERSION_KEYS = frozenset({
    "affiliate_id",
    "affiliate_name",
    "affiliate_net_commission",
    "app_type",
    "attribution_type",
    "campaign_mcn_id",
    "campaign_mcn_name",
    "capped_commission",
    "checkout_cap",
    "checkout_complete_time",
    "checkout_id",
    "checkout_status",
    "checkout_status_app",
    "click_id",
    "click_time",
    "content_type",
    "conversion_status",
    "device",
    "direct_source",
    "eligible_seller_commission",
    "estimated_total_commission",
    "estimated_total_commission_with_mcn",
    "estimated_validation_month",
    "first_external_source",
    "gross_commission",
    "indirect_source",
    "internal_source",
    "is_shopee_capped",
    "last_external_source",
    "linked_mcn_commission_rate",
    "linked_mcn_id",
    "linked_mcn_name",
    "mcn_agreement_id",
    "mcn_management_fee_commission",
    "mcn_management_fee_seller_commission",
    "orders",
    "product_type",
    "purchase_time",
    "referrer",
    "report_payment_validation_info",
    "tenant",
    "total_brand_commission",
    "traffic_type",
    "ua_type",
    "user_status",
    "utm_content",
})

CLICK_FIELDS: list[FieldMapping] = [
    FieldMapping("click_id", "click_id", "str", False, FieldVerification.INFERRED, "Chưa xác minh có field này"),
    FieldMapping("sub_id", "sub_id", "str", False, FieldVerification.VERIFIED, "Sub ID — đã thấy nhưng giá trị là '----' cho click cũ"),
    FieldMapping("click_time", "click_time", "timestamp", False, FieldVerification.VERIFIED),
    FieldMapping("click_region", "click_region", "str", False, FieldVerification.VERIFIED, "Đã thấy trong click report POC"),
    FieldMapping("device_type", "device_type", "str", False, FieldVerification.INFERRED),
    FieldMapping("utm_content", "utm_content", "str", False, FieldVerification.INFERRED, "Có thể chứa sub_id — chưa xác minh backend filter"),
]


def get_required_conversion_fields() -> list[str]:
    """Trả về danh sách canonical names bắt buộc."""
    return [item.canonical for item in CONVERSION_FIELDS if item.required]


def get_all_canonical_names(report_type: str = "conversion") -> list[str]:
    """Tất cả canonical names cho một loại report."""
    fields = CONVERSION_FIELDS if report_type == "conversion" else CLICK_FIELDS
    return [item.canonical for item in fields]


def build_raw_to_canonical_map(report_type: str = "conversion") -> dict[str, str]:
    """Dict raw_path → canonical cho lookup nhanh."""
    fields = CONVERSION_FIELDS if report_type == "conversion" else CLICK_FIELDS
    return {item.raw_path: item.canonical for item in fields}


@dataclass
class SchemaCheckResult:
    """Kết quả kiểm tra schema một record."""

    missing_required: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    type_mismatches: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.missing_required

    @property
    def has_drift(self) -> bool:
        return bool(self.unknown_fields)


def is_live_nested_conversion(raw: dict[str, Any]) -> bool:
    """Live report rows carry orders[] and utm_content, not a top-level conversion_id."""
    return isinstance(raw, dict) and "orders" in raw and "conversion_id" not in raw


def check_live_conversion_schema(raw: dict[str, Any]) -> SchemaCheckResult:
    """Schema check for one live nested conversion row."""
    result = SchemaCheckResult()
    if "checkout_id" not in raw:
        result.missing_required.append("checkout_id")
    if "orders" not in raw:
        result.missing_required.append("orders")
    elif not isinstance(raw.get("orders"), list):
        result.type_mismatches.append(("orders", "list", type(raw.get("orders")).__name__))
    for key in raw:
        if key not in OBSERVED_LIVE_CONVERSION_KEYS:
            result.unknown_fields.append(key)
    return result


def check_conversion_schema(raw: dict[str, Any]) -> SchemaCheckResult:
    """Kiểm tra một raw conversion record có đúng schema mong đợi."""
    result = SchemaCheckResult()
    known_raw_names = {item.raw_path for item in CONVERSION_FIELDS}

    for item in CONVERSION_FIELDS:
        if item.required and item.raw_path not in raw:
            result.missing_required.append(item.raw_path)

    for key in raw:
        if key not in known_raw_names:
            result.unknown_fields.append(key)

    for item in CONVERSION_FIELDS:
        if item.raw_path not in raw:
            continue
        value = raw[item.raw_path]
        if value is None:
            continue
        if item.dtype in ("int", "float"):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                result.type_mismatches.append((item.raw_path, item.dtype, type(value).__name__))
        elif item.dtype == "str":
            if not isinstance(value, str):
                result.type_mismatches.append((item.raw_path, item.dtype, type(value).__name__))
    return result
