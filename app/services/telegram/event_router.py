import logging
from app.constants import JobStatus

logger = logging.getLogger(__name__)

class TelegramEventRouter:
    def __init__(self, client, command_handler):
        self.client = client
        self.command_handler = command_handler

    def dispatch(self, update: dict):
        if "message" in update:
            self._handle_message(update["message"])
        elif "callback_query" in update:
            self._handle_callback_query(update["callback_query"])

    def _handle_message(self, message: dict):
        text = message.get("text", "")
        if not text.startswith("/"): return
        parts = text.split()
        cmd = parts[0][1:].split("@")[0].lower()
        args = parts[1:]
        self.command_handler.handle_command(cmd, args)

    def _handle_callback_query(self, query: dict):
        callback_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        message_id = message.get("message_id")
        user = query.get("from", {}).get("first_name", "User")

        if ":" not in data: return
        action, target_id = data.split(":", 1)
        
        try:
            if action == "approve":
                self._handle_approve(callback_id, int(target_id), message_id, user)
            elif action == "cancel":
                self._handle_cancel(callback_id, int(target_id), message_id, user)
            elif action.startswith("style"):
                self._handle_style(callback_id, data, int(target_id), message_id, user)
        except Exception as e:
            logger.exception("[Telegram] Callback failed")
            self.client.answer_callback_query(callback_id, f"❌ Lỗi: {e}")

    def _handle_approve(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status != JobStatus.DRAFT:
                self.client.answer_callback_query(callback_id, "❌ Job không hợp lệ")
                return
            job.status = JobStatus.PENDING
            job.is_approved = True
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Approved by {user_name}")
        self.client.answer_callback_query(callback_id, f"✅ Job #{job_id} approved")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
        self.client.send_message(f"✅ Approved Job #{job_id} by {user_name}")

    def _handle_cancel(self, callback_id: str, job_id: int, message_id: int, user_name: str):
        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.job import JobService
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status not in (JobStatus.DRAFT, JobStatus.PENDING):
                self.client.answer_callback_query(callback_id, "❌ Không thể hủy Job này")
                return
            job.status = JobStatus.CANCELLED
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Cancelled by {user_name}")
        self.client.answer_callback_query(callback_id, f"❌ Job #{job_id} cancelled")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
        self.client.send_message(f"❌ Cancelled Job #{job_id} by {user_name}")

    def _handle_style(self, callback_id: str, action: str, job_id: int, message_id: int, user_name: str):
        from app.database.core import SessionLocal
        from app.database.models import Job
        from app.services.notifier_service import NotifierService
        style = action.split("_")[1]
        with SessionLocal() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or job.status != JobStatus.AWAITING_STYLE:
                self.client.answer_callback_query(callback_id, "❌ Sai trạng thái")
                return
            if style == "skip":
                job.status = JobStatus.DRAFT
                if job.caption: job.caption = job.caption.replace("[AI_GENERATE]", "").strip()
                db.commit()
                NotifierService.notify_draft_ready(job)
            else:
                job.ai_style = style
                job.status = JobStatus.DRAFT
                db.commit()
        self.client.answer_callback_query(callback_id, f"✅ Style: {style}")
        self.client.edit_message_reply_markup(message_id, reply_markup=None)
