"""
Test: Switch to Dancer sexy context, then open composer and attach video.
Goal: Verify that after switching, the composer posts AS the Page.
Screenshot at every step.
"""
import os, time, logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

OUT = "/tmp/switch_post_test"
os.makedirs(OUT, exist_ok=True)

def ss(page, name):
    path = f"{OUT}/{name}.png"
    page.screenshot(path=path, full_page=False)
    logger.info(f"📸 {path}")

def test():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(10000)

        target = "https://www.facebook.com/profile.php?id=61564820652101"
        
        # ─── Step 1: Go to Page ───
        logger.info("Step 1: Navigating to Page...")
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        ss(page, "01_page_loaded")
        
        # ─── Step 2: Open avatar menu ───
        logger.info("Step 2: Opening profile menu...")
        top_imgs = page.locator('div[role="banner"] image, div[role="banner"] img').all()
        if not top_imgs:
            logger.error("❌ No images found in banner")
            return
        avatar_btn = top_imgs[-1]
        avatar_btn.click()
        page.wait_for_timeout(2000)
        ss(page, "02_menu_open")
        
        # ─── Step 3: Check if already on Dancer sexy ───
        # The first item in the dropdown should be the active profile
        # If it has a checkmark, we're already switched
        logger.info("Step 3: Checking current active profile...")
        
        # Find the dropdown menu items - look for Dancer sexy directly
        # In the menu, 'Dancer sexy' appears at the top
        dancer_in_menu = page.get_by_text("Dancer sexy", exact=True).first
        if dancer_in_menu.count() > 0 and dancer_in_menu.is_visible():
            logger.info("  'Dancer sexy' visible in menu. Clicking to ensure switch...")
            dancer_in_menu.click()
            page.wait_for_timeout(3000)
            ss(page, "03_clicked_dancer")
        else:
            logger.info("  'Dancer sexy' not directly visible, trying 'Xem tất cả trang cá nhân'...")
            see_all = page.get_by_text("Xem tất cả trang cá nhân", exact=False).first
            if see_all.count() > 0:
                see_all.click()
                page.wait_for_timeout(2000)
                dancer_in_list = page.get_by_text("Dancer sexy", exact=True).first
                if dancer_in_list.count() > 0:
                    dancer_in_list.click()
                    page.wait_for_timeout(3000)

        # ─── Step 4: Reload Page and check composer ───
        logger.info("Step 4: Reloading Page to verify context switch...")
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        ss(page, "04_page_after_switch")
        
        # Check what the composer shows
        body_text = page.evaluate("document.body.innerText")
        if "Chia sẻ suy nghĩ" in body_text or "đang nghĩ gì" in body_text:
            logger.info("  ✅ Composer visible on Page!")
        else:
            logger.info("  ❌ Composer text not found")
        
        # ─── Step 5: Open composer ───
        logger.info("Step 5: Opening composer...")
        composer_locators = [
            page.locator("div[data-pagelet='FeedComposer'] div[role='button']").first,
            page.locator("div[aria-describedby][role='button']").first,
            page.get_by_text("Chia sẻ suy nghĩ", exact=False).first,
            page.get_by_text("đang nghĩ gì", exact=False).first
        ]
        
        composer = None
        for loc in composer_locators:
            if loc.count() > 0 and loc.is_visible():
                composer = loc
                break
        
        if not composer:
            logger.error("  ❌ Composer button not found")
            ss(page, "05_no_composer")
            context.close()
            return
            
        composer.scroll_into_view_if_needed()
        composer.click(timeout=10000)
        page.wait_for_timeout(3000)
        ss(page, "05_composer_open")
        
        # ─── Step 6: Check who is posting ───
        logger.info("Step 6: Checking who the composer says is posting...")
        # The composer modal should show "Dancer sexy" at the top if switched correctly
        dialog = page.locator("div[role='dialog']").first
        if dialog.count() > 0:
            dialog_text = dialog.evaluate("el => el.innerText")
            if "Dancer sexy" in dialog_text:
                logger.info("  ✅✅✅ Composer says posting as 'Dancer sexy'! Switch works!")
            else:
                first_100 = dialog_text[:200].replace('\n', ' | ')
                logger.info(f"  ❌ Composer does NOT say 'Dancer sexy'. Text: {first_100}")
        
        # ─── Step 7: Attach video ───
        logger.info("Step 7: Attaching video...")
        file_inputs = page.locator("input[type='file']")
        video_input = None
        for i in range(file_inputs.count()):
            accept = file_inputs.nth(i).get_attribute("accept") or ""
            if "video" in accept:
                video_input = file_inputs.nth(i)
                break
        
        if video_input:
            video_input.set_input_files("/home/vu/toolsauto/content/reup/tiktok/viral_30_7604097945885084936_reup.mp4")
            page.wait_for_timeout(5000)
            ss(page, "06_video_attached")
            logger.info("  ✅ Video attached")
        else:
            logger.info("  ❌ No video file input found")
        
        # ─── Step 8: Check if Tiếp/Đăng buttons appear ───
        logger.info("Step 8: Checking for Tiếp/Đăng buttons...")
        for label in ["Tiếp", "Đăng", "Đăng bài", "Post", "Next"]:
            els = page.locator(f'div[aria-label="{label}"]').all()
            visible = [e for e in els if e.is_visible()]
            if visible:
                logger.info(f"  ✅ Found '{label}' button ({len(visible)} visible)")
            
            text_els = page.get_by_text(label, exact=True).all()
            text_visible = [e for e in text_els if e.is_visible()]
            if text_visible:
                logger.info(f"  ✅ Found text '{label}' ({len(text_visible)} visible)")
        
        ss(page, "07_buttons_check")
        
        logger.info("🛑 Test done. NOT clicking post.")
        time.sleep(3)
        context.close()

if __name__ == "__main__":
    test()
