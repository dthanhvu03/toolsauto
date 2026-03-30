import sqlite3
import os
import sys

def migrate():
    sys.path.insert(0, os.path.abspath('.'))
    try:
        from app.config import DB_PATH
        actual_path = DB_PATH.replace('sqlite:///', '')
    except ImportError:
        actual_path = "data/auto_publisher.db"
        
    print(f"Connecting to database at: {actual_path}")
    conn = sqlite3.connect(actual_path)
    cursor = conn.cursor()

    sql = """
    CREATE TABLE IF NOT EXISTS viral_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform VARCHAR DEFAULT 'facebook',
        url VARCHAR UNIQUE,
        title VARCHAR,
        views INTEGER DEFAULT 0,
        scraped_by_account_id INTEGER,
        status VARCHAR DEFAULT 'NEW',
        created_at INTEGER,
        updated_at INTEGER,
        FOREIGN KEY(scraped_by_account_id) REFERENCES accounts(id)
    );
    """
    
    try:
        cursor.execute(sql)
        print("Created table viral_materials")
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_viral_materials_platform ON viral_materials(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_viral_materials_url ON viral_materials(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_viral_materials_views ON viral_materials(views)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_viral_materials_status ON viral_materials(status)")
        print("Created indexes for viral_materials")
    except sqlite3.OperationalError as e:
        print(f"Error creating table: {e}")

    conn.commit()
    conn.close()
    print("Migration finished.")

if __name__ == "__main__":
    migrate()
