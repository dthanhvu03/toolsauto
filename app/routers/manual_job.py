from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
import os
import time
import uuid
import shutil
import logging
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.database.models import Account, Job
from app.main_templates import templates

router = APIRouter(prefix="/jobs/manual", tags=["manual-jobs"])
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_DIR = os.path.join(BASE_DIR, "content", "manual")


@router.get("/form", response_class=HTMLResponse)
def manual_job_form(request: Request, db: Session = Depends(get_db)):
    """Return the manual-job creation form (called via HTMX into a modal)."""
    accounts = db.query(Account).filter(Account.is_active == True, Account.login_status == "ACTIVE").all()
    pages_by_acc = []
    for acc in accounts:
        for pg in (acc.managed_pages_list or []):
            pages_by_acc.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "page_url": pg.get("url", ""),
                "page_name": pg.get("name", pg.get("url", "")),
            })
    return templates.TemplateResponse("fragments/manual_job_form.html", {
        "request": request,
        "pages": pages_by_acc,
    })


@router.post("/create", response_class=HTMLResponse)
async def manual_job_create(
    request: Request,
    account_id: int = Form(...),
    target_page: str = Form(...),
    caption: str = Form(""),
    media: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """Create a high-priority manual job, bypassing AI and crawl stages."""
    os.makedirs(MANUAL_DIR, exist_ok=True)
    
    media_path = None
    if media and media.filename:
        ext = media.filename.rsplit(".", 1)[-1] if "." in media.filename else "mp4"
        filename = f"manual_{uuid.uuid4().hex[:8]}.{ext}"
        dest = os.path.join(MANUAL_DIR, filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(media.file, f)
        media_path = dest

    try:
        job = Job(
            platform="facebook",
            account_id=account_id,
            target_page=target_page,
            caption=caption.strip() or None,
            media_path=media_path,
            status="PENDING",
            schedule_ts=int(time.time()),
            tries=0,
            max_tries=3,
        )
        # Give this job the highest priority by setting a very early schedule timestamp
        job.schedule_ts = int(time.time()) - 999999  # Forces it to the front of queue
        db.add(job)
        db.commit()
        db.refresh(job)
        msg = f"✅ Job #{job.id} đã được thêm vào Queue với độ ưu tiên tối đa!"
    except Exception as e:
        logger.error(f"Manual job create error: {e}")
        msg = f"❌ Lỗi tạo Job: {e}"

    return HTMLResponse(
        f'<div class="p-3 text-sm rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium">{msg}</div>'
        f'<script>if(window.refreshJobs) window.refreshJobs(1); setTimeout(() => document.getElementById("manualJobDialog").close(), 2000);</script>'
    )
