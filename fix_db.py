import sqlite3
import json
import os

db_path = os.path.join(os.path.dirname(__file__), 'data/auto_publisher.db')
conn = sqlite3.connect(db_path)
steps = ["open_session", "navigate_to_post", "dismiss_overlay", "focus_comment_box", "write_comment", "submit_comment", "delay_random", "verify_posted", "close_session"]
conn.execute('UPDATE workflow_definitions SET steps=? WHERE name=?', (json.dumps(steps), 'comment_facebook'))
conn.commit()
print("Fixed DB")
