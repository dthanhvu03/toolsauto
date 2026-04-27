from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List
import time
import logging
from zoneinfo import ZoneInfo
from app.config import TIMEZONE

from app.database.core import get_db
from app.services.job import JobService

from app.main_templates import templates


router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

@router.get("/table", response_class=HTMLResponse)
def get_jobs_table(
    request: Request, 
    status: str = "active",
    page: int = 1,
    per_page: int = 20,
    q: str = "",
    db: Session = Depends(get_db)
):
    """HTMX fragment: Returns the full jobs table with filter + pagination."""
    res = JobService.get_jobs_paged(db, status=status, page=page, per_page=per_page, q=q)
    
    return templates.TemplateResponse(
        "fragments/jobs_table.html", 
        {
            "request": request, 
            "jobs": res["jobs"], 
            "current_status": status,
            "current_page": res["page"],
            "total_pages": res["total_pages"],
            "total_jobs": res["total"],
            "per_page": per_page,
            "q": q,
            "now": int(time.time())
        }
    )
    
@router.get("/{job_id}/row", response_class=HTMLResponse)
def get_job_row(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: Returns a single job row."""
    job = JobService.get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/retry", response_class=HTMLResponse)
def retry_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        JobService.retry_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Retry failed for job {job_id}: {e}")
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/reset-draft", response_class=HTMLResponse)
def reset_job_to_draft(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        JobService.reset_to_draft(db, job_id)
    except ValueError as e:
        logger.warning(f"Reset-draft failed for job {job_id}: {e}")
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/cancel", response_class=HTMLResponse)
def cancel_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        JobService.cancel_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Cancel failed for job {job_id}: {e}")
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/reschedule", response_class=HTMLResponse)
def reschedule_job(job_id: int, request: Request, new_date: str = Form(...), new_time: str = Form(...), db: Session = Depends(get_db)):
    try:
        from datetime import datetime
        dt_naive = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
        JobService.reschedule_job(db, job_id, int(dt_aware.timestamp()))
    except Exception as e:
        logger.warning(f"Reschedule failed for job {job_id}: {e}")
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/force-run", response_class=HTMLResponse)
def force_run_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        JobService.force_run_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Force-run failed for job {job_id}: {e}")
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/approve", response_class=HTMLResponse)
def approve_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    JobService.approve_job(db, job_id)
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/{job_id}/caption", response_class=HTMLResponse)
def update_job_caption(job_id: int, request: Request, caption: str = Form(""), db: Session = Depends(get_db)):
    JobService.update_job_caption(db, job_id, caption)
    job = JobService.get_job_by_id(db, job_id)
    return templates.TemplateResponse("fragments/job_row.html", {"request": request, "job": job, "now": int(time.time())})

@router.post("/create", response_class=HTMLResponse)
def create_job(
    request: Request,
    account_id: int = Form(...),
    media_file: UploadFile = File(...),
    caption: str = Form(""),
    schedule_time: str = Form(...),
    randomize_caption: bool = Form(False),
    affiliate_url: str = Form(""),
    target_page: str = Form(""),
    db: Session = Depends(get_db)
):
    from app.services.account import AccountService
    accounts = AccountService.get_active_accounts(db)
    try:
        from datetime import datetime
        dt_naive = datetime.strptime(schedule_time, "%Y-%m-%dT%H:%M")
        dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
        schedule_ts = int(dt_aware.timestamp())
        
        job = JobService.create_job_from_upload(
            db, account_id, media_file, caption, schedule_ts, randomize_caption, affiliate_url, target_page
        )
        return templates.TemplateResponse("fragments/create_job_form.html", {"request": request, "accounts": accounts, "success": True, "new_job": job})
    except Exception as e:
        return templates.TemplateResponse("fragments/create_job_form.html", {"request": request, "accounts": accounts, "error": str(e)})

@router.post("/bulk_create", response_class=HTMLResponse)
async def bulk_create_jobs(
    request: Request,
    account_id: int = Form(...),
    media_files: List[UploadFile] = File(...),
    captions: List[str] = Form(...),
    schedule_times: List[str] = Form(...),
    randomize_caption: bool = Form(False),
    affiliate_url: str = Form(""),
    auto_comment_text: str = Form(""),
    target_page: str = Form(""),
    db: Session = Depends(get_db)
):
    from app.services.account import AccountService
    accounts = AccountService.get_active_accounts(db)
    try:
        batch_id = JobService.bulk_create_jobs_from_uploads(
            db, account_id, media_files, captions, schedule_times, randomize_caption, affiliate_url, auto_comment_text, target_page
        )
        return templates.TemplateResponse("fragments/create_job_form.html", {"request": request, "accounts": accounts, "success": True, "bulk_success": True})
    except Exception as e:
        logger.error(f"Bulk failed: {e}")
        return templates.TemplateResponse("fragments/create_job_form.html", {"request": request, "accounts": accounts, "error": str(e)})
 
@router.get("/{job_id}/details", response_class=HTMLResponse)
def get_job_details(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = JobService.get_job_by_id(db, job_id)
    if not job: raise HTTPException(status_code=404)
    events = JobService.get_job_events(db, job_id, limit=20)
    return templates.TemplateResponse("fragments/job_details.html", {"request": request, "job": job, "events": events, "now": int(time.time())})
