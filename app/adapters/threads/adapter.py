import logging
import os
import random
import re
import time
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Locator, Page, Playwright

from app.adapters.common.decorators import playwright_safe_action
from app.adapters.common.session import PlatformSessionManager, SessionStatus
from app.adapters.contracts import AdapterInterface, PublishResult
from app.database.models import Job

logger = logging.getLogger(__name__)


class ThreadsSessionInvalidError(RuntimeError):
    """Raised when the stored Threads session is no longer authenticated."""


class ThreadsAdapter(AdapterInterface):
    PLATFORM = "threads"
    HOME_URL = "https://www.threads.net/"
    LOGIN_INDICATORS = (
        'input[name="username"]',
        'input[name="password"]',
        'input[autocomplete="username"]',
        'input[autocomplete="current-password"]',
    )
    AUTH_INDICATORS = (
        'a[href="/notifications"]',
        'a[href^="/@"]',
        'svg[aria-label="Home"]',
        'svg[aria-label="Search"]',
    )
    COMPOSE_SELECTORS = (
        'div[role="button"]:has-text("Start a thread")',
        'div[role="button"]:has-text("New thread")',
        'div[role="button"]:has-text("Create")',
        'div[role="button"]:has-text("Bat dau mot thread")',
        'svg[aria-label="Create"]',
        'svg[aria-label="New thread"]',
    )
    TEXTBOX_SELECTORS = (
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[role="textbox"][contenteditable="true"]',
    )
    FILE_INPUT_SELECTORS = (
        'input[type="file"]',
        'input[type="file"][accept*="image"]',
        'input[type="file"][accept*="video"]',
    )
    POST_BUTTON_SELECTORS = (
        'div[role="button"]:has-text("Post")',
        'div[role="button"]:has-text("Share")',
        'div[role="button"]:has-text("Dang")',
        'button:has-text("Post")',
        'button:has-text("Share")',
    )
    ERROR_TEXTS = (
        "something went wrong",
        "try again later",
        "couldn't post",
        "could not post",
    )
    POST_PATH_RE = re.compile(
        r"(/(?:@[^/?#\"'>]+/post/[^/?#\"'>]+|t/[^/?#\"'>]+))",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._session_status = SessionStatus.EXPIRED

    def open_session(self, profile_path: str) -> bool:
        if self.playwright or self.context or self.page:
            logger.warning(
                "ThreadsAdapter: Session already open, closing previous session first."
            )
            self.close_session()

        logger.info(
            "ThreadsAdapter: Opening persistent context at profile: %s",
            profile_path,
        )
        bundle = PlatformSessionManager.launch(
            profile_path=profile_path,
            platform=self.PLATFORM,
            headless=True,
            viewport={"width": 1280, "height": 720},
            extra_args=["--js-flags=--lite-mode"],
        )
        if not bundle:
            return False

        self.playwright, self.context, self.page = bundle
        try:
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            self._sleep(2.0, 3.0)
            self._session_status = PlatformSessionManager.check_session_valid(
                self.page,
                self.PLATFORM,
                login_indicators=list(self.LOGIN_INDICATORS),
                authenticated_indicators=list(self.AUTH_INDICATORS),
            )
            if self._session_status == SessionStatus.NEEDS_LOGIN:
                logger.warning(
                    "ThreadsAdapter: Session requires manual login for profile %s.",
                    profile_path,
                )
            elif self._session_status == SessionStatus.EXPIRED:
                logger.warning(
                    "ThreadsAdapter: Session state is ambiguous for profile %s.",
                    profile_path,
                )
            else:
                logger.info("ThreadsAdapter: Session opened successfully.")
            return True
        except Exception as exc:
            logger.error("ThreadsAdapter: Failed while opening session: %s", exc)
            self.close_session()
            return False

    @playwright_safe_action(default=False, catch=(Exception,), logger_name=__name__)
    def _is_session_alive(self) -> bool:
        if not self.page or not self.context:
            return False
        _ = self.page.url
        return True

    @playwright_safe_action(default=False, catch=(Exception,), logger_name=__name__)
    def _is_visible(self, locator: Locator | None) -> bool:
        if locator is None:
            return False
        return locator.count() > 0 and locator.is_visible()

    def _sleep(self, min_seconds: float = 0.8, max_seconds: float = 1.6) -> None:
        if not self.page:
            return
        wait_ms = int(random.uniform(min_seconds, max_seconds) * 1000)
        self.page.wait_for_timeout(wait_ms)

    def _find_first_visible(
        self,
        selectors: tuple[str, ...],
        timeout_ms: int = 5000,
    ) -> Locator | None:
        if not self.page:
            return None

        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            for selector in selectors:
                try:
                    locator = self.page.locator(selector).first
                    if self._is_visible(locator):
                        return locator
                except Exception:
                    continue
            self.page.wait_for_timeout(250)
        return None

    def _normalize_post_url(self, value: str | None) -> str | None:
        if not value:
            return None

        match = self.POST_PATH_RE.search(str(value))
        if not match:
            return None

        path = match.group(1).rstrip("/")
        return f"{self.HOME_URL.rstrip('/')}{path}"

    def _extract_post_id(self, post_url: str | None) -> str | None:
        normalized = self._normalize_post_url(post_url)
        if not normalized:
            return None
        return normalized.rstrip("/").split("/")[-1]

    def _collect_urls_from_payload(self, payload: object) -> list[str]:
        found: set[str] = set()

        def visit(value: object) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    visit(item)
                return
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if isinstance(value, str):
                normalized = self._normalize_post_url(value)
                if normalized:
                    found.add(normalized)

        visit(payload)
        return sorted(found)

    @playwright_safe_action(default=list(), catch=(Exception,), logger_name=__name__)
    def _collect_urls_from_dom(self) -> list[str]:
        if not self.page:
            return []

        hrefs = self.page.evaluate(
            """
            () => Array.from(
                document.querySelectorAll('a[href*="/post/"], a[href*="/t/"]')
            )
            .map((node) => node.getAttribute("href"))
            .filter(Boolean)
            """
        ) or []

        urls: list[str] = []
        current_url = self._normalize_post_url(self.page.url)
        if current_url:
            urls.append(current_url)
        for href in hrefs:
            normalized = self._normalize_post_url(href)
            if normalized and normalized not in urls:
                urls.append(normalized)

        if urls:
            return urls

        html = self.page.content()
        for path in self.POST_PATH_RE.findall(html):
            normalized = self._normalize_post_url(path)
            if normalized and normalized not in urls:
                urls.append(normalized)
        return urls

    def _capture_post_reference(self, observed_urls: list[str]) -> tuple[str | None, str | None]:
        ordered_urls: list[str] = []
        for candidate in observed_urls + self._collect_urls_from_dom():
            normalized = self._normalize_post_url(candidate)
            if normalized and normalized not in ordered_urls:
                ordered_urls.append(normalized)

        if not ordered_urls:
            return None, None

        post_url = ordered_urls[0]
        return post_url, self._extract_post_id(post_url)

    def _session_invalid_result(self, reason: str) -> PublishResult:
        message = f"SessionInvalid: {reason}"
        return PublishResult(
            ok=False,
            is_fatal=True,
            error=message,
            details={"invalidate_account": True},
        )

    def _page_needs_login(self) -> bool:
        if not self.page:
            return True

        current_url = (self.page.url or "").lower()
        if "login" in current_url:
            return True

        content = self.page.content()
        if '"is_logged_out":true' in content or '"is_logged_out": true' in content:
            return True

        for selector in self.LOGIN_INDICATORS:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _wait_for_post_button_ready(self, locator: Locator) -> bool:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if locator.get_attribute("aria-disabled") != "true":
                    return True
            except Exception:
                pass
            self._sleep(0.6, 1.1)
        return False

    def _page_has_publish_error(self) -> bool:
        if not self.page:
            return True

        body_text = (self.page.content() or "").lower()
        return any(error_text in body_text for error_text in self.ERROR_TEXTS)

    def publish(self, job: Job) -> PublishResult:
        logger.info("ThreadsAdapter: Publishing job %s", job.id)

        if not self.page or not self._is_session_alive():
            return PublishResult(
                ok=False,
                error="Browser session is not initialized.",
                is_fatal=True,
            )

        if self._session_status == SessionStatus.NEEDS_LOGIN or self._page_needs_login():
            logger.error("ThreadsAdapter: Account session is no longer authenticated.")
            return self._session_invalid_result("account session is logged out")

        caption = (job.caption or "").strip()
        observed_urls: list[str] = []

        def capture_response(response) -> None:
            try:
                parsed = urlparse(response.url)
            except Exception:
                return

            if "threads.net" not in parsed.netloc:
                return

            try:
                payload = response.json()
            except Exception:
                return

            for url in self._collect_urls_from_payload(payload):
                if url not in observed_urls:
                    observed_urls.append(url)

        self.page.on("response", capture_response)
        try:
            self.page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=60000)
            self._sleep(2.0, 3.0)

            if self._page_needs_login():
                return self._session_invalid_result("account session is logged out")

            compose_button = self._find_first_visible(self.COMPOSE_SELECTORS, timeout_ms=12000)
            if not compose_button:
                return PublishResult(
                    ok=False,
                    error="Could not find Threads compose button.",
                    is_fatal=False,
                )
            compose_button.click()
            self._sleep(1.2, 2.0)

            textbox = self._find_first_visible(self.TEXTBOX_SELECTORS, timeout_ms=10000)
            if not textbox:
                return PublishResult(
                    ok=False,
                    error="Could not find Threads caption textbox.",
                    is_fatal=False,
                )

            textbox.click()
            self._sleep(0.4, 0.8)
            if caption:
                textbox.fill(caption)
                self._sleep(0.8, 1.4)

            media_path = job.media_path
            if media_path:
                if not os.path.exists(media_path):
                    return PublishResult(
                        ok=False,
                        error=f"Media file not found: {media_path}",
                        is_fatal=False,
                    )

                file_input = self._find_first_visible(
                    self.FILE_INPUT_SELECTORS,
                    timeout_ms=5000,
                )
                if not file_input:
                    return PublishResult(
                        ok=False,
                        error="Could not find Threads media file input.",
                        is_fatal=False,
                    )

                file_input.set_input_files(media_path)
                self._sleep(4.0, 6.0)

            post_button = self._find_first_visible(self.POST_BUTTON_SELECTORS, timeout_ms=10000)
            if not post_button:
                return PublishResult(
                    ok=False,
                    error="Could not find Threads Post button.",
                    is_fatal=False,
                )
            if not self._wait_for_post_button_ready(post_button):
                return PublishResult(
                    ok=False,
                    error="Threads Post button never became enabled.",
                    is_fatal=False,
                )

            post_button.click()
            self._sleep(2.0, 3.0)

            deadline = time.time() + 30
            while time.time() < deadline:
                if self._page_has_publish_error():
                    return PublishResult(
                        ok=False,
                        error="Threads reported a publish error.",
                        is_fatal=False,
                    )

                post_url, external_post_id = self._capture_post_reference(observed_urls)
                if post_url:
                    logger.info(
                        "ThreadsAdapter: Publish completed for job %s with post_url=%s",
                        job.id,
                        post_url,
                    )
                    return PublishResult(
                        ok=True,
                        details={"post_url": post_url},
                        external_post_id=external_post_id,
                    )

                self._sleep(1.0, 1.8)

            return PublishResult(
                ok=False,
                error="Publish action completed but post_url could not be captured.",
                is_fatal=False,
            )
        except ThreadsSessionInvalidError as exc:
            logger.error("ThreadsAdapter: Session invalid while publishing: %s", exc)
            return self._session_invalid_result(str(exc))
        except Exception as exc:
            logger.error("ThreadsAdapter: Exception during publish: %s", exc)
            return PublishResult(ok=False, error=str(exc), is_fatal=False)
        finally:
            try:
                self.page.remove_listener("response", capture_response)
            except Exception:
                pass

    def check_published_state(self, job: Job) -> PublishResult:
        if not self.page or not self._is_session_alive():
            return PublishResult(
                ok=False,
                error="Browser session is not initialized.",
                is_fatal=False,
            )

        post_url = self._normalize_post_url(getattr(job, "post_url", None))
        if not post_url:
            return PublishResult(
                ok=False,
                error="Threads footprint check requires an existing post_url.",
                is_fatal=False,
            )

        try:
            self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            self._sleep(1.5, 2.5)
            if self._page_needs_login():
                return self._session_invalid_result("account session is logged out")
            if self._page_has_publish_error():
                return PublishResult(
                    ok=False,
                    error="Threads post page shows an error state.",
                    is_fatal=False,
                )
            return PublishResult(
                ok=True,
                details={"post_url": post_url},
                external_post_id=self._extract_post_id(post_url),
            )
        except Exception as exc:
            return PublishResult(
                ok=False,
                error=f"Threads footprint check failed: {exc}",
                is_fatal=False,
            )

    def close_session(self) -> None:
        try:
            if self.page:
                self.page.close()
        except Exception as exc:
            logger.warning("ThreadsAdapter: Error closing page: %s", exc)
        try:
            if self.context:
                self.context.close()
        except Exception as exc:
            logger.warning("ThreadsAdapter: Error closing context: %s", exc)
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            logger.warning("ThreadsAdapter: Error stopping Playwright: %s", exc)

        self.playwright = None
        self.context = None
        self.page = None
        self._session_status = SessionStatus.EXPIRED
