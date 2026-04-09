import sqlite3, os
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'auto_publisher.db')
print('DB path:', db_path, 'Exists:', os.path.exists(db_path))
conn = sqlite3.connect(db_path)
print('Tables:', [r[0] for r in conn.execute(chr(34+49)+'SELECT name FROM sqlite_master WHERE type='+chr(39)+'table'+chr(39)+chr(34+49)).fetchall()])
conn.close()
