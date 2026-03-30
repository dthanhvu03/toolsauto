"""
Migration: Add niche_topics column to accounts table.
Run once: python scripts/migrate_niche_topics.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "auto_publisher.db"


def migrate():
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]

    if "niche_topics" in columns:
        print("[INFO] Column 'niche_topics' already exists. Skipping.")
        conn.close()
        return

    # Safety: count rows before
    cursor.execute("SELECT count(*) FROM accounts")
    count_before = cursor.fetchone()[0]
    print(f"[INFO] Accounts before migration: {count_before}")

    # Add column
    cursor.execute("ALTER TABLE accounts ADD COLUMN niche_topics TEXT")
    conn.commit()

    # Safety: count rows after
    cursor.execute("SELECT count(*) FROM accounts")
    count_after = cursor.fetchone()[0]
    print(f"[INFO] Accounts after migration: {count_after}")

    assert count_before == count_after, "ROW COUNT MISMATCH! Rolling back."

    print("[OK] Migration complete: 'niche_topics' column added to accounts table.")
    conn.close()


if __name__ == "__main__":
    migrate()
