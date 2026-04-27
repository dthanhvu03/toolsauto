import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.database.models import Job
from app.services.job import JobService
from app.services.telegram_client import TelegramClient
from app.constants import JobStatus
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramService:

    @staticmethod
    def process_callback(db: Session, callback_query: Dict[str, Any]) -> bool:
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")
        user_name = callback_query.get("from", {}).get("first_name", "User")

        parts = data.split(":", 1)
        if len(parts) != 2:
            return False

        action, job_id_str = parts
        try:
            job_id = int(job_id_str)
        except ValueError:
            return False

        client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        job = db.query(Job).filter(Job.id == job_id).first()

        if not job:
            client.answer_callback_query(callback_id, "❌ Job không tồn tại!")
            return True

        if action == "approve":
            if job.status != JobStatus.DRAFT:
                client.answer_callback_query(callback_id, f"⚠️ Job #{job_id} đã ở trạng thái {job.status}")
            else:
                job.status = JobStatus.PENDING
                job.is_approved = True
                db.commit()
                JobService._log_event(db, job_id, "INFO", f"Approved via Telegram by {user_name}")
                client.answer_callback_query(callback_id, f"✅ Job #{job_id} đã được duyệt!")
                client.edit_message_reply_markup(message_id, reply_markup=None)

        elif action == "cancel":
            if job.status not in (JobStatus.DRAFT, JobStatus.PENDING):
                client.answer_callback_query(callback_id, f"⚠️ Job #{job_id} đã ở trạng thái {job.status}")
            else:
                job.status = JobStatus.CANCELLED
                db.commit()
                JobService._log_event(db, job_id, "INFO", f"Cancelled via Telegram by {user_name}")
                client.answer_callback_query(callback_id, f"❌ Job #{job_id} đã bị hủy!")
                client.edit_message_reply_markup(message_id, reply_markup=None)
        
        return True
