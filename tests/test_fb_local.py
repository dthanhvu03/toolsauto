import sys, os
sys.path.insert(0, '/home/vu/toolsauto')
from app.core.database.core import SessionLocal
from app.core.database.models import Job, Account
from app.adapters.dispatcher import Dispatcher
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

db = SessionLocal()
job = db.query(Job).filter(Job.id == 470).first()
if job:
    print(f'Testing Job {job.id}...')
    job.status = 'PENDING'
    job.media_path = '/home/vu/toolsauto/storage/media/reup/tiktok/viral_799_tikwm_reup.mp4'
    job.processed_media_path = None
    db.commit()
    try:
        Dispatcher.dispatch(job, db)
    except Exception as e:
        print(f'Error: {e}')
else:
    print('No job found.')
