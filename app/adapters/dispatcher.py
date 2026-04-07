import logging
from app.database.models import Job
from app.adapters.contracts import PublishResult, AdapterInterface
from app.services.media_processor import MediaProcessor
from app.services.workflow_registry import WorkflowRegistry
from app.config import FFMPEG_ENABLED, FFMPEG_PROFILE

logger = logging.getLogger(__name__)
from app.services.runtime_events import emit as rt_emit
from app.services import job_tracer

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
    """
    Prefer DB-driven adapter from WorkflowRegistry (platform_configs.adapter_class).
    Fall back to legacy routing if Registry fails or returns DummyAdapter/GenericAdapter
    for platforms that have dedicated adapters (facebook, tiktok, instagram).
    """
    from app.adapters.generic.adapter import GenericAdapter

    # Map of platforms that have dedicated (non-Generic) adapters
    _DEDICATED_ADAPTERS = {
        "facebook": lambda: FacebookAdapter(),
    }

    registry_adapter: AdapterInterface | None = None
    try:
        registry_adapter = WorkflowRegistry.get_adapter(platform)
    except Exception as e:
        logger.warning(
            "[Dispatcher] WorkflowRegistry.get_adapter(%r) failed: %s",
            platform,
            e,
            exc_info=True,
        )

    if registry_adapter is None:
        if platform in _DEDICATED_ADAPTERS:
            return _DEDICATED_ADAPTERS[platform]()
        return DummyAdapter()

    # If Registry returned DummyAdapter or GenericAdapter for a platform
    # that has its own dedicated adapter, prefer the dedicated one.
    if platform in _DEDICATED_ADAPTERS and isinstance(registry_adapter, (DummyAdapter, GenericAdapter)):
        logger.info(
            "[Dispatcher] Platform '%s' has dedicated adapter. "
            "Overriding %s from Registry.",
            platform, type(registry_adapter).__name__,
        )
        return _DEDICATED_ADAPTERS[platform]()

    return registry_adapter

class Dispatcher:
    """
    Wraps adapter execution to enforce guarantees:
    1. Error trapping
    2. Guaranteed close_session in finally block
    3. FFmpeg pre-processing (if enabled)
    """
    
    @staticmethod
    def _inject_cta(platform: str, text: str, locale: str = "vi") -> str:
        """Inject random CTA into raw link text using Registry phase 2."""
        if not text: return text
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        if all(l.startswith('http') for l in lines) and lines:
            try:
                cta_list = WorkflowRegistry.get_cta_templates(platform, locale=locale)
            except Exception as e:
                logger.warning(f"[Dispatcher] CTA DB fetch failed: {e}")
                cta_list = []
                
            if cta_list and cta_list != ["{link}"]:
                import random
                template = random.choice(cta_list)
                rt_emit("cta_injected", platform=platform, locale=locale,
                        source="db", template_preview=template[:50],
                        pool_size=len(cta_list))
            else:
                if platform == "facebook":
                    from app.adapters.facebook.adapter import FacebookAdapter
                    import random
                    template = random.choice(FacebookAdapter.CTA_POOL)
                    rt_emit("cta_injected", platform=platform, locale=locale,
                            source="static_fallback", template_preview=template[:50],
                            reason="no DB templates")
                else:
                    template = "{link}"
                    rt_emit("cta_injected", platform=platform, locale=locale,
                            source="default", template_preview="{link}",
                            reason="no templates for platform")
            return template.replace("{link}", '\n'.join(lines))
        return text
    
    @staticmethod
    def dispatch(job: Job, db=None) -> PublishResult:
        adapter = get_adapter(job.platform)
        if not adapter:
            return PublishResult(ok=False, is_fatal=True, error="Unknown platform adapter")
            
        try:
            logger.info("[Job %s] Dispatching to %s adapter", job.id, job.platform)
            
            job_type = getattr(job, 'job_type', 'POST') or 'POST'
            
            # --- [n8n-lite Phase 2] Fetch Workflow active steps ---
            active_steps = None
            try:
                workflow = WorkflowRegistry.get_workflow(job.platform, job_type)
                if workflow and workflow.steps:
                    active_steps = workflow.steps
            except Exception as e:
                logger.warning(f"[Dispatcher] Failed to fetch workflow steps for {job.platform}/{job_type}: {e}")
            setattr(job, "active_steps", active_steps)
            setattr(adapter, "active_steps", active_steps)
            if active_steps is not None:
                rt_emit("step_config_loaded", platform=job.platform,
                        job_type=job_type, job_id=job.id,
                        active_steps=active_steps, source="db")
            
            # --- Start Node Tracing ---
            job_tracer.start_job_trace(job.id, job.platform, job_type, active_steps or [])
            
            # 1. Quick DB Check
            if job.external_post_id:
                logger.warning("[Job %s] DB Idempotency check: external_post_id %s already exists. Skipping publish.", job.id, job.external_post_id)
                return PublishResult(ok=True, external_post_id=job.external_post_id, details={"msg": "Skipped due to DB idempotency"})
            
            # 2. Open Session (if this fails, it's usually fatal or at least needs backoff)
            if not adapter.open_session(job.account.resolved_profile_path):
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
            if FFMPEG_ENABLED and job.resolved_media_path and not job.resolved_processed_media_path:
                if MediaProcessor.is_video(job.resolved_media_path):
                    logger.info("[Job %s] Running FFmpeg pre-processing (profile=%s)", job.id, FFMPEG_PROFILE)
                    proc_result = MediaProcessor.process(job.resolved_media_path, profile=FFMPEG_PROFILE, job=job)
                    
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
            # --- [n8n-lite Phase 2] CTA Injection at Dispatcher level ---
            # CTA logic pull up for both POST and COMMENT flow
            final_comment_text = Dispatcher._inject_cta(job.platform, job.auto_comment_text)
            
            # 5. Execute based on job_type
            if job_type == "COMMENT":
                # COMMENT job: navigate to post and add comment
                logger.info("[Job %s] Dispatching COMMENT job on post: %s", job.id, job.post_url)
                
                # N8n-lite: Inject CTA to comment
                result = adapter.post_comment(job.post_url, final_comment_text)
                # COMMENT failures are NEVER fatal
                if not result.ok:
                    result.is_fatal = False
                
                if result.ok:
                    job_tracer.finish_job_trace(job.id, "completed")
                else:
                    job_tracer.finish_job_trace(job.id, "failed", result.error)
                return result
            
            # POST job: standard publish flow
            # N8n-lite: Inject CTA to caption if it exists
            original_caption = getattr(job, "caption", "")
            if original_caption:
                job.caption = Dispatcher._inject_cta(job.platform, original_caption)
                
            original_path = job.media_path
            if job.resolved_processed_media_path:
                job.media_path = job.resolved_processed_media_path  # Temporarily swap for adapter
            else:
                job.media_path = job.resolved_media_path

            result = adapter.publish(job)
            
            job.media_path = original_path  # Restore original path
            
            if result.ok:
                job_tracer.finish_job_trace(job.id, "completed")
            else:
                job_tracer.finish_job_trace(job.id, "failed", result.error)
                
            return result
            
        except Exception as e:
            job_tracer.finish_job_trace(job.id, "failed", str(e))
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
