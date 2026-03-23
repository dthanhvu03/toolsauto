"""
Scrape managed Facebook Pages for each active account.

Opens each account's browser profile, navigates to the Pages management page,
and extracts all Page names + URLs. Saves results to the account's managed_pages column.

Usage:
    python scripts/scrape_pages.py              # Scrape all active accounts
    python scripts/scrape_pages.py --account 4  # Scrape specific account
"""
import sys
import os
import json
import logging
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [PAGE_SCRAPER] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def scrape_pages_for_account(account_id: int, profile_path: str, account_name: str) -> list[dict]:
    """
    Open browser profile and scrape managed pages from Facebook.
    Returns list of {"name": "...", "url": "..."} dicts.
    """
    from playwright.sync_api import sync_playwright
    import random
    import time

    pages_found = []

    logger.info("Opening browser for account %d (%s)...", account_id, account_name)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-infobars",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            # Navigate to Pages management
            logger.info("  Navigating to Pages management...")
            page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)

            # Check login
            if page.locator('input[name="email"]').count() > 0:
                logger.error("  ❌ Account not logged in! Skipping.")
                return []

            # Handle "Chuyển tài khoản" (Switch Account) page
            # This appears when the browser profile is in a Page context instead of personal profile
            # The "Tiếp tục" button may be an <input type="submit">, not a <button>
            page_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
            if "Chuyển tài khoản" in page_text or "Switch account" in page_text:
                logger.info("  ⚡ Detected 'Chuyển tài khoản' page — switching to personal profile...")
                switch_btn = page.locator('input[type="submit"], button, [role="button"]').filter(has_text="Tiếp tục")
                if switch_btn.count() == 0:
                    switch_btn = page.locator('input[type="submit"], button, [role="button"]').filter(has_text="Continue")
                if switch_btn.count() > 0:
                    switch_btn.first.click()
                    page.wait_for_timeout(5000)
                    # After switching, navigate again to pages management
                    logger.info("  ✅ Switched! Navigating to Pages management again...")
                    page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(5000)
                else:
                    logger.warning("  ⚠️ Switch page detected but 'Tiếp tục' button not found")

            # Wait for page list to render
            page.wait_for_timeout(3000)

            # Strategy 1: Look for page cards with links
            # Facebook shows pages as cards with links to the page
            page_links = page.locator('a[href*="/profile.php?id="], a[href*="facebook.com/"][role="link"]').all()

            seen_urls = set()
            for link in page_links:
                try:
                    href = link.get_attribute("href") or ""
                    if not href or href == "" or href == "#" or href.endswith("/pages/?category=your_pages"):
                        continue

                    if "notifications" in href.lower() or "settings" in href.lower():
                        continue

                    # Clean URL
                    clean_url = href.split("?")[0] if "profile.php" not in href else href.split("&")[0]
                    if not clean_url.startswith("http"):
                        clean_url = "https://www.facebook.com" + clean_url

                    if clean_url in seen_urls:
                        continue

                    # Try to get the page name from the link text or nearby elements
                    name = ""
                    try:
                        name = link.inner_text().strip()
                    except Exception:
                        pass

                    if not name or len(name) > 100 or len(name) < 2:
                        continue

                    # Skip non-page items and specific UI elements
                    skip_words = ["tạo", "create", "quảng cáo", "ads", "trang", "page", "xem thêm", "see more", "meta business suite", "hộp thư", "thông tin chi tiết"]
                    if any(w in name.lower() for w in skip_words) and len(name) < 20:
                        continue
                        
                    skip_urls = ["business.facebook.com", "/latest/", "/login", "/reg/", "/privacy/"]
                    if any(s_url in clean_url.lower() for s_url in skip_urls):
                        continue

                    seen_urls.add(clean_url)
                    pages_found.append({"name": name, "url": clean_url})
                    logger.info("    📄 Found page: %s → %s", name, clean_url)
                except Exception:
                    continue

            # Strategy 2: If no pages found via links, try scraping the sidebar/list
            if not pages_found:
                logger.info("  Strategy 1 found nothing. Trying broader scan...")

                # Try the "Your Pages" section which may have different selectors
                page.goto("https://www.facebook.com/pages/?category=your_pages&ref=bookmarks", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(5000)

                # Look for any link that looks like a page
                all_links = page.locator('a').all()
                for link in all_links:
                    try:
                        href = link.get_attribute("href") or ""
                        if not href:
                            continue
                        # Match profile.php?id= pattern (common for pages)
                        if "profile.php?id=" in href or (href.startswith("/") and "/" not in href[1:] and len(href) > 3):
                            clean_url = href.split("?")[0] if "profile.php" not in href else href.split("&")[0]
                            if not clean_url.startswith("http"):
                                clean_url = "https://www.facebook.com" + clean_url

                            if clean_url in seen_urls:
                                continue

                            name = ""
                            try:
                                name = link.inner_text().strip()
                            except Exception:
                                pass

                            if name and 2 < len(name) < 100:
                                # Additional global filters
                                skip_urls = ["business.facebook.com", "/latest/", "/login", "/reg/", "/privacy/", "/about/", "/help/", "/policies/", "developers.facebook", "l.facebook.com", "/watch/", "/lite/", "/careers/"]
                                skip_names = ["meta business suite", "hộp thư", "thông tin chi tiết", "inbox", "insights", "sign up", "log in", "messenger", "facebook lite", "video", "privacy policy", "privacy centre", "about", "developers", "careers", "cookies", "adchoices", "terms", "help"]
                                
                                if any(s_url in clean_url.lower() for s_url in skip_urls):
                                    continue
                                if any(s_name in name.lower() for s_name in skip_names):
                                    continue
                                    
                                seen_urls.add(clean_url)
                                pages_found.append({"name": name, "url": clean_url})
                                logger.info("    📄 Found page (strategy 2): %s → %s", name, clean_url)
                    except Exception:
                        continue

            # Strategy 3: Navigate to the switch profile menu
            if not pages_found:
                logger.info("  Strategies 1-2 found nothing. Trying profile switcher...")
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)

                # Click account menu
                avatar_btn = page.locator('div[role="navigation"] svg[role="img"]').last
                if avatar_btn and avatar_btn.is_visible():
                    avatar_btn.click()
                    page.wait_for_timeout(2000)

                    # Click "See all profiles" / "Xem tất cả trang cá nhân"
                    see_all = page.locator('div[role="dialog"] div[role="button"]:has-text("Xem tất cả"), div[role="dialog"] div[role="button"]:has-text("See all")').first
                    if see_all and see_all.is_visible():
                        see_all.click()
                        page.wait_for_timeout(2000)

                        # List all profile items (excluding the personal profile)
                        items = page.locator('div[role="dialog"] div[role="button"]').all()
                        for item in items:
                            try:
                                text = item.inner_text().strip()
                                # Skip personal profile and control buttons
                                if text in [account_name, "Tạo Trang mới", "Create new Page", ""]:
                                    continue
                                if any(skip in text.lower() for skip in ["xem tất cả", "see all", "tạo", "create"]):
                                    continue

                                # This is likely a managed page name
                                if 2 < len(text) < 100:
                                    # We don't have URL from switcher, we'll need to navigate
                                    pages_found.append({"name": text, "url": ""})
                                    logger.info("    📄 Found page (switcher): %s", text)
                            except Exception:
                                continue

                    # Dismiss dialog
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(1000)

                # Try to resolve URLs for pages found via switcher
                for pg in pages_found:
                    if not pg["url"]:
                        try:
                            search_url = f"https://www.facebook.com/search/pages/?q={pg['name']}"
                            page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
                            page.wait_for_timeout(3000)
                            # Find first result matching the name
                            result_link = page.locator(f'a:has-text("{pg["name"]}")').first
                            if result_link and result_link.is_visible():
                                href = result_link.get_attribute("href") or ""
                                if href:
                                    pg["url"] = href.split("?")[0] if "profile.php" not in href else href.split("&")[0]
                                    if not pg["url"].startswith("http"):
                                        pg["url"] = "https://www.facebook.com" + pg["url"]
                                    logger.info("    🔗 Resolved URL for '%s': %s", pg["name"], pg["url"])
                        except Exception as e:
                            logger.warning("    ⚠️ Could not resolve URL for '%s': %s", pg["name"], e)

            logger.info("  Total pages found for account %d: %d", account_id, len(pages_found))

        except Exception as e:
            logger.exception("  ❌ Error scraping pages for account %d: %s", account_id, e)
        finally:
            context.close()

    return pages_found


