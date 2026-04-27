"""Service package compatibility layer.

PLAN-028 moves service implementation files into domain packages while
preserving legacy imports such as ``app.services.job`` and
``from app.services import settings``.
"""

from importlib import import_module
import importlib.abc
import importlib.util
import sys


_ALIASES = {
    "settings": "platform.settings",
    "account": "platform.account",
    "page_utils": "platform.page_utils",
    "platform_config_service": "platform.config_service",
    "workflow_registry": "platform.workflow_registry",
    "ai_native_fallback": "ai.native_fallback",
    "ai_pipeline": "ai.pipeline",
    "ai_runtime": "ai.runtime",
    "ai_service": "ai.service",
    "gemini_api": "ai.gemini_api",
    "gemini_rpa": "ai.gemini_rpa",
    "brain_factory": "ai.brain_factory",
    "telegram_client": "telegram.client",
    "telegram_command_handler": "telegram.command_handler",
    "telegram_event_router": "telegram.event_router",
    "telegram_poller": "telegram.poller",
    "telegram_service": "telegram.service",
    "notifier_formatting": "telegram.notifier.formatting",
    "notifier_service": "telegram.notifier.service",
    "notifiers": "telegram.notifier",
    "notifiers.base": "telegram.notifier.base",
    "notifiers.telegram": "telegram.notifier.telegram",
    "incident_logger": "observability.incident_logger",
    "log_normalizer": "observability.log_normalizer",
    "log_query_facade": "observability.log_query_facade",
    "log_query_service": "observability.log_query_service",
    "log_service": "observability.log_service",
    "metrics_checker": "observability.metrics_checker",
    "system_monitor": "observability.system_monitor",
    "audit_logger": "observability.audit_logger",
    "runtime_events": "observability.runtime_events",
    "health": "observability.health",
    "job": "jobs.job",
    "job_queue": "jobs.queue",
    "job_tracer": "jobs.tracer",
    "worker": "jobs.worker",
    "cleanup": "jobs.cleanup",
    "content_orchestrator": "content.orchestrator",
    "media_processor": "content.media_processor",
    "video_protector": "content.video_protector",
    "news_scraper": "content.news_scraper",
    "threads_news": "content.threads_news",
    "yt_dlp_path": "content.yt_dlp_path",
    "discovery_scraper": "viral.discovery_scraper",
    "tiktok_scraper": "viral.tiktok_scraper",
    "viral_processor": "viral.processor",
    "viral_scan": "viral.scan",
    "viral_service": "viral.service",
    "reup_processor": "viral.reup_processor",
    "strategic": "viral.strategic",
    "fb_compliance": "compliance.fb_compliance",
    "compliance_service": "compliance.service",
    "affiliate_ai": "compliance.affiliate_ai",
    "affiliate_service": "compliance.affiliate_service",
    "dashboard_service": "dashboard.dashboard_service",
    "ai_studio_service": "dashboard.ai_studio_service",
    "syspanel_service": "dashboard.syspanel_service",
    "insights_service": "dashboard.insights_service",
    "threads_service": "dashboard.threads_service",
    "database_service": "db.database_service",
    "db_acl": "db.acl",
    "sql_validator": "db.sql_validator",
}


class _ServiceAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        prefix = f"{__name__}."
        if not fullname.startswith(prefix):
            return None
        old_name = fullname[len(prefix):]
        if old_name not in _ALIASES:
            return None
        is_package = old_name == "notifiers"
        return importlib.util.spec_from_loader(fullname, self, is_package=is_package)

    def create_module(self, spec):
        old_name = spec.name[len(f"{__name__}."):]
        target = import_module(f"{__name__}.{_ALIASES[old_name]}")
        sys.modules[spec.name] = target
        if "." not in old_name:
            globals()[old_name] = target
        return target

    def exec_module(self, module):
        return None


if not any(isinstance(finder, _ServiceAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _ServiceAliasFinder())


def __getattr__(name: str):
    if name in _ALIASES and "." not in name:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(name for name in _ALIASES if "." not in name)
