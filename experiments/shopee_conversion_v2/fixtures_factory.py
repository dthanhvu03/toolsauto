"""Synthetic fixtures cho Conversion Sync V2.

Các file này chứng minh logic parser/đối soát.
Chúng KHÔNG phải dữ liệu live từ Shopee.
Envelope API là giả lập vì raw response POC không được lưu.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_CONVERSION_BASE: dict[str, Any] = {
    "conversion_id": "CONV_SAMPLE_001",
    "checkout_id": "CHK_SAMPLE_001",
    "order_id": "ORD_SAMPLE_001",
    "order_sn": None,
    "affiliate_transaction_id": None,
    "sub_id": "G3lkg1JK",
    "click_id": None,
    "purchase_time": "2026-10-22T03:00:00Z",
    "click_time": None,
    "conversion_status": "1",
    "checkout_status": "1",
    "order_status": "COMPLETED",
    "gross_commission": 15000,
    "capped_commission": 12000,
    "estimated_total_commission": 12000,
    "affiliate_net_commission": 10000,
    "item_commission": 10000,
    "item_id": "12345678",
    "shop_id": "87654321",
    "item_name": "Sản phẩm test ABC",
    "item_price": 200000,
}

_CLICK_BASE: dict[str, Any] = {
    "click_id": "CLK_SAMPLE_001",
    "sub_id": "G3lkg1JK",
    "click_time": "2026-10-22T01:37:36Z",
    "click_region": "Viet Nam",
    "device_type": "mobile",
    "utm_content": "G3lkg1JK",
}

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def make_conversion(**overrides: Any) -> dict[str, Any]:
    """Tạo một fixture conversion, merge overrides."""
    record = copy.deepcopy(_CONVERSION_BASE)
    record.update(overrides)
    return record


def make_click(**overrides: Any) -> dict[str, Any]:
    record = copy.deepcopy(_CLICK_BASE)
    record.update(overrides)
    return record


def wrap_api_response(records: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    """Bọc records thành cấu trúc response API giả lập.

    Cấu trúc này là SYNTHETIC — chưa xác minh cấu trúc envelope thật.
    """
    count = len(records) if total is None else total
    return {
        "code": 0,
        "message": "success",
        "data": {
            "list": records,
            "total": count,
            "page": 1,
            "page_size": 50,
        },
    }


def fixture_empty() -> dict[str, Any]:
    return wrap_api_response([])


def fixture_single_matched() -> dict[str, Any]:
    return wrap_api_response([make_conversion()])


def fixture_single_unmatched_no_sub_id() -> dict[str, Any]:
    return wrap_api_response([make_conversion(conversion_id="CONV_NOSUB_001", sub_id=None)])


def fixture_single_unmatched_dash_sub_id() -> dict[str, Any]:
    return wrap_api_response([make_conversion(conversion_id="CONV_DASH_001", sub_id="----")])


def fixture_single_unmatched_unknown_sub_id() -> dict[str, Any]:
    return wrap_api_response([make_conversion(conversion_id="CONV_UNKNOWN_001", sub_id="zZzZzZzZ")])


def fixture_case_mismatch() -> dict[str, Any]:
    return wrap_api_response([make_conversion(conversion_id="CONV_CASE_001", sub_id="g3lkg1jk")])


def fixture_multiple_same_sub_id() -> dict[str, Any]:
    records = [
        make_conversion(conversion_id=f"CONV_MULTI_00{idx}", order_id=f"ORD_MULTI_00{idx}")
        for idx in (1, 2, 3)
    ]
    return wrap_api_response(records)


def fixture_status_change() -> dict[str, Any]:
    return wrap_api_response(
        [make_conversion(conversion_id="CONV_STATUS_001", conversion_status="2", order_status="SHIPPED")]
    )


def fixture_commission_reduced() -> dict[str, Any]:
    return wrap_api_response(
        [
            make_conversion(
                conversion_id="CONV_COMMISSION_001",
                capped_commission=8000,
                estimated_total_commission=8000,
                affiliate_net_commission=6000,
                item_commission=6000,
            )
        ]
    )


def fixture_commission_reversed() -> dict[str, Any]:
    return wrap_api_response(
        [
            make_conversion(
                conversion_id="CONV_REVERSED_001",
                conversion_status="3",
                order_status="CANCELLED",
                gross_commission=0,
                capped_commission=0,
                estimated_total_commission=0,
                affiliate_net_commission=0,
                item_commission=0,
            )
        ]
    )


def fixture_missing_commission() -> dict[str, Any]:
    return wrap_api_response(
        [
            make_conversion(
                conversion_id="CONV_NULLCOMM_001",
                gross_commission=None,
                capped_commission=None,
                estimated_total_commission=None,
                affiliate_net_commission=None,
                item_commission=None,
            )
        ]
    )


def fixture_unknown_fields() -> dict[str, Any]:
    record = make_conversion(conversion_id="CONV_DRIFT_001")
    record["new_unknown_field"] = "surprise"
    record["another_unknown"] = 42
    return wrap_api_response([record])


def fixture_missing_required_fields() -> dict[str, Any]:
    record = make_conversion(conversion_id=None)
    record.pop("conversion_status", None)
    return wrap_api_response([record])


def fixture_multi_item_order() -> dict[str, Any]:
    return wrap_api_response(
        [
            make_conversion(
                conversion_id="CONV_ITEM_001",
                order_id="ORD_MULTI_ITEM",
                item_id="ITEM_A",
                item_name="Sản phẩm A",
                item_price=100000,
                item_commission=5000,
            ),
            make_conversion(
                conversion_id="CONV_ITEM_002",
                order_id="ORD_MULTI_ITEM",
                item_id="ITEM_B",
                item_name="Sản phẩm B",
                item_price=300000,
                item_commission=15000,
            ),
        ]
    )


def fixture_utc_plus7_timestamp() -> dict[str, Any]:
    return wrap_api_response(
        [make_conversion(conversion_id="CONV_TZ_001", purchase_time="2026-10-22 10:00:00+07:00")]
    )


def fixture_duplicate_import_batch() -> dict[str, Any]:
    return fixture_single_matched()


def fixture_clicks_with_sub_id() -> dict[str, Any]:
    return wrap_api_response([make_click()])


def fixture_clicks_dash_sub_id() -> dict[str, Any]:
    return wrap_api_response([make_click(click_id="CLK_DASH_001", sub_id="----", utm_content="----")])


def save_fixture(name: str, records: list[dict[str, Any]] | dict[str, Any]) -> Path:
    """Lưu fixture ra file JSON."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{name}.json"
    data = records if isinstance(records, dict) and "data" in records else wrap_api_response(records)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_fixture(name: str) -> dict[str, Any]:
    """Đọc fixture từ file JSON."""
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def all_fixture_payloads() -> dict[str, dict[str, Any]]:
    return {
        "empty": fixture_empty(),
        "single_matched": fixture_single_matched(),
        "no_sub_id": fixture_single_unmatched_no_sub_id(),
        "dash_sub_id": fixture_single_unmatched_dash_sub_id(),
        "unknown_sub_id": fixture_single_unmatched_unknown_sub_id(),
        "case_mismatch": fixture_case_mismatch(),
        "multiple_same_sub_id": fixture_multiple_same_sub_id(),
        "status_change": fixture_status_change(),
        "commission_reduced": fixture_commission_reduced(),
        "commission_reversed": fixture_commission_reversed(),
        "missing_commission": fixture_missing_commission(),
        "unknown_fields": fixture_unknown_fields(),
        "missing_required": fixture_missing_required_fields(),
        "multi_item_order": fixture_multi_item_order(),
        "utc_plus7": fixture_utc_plus7_timestamp(),
        "clicks_with_sub_id": fixture_clicks_with_sub_id(),
        "clicks_dash_sub_id": fixture_clicks_dash_sub_id(),
    }
