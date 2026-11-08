"""Chọn adapter theo nền tảng (PLAN-166: đăng bài trực tiếp FB / IG / TikTok / Story đã gỡ — đăng qua Buffer)."""
import logging

from app.adapters.contracts import AdapterInterface, PublishResult
from app.constants import Platform
from app.core.database.models import Job
from app.core.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)

# Canonical job.platform / registry keys — see app.constants.Platform
_PLATFORM_ALIASES: dict[str, str] = {
    "fb": Platform.FACEBOOK,
}


def normalize_platform(platform: str | None) -> str:
    """Return a single canonical platform key (lowercase StrEnum value)."""
    if not platform:
        return ""
    key = str(platform).strip().lower()
    return _PLATFORM_ALIASES.get(key, key)


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
    for platforms that have dedicated adapters (threads, buffer).
    PLAN-166: Instagram / TikTok upload đã gỡ — platform_configs cũ trỏ tới chúng sẽ rơi về DummyAdapter.

    ``platform`` is normalized via ``normalize_platform`` — must match ``app.constants.Platform``.
    """
    platform = normalize_platform(platform)
    from app.adapters.generic.adapter import GenericAdapter

    from app.features.threads.adapter import ThreadsAdapter
    from app.features.buffer.adapter import BufferAdapter

    # Map of platforms that have dedicated (non-Generic) adapters
    _DEDICATED_ADAPTERS = {
        Platform.THREADS: lambda: ThreadsAdapter(),
        Platform.BUFFER: lambda: BufferAdapter(),
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
