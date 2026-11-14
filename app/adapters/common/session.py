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


_CHROMIUM_VERSION: str | None = None

# Headless dùng bản Chromium đầy đủ (chế độ headless mới) — cùng binary với cửa sổ đăng nhập tay, nên plugins,
# languages, Accept-Language, window.chrome, Client Hints (sec-ch-ua) khớp phiên đăng nhập. Bản headless shell mặc
# định của Playwright gửi sec-ch-ua «HeadlessChrome», plugins 0, không có Accept-Language.
HEADLESS_CHANNEL = "chromium"


def _reduced_user_agent(version: str) -> str:
    """UA kiểu Chrome thật (UA reduction): chỉ giữ số major, ví dụ ``Chrome/145.0.0.0``."""
    major = version.split(".", 1)[0]
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )


def _chromium_version(pw: Playwright) -> str | None:
    """Phiên bản Chromium của Playwright — mở thử một lần / tiến trình rồi nhớ (trước: mỗi lần mở trình duyệt headless
    lại khởi thêm một Chromium chỉ để đọc version). Lỗi → None (dùng UA mặc định)."""
    global _CHROMIUM_VERSION
    if _CHROMIUM_VERSION is None:
        browser = None
        try:
            browser = pw.chromium.launch(channel=HEADLESS_CHANNEL)
            _CHROMIUM_VERSION = browser.version
        except Exception as exc:
            logger.warning("Session: không đọc được phiên bản Chromium: %s", exc)
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
    return _CHROMIUM_VERSION


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
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-features=SitePerProcess",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disk-cache-size=104857600",
            "--media-cache-size=52428800",
        ]
        if extra_args:
            args.extend(extra_args)

        pw = None
        context = None
        try:
            pw = sync_playwright().start()
            logger.info(
                "%s: launch_persistent headless=%s profile=%s",
                prefix, headless, profile_path,
            )
            launch_kwargs = {
                "user_data_dir": profile_path,
                "headless": headless,
                "viewport": vp,
                "args": args,
            }
            if user_agent:
                launch_kwargs["user_agent"] = user_agent
            elif headless:
                # Headless mới vẫn ghi «HeadlessChrome» trong chuỗi UA (Client Hints thì sạch) → khai UA Chrome thật.
                ver = _chromium_version(pw)
                if ver:
                    launch_kwargs["user_agent"] = _reduced_user_agent(ver)

            # Không chèn script giả navigator.webdriver / window.chrome: cờ AutomationControlled đã cho
            # webdriver=false như Chrome thật, Chromium đầy đủ có sẵn window.chrome thật (giả tay lại thành dấu vết).
            if headless:
                try:
                    context = pw.chromium.launch_persistent_context(channel=HEADLESS_CHANNEL, **launch_kwargs)
                except Exception as exc:
                    logger.warning(
                        "%s: không mở được Chromium đầy đủ ở chế độ headless (%s) — dùng headless shell.",
                        prefix, exc,
                    )
                    context = pw.chromium.launch_persistent_context(**launch_kwargs)
            else:
                context = pw.chromium.launch_persistent_context(**launch_kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(PLAYWRIGHT_DEFAULT_TIMEOUT_MS)
            return pw, context, page
        except Exception as e:
            logger.error(
                "%s: Failed to bootstrap playwright session: %s",
                prefix, e,
            )
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if pw is not None:
                try:
                    pw.stop()
                except Exception:
                    pass
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


SessionManager = PlatformSessionManager
PlatformSessionManager.launch_persistent = PlatformSessionManager.launch


