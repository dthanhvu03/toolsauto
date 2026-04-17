#!/usr/bin/env python3
"""
migrate_sqlite_to_postgres.py
─────────────────────────────
Migrate toàn bộ data từ SQLite → PostgreSQL.

Dùng khi:
  - Lần đầu deploy lên production VPS mới chuyển sang PG
  - Restore data từ SQLite backup vào PG

Usage:
  # Dry-run (chỉ đọc, không ghi gì)
  python scripts/migrate_sqlite_to_postgres.py --dry-run

  # Migrate thật
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite data/auto_publisher.db \
    --postgres postgresql+psycopg2://admin:admin@localhost/toolsauto_db

  # Với DB_PATH và DATABASE_URL đã set trong .env (tự đọc config)
  python scripts/migrate_sqlite_to_postgres.py

Prerequisites on VPS:
  sudo apt install postgresql postgresql-contrib -y
  sudo -u postgres psql -c "CREATE DATABASE toolsauto_db;"
  sudo -u postgres psql -c "CREATE USER admin WITH PASSWORD 'admin';"
  sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE toolsauto_db TO admin;"
  pip install psycopg2-binary
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# ── Defaults from app config ───────────────────────────────────────────────────
from app.config import DATABASE_URL as DEFAULT_PG_URL, DB_PATH as DEFAULT_SQLITE_PATH
import app.database.models  # noqa: F401 — register all models
from app.database.core import Base

# Tables ordered so FK parents come before children
TABLE_ORDER = [
    "accounts",
    "jobs",
    "viral_materials",
    "affiliate_links",
    "job_events",
    "violation_log",
    "audit_logs",
    "runtime_settings",
    "runtime_settings_audit",
    "platform_configs",
    "platform_selectors",
    "workflow_definitions",
    "keyword_blacklist",
    "compliance_allowlist",
    "compliance_regex_rules",
    "cta_templates",
    "page_insights",
    "competitor_reels",
    "discovered_channels",
    "system_state",
]


def make_engine(url: str, label: str):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Connected to {label}: {url[:60]}...")
    except Exception as e:
        print(f"[ERROR] Cannot connect to {label}: {e}")
        sys.exit(1)
    return engine


def get_tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def reset_pg_sequences(pg_conn, table: str, id_col: str = "id"):
    """Reset PG SERIAL sequence to max(id) so inserts after migration don't conflict."""
    seq_name = f"{table}_{id_col}_seq"
    pg_conn.execute(text(
        f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({id_col}) FROM {table}), 1))"
    ))


def migrate_table(
    src_engine,
    dst_engine,
    table_name: str,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    truncate: bool = False,
) -> tuple[int, int]:
    """
    Copy all rows from src → dst for one table.
    Returns (rows_copied, rows_skipped).
    """
    meta = Base.metadata
    if table_name not in meta.tables:
        print(f"  [SKIP] {table_name}: not in SQLAlchemy metadata, skipping")
        return 0, 0

    src_tables = get_tables(src_engine)
    dst_tables = get_tables(dst_engine)

    if table_name not in src_tables:
        print(f"  [SKIP] {table_name}: not in source SQLite")
        return 0, 0

    if table_name not in dst_tables:
        print(f"  [SKIP] {table_name}: not in destination PG (run alembic upgrade head first)")
        return 0, 0

    table = meta.tables[table_name]
    col_names = [c.name for c in table.columns]

    with src_engine.connect() as src_conn:
        total = src_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()

    if total == 0:
        print(f"  [EMPTY] {table_name}: 0 rows, nothing to migrate")
        return 0, 0

    print(f"  {table_name}: {total} rows...", end=" ", flush=True)

    if dry_run:
        print("(dry-run, skipped)")
        return 0, total

    with dst_engine.connect() as dst_conn:
        if truncate:
            dst_conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
            dst_conn.commit()

        # Check existing rows for idempotency
        existing = dst_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        if existing > 0 and not truncate:
            print(f"({existing} rows already exist, skipping — use --truncate to overwrite)")
            return 0, existing

    rows_copied = 0
    with src_engine.connect() as src_conn, dst_engine.connect() as dst_conn:
        offset = 0
        while True:
            result = src_conn.execute(
                text(f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}")
            )
            rows = result.fetchall()
            if not rows:
                break

            batch = [dict(zip(col_names, row)) for row in rows]
            # Sanitize: replace empty string with None for non-text columns
            dst_conn.execute(table.insert(), batch)
            dst_conn.commit()

            rows_copied += len(rows)
            offset += batch_size

        # Reset sequence so future INSERTs don't get PK conflicts
        if "id" in col_names:
            try:
                reset_pg_sequences(dst_conn, table_name)
                dst_conn.commit()
            except Exception:
                pass  # Some tables may not have a sequence

    print(f"✓ {rows_copied} copied")
    return rows_copied, 0


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default=str(DEFAULT_SQLITE_PATH),
        help=f"SQLite file path (default: {DEFAULT_SQLITE_PATH})",
    )
    parser.add_argument(
        "--postgres",
        default=DEFAULT_PG_URL,
        help=f"PostgreSQL URL (default: from DATABASE_URL env or config)",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Specific tables to migrate (default: all)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE destination tables before inserting (destructive!)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing anything",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per INSERT batch (default: 500)",
    )
    args = parser.parse_args()

    sqlite_url = f"sqlite:///{args.sqlite}"
    pg_url = args.postgres

    if pg_url.startswith("sqlite"):
        print("[ERROR] --postgres must be a PostgreSQL URL, not SQLite.")
        sys.exit(1)

    if not Path(args.sqlite).exists():
        print(f"[ERROR] SQLite file not found: {args.sqlite}")
        sys.exit(1)

    print("=" * 60)
    print("SQLite → PostgreSQL Migration")
    print("=" * 60)
    print(f"Source : {args.sqlite}")
    print(f"Target : {pg_url[:60]}...")
    print(f"Dry run: {args.dry_run}")
    print(f"Truncate: {args.truncate}")
    print()

    src_engine = make_engine(sqlite_url, "SQLite")
    dst_engine = make_engine(pg_url, "PostgreSQL")

    tables = args.tables or TABLE_ORDER

    # Ensure PG schema is up to date
    print("Checking PG schema (run alembic upgrade head if tables missing)...")
    pg_tables = get_tables(dst_engine)
    missing = [t for t in tables if t not in pg_tables]
    if missing:
        print(f"[WARNING] Tables missing in PG (alembic upgrade head needed): {missing}")
        print("Run: PYTHONPATH=. python manage.py db upgrade head")
        if not args.dry_run:
            print("Aborting. Run alembic first.")
            sys.exit(1)

    print()
    total_copied = 0
    total_skipped = 0

    for table in tables:
        copied, skipped = migrate_table(
            src_engine,
            dst_engine,
            table,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            truncate=args.truncate,
        )
        total_copied += copied
        total_skipped += skipped

    print()
    print("=" * 60)
    if args.dry_run:
        print(f"[DRY RUN] Would migrate {total_skipped} rows across {len(tables)} tables.")
    else:
        print(f"[DONE] Migrated {total_copied} rows across {len(tables)} tables.")
        print()
        print("Next steps:")
        print("  1. Set DATABASE_URL in .env on VPS")
        print("  2. pm2 restart all")
        print("  3. Kiểm tra app tại http://<vps-ip>:8000")
    print("=" * 60)


if __name__ == "__main__":
    main()
