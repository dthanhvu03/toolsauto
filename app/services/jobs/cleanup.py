"""
Cleanup Service — Archives or deletes media files for completed/stale jobs.

Policy:
  - DONE jobs older than CLEANUP_DONE_AFTER_DAYS  → move file to content/done/
  - FAILED jobs older than CLEANUP_FAILED_AFTER_DAYS → delete file (no value keeping)
  - Orphaned .tmp files in content/media/ older than 1 hour → delete (crashed writes)
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.database.models import IncidentLog, Job, JobEvent
from app.config import CONTENT_DIR
from app.constants import JobStatus
from app.services import settings as runtime_settings


logger = logging.getLogger(__name__)

# Configuration (override via env vars if needed)
CLEANUP_DONE_AFTER_DAYS   = int(os.getenv("CLEANUP_DONE_AFTER_DAYS", "1"))    # Delete media after 1 day
CLEANUP_FAILED_AFTER_DAYS = int(os.getenv("CLEANUP_FAILED_AFTER_DAYS", "1"))  # Delete media after 1 day
CLEANUP_TMP_AFTER_HOURS   = 1                                                   # Remove stale .tmp files after 1h

MEDIA_DIR = CONTENT_DIR / "media"
LOG_CLEANUP_INTERVAL_SEC = 86400
_last_log_cleanup_ts = 0.0

def now_ts():
    return int(time.time())


def _cleanup_old_logs(db: Session, days: int = 30) -> dict:
    """Delete raw log rows older than retention; keep aggregate incident_groups intact."""
    result = {"job_events_deleted": 0, "incident_logs_deleted": 0}
    if days <= 0:
        logger.warning("[Cleanup] Invalid log retention days=%s; skipping log cleanup.", days)
        return result

    cutoff_ts = now_ts() - days * 86400
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        result["job_events_deleted"] = (
            db.query(JobEvent)
            .filter(JobEvent.ts < cutoff_ts)
            .delete(synchronize_session=False)
        )
        result["incident_logs_deleted"] = (
            db.query(IncidentLog)
            .filter(IncidentLog.occurred_at < cutoff_dt)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(
            "[Cleanup] Log retention days=%d deleted job_events=%d incident_logs=%d",
            days,
            result["job_events_deleted"],
            result["incident_logs_deleted"],
        )
        return result
    except Exception as e:
        db.rollback()
        logger.warning("[Cleanup] old_logs failed: %s", e)
        return result


class CleanupService:

    @classmethod
    def run(cls, db: Session):
        """
        Called by the Worker once per cycle (after every tick).
        Runs all cleanup sub-tasks non-fatally — errors are logged but never propagate.
        """
        try:
            cls._archive_done_files(db)
        except Exception as e:
            logger.warning("[Cleanup] archive_done_files failed: %s", e)

        try:
            cls._delete_failed_files(db)
        except Exception as e:
            logger.warning("[Cleanup] delete_failed_files failed: %s", e)

        try:
            cls._delete_cancelled_files(db)
        except Exception as e:
            logger.warning("[Cleanup] delete_cancelled_files failed: %s", e)

        try:
            cls._remove_stale_tmp_files()
        except Exception as e:
            logger.warning("[Cleanup] remove_stale_tmp_files failed: %s", e)

        try:
            cls._clear_browser_caches()
        except Exception as e:
            logger.warning("[Cleanup] clear_browser_caches failed: %s", e)

        cls._run_daily_log_cleanup(db)

    @classmethod
    def _run_daily_log_cleanup(cls, db: Session):
        global _last_log_cleanup_ts
        current_ts = time.time()
        if (current_ts - _last_log_cleanup_ts) < LOG_CLEANUP_INTERVAL_SEC:
            return

        try:
            days = runtime_settings.get_int("cleanup.log_retention_days", 30, db=db)
            _cleanup_old_logs(db, days=days)
            _last_log_cleanup_ts = current_ts
        except Exception as e:
            db.rollback()
            logger.warning("[Cleanup] daily old_logs failed: %s", e)

    @classmethod
    def _archive_done_files(cls, db: Session):
        """Delete media files of DONE jobs (>= CLEANUP_DONE_AFTER_DAYS old) from disk.
        
        Rationale: Once a post is published successfully, the platform (Facebook/etc.) 
        stores the media on its own servers. Keeping local copies wastes disk space
        especially with bulk uploads (50 videos x 100MB = 5GB per batch).
        """
        cutoff = now_ts() - CLEANUP_DONE_AFTER_DAYS * 86400
        from sqlalchemy import or_
        jobs = (
            db.query(Job)
            .filter(Job.status == JobStatus.DONE, Job.finished_at <= cutoff)
            .filter(or_(Job.media_path.isnot(None), Job.processed_media_path.isnot(None)))
            .all()
        )

        cleaned = 0
        for job in jobs:
            # Delete original media
            if job.media_path and os.path.exists(job.media_path):
                try:
                    os.unlink(job.media_path)
                    logger.info("[Cleanup] Deleted DONE media: %s (job #%s)", job.media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.media_path, e)
            # Delete processed media
            if job.processed_media_path and os.path.exists(job.processed_media_path):
                try:
                    os.unlink(job.processed_media_path)
                    logger.info("[Cleanup] Deleted DONE processed: %s (job #%s)", job.processed_media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.processed_media_path, e)
            
            job.media_path = None
            job.processed_media_path = None
            cleaned += 1

        if cleaned:
            db.commit()
            logger.info("[Cleanup] Cleaned %d DONE job media file(s).", cleaned)

    @classmethod
    def _delete_failed_files(cls, db: Session):
        """Delete media files of FAILED jobs older than CLEANUP_FAILED_AFTER_DAYS."""
        cutoff = now_ts() - CLEANUP_FAILED_AFTER_DAYS * 86400
        from sqlalchemy import or_
        jobs = (
            db.query(Job)
            .filter(Job.status == JobStatus.FAILED, Job.finished_at <= cutoff)
            .filter(or_(Job.media_path.isnot(None), Job.processed_media_path.isnot(None)))
            .all()
        )

        deleted = 0
        for job in jobs:
            if job.media_path and os.path.exists(job.media_path):
                try:
                    os.unlink(job.media_path)
                    logger.info("[Cleanup] Deleted FAILED media: %s (job #%s)", job.media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.media_path, e)
            if job.processed_media_path and os.path.exists(job.processed_media_path):
                try:
                    os.unlink(job.processed_media_path)
                    logger.info("[Cleanup] Deleted FAILED processed: %s (job #%s)", job.processed_media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.processed_media_path, e)

            job.media_path = None
            job.processed_media_path = None
            deleted += 1

        if deleted:
            db.commit()
            logger.info("[Cleanup] Cleaned %d FAILED job media file(s).", deleted)

    @classmethod
    def _delete_cancelled_files(cls, db: Session):
        """Delete media files of CANCELLED jobs immediately (no waiting period).
        
        Rationale: User explicitly decided not to use these files.
        No reason to keep them wasting disk space.
        """
        from sqlalchemy import or_
        jobs = (
            db.query(Job)
            .filter(Job.status == JobStatus.CANCELLED)
            .filter(or_(Job.media_path.isnot(None), Job.processed_media_path.isnot(None)))
            .all()
        )

        deleted = 0
        for job in jobs:
            if job.media_path and os.path.exists(job.media_path):
                try:
                    os.unlink(job.media_path)
                    logger.info("[Cleanup] Deleted CANCELLED media: %s (job #%s)", job.media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.media_path, e)
            if job.processed_media_path and os.path.exists(job.processed_media_path):
                try:
                    os.unlink(job.processed_media_path)
                    logger.info("[Cleanup] Deleted CANCELLED processed: %s (job #%s)", job.processed_media_path, job.id)
                except Exception as e:
                    logger.warning("[Cleanup] Could not delete %s: %s", job.processed_media_path, e)

            job.media_path = None
            job.processed_media_path = None
            deleted += 1

        if deleted:
            db.commit()
            logger.info("[Cleanup] Cleaned %d CANCELLED job media file(s).", deleted)

    @classmethod
    def _remove_stale_tmp_files(cls):
        """Delete orphaned .tmp files in content/media/ left by crashed uploads."""
        cutoff = time.time() - CLEANUP_TMP_AFTER_HOURS * 3600
        removed = 0
        for fname in os.listdir(MEDIA_DIR):
            if fname.endswith(".tmp"):
                fpath = MEDIA_DIR / fname
                try:
                    if os.path.getmtime(str(fpath)) < cutoff:
                        os.unlink(fpath)
                        removed += 1
                        logger.info("[Cleanup] Removed stale tmp: %s", fpath)
                except Exception as e:
                    logger.warning("[Cleanup] Could not remove tmp %s: %s", fpath, e)

        if removed:
            logger.info("[Cleanup] Removed %d stale .tmp file(s).", removed)

    @classmethod
    def _clear_browser_caches(cls):
        """
        Delete bulky Chrome cache directories per account profile.
        These grow to ~1-2GB per account. Safe to delete.
        Keeps Cookies and Local Storage intact.
        """
        from app.config import PROFILES_DIR
        import shutil

        if not PROFILES_DIR.exists():
            return

        cache_dirs = ["Default/Cache", "Default/Code Cache", "Default/GPUCache"]
        freed_mb = 0.0

        for profile in PROFILES_DIR.iterdir():
            if not profile.is_dir():
                continue
                
            for c_dir in cache_dirs:
                target = profile / c_dir
                if target.exists() and target.is_dir():
                    try:
                        # Calculate size
                        size_bytes = sum(f.stat().st_size for f in target.glob('**/*') if f.is_file())
                        shutil.rmtree(target)
                        freed_mb += size_bytes / (1024 * 1024)
                    except Exception as e:
                        logger.warning("[Cleanup] Failed to clear %s: %s", target, e)

        if freed_mb > 0:
            logger.info("[Cleanup] Cleared %.1f MB of browser cache.", freed_mb)
