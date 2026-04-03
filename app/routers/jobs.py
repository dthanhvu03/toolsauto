from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
import time
import os
import uuid
import shutil
import hashlib
import logging
from zoneinfo import ZoneInfo
from app.config import TIMEZONE

from app.database.core import get_db
from app.database.models import Job, Account
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
    query = db.query(Job)
    
    # Status filter
    if status == "active":
        query = query.filter(Job.status.in_(["AWAITING_STYLE", "DRAFT", "PENDING", "RUNNING", "AI_PROCESSING"]))
    elif status in ("DRAFT", "PENDING", "RUNNING", "DONE", "FAILED", "CANCELLED"):
        query = query.filter(Job.status == status)
    # else "all" → no filter

    # Search filter (optional, backward compatible)
    q = (q or "").strip()
    if q:
        # If numeric, treat as possible job id
        if q.isdigit():
            query = query.filter(Job.id == int(q))
        else:
            query = query.join(Account, Job.account_id == Account.id).filter(
                or_(
                    Account.name.ilike(f"%{q}%"),
                    Job.target_page.ilike(f"%{q}%"),
                    Job.caption.ilike(f"%{q}%"),
                    Job.post_url.ilike(f"%{q}%"),
                )
            )
    
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    
    jobs = query.order_by(Job.schedule_ts.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    return templates.TemplateResponse(
        "fragments/jobs_table.html", 
        {
            "request": request, 
            "jobs": jobs, 
            "current_status": status,
            "current_page": page,
            "total_pages": total_pages,
            "total_jobs": total,
            "per_page": per_page,
            "q": q,
            "now": int(time.time())
        }
    )
    
@router.get("/{job_id}/row", response_class=HTMLResponse)
def get_job_row(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: Returns a single job row."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/retry", response_class=HTMLResponse)
def retry_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX action: Manual retry -> moves FAILED to PENDING."""
    try:
        JobService.retry_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Retry failed for job {job_id}: {e}")
        
    job = db.query(Job).filter(Job.id == job_id).first()
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/reset-draft", response_class=HTMLResponse)
def reset_job_to_draft(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX action: Resets AI_PROCESSING/FAILED/RUNNING -> DRAFT for re-processing."""
    try:
        JobService.reset_to_draft(db, job_id)
    except ValueError as e:
        logger.warning(f"Reset-draft failed for job {job_id}: {e}")
        
    job = db.query(Job).filter(Job.id == job_id).first()
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/cancel", response_class=HTMLResponse)
def cancel_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX action: Moves PENDING to CANCELLED."""
    try:
        JobService.cancel_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Cancel failed for job {job_id}: {e}")
        
    job = db.query(Job).filter(Job.id == job_id).first()
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/reschedule", response_class=HTMLResponse)
def reschedule_job(
    job_id: int, 
    request: Request, 
    new_date: str = Form(...),
    new_time: str = Form(...),
    db: Session = Depends(get_db)
):
    """HTMX action: Updates schedule_ts for PENDING."""
    try:
        # Parse datetime-local from HTML
        from datetime import datetime
        fmt = "%Y-%m-%d %H:%M"
        dt_naive = datetime.strptime(f"{new_date} {new_time}", fmt)
        dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
        new_ts = int(dt_aware.timestamp())
        JobService.reschedule_job(db, job_id, new_ts)
    except ValueError as e:
        logger.warning(f"Reschedule failed for job {job_id}: {e}")
    except Exception as e:
        logger.warning(f"Reschedule parse error for job {job_id}: {e}")
        
    job = db.query(Job).filter(Job.id == job_id).first()
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/force-run", response_class=HTMLResponse)
def force_run_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX action: Moves schedule_ts to now for PENDING."""
    try:
        JobService.force_run_job(db, job_id)
    except ValueError as e:
        logger.warning(f"Force-run failed for job {job_id}: {e}")
        
    job = db.query(Job).filter(Job.id == job_id).first()
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/approve", response_class=HTMLResponse)
def approve_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX action: Moves DRAFT to PENDING."""
    job = db.query(Job).filter(Job.id == job_id, Job.status == "DRAFT").first()
    if job:
        job.status = "PENDING"
        job.is_approved = True
        db.commit()
        JobService._log_event(db, job_id, "INFO", "User approved AI Draft")
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

@router.post("/{job_id}/caption", response_class=HTMLResponse)
def update_job_caption(
    job_id: int, 
    request: Request, 
    caption: str = Form(""),
    db: Session = Depends(get_db)
):
    """HTMX action: Updates caption for DRAFT jobs."""
    job = db.query(Job).filter(Job.id == job_id, Job.status == "DRAFT").first()
    if job:
        job.caption = caption
        db.commit()
        JobService._log_event(db, job_id, "INFO", "User edited Draft caption")
    return templates.TemplateResponse(
        "fragments/job_row.html", 
        {"request": request, "job": job, "now": int(time.time())}
    )

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
    """HTMX endpoint to create a manual job."""
    accounts = db.query(Account).all()
    try:
        from datetime import datetime
        
        # Parse the naive local datetime string from HTML5 datetime-local
        dt_naive = datetime.strptime(schedule_time, "%Y-%m-%dT%H:%M")
        
        # Enforce the system timezone explicitly to generate correct UTC epoch
        dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
        schedule_ts = int(dt_aware.timestamp())
        
        # Save the uploaded file
        if not media_file.filename:
            raise ValueError("No file uploaded or file is empty.")
            
        ext = os.path.splitext(media_file.filename)[1].lower()
        if not ext:
            ext = ".mp4" if "video" in media_file.content_type else ".jpg"
            
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        media_dir = os.path.abspath("content/media")
        os.makedirs(media_dir, exist_ok=True)
        
        # --- ATOMIC WRITE: temp file → fsync → rename ---
        import tempfile
        
        saved_path = os.path.join(media_dir, unique_filename)  # Final target path
        
        tmp_fd, tmp_path = tempfile.mkstemp(dir=media_dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                shutil.copyfileobj(media_file.file, tmp_file)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())  # Force bytes to disk before rename
        except Exception:
            os.unlink(tmp_path)   # Clean up temp file on error
            raise
        
        os.rename(tmp_path, saved_path)  # Atomic on Linux (same filesystem)
        logger.info(f"Saved uploaded media to: {saved_path}")
        
        # Verify file is non-empty
        if os.path.getsize(saved_path) == 0:
            os.unlink(saved_path)
            raise ValueError("Uploaded file is empty (0 bytes). Rejected.")
        
        # Compute dedupe_key = SHA256(account_id + uuid filename)
        dedupe_raw = f"{account_id}:{unique_filename}"
        dedupe_key = hashlib.sha256(dedupe_raw.encode()).hexdigest()[:16]
        
        job = JobService.create_job(
            db=db,
            account_id=account_id,
            media_path=saved_path,
            caption=caption,
            schedule_ts=schedule_ts,
            randomize_caption=randomize_caption,
            dedupe_key=dedupe_key,
            affiliate_url=affiliate_url,
            target_page=target_page.strip() if target_page else None
        )
        
        return templates.TemplateResponse(
            "fragments/create_job_form.html", 
            {
                "request": request, 
                "accounts": accounts, 
                "success": True, 
                "new_job": job
            }
        )
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return templates.TemplateResponse(
            "fragments/create_job_form.html", 
            {
                "request": request, 
                "accounts": accounts, 
                "error": str(e),
                "form_data": {
                    "account_id": account_id,
                    "media_path": getattr(media_file, "filename", ""),
                    "caption": caption,
                    "schedule_time": schedule_time,
                    "randomize_caption": randomize_caption
                }
            }
        )

@router.post("/bulk_create", response_class=HTMLResponse)
def bulk_create_jobs(
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
    """
    Orchestration endpoint for bulk creating jobs via drag and drop.
    """
    accounts = db.query(Account).all()
    try:
        from app.config import MAX_FILES_PER_BATCH
        from datetime import datetime
        
        # Check Limits
        if len(media_files) > MAX_FILES_PER_BATCH:
            raise ValueError(f"Vượt quá giới hạn {MAX_FILES_PER_BATCH} file mỗi lần upload. Vui lòng chia nhỏ.")
        
        if len(media_files) != len(captions) or len(media_files) != len(schedule_times):
            raise ValueError("Dữ liệu form bị lệch. Vui lòng thử lại.")

        account = db.query(Account).filter(Account.id == account_id).first()
        if not account or not account.is_active:
            raise ValueError("Tài khoản không tồn tại hoặc đã bị vô hiệu hóa.")
        
        batch_id = uuid.uuid4().hex
        media_dir = os.path.abspath("content/media")
        os.makedirs(media_dir, exist_ok=True)
        
        import tempfile
        
        saved_temp_paths = []
        jobs_to_insert = []
        
        # Clean affiliate_url and auto_comment_text
        clean_affiliate = affiliate_url.strip() if affiliate_url and affiliate_url.strip() else None
        clean_auto_comment = auto_comment_text.strip() if auto_comment_text and auto_comment_text.strip() else None
        
        # Track the minimum valid time required to prevent spam
        last_valid_ts = account.last_post_ts or 0
        
        try:
            # Phase 1: Preparation, File Writing to .tmp, and Validation
            for i, media_file in enumerate(media_files):
                if not media_file.filename:
                    continue  # Skip empty selections
                    
                # 1. Parse Time
                try:
                    dt_naive = datetime.strptime(schedule_times[i], "%Y-%m-%dT%H:%M")
                    dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
                    row_ts = int(dt_aware.timestamp())
                except ValueError:
                    raise ValueError(f"Định dạng giờ không hợp lệ ở file {media_file.filename}")

                # 2. Strict Backend Schedulling Calculation
                expected_min_ts = last_valid_ts + account.cooldown_seconds if last_valid_ts > 0 else row_ts
                adjusted_ts = max(row_ts, expected_min_ts)
                last_valid_ts = adjusted_ts
                
                # 3. File Preparation
                ext = os.path.splitext(media_file.filename)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                final_path = os.path.join(media_dir, unique_filename)
                
                # 4. Atomic Write to Temp
                tmp_fd, tmp_path = tempfile.mkstemp(dir=media_dir, suffix=".tmp")
                with os.fdopen(tmp_fd, "wb") as tmp_file:
                    shutil.copyfileobj(media_file.file, tmp_file)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                
                if os.path.getsize(tmp_path) == 0:
                    raise ValueError(f"File {media_file.filename} bị rỗng (0 bytes).")
                    
                saved_temp_paths.append((tmp_path, final_path))
                
                # 5. Idempotency Key + Tracking Setup
                dedupe_raw = f"{account_id}:{unique_filename}"
                dedupe_key = hashlib.sha256(dedupe_raw.encode()).hexdigest()[:16]
                tracking_code = str(uuid.uuid4())[:8]
                
                # Replace placeholder with actual tracking URL
                final_auto_comment = clean_auto_comment
                if final_auto_comment:
                    from app.config import VERCEL_REDIRECT_URL

                    vercel_url = (VERCEL_REDIRECT_URL or "").strip().rstrip("/")
                    if vercel_url:
                        full_tracking_url = f"{vercel_url}/r/{tracking_code}"
                    else:
                        full_tracking_url = f"/r/{tracking_code}"
                    final_auto_comment = final_auto_comment.replace(
                        "{tracking_url}", full_tracking_url
                    )

                initial_status = "DRAFT" if captions[i] and "[AI_GENERATE]" in captions[i] else "PENDING"

                job = Job(
                    platform=account.platform,
                    account_id=account.id,
                    media_path=final_path,
                    caption=captions[i],
                    schedule_ts=adjusted_ts,
                    status=initial_status,
                    tries=0,
                    dedupe_key=dedupe_key,
                    batch_id=batch_id,
                    tracking_code=tracking_code,
                    tracking_url=f"/r/{tracking_code}",
                    affiliate_url=clean_affiliate,
                    auto_comment_text=final_auto_comment,
                    target_page=target_page.strip() if target_page else None
                )
                jobs_to_insert.append(job)

            if not jobs_to_insert:
                raise ValueError("Không có file nào hợp lệ để upload.")

            # Phase 2: All or Nothing Commit to DB
            for job in jobs_to_insert:
                db.add(job)
                
            db.flush() 
            
            if randomize_caption:
                for job in jobs_to_insert:
                    raw_string = f"{job.id}-{job.created_at}"
                    salt = hashlib.sha256(raw_string.encode()).hexdigest()[:8]
                    job.caption = f"{job.caption}\n\n[ref:{salt}]"

            db.commit() 
            
            # Phase 3: Rename all temp files to final destination AFTER successful commit
            for tmp_path, final_path in saved_temp_paths:
                os.rename(tmp_path, final_path)
                
            logger.info(f"Successfully bulk uploaded {len(jobs_to_insert)} jobs for batch {batch_id}")

            return templates.TemplateResponse(
                "fragments/create_job_form.html", 
                {
                    "request": request, 
                    "accounts": accounts, 
                    "success": True, 
                    "bulk_success_count": len(jobs_to_insert)
                }
            )

        except Exception as batch_error:
            # ROLLBACK INITIATED
            db.rollback()
            for tmp_path, _ in saved_temp_paths:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path) # Burn the temporary files
            raise batch_error
            
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}")
        return templates.TemplateResponse(
            "fragments/create_job_form.html", 
            {
                "request": request, 
                "accounts": accounts, 
                "error": str(e)
            }
        )
