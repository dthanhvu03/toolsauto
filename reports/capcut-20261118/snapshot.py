"""Reproduce product-specific aggregate evidence without writes, syncs or messages."""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values
from cashback_bot import store_campaign

ROOT = Path(__file__).resolve().parents[2]
START = datetime(2026, 11, 18, 2, 1, 59, tzinfo=timezone.utc)
NOW = datetime.now(timezone.utc)
config = dotenv_values(ROOT / ".env")
raw_admins = os.environ.get("STORE_ADMIN_IDS") or config.get("STORE_ADMIN_IDS")
if not raw_admins:
    raise RuntimeError("STORE_ADMIN_IDS required to exclude admin activity")
admins = tuple(int(part.strip()) for part in raw_admins.split(",") if part.strip())
if not admins:
    raise RuntimeError("STORE_ADMIN_IDS must not be empty")
raw_path = os.environ.get("STORE_DB_PATH") or config.get("STORE_DB_PATH") or "./data/store.sqlite"
store_path = Path(raw_path)
if not store_path.is_absolute():
    store_path = ROOT / store_path
reports = {}
for name, since, until in (
    ("after_code_commit", START, NOW),
    ("seven_days_before_code_commit", START - timedelta(days=7), START),
):
    reports[name] = store_campaign.report(
        since, 2, until, store_path, source_prefix="threads_ai_", exclude_user_ids=admins,
    )
    if reports[name]["errors"]:
        raise RuntimeError(reports[name]["errors"])
if reports["after_code_commit"]["product"]["name"].lower().find("capcut") < 0:
    raise RuntimeError("Product 2 is no longer the expected CapCut item")
with closing(sqlite3.connect(store_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
    placeholders = ",".join("?" for _ in admins)
    independent = conn.execute(
        f"""SELECT COUNT(*) FROM users u JOIN state s ON s.key = 'src:' || u.user_id
            WHERE julianday(u.created_at) >= julianday(?) AND julianday(u.created_at) < julianday(?)
            AND substr(s.value,1,11) = 'threads_ai_' AND u.user_id NOT IN ({placeholders})""",
        (START.isoformat(), NOW.isoformat(), *admins),
    ).fetchone()[0]
    facts = conn.execute(
        "SELECT price,upstream_cost,upstream_stock,synced_at FROM products WHERE id = 2"
    ).fetchone()
assert independent == reports["after_code_commit"]["cohort"]["customers"]
proof = {
    "observed_at": NOW.isoformat(),
    "observation_boundary": START.isoformat(),
    "independent_cohort_count": independent,
    "independent_sql_matches": True,
    "excluded_admin_count": len(admins),
    "product_economics": {"price": facts[0], "recorded_unit_cost": facts[1],
                         "gross_spread_before_expenses": facts[0] - facts[1] if facts[1] is not None else None,
                         "cached_stock": facts[2], "catalog_synced_at": facts[3]},
    "reports": reports,
    "limitations": [
        "The code commit time is an observation boundary, not a confirmed runtime activation or post attribution.",
        "First-touch source is shared with older posts; a count after START does not prove acquisition by CapCut.",
        "Previous seven days are context, not an equal-duration controlled experiment or causal baseline.",
        "Price and cached inventory must be rechecked before publication; no purchase or voucher is attempted.",
        "Admin IDs are used only for filtering and are never included in output.",
    ],
}
destination = Path(__file__).with_name("cohort-proof.json")
destination.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"observed_at": NOW.isoformat(), "independent_sql_matches": True,
                  "cohort": reports["after_code_commit"]["cohort"],
                  "product_economics": proof["product_economics"]}, ensure_ascii=False))
