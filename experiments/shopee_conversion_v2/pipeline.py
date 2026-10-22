"""Import pipeline — orchestrates parse → upsert → reconcile.

Thiết kế idempotent: import cùng dữ liệu hai lần không tạo trùng.
Không xóa conversion cũ khi báo cáo mới không trả lại nó.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from experiments.shopee_conversion_v2.database import ConversionDatabase
from experiments.shopee_conversion_v2.parser import ParseResult, parse_conversion_response
from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader, ReconciliationEngine, ReconciliationResult

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Kết quả tổng hợp một lần import."""

    sync_run_id: int | None = None
    parse_result: ParseResult | None = None
    total_new: int = 0
    total_updated: int = 0
    total_unchanged: int = 0
    total_quarantined: int = 0
    total_errors: int = 0
    reconciliation: ReconciliationResult | None = None
    error_messages: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        recon = self.reconciliation.summary() if self.reconciliation else None
        return {
            "sync_run_id": self.sync_run_id,
            "new": self.total_new,
            "updated": self.total_updated,
            "unchanged": self.total_unchanged,
            "quarantined": self.total_quarantined,
            "errors": self.total_errors,
            "reconciliation": recon,
        }


def import_click_snapshot(
    raw_response: dict[str, Any],
    conversion_db: ConversionDatabase,
    source_label: str,
    evidence: str,
) -> dict[str, int]:
    """Lưu click đã quan sát. Không tạo conversion và không đối soát tiền."""
    rows = ((raw_response.get("data") or {}).get("list")) or []
    if not isinstance(rows, list):
        raise ValueError("click snapshot data.list must be a list")
    run_id = conversion_db.start_sync_run(source=source_label, report_type="click")
    new = unchanged = errors = 0
    messages: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            errors += 1
            messages.append("Click row is not an object")
            continue
        try:
            action = conversion_db.upsert_click_observation(
                observation_key=str(row.get("observation_key") or ""),
                sub_id=None if row.get("sub_id") in (None, "") else str(row.get("sub_id")),
                click_time=None if row.get("click_time") in (None, "") else str(row.get("click_time")),
                source=source_label,
                evidence=evidence,
            )
        except Exception as exc:
            errors += 1
            messages.append(str(exc))
            continue
        if action == "new":
            new += 1
        else:
            unchanged += 1
    conversion_db.complete_sync_run(
        run_id,
        {
            "total_raw": len(rows),
            "total_valid": new + unchanged,
            "total_errors": errors,
            "total_new": new,
            "total_updated": 0,
            "total_unchanged": unchanged,
        },
        errors=messages,
    )
    return {"new": new, "unchanged": unchanged, "errors": errors, "created_conversions": 0}


def import_conversions(
    raw_response: dict[str, Any],
    conversion_db: ConversionDatabase,
    cashback_reader: CashbackDBReader | None = None,
    source_label: str = "fixture",
    skip_reconciliation: bool = False,
) -> ImportResult:
    """Import conversion data: parse → upsert → reconcile."""
    result = ImportResult()
    run_id = conversion_db.start_sync_run(source=source_label, report_type="conversion")
    result.sync_run_id = run_id
    try:
        parse_result = parse_conversion_response(raw_response, source_label=source_label)
        result.parse_result = parse_result
        for error in parse_result.errors:
            result.error_messages.append(f"Parse[{error.index}].{error.field}: {error.error}")
        if parse_result.has_schema_drift:
            result.error_messages.append("Schema drift: unknown fields present")
        for record in parse_result.records:
            try:
                action, _db_id = conversion_db.upsert_conversion(record, sync_run_id=run_id)
            except Exception as exc:
                result.total_errors += 1
                result.error_messages.append(f"Upsert {record.get('conversion_id')}: {exc}")
                logger.error("Upsert error: %s", exc)
                continue
            if action == "new":
                result.total_new += 1
            elif action == "updated":
                result.total_updated += 1
            else:
                result.total_unchanged += 1
        for held in parse_result.quarantined:
            try:
                action = conversion_db.quarantine_conversion(held, sync_run_id=run_id)
            except Exception as exc:
                result.total_errors += 1
                result.error_messages.append(f"Quarantine {held.get('quarantine_key')}: {exc}")
                continue
            if action == "new":
                result.total_quarantined += 1
        if not skip_reconciliation:
            engine = ReconciliationEngine(conversion_db, cashback_reader)
            result.reconciliation = engine.reconcile_all(sync_run_id=run_id)
        conversion_db.complete_sync_run(
            run_id,
            {
                "total_raw": parse_result.total_raw,
                "total_valid": parse_result.valid_count,
                "total_errors": parse_result.error_count + result.total_errors,
                "total_new": result.total_new,
                "total_updated": result.total_updated,
                "total_unchanged": result.total_unchanged,
            },
            errors=result.error_messages,
        )
        return result
    except Exception as exc:
        conversion_db.fail_sync_run(run_id, str(exc))
        result.error_messages.append(f"Pipeline error: {exc}")
        logger.error("Pipeline error: %s", exc)
        raise
