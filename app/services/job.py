"""
Service layer for managing Job entities and their lifecycle.
"""
import time
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.database.core import SessionLocal
from app.database.models import Job, JobEvent, Account
from app.config import COMMENT_JOB_DELAY_MAX_SEC, COMMENT_JOB_DELAY_MIN_SEC
from app.constants import JobStatus, JobType
from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)


def now_ts():
    return int(time.time())

class JobService:
    VALID_EXTENSIONS = ('.mp4', '.jpg', '.jpeg', '.png')
    
    @staticmethod
    def get_job_by_id(db: Session, job_id: int) -> Optional[Job]:
        return db.query(Job).filter(Job.id == job_id).first()

    @staticmethod
    def get_job_events(db: Session, job_id: int, limit: int = 50) -> list[JobEvent]:
        return db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.id.desc()).limit(limit).all()
    
    @staticmethod
    def create_job(db: Session, account_id: int, media_path: str, caption: str, schedule_ts: int, randomize_caption: bool, dedupe_key: str = None, affiliate_url: str = None, target_page: str = None) -> Job:
        """Creates a new PENDING job with strict validations."""
        # 1. Validate Account
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account ID {account_id} does not exist.")
            
        # 2. Validate Schedule
        if schedule_ts < now_ts():
            raise ValueError("Schedule time cannot be in the past.")
            
        # 3. Normalize and Validate Media Path
        norm_path = os.path.abspath(media_path.strip())
        _, ext = os.path.splitext(norm_path)
        if ext.lower() not in JobService.VALID_EXTENSIONS:
            raise ValueError(f"Media extension {ext} not supported. Must be one of {JobService.VALID_EXTENSIONS}")
            
        if not os.path.exists(norm_path):
            raise ValueError(f"Media file not found at path: {norm_path}")
            
        # 4. Create Job with tracking
        import uuid
        tracking_code = str(uuid.uuid4())[:8]
        tracking_url = f"/r/{tracking_code}"
        
        initial_status = JobStatus.DRAFT if caption and "[AI_GENERATE]" in caption else JobStatus.PENDING
        
        new_job = Job(
            platform=account.platform,
            account_id=account.id,
            media_path=norm_path,
            caption=caption,
            schedule_ts=schedule_ts,
            status=initial_status,
            tries=0,
            dedupe_key=dedupe_key,
            tracking_code=tracking_code,
            tracking_url=tracking_url,
            affiliate_url=affiliate_url.strip() if affiliate_url and affiliate_url.strip() else None,
            target_page=target_page.strip() if target_page and target_page.strip() else None
        )
        
        from sqlalchemy.exc import IntegrityError
        
        db.add(new_job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError("Duplicate job detected (same account + file combination). Skipped.")
        db.refresh(new_job)
        
        # 5. Handle Caption Randomization with Deterministic Salt
        if randomize_caption:
            import hashlib
            # Create a mathematically unique salt guaranteed to belong only to this specific job
            raw_string = f"{new_job.id}-{new_job.created_at}"
            salt = hashlib.sha256(raw_string.encode()).hexdigest()[:8]
            new_job.caption = f"{caption}\n\n[ref:{salt}]"
            
            db.commit()
            db.refresh(new_job)
            
        # Log creation
        JobService._log_event(db, new_job.id, "INFO", "Job manually created via UI")
        
        # 6. Register tracking code on Vercel (non-blocking)
        JobService._register_vercel_tracking(new_job)
        
        return new_job

    @staticmethod
    def create_job_from_upload(
        db: Session, 
        account_id: int, 
        media_file, 
        caption: str, 
        schedule_ts: int, 
        randomize_caption: bool, 
        affiliate_url: str = "", 
        target_page: str = ""
    ) -> Job:
        import uuid
        import shutil
        import hashlib
        
        if not media_file.filename:
            raise ValueError("No file uploaded.")
            
        ext = os.path.splitext(media_file.filename)[1].lower() or (".mp4" if "video" in media_file.content_type else ".jpg")
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        media_dir = os.path.abspath("content/media")
        os.makedirs(media_dir, exist_ok=True)
        saved_path = os.path.join(media_dir, unique_filename)
        
        with open(saved_path, "wb") as f:
            shutil.copyfileobj(media_file.file, f)
        
        dedupe_raw = f"{account_id}:{unique_filename}"
        dedupe_key = hashlib.sha256(dedupe_raw.encode()).hexdigest()[:16]
        
        return JobService.create_job(db, account_id, saved_path, caption, schedule_ts, randomize_caption, dedupe_key, affiliate_url, target_page.strip())
    
    @staticmethod
    def _register_vercel_tracking(job: Job):
        """
        Register tracking code on Vercel redirect service.
        Non-blocking: failure is silently logged, local tracking still works.
        """
        from app.config import VERCEL_REDIRECT_URL
        vercel_url = VERCEL_REDIRECT_URL
        
        if not vercel_url or not job.affiliate_url or not job.tracking_code:
            return
            
        try:
            import requests
            resp = requests.post(
                f"{vercel_url}/api/register",
                json={"code": job.tracking_code, "url": job.affiliate_url},
                timeout=5
            )
            if resp.ok:
                job.tracking_url = f"{vercel_url}/r/{job.tracking_code}"
        except Exception:
            pass  # Non-blocking — local tracking still works
    
    @staticmethod
    def mark_done(db: Session, job: Job, details: str = None, external_post_id: str = None, post_url: str = None):
        """Transitions RUNNING -> DONE."""
        job.status = JobStatus.DONE
        job.finished_at = now_ts()
        job.last_error = None
        if external_post_id:
            job.external_post_id = external_post_id
        if post_url:
            job.post_url = post_url
        
        if job.account:
            job.account.last_post_ts = now_ts()
            job.account.consecutive_fatal_failures = 0  # Reset circuit breaker
            
        JobService._log_event(db, job.id, "INFO", "Job marked DONE", details)
        
        # Auto-create COMMENT job if POST has auto_comment_text
        if job.job_type == JobType.POST and job.auto_comment_text and (post_url or job.post_url):
            import random
            delay = random.randint(COMMENT_JOB_DELAY_MIN_SEC, COMMENT_JOB_DELAY_MAX_SEC)
            comment_job = Job(
                job_type=JobType.COMMENT,
                platform=job.platform,
                account_id=job.account_id,
                parent_job_id=job.id,
                post_url=post_url or job.post_url,
                auto_comment_text=job.auto_comment_text,
                status=JobStatus.PENDING,
                scheduled_at=now_ts() + delay,
                schedule_ts=now_ts() + delay,  # Also set for compatibility
                media_path=job.media_path,
                caption="",
            )
            db.add(comment_job)
            JobService._log_event(db, job.id, "INFO", 
                f"Auto COMMENT job created (delay={delay}s)")
        
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def mark_failed_or_retry(db: Session, job: Job, error_msg: str, is_fatal: bool, error_type: Optional[str] = None):
        """
        Transitions RUNNING -> FAILED or RUNNING -> PENDING explicitly based on errors.
        """
        job.tries += 1
        job.last_error = error_msg
        job.error_type = error_type or ("FATAL" if is_fatal else "RETRYABLE")
        
        JobService._log_event(db, job.id, "ERROR", error_msg, f"is_fatal={is_fatal}, tries={job.tries}/{job.max_tries}")
        
        # Circuit Breaker logic
        if is_fatal and job.account:
            job.account.consecutive_fatal_failures += 1
            if job.account.consecutive_fatal_failures >= 3:
                job.account.is_active = False
                JobService._log_event(db, job.id, "WARN", f"Circuit breaker activated for account {job.account.name}")
        
        if is_fatal or job.tries >= job.max_tries:
            job.status = JobStatus.FAILED
            job.finished_at = now_ts()
        else:
            job.status = JobStatus.PENDING
            # Exponential backoff
            backoff_mins = 5 if job.tries == 1 else 15
            job.schedule_ts = now_ts() + (backoff_mins * 60)
            
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        
    @staticmethod
    def update_heartbeat(db: Session, job_id: int):
        """Updates the heartbeat of a RUNNING job with silent retries for locking."""
        import sqlalchemy.exc
        import time as _time
        for attempt in range(3):
            try:
                db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.RUNNING).update(
                    {"last_heartbeat_at": int(_time.time())}
                )
                db.commit()
                break
            except sqlalchemy.exc.OperationalError:
                db.rollback()
                if attempt < 2:
                    _time.sleep(0.5 * (attempt + 1))
                continue
            except Exception:
                db.rollback()
                break
        
    @staticmethod
    def get_jobs_paged(db: Session, status: str = "active", page: int = 1, per_page: int = 20, q: str = "") -> dict:
        from sqlalchemy import or_
        query = db.query(Job)
        
        # Status filter
        if status == "active":
            query = query.filter(Job.status.in_([JobStatus.AWAITING_STYLE, JobStatus.DRAFT, JobStatus.PENDING, JobStatus.RUNNING, JobStatus.AI_PROCESSING]))
        elif status in (JobStatus.DRAFT, JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            query = query.filter(Job.status == status)

        # Search filter
        q = (q or "").strip()
        if q:
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
        return {
            "jobs": jobs,
            "total": total,
            "total_pages": total_pages,
            "page": page
        }

    @staticmethod
    def create_high_priority_manual_job(db: Session, account_id: int, target_page: str, caption: str = None, media_path: str = None) -> Job:
        job = Job(
            platform="facebook",
            account_id=account_id,
            target_page=target_page,
            caption=caption,
            media_path=media_path,
            status=JobStatus.PENDING,
            schedule_ts=int(time.time()) - 999999, # Priority boost
            tries=0,
            max_tries=3,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        JobService._log_event(db, job.id, "INFO", "High-priority manual job created")
        return job

    @staticmethod
    def create_manual_job_with_file(db: Session, account_id: int, target_page: str, caption: str, media_file) -> Job:
        import uuid
        import shutil
        from app.config import CONTENT_DIR
        MANUAL_DIR = str(CONTENT_DIR / "manual")
        
        media_path = None
        if media_file and media_file.filename:
            os.makedirs(MANUAL_DIR, exist_ok=True)
            ext = media_file.filename.rsplit(".", 1)[-1] if "." in media_file.filename else "mp4"
            media_path = os.path.join(MANUAL_DIR, f"manual_{uuid.uuid4().hex[:8]}.{ext}")
            with open(media_path, "wb") as f:
                shutil.copyfileobj(media_file.file, f)
        
        return JobService.create_high_priority_manual_job(db, account_id, target_page, caption, media_path)

    @staticmethod
    def approve_job(db: Session, job_id: int):
        job = JobService.get_job_by_id(db, job_id)
        if job and job.status == JobStatus.DRAFT:
            job.status = JobStatus.PENDING
            db.commit()
            JobService._log_event(db, job.id, "INFO", "Job approved and moved to PENDING")

    @staticmethod
    def update_job_caption(db: Session, job_id: int, caption: str):
        job = JobService.get_job_by_id(db, job_id)
        if job:
            job.caption = caption
            db.commit()
            JobService._log_event(db, job.id, "INFO", "Job caption updated manually")

    @staticmethod
    def bulk_create_jobs(db: Session, account_id: int, files_data: list) -> str:
        """
        files_data: list of dict { 'final_path', 'caption', 'adjusted_ts', 'dedupe_key', 'tracking_code', 'clean_affiliate', 'final_auto_comment', 'target_page', 'initial_status' }
        """
        import uuid
        import hashlib
        batch_id = uuid.uuid4().hex
        jobs_to_insert = []
        
        for data in files_data:
            job = Job(
                platform=data['platform'],
                account_id=account_id,
                media_path=data['final_path'],
                caption=data['caption'],
                schedule_ts=data['adjusted_ts'],
                status=data['initial_status'],
                tries=0,
                dedupe_key=data['dedupe_key'],
                batch_id=batch_id,
                tracking_code=data['tracking_code'],
                tracking_url=f"/r/{data['tracking_code']}",
                affiliate_url=data['clean_affiliate'],
                auto_comment_text=data['final_auto_comment'],
                target_page=data['target_page']
            )
            jobs_to_insert.append(job)

        for job in jobs_to_insert:
            db.add(job)
        db.flush() 

        # Handle Caption Randomization
        for job in jobs_to_insert:
            raw_string = f"{job.id}-{job.created_at}"
            salt = hashlib.sha256(raw_string.encode()).hexdigest()[:8]
            job.caption = f"{job.caption}\n\n[ref:{salt}]"

        db.commit()
        return batch_id

    @staticmethod
    def bulk_create_jobs_from_uploads(
        db: Session,
        account_id: int,
        media_files: list,
        captions: list,
        schedule_times: list,
        randomize_caption: bool,
        affiliate_url: str = "",
        auto_comment_text: str = "",
        target_page: str = ""
    ) -> str:
        import uuid
        import shutil
        import hashlib
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.config import MAX_FILES_PER_BATCH, TIMEZONE
        from app.services.account import AccountService
        
        if len(media_files) > MAX_FILES_PER_BATCH:
            raise ValueError(f"Limit {MAX_FILES_PER_BATCH} files.")
        
        account = AccountService.get_account_by_id(db, account_id)
        if not account or not account.is_active:
            raise ValueError("Invalid account.")
        
        media_dir = os.path.abspath("content/media")
        os.makedirs(media_dir, exist_ok=True)
        
        files_data = []
        last_valid_ts = account.last_post_ts or 0
        clean_affiliate = affiliate_url.strip() if affiliate_url else None
        clean_auto_comment = auto_comment_text.strip() if auto_comment_text else None
        
        for i, media_file in enumerate(media_files):
            if not media_file.filename: continue
            
            dt_naive = datetime.strptime(schedule_times[i], "%Y-%m-%dT%H:%M")
            dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
            row_ts = int(dt_aware.timestamp())
            adjusted_ts = max(row_ts, last_valid_ts + account.cooldown_seconds if last_valid_ts > 0 else row_ts)
            last_valid_ts = adjusted_ts
            
            ext = os.path.splitext(media_file.filename)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}{ext}"
            final_path = os.path.join(media_dir, unique_filename)
            
            with open(final_path, "wb") as f:
                shutil.copyfileobj(media_file.file, f)
                
            dedupe_key = hashlib.sha256(f"{account_id}:{unique_filename}".encode()).hexdigest()[:16]
            tracking_code = str(uuid.uuid4())[:8]
            
            final_comment = clean_auto_comment
            if final_comment:
                from app.config import VERCEL_REDIRECT_URL
                vurl = (VERCEL_REDIRECT_URL or "").strip().rstrip("/")
                full_turl = f"{vurl}/r/{tracking_code}" if vurl else f"/r/{tracking_code}"
                final_comment = final_comment.replace("{tracking_url}", full_turl)
 
            files_data.append({
                'platform': account.platform,
                'final_path': final_path,
                'caption': captions[i],
                'adjusted_ts': adjusted_ts,
                'dedupe_key': dedupe_key,
                'tracking_code': tracking_code,
                'clean_affiliate': clean_affiliate,
                'final_auto_comment': final_comment,
                'target_page': target_page.strip() if target_page else None,
                'initial_status': JobStatus.DRAFT if "[AI_GENERATE]" in captions[i] else JobStatus.PENDING
            })
 
        return JobService.bulk_create_jobs(db, account_id, files_data)

    @staticmethod
    def rollback_to_pending(db: Session, job: Job, reason: str):
        """Rolls back a locked job to PENDING if pre-dispatch validation fails."""
        job.status = JobStatus.PENDING
        # Delay it briefly to avoid immediate re-lock looping
        job.schedule_ts = now_ts() + 60
        JobService._log_event(db, job.id, "WARN", f"Rolled back to PENDING: {reason}")
        db.commit()
        
    @staticmethod
    def retry_job(db: Session, job_id: int):
        """Transitions FAILED -> PENDING. Does not reset tries."""
        job = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.FAILED).first()
        if not job:
            raise ValueError("Job is not in FAILED state or does not exist.")
            
        # Verify media file exists before allowing retry
        if not job.resolved_media_path:
            raise ValueError("Cannot retry: media file has been deleted")

        now = now_ts()
        job.status = JobStatus.PENDING
        job.schedule_ts = now
        
        db.commit()
        JobService._log_event(db, job_id, "INFO", "MANUAL_RETRY")

    @staticmethod
    def reset_to_draft(db: Session, job_id: int):
        """Transitions AI_PROCESSING/FAILED/PENDING -> DRAFT for re-processing."""
        rows_affected = db.query(Job).filter(
            Job.id == job_id,
            Job.status.in_([JobStatus.AI_PROCESSING, JobStatus.FAILED, JobStatus.PENDING, JobStatus.RUNNING])
        ).update({
            "status": JobStatus.DRAFT,
            "last_error": None,
            "tries": 0,
        }, synchronize_session="fetch")
        if rows_affected == 0:
            raise ValueError("Job is not in a resettable state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "RESET_TO_DRAFT")

    @staticmethod
    def cancel_job(db: Session, job_id: int):
        """Transitions PENDING, DRAFT, or AI_PROCESSING -> CANCELLED."""
        rows_affected = db.query(Job).filter(Job.id == job_id, Job.status.in_([JobStatus.PENDING, JobStatus.DRAFT, JobStatus.AI_PROCESSING])).update({
            "status": JobStatus.CANCELLED
        }, synchronize_session="fetch")
        if rows_affected == 0:
            raise ValueError("Job is not in PENDING/DRAFT/AI_PROCESSING state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_CANCELLED")
        
    @staticmethod
    def reschedule_job(db: Session, job_id: int, new_ts: int):
        """Updates schedule_ts for a PENDING job."""
        if new_ts < now_ts():
            raise ValueError("Schedule time cannot be in the past.")
        rows_affected = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.PENDING).update({
            "schedule_ts": new_ts
        })
        if rows_affected == 0:
            raise ValueError("Job is not in PENDING state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_RESCHEDULED")

    @staticmethod
    def force_run_job(db: Session, job_id: int):
        """Sets schedule_ts to now for a PENDING job."""
        now = now_ts()
        rows_affected = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.PENDING).update({
            "schedule_ts": now
        })
        if rows_affected == 0:
            raise ValueError("Job is not in PENDING state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_FORCED")

    @staticmethod
    def _log_event(db: Session, job_id: int, level: str, message: str, meta: str = None):
        """Best-effort event logging that must never break business state transitions."""
        payload = {
            "job_id": job_id,
            "level": level,
            "message": message,
            "meta_json": meta,
        }

        last_err = None
        for attempt in range(2):
            event_db = SessionLocal()
            try:
                event_db.add(JobEvent(**payload))
                event_db.commit()
                return
            except Exception as exc:
                last_err = exc
                event_db.rollback()
                if attempt == 0:
                    logger.warning(
                        "[Job %s] _log_event failed on attempt %s, retrying once: %s",
                        job_id,
                        attempt + 1,
                        exc,
                    )
                    continue
            finally:
                event_db.close()

        logger.error("[Job %s] _log_event failed after retry: %s", job_id, last_err)
