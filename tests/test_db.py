import sys, os
sys.path.insert(0, '/home/vu/toolsauto')
from app.core.database.core import SessionLocal
from app.core.database.models import Job, NewsArticle

db = SessionLocal()
print('--- Recent Threads Jobs ---')
jobs = db.query(Job).filter(Job.platform == 'threads').order_by(Job.id.desc()).limit(3).all()
for j in jobs:
    print(f'Job #{j.id} | Status: {j.status} | Caption: {j.caption[:60]}... | Error: {j.last_error}')

print('\n--- Recent News Articles ---')
articles = db.query(NewsArticle).order_by(NewsArticle.id.desc()).limit(3).all()
for a in articles:
    print(f'Article #{a.id} | Status: {a.status} | Title: {a.title[:60]}...')
