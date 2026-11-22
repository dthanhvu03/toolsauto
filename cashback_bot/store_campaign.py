"""Read-only new-customer observation window for one Store product (PLAN-173).

This is a cohort report, not attribution to a post or proof of campaign lift.
Example: python -m cashback_bot.store_campaign --since 2026-11-18T02:01:59Z --product-id 1 --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot import all_users

NOTES = [
    "New customers joined in [since, until); events must also occur after their join and before until.",
    "Source is first-touch; the time boundary and shared source codes do not establish campaign/post attribution or causality.",
    "Product/confirm markers retain only the first observation per customer; missing markers do not prove a drop-off.",
    "Stages are independent and QR is optional. Paid means credited top-up, not necessarily a delivered order.",
    "24h rate excludes customers not yet observed for 24h; order timestamp is creation, not delivery completion.",
    "Order/top-up status is current, not a historical reconstruction. Current catalog/cache may change; stock is not guaranteed.",
]
STAGES = ("product", "confirm", "qr", "paid", "order")


def _moment(value: str | datetime | None) -> datetime | None:
    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None or moment.utcoffset() is None:
            return None
        return moment.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _catalog(conn: sqlite3.Connection, product_id: int) -> dict:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
    wanted = [key for key in ("id", "name", "price", "description", "active", "upstream_id", "upstream_available",
                              "upstream_cost", "upstream_stock", "synced_at") if key in columns]
    row = conn.execute(f"SELECT {', '.join(wanted)} FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ValueError("selected product not found")
    product = dict(row)
    product["stock_is_cached"] = True
    return product


def _summary(members: list[dict], product_id: int, until: datetime) -> dict:
    mature = [person for person in members if person["joined"] + timedelta(hours=24) <= until]

    def scope(selected: bool) -> dict:
        events = [[event for event in person["events"] if not selected or event["product_id"] == product_id]
                  for person in members]
        orders = [event for group in events for event in group if event["stage"] == "order"]
        qr_statuses: dict[str, int] = {}
        for event in (event for group in events for event in group if event["stage"] == "qr"):
            status = event["status"]
            qr_statuses[status] = qr_statuses.get(status, 0) + 1
        converted = sum(any(event["stage"] == "order" and
                            (not selected or event["product_id"] == product_id) and
                            event["at"] < person["joined"] + timedelta(hours=24)
                            for event in person["events"]) for person in mature)
        return {
            "stages": {stage: sum(any(event["stage"] == stage for event in group) for group in events)
                       for stage in STAGES},
            "qr_requests_by_current_status": qr_statuses,
            "delivered_orders": len(orders),
            "revenue_after_refunds": sum(event["revenue"] for event in orders),
            "mature_24h": len(mature), "converted_24h": converted,
            "conversion_24h_pct": round(converted * 100 / len(mature), 1) if mature else None,
            "not_converted_24h": len(mature) - converted,
        }

    return {"customers": len(members), "not_yet_24h": len(members) - len(mature),
            "all_products": scope(False), "selected_product": scope(True)}


def report(since: datetime, product_id: int, now: datetime | None = None, store_path: Path | None = None,
           source_prefix: str | None = None, exclude_user_ids=(), source_exact: bool = False) -> dict:
    """Read one snapshot and return product facts plus aggregate cohort/source results, never customer IDs."""
    since, until = _moment(since), _moment(now or datetime.now(timezone.utc))
    if since is None or until is None or since > until:
        raise ValueError("since/until must be timezone-aware and since <= until")
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
        raise ValueError("product_id must be a positive integer")
    excluded = {int(value) for value in exclude_user_ids}
    result = {"since": since.isoformat(), "until": until.isoformat(), "product_id": product_id,
              "source_prefix": source_prefix, "source_exact": source_exact,
              "excluded_account_count": len(excluded), "product": None,
              "cohort": None, "sources": [], "notes": NOTES, "errors": []}
    try:
        with closing(_open(store_path or all_users.store_db())) as conn:
            conn.execute("BEGIN")
            result["product"] = _catalog(conn, product_id)
            people: dict[int, dict] = {}
            rows = conn.execute(
                "SELECT u.user_id, u.created_at, s.value AS source FROM users u "
                "LEFT JOIN state s ON s.key = 'src:' || u.user_id "
                "WHERE julianday(u.created_at) >= julianday(?) AND julianday(u.created_at) < julianday(?)",
                (since.isoformat(), until.isoformat()),
            )
            for row in rows:
                joined = _moment(row["created_at"])
                source = row["source"] or "không ghi nhận nguồn"
                source_matches = (source == source_prefix if source_exact else
                                  source_prefix is None or source.startswith(source_prefix))
                if row["user_id"] not in excluded and joined is not None and source_matches:
                    people[row["user_id"]] = {"source": source, "joined": joined, "events": []}

            def add(uid, stage, pid, stamp, **extra):
                person, moment = people.get(uid), _moment(stamp)
                if person is not None and moment is not None and person["joined"] <= moment < until:
                    person["events"].append({"stage": stage, "product_id": pid, "at": moment, **extra})

            for row in conn.execute("SELECT key, value FROM state WHERE key LIKE 'step:product:%' OR key LIKE 'step:confirm:%'"):
                parts = row["key"].split(":", 2)
                product, separator, stamp = str(row["value"] or "").partition("@")
                if len(parts) == 3 and parts[2].isdigit() and separator and product.isdigit():
                    add(int(parts[2]), parts[1], int(product), stamp)
            bounds = (since.isoformat(), until.isoformat())
            for row in conn.execute(
                "SELECT id, user_id, intent_product_id, status, created_at, resolved_at FROM topups "
                "WHERE julianday(created_at) >= julianday(?) AND julianday(created_at) < julianday(?)", bounds,
            ):
                if row["intent_product_id"] is not None:
                    add(row["user_id"], "qr", row["intent_product_id"], row["created_at"], status=row["status"])
                if row["status"] == "paid":
                    add(row["user_id"], "paid", row["intent_product_id"], row["resolved_at"])
            for row in conn.execute(
                "SELECT user_id, product_id, total, refunded, created_at FROM orders "
                "WHERE status IN ('done','partial') AND total > COALESCE(refunded,0) "
                "AND julianday(created_at) >= julianday(?) AND julianday(created_at) < julianday(?)", bounds,
            ):
                add(row["user_id"], "order", row["product_id"], row["created_at"],
                    revenue=int(row["total"]) - int(row["refunded"] or 0))
            members = list(people.values())
            result["cohort"] = _summary(members, product_id, until)
            result["sources"] = [{"source": source, **_summary([p for p in members if p["source"] == source],
                                                               product_id, until)}
                                 for source in sorted({person["source"] for person in members})]
    except (sqlite3.Error, OSError, ValueError) as error:
        result["errors"] = ["ai_store: selected product not found" if isinstance(error, ValueError)
                            else f"ai_store: read unavailable ({type(error).__name__})"]
    return result


def summary(rep: dict) -> str:
    lines = [f"Store observation window: {rep['since']} → {rep['until']}", f"Product #{rep['product_id']}"]
    if rep["cohort"] is not None:
        cohort = rep["cohort"]
        for label, group in [("All products", cohort["all_products"]), ("Selected product", cohort["selected_product"])]:
            rate = group["conversion_24h_pct"]
            lines.append(f"{label}: new customers={cohort['customers']}; stages={group['stages']}; "
                         f"24h={group['converted_24h']}/{group['mature_24h']} "
                         f"({rate if rate is not None else 'not mature'}); revenue after refunds={group['revenue_after_refunds']}")
        lines.append(f"Not yet observed for 24h: {cohort['not_yet_24h']}")
    lines.extend(rep["errors"])
    lines.extend(rep["notes"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until")
    parser.add_argument("--product-id", required=True, type=int)
    parser.add_argument("--source-prefix")
    parser.add_argument("--source-exact", action="store_true",
                        help="Require --source-prefix to match the stored source exactly")
    parser.add_argument("--exclude-user-id", action="append", type=int, default=[])
    parser.add_argument("--store-db", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    since, until = _moment(args.since), _moment(args.until) if args.until else datetime.now(timezone.utc)
    if since is None or until is None or since > until or args.product_id <= 0:
        parser.error("--since/--until need timezone offsets and since <= until; --product-id must be positive")
    rep = report(since, args.product_id, until, args.store_db, args.source_prefix, args.exclude_user_id,
                 source_exact=args.source_exact)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else summary(rep))
    return int(bool(rep["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
