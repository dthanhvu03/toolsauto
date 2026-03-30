"""
Migration 10: Convert competitor_urls from list-of-strings to list-of-objects.

Before: ["https://tiktok.com/@a", "https://tiktok.com/@b"]
After:  [{"url": "https://tiktok.com/@a", "target_page": null}, {"url": "https://tiktok.com/@b", "target_page": null}]

This enables mapping each competitor URL to a specific Facebook target page.
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

    rows = cursor.execute(
        "SELECT id, competitor_urls FROM accounts "
        "WHERE competitor_urls IS NOT NULL AND competitor_urls != ''"
    ).fetchall()

    migrated = 0
    skipped = 0
    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data = [u.strip() for u in raw.split(",") if u.strip()]

        if not isinstance(data, list):
            data = [str(data)]

        if data and isinstance(data[0], dict) and "url" in data[0]:
            print(f"  Account {row_id}: already in new format, skipping")
            skipped += 1
            continue

        new_data = [{"url": str(u), "target_page": None} for u in data if u]
        new_json = json.dumps(new_data, ensure_ascii=False)

        cursor.execute(
            "UPDATE accounts SET competitor_urls = ? WHERE id = ?",
            (new_json, row_id),
        )
        migrated += 1
        print(f"  Account {row_id}: migrated {len(new_data)} URLs")

    conn.commit()
    conn.close()
    print(f"\nMigration finished. {migrated} accounts updated, {skipped} already current.")


if __name__ == "__main__":
    migrate()
