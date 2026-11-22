"""PLAN-180 read-only: đếm quote_source trong link_policy_snapshots. Không ghi DB."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cashback_bot.config import load_settings  # noqa: E402


def main() -> int:
    settings = load_settings()
    db = Path(settings.db_path)
    if not db.is_absolute():
        db = ROOT / db
    if not db.exists():
        print(json.dumps({"error": "db_missing", "path": str(db)}))
        return 1
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(link_policy_snapshots)")}
        if "quote_source" not in cols:
            print(json.dumps({"error": "quote_source_column_missing", "path": str(db)}))
            return 1
        rows = conn.execute(
            "SELECT COALESCE(quote_source, '(null)') AS src, COUNT(*) "
            "FROM link_policy_snapshots GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        recent = conn.execute(
            "SELECT COALESCE(quote_source, '(null)'), COUNT(*) FROM ("
            "  SELECT quote_source FROM link_policy_snapshots ORDER BY rowid DESC LIMIT 50"
            ") GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    finally:
        conn.close()
    out = {
        "at": datetime.now(timezone.utc).isoformat(),
        "plan": "PLAN-180",
        "db": str(db),
        "mode": "readonly",
        "all_time": {k: v for k, v in rows},
        "last_50": {k: v for k, v in recent},
        "primary": settings.product_quote_primary,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
