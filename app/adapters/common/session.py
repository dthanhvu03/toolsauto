"""
Common Session Manager — Playwright persistent context bootstrap.
Extracted from FacebookSessionManager pattern, generalized for all platforms.
Each platform adapter calls PlatformSessionManager.launch() with its own config.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from app.config import (
    PLAYWRIGHT_DEFAULT_TIMEOUT_MS,
    PROFILES_DIR,
)
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

logger = logging.getLogger(__name__)


class SessionStatus:
    """Describes result of session health check."""
    VALID = "valid"
    EXPIRED = "expired"
    MISSING_PROFILE = "missing_profile"
    NEEDS_LOGIN = "needs_login"


class PlatformSessionManager:
    """
    Launch and manage Chromium persistent contexts for any platform.
    
    Design principles (per user review):
    - Does NOT attempt to bypass any login/checkpoint mechanisms
    - If session is invalid, returns clear status for manual re-login
    - Never assumes sessions last forever
    - Each platform gets its own isolated profile directory
    """

    @staticmethod
    def resolve_profile_path(profile_path: str, platform: str = "") -> str:
        """
        Ensures profile_path is valid, rebasing if necessary.
        Similar to FacebookSessionManager._resolve_portable_path but generalized.
        """
        if not profile_path:
            return profile_path

        p = Path(profile_path)

        # 1. Exists as-is
        if p.exists() and p.is_dir():
            return str(p.absolute())

        # 2. Try rebase under PROFILES_DIR
        if p.is_absolute():
            rebased = PROFILES_DIR / p.name
            if rebased.exists() and rebased.is_dir():
                logger.info(
                    "%sSessionManager: Path rebased %s -> %s",
                    platform.capitalize() if platform else "Platform",
                    profile_path, rebased,
                )
                return str(rebased.absolute())

        # 3. Return original (may trigger fresh profile creation)
        return profile_path

    @staticmethod
    def check_profile_health(profile_path: str, platform: str = "") -> str:
        """
        Check if a browser profile directory looks healthy.
        Returns a SessionStatus constant.
        """
        prefix = f"{platform.capitalize()}Session" if platform else "Session"
        
        if not profile_path:
            logger.warning("%s: No profile_path provided.", prefix)
            return SessionStatus.MISSING_PROFILE

        pp = profile_path.strip()
        if not os.path.isdir(pp):
            logger.warning(
                "%s: profile_path missing or not a directory: %s",
                prefix, pp,
            )
            return SessionStatus.MISSING_PROFILE

        default_data = os.path.join(pp, "Default")
        if not os.path.isdir(default_data):
            logger.warning(
                "%s: No Chromium 'Default' profile under %s — "
                "session may require manual login.",
                prefix, pp,
            )
            return SessionStatus.NEEDS_LOGIN

        return SessionStatus.VALID

    @staticmethod
    def launch(
        profile_path: str,
        platform: str = "",
        headless: bool = False,
        viewport: dict | None = None,
        user_agent: str | None = None,
        extra_args: list[str] | None = None,
    ) -> tuple[Playwright, BrowserContext, Page] | None:
        """
        Start Playwright with a persistent Chromium context.
        
        Returns (playwright, context, page) or None on failure.
        Caller owns lifecycle (must call close_session).
        
        Args:
            profile_path: Path to Chromium user data directory
            platform: Platform name for logging
            headless: Run without UI (False = visible browser for manual login)
            viewport: Browser viewport dimensions
            user_agent: Custom user agent string
            extra_args: Additional Chromium launch arguments
        """
        prefix = f"{platform.capitalize()}Session" if platform else "Session"
        
        # Resolve portable path
        profile_path = PlatformSessionManager.resolve_profile_path(
            profile_path, platform
        )

        # Health check (log only, don't block — caller decides)
        health = PlatformSessionManager.check_profile_health(
            profile_path, platform
        )
        if health == SessionStatus.MISSING_PROFILE:
            logger.warning(
                "%s: Profile directory missing. "
                "Chromium will create a fresh (logged-out) profile at: %s",
                prefix, profile_path,
            )

        vp = viewport or {"width": 1280, "height": 720}
        ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        args = [
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-features=SitePerProcess",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
        ]
        if extra_args:
            args.extend(extra_args)

        try:
            pw = sync_playwright().start()
            logger.info(
                "%s: launch_persistent headless=%s profile=%s",
                prefix, headless, profile_path,
            )
            context = pw.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=headless,
                viewport=vp,
                user_agent=ua,
                args=args,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(PLAYWRIGHT_DEFAULT_TIMEOUT_MS)
            return pw, context, page
        except Exception as e:
            logger.error(
                "%s: Failed to bootstrap playwright session: %s",
                prefix, e,
            )
            return None

    @staticmethod
    def check_session_valid(
        page: Page,
        platform: str,
        login_indicators: list[str],
        authenticated_indicators: list[str],
    ) -> str:
        """
        Determine if the current browser session is authenticated.
        
        Args:
            page: The active Playwright page
            platform: Platform name for logging
            login_indicators: Locators that indicate a login page 
                              (e.g., 'input[name="email"]')
            authenticated_indicators: Locators that indicate logged-in state 
                                       (e.g., 'div[role="navigation"]')
        
        Returns:
            SessionStatus.VALID if authenticated
            SessionStatus.NEEDS_LOGIN if login page detected
            SessionStatus.EXPIRED if ambiguous state
        """
        prefix = f"{platform.capitalize()}Session"

        # Check for authenticated indicators first
        for indicator in authenticated_indicators:
            try:
                if page.locator(indicator).count() > 0:
                    logger.info(
                        "%s: Authenticated indicator found: %s",
                        prefix, indicator,
                    )
                    return SessionStatus.VALID
            except Exception:
                continue

        # Check for login page indicators
        for indicator in login_indicators:
            try:
                if page.locator(indicator).count() > 0:
                    logger.warning(
                        "%s: Login page detected (indicator: %s). "
                        "Session is invalid — manual login required.",
                        prefix, indicator,
                    )
                    return SessionStatus.NEEDS_LOGIN
            except Exception:
                continue

        logger.warning(
            "%s: Could not determine session state — "
            "neither login nor auth indicators found.",
            prefix,
        )
        return SessionStatus.EXPIRED
