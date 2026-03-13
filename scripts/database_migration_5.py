import sqlite3
import os
import sys

def migrate():
    sys.path.insert(0, os.path.abspath('.'))
    try:
        from app.config import DB_PATH
        # DB_PATH in config.py is sqlite:///data/auto_publisher.db
        # We need the actual file path
        actual_path = DB_PATH.replace('sqlite:///', '')
    except ImportError:
        actual_path = "data/auto_publisher.db"
        
    print(f"Connecting to database at: {actual_path}")
    conn = sqlite3.connect(actual_path)
    cursor = conn.cursor()

    columns_to_add = [
        ("sleep_start_time", "TEXT"),
        ("sleep_end_time", "TEXT")
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column {col_name} already exists.")
            else:
                print(f"Error adding {col_name}: {e}")

    conn.commit()
    conn.close()
    print("Migration finished.")

if __name__ == "__main__":
    migrate()
