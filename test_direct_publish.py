"""
Direct publish test — bypasses DB jobs entirely.
Tests the full Facebook Reels publish flow step-by-step with detailed logging
and screenshots at every critical stage.

Usage:
    python test_direct_publish.py

Uses video: /home/vu/toolsauto/content/viral_38_7597296859249511687_reup.mp4
Uses account: Nguyen Ngoc Vi (profile facebook_4)
"""
import sys
import os
import time
import logging
import random
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [TEST_PUBLISH] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUT = Path("/tmp/test_direct_publish")
OUT.mkdir(parents=True, exist_ok=True)

VIDEO_PATH = "/home/vu/toolsauto/content/viral_38_7597296859249511687_reup.mp4"
PROFILE_PATH = "/home/vu/toolsauto/content/profiles/facebook_4"
TEST_CAPTION = "Test post debug 🔥 #testing"
ACCOUNT_NAME = "Nguyen Ngoc Vi"


def ss(page, name: str):
    """Save screenshot with timestamp."""
    path = OUT / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        logger.info("📸 Screenshot: %s", path)
    except Exception as e:
        logger.warning("📸 Screenshot failed: %s", e)


def save_html(page, name: str):
    """Save page HTML for debugging."""
    path = OUT / f"{name}.html"
    try:
        path.write_text(page.content(), encoding='utf-8')
        logger.info("📄 HTML saved: %s", path)
    except Exception as e:
        logger.warning("📄 HTML save failed: %s", e)


def log_visible_buttons(page, surface, label: str):
    """Log all visible buttons in the current surface for debugging."""
    try:
        buttons = surface.locator("button, div[role='button'], a[role='button']")
        visible = []
        for idx in range(min(buttons.count(), 30)):
            btn = buttons.nth(idx)
            try:
                if btn.is_visible():
                    text = (btn.get_attribute("aria-label") or btn.inner_text() or "").strip()
                    if text and len(text) < 100:
                        visible.append(text)
            except Exception:
                pass
        logger.info("[%s] Visible buttons (%d): %s", label, len(visible), visible[:15])
    except Exception as e:
        logger.warning("[%s] Failed to log buttons: %s", label, e)


def log_file_inputs(page, surface, label: str):
    """Log all file inputs."""
    try:
        inputs = surface.locator("input[type='file']")
        count = inputs.count()
        logger.info("[%s] File inputs found: %d", label, count)
        for i in range(count):
            inp = inputs.nth(i)
            accept = inp.get_attribute("accept") or "(no accept)"
            logger.info("  [%d] accept=%s", i, accept[:80])
    except Exception as e:
        logger.warning("[%s] Failed to log file inputs: %s", label, e)


def log_textboxes(page, surface, label: str):
    """Log all textboxes."""
    try:
        boxes = surface.locator('div[contenteditable="true"], div[role="textbox"], textarea')
        visible = []
        for idx in range(min(boxes.count(), 10)):
            box = boxes.nth(idx)
            try:
                if box.is_visible():
                    placeholder = (
                        box.get_attribute("aria-placeholder") or
                        box.get_attribute("placeholder") or
                        "(no placeholder)"
                    ).strip()
                    visible.append(placeholder)
            except Exception:
                pass
        logger.info("[%s] Visible textboxes (%d): %s", label, len(visible), visible)
    except Exception as e:
        logger.warning("[%s] Failed to log textboxes: %s", label, e)


def full_inventory(page, surface, label: str):
    """Full inventory of the current surface."""
    log_visible_buttons(page, surface, label)
    log_file_inputs(page, surface, label)
    log_textboxes(page, surface, label)


