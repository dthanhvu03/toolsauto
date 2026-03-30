import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.core import SessionLocal
from app.database.models import Job, ViralMaterial

db = SessionLocal()
jobs = db.query(Job).filter(Job.status.in_(['PENDING', 'DRAFT', 'AWAITING_STYLE', 'AI_PROCESSING'])).all()
mismatched = []
fixed = 0

for j in jobs:
    if not j.media_path: continue
    m = re.search(r'viral_(\d+)_', j.media_path)
    if not m: continue
    vid = int(m.group(1))
    v = db.query(ViralMaterial).filter(ViralMaterial.id == vid).first()
    if v and v.target_page and j.target_page != v.target_page:
        mismatched.append((j.id, j.target_page, v.target_page, j.status))
        j.target_page = v.target_page
        fixed += 1

print(f"Found {len(mismatched)} mismatched jobs.")
for m in mismatched[:10]:
    print(m)

if fixed:
    db.commit()
    print(f"Fixed {fixed} jobs.")

db.close()