def main():
    parser = argparse.ArgumentParser(description="Scrape managed Facebook pages")
    parser.add_argument("--account", type=int, help="Specific account ID to scrape")
    args = parser.parse_args()

    from app.database.core import SessionLocal
    from app.database.models import Account

    with SessionLocal() as db:
        query = db.query(Account).filter(Account.is_active == True)
        if args.account:
            query = query.filter(Account.id == args.account)

        accounts = query.all()

        if not accounts:
            logger.error("No active accounts found.")
            return 1

        logger.info("=" * 60)
        logger.info("  MANAGED PAGES SCRAPER")
        logger.info("  Accounts to scan: %d", len(accounts))
        logger.info("=" * 60)

        for account in accounts:
            if not account.profile_path:
                logger.warning("  Account %d (%s) has no profile_path. Skipping.", account.id, account.name)
                continue

            pages = scrape_pages_for_account(account.id, account.profile_path, account.name)

            if pages:
                account.managed_pages = json.dumps(pages, ensure_ascii=False)
                db.commit()
                logger.info("  ✅ Saved %d pages for account %d (%s)", len(pages), account.id, account.name)
            else:
                logger.warning("  ⚠️ No pages found for account %d (%s)", account.id, account.name)

        # Print summary
        logger.info("=" * 60)
        logger.info("  SUMMARY")
        for account in accounts:
            db.refresh(account)
            page_list = account.managed_pages_list
            logger.info("  Account %d (%s): %d pages", account.id, account.name, len(page_list))
            for pg in page_list:
                logger.info("    • %s → %s", pg.get("name", "?"), pg.get("url", "?"))
        logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
