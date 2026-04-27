"""
GenericAdapter — Data-driven workflow automation for any platform.

This adapter reads its entire execution plan from the database:
- Platform config (base_urls, viewport) from platform_configs
- Workflow steps from workflow_definitions  
- Selectors from platform_selectors

No platform-specific code needed. Just configure via Admin UI.

Usage by Dispatcher:
    When adapter_class = "app.adapters.generic.adapter.GenericAdapter"
    the Dispatcher instantiates this adapter, which loads workflow
    from DB and executes steps via ActionExecutor.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from playwright.sync_api import Playwright, BrowserContext, Page

from app.adapters.contracts import AdapterInterface, PublishResult
from app.adapters.common.decorators import playwright_safe_action
from app.adapters.common.session import PlatformSessionManager, SessionStatus
from app.adapters.generic.action_executor import (
    ActionExecutor,
    StepConfig,
    ValueResolver,
)
from app.config import SAFE_MODE

logger = logging.getLogger(__name__)


@playwright_safe_action(default=None, logger_name=__name__)
def _safe_close_resource(resource: Any) -> None:
    resource.close()


@playwright_safe_action(default=None, logger_name=__name__)
def _safe_stop_playwright(playwright: Playwright) -> None:
    playwright.stop()

try:
    from app.services.job_tracer import update_active_node
except ImportError:
    def update_active_node(*a, **kw): pass


class GenericAdapter(AdapterInterface):
    """
    Data-driven adapter that executes workflow steps from the database.

    Lifecycle:
    1. open_session(profile_path) → launch persistent browser
    2. publish(job) → load workflow → execute steps via ActionExecutor
    3. close_session() → cleanup

    No hardcoded platform logic. Everything comes from DB.
    """

    def __init__(self, platform: str = ""):
        self.platform = platform
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._executor: ActionExecutor | None = None
        self._platform_config: Any = None

    # ── Session Management ───────────────────────────────────────

    def open_session(self, profile_path: str) -> bool:
        """Launch persistent browser with user's local profile."""
        if self.playwright or self.context or self.page:
            logger.warning("GenericAdapter[%s]: Session already open, closing.", self.platform)
            self.close_session()

        # Load platform config for viewport/user_agent
        self._load_platform_config()

        viewport = {"width": 1280, "height": 720}
        if self._platform_config and self._platform_config.viewport:
            viewport = self._platform_config.viewport

        logger.info(
            "GenericAdapter[%s]: Opening session at %s",
            self.platform, profile_path,
        )

        bundle = PlatformSessionManager.launch(
            profile_path=profile_path,
            platform=self.platform,
            headless=False,
            viewport=viewport,
        )

        if not bundle:
            logger.error("GenericAdapter[%s]: Failed to launch browser.", self.platform)
            return False

        self.playwright, self.context, self.page = bundle
        self._executor = ActionExecutor(
            self.page, self.platform, self._platform_config,
        )

        logger.info("GenericAdapter[%s]: Session opened.", self.platform)
        return True

    # ── Publish ──────────────────────────────────────────────────

    def publish(self, job) -> PublishResult:
        """
        Load workflow from DB, parse steps, execute via ActionExecutor.
        """
        logger.info("GenericAdapter[%s]: Publishing job %s", self.platform, job.id)

        if not self.page or not self._executor:
            return PublishResult(
                ok=False, error="Browser session not initialized.", is_fatal=True,
            )

        # Load workflow steps from DB
        steps = self._load_workflow_steps(job)
        if not steps:
            return PublishResult(
                ok=False,
                error=f"No workflow steps configured for {self.platform}:POST. "
                      f"Please configure workflow in Admin → Workflows tab.",
            )

        # Build execution context
        context = self._build_context(job)

        # SAFE_MODE check
        if SAFE_MODE:
            logger.info(
                "GenericAdapter[%s]: SAFE_MODE enabled. "
                "Would execute %d steps. Skipping.",
                self.platform, len(steps),
            )
            return PublishResult(
                ok=True,
                external_post_id="safe_mode_dry_run",
                details={
                    "msg": "Dry run successful",
                    "safe_mode": True,
                    "steps_count": len(steps),
                    "step_names": [s.name for s in steps],
                },
            )

        # Execute all steps
        overall_ok, step_results = self._executor.execute_steps(
            steps, context, job_id=job.id,
        )

        # Build result
        details = {
            "steps_executed": len(step_results),
            "steps_total": len(steps),
            "step_results": [
                {
                    "name": r.step_name,
                    "action": r.action,
                    "success": r.success,
                    "error": r.error or None,
                    "duration_ms": round(r.duration_ms, 1),
                    "strategy": r.locator_strategy_used or None,
                }
                for r in step_results
            ],
        }

        if overall_ok:
            logger.info(
                "GenericAdapter[%s]: Job %s completed (%d/%d steps OK).",
                self.platform, job.id, len(step_results), len(steps),
            )
            return PublishResult(ok=True, details=details)
        else:
            # Find the failing step
            failed = next((r for r in step_results if not r.success), None)
            error_msg = f"Step '{failed.step_name}' failed: {failed.error}" if failed else "Unknown failure"
            artifacts = failed.artifacts if failed else {}

            logger.error(
                "GenericAdapter[%s]: Job %s failed at step '%s'.",
                self.platform, job.id,
                failed.step_name if failed else "unknown",
            )
            return PublishResult(
                ok=False,
                error=error_msg,
                details=details,
                artifacts=artifacts,
            )

    # ── Idempotency / Comment ────────────────────────────────────

    def check_published_state(self, job) -> PublishResult:
        logger.info(
            "GenericAdapter[%s]: check_published_state (not implemented)",
            self.platform,
        )
        return PublishResult(ok=False, error="Not implemented for generic adapter")

    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        logger.info(
            "GenericAdapter[%s]: post_comment (not implemented)",
            self.platform,
        )
        return PublishResult(ok=False, error="Not implemented for generic adapter")

    # ── Cleanup ──────────────────────────────────────────────────

    def close_session(self) -> None:
        logger.info("GenericAdapter[%s]: Closing session.", self.platform)
        if self.page:
            _safe_close_resource(self.page)
        if self.context:
            _safe_close_resource(self.context)
        if self.playwright:
            _safe_stop_playwright(self.playwright)
        self.page = None
        self.context = None
        self.playwright = None
        self._executor = None

    # ── Internal ─────────────────────────────────────────────────

    def _load_platform_config(self) -> None:
        """Load platform config from WorkflowRegistry."""
        try:
            from app.services.workflow_registry import WorkflowRegistry
            self._platform_config = WorkflowRegistry.get_platform_config(self.platform)
        except Exception as e:
            logger.warning(
                "GenericAdapter[%s]: Failed to load platform config: %s",
                self.platform, e,
            )

    def _load_workflow_steps(self, job) -> list[StepConfig]:
        """Load and parse workflow steps from DB."""
        try:
            from app.services.workflow_registry import WorkflowRegistry

            job_type = getattr(job, "job_type", "POST") or "POST"
            workflow = WorkflowRegistry.get_workflow(self.platform, job_type)

            if not workflow or not workflow.steps:
                logger.warning(
                    "GenericAdapter[%s]: No workflow found for %s:%s",
                    self.platform, self.platform, job_type,
                )
                return []

            # Parse steps — supports both new object format and legacy string format
            steps = []
            for raw_step in workflow.steps:
                step = StepConfig.from_dict(raw_step)
                steps.append(step)

            logger.info(
                "GenericAdapter[%s]: Loaded %d steps from workflow '%s'",
                self.platform, len(steps), workflow.name,
            )
            return steps

        except Exception as e:
            logger.error(
                "GenericAdapter[%s]: Failed to load workflow: %s",
                self.platform, e,
            )
            return []

    def _build_context(self, job) -> dict:
        """Build execution context dict for ValueResolver."""
        context: dict = {"job": job}

        # Account
        account = getattr(job, "account", None)
        if account:
            context["account"] = account

        # Platform config
        if self._platform_config:
            context["platform"] = self._platform_config

        return context