def main():
    # Validate video exists
    if not os.path.exists(VIDEO_PATH):
        logger.error("❌ Video not found: %s", VIDEO_PATH)
        return 1

    logger.info("=" * 60)
    logger.info("  DIRECT PUBLISH TEST")
    logger.info("  Video:   %s", VIDEO_PATH)
    logger.info("  Profile: %s", PROFILE_PATH)
    logger.info("  Caption: %s", TEST_CAPTION)
    logger.info("  Output:  %s", OUT)
    logger.info("=" * 60)

    from app.adapters.facebook.adapter import FacebookAdapter

    adapter = FacebookAdapter()

    if not adapter.open_session(PROFILE_PATH):
        logger.error("❌ Failed to open browser session!")
        return 1

    page = adapter.page
    assert page is not None

    try:
        # ━━━ STEP 1: Navigate to Facebook ━━━
        logger.info("━━━ STEP 1: Navigate to Facebook ━━━")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        ss(page, "01_facebook_loaded")

        # Check login status
        login_btn = page.locator('button[name="login"]').count() > 0
        email_in = page.locator('input[name="email"]').count() > 0
        nav_present = page.locator('div[role="navigation"]').count() > 0
        logger.info("  login_btn=%s, email_in=%s, nav_present=%s", login_btn, email_in, nav_present)

        if (login_btn and email_in) or not nav_present:
            logger.error("❌ Account is NOT logged in! Cannot continue.")
            ss(page, "01_NOT_LOGGED_IN")
            return 1
        logger.info("  ✅ Logged in OK")

        # ━━━ STEP 2: Switch to Personal Profile ━━━
        logger.info("━━━ STEP 2: Switch to Personal Profile (%s) ━━━", ACCOUNT_NAME)
        adapter._switch_to_personal_profile(ACCOUNT_NAME)
        page.wait_for_timeout(3000)
        ss(page, "02_after_profile_switch")

        # ━━━ STEP 3: Pre-scan existing reels ━━━
        logger.info("━━━ STEP 3: Pre-scan existing reels ━━━")
        reels_url = "https://www.facebook.com/me/reels_tab"
        page.goto(reels_url, wait_until="commit", timeout=15000)
        page.wait_for_timeout(3000)

        pre_existing = []
        for link in page.locator('a').all():
            try:
                href = link.get_attribute("href")
                if href and "/reel/" in href and len(href) > 20:
                    clean = href.split("?")[0]
                    full = clean if clean.startswith("http") else "https://www.facebook.com" + clean
                    if full not in pre_existing:
                        pre_existing.append(full)
            except Exception:
                pass
        logger.info("  Pre-existing reels: %d", len(pre_existing))
        for r in pre_existing[:5]:
            logger.info("    • %s", r)
        ss(page, "03_pre_scan_reels")

        # ━━━ STEP 4: Navigate back to feed ━━━
        logger.info("━━━ STEP 4: Navigate back to feed ━━━")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # Ensure personal profile context
        adapter._switch_to_personal_profile(ACCOUNT_NAME)
        page.wait_for_timeout(3000)
        ss(page, "04_back_on_feed")

        # ━━━ STEP 5: Neutralize overlays ━━━
        logger.info("━━━ STEP 5: Neutralize overlays ━━━")
        adapter._neutralize_overlays()
        page.wait_for_timeout(1000)

        # ━━━ STEP 6: Try to open Reels composer ━━━
        logger.info("━━━ STEP 6: Open Reels composer ━━━")
        entrypoint = adapter._open_personal_reels_entry()
        logger.info("  Entrypoint result: %s", entrypoint or "NOT FOUND ❌")
        ss(page, "06_after_entry_attempt")

        if not entrypoint:
            logger.error("❌ Could not find Reels entry point!")
            surface = adapter._find_active_publish_surface()
            full_inventory(page, surface, "ENTRY_MISSING")
            save_html(page, "06_entry_missing")
            return 1
        logger.info("  ✅ Composer opened via: %s", entrypoint)

        # ━━━ STEP 7: Upload video ━━━
        logger.info("━━━ STEP 7: Upload video ━━━")
        surface = adapter._find_active_publish_surface()
        full_inventory(page, surface, "PRE_UPLOAD")

        file_input = adapter._select_file_input(surface, VIDEO_PATH)
        if not file_input:
            logger.error("❌ No file input found in surface!")
            save_html(page, "07_no_file_input")
            return 1

        logger.info("  Setting file input...")
        file_input.set_input_files(VIDEO_PATH)
        logger.info("  ⏳ Waiting for video preview to load (8s)...")
        page.wait_for_timeout(8000)
        ss(page, "07_video_uploaded")

        surface = adapter._find_active_publish_surface()
        full_inventory(page, surface, "POST_UPLOAD")

        # ━━━ STEP 8: Type caption (pre-Next) ━━━
        logger.info("━━━ STEP 8: Type caption (pre-Next attempt) ━━━")
        caption_typed = adapter._type_caption_in_surface(surface, TEST_CAPTION)
        logger.info("  Caption typed pre-Next: %s", caption_typed)

        # ━━━ STEP 9: Navigate through Next steps ━━━
        logger.info("━━━ STEP 9: Navigate through Next/Tiếp steps ━━━")
        for step in range(6):
            surface = adapter._find_active_publish_surface()
            post_btn = adapter._find_post_button(surface)
            if post_btn:
                logger.info("  ✅ Post button found at step %d", step)
                break

            next_btn = adapter._find_next_button(surface)
            if not next_btn:
                logger.info("  No more Next buttons at step %d", step)
                break

            logger.info("  Clicking Next at step %d...", step + 1)
            adapter._click_locator(next_btn, f"next step {step+1}", timeout=5000)
            page.wait_for_timeout(3000)
            ss(page, f"09_after_next_{step+1}")

            # Try caption again after Next
            if not caption_typed:
                surface = adapter._find_active_publish_surface()
                caption_typed = adapter._type_caption_in_surface(surface, TEST_CAPTION)
                if caption_typed:
                    logger.info("  ✅ Caption typed after Next step %d", step + 1)

        # ━━━ STEP 10: Final caption attempt ━━━
        surface = adapter._find_active_publish_surface()
        if not caption_typed:
            logger.info("━━━ STEP 10: Final caption attempt ━━━")
            caption_typed = adapter._type_caption_in_surface(surface, TEST_CAPTION)
            logger.info("  Caption typed final: %s", caption_typed)

        # ━━━ STEP 11: Pre-Post inventory ━━━
        logger.info("━━━ STEP 11: Pre-Post inventory ━━━")
        full_inventory(page, surface, "PRE_POST")
        
        post_btn = adapter._find_post_button(surface)
        ss(page, "11_pre_post")

        if not post_btn:
            logger.error("❌ Post button NOT FOUND at final stage!")
            save_html(page, "11_no_post_button")
            return 1

        logger.info("  ✅ Post button FOUND")

        # ━━━ STEP 12: Wait for Post button to be enabled ━━━ 
        logger.info("━━━ STEP 12: Wait for Post button to be enabled ━━━")
        try:
            post_handle = post_btn.element_handle()
            if post_handle:
                page.wait_for_function(
                    'el => el.getAttribute("aria-disabled") !== "true"',
                    arg=post_handle,
                    timeout=120000,
                )
                logger.info("  ✅ Post button is enabled")
        except Exception as e:
            logger.warning("  ⚠️ Wait for button enabled failed: %s", e)

        # ━━━ STEP 13: Click Post ━━━
        logger.info("━━━ STEP 13: CLICKING POST BUTTON ━━━")
        page.wait_for_timeout(random.randint(1000, 3000))  # Human hesitation
        
        clicked = adapter._click_locator(post_btn, "POST button", timeout=10000)
        logger.info("  Click result: %s", clicked)
        page.wait_for_timeout(3000)
        ss(page, "13_post_clicked")

        if not clicked:
            logger.error("❌ Failed to click Post button!")
            return 1

        # ━━━ STEP 14: Wait for submission ━━━
        logger.info("━━━ STEP 14: Waiting for post submission ━━━")
        submission_result = adapter._wait_for_post_submission()
        logger.info("  Submission result: %s", submission_result)
        ss(page, "14_after_submission")

        if submission_result == "error":
            logger.error("❌ Facebook showed an error after posting!")
            save_html(page, "14_submission_error")
            return 1

        # ━━━ STEP 15: Verify on profile ━━━
        logger.info("━━━ STEP 15: Verify post on profile (Reels tab) ━━━")
        page.wait_for_timeout(5000)
        page.goto(reels_url, wait_until="commit", timeout=15000)
        page.wait_for_timeout(4000)
        ss(page, "15_reels_tab_after_post")

        post_existing = []
        for link in page.locator('a').all():
            try:
                href = link.get_attribute("href")
                if href and "/reel/" in href and len(href) > 20:
                    clean = href.split("?")[0]
                    full = clean if clean.startswith("http") else "https://www.facebook.com" + clean
                    if full not in post_existing:
                        post_existing.append(full)
            except Exception:
                pass

        new_reels = [r for r in post_existing if r not in pre_existing]

        logger.info("=" * 60)
        logger.info("  RESULT SUMMARY")
        logger.info("  Pre-existing reels:  %d", len(pre_existing))
        logger.info("  Post-publish reels:  %d", len(post_existing))
        logger.info("  NEW reels detected:  %d", len(new_reels))
        logger.info("  Caption typed:       %s", caption_typed)
        logger.info("  Post clicked:        %s", clicked)
        logger.info("  Submission result:   %s", submission_result)
        for r in new_reels:
            logger.info("  🆕 %s", r)
        logger.info("=" * 60)

        if new_reels:
            logger.info("  ✅✅✅ PASS — New reel detected: %s", new_reels[0])
        else:
            logger.warning("  ❌❌❌ FAIL — No new reel found after posting!")
            logger.warning("  Check screenshots in: %s", OUT)

        logger.info("  All screenshots: %s", OUT)
        return 0 if new_reels else 1

    except Exception as e:
        logger.exception("❌ UNHANDLED EXCEPTION: %s", e)
        try:
            ss(page, "CRASH")
            save_html(page, "CRASH")
        except Exception:
            pass
        return 1

    finally:
        logger.info("Closing browser session...")
        adapter.close_session()
        logger.info("Done.")


if __name__ == "__main__":
    raise SystemExit(main())
