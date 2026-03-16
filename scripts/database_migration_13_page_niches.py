"""
Migration 13: Add page_niches column to accounts.

Stores per-page niches mapping as JSON string.
"""
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
    if "page_niches" not in columns:
        cursor.execute("ALTER TABLE accounts ADD COLUMN page_niches VARCHAR")
        print("Added accounts.page_niches column.")
    else:
        print("accounts.page_niches already exists, skipping.")

    conn.commit()
    conn.close()
    print("Migration finished.")


if __name__ == "__main__":
    migrate()
