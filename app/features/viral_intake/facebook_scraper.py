from __future__ import annotations

import asyncio
import concurrent.futures
import fcntl
import logging
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright

from app.config import PROFILES_DIR

logger = logging.getLogger(__name__)

PROFILE_DIR = str(Path(PROFILES_DIR) / "facebook_scanner")
LOCK_FILE = str(Path(PROFILES_DIR) / "facebook_scanner.lock")


def normalize_facebook_reels_url(url: str) -> str:
    """Normalize Facebook Reel or video link to canonical https://www.facebook.com/reel/<id>."""
    raw = (url or "").strip()
    if not raw:
        return ""

    # Check for /reel/<id>
    reel_match = re.search(r"/reel/([^/?&#]+)", raw)
    if reel_match:
        reel_id = reel_match.group(1).strip()
        if reel_id:
            return f"https://www.facebook.com/reel/{reel_id}"

    # Check for /videos/<id>
    videos_match = re.search(r"/videos/([0-9]+)", raw)
    if videos_match:
        video_id = videos_match.group(1).strip()
        if video_id:
            return f"https://www.facebook.com/reel/{video_id}"

    # Check for watch/?v=<id>
    watch_match = re.search(r"[?&]v=([0-9]+)", raw)
    if watch_match:
        v_id = watch_match.group(1).strip()
        if v_id:
            return f"https://www.facebook.com/reel/{v_id}"

    # Strip query params and hash
    parts = urlsplit(raw)
    clean_path = parts.path.rstrip("/")
    if clean_path:
        return f"https://www.facebook.com{clean_path}"
    return raw


def _clean_stale_singleton_lock(profile_dir: str) -> None:
    """Remove stale Chromium SingletonLock / SingletonSocket if process holding it died."""
    for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        lock_path = os.path.join(profile_dir, lock_name)
        try:
            if os.path.islink(lock_path) or os.path.exists(lock_path):
                os.unlink(lock_path)
                logger.info("[FB_SCANNER] Cleaned stale lock: %s", lock_path)
        except Exception as exc:
            logger.debug("[FB_SCANNER] Error removing stale lock %s: %s", lock_path, exc)


async def _async_scrape_reels(page_url: str, max_videos: int = 30) -> list[str]:
    """Scrape reel URLs from a Facebook page reels tab using Playwright persistent context."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    lock_dir = os.path.dirname(LOCK_FILE)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)

    lock_fd = None
    lock_acquired = False
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o666)
        # Acquire non-blocking flock to prevent multiple processes from colliding on the same profile
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_acquired = True
        _clean_stale_singleton_lock(PROFILE_DIR)
    except (BlockingIOError, OSError, PermissionError) as exc:
        logger.warning(
            "Facebook scraper process lock currently held by another worker. Aborting scrape to avoid profile collision."
        )
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception:
                pass
            lock_fd = None
        return []
    except Exception as exc:
        logger.warning("[FB_SCANNER] Unexpected error acquiring profile lock: %s", exc)
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except Exception:
                pass
            lock_fd = None
        return []

    reels: list[str] = []
    seen: set[str] = set()

    try:
        async with async_playwright() as pw:
            ctx = None
            page = None
            try:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=PROFILE_DIR,
                    headless=True,
                    viewport={"width": 1280, "height": 900},
                    locale="vi-VN",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-infobars",
                        "--disk-cache-size=104857600",
                        "--media-cache-size=52428800",
                    ],
                )
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                # Navigation with timeout handling
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as nav_exc:
                    logger.warning("[FB_SCANNER] Navigation timeout or warning on %s: %s", page_url, nav_exc)

                await page.wait_for_timeout(2000)

                # Modal / cookie / login overlay dismissal
                modal_selectors = [
                    'button[data-cookiebanner="accept_button"]',
                    'button[data-cookiebanner="accept_only_essential_button"]',
                    'div[role="dialog"] button:has-text("Cho phép")',
                    'div[role="dialog"] button:has-text("Accept")',
                    'div[aria-label="Close"]',
                    'div[aria-label="Đóng"]',
                    '[aria-label="Đóng"]',
                    '[aria-label="Close"]',
                    'div[role="dialog"] [aria-label*="Đóng"]',
                    'div[role="dialog"] [aria-label*="Close"]',
                ]
                for sel in modal_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

                # Dynamic scrolling loop
                scroll_count = max(4, min(int(max_videos / 5) + 2, 10))
                stagnant_count = 0

                for _ in range(scroll_count):
                    raw_links = await page.evaluate("""() => {
                        const list = [];
                        for (let a of document.querySelectorAll('a')) {
                            if (a.href) {
                                if (a.href.includes('/reel/') || a.href.includes('/videos/')) {
                                    list.push(a.href);
                                }
                            }
                        }
                        return Array.from(new Set(list));
                    }""")

                    prev_len = len(seen)
                    for raw in raw_links:
                        canon = normalize_facebook_reels_url(raw)
                        if canon and canon not in seen:
                            seen.add(canon)
                            reels.append(canon)
                            if len(reels) >= max_videos:
                                break

                    if len(reels) >= max_videos:
                        break

                    if len(seen) == prev_len:
                        stagnant_count += 1
                        if stagnant_count >= 3:
                            break
                    else:
                        stagnant_count = 0

                    await page.mouse.wheel(0, 1500)
                    await page.wait_for_timeout(1500)

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception as p_err:
                        logger.debug("[FB_SCANNER] Error closing page: %s", p_err)
                if ctx:
                    try:
                        await ctx.close()
                    except Exception as c_err:
                        logger.debug("[FB_SCANNER] Error closing context: %s", c_err)
    except Exception as exc:
        logger.error("[FB_SCANNER] Error in _async_scrape_reels: %s", exc)
    finally:
        if lock_acquired and lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(lock_fd)
            except Exception:
                pass

    return reels


def scan_facebook_reels(page_url: str, max_videos: int = 30) -> list[str]:
    """Public interface for scanning Facebook Reels from a source page. Safe across event loops."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an active event loop -> offload to thread
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(asyncio.run, _async_scrape_reels(page_url, max_videos=max_videos))
                return future.result(timeout=120)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        else:
            return asyncio.run(_async_scrape_reels(page_url, max_videos=max_videos))
    except Exception as exc:
        logger.error("[FB_SCANNER] scan_facebook_reels error: %s", exc)
        return []
