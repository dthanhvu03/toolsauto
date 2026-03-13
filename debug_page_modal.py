"""
Mode-aware debug harness for Facebook publish entry flows.

- personal: try direct Reels entry first, then composer fallback
- page: open the Page Reels entry

This script never clicks the final Post button.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

from app.adapters.facebook.adapter import FacebookAdapter


DEFAULT_TARGET_PAGE = "https://www.facebook.com/profile.php?id=61564820652101"
DEFAULT_PROFILE_DIR = "/home/vu/toolsauto/content/profiles/facebook_4"
DEFAULT_VIDEO_FILE = "/tmp/test_reels.mp4"
DEFAULT_OUTPUT_DIR = "/tmp/debug_modal"
DEFAULT_CAPTION = "Test debug Reels flow #v9999"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug Facebook publish entry flows without posting.")
    parser.add_argument(
        "--mode",
        choices=("personal", "page"),
        default=os.getenv("FB_DEBUG_MODE", "personal"),
        help="Which publish flow to debug.",
    )
    parser.add_argument(
        "--profile-dir",
        default=os.getenv("FB_PROFILE_DIR", DEFAULT_PROFILE_DIR),
        help="Persistent Playwright profile directory.",
    )
    parser.add_argument(
        "--target-page",
        default=os.getenv("FB_TARGET_PAGE", DEFAULT_TARGET_PAGE),
        help="Page URL used for page-mode debugging.",
    )
    parser.add_argument(
        "--video-file",
        default=os.getenv("FB_VIDEO_FILE", DEFAULT_VIDEO_FILE),
        help="Media file to upload.",
    )
    parser.add_argument(
        "--caption",
        default=os.getenv("FB_DEBUG_CAPTION", DEFAULT_CAPTION),
        help="Caption used during the debug flow.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.getenv("FB_DEBUG_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots.",
    )
    parser.add_argument(
        "--max-next",
        type=int,
        default=int(os.getenv("FB_DEBUG_MAX_NEXT", "6")),
        help="Maximum number of Next/Tiep clicks.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Launch Chromium in headless mode.",
    )
    return parser.parse_args()


def screenshot(page, out_dir: Path, name: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"[shot] {path}")


def open_debug_session(adapter: FacebookAdapter, profile_dir: str, headless: bool):
    adapter.playwright = sync_playwright().start()
    adapter.context = adapter.playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--js-flags=--lite-mode",
            "--disable-features=SitePerProcess",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
        ],
    )
    adapter.page = adapter.context.pages[0] if adapter.context.pages else adapter.context.new_page()
    adapter.page.set_default_timeout(60000)


def main() -> int:
    args = parse_args()
    adapter = FacebookAdapter()
    out_dir = Path(args.out_dir)

    try:
        open_debug_session(adapter, args.profile_dir, args.headless)
        page = adapter.page
        assert page is not None

        if args.mode == "page":
            print(f"[mode] page -> {args.target_page}")
            page.goto(args.target_page, wait_until="domcontentloaded")
        else:
            print("[mode] personal -> https://www.facebook.com/")
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, out_dir, "01_loaded")

        adapter._neutralize_overlays()

        if args.mode == "page":
            entrypoint_used = adapter._open_page_reels_entry()
        else:
            entrypoint_used = adapter._open_personal_reels_entry()

        print(f"[entrypoint] {entrypoint_used or 'not_found'}")
        screenshot(page, out_dir, "02_entry_attempt")

        if not entrypoint_used:
            surface = adapter._find_active_publish_surface()
            adapter._log_surface_inventory(surface, "debug_entry_missing")
            return 1

        surface = adapter._find_active_publish_surface()
        adapter._log_surface_inventory(surface, "debug_entry_opened")

        file_input = adapter._select_file_input(surface, args.video_file)
        if not file_input:
            print("[error] no file input found in active publish surface")
            screenshot(page, out_dir, "03_no_file_input")
            adapter._log_surface_inventory(surface, "debug_no_file_input")
            return 1

        file_input.set_input_files(args.video_file)
        page.wait_for_timeout(8000)
        screenshot(page, out_dir, "03_video_uploaded")

        surface = adapter._find_active_publish_surface()
        adapter._log_surface_inventory(surface, "debug_after_upload")

        caption_typed = False
        pre_next_caption = args.mode == "page" or entrypoint_used == "direct_reels"
        if pre_next_caption:
            caption_typed = adapter._type_caption_in_surface(surface, args.caption)

        for step in range(args.max_next):
            surface = adapter._find_active_publish_surface()
            post_button = adapter._find_post_button(surface)
            if post_button:
                print(f"[publish] post button visible at step {step}")
                screenshot(page, out_dir, f"04_post_visible_step_{step}")
                break

            next_button = adapter._find_next_button(surface)
            if not next_button:
                print(f"[publish] no next button at step {step}")
                screenshot(page, out_dir, f"04_no_next_step_{step}")
                break

            print(f"[publish] clicking next at step {step + 1}")
            adapter._click_locator(next_button, f"debug next button step {step + 1}", timeout=5000)
            page.wait_for_timeout(3000)
            screenshot(page, out_dir, f"04_after_next_{step + 1}")

            if pre_next_caption and not caption_typed:
                surface = adapter._find_active_publish_surface()
                caption_typed = adapter._type_caption_in_surface(surface, args.caption)

        surface = adapter._find_active_publish_surface()
        if not caption_typed:
            caption_typed = adapter._type_caption_in_surface(surface, args.caption)

        adapter._log_surface_inventory(surface, "debug_final_surface")
        screenshot(page, out_dir, "05_final_surface")

        post_button = adapter._find_post_button(surface)
        print(f"[caption] typed={caption_typed}")
        print(f"[publish] final post button found={bool(post_button)}")
        print("[done] debug flow completed without posting")
        return 0

    finally:
        adapter.close_session()


if __name__ == "__main__":
    raise SystemExit(main())
