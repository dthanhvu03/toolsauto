import logging
from app.database.models import Job
from app.adapters.contracts import PublishResult, AdapterInterface
from app.services.media_processor import MediaProcessor
from app.config import FFMPEG_ENABLED, FFMPEG_PROFILE

logger = logging.getLogger(__name__)

from app.adapters.facebook.adapter import FacebookAdapter

class DummyAdapter(AdapterInterface):
    """A dummy adapter for scaffolding and testing."""
    def open_session(self, profile_path: str) -> bool:
        logger.info("DummyAdapter: open_session for %s", profile_path)
        return True
        
    def publish(self, job: Job) -> PublishResult:
        logger.info("DummyAdapter: publishing job %s", job.id)
        return PublishResult(ok=True, details={"msg": "Dummy success"})
        
    def check_published_state(self, job: Job) -> PublishResult:
        logger.info("DummyAdapter: check_published_state for job %s", job.id)
        return PublishResult(ok=False, error="Footprint not found")
        
    def close_session(self):
        logger.info("DummyAdapter: close_session called")

def get_adapter(platform: str) -> AdapterInterface:
    """Registry pattern to get the appropriate adapter for a platform."""
    if platform == "facebook":
        return FacebookAdapter()
    return DummyAdapter()

class Dispatcher:
    """
    Wraps adapter execution to enforce guarantees:
    1. Error trapping
    2. Guaranteed close_session in finally block
    3. FFmpeg pre-processing (if enabled)
    """
    
    @staticmethod
    def dispatch(job: Job, db=None) -> PublishResult:
        adapter = get_adapter(job.platform)
        if not adapter:
            return PublishResult(ok=False, is_fatal=True, error="Unknown platform adapter")
            
        try:
            logger.info("[Job %s] Dispatching to %s adapter", job.id, job.platform)
            
            # 1. Quick DB Check
            if job.external_post_id:
                logger.warning("[Job %s] DB Idempotency check: external_post_id %s already exists. Skipping publish.", job.id, job.external_post_id)
                return PublishResult(ok=True, external_post_id=job.external_post_id, details={"msg": "Skipped due to DB idempotency"})
            
            # 2. Open Session (if this fails, it's usually fatal or at least needs backoff)
            if not adapter.open_session(job.account.profile_path):
                return PublishResult(ok=False, is_fatal=False, error="Failed to open browser session")
                
            # 3. Remote Truth Verification (Idempotency)
            # We only spend the latency to check remote timelines if this is a known Retry (tries > 0)
            if getattr(job, "tries", 0) > 0:
                logger.info("[Job %s] Job is a retry. Checking external footprint for idempotency.", job.id)
                check_result = adapter.check_published_state(job)
                if check_result.ok:
                    logger.warning("[Job %s] Idempotency confirmed. Footprint found externally. Skipping duplicate publish.", job.id)
                    return check_result
                else:
                    logger.info("[Job %s] Footprint not found externally. Proceeding with publish.", job.id)

            # 4. FFmpeg Pre-Processing (if enabled and file is video)
            if FFMPEG_ENABLED and job.media_path and not job.processed_media_path:
                if MediaProcessor.is_video(job.media_path):
                    logger.info("[Job %s] Running FFmpeg pre-processing (profile=%s)", job.id, FFMPEG_PROFILE)
                    proc_result = MediaProcessor.process(job.media_path, profile=FFMPEG_PROFILE, job=job)
                    
                    if proc_result.success:
                        job.processed_media_path = proc_result.output_path
                        if db:
                            db.commit()
                        logger.info("[Job %s] FFmpeg done: %s", job.id, proc_result.output_path)
                    elif proc_result.is_fatal:
                        return PublishResult(ok=False, is_fatal=True, error=f"FFmpeg fatal: {proc_result.error}")
                    else:
                        logger.warning("[Job %s] FFmpeg failed (retryable): %s. Publishing original.", job.id, proc_result.error)

            # Lấy job_type để dùng cho execute flow
            job_type = getattr(job, 'job_type', 'POST') or 'POST'
            
            # 5. Execute based on job_type
            if job_type == "COMMENT":
                # COMMENT job: navigate to post and add comment
                logger.info("[Job %s] Dispatching COMMENT job on post: %s", job.id, job.post_url)
                result = adapter.post_comment(job.post_url, job.auto_comment_text)
                # COMMENT failures are NEVER fatal
                if not result.ok:
                    result.is_fatal = False
                return result
            
            # POST job: standard publish flow
            original_path = job.media_path
            if job.processed_media_path:
                job.media_path = job.processed_media_path  # Temporarily swap for adapter
            
            result = adapter.publish(job)
            
            job.media_path = original_path  # Restore original path
            return result
            
        except Exception as e:
            # Check for specific class of session invalidation errors
            if "SessionInvalid" in type(e).__name__ or "SessionInvalid" in str(e):
                logger.error("[Job %s] Adapter hit a fatal SessionInvalid exception. Account must be invalidated.", job.id)
                # Instead of interacting with the DB here, we return a targeted tuple or special PublishResult
                # letting the Worker handle the Account updates via AccountService to maintain tight session boundaries.
                return PublishResult(
                    ok=False, 
                    is_fatal=True, 
                    error=f"SessionInvalid: {str(e)}", 
                    details={"invalidate_account": True}
                )

            logger.exception("[Job %s] Unhandled adapter exception: %s", job.id, str(e))
            return PublishResult(ok=False, is_fatal=False, error=f"Unhandled Adapter Exception: {str(e)}")
            
        finally:
            # THIS IS A MUST-HOLD INVARIANT
            # We guarantee the browser context is destroyed.
            try:
                adapter.close_session()
                logger.info("[Job %s] Session closed gracefully", job.id)
            except Exception as e:
                logger.error("[Job %s] CRITICAL: Failed to close session: %s", job.id, str(e))
