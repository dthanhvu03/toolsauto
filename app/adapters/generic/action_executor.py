"""
ActionExecutor — Shared workflow step execution engine.

This is the core of the No-Code architecture. It executes individual
workflow steps defined in the database, using the LocatorStrategy
for resilient element resolution.

Architecture (3-tier):
    ActionExecutor (this) ← GenericAdapter ← Dispatcher
    ActionExecutor (this) ← CustomAdapter (reuse for common steps)

Supported actions:
    navigate, click, fill, upload_file, wait, verify, check_auth
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Page

from app.adapters.common.locator import LocatorStrategy, LocatorCandidate
from app.adapters.common.session import PlatformSessionManager, SessionStatus
from app.config import LOGS_DIR

logger = logging.getLogger(__name__)

# Optional tracer imports
try:
    from app.services.job_tracer import update_active_node
except ImportError:
    def update_active_node(*a, **kw): pass

try:
    from app.services.runtime_events import emit as rt_emit
except ImportError:
    def rt_emit(*a, **kw): pass


# ── Step Schema ──────────────────────────────────────────────────

@dataclass
class StepConfig:
    """
    Standardized step definition. Parsed from workflow_definitions.steps JSON.

    Example JSON:
    {
        "name": "fill_caption",
        "action": "fill",
        "selector_keys": ["caption:caption_input", "caption:text_area"],
        "value_source": "job.caption",
        "required": true,
        "timeout_ms": 10000,
        "wait_after_ms": 500,
        "retry_count": 1,
        "continue_on_error": false
    }
    """
    name: str
    action: str  # navigate, click, fill, upload_file, wait, verify, check_auth
    selector_keys: list[str] = field(default_factory=list)
    value_source: str = ""
    url_key: str = ""          # For navigate: key in platform.base_urls
    url: str = ""              # For navigate: literal URL
    required: bool = True
    timeout_ms: int = 10000
    wait_after_ms: int = 1000
    retry_count: int = 1
    continue_on_error: bool = False
    # verify-specific
    success_selector_keys: list[str] = field(default_factory=list)
    error_selector_keys: list[str] = field(default_factory=list)
    # check_auth-specific
    login_selector_keys: list[str] = field(default_factory=list)
    auth_selector_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "StepConfig":
        """Parse a step dict, with backward-compat for string-only steps."""
        if isinstance(d, str):
            # Legacy format: just a step name string
            return cls(name=d, action="legacy", required=False, continue_on_error=True)
        return cls(
            name=d.get("name", "unnamed"),
            action=d.get("action", "wait"),
            selector_keys=d.get("selector_keys", []),
            value_source=d.get("value_source", ""),
            url_key=d.get("url_key", ""),
            url=d.get("url", ""),
            required=d.get("required", True),
            timeout_ms=d.get("timeout_ms", 10000),
            wait_after_ms=d.get("wait_after_ms", 1000),
            retry_count=d.get("retry_count", 1),
            continue_on_error=d.get("continue_on_error", False),
            success_selector_keys=d.get("success_selector_keys", []),
            error_selector_keys=d.get("error_selector_keys", []),
            login_selector_keys=d.get("login_selector_keys", []),
            auth_selector_keys=d.get("auth_selector_keys", []),
        )


# ── Step Result ──────────────────────────────────────────────────

@dataclass
class StepResult:
    """Result of executing a single step."""
    step_name: str
    action: str
    success: bool
    error: str = ""
    duration_ms: float = 0
    locator_strategy_used: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


# ── Value Source Resolver ────────────────────────────────────────

class ValueResolver:
    """
    Resolve value_source strings to actual values.

    Convention:
        job.caption        → job object attribute
        account.username   → account object attribute  
        platform.base_urls.upload → platform config nested key
        literal:Post now   → literal string "Post now"
        (empty)            → None
    """

    @staticmethod
    def resolve(source: str, context: dict) -> Any:
        if not source:
            return None

        # Literal value
        if source.startswith("literal:"):
            return source[8:]

        parts = source.split(".", 1)
        if len(parts) < 2:
            return context.get(source)

        obj_name, attr_path = parts
        obj = context.get(obj_name)
        if obj is None:
            return None

        # Navigate nested attributes/keys
        for key in attr_path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(key)
            elif hasattr(obj, key):
                obj = getattr(obj, key)
            else:
                return None
            if obj is None:
                return None

        return obj


# ── Action Executor ──────────────────────────────────────────────

class ActionExecutor:
    """
    Executes individual workflow steps against a Playwright page.

    Usage:
        executor = ActionExecutor(page, "tiktok", platform_config)
        result = executor.execute_step(step_config, context)
        results = executor.execute_steps(step_configs, context)
    """

    def __init__(
        self,
        page: Page,
        platform: str,
        platform_config: Any = None,
    ):
        self.page = page
        self.platform = platform
        self.platform_config = platform_config
        self.locator_engine = LocatorStrategy(page, platform)
        self._step_log: list[StepResult] = []

    def execute_steps(
        self,
        steps: list[StepConfig],
        context: dict,
        job_id: int = 0,
    ) -> tuple[bool, list[StepResult]]:
        """
        Execute a list of steps sequentially.

        Returns (overall_success, list_of_step_results).
        Stops on first required step failure (unless continue_on_error).
        """
        results: list[StepResult] = []
        overall_ok = True

        for i, step in enumerate(steps):
            logger.info(
                "[%s][Job %s] Step %d/%d: %s (%s)",
                self.platform, job_id, i + 1, len(steps),
                step.name, step.action,
            )
            update_active_node(job_id, step.name)

            result = self.execute_step(step, context, job_id=job_id)
            results.append(result)
            self._step_log.append(result)

            if result.success:
                logger.info(
                    "[%s][Job %s] ✓ Step '%s' OK (%.0fms, strategy=%s)",
                    self.platform, job_id, step.name,
                    result.duration_ms, result.locator_strategy_used or "n/a",
                )
            else:
                logger.warning(
                    "[%s][Job %s] ✗ Step '%s' FAILED: %s",
                    self.platform, job_id, step.name, result.error,
                )
                if step.required and not step.continue_on_error:
                    overall_ok = False
                    logger.error(
                        "[%s][Job %s] Required step '%s' failed. Aborting workflow.",
                        self.platform, job_id, step.name,
                    )
                    break
                else:
                    logger.info(
                        "[%s][Job %s] Step '%s' is optional/continue_on_error. Continuing.",
                        self.platform, job_id, step.name,
                    )

        return overall_ok, results

    def execute_step(
        self,
        step: StepConfig,
        context: dict,
        job_id: int = 0,
    ) -> StepResult:
        """Execute a single step with retry support."""
        last_result = StepResult(
            step_name=step.name,
            action=step.action,
            success=False,
            error="No attempts made",
        )

        for attempt in range(max(1, step.retry_count)):
            t0 = time.time()
            try:
                result = self._dispatch_action(step, context, job_id)
                result.duration_ms = (time.time() - t0) * 1000
                last_result = result

                if result.success:
                    # Wait after successful action
                    if step.wait_after_ms > 0:
                        self.page.wait_for_timeout(step.wait_after_ms)
                    return result
                else:
                    if attempt < step.retry_count - 1:
                        logger.info(
                            "[%s] Retry %d/%d for step '%s'",
                            self.platform, attempt + 2, step.retry_count, step.name,
                        )
                        self.page.wait_for_timeout(1000)  # Brief pause before retry

            except Exception as e:
                last_result = StepResult(
                    step_name=step.name,
                    action=step.action,
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - t0) * 1000,
                    artifacts=self._capture_artifacts(job_id, step.name),
                )
                if attempt < step.retry_count - 1:
                    logger.info(
                        "[%s] Retry %d/%d for step '%s' after error: %s",
                        self.platform, attempt + 2, step.retry_count, step.name, e,
                    )
                    self.page.wait_for_timeout(1000)

        return last_result

    # ── Action Dispatch ──────────────────────────────────────────

    def _dispatch_action(
        self,
        step: StepConfig,
        context: dict,
        job_id: int,
    ) -> StepResult:
        """Route to the correct action handler."""
        action = step.action.lower()
        handlers = {
            "navigate": self._action_navigate,
            "click": self._action_click,
            "fill": self._action_fill,
            "upload_file": self._action_upload_file,
            "wait": self._action_wait,
            "verify": self._action_verify,
            "check_auth": self._action_check_auth,
        }

        handler = handlers.get(action)
        if not handler:
            # Legacy string-only step — skip gracefully
            if action == "legacy":
                return StepResult(
                    step_name=step.name, action=action,
                    success=True, details={"skipped": "legacy step format"},
                )
            return StepResult(
                step_name=step.name, action=action,
                success=False, error=f"Unknown action type: {action}",
            )

        return handler(step, context, job_id)

    # ── Action: Navigate ─────────────────────────────────────────

    def _action_navigate(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Navigate to a URL."""
        url = step.url  # Literal URL first

        # Try url_key from platform config
        if not url and step.url_key and self.platform_config:
            base_urls = getattr(self.platform_config, "base_urls", {}) or {}
            url = base_urls.get(step.url_key, "")

        # Try value_source
        if not url and step.value_source:
            url = ValueResolver.resolve(step.value_source, context)

        if not url:
            return StepResult(
                step_name=step.name, action="navigate",
                success=False,
                error=f"No URL resolved (url_key={step.url_key!r}, url={step.url!r})",
            )

        self.page.goto(str(url), wait_until="domcontentloaded")
        return StepResult(
            step_name=step.name, action="navigate",
            success=True, details={"url": str(url)},
        )

    # ── Action: Click ────────────────────────────────────────────

    def _action_click(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Click an element resolved via selector_keys."""
        candidates = self._build_candidates(step.selector_keys)
        if not candidates:
            return StepResult(
                step_name=step.name, action="click",
                success=False, error="No selector candidates provided.",
            )

        result = self.locator_engine.resolve(
            step.name, candidates,
            must_be_visible=True,
            timeout_ms=step.timeout_ms,
        )

        if not result.found or not result.locator:
            return StepResult(
                step_name=step.name, action="click",
                success=False,
                error=f"Element not found for click ({result.attempts}/{result.total_candidates} tried)",
                artifacts=self._capture_artifacts(job_id, step.name),
                details={"locator_log": result.log_entries},
            )

        result.locator.click(timeout=step.timeout_ms)
        return StepResult(
            step_name=step.name, action="click",
            success=True,
            locator_strategy_used=result.strategy_used,
        )

    # ── Action: Fill ─────────────────────────────────────────────

    def _action_fill(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Fill a text field with a resolved value."""
        value = ValueResolver.resolve(step.value_source, context)
        if not value and step.required:
            return StepResult(
                step_name=step.name, action="fill",
                success=False,
                error=f"No value resolved from source: {step.value_source!r}",
            )
        if not value:
            return StepResult(
                step_name=step.name, action="fill",
                success=True, details={"skipped": "empty value, step not required"},
            )

        candidates = self._build_candidates(step.selector_keys)
        result = self.locator_engine.resolve(
            step.name, candidates,
            must_be_visible=True,
            timeout_ms=step.timeout_ms,
        )

        if not result.found or not result.locator:
            return StepResult(
                step_name=step.name, action="fill",
                success=False,
                error="Fill target not found.",
                artifacts=self._capture_artifacts(job_id, step.name),
                details={"locator_log": result.log_entries},
            )

        # Click to focus, then fill
        try:
            result.locator.click()
            self.page.wait_for_timeout(300)
        except Exception:
            pass

        result.locator.fill(str(value))
        return StepResult(
            step_name=step.name, action="fill",
            success=True,
            locator_strategy_used=result.strategy_used,
            details={"chars_filled": len(str(value))},
        )

    # ── Action: Upload File ──────────────────────────────────────

    def _action_upload_file(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Attach a file to a file input element."""
        import os
        file_path = ValueResolver.resolve(step.value_source, context)
        if not file_path:
            return StepResult(
                step_name=step.name, action="upload_file",
                success=False,
                error=f"No file path from source: {step.value_source!r}",
            )

        if not os.path.exists(str(file_path)):
            return StepResult(
                step_name=step.name, action="upload_file",
                success=False,
                error=f"File not found: {file_path}",
            )

        candidates = self._build_candidates(step.selector_keys)
        result = self.locator_engine.resolve(
            step.name, candidates,
            must_be_visible=False,  # File inputs are typically hidden
            timeout_ms=step.timeout_ms,
        )

        if not result.found or not result.locator:
            return StepResult(
                step_name=step.name, action="upload_file",
                success=False,
                error="File input element not found.",
                artifacts=self._capture_artifacts(job_id, step.name),
                details={"locator_log": result.log_entries},
            )

        result.locator.set_input_files(str(file_path))
        return StepResult(
            step_name=step.name, action="upload_file",
            success=True,
            locator_strategy_used=result.strategy_used,
            details={"file": str(file_path)},
        )

    # ── Action: Wait ─────────────────────────────────────────────

    def _action_wait(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Static wait."""
        wait_ms = step.timeout_ms or step.wait_after_ms or 1000
        self.page.wait_for_timeout(wait_ms)
        return StepResult(
            step_name=step.name, action="wait",
            success=True, details={"waited_ms": wait_ms},
        )

    # ── Action: Verify ───────────────────────────────────────────

    def _action_verify(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Check for success or error indicators on the page."""
        # Check error indicators first
        for key in step.error_selector_keys:
            candidates = self._build_candidates([key])
            result = self.locator_engine.resolve(
                f"{step.name}:error", candidates,
                must_be_visible=True,
                timeout_ms=3000,
            )
            if result.found:
                return StepResult(
                    step_name=step.name, action="verify",
                    success=False,
                    error="Error indicator found on page.",
                    artifacts=self._capture_artifacts(job_id, step.name),
                    details={"error_selector": key},
                )

        # Check success indicators
        for key in step.success_selector_keys:
            candidates = self._build_candidates([key])
            result = self.locator_engine.resolve(
                f"{step.name}:success", candidates,
                must_be_visible=True,
                timeout_ms=3000,
            )
            if result.found:
                return StepResult(
                    step_name=step.name, action="verify",
                    success=True,
                    details={"success_selector": key},
                )

        # Neither found — ambiguous
        return StepResult(
            step_name=step.name, action="verify",
            success=True,  # Treat ambiguous as non-fatal
            details={"status": "ambiguous", "note": "No explicit success/error indicator found"},
        )

    # ── Action: Check Auth ───────────────────────────────────────

    def _action_check_auth(
        self, step: StepConfig, context: dict, job_id: int,
    ) -> StepResult:
        """Validate that the browser session is authenticated."""
        # Check authenticated indicators
        for key in step.auth_selector_keys:
            candidates = self._build_candidates([key])
            result = self.locator_engine.resolve(
                f"{step.name}:auth", candidates,
                must_be_visible=True,
                timeout_ms=3000,
            )
            if result.found:
                return StepResult(
                    step_name=step.name, action="check_auth",
                    success=True, details={"status": "authenticated"},
                )

        # Check login indicators
        for key in step.login_selector_keys:
            candidates = self._build_candidates([key])
            result = self.locator_engine.resolve(
                f"{step.name}:login", candidates,
                must_be_visible=True,
                timeout_ms=3000,
            )
            if result.found:
                return StepResult(
                    step_name=step.name, action="check_auth",
                    success=False,
                    error="Session expired. Manual re-login required.",
                    details={"status": "needs_login"},
                )

        return StepResult(
            step_name=step.name, action="check_auth",
            success=False,
            error="Cannot determine auth state.",
            details={"status": "ambiguous"},
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _build_candidates(self, selector_keys: list[str]) -> list[LocatorCandidate]:
        """
        Build LocatorCandidate list from selector_keys.
        Each key is looked up in DB first, then used as raw CSS fallback.
        """
        candidates: list[LocatorCandidate] = []

        for key in selector_keys:
            # Try DB lookup: key format is "category:selector_name"
            parts = key.split(":", 1)
            if len(parts) == 2:
                db_candidates = self.locator_engine.build_candidates_from_db(
                    parts[0], parts[1],
                )
                candidates.extend(db_candidates)
            else:
                # Raw selector as CSS fallback
                candidates.append(LocatorCandidate(
                    strategy="css_fallback",
                    locator_type="css",
                    value=key,
                    source="literal",
                ))

        return candidates

    def _capture_artifacts(self, job_id: int, stage: str) -> dict[str, str]:
        """Capture screenshot + HTML for debugging."""
        artifacts: dict[str, str] = {}
        if not self.page:
            return artifacts

        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage).strip("_") or "unknown"
        d = Path(LOGS_DIR) / self.platform
        d.mkdir(parents=True, exist_ok=True)
        bp = d / f"job_{job_id}_{safe}"

        try:
            ss = bp.with_suffix(".png")
            self.page.screenshot(path=str(ss), full_page=False)
            artifacts["screenshot"] = str(ss)
        except Exception as e:
            logger.warning("[%s] Screenshot failed: %s", self.platform, e)

        try:
            hp = bp.with_suffix(".html")
            hp.write_text(self.page.content(), encoding="utf-8")
            artifacts["html"] = str(hp)
        except Exception as e:
            logger.warning("[%s] HTML capture failed: %s", self.platform, e)

        return artifacts

    def get_step_log(self) -> list[StepResult]:
        """Return full execution audit trail."""
        return list(self._step_log)
