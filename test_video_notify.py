import logging
logging.basicConfig(level=logging.DEBUG)
from app.database.core import SessionLocal
from app.database.models import Job
from app.services.notifier import NotifierService, TelegramNotifier
import app.config as config

def test_notify():
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == 198).first()
    if not job:
        print("Job not found")
        return
        
    print(f"Testing notify for Job {job.id} with video: {job.media_path}")
    
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
    NotifierService.notify_draft_ready(job)
    print("Notification sent!")

if __name__ == "__main__":
    test_notify()
