"""Read imported Shopee campaign aggregates only; never request a sync or expose customers."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.features.threads.growth.conversions import cashback_db

FOLDER = Path(__file__).resolve().parent


def measure(path: Path, manifest: dict) -> dict:
    result = {
        "plan": "PLAN-180", "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "available", "post_url": manifest.get("post_url"),
        "sub_ids": [p["sub_id"] for p in manifest["products"]], "products": [],
        "limitations": [
            "Counts are imported Shopee records, not live clicks or a claim that no one clicked.",
            "Link previews and unknown self-clicks cannot be excluded from imported click counts.",
            "Conversion and commission statuses are current; pending amounts are not settled income or profit.",
            "Public affiliate campaign links do not establish Cashbot customer use or personal cashback.",
            "Impressions and money actually received are not available from this report.",
        ],
        "impressions": None, "cash_received_vnd": None, "cashbot_new_customers_attributed": None,
        "source_db_mode": "ro", "sync_requested": False,
    }
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            sync = conn.execute("SELECT status,started_at,completed_at FROM shopee_sync_runs "
                                "ORDER BY id DESC LIMIT 1").fetchone()
            result["last_import"] = dict(zip(("status", "started_at", "completed_at"), sync)) if sync else None
            successful = conn.execute(
                "SELECT status,started_at,completed_at,window_start,window_end FROM shopee_sync_runs "
                "WHERE status='success' AND completed_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
            result["last_successful_import"] = dict(zip(
                ("status", "started_at", "completed_at", "window_start", "window_end"), successful)) if successful else None
            attempt = manifest.get("attempt_started_at")
            if attempt and successful:
                completed = datetime.fromisoformat(successful[2].replace("Z", "+00:00"))
                published = datetime.fromisoformat(attempt.replace("Z", "+00:00"))
                result["successful_import_completed_after_attempt"] = completed >= published
                window_start = datetime.fromisoformat(successful[3].replace("Z", "+00:00")) if successful[3] else None
                window_end = datetime.fromisoformat(successful[4].replace("Z", "+00:00")) if successful[4] else None
                result["successful_import_window_covers_attempt"] = (
                    window_start <= published <= window_end if window_start and window_end else None)
            else:
                result["successful_import_completed_after_attempt"] = None
                result["successful_import_window_covers_attempt"] = None
            for item in manifest["products"]:
                sub = item["sub_id"]
                clicks = conn.execute("SELECT COUNT(*),MAX(click_time) FROM shopee_clicks WHERE sub_id=?",
                                      (sub,)).fetchone()
                count, orders, gross, net, missing_net = conn.execute(
                    "SELECT COUNT(*),COUNT(DISTINCT order_sn),SUM(gross_commission_vnd),"
                    "SUM(net_commission_vnd),SUM(net_commission_vnd IS NULL) "
                    "FROM shopee_conversions WHERE sub_id=?", (sub,)).fetchone()
                states = conn.execute("SELECT order_status,conversion_status,validation_status,settlement_status,"
                                      "COUNT(*) FROM shopee_conversions WHERE sub_id=? "
                                      "GROUP BY order_status,conversion_status,validation_status,settlement_status",
                                      (sub,)).fetchall()
                result["products"].append({
                    "sub_id": sub, "item_id": item["item_id"], "name": item["name"],
                    "imported_click_records": clicks[0], "latest_imported_click_at": clicks[1],
                    "conversion_rows": count, "distinct_reported_orders": orders,
                    "gross_commission_recorded_vnd": gross if count else 0,
                    "net_commission_recorded_vnd": net if count else 0,
                    "rows_missing_net_commission": missing_net or 0,
                    "statuses": [dict(zip(("order", "conversion", "validation", "settlement", "rows"), row))
                                 for row in states],
                })
    except (OSError, sqlite3.Error) as exc:
        result.update(status="unavailable", error_type=type(exc).__name__)
        result["products"] = []
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((FOLDER / "manifest.json").read_text())
    result = measure(cashback_db(), manifest)
    target = FOLDER / ("measurement-baseline.json" if args.baseline else "measurement.json")
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
