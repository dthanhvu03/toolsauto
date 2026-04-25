"""
Instagram Adapter — Resilient automation with multi-layer locator strategy.

Architecture mirrors TiktokAdapter:
- Session: Local persistent profile, manual login if expired
- Locators: DB primary → DB secondary → heuristic fallback
- Flow: Navigate → New Post → Upload → Caption → Next → Share
- No bypass of platform security mechanisms
"""
import logging
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import Playwright, BrowserContext, Page

from app.adapters.contracts import AdapterInterface, PublishResult
from app.adapters.common.session import PlatformSessionManager, SessionStatus
from app.adapters.common.locator import LocatorStrategy, LocatorCandidate
from app.adapters.instagram.selectors import HEURISTIC_SELECTORS
from app.database.models import Job
from app.config import SAFE_MODE, LOGS_DIR, INSTAGRAM_HOST

logger = logging.getLogger(__name__)

try:
    from app.services.job_tracer import update_active_node
except ImportError:
    def update_active_node(*a, **kw): pass

try:
    from app.services.runtime_events import emit as rt_emit
except ImportError:
    def rt_emit(*a, **kw): pass


class InstagramAdapter(AdapterInterface):
    """
    Instagram automation adapter with resilient locator strategy.
    
    Instagram web flow (Reels/Post):
    1. Log in via persistent profile
    2. Click "New post" (+ icon)
    3. Select file from computer  
    4. Fill caption
    5. Click "Next" (possibly multiple times for filters/crop)
    6. Click "Share"
    """

    PLATFORM = "instagram"
    HOME_URL = f"{INSTAGRAM_HOST}/"
    HOST_NETLOC = urlparse(INSTAGRAM_HOST).netloc.lower()

    def __init__(self):
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._locator_engine: LocatorStrategy | None = None

    # ── Phase 1: Session Management ──────────────────────────────

    def open_session(self, profile_path: str) -> bool:
        """Launch persistent browser with user's local profile."""
        if self.playwright or self.context or self.page:
            logger.warning("InstagramAdapter: Session already open, closing previous.")
            self.close_session()

        logger.info("InstagramAdapter: Opening persistent context at: %s", profile_path)

        bundle = PlatformSessionManager.launch(
            profile_path=profile_path,
            platform=self.PLATFORM,
            headless=False,
            viewport={"width": 1280, "height": 720},
        )

        if not bundle:
            logger.error("InstagramAdapter: Failed to launch browser.")
            return False

        self.playwright, self.context, self.page = bundle
        self._locator_engine = LocatorStrategy(self.page, self.PLATFORM)

        # Navigate to Instagram
        try:
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded")
            self.page.wait_for_timeout(4000)
        except Exception as e:
            logger.error("InstagramAdapter: Navigation failed: %s", e)
            self.close_session()
            return False

        # Session validation
        login_indicators = [
            s[1] for s in HEURISTIC_SELECTORS["login"]["login_indicators"]
            if s[0] == "css"
        ]
        auth_indicators = [
            s[1] for s in HEURISTIC_SELECTORS["login"]["authenticated_indicators"]
            if s[0] == "css"
        ]

        status = PlatformSessionManager.check_session_valid(
            self.page, self.PLATFORM,
            login_indicators=login_indicators,
            authenticated_indicators=auth_indicators,
        )

        if status == SessionStatus.NEEDS_LOGIN:
            logger.error(
                "InstagramAdapter: Not authenticated. "
                "Please log in manually then retry. Profile: %s",
                profile_path,
            )
            rt_emit("session_invalid", platform=self.PLATFORM,
                     reason="needs_manual_login", profile_path=profile_path)
            return False

        if status == SessionStatus.EXPIRED:
            logger.warning("InstagramAdapter: Ambiguous session. Proceeding cautiously.")

        logger.info("InstagramAdapter: Session opened successfully.")
        return True

    # ── Phase 3: Publish Flow ────────────────────────────────────

    def publish(self, job: Job) -> PublishResult:
        """
        Instagram publish flow:
        Navigate → New Post → Upload → Caption → Next → Share.
        """
        logger.info("InstagramAdapter: Publishing job %s", job.id)

        if not self.page or not self._locator_engine:
            return PublishResult(
                ok=False, error="Browser session not initialized.", is_fatal=True
            )

        engine = self._locator_engine

        try:
            # ── Step 1: Ensure on Instagram home ──
            update_active_node(job.id, "navigate_home")
            if self.HOST_NETLOC not in urlparse(self.page.url).netloc.lower():
                self.page.goto(self.HOME_URL, wait_until="domcontentloaded")
                self.page.wait_for_timeout(3000)

            # Auth re-check
            if "login" in self.page.url.lower() or "accounts/login" in self.page.url:
                return self._failure_result(
                    job.id, "navigate_home",
                    "Instagram redirected to login. Session expired.",
                    is_fatal=True,
                    extra={"invalidate_account": True},
                )

            # ── Step 2: Click "New Post" button ──
            update_active_node(job.id, "open_new_post")
            logger.info("InstagramAdapter: Opening new post dialog...")

            new_post_candidates = engine.build_candidates_from_db(
                "upload", "new_post_button",
                heuristic_fallbacks=[
                    LocatorCandidate(
                        strategy="heuristic", locator_type=s[0],
                        value=s[1], source="static"
                    )
                    for s in HEURISTIC_SELECTORS["upload"]["new_post_button"]
                ],
            )
            new_post = engine.resolve("new_post_button", new_post_candidates)

            if not new_post.found or not new_post.locator:
                self._log_resolution_failure(job.id, "new_post_button", new_post)
                return self._failure_result(
                    job.id, "open_new_post",
                    "New Post button not found on Instagram.",
                    extra={"locator_log": new_post.log_entries},
                )

            new_post.locator.click()
            self.page.wait_for_timeout(3000)

            # ── Step 3: Upload media ──
            update_active_node(job.id, "upload_media")
            logger.info("InstagramAdapter: Uploading media: %s", job.media_path)

            if not os.path.exists(job.media_path):
                return self._failure_result(
                    job.id, "upload_media",
                    f"Media file not found: {job.media_path}",
                )

            # Find file input
            file_candidates = engine.build_candidates_from_db(
                "upload", "file_input",
                heuristic_fallbacks=[
                    LocatorCandidate(
                        strategy="heuristic", locator_type=s[0],
                        value=s[1], source="static"
                    )
                    for s in HEURISTIC_SELECTORS["upload"]["file_input"]
                ],
            )
            file_result = engine.resolve(
                "file_input", file_candidates, must_be_visible=False
            )

            if not file_result.found or not file_result.locator:
                # Try clicking "Select from computer" first
                select_candidates = engine.build_candidates_from_db(
                    "upload", "select_from_computer",
                    heuristic_fallbacks=[
                        LocatorCandidate(
                            strategy="heuristic", locator_type=s[0],
                            value=s[1], source="static"
                        )
                        for s in HEURISTIC_SELECTORS["upload"]["select_from_computer"]
                    ],
                )
                select_result = engine.resolve("select_from_computer", select_candidates)
                if select_result.found and select_result.locator:
                    select_result.locator.click()
                    self.page.wait_for_timeout(2000)

                # Retry file input
                file_result = engine.resolve(
                    "file_input", file_candidates, must_be_visible=False
                )

            if not file_result.found or not file_result.locator:
                return self._failure_result(
                    job.id, "upload_media",
                    "File input not found on Instagram.",
                    extra={"locator_log": file_result.log_entries},
                )

            try:
                file_result.locator.set_input_files(job.media_path)
                logger.info("InstagramAdapter: Media attached.")
                self.page.wait_for_timeout(6000)
            except Exception as e:
                return self._failure_result(
                    job.id, "upload_media", f"Failed to attach file: {e}"
                )

            # ── Step 4: Navigate through Next buttons ──
            update_active_node(job.id, "navigate_steps")
            for step in range(4):
                next_candidates = engine.build_candidates_from_db(
                    "publish", "next_button",
                    heuristic_fallbacks=[
                        LocatorCandidate(
                            strategy="heuristic", locator_type=s[0],
                            value=s[1], source="static"
                        )
                        for s in HEURISTIC_SELECTORS["publish"]["next_button"]
                    ],
                )
                next_result = engine.resolve("next_button", next_candidates)

                if not next_result.found:
                    break

                logger.info("InstagramAdapter: Clicking Next (step %d)", step + 1)
                next_result.locator.click()
                self.page.wait_for_timeout(3000)

            # ── Step 5: Fill Caption ──
            update_active_node(job.id, "fill_caption")
            caption = (job.caption or "").strip()
            if caption:
                logger.info("InstagramAdapter: Filling caption (%d chars)", len(caption))
                caption_candidates = engine.build_candidates_from_db(
                    "caption", "caption_input",
                    heuristic_fallbacks=[
                        LocatorCandidate(
                            strategy="heuristic", locator_type=s[0],
                            value=s[1], source="static"
                        )
                        for s in HEURISTIC_SELECTORS["caption"]["caption_input"]
                    ],
                )
                caption_result = engine.resolve("caption_input", caption_candidates)

                if caption_result.found and caption_result.locator:
                    try:
                        caption_result.locator.click()
                        self.page.wait_for_timeout(500)
                        caption_result.locator.fill(caption)
                        logger.info("InstagramAdapter: Caption filled.")
                    except Exception as e:
                        logger.warning("InstagramAdapter: Caption fill failed: %s", e)
                else:
                    logger.warning("InstagramAdapter: Caption input not found.")

            # ── Step 6: Click Share ──
            update_active_node(job.id, "post_content")
            logger.info("InstagramAdapter: Looking for Share button...")
            self.page.wait_for_timeout(2000)

            share_candidates = engine.build_candidates_from_db(
                "publish", "share_button",
                heuristic_fallbacks=[
                    LocatorCandidate(
                        strategy="heuristic", locator_type=s[0],
                        value=s[1], source="static"
                    )
                    for s in HEURISTIC_SELECTORS["publish"]["share_button"]
                ],
            )
            share_result = engine.resolve(
                "share_button", share_candidates,
                must_be_visible=True,
            )

            if not share_result.found or not share_result.locator:
                return self._failure_result(
                    job.id, "post_content",
                    "Share button not found.",
                    extra={"locator_log": share_result.log_entries},
                )

            if SAFE_MODE:
                logger.info("InstagramAdapter: SAFE_MODE — skipping Share click.")
                return PublishResult(
                    ok=True, external_post_id="safe_mode_dry_run",
                    details={"msg": "Dry run successful", "safe_mode": True},
                )

            share_result.locator.click(timeout=10000)
            logger.info("InstagramAdapter: Share button clicked.")

            # ── Step 7: Verify ──
            update_active_node(job.id, "verify_post")
            self.page.wait_for_timeout(10000)
            confirmation = self._check_post_confirmation()

            if confirmation == "error":
                return self._failure_result(
                    job.id, "verify_post",
                    "Instagram displayed an error after sharing.",
                )

            logger.info("InstagramAdapter: Post completed (confirmation=%s)", confirmation)
            return PublishResult(
                ok=True,
                details={
                    "confirmation": confirmation,
                    "locator_audit": engine.get_resolution_log(),
                },
            )

        except Exception as e:
            logger.exception("InstagramAdapter: Unhandled error: %s", e)
            self._capture_debug_artifacts(job.id, "unhandled_error")
            return self._failure_result(job.id, "unhandled", f"Unhandled error: {e}")

    # ── Idempotency / Comment ────────────────────────────────────

    def check_published_state(self, job: Job) -> PublishResult:
        logger.info("InstagramAdapter: check_published_state for job %s", job.id)
        return PublishResult(ok=False, error="Instagram footprint check not implemented yet")

    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        logger.info("InstagramAdapter: post_comment to %s", post_url)
        return PublishResult(ok=False, error="Instagram comment not implemented yet")

    # ── Cleanup ──────────────────────────────────────────────────

    def close_session(self) -> None:
        logger.info("InstagramAdapter: Closing session.")
        if self.page:
            try: self.page.close()
            except Exception: pass
        if self.context:
            try: self.context.close()
            except Exception: pass
        if self.playwright:
            try: self.playwright.stop()
            except Exception: pass
        self.page = None
        self.context = None
        self.playwright = None
        self._locator_engine = None

    # ── Helpers ──────────────────────────────────────────────────

    def _check_post_confirmation(self) -> str:
        for ltype, lval in HEURISTIC_SELECTORS["confirmation"]["success_indicators"]:
            try:
                loc = self.page.locator(lval) if ltype == "css" else self.page.get_by_text(lval)
                if loc.count() > 0:
                    return "success"
            except Exception:
                continue
        for ltype, lval in HEURISTIC_SELECTORS["confirmation"]["error_indicators"]:
            try:
                loc = self.page.locator(lval) if ltype == "css" else self.page.get_by_text(lval)
                if loc.count() > 0:
                    return "error"
            except Exception:
                continue
        return "unknown"

    def _failure_result(self, job_id, stage, error, *, is_fatal=False, extra=None):
        artifacts = self._capture_debug_artifacts(job_id, stage)
        details = {"failed_stage": stage, "artifacts": artifacts}
        if extra:
            details.update(extra)
        return PublishResult(
            ok=False, error=error, is_fatal=is_fatal,
            details=details, artifacts=artifacts,
        )

    def _capture_debug_artifacts(self, job_id, stage):
        artifacts = {}
        if not self.page:
            return artifacts
        import re
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage).strip("_") or "unknown"
        d = Path(LOGS_DIR) / "instagram"
        d.mkdir(parents=True, exist_ok=True)
        bp = d / f"job_{job_id}_{safe}"
        try:
            ss = bp.with_suffix(".png")
            self.page.screenshot(path=str(ss), full_page=False)
            artifacts["screenshot"] = str(ss)
        except Exception: pass
        try:
            hp = bp.with_suffix(".html")
            hp.write_text(self.page.content(), encoding="utf-8")
            artifacts["html"] = str(hp)
        except Exception: pass
        return artifacts

    def _log_resolution_failure(self, job_id, action, result):
        logger.warning(
            "InstagramAdapter: [Job %s] Locator '%s' failed (%d/%d attempts).",
            job_id, action, result.attempts, result.total_candidates,
        )
        for entry in result.log_entries:
            logger.debug("  %s", entry)
