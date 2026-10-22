"""CLI prototype — chạy thử import, reconcile và báo cáo.

Usage:
    python -m experiments.shopee_conversion_v2.cli import-fixture <name>
    python -m experiments.shopee_conversion_v2.cli import-file <path.json>
    python -m experiments.shopee_conversion_v2.cli reconcile
    python -m experiments.shopee_conversion_v2.cli report
    python -m experiments.shopee_conversion_v2.cli schema-check <path.json>
    python -m experiments.shopee_conversion_v2.cli generate-fixtures
    python -m experiments.shopee_conversion_v2.cli run-tests

Không đưa cookie hoặc access token vào CLI arguments.
Không in Affiliate Link đầy đủ.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from experiments.shopee_conversion_v2.database import ConversionDatabase
from experiments.shopee_conversion_v2.fixtures_factory import FIXTURE_DIR, all_fixture_payloads
from experiments.shopee_conversion_v2.parser import parse_conversion_response
from experiments.shopee_conversion_v2.pipeline import ImportResult, import_click_snapshot, import_conversions
from experiments.shopee_conversion_v2.shadow_report import build_shadow_report, format_shadow_report
from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader, ReconciliationEngine
from experiments.shopee_conversion_v2.schema_map import check_conversion_schema

MODULE_DIR = Path(__file__).parent
DB_PATH = MODULE_DIR / "data" / "conversion_poc.sqlite"
CASHBACK_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cashback.sqlite"


def get_db() -> ConversionDatabase:
    db = ConversionDatabase(DB_PATH)
    db.migrate()
    return db


def get_cashback_reader() -> CashbackDBReader | None:
    if not CASHBACK_DB_PATH.exists():
        print("ℹ️  Cashback DB không tồn tại tại:", CASHBACK_DB_PATH)
        return None
    reader = CashbackDBReader(CASHBACK_DB_PATH)
    if not reader.verify_readonly():
        print("⚠️  CẢNH BÁO: Cashback DB không ở chế độ read-only!")
        return None
    return reader


def cmd_import_fixture(args: argparse.Namespace) -> None:
    """Import một fixture theo tên."""
    fixture_path = FIXTURE_DIR / f"{args.name}.json"
    if not fixture_path.exists():
        print(f"❌ Fixture '{args.name}' không tồn tại. Chạy 'generate-fixtures' trước.")
        sys.exit(1)
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    result = import_conversions(raw, get_db(), get_cashback_reader(), source_label=f"fixture:{args.name}")
    _print_import_result(result)


def cmd_import_file(args: argparse.Namespace) -> None:
    """Import từ file JSON tùy chỉnh."""
    path = Path(args.path)
    if not path.exists():
        print(f"❌ File không tồn tại: {path}")
        sys.exit(1)
    raw = json.loads(path.read_text(encoding="utf-8"))
    prefix = "live_verified" if args.dataset == "live_verified" else "synthetic"
    result = import_conversions(raw, get_db(), get_cashback_reader(), source_label=f"{prefix}:{path.name}")
    _print_import_result(result)


def cmd_import_clicks(args: argparse.Namespace) -> None:
    """Import click observations. Does not create conversions."""
    path = Path(args.path)
    if not path.exists():
        print(f"❌ File không tồn tại: {path}")
        sys.exit(1)
    raw = json.loads(path.read_text(encoding="utf-8"))
    evidence = args.evidence
    prefix = "live_verified" if evidence == "live_verified_summary" else "synthetic"
    result = import_click_snapshot(raw, get_db(), source_label=f"{prefix}:{path.stem}", evidence=evidence)
    print("\n📥 CLICK SNAPSHOT")
    print(f"  New:        {result['new']}")
    print(f"  Unchanged:  {result['unchanged']}")
    print(f"  Errors:     {result['errors']}")
    print(f"  Conversions created: {result['created_conversions']}")


def cmd_shadow_report(_args: argparse.Namespace) -> None:
    """Báo cáo shadow. Không chi tiền và không in user id."""
    report = build_shadow_report(get_db(), get_cashback_reader())
    print(format_shadow_report(report))


def cmd_reconcile(_args: argparse.Namespace) -> None:
    """Chạy lại đối chiếu trên tất cả conversions."""
    db = get_db()
    reader = get_cashback_reader()
    engine = ReconciliationEngine(db, reader)
    result = engine.reconcile_all()
    summary = result.summary()
    print("\n📊 KẾT QUẢ ĐỐI CHIẾU")
    print("=" * 50)
    print(f"  Tổng conversion:  {summary['total']}")
    print(f"  ✅ Matched:        {summary['matched']}")
    print(f"  ❌ Unmatched:      {summary['unmatched']}")
    print(f"  ⚠️  Ambiguous:     {summary['ambiguous']}")
    print(f"  💥 Errors:         {summary['errors']}")
    print("\n📋 CHI TIẾT:")
    for detail in result.details:
        sub_id_display = detail.get("sub_id") or "(none)"
        status = detail.get("status")
        status_icon = {"matched": "✅", "unmatched": "❌", "ambiguous": "⚠️"}.get(status, "❓")
        tg_id = detail.get("telegram_user_id")
        tg_display = f" → user:{tg_id}" if tg_id else ""
        print(
            f"  {status_icon} {detail.get('conversion_id')} | sub_id={sub_id_display} | "
            f"{status} | {detail.get('method')}{tg_display}"
        )
        if detail.get("notes"):
            print(f"     📝 {detail['notes']}")


def cmd_report(_args: argparse.Namespace) -> None:
    """Báo cáo tổng hợp."""
    db = get_db()
    conversions = db.get_all_conversions()
    print("\n📊 BÁO CÁO TỔNG HỢP")
    print("=" * 60)
    print(f"  Tổng conversion trong DB: {len(conversions)}")
    print("\n  DANH SÁCH CONVERSION:")
    for conv in conversions:
        commission = conv.get("affiliate_net_commission")
        comm_str = "N/A" if commission is None else f"{commission:.0f}"
        print(
            f"  {conv.get('conversion_id') or '?'}  "
            f"sub_id={conv.get('sub_id') or '-'}  "
            f"status={conv.get('order_status_raw')}/{conv.get('conversion_status_raw')}  "
            f"net={comm_str}  "
            f"purchase={conv.get('purchase_time')}"
        )
    summary = db.get_attribution_summary()
    print("\n  ATTRIBUTION SUMMARY:")
    for key, icon in (("matched", "✅"), ("unmatched", "❌"), ("ambiguous", "⚠️"), ("total", "❓")):
        print(f"    {icon} {key}: {summary.get(key, 0)}")
    print("\n  📜 LỊCH SỬ THAY ĐỔI:")
    for conv in conversions:
        history = db.get_conversion_history(int(conv["id"]))
        for item in history:
            if item["change_type"] == "initial":
                continue
            print(
                f"    [{item['change_type']}] {conv['conversion_id']} "
                f"status: {item['old_order_status']}→{item['new_order_status']} | "
                f"commission: {item['old_affiliate_net_commission']}→{item['new_affiliate_net_commission']} | "
                f"at {item['observed_at']}"
            )
    runs = db.get_sync_runs()
    print(f"\n  SYNC RUNS ({len(runs)}):")
    for run in runs:
        print(
            f"    #{run['run_id']} {run['source']} {run['status']:<10} "
            f"raw={run['total_raw']} new={run['total_new']} upd={run['total_updated']} "
            f"unch={run['total_unchanged']} err={run['total_errors']} at {run['started_at']}"
        )


def cmd_schema_check(args: argparse.Namespace) -> None:
    """Kiểm tra schema của file JSON."""
    path = Path(args.path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data", {})
    records = data.get("list", []) if isinstance(data, dict) else []
    print(f"\n🔍 SCHEMA CHECK: {path}")
    print(f"   Records: {len(records)}")
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            print(f"  [{idx}] ❌ Không phải object")
            continue
        result = check_conversion_schema(rec)
        flags = []
        if result.is_valid:
            flags.append("✅ OK")
        else:
            flags.append(f"❌ Missing required: {result.missing_required}")
        if result.unknown_fields:
            flags.append(f"⚠️  Unknown fields: {result.unknown_fields}")
        if result.type_mismatches:
            flags.append(f"⚠️  Type mismatches: {result.type_mismatches}")
        print(f"  [{idx}] " + " | ".join(flags))


def cmd_generate_fixtures(_args: argparse.Namespace) -> None:
    """Tạo tất cả fixture files."""
    payloads = all_fixture_payloads()
    print(f"📁 Generating {len(payloads)} fixtures in {FIXTURE_DIR}")
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count = len(payload.get("data", {}).get("list", []))
        print(f"  ✅ {name}.json ({count} records)")
    print("Done.")


def cmd_run_tests(_args: argparse.Namespace) -> None:
    """Chạy test suite."""
    test_dir = MODULE_DIR / "tests"
    cmd = [sys.executable, "-m", "pytest", str(test_dir), "-q", "--tb=short"]
    print("🧪 Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=MODULE_DIR.parents[1])
    sys.exit(result.returncode)


def _print_import_result(result: ImportResult) -> None:
    """In kết quả import."""
    parse = result.parse_result
    print("\n📥 KẾT QUẢ IMPORT")
    print("=" * 50)
    print(f"  Sync Run ID:  #{result.sync_run_id}")
    if parse:
        print("\n  PARSE:")
        print(f"    Raw records:    {parse.total_raw}")
        print(f"    Valid:          {parse.valid_count}")
        print(f"    Errors:         {parse.error_count}")
        print(f"    Schema drift:   {'⚠️  YES' if parse.has_schema_drift else '✅ No'}")
    print("\n  UPSERT:")
    print(f"    New:            {result.total_new}")
    print(f"    Updated:        {result.total_updated}")
    print(f"    Unchanged:      {result.total_unchanged}")
    if result.reconciliation:
        summary = result.reconciliation.summary()
        print("\n  RECONCILIATION:")
        print(f"    Total:          {summary['total']}")
        print(f"    ✅ Matched:      {summary['matched']}")
        print(f"    ❌ Unmatched:    {summary['unmatched']}")
        print(f"    ⚠️  Ambiguous:   {summary['ambiguous']}")
        print(f"    💥 Errors:       {summary['errors']}")
    if result.error_messages:
        print(f"\n  ⚠️  ERRORS ({len(result.error_messages)}):")
        for msg in result.error_messages:
            print(f"    • {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="shopee-conversion-v2", description="Shopee Affiliate Conversion Sync V2 Prototype CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fixture = sub.add_parser("import-fixture", help="Import named fixture")
    p_fixture.add_argument("name", help="Fixture name (without .json)")
    p_fixture.set_defaults(func=cmd_import_fixture)

    p_file = sub.add_parser("import-file", help="Import from JSON file")
    p_file.add_argument("path", help="Path to JSON file")
    p_file.add_argument("--dataset", default="synthetic", choices=["synthetic", "live_verified"])
    p_file.set_defaults(func=cmd_import_file)

    p_recon = sub.add_parser("reconcile", help="Re-run reconciliation")
    p_recon.set_defaults(func=cmd_reconcile)

    p_report = sub.add_parser("report", help="Print summary report")
    p_report.set_defaults(func=cmd_report)

    p_clicks = sub.add_parser("import-clicks", help="Import a click snapshot without creating conversions")
    p_clicks.add_argument("path", help="Path to click JSON")
    p_clicks.add_argument("--evidence", default="synthetic", choices=["synthetic", "live_verified_summary"])
    p_clicks.set_defaults(func=cmd_import_clicks)

    p_shadow = sub.add_parser("shadow-report", help="Print shadow reconciliation")
    p_shadow.set_defaults(func=cmd_shadow_report)

    p_schema = sub.add_parser("schema-check", help="Check schema of JSON file")
    p_schema.add_argument("path", help="Path to JSON file")
    p_schema.set_defaults(func=cmd_schema_check)

    p_gen = sub.add_parser("generate-fixtures", help="Generate all test fixtures")
    p_gen.set_defaults(func=cmd_generate_fixtures)

    p_test = sub.add_parser("run-tests", help="Run test suite")
    p_test.set_defaults(func=cmd_run_tests)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
