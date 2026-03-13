"""
Personal-profile visual test for the dual-entry Reels strategy.

Flow:
1. Try direct Reels entry on the personal profile.
2. Fall back to the generic composer if direct entry is unavailable.
3. Upload media, walk through Next steps, and stop before posting.
"""
import logging
from pathlib import Path

from app.adapters.facebook.adapter import FacebookAdapter


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROFILE_DIR = "/home/vu/toolsauto/content/profiles/facebook_4"
VIDEO_FILE = "/home/vu/toolsauto/content/reup/tiktok/viral_30_7604097945885084936_reup.mp4"
OUT_DIR = Path("/tmp/personal_reels_flow")


def ss(page, name: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    logger.info("Screenshot: %s", path)


def test():
    adapter = FacebookAdapter()
    if not adapter.open_session(PROFILE_DIR):
        logger.error("Could not open browser session.")
        return

    try:
        page = adapter.page
        assert page is not None

        logger.info("Personal dual-entry test: loading Facebook home...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        adapter._neutralize_overlays()
        ss(page, "01_home_loaded")

        entrypoint_used = adapter._open_personal_reels_entry()
        logger.info("Personal dual-entry test: entrypoint=%s", entrypoint_used)
        ss(page, "02_entry_attempt")
        if not entrypoint_used:
            surface = adapter._find_active_publish_surface()
            adapter._log_surface_inventory(surface, "personal_test_entry_missing")
            return

        surface = adapter._find_active_publish_surface()
        adapter._log_surface_inventory(surface, "personal_test_entry_opened")

        file_input = adapter._select_file_input(surface, VIDEO_FILE)
        if not file_input:
            logger.error("No file input found for personal flow.")
            ss(page, "03_no_file_input")
            return

        file_input.set_input_files(VIDEO_FILE)
        page.wait_for_timeout(8000)
        ss(page, "03_video_uploaded")

        surface = adapter._find_active_publish_surface()
        caption_typed = False
        if entrypoint_used == "direct_reels":
            caption_typed = adapter._type_caption_in_surface(surface, "Test personal reels flow #v9999")
        logger.info("Caption typed before Next: %s", caption_typed)

        for step in range(6):
            surface = adapter._find_active_publish_surface()
            post_button = adapter._find_post_button(surface)
            if post_button:
                logger.info("Post button visible at step %d", step)
                ss(page, f"04_post_visible_{step}")
                break

            next_button = adapter._find_next_button(surface)
            if not next_button:
                logger.info("No more Next/Tiep buttons at step %d", step)
                ss(page, f"04_no_next_{step}")
                break

            logger.info("Clicking Next/Tiep step %d", step + 1)
            adapter._click_locator(next_button, f"personal test next button step {step + 1}", timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, f"04_after_next_{step + 1}")

            if entrypoint_used == "direct_reels" and not caption_typed:
                surface = adapter._find_active_publish_surface()
                caption_typed = adapter._type_caption_in_surface(surface, "Test personal reels flow #v9999")

        surface = adapter._find_active_publish_surface()
        if not caption_typed:
            caption_typed = adapter._type_caption_in_surface(surface, "Test personal reels flow #v9999")
        adapter._log_surface_inventory(surface, "personal_test_final_surface")
        ss(page, "05_final_surface")

        logger.info("Final post button found: %s", bool(adapter._find_post_button(surface)))
        logger.info("Personal dual-entry test finished. Not posting.")

    finally:
        adapter.close_session()


if __name__ == "__main__":
    test()
