"""
Step-by-step test to find and verify the Page switch mechanism.
Takes a screenshot at every step so we can see exactly what's happening.
"""
import os, time, logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

OUT = "/tmp/switch_steps"
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

        # Step 1: Go to Page
        target = "https://www.facebook.com/profile.php?id=61564820652101"
        logger.info(f"Step 1: Navigating to {target}")
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        ss(page, "01_page_loaded")

        # Step 2: Scan all visible buttons/links for switch-related text
        logger.info("Step 2: Scanning for switch-related elements...")
        body_text = page.evaluate("document.body.innerText")
        for keyword in ["Chuyển", "Switch", "Đổi sang", "Chuyển sang", "Chuyển đổi", "Dùng Facebook với vai trò"]:
            if keyword.lower() in body_text.lower():
                logger.info(f"  ✅ Found text containing: '{keyword}'")
            else:
                logger.info(f"  ❌ NOT found: '{keyword}'")
        
        # Step 3: Look for avatar/profile icon in top right corner
        logger.info("Step 3: Looking for top-right profile menu...")
        
        # On Facebook, the top-right has an avatar image that opens a dropdown menu
        # Try multiple selectors for the profile/account menu icon
        avatar_selectors = [
            'div[aria-label="Tài khoản của bạn"]',
            'div[aria-label="Your profile"]',
            'svg[aria-label="Tài khoản của bạn"]',
            'image[aria-label="Tài khoản của bạn"]',
            # The rightmost icon in the top bar
            'div[role="navigation"] a[role="link"][aria-current]',  # Usually links to profile
        ]
        
        avatar_btn = None
        for sel in avatar_selectors:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                avatar_btn = el
                logger.info(f"  ✅ Found avatar menu via: {sel}")
                break
            else:
                logger.info(f"  ❌ Not found: {sel}")
        
        if not avatar_btn:
            # Last resort: look for the actual avatar image in the top bar
            # Facebook top bar typically has navigation links, the last image is the profile
            logger.info("  Trying last-resort: rightmost img in top bar...")
            top_imgs = page.locator('div[role="banner"] image, div[role="banner"] img').all()
            if top_imgs:
                avatar_btn = top_imgs[-1]  # typically the last one is the profile pic
                logger.info(f"  Found {len(top_imgs)} images in banner, using last one")
        
        if avatar_btn:
            logger.info("Step 4: Clicking avatar menu...")
            avatar_btn.click()
            page.wait_for_timeout(2000)
            ss(page, "02_avatar_menu_open")
            
            # Step 5: Look for "Xem tất cả trang cá nhân" or "See all profiles"
            logger.info("Step 5: Looking for 'Xem tất cả trang cá nhân' / 'See all profiles'...")
            see_all = page.get_by_text("Xem tất cả trang cá nhân", exact=False).first
            if see_all.count() == 0:
                see_all = page.get_by_text("See all profiles", exact=False).first
            
            if see_all.count() > 0 and see_all.is_visible():
                logger.info("  ✅ Found 'Xem tất cả trang cá nhân'. Clicking...")
                see_all.click()
                page.wait_for_timeout(2000)
                ss(page, "03_all_profiles")
                
                # Step 6: Look for the Page name to switch to
                logger.info("Step 6: Looking for Page 'Dancer sexy' to switch to...")
                page_item = page.get_by_text("Dancer sexy", exact=False).first
                if page_item.count() > 0 and page_item.is_visible():
                    logger.info("  ✅ Found 'Dancer sexy'. Clicking...")
                    page_item.click()
                    page.wait_for_timeout(5000)
                    ss(page, "04_switched_to_page")
                    
                    # Verify: check if the composer now says "Dancer sexy" or similar
                    logger.info("Step 7: Verifying switch...")
                    page.goto(target, wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                    ss(page, "05_page_after_switch")
                    
                    # Check if composer area changed
                    body_after = page.evaluate("document.body.innerText")
                    if "Bạn đang nghĩ gì" in body_after or "đang nghĩ gì" in body_after:
                        logger.info("  ✅ Composer visible after switch!")
                    else:
                        logger.info("  ❌ Composer not visible after switch")
                else:
                    logger.info("  ❌ 'Dancer sexy' not found in profiles list")
            else:
                logger.info("  ❌ 'Xem tất cả trang cá nhân' not found")
                
                # Try alternative: look for the Page name directly in the menu
                logger.info("  Trying alternative: looking for Page name directly in menu...")
                page_direct = page.get_by_text("Dancer sexy", exact=False).first
                if page_direct.count() > 0 and page_direct.is_visible():
                    logger.info("  ✅ Found 'Dancer sexy' directly in menu")
                    page_direct.click()
                    page.wait_for_timeout(5000)
                    ss(page, "03_alt_switched")
                else:
                    logger.info("  ❌ 'Dancer sexy' not found in menu either")
                    # Dump all visible text in the menu area for debugging
                    menu_text = page.evaluate("""
                        () => {
                            const dialogs = document.querySelectorAll('div[role="dialog"], div[role="menu"]');
                            return Array.from(dialogs).map(d => d.innerText.substring(0, 300)).join('\\n---\\n');
                        }
                    """)
                    logger.info(f"  Menu/dialog text: {menu_text[:500]}")
        else:
            logger.info("❌ Could not find avatar menu at all!")
            
            # Dump all interactive elements in the top bar for debugging
            logger.info("Dumping top bar elements...")
            top_elements = page.evaluate("""
                () => {
                    const banner = document.querySelector('div[role="banner"]');
                    if (!banner) return 'No banner found';
                    const buttons = banner.querySelectorAll('[role="button"], [role="link"], a, button');
                    return Array.from(buttons).map(b => ({
                        tag: b.tagName,
                        role: b.getAttribute('role'),
                        ariaLabel: b.getAttribute('aria-label'),
                        text: b.innerText?.substring(0, 50)
                    }));
                }
            """)
            logger.info(f"Top bar elements: {top_elements}")

        time.sleep(2)
        context.close()
        logger.info("Test complete!")

if __name__ == "__main__":
    test()
