import sys
import os
import logging
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [INSIGHTS] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def parse_views(text):
    import re
    text = text.upper().replace(',', '.')
    match = re.search(r'([\d\.]+)\s*K', text)
    if match: return int(float(match.group(1)) * 1000)
    match = re.search(r'([\d\.]+)\s*M', text)
    if match: return int(float(match.group(1)) * 1000000)
    match = re.search(r'(\d+)', text)
    if match: return int(float(match.group(1)))
    return 0

def scrape_insights_for_page(page, db_session, account_id, target_url, platform="facebook"):
    from app.database.models import PageInsight, now_ts
    
    logger.info(f"  -> Scraping {platform.upper()}: {target_url}")
    try:
        if platform == "facebook":
            page.goto(target_url.rstrip("/") + "/reels/", timeout=60000)
        else:
            page.goto(target_url.rstrip("/"), timeout=60000)
            
        page.wait_for_timeout(5000)
        
        # Scroll much more to catch older videos that might be exploding right now
        scroll_times = 15 if platform == "facebook" else 5
        for _ in range(scroll_times):
            page.keyboard.press("End")
            page.wait_for_timeout(2000)
            
        # Selectors based on platform
        if platform == "facebook":
            # Facebook Reels grid usually only shows views. Likes might require hover/click.
            # But sometimes aria-label on the link contains both.
            js_query = """() => {
                const reels = [];
                document.querySelectorAll('a[href*="/reel/"]').forEach(l => {
                    const text = l.innerText;
                    const aria = l.getAttribute('aria-label') || '';
                    if(text && text.trim().length > 0) {
                        reels.push({
                            href: l.href, 
                            text: text.replace(/\\n/g, ' '),
                            aria: aria
                        });
                    }
                });
                return reels;
            }"""
        elif platform == "tiktok":
            js_query = r"""() => {
                const videos = [];
                document.querySelectorAll('div[data-e2e="user-post-item"]').forEach(container => {
                    const link = container.querySelector('a');
                    const viewCount = container.querySelector('[data-e2e="video-views"]')?.innerText || '';
                    if(link && viewCount) {
                        videos.push({
                            href: link.href,
                            text: viewCount.replace(/\n/g, ' '),
                            likes: 0 // Grid doesn't usually show likes on TikTok either
                        });
                    }
                });
                // Fallback for older layouts
                if(videos.length === 0) {
                    document.querySelectorAll('a[href*="/video/"]').forEach(l => {
                        const text = l.innerText; 
                        if(text && (text.includes('K') || text.includes('M') || /\d/.test(text))) {
                            videos.push({href: l.href, text: text.replace(/\n/g, ' ')});
                        }
                    });
                }
                return videos;
            }"""
        elif platform == "instagram":
            js_query = """() => {
                const reels = [];
                document.querySelectorAll('a[href*="/reel/"], a[href*="/reels/"]').forEach(l => {
                    const text = l.innerText;
                    reels.push({href: l.href, text: text});
                });
                return reels;
            }"""
        else:
            return

        items_data = page.evaluate(js_query)
        
        valid_items = []
        seen = set()
        for r in items_data:
            href = r['href'].split('?')[0]
            if href not in seen:
                seen.add(href)
                views = parse_views(r['text'].strip())
                if views > 0:
                    valid_items.append({"url": href, "views": views, "raw": r['text']})
        
        saved_count = 0
        for r in valid_items:
            # Try to extract likes from aria-label if present (FB)
            likes = 0
            if platform == "facebook" and "aria" in r:
                import re
                # Example: "Reel by XYZ. 1.2K views. 45 likes."
                like_match = re.search(r'([\d\.,]+)\s*(?:likes|lượt thích|thích)', r['aria'].lower())
                if like_match:
                    likes = parse_views(like_match.group(1))

            insight = PageInsight(
                account_id=account_id,
                platform=platform,
                page_url=target_url,
                page_name=target_url.split('/')[-1] or "Unknown",
                post_url=r['url'],
                views=r['views'],
                likes=likes,
                caption=f"Views: {r['raw']}", 
                recorded_at=now_ts()
            )
            db_session.add(insight)
            saved_count += 1
            
        db_session.commit()
        logger.info(f"  ✅ Saved {saved_count} insights for {target_url} ({platform})")
        
    except Exception as e:
        logger.error(f"  ❌ Error scraping {target_url} ({platform}): {e}")

def main():
    from app.database.core import SessionLocal
    from app.database.models import Account

    logger.info("Initializing Multi-Platform Insights Scraper...")
    with SessionLocal() as db:
        accounts = db.query(Account).filter(Account.is_active == True).all()
        
        for account in accounts:
            if not account.profile_path:
                continue
            
            # 1. Managed Facebook Pages
            fb_targets = set()
            for p in account.managed_pages_list:
                if p.get("url"): fb_targets.add(p["url"])
            for p in account.target_pages_list:
                if p and "facebook.com" in p: fb_targets.add(p)
                
            # 2. Competitor TikTok Channels
            import json
            tk_targets = set()
            if account.competitor_urls:
                try:
                    data = json.loads(account.competitor_urls)
                    if isinstance(data, list):
                        for item in data:
                            url = item.get("url") if isinstance(item, dict) else str(item)
                            if url and "tiktok.com" in url:
                                tk_targets.add(url)
                except Exception: pass
                
            # 3. Instagram (if any)
            ig_targets = set()
            if account.platform == "instagram" and account.target_page:
                ig_targets.add(account.target_page)
            for p in account.target_pages_list:
                if p and "instagram.com" in p: ig_targets.add(p)

            if not fb_targets and not tk_targets and not ig_targets:
                continue
                
            logger.info(f"Opening Profile: Account #{account.id} ({account.name})")
            try:
                with sync_playwright() as pw:
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=account.profile_path,
                        headless=True,
                        viewport={"width": 1280, "height": 720},
                        args=["--disable-blink-features=AutomationControlled", "--no-first-run", "--disable-infobars"]
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    
                    # Scrape FB
                    for url in fb_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="facebook")
                    
                    # Scrape TikTok
                    for url in tk_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="tiktok")
                        
                    # Scrape IG
                    for url in ig_targets:
                        scrape_insights_for_page(page, db, account.id, url, platform="instagram")
                        
                    context.close()
            except Exception as e:
                logger.error(f"Error launching browser for {account.name}: {e}")

if __name__ == "__main__":
    main()
