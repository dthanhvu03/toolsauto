"""
Migration 11: Add target_pages column to accounts table.

Keeps the old target_page column for backward compat.
New column stores JSON array of page URLs, e.g. ["https://fb.com/page1", "https://fb.com/page2"].
If account already has a single target_page, seeds target_pages with it.
"""
import json
import os
import sqlite3
import sys


def migrate():
    sys.path.insert(0, os.path.abspath("."))
    try:
        from app.config import DB_PATH
        actual_path = DB_PATH.replace("sqlite:///", "")
    except ImportError:
        actual_path = "data/auto_publisher.db"

    print(f"Connecting to database at: {actual_path}")
    conn = sqlite3.connect(actual_path)
    cursor = conn.cursor()

    columns = {row[1] for row in cursor.execute("PRAGMA table_info(accounts)").fetchall()}

    if "target_pages" not in columns:
        cursor.execute("ALTER TABLE accounts ADD COLUMN target_pages VARCHAR")
        print("Added accounts.target_pages column.")
    else:
        print("accounts.target_pages already exists, skipping ALTER.")

    rows = cursor.execute(
        "SELECT id, target_page, target_pages FROM accounts "
        "WHERE target_page IS NOT NULL AND target_page != '' "
        "AND (target_pages IS NULL OR target_pages = '')"
    ).fetchall()

    seeded = 0
    for row_id, tp, existing_tps in rows:
        pages = [tp.strip()]
        cursor.execute(
            "UPDATE accounts SET target_pages = ? WHERE id = ?",
            (json.dumps(pages, ensure_ascii=False), row_id),
        )
        seeded += 1
        print(f"  Account {row_id}: seeded target_pages from target_page '{tp}'")

    conn.commit()
    conn.close()
    print(f"\nMigration finished. Column added. {seeded} accounts seeded from existing target_page.")


if __name__ == "__main__":
    migrate()
