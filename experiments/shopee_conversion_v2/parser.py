"""Parser: chuyển raw JSON → normalized records.

Fixture envelope là synthetic. Timestamp có timezone được đổi về UTC.
Không tự dịch mã trạng thái số thành Approved/Rejected.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from experiments.shopee_conversion_v2.money import payable_vnd, vnd_text
from experiments.shopee_conversion_v2.schema_map import (
    CLICK_FIELDS,
    CONVERSION_FIELDS,
    FieldMapping,
    check_conversion_schema,
    check_live_conversion_schema,
    is_live_nested_conversion,
)

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


@dataclass
class ParseError:
    index: int
    field: str | None
    error: str
    raw_snippet: str | None = None


@dataclass
class ParseResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    schema_checks: list[Any] = field(default_factory=list)
    total_raw: int = 0
    source_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def valid_count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_schema_drift(self) -> bool:
        return any(getattr(check, "has_drift", False) for check in self.schema_checks)


def normalize_timestamp(value: Any) -> str | None:
    """Normalize timestamp thành ISO 8601 UTC string.

    Không có timezone thì thêm hậu tố _NO_TZ thay vì tự gán múi giờ.
    """
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return str(value)[:60]

    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        try:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        parse_value = value
        forced_utc = False
        if parse_value.endswith("Z"):
            parse_value = parse_value[:-1]
            forced_utc = True
        for fmt in _TIMESTAMP_FORMATS:
            try:
                dt = datetime.strptime(parse_value, fmt)
            except ValueError:
                continue
            if forced_utc:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            return dt.strftime("%Y-%m-%dT%H:%M:%S_NO_TZ")
        logger.warning("Unparseable timestamp: %s", value[:60])
        return value[:60]

    return str(value)[:60]


def parse_conversion_response(raw_response: dict[str, Any], source_label: str = "fixture") -> ParseResult:
    """Parse Conversion Report API response."""
    result = ParseResult(
        source_meta={
            "source": source_label,
            "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    data = raw_response.get("data") if isinstance(raw_response, dict) else None
    if not isinstance(data, dict):
        result.errors.append(
            ParseError(
                index=-1,
                field="data",
                error="Missing or invalid 'data' envelope",
                raw_snippet=str(raw_response)[:200],
            )
        )
        return result

    records_raw = data.get("list")
    if not isinstance(records_raw, list):
        result.errors.append(
            ParseError(
                index=-1,
                field="data.list",
                error="Missing or invalid 'data.list'",
                raw_snippet=str(data)[:200],
            )
        )
        return result

    result.total_raw = len(records_raw)
    result.source_meta["api_total"] = data.get("total", data.get("total_count"))
    result.source_meta["api_page"] = data.get("page", data.get("page_num"))
    seen_identities: set[str] = set()

    for idx, raw_rec in enumerate(records_raw):
        if not isinstance(raw_rec, dict):
            result.errors.append(
                ParseError(
                    index=idx,
                    field=None,
                    error="Record is not a dict",
                    raw_snippet=str(raw_rec)[:200],
                )
            )
            continue
        if is_live_nested_conversion(raw_rec):
            schema_check = check_live_conversion_schema(raw_rec)
            result.schema_checks.append(schema_check)
            if not schema_check.is_valid:
                result.errors.append(
                    ParseError(
                        index=idx,
                        field=None,
                        error=f"Missing required fields: {schema_check.missing_required}",
                    )
                )
                result.quarantined.append(
                    _quarantine(
                        "missing_required",
                        raw_rec.get("checkout_id"),
                        None,
                        raw_rec.get("affiliate_id"),
                    )
                )
                continue
            expanded, held = _expand_live_conversion(raw_rec, idx, result.errors)
            result.quarantined.extend(held)
            for record in expanded:
                identity = record["conversion_id"]
                if identity in seen_identities:
                    result.quarantined.append({
                        "quarantine_key": f"duplicate:{identity}",
                        "reason": "duplicate_identity",
                        "checkout_id": record.get("checkout_id"),
                        "order_id": record.get("order_id"),
                        "affiliate_id": record.get("_extra_fields", {}).get("affiliate_id"),
                    })
                    result.errors.append(
                        ParseError(index=idx, field="conversion_id", error="Duplicate identity in the same response")
                    )
                    continue
                seen_identities.add(identity)
                result.records.append(record)
            continue
        schema_check = check_conversion_schema(raw_rec)
        result.schema_checks.append(schema_check)
        if not schema_check.is_valid:
            snippet = str({key: raw_rec.get(key) for key in ("conversion_id", "sub_id")})[:200]
            result.errors.append(
                ParseError(
                    index=idx,
                    field=None,
                    error=f"Missing required fields: {schema_check.missing_required}",
                    raw_snippet=snippet,
                )
            )
        normalized = _normalize_record(raw_rec, idx, result.errors, CONVERSION_FIELDS)
        if normalized is not None:
            result.records.append(normalized)
    return result


def _money(value: Any) -> int | None:
    """Giữ nguyên số API. Không chia đơn vị và không coi đây là tiền đã nhận."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise InvalidOperation("bool is not money")
    amount = Decimal(str(value))
    if amount != amount.to_integral_value():
        raise InvalidOperation("non-integral money is not verified")
    return int(amount)


