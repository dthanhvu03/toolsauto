from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.database.models import Job
from app.services.job import JobService
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/callback")
async def telegram_callback(request: Request, db: Session = Depends(get_db)):
    """
    Nhận callback từ Telegram khi user click inline button.
    Telegram gửi JSON update chứa callback_query.
    """
    from app.services.telegram_client import TelegramClient

    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid json"}

    callback_query = body.get("callback_query")
    if not callback_query:
        return {"ok": True}  # Ignore non-callback updates

    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")  # e.g. "approve:123"
    message = callback_query.get("message", {})
    message_id = message.get("message_id")
    user_name = callback_query.get("from", {}).get("first_name", "User")

    # Parse action:job_id
    parts = data.split(":", 1)
    if len(parts) != 2:
        return {"ok": True}

    action, job_id_str = parts
    try:
        job_id = int(job_id_str)
    except ValueError:
        return {"ok": True}

    client = TelegramClient(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        client.answer_callback_query(callback_id, "❌ Job không tồn tại!")
        return {"ok": True}

    if action == "approve":
        if job.status != "DRAFT":
            client.answer_callback_query(callback_id, f"⚠️ Job #{job_id} đã ở trạng thái {job.status}")
        else:
            job.status = "PENDING"
            job.is_approved = True
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Approved via Telegram by {user_name}")
            client.answer_callback_query(callback_id, f"✅ Job #{job_id} đã được duyệt!")
            # Update message: remove buttons, add confirmation
            client.edit_message_reply_markup(message_id, reply_markup=None)

    elif action == "cancel":
        if job.status not in ("DRAFT", "PENDING"):
            client.answer_callback_query(callback_id, f"⚠️ Job #{job_id} đã ở trạng thái {job.status}")
        else:
            job.status = "CANCELLED"
            db.commit()
            JobService._log_event(db, job_id, "INFO", f"Cancelled via Telegram by {user_name}")
            client.answer_callback_query(callback_id, f"❌ Job #{job_id} đã bị hủy!")
            client.edit_message_reply_markup(message_id, reply_markup=None)

    else:
        client.answer_callback_query(callback_id, "⚠️ Unknown action")

    return {"ok": True}
