import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "auto_publisher.db"))

def upgrade():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "last_metrics_check_ts" not in columns:
            print("Adding 'last_metrics_check_ts' column to 'jobs' table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN last_metrics_check_ts INTEGER")
            
            # Backfill existing checked metrics appropriately
            cursor.execute('''
                UPDATE jobs 
                SET last_metrics_check_ts = finished_at 
                WHERE metrics_checked = 1
            ''')
            
            print("Creating index 'idx_jobs_last_metrics_check'...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_metrics_check ON jobs(last_metrics_check_ts)")
            
            conn.commit()
            print("Migration successful.")
        else:
            print("Column 'last_metrics_check_ts' already exists. Skipping.")
            
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    upgrade()
