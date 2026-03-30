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

    columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(viral_materials)").fetchall()
    }
    if "last_error" not in columns:
        cursor.execute("ALTER TABLE viral_materials ADD COLUMN last_error VARCHAR")
        print("Added viral_materials.last_error")
    else:
        print("viral_materials.last_error already exists")

    conn.commit()
    conn.close()
    print("Migration finished.")


if __name__ == "__main__":
    migrate()
