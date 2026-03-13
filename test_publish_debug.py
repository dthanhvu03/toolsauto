"""
Diagnostic test for Facebook publish verification.

Runs the full publish flow for a specific job, captures screenshots at every
stage, and verifies whether the post actually appears on the profile.

Usage:
    python test_publish_debug.py <job_id>
    python test_publish_debug.py <job_id> --headless

Screenshots are saved to /tmp/publish_debug/
"""
import sys
import os
import time
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import Job, Account
from app.adapters.facebook.adapter import FacebookAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [PUBLISH_DEBUG] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUT = Path("/tmp/publish_debug")

def ss(page, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    logger.info("📸 %s", path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Debug Facebook publish flow for a specific job")
    parser.add_argument("job_id", type=int, help="Job ID to test")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--dry-run", action="store_true", help="Stop before clicking Post (debug only)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == args.job_id).first()
        if not job:
            logger.error("Job %d not found", args.job_id)
            return 1

        acc = db.query(Account).filter(Account.id == job.account_id).first()
        if not acc:
            logger.error("Account %d not found", job.account_id)
            return 1

        logger.info("═══════════════════════════════════════════")
        logger.info("  Job ID:     %d", job.id)
        logger.info("  Account:    %s", acc.name)
        logger.info("  Platform:   %s", job.platform)
        logger.info("  Target:     %s", job.target_page or "Personal Profile")
        logger.info("  Media:      %s", job.media_path)
        logger.info("  Caption:    %s", (job.caption or "")[:80])
        logger.info("  Status:     %s", job.status)
        logger.info("═══════════════════════════════════════════")

        if not job.media_path or not os.path.exists(job.media_path):
            logger.error("Media file not found: %s", job.media_path)
            return 1

        adapter = FacebookAdapter()
        if not adapter.open_session(acc.profile_path):
            logger.error("Failed to open browser session")
            return 1

        try:
            page = adapter.page
            assert page is not None

            # Step 1: Navigate
            target = job.target_page or "https://www.facebook.com/"
            if not target.startswith("http"):
                target = "https://" + target
            logger.info("Step 1: Navigating to %s", target)
            page.goto(target, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            # Switch back to personal profile if needed
            if not job.target_page:
                logger.info("Step 1.5: Ensuring context is Personal Profile (%s)...", acc.name)
                adapter._switch_to_personal_profile(acc.name)
                page.wait_for_timeout(3000)
                
            ss(page, "01_loaded")

            # Step 2: Pre-scan existing reels
            logger.info("Step 2: Pre-scanning existing reels...")
            if job.target_page:
                reels_url = job.target_page.rstrip('/') + '/reels_tab'
            else:
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
            logger.info("  Found %d existing reels", len(pre_existing))
            for r in pre_existing[:5]:
                logger.info("    • %s", r)
            ss(page, "02_pre_scan_reels")

            # Step 3: Navigate back, open composer
            if job.target_page:
                page.goto(job.target_page, wait_until="domcontentloaded")
            else:
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # Ensure we are on the personal profile (if we navigated away and it got lost)
            if not job.target_page:
                adapter._switch_to_personal_profile(acc.name)
                page.wait_for_timeout(3000)

            adapter._neutralize_overlays()
            logger.info("Step 3: Opening composer...")

            if job.target_page:
                entrypoint = adapter._open_page_reels_entry()
            else:
                entrypoint = adapter._open_personal_reels_entry()

            logger.info("  Entrypoint: %s", entrypoint or "NOT FOUND")
            ss(page, "03_entry_attempt")

            if not entrypoint:
                logger.error("❌ Could not find Reels entry. Aborting.")
                surface = adapter._find_active_publish_surface()
                adapter._log_surface_inventory(surface, "debug_entry_missing")
                return 1

            # Step 4: Upload video
            logger.info("Step 4: Uploading video...")
            surface = adapter._find_active_publish_surface()
            file_input = adapter._select_file_input(surface, job.media_path)
            if not file_input:
                logger.error("❌ No file input found")
                return 1

            file_input.set_input_files(job.media_path)
            page.wait_for_timeout(8000)
            ss(page, "04_video_uploaded")

            # Step 5: Type caption
            logger.info("Step 5: Typing caption...")
            surface = adapter._find_active_publish_surface()
            caption_typed = adapter._type_caption_in_surface(surface, job.caption or "")
            logger.info("  Caption typed: %s", caption_typed)

            # Step 6: Navigate through Next steps
            logger.info("Step 6: Walking through Next/Tiếp steps...")
            for step in range(6):
                surface = adapter._find_active_publish_surface()
                post_btn = adapter._find_post_button(surface)
                if post_btn:
                    logger.info("  Post button found at step %d", step)
                    break

                next_btn = adapter._find_next_button(surface)
                if not next_btn:
                    logger.info("  No more Next buttons at step %d", step)
                    break

                adapter._click_locator(next_btn, f"next step {step+1}", timeout=5000)
                page.wait_for_timeout(3000)
                ss(page, f"05_after_next_{step+1}")

                if not caption_typed:
                    surface = adapter._find_active_publish_surface()
                    caption_typed = adapter._type_caption_in_surface(surface, job.caption or "")

            surface = adapter._find_active_publish_surface()
            if not caption_typed:
                caption_typed = adapter._type_caption_in_surface(surface, job.caption or "")

            post_btn = adapter._find_post_button(surface)
            ss(page, "06_pre_post")

            logger.info("═══════════════════════════════════════════")
            logger.info("  Caption typed:   %s", caption_typed)
            logger.info("  Post button:     %s", "FOUND ✅" if post_btn else "NOT FOUND ❌")
            logger.info("═══════════════════════════════════════════")

            if args.dry_run:
                logger.info("🛑 DRY RUN mode — stopping before clicking Post.")
                return 0

            if not post_btn:
                logger.error("❌ Post button not found. Cannot continue.")
                return 1

            # Step 7: Click Post
            logger.info("Step 7: CLICKING POST BUTTON...")
            adapter._click_locator(post_btn, "post button", timeout=10000)
            ss(page, "07_post_clicked")

            # Step 8: Wait for submission
            logger.info("Step 8: Waiting for submission...")
            result = adapter._wait_for_post_submission()
            logger.info("  Submission result: %s", result)
            ss(page, "08_after_submission")

            if result == "error":
                logger.error("❌ Facebook showed an error after posting!")
                return 1

            # Step 9: Verify on profile
            logger.info("Step 9: Verifying post on profile...")
            page.wait_for_timeout(5000)
            page.goto(reels_url, wait_until="commit", timeout=15000)
            page.wait_for_timeout(4000)
            ss(page, "09_post_reels_tab")

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
            logger.info("  Post-publish reels: %d (was %d)", len(post_existing), len(pre_existing))
            logger.info("  NEW reels found: %d", len(new_reels))
            for r in new_reels:
                logger.info("    🆕 %s", r)

            logger.info("═══════════════════════════════════════════")
            if new_reels:
                logger.info("  ✅ PASS — New reel detected: %s", new_reels[0])
            else:
                logger.warning("  ❌ FAIL — No new reel found after posting!")
                logger.warning("  This means the post did NOT appear on the profile.")
            logger.info("═══════════════════════════════════════════")
            logger.info("  Screenshots saved to: %s", OUT)

            return 0 if new_reels else 1

        finally:
            adapter.close_session()

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
