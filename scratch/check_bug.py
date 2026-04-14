import sqlite3
import os

db_path = '/home/vu/toolsauto/data/auto_publisher.db'
if not os.path.exists(db_path):
    # try relative
    db_path = 'data/auto_publisher.db'

print(f"Checking DB: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Check table/view
cur.execute("SELECT type, name FROM sqlite_master WHERE name='page_insights'")
print(f"Type of 'page_insights': {cur.fetchone()}")

# 2. Check for duplicate post_urls
cur.execute("""
    SELECT post_url, COUNT(*) as cnt, GROUP_CONCAT(COALESCE(caption, 'NULL'), ' | ') 
    FROM page_insights 
    GROUP BY post_url 
    HAVING cnt > 1 
    LIMIT 5
""")
print("\n--- Duplicate post_urls in page_insights ---")
for r in cur.fetchall():
    print(r)

# 3. Check for "Views:" captions
cur.execute("SELECT id, caption, post_url FROM page_insights WHERE caption LIKE '%Views:%' LIMIT 5")
print("\n--- Captions containing 'Views:' ---")
for r in cur.fetchall():
    print(r)

# 4. Check job distribution
cur.execute("SELECT job_type, COUNT(*) FROM jobs WHERE status='DONE' GROUP BY job_type")
print("\n--- Job Type Distribution ---")
print(cur.fetchall())

conn.close()
