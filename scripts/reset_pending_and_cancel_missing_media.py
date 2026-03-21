import argparse
import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from app.database.core import engine  # noqa: E402
import app.config as config  # noqa: E402


def _pick_media_path(row) -> str | None:
    p1 = row.get("processed_media_path") or None
    p2 = row.get("media_path") or None
    return p1 or p2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="Limit rows scanned for missing media (0 = all)")
    args = ap.parse_args()

    db_path = os.getenv("DB_PATH", config.DB_PATH)
    now = int(time.time())

    reset_ids = []
    cancel_ids = []

    with engine.begin() as conn:
        # 1) Reset PENDING schedule_ts to now
        pending_rows = conn.execute(
            text("SELECT id FROM jobs WHERE status='PENDING'")
        ).fetchall()
        reset_ids = [int(r[0]) for r in pending_rows]

        # 2) Cancel missing media for non-DONE
        sql = "SELECT id, status, media_path, processed_media_path FROM jobs WHERE status != 'DONE'"
        if args.limit and args.limit > 0:
            sql += " LIMIT :lim"
            rows = conn.execute(text(sql), {"lim": int(args.limit)}).mappings().all()
        else:
            rows = conn.execute(text(sql)).mappings().all()

        missing = []
        for r in rows:
            path = _pick_media_path(r)
            if not path:
                missing.append((int(r["id"]), r["status"], None))
                continue
            p = Path(str(path))
            if not p.exists():
                missing.append((int(r["id"]), r["status"], str(p)))

        cancel_ids = [m[0] for m in missing]

        print("DB:", db_path)
        print("Dry-run:", (not args.apply))
        print("PENDING reset count:", len(reset_ids))
        print("Missing-media cancel count (non-DONE):", len(cancel_ids))
        if reset_ids:
            print("Reset sample ids:", reset_ids[:20])
        if cancel_ids:
            print("Cancel sample ids:", cancel_ids[:20])

        if not args.apply:
            return

        if reset_ids:
            conn.execute(
                text("UPDATE jobs SET schedule_ts=:now WHERE status='PENDING'"),
                {"now": now},
            )

        if cancel_ids:
            # Update per-id only (avoid accidental broad updates when one path is NULL but the other exists)
            for job_id, st, pth in missing:
                err = "Missing media file (path null/empty)" if not pth else f"Missing media file: {pth}"
                conn.execute(
                    text(
                        "UPDATE jobs SET status='CANCELLED', last_error=:err, finished_at=:now "
                        "WHERE id=:id AND status != 'DONE'"
                    ),
                    {"err": err, "now": now, "id": int(job_id)},
                )

        print("APPLIED OK.")


if __name__ == "__main__":
    main()

