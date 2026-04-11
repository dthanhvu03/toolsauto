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
from sqlalchemy.orm import Session
from app.database.models import Job
from app.config import CONTENT_DIR
from app.constants import JobStatus


logger = logging.getLogger(__name__)

# Configuration (override via env vars if needed)
CLEANUP_DONE_AFTER_DAYS   = int(os.getenv("CLEANUP_DONE_AFTER_DAYS", "1"))    # Delete media after 1 day
CLEANUP_FAILED_AFTER_DAYS = int(os.getenv("CLEANUP_FAILED_AFTER_DAYS", "1"))  # Delete media after 1 day
CLEANUP_TMP_AFTER_HOURS   = 1                                                   # Remove stale .tmp files after 1h

MEDIA_DIR = CONTENT_DIR / "media"

def now_ts():
    return int(time.time())


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

