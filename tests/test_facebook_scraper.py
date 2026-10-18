from __future__ import annotations

import asyncio
import fcntl
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.viral_intake.facebook_scraper import (
    _async_scrape_reels,
    _clean_stale_singleton_lock,
    normalize_facebook_reels_url,
    scan_facebook_reels,
)


def test_normalize_facebook_reels_url():
    # Standard reel URLs
    assert normalize_facebook_reels_url("https://www.facebook.com/reel/123456789/") == "https://www.facebook.com/reel/123456789"
    assert normalize_facebook_reels_url("https://www.facebook.com/reel/123456789?mibextid=wwXIfr") == "https://www.facebook.com/reel/123456789"
    assert normalize_facebook_reels_url("https://web.facebook.com/reel/123456789") == "https://www.facebook.com/reel/123456789"

    # Videos URLs
    assert normalize_facebook_reels_url("https://www.facebook.com/somepage/videos/9876543210/") == "https://www.facebook.com/reel/9876543210"

    # Watch query param
    assert normalize_facebook_reels_url("https://www.facebook.com/watch/?v=1122334455") == "https://www.facebook.com/reel/1122334455"

    # Empty
    assert normalize_facebook_reels_url("") == ""
    assert normalize_facebook_reels_url(None) == ""


def test_clean_stale_singleton_lock(tmp_path):
    lock_path = tmp_path / "SingletonLock"
    lock_path.write_text("dummy")
    assert lock_path.exists()
    _clean_stale_singleton_lock(str(tmp_path))
    assert not lock_path.exists()


@pytest.mark.anyio
async def test_async_scrape_reels_success(tmp_path, monkeypatch):
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.LOCK_FILE", str(tmp_path / "test.lock"))

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.keyboard.press = AsyncMock()
    mock_page.mouse.wheel = AsyncMock()
    mock_page.close = AsyncMock()

    # Modal close button mock
    mock_locator = MagicMock()
    mock_btn = AsyncMock()
    mock_btn.is_visible = AsyncMock(return_value=True)
    mock_btn.click = AsyncMock()
    mock_locator.first = mock_btn
    mock_page.locator = MagicMock(return_value=mock_locator)

    # Return links from page.evaluate
    mock_page.evaluate = AsyncMock(return_value=[
        "https://www.facebook.com/reel/1000000001?ref=share",
        "https://www.facebook.com/somepage/videos/1000000002/",
        "https://www.facebook.com/reel/1000000001",  # duplicate
    ])

    mock_ctx = AsyncMock()
    mock_ctx.pages = [mock_page]
    mock_ctx.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_ctx)

    mock_pw_context_manager = MagicMock()
    mock_pw_context_manager.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_context_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("app.features.viral_intake.facebook_scraper.async_playwright", return_value=mock_pw_context_manager):
        results = await _async_scrape_reels("https://www.facebook.com/somepage/reels", max_videos=10)

    assert len(results) == 2
    assert "https://www.facebook.com/reel/1000000001" in results
    assert "https://www.facebook.com/reel/1000000002" in results
    mock_page.close.assert_awaited_once()
    mock_ctx.close.assert_awaited_once()


@pytest.mark.anyio
async def test_async_scrape_reels_navigation_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.LOCK_FILE", str(tmp_path / "test.lock"))

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=TimeoutError("Navigation timed out"))
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.keyboard.press = AsyncMock()
    mock_locator = MagicMock()
    mock_btn = AsyncMock()
    mock_btn.is_visible = AsyncMock(return_value=False)
    mock_locator.first = mock_btn
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_page.evaluate = AsyncMock(return_value=[])
    mock_page.close = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.pages = [mock_page]
    mock_ctx.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_ctx)

    mock_pw_cm = MagicMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.features.viral_intake.facebook_scraper.async_playwright", return_value=mock_pw_cm):
        results = await _async_scrape_reels("https://www.facebook.com/slowpage/reels", max_videos=5)

    assert results == []
    mock_page.close.assert_awaited_once()
    mock_ctx.close.assert_awaited_once()


def test_scan_facebook_reels_sync():
    with patch("app.features.viral_intake.facebook_scraper._async_scrape_reels", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = ["https://www.facebook.com/reel/12345"]
        res = scan_facebook_reels("https://www.facebook.com/test/reels", max_videos=5)
        assert res == ["https://www.facebook.com/reel/12345"]


@pytest.mark.anyio
async def test_scan_facebook_reels_inside_running_event_loop():
    # When called inside an already running event loop, it should use ThreadPoolExecutor
    with patch("app.features.viral_intake.facebook_scraper._async_scrape_reels", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = ["https://www.facebook.com/reel/88888"]
        res = scan_facebook_reels("https://www.facebook.com/test/reels", max_videos=5)
        assert res == ["https://www.facebook.com/reel/88888"]


def test_scan_facebook_reels_handles_exception():
    with patch("app.features.viral_intake.facebook_scraper._async_scrape_reels", side_effect=RuntimeError("Playwright crashed")):
        res = scan_facebook_reels("https://www.facebook.com/error/reels")
        assert res == []


@pytest.mark.anyio
async def test_active_lock_aborts_scrape(tmp_path, monkeypatch):
    lock_file = str(tmp_path / ".fb_scraper.lock")
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.LOCK_FILE", lock_file)
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.PROFILE_DIR", str(tmp_path / "profile"))

    # Acquire an exclusive lock on .fb_scraper.lock in a separate file descriptor
    held_fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o666)
    fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock()

    mock_pw_cm = MagicMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=None)

    try:
        with patch("app.features.viral_intake.facebook_scraper.async_playwright", return_value=mock_pw_cm) as mock_pw_init:
            # 1. Direct async invocation: must abort and return empty list without launching browser
            res_async = await _async_scrape_reels("https://www.facebook.com/activepage/reels", max_videos=10)
            assert res_async == []
            mock_pw_init.assert_not_called()
            mock_pw.chromium.launch_persistent_context.assert_not_called()

            # 2. Public synchronous wrapper: must also abort and return empty list without launching browser
            res_sync = scan_facebook_reels("https://www.facebook.com/activepage/reels", max_videos=10)
            assert res_sync == []
            mock_pw_init.assert_not_called()
            mock_pw.chromium.launch_persistent_context.assert_not_called()
    finally:
        fcntl.flock(held_fd, fcntl.LOCK_UN)
        os.close(held_fd)


def test_active_lock_aborts_scan_reels_no_loop(tmp_path, monkeypatch):
    lock_file = str(tmp_path / ".fb_scraper.lock")
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.LOCK_FILE", lock_file)
    monkeypatch.setattr("app.features.viral_intake.facebook_scraper.PROFILE_DIR", str(tmp_path / "profile"))

    held_fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o666)
    fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock()

    mock_pw_cm = MagicMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=None)

    try:
        with patch("app.features.viral_intake.facebook_scraper.async_playwright", return_value=mock_pw_cm) as mock_pw_init:
            res = scan_facebook_reels("https://www.facebook.com/activepage/reels", max_videos=10)
            assert res == []
            mock_pw_init.assert_not_called()
            mock_pw.chromium.launch_persistent_context.assert_not_called()
    finally:
        fcntl.flock(held_fd, fcntl.LOCK_UN)
        os.close(held_fd)

