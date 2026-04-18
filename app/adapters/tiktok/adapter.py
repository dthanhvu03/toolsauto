"""
TikTok Adapter — Resilient automation with multi-layer locator strategy.

Architecture (per user review):
- Session: Local persistent profile, manual login if expired
- Locators: DB primary → DB secondary → heuristic fallback
- Flow: Navigate → Upload → Caption → Confirm
- Logging: Every step traced with source, timing, result
- No bypass/hack of platform security mechanisms
"""
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Playwright, BrowserContext, Page, Locator

from app.adapters.contracts import AdapterInterface, PublishResult
from app.adapters.common.session import PlatformSessionManager, SessionStatus
from app.adapters.common.locator import LocatorStrategy, LocatorCandidate
from app.adapters.tiktok.selectors import HEURISTIC_SELECTORS
from app.database.models import Job
from app.config import SAFE_MODE, LOGS_DIR, TIKTOK_HOST, TIKTOK_UPLOAD_URL

logger = logging.getLogger(__name__)

# Optional: import tracer if available
try:
    from app.services.job_tracer import update_active_node
except ImportError:
    def update_active_node(*a, **kw): pass

try:
    from app.services.runtime_events import emit as rt_emit
except ImportError:
    def rt_emit(*a, **kw): pass


class TiktokAdapter(AdapterInterface):
    """
    TikTok automation adapter with resilient locator strategy.
    
    Session flow:
    1. open_session() → launch persistent browser with user's profile
    2. Validate session → if expired, return error (user must re-login manually)
    3. publish() → Navigate → Upload → Caption → Confirm
    4. close_session() → guaranteed cleanup
    """

    PLATFORM = "tiktok"
    UPLOAD_URL = TIKTOK_UPLOAD_URL

    def __init__(self):
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._locator_engine: LocatorStrategy | None = None

    # ── Phase 1: Session Management ──────────────────────────────

    def open_session(self, profile_path: str) -> bool:
        """
        Launch persistent browser context using user's local profile.
        Does NOT attempt to bypass login — if session is expired,
        returns False and logs clear instructions for manual re-login.
        """
        if self.playwright or self.context or self.page:
            logger.warning("TiktokAdapter: Session already open, closing previous.")
            self.close_session()

        logger.info("TiktokAdapter: Opening persistent context at: %s", profile_path)

        bundle = PlatformSessionManager.launch(
            profile_path=profile_path,
            platform=self.PLATFORM,
            headless=False,  # Visible browser for potential manual login
            viewport={"width": 1280, "height": 720},
        )

        if not bundle:
            logger.error(
                "TiktokAdapter: Failed to launch browser. "
                "Check Playwright installation and profile path."
            )
            return False

        self.playwright, self.context, self.page = bundle
        self._locator_engine = LocatorStrategy(self.page, self.PLATFORM)

        # Navigate to TikTok to check session validity
        try:
            self.page.goto(f"{TIKTOK_HOST}/", wait_until="domcontentloaded")
            self.page.wait_for_timeout(3000)
        except Exception as e:
            logger.error("TiktokAdapter: Failed to navigate to TikTok: %s", e)
            self.close_session()
            return False

        # Validate session state
        login_indicators = [
            sel[1] for sel in HEURISTIC_SELECTORS["login"]["login_indicators"]
            if sel[0] == "css"
        ]
        auth_indicators = [
            sel[1] for sel in HEURISTIC_SELECTORS["login"]["authenticated_indicators"]
            if sel[0] == "css"
        ]

        session_status = PlatformSessionManager.check_session_valid(
            self.page,
            self.PLATFORM,
            login_indicators=login_indicators,
            authenticated_indicators=auth_indicators,
        )

        if session_status == SessionStatus.NEEDS_LOGIN:
            logger.error(
                "TiktokAdapter: Session is not authenticated. "
                "Please open the browser manually and log into TikTok, "
                "then retry the job. Profile path: %s",
                profile_path,
            )
            rt_emit(
                "session_invalid",
                platform=self.PLATFORM,
                reason="needs_manual_login",
                profile_path=profile_path,
            )
            return False

        if session_status == SessionStatus.EXPIRED:
            logger.warning(
                "TiktokAdapter: Session state is ambiguous. "
                "Proceeding cautiously — may fail at upload step."
            )

        logger.info("TiktokAdapter: Session opened successfully.")
        return True

    # ── Phase 3: Publish Flow ────────────────────────────────────

    def publish(self, job: Job) -> PublishResult:
        """
        Execute TikTok upload automation.
        Flow: Navigate to Upload → Attach File → Fill Caption → Click Post.
        """
        logger.info("TiktokAdapter: Publishing job %s", job.id)

        if not self.page or not self._locator_engine:
            return PublishResult(
                ok=False, error="Browser session not initialized.", is_fatal=True
            )

        engine = self._locator_engine

        try:
            # ── Step 1: Navigate to Upload Page ──
            update_active_node(job.id, "navigate_upload")
            logger.info("TiktokAdapter: Navigating to upload page...")

            self.page.goto(self.UPLOAD_URL, wait_until="domcontentloaded")
            self.page.wait_for_timeout(4000)

            # Re-check auth after navigation (TikTok may redirect to login)
            current_url = self.page.url.lower()
            if "login" in current_url or "signin" in current_url:
                return self._failure_result(
                    job.id, "navigate_upload",
                    "TikTok redirected to login page. Session expired — "
                    "manual re-login required.",
                    is_fatal=True,
                    extra={"invalidate_account": True},
                )

            # ── Step 2: Upload Media File ──
            update_active_node(job.id, "upload_media")
            logger.info("TiktokAdapter: Uploading media: %s", job.media_path)

            if not os.path.exists(job.media_path):
                return self._failure_result(
                    job.id, "upload_media",
                    f"Media file not found: {job.media_path}",
                )

            # Find file input using multi-layer strategy
            file_candidates = engine.build_candidates_from_db(
                "upload", "file_input",
                heuristic_fallbacks=[
                    LocatorCandidate(
                        strategy="heuristic", locator_type=sel[0],
                        value=sel[1], source="static"
                    )
                    for sel in HEURISTIC_SELECTORS["upload"]["file_input"]
                ],
            )
            file_result = engine.resolve(
                "file_input", file_candidates,
                must_be_visible=False,  # File inputs are often hidden
            )

            if not file_result.found or not file_result.locator:
                self._log_resolution_failure(job.id, "file_input", file_result)
                return self._failure_result(
                    job.id, "upload_media",
                    "File input not found. TikTok UI may have changed.",
                    extra={"locator_log": file_result.log_entries},
                )

            # Attach file
            try:
                file_result.locator.set_input_files(job.media_path)
                logger.info("TiktokAdapter: Media file attached. Waiting for processing...")
                self.page.wait_for_timeout(8000)  # Wait for upload/processing
            except Exception as e:
                return self._failure_result(
                    job.id, "upload_media",
                    f"Failed to attach media file: {e}",
                )

            # ── Step 3: Fill Caption ──
            update_active_node(job.id, "fill_caption")
            caption = (job.caption or "").strip()
            if caption:
                logger.info("TiktokAdapter: Filling caption (%d chars)", len(caption))

                caption_candidates = engine.build_candidates_from_db(
                    "caption", "caption_input",
                    heuristic_fallbacks=[
                        LocatorCandidate(
                            strategy="heuristic", locator_type=sel[0],
                            value=sel[1], source="static"
                        )
                        for sel in HEURISTIC_SELECTORS["caption"]["caption_input"]
                    ],
                )
                caption_result = engine.resolve("caption_input", caption_candidates)

                if caption_result.found and caption_result.locator:
                    try:
                        caption_result.locator.click()
                        self.page.wait_for_timeout(500)
                        # Clear existing content
                        caption_result.locator.press("Control+a")
                        self.page.wait_for_timeout(200)
                        caption_result.locator.fill(caption)
                        logger.info("TiktokAdapter: Caption filled successfully.")
                    except Exception as e:
                        logger.warning(
                            "TiktokAdapter: Caption fill failed: %s. "
                            "Proceeding without caption.", e
                        )
                else:
                    logger.warning(
                        "TiktokAdapter: Caption input not found. "
                        "Publishing without caption."
                    )

            # ── Step 4: Click Post Button ──
            update_active_node(job.id, "post_content")
            logger.info("TiktokAdapter: Looking for Post button...")

            # Wait a moment for UI to settle after caption
            self.page.wait_for_timeout(2000)

            post_candidates = engine.build_candidates_from_db(
                "publish", "post_button",
                heuristic_fallbacks=[
                    LocatorCandidate(
                        strategy="heuristic", locator_type=sel[0],
                        value=sel[1], source="static"
                    )
                    for sel in HEURISTIC_SELECTORS["publish"]["post_button"]
                ],
            )
            post_result = engine.resolve(
                "post_button", post_candidates,
                must_be_visible=True,
                must_be_enabled=True,
            )

            if not post_result.found or not post_result.locator:
                self._log_resolution_failure(job.id, "post_button", post_result)
                return self._failure_result(
                    job.id, "post_button",
                    "Post button not found or not enabled.",
                    extra={"locator_log": post_result.log_entries},
                )

            if SAFE_MODE:
                logger.info("TiktokAdapter: SAFE_MODE enabled — skipping final click.")
                return PublishResult(
                    ok=True,
                    external_post_id="safe_mode_dry_run",
                    details={"msg": "Dry run successful", "safe_mode": True},
                )

            # Click Post
            try:
                post_result.locator.click(timeout=10000)
                logger.info("TiktokAdapter: Post button clicked.")
            except Exception as e:
                return self._failure_result(
                    job.id, "post_click",
                    f"Failed to click Post button: {e}",
                )

            # ── Step 5: Verify Submission ──
            update_active_node(job.id, "verify_post")
            logger.info("TiktokAdapter: Waiting for upload confirmation...")
            self.page.wait_for_timeout(10000)

            # Check for success/error indicators
            confirmation = self._check_post_confirmation(engine)

            if confirmation == "error":
                return self._failure_result(
                    job.id, "verify_post",
                    "TikTok displayed an error after posting.",
                )

            logger.info(
                "TiktokAdapter: Post completed (confirmation=%s).",
                confirmation,
            )
            return PublishResult(
                ok=True,
                details={
                    "confirmation": confirmation,
                    "locator_audit": engine.get_resolution_log(),
                },
            )

        except Exception as e:
            logger.exception("TiktokAdapter: Unhandled error in publish: %s", e)
            self._capture_debug_artifacts(job.id, "unhandled_error")
            return self._failure_result(
                job.id, "unhandled",
                f"Unhandled error: {e}",
            )

    # ── Idempotency Check ────────────────────────────────────────

    def check_published_state(self, job: Job) -> PublishResult:
        """Check if a post already exists (for retry idempotency)."""
        logger.info("TiktokAdapter: check_published_state for job %s", job.id)
        # TikTok doesn't have a simple timeline scrape mechanism
        # Return not-found to let publisher proceed normally
        return PublishResult(ok=False, error="TikTok footprint check not implemented yet")

    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        """Post a comment on a TikTok video."""
        logger.info("TiktokAdapter: post_comment to %s", post_url)
        return PublishResult(ok=False, error="TikTok comment not implemented yet")

    # ── Session Cleanup ──────────────────────────────────────────

    def close_session(self) -> None:
        """Guaranteed cleanup of all browser resources."""
        logger.info("TiktokAdapter: Closing session.")
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.playwright = None
        self._locator_engine = None

    # ── Internal Helpers ─────────────────────────────────────────

    def _check_post_confirmation(self, engine: LocatorStrategy) -> str:
        """Check for success or error indicators after posting."""
        # Check success indicators
        for ltype, lval in HEURISTIC_SELECTORS["confirmation"]["success_indicators"]:
            try:
                loc = self.page.locator(lval) if ltype == "css" else self.page.get_by_text(lval)
                if loc.count() > 0:
                    return "success"
            except Exception:
                continue

        # Check error indicators
        for ltype, lval in HEURISTIC_SELECTORS["confirmation"]["error_indicators"]:
            try:
                loc = self.page.locator(lval) if ltype == "css" else self.page.get_by_text(lval)
                if loc.count() > 0:
                    return "error"
            except Exception:
                continue

        return "unknown"

    def _failure_result(
        self,
        job_id: int,
        stage: str,
        error: str,
        *,
        is_fatal: bool = False,
        extra: dict | None = None,
    ) -> PublishResult:
        """Create a standardized failure result with debug artifacts."""
        artifacts = self._capture_debug_artifacts(job_id, stage)
        details = {"failed_stage": stage, "artifacts": artifacts}
        if extra:
            details.update(extra)
        return PublishResult(
            ok=False, error=error, is_fatal=is_fatal,
            details=details, artifacts=artifacts,
        )

    def _capture_debug_artifacts(self, job_id: int, stage: str) -> dict[str, str]:
        """Capture screenshot + HTML for debugging."""
        artifacts: dict[str, str] = {}
        if not self.page:
            return artifacts

        import re
        safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage).strip("_") or "unknown"
        artifact_dir = Path(LOGS_DIR) / "tiktok"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        base_path = artifact_dir / f"job_{job_id}_{safe_stage}"

        try:
            ss_path = base_path.with_suffix(".png")
            self.page.screenshot(path=str(ss_path), full_page=False)
            artifacts["screenshot"] = str(ss_path)
        except Exception as e:
            logger.warning("TiktokAdapter: Screenshot capture failed: %s", e)

        try:
            html_path = base_path.with_suffix(".html")
            html_path.write_text(self.page.content(), encoding="utf-8")
            artifacts["html"] = str(html_path)
        except Exception as e:
            logger.warning("TiktokAdapter: HTML capture failed: %s", e)

        return artifacts

    def _log_resolution_failure(self, job_id: int, action: str, result) -> None:
        """Log locator resolution failure details."""
        logger.warning(
            "TiktokAdapter: [Job %s] Locator '%s' failed after %d/%d attempts.",
            job_id, action, result.attempts, result.total_candidates,
        )
        for entry in result.log_entries:
            logger.debug("  %s", entry)
