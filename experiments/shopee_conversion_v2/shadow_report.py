"""Shadow reconciliation report.

Tách click, conversion, quarantine và từng loại hoa hồng.
Không cộng các cấp hoa hồng vào một số. payable_vnd luôn là NULL.
"""
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from typing import Any

from experiments.shopee_conversion_v2.database import ConversionDatabase
from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader


def dataset_class(source: str | None) -> str:
    """Phân loại nguồn để không trộn số synthetic với số đã quan sát."""
    if not source:
        return "unspecified"
    if source.startswith("live_sanitized"):
        return "live_sanitized"
    if source.startswith("live_verified"):
        return "live_verified_summary"
    if source.startswith("synthetic") or source.startswith("fixture") or source.startswith("file:"):
        return "synthetic"
    if source.startswith("test"):
        return "synthetic"
    return "unspecified"


def _load_extra(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _click_bucket(sub_id: str | None, reader: CashbackDBReader | None) -> str:
    if sub_id in (None, "", "----"):
        return "missing_sub_id"
    if reader is None:
        return "unmatched"
    found = reader.lookup_sub_id(sub_id)
    if not found:
        return "unmatched"
    if len(found) > 1:
        return "ambiguous"
    return "matched"


def build_shadow_report(
    conversion_db: ConversionDatabase,
    cashback_reader: CashbackDBReader | None = None,
) -> dict[str, Any]:
    """Báo cáo chỉ đọc trên prototype DB và cashback DB read-only."""
    clicks = conversion_db.get_click_observations()
    click_counts: Counter[str] = Counter()
    click_classes: Counter[str] = Counter()
    for click in clicks:
        click_counts[_click_bucket(click.get("sub_id"), cashback_reader)] += 1
        click_classes[click.get("evidence") or dataset_class(click.get("source"))] += 1

    attributions = {row["conversion_db_id"]: row for row in conversion_db.get_all_attributions()}
    conversions = conversion_db.get_all_conversions()
    runs = conversion_db.get_sync_runs()
    run_source = {run["run_id"]: run.get("source") for run in runs}
    status_counts: Counter[str] = Counter()
    unknown_status_matched = 0
    money_by_class: dict[str, dict[str, Any]] = {}
    for conv in conversions:
        attr = attributions.get(conv["id"])
        status = attr["match_status"] if attr else "not_reconciled"
        status_counts[status] += 1
        if status == "matched" and conv.get("internal_status") == "unknown":
            unknown_status_matched += 1
        origin = dataset_class(run_source.get(conv.get("last_sync_run_id")))
        bucket = money_by_class.setdefault(
            origin,
            {
                "rows": 0,
                "estimated_commission_vnd": Decimal("0"),
                "reported_commission_vnd": Decimal("0"),
                "platform_component_vnd": Decimal("0"),
                "estimated_rows": 0,
                "reported_rows": 0,
                "platform_rows": 0,
                "unscaled_rows": 0,
                "payable_vnd": None,
            },
        )
        bucket["rows"] += 1
        extra = _load_extra(conv.get("extra_fields_json"))
        scaled = extra.get("money_scale") == "100000"
        if not scaled:
            bucket["unscaled_rows"] += 1
            continue
        for key, count_key, raw_key in (
            ("estimated_commission_vnd", "estimated_rows", "estimated_vnd"),
            ("reported_commission_vnd", "reported_rows", "affiliate_net_vnd"),
            ("platform_component_vnd", "platform_rows", "gross_vnd"),
        ):
            amount = _decimal_or_none(extra.get(raw_key))
            if amount is None:
                continue
            bucket[key] += amount
            bucket[count_key] += 1

    quarantine = conversion_db.get_quarantine_rows()
    reasons = Counter(row.get("reason") or "unspecified" for row in quarantine)
    history_changes = 0
    for conv in conversions:
        for item in conversion_db.get_conversion_history(int(conv["id"])):
            if item.get("change_type") != "initial":
                history_changes += 1
    prevented = sum(int(run.get("total_unchanged") or 0) for run in runs)
    schema_notes = 0
    for run in runs:
        details = run.get("error_details") or ""
        if "Schema drift" in details or "Missing" in details or "Duplicate identity" in details:
            schema_notes += 1

    money_out = {}
    for origin, bucket in money_by_class.items():
        money_out[origin] = {
            "rows": bucket["rows"],
            "estimated_commission_vnd": format(bucket["estimated_commission_vnd"], "f"),
            "reported_commission_vnd": format(bucket["reported_commission_vnd"], "f"),
            "platform_component_vnd": format(bucket["platform_component_vnd"], "f"),
            "estimated_rows": bucket["estimated_rows"],
            "reported_rows": bucket["reported_rows"],
            "platform_rows": bucket["platform_rows"],
            "unscaled_rows": bucket["unscaled_rows"],
            "payable_vnd": None,
            "components_are_separate": True,
        }

    return {
        "clicks": {
            "total": len(clicks),
            "matched": click_counts.get("matched", 0),
            "unmatched": click_counts.get("unmatched", 0),
            "ambiguous": click_counts.get("ambiguous", 0),
            "missing_sub_id": click_counts.get("missing_sub_id", 0),
            "conversions_created_from_clicks": 0,
            "evidence": dict(click_classes),
        },
        "conversions": {
            "total": len(conversions),
            "matched": status_counts.get("matched", 0),
            "unmatched": status_counts.get("unmatched", 0),
            "ambiguous": status_counts.get("ambiguous", 0),
            "missing_sub_id": status_counts.get("missing_sub_id", 0),
            "not_reconciled": status_counts.get("not_reconciled", 0),
            "matched_internal_status_unknown": unknown_status_matched,
        },
        "quarantine": {
            "count": len(quarantine),
            "reasons": dict(reasons),
        },
        "money_by_dataset": money_out,
        "history_changes": history_changes,
        "duplicate_rows_prevented": prevented,
        "sync_runs": len(runs),
        "schema_or_identity_runs": schema_notes,
        "payable_vnd": None,
    }


def format_shadow_report(report: dict[str, Any]) -> str:
    """Văn bản báo cáo. Không in user id hay dữ liệu người mua."""
    clicks = report["clicks"]
    conv = report["conversions"]
    quarantine = report["quarantine"]
    lines = [
        "SHADOW RECONCILIATION",
        "payable_vnd: NULL",
        f"1. Clicks observed: {clicks['total']}",
        f"2. Clicks matched to Cashback DB: {clicks['matched']}",
        f"   Clicks missing sub_id: {clicks['missing_sub_id']}",
        f"   Clicks unmatched: {clicks['unmatched']}",
        f"   Click evidence: {clicks['evidence']}",
        "   Conversions created from clicks: 0",
        f"3. Conversions imported: {conv['total']}",
        f"4. Matched / unmatched / ambiguous: {conv['matched']} / {conv['unmatched']} / {conv['ambiguous']}",
        f"5. Conversions missing sub_id: {conv['missing_sub_id']}",
        f"6. Quarantine: {quarantine['count']} reasons={quarantine['reasons']}",
        "7. Commission by dataset. These lines are not added together.",
    ]
    if not report["money_by_dataset"]:
        lines.append("   (no conversion rows)")
    for origin, money in report["money_by_dataset"].items():
        lines.append(
            f"   [{origin}] rows={money['rows']} "
            f"estimated_commission_vnd={money['estimated_commission_vnd']} "
            f"reported_commission_vnd={money['reported_commission_vnd']} "
            f"platform_component_vnd={money['platform_component_vnd']} "
            f"unscaled_rows={money['unscaled_rows']} payable_vnd=NULL"
        )
    lines.append(f"8. Status or commission changes: {report['history_changes']}")
    lines.append(f"9. Duplicate rows prevented: {report['duplicate_rows_prevented']}")
    lines.append(f"10. Sync runs with schema or identity notes: {report['schema_or_identity_runs']}")
    lines.append(
        f"Matched conversions still internal_status=unknown: {conv['matched_internal_status_unknown']}"
    )
    return "\n".join(lines)
