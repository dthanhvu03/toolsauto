"""
Playwright persistent context bootstrap for Facebook (isolated Chromium profile).
Extracted from FacebookAdapter for reuse and smaller adapter surface.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from app.config import (
    FACEBOOK_PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_DEFAULT_TIMEOUT_MS,
    PROFILES_DIR,
)

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

logger = logging.getLogger(__name__)


class FacebookSessionManager:
    """Launch and wire a Chromium persistent context with RAM-oriented flags."""

    @staticmethod
    def _resolve_portable_path(profile_path: str) -> str:
        """
        Ensures profile_path is valid even if it was transferred from a different 
        environment (different BASE_DIR). 
        If absolute path doesn't exist, it tries to rebase it relative to PROFILES_DIR.
        """
        if not profile_path:
            return profile_path
            
        p = Path(profile_path)
        
        # 1. If it exists as is, return it
        if p.exists() and p.is_dir():
            return str(p.absolute())
            
        # 2. If it's absolute but missing (e.g. from local), try to find its basename 
        # in the current PROFILES_DIR
        if p.is_absolute():
            rebased = PROFILES_DIR / p.name
            if rebased.exists() and rebased.is_dir():
                logger.info("FacebookSessionManager: Path rebased from %s -> %s", profile_path, rebased)
                return str(rebased.absolute())
                
        # 3. Fallback to whatever was given
        return profile_path

    @staticmethod
    def log_profile_health(profile_path: str | None) -> None:
        if not profile_path:
            return
        pp = profile_path.strip()
        if not os.path.isdir(pp):
            logger.warning(
                "FacebookSessionManager: profile_path is missing or not a directory — "
                "Chromium may create an empty profile (login wall): %s",
                pp,
            )
            return
        default_data = os.path.join(pp, "Default")
        if not os.path.isdir(default_data):
            logger.warning(
                "FacebookSessionManager: No Chromium 'Default' profile under %s — "
                "session may not be logged in (wrong folder or fresh copy).",
                pp,
            )

    @staticmethod
    def launch_persistent(profile_path: str) -> tuple[Playwright, BrowserContext, Page] | None:
        """
        Start sync Playwright + persistent Chromium. Returns (playwright, context, page) or None on failure.
        Caller owns lifecycle (stop playwright after context.close()).
        """
        # Portable Path Resolution
        profile_path = FacebookSessionManager._resolve_portable_path(profile_path)

        FacebookSessionManager.log_profile_health(profile_path)
        pw = None
        context = None
        try:
            pw = sync_playwright().start()
            headless = FACEBOOK_PLAYWRIGHT_HEADLESS
            logger.info(
                "FacebookSessionManager: launch_persistent headless=%s (FACEBOOK_PLAYWRIGHT_HEADLESS)",
                headless,
            )
            ua = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                if sys.platform.startswith("linux")
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            context = pw.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=headless,
                viewport={"width": 1280, "height": 720},
                user_agent=ua,
                args=[
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
                ],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(PLAYWRIGHT_DEFAULT_TIMEOUT_MS)
            try:
                page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            except Exception:
                pass
            return pw, context, page
        except Exception as e:
            logger.error("FacebookSessionManager: Failed to bootstrap playwright session: %s", e)
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
