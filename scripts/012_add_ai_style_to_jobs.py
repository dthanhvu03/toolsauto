import sqlite3
import os
import sys

# Try to resolve path based on where it's run
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, "data", "auto_publisher.db")

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    sys.exit(1)

print(f"Connecting to database at {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("Adding ai_style column to jobs table...")
    cursor.execute("ALTER TABLE jobs ADD COLUMN ai_style TEXT DEFAULT 'short';")
    print("Column added successfully!")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("Column ai_style already exists. Good to go!")
    else:
        print(f"Error: {e}")
        conn.rollback()
        sys.exit(1)

conn.commit()
conn.close()
print("Migration complete!")