def _quarantine(reason: str, checkout_id: Any, order_id: Any, affiliate_id: Any) -> dict[str, Any]:
    return {
        "quarantine_key": f"{reason}:{affiliate_id or 'none'}:{checkout_id or 'none'}:{order_id or 'none'}",
        "reason": reason,
        "checkout_id": None if checkout_id in (None, "") else str(checkout_id),
        "order_id": None if order_id in (None, "") else str(order_id),
        "affiliate_id": None if affiliate_id in (None, "") else str(affiliate_id),
    }


def _expand_live_conversion(
    raw: dict[str, Any],
    index: int,
    errors: list[ParseError],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Tách live row thành một record cho mỗi order.

    Khóa inferred:{affiliate}:{checkout}:{order} là khóa nội bộ, không phải ID Shopee.
    Thiếu một trong ba thành phần thì đưa vào quarantine, không ghi đè conversion.
    Hoa hồng cấp checkout chỉ gắn vào order đầu tiên.
    """
    orders = raw.get("orders") or []
    checkout_raw = raw.get("checkout_id")
    affiliate_raw = raw.get("affiliate_id")
    if not orders:
        errors.append(ParseError(index=index, field="orders", error="Live conversion has no orders"))
        return [], [_quarantine("missing_orders", checkout_raw, None, affiliate_raw)]
    if affiliate_raw in (None, ""):
        errors.append(ParseError(index=index, field="affiliate_id", error="Missing affiliate scope"))
        held = []
        for order in orders:
            order_id = order.get("order_id") if isinstance(order, dict) else None
            held.append(_quarantine("missing_affiliate_id", checkout_raw, order_id, None))
        return [], held
    if checkout_raw in (None, ""):
        errors.append(ParseError(index=index, field="checkout_id", error="Missing checkout_id"))
        return [], [_quarantine("missing_checkout_id", None, None, affiliate_raw)]

    checkout_id = str(checkout_raw)
    affiliate_id = str(affiliate_raw)
    utm = raw.get("utm_content")
    sub_id = None if utm in (None, "") else str(utm)
    multiple_orders = len(orders) > 1
    records: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for order_index, order in enumerate(orders):
        if not isinstance(order, dict):
            errors.append(ParseError(index=index, field="orders", error="Order is not a dict"))
            held.append(_quarantine("invalid_order", checkout_id, None, affiliate_id))
            continue
        order_id = order.get("order_id")
        if not order_id:
            errors.append(ParseError(index=index, field="order_id", error="Missing order_id"))
            held.append(_quarantine("missing_order_id", checkout_id, None, affiliate_id))
            continue
        try:
            gross = _money(raw.get("gross_commission")) if order_index == 0 else None
            capped = _money(raw.get("capped_commission")) if order_index == 0 else None
            estimated = _money(raw.get("estimated_total_commission")) if order_index == 0 else None
            net = _money(raw.get("affiliate_net_commission")) if order_index == 0 else None
        except (InvalidOperation, ValueError) as exc:
            errors.append(ParseError(index=index, field="commission", error=f"Cannot convert money: {exc}"))
            gross = capped = estimated = net = None
        items = []
        item_commission_sum = 0
        saw_item_commission = False
        for item in order.get("items") or []:
            if not isinstance(item, dict):
                continue
            try:
                item_commission = _money(item.get("item_commission"))
                item_price = _money(item.get("item_price"))
            except (InvalidOperation, ValueError) as exc:
                errors.append(ParseError(index=index, field="item_commission", error=f"Cannot convert item money: {exc}"))
                item_commission = None
                item_price = None
            if item_commission is not None:
                saw_item_commission = True
                item_commission_sum += item_commission
            items.append({
                "item_id": None if item.get("item_id") is None else str(item.get("item_id")),
                "item_name": item.get("item_name"),
                "item_price": item_price,
                "item_commission": item_commission,
                "quantity": item.get("qty", item.get("quantity", 1)),
                "model_id": None if item.get("model_id") is None else str(item.get("model_id")),
            })
        order_status = None if order.get("order_status") is None else str(order.get("order_status"))
        checkout_status = None if raw.get("checkout_status") is None else str(raw.get("checkout_status"))
        status_conflict = order_status == "COMPLETED" and checkout_status == "Waiting for payment"
        review = "needs_review" if multiple_orders or not items or status_conflict else "stable_inferred"
        item_sum = item_commission_sum if saw_item_commission else None
        records.append({
            "conversion_id": f"inferred:{affiliate_id}:{checkout_id}:{order_id}",
            "checkout_id": checkout_id,
            "order_id": str(order_id),
            "order_sn": None if order.get("order_sn") is None else str(order.get("order_sn")),
            "affiliate_transaction_id": None if order.get("affiliate_transaction_id") is None else str(order.get("affiliate_transaction_id")),
            "sub_id": sub_id,
            "click_id": None if raw.get("click_id") is None else str(raw.get("click_id")),
            "purchase_time": normalize_timestamp(raw.get("purchase_time")),
            "click_time": normalize_timestamp(raw.get("click_time")),
            "conversion_status": None if raw.get("conversion_status") is None else str(raw.get("conversion_status")),
            "checkout_status": checkout_status,
            "order_status": order_status,
            "gross_commission": gross,
            "capped_commission": capped,
            "estimated_total_commission": estimated,
            "affiliate_net_commission": net,
            "item_commission": item_sum,
            "_items": items,
            "_extra_fields": {
                "affiliate_id": affiliate_id,
                "identity_verified": False,
                "identity_official": False,
                "identity_method": "inferred_affiliate_checkout_order",
                "review_status": review,
                "status_conflict": status_conflict,
                "money_scale": "100000",
                "money_scale_verification": "live_dashboard_one_order",
                "money_unit": "VND",
                "gross_vnd": vnd_text(gross),
                "capped_vnd": vnd_text(capped),
                "estimated_vnd": vnd_text(estimated),
                "affiliate_net_vnd": vnd_text(net),
                "item_commission_vnd": vnd_text(item_sum),
                "brand_vnd": vnd_text(raw.get("total_brand_commission")) if order_index == 0 else None,
                "item_commission_equals_gross": item_sum == gross and gross is not None,
                "do_not_sum_components": True,
                "payable_vnd": payable_vnd(),
                "commission_not_payable": True,
            },
        })
    return records, held


def parse_click_response(raw_response: dict[str, Any], source_label: str = "fixture") -> ParseResult:
    """Parse Click Report API response."""
    result = ParseResult(
        source_meta={
            "source": source_label,
            "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    data = raw_response.get("data") if isinstance(raw_response, dict) else None
    if not isinstance(data, dict):
        result.errors.append(ParseError(index=-1, field="data", error="Missing 'data' envelope"))
        return result
    records_raw = data.get("list", [])
    if not isinstance(records_raw, list):
        result.errors.append(ParseError(index=-1, field="data.list", error="Invalid 'data.list'"))
        return result
    result.total_raw = len(records_raw)
    for idx, raw_rec in enumerate(records_raw):
        if not isinstance(raw_rec, dict):
            result.errors.append(
                ParseError(index=idx, field=None, error="Record is not a dict", raw_snippet=str(raw_rec)[:200])
            )
            continue
        normalized = _normalize_record(raw_rec, idx, result.errors, CLICK_FIELDS)
        if normalized is not None:
            result.records.append(normalized)
    return result


def _normalize_record(
    raw: dict[str, Any],
    index: int,
    errors: list[ParseError],
    fields: list[FieldMapping],
) -> dict[str, Any]:
    """Normalize một raw record theo field map."""
    out: dict[str, Any] = {}
    for item in fields:
        raw_val = raw.get(item.raw_path)
        if item.dtype == "timestamp":
            out[item.canonical] = normalize_timestamp(raw_val)
            continue
        if item.dtype in ("int", "float"):
            if raw_val is None:
                out[item.canonical] = None
                continue
            if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
                out[item.canonical] = raw_val
                continue
            try:
                out[item.canonical] = float(raw_val) if item.dtype == "float" else int(raw_val)
            except (TypeError, ValueError):
                errors.append(
                    ParseError(
                        index=index,
                        field=item.raw_path,
                        error=f"Cannot convert to {item.dtype}: {raw_val!r}",
                    )
                )
                out[item.canonical] = None
            continue
        out[item.canonical] = None if raw_val is None else str(raw_val)

    known = {item.raw_path for item in fields}
    extra = {key: value for key, value in raw.items() if key not in known}
    if extra:
        out["_extra_fields"] = extra
    return out
