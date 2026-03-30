"""
Migration: Add managed_pages column to accounts table.
Run: python scripts/migrate_managed_pages.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "auto_publisher.db")

def migrate():
    db_path = os.path.abspath(DB_PATH)
    print(f"Migrating: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "managed_pages" in columns:
        print("  ✅ Column 'managed_pages' already exists. Skipping.")
    else:
        cursor.execute("ALTER TABLE accounts ADD COLUMN managed_pages TEXT")
        conn.commit()
        print("  ✅ Added 'managed_pages' column to accounts table.")
    
    # Verify
    cursor.execute("SELECT count(*) FROM accounts")
    count = cursor.fetchone()[0]
    print(f"  📊 Total accounts: {count}")
    
    conn.close()
    print("Done.")

if __name__ == "__main__":
    migrate()
