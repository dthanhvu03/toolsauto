from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.services.telegram_service import TelegramService

router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/callback")
async def telegram_callback(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid json"}

    callback_query = body.get("callback_query")
    if not callback_query:
        return {"ok": True}

    TelegramService.process_callback(db, callback_query)
    return {"ok": True}
