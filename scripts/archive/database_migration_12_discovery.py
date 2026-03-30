"""
Migration 12: Create discovered_channels table for Automated Competitor Discovery.

Stores TikTok channels found via hashtag/keyword search, scored by avg views and post frequency.
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

    tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    if "discovered_channels" in tables:
        print("Table discovered_channels already exists, skipping.")
    else:
        cursor.execute("""
            CREATE TABLE discovered_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER REFERENCES accounts(id),
                channel_url VARCHAR NOT NULL,
                channel_name VARCHAR,
                keyword_used VARCHAR,
                follower_count INTEGER DEFAULT 0,
                video_count INTEGER DEFAULT 0,
                avg_views INTEGER DEFAULT 0,
                post_frequency REAL DEFAULT 0.0,
                score REAL DEFAULT 0.0,
                status VARCHAR DEFAULT 'NEW',
                discovered_at INTEGER,
                created_at INTEGER,
                updated_at INTEGER
            )
        """)
        cursor.execute("CREATE INDEX ix_discovered_channels_account_id ON discovered_channels(account_id)")
        cursor.execute("CREATE INDEX ix_discovered_channels_status ON discovered_channels(status)")
        cursor.execute("CREATE INDEX ix_discovered_channels_score ON discovered_channels(score)")
        cursor.execute("CREATE UNIQUE INDEX ix_discovered_channels_url_acc ON discovered_channels(channel_url, account_id)")
        print("Created table discovered_channels with indexes.")

    conn.commit()
    conn.close()
    print("Migration finished.")


if __name__ == "__main__":
    migrate()
