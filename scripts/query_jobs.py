import sys, os
sys.path.insert(0, "/home/vu/toolsauto")
from app.database.core import SessionLocal
from app.database.models import Job, Account

db = SessionLocal()

# List recent jobs with existing video
jobs = db.query(Job).order_by(Job.id.desc()).limit(10).all()
for j in jobs:
    path = j.resolved_processed_media_path or j.resolved_media_path
    exists = os.path.exists(path) if path else False
    mark = "✅" if exists else "❌"
    print(f"  {mark} Job {j.id} | {j.status} | acc={j.account_id} | page={j.target_page} | {os.path.basename(path or '')}")

db.close()
