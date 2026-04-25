import time
import logging
import sys
import os
from pathlib import Path
import asyncio
from playwright.async_api import async_playwright
import hashlib

# Repo root on sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.utils.logger import setup_shared_logger
setup_shared_logger("app")
logger = setup_shared_logger("threads_auto_reply")

from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import Account, ThreadsInteraction
from app.services.gemini_api import GeminiAPIService

async def process_account(account: Account, db: Session):
    logger.info(f"Processing Threads auto-reply for account: {account.name}")
    
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=account.resolved_profile_path,
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            
            page = await context.new_page()
            logger.info("Checking notifications...")
            await page.goto("https://www.threads.net/notifications", wait_until="load", timeout=60000)
            await asyncio.sleep(8)
            
            # Find notification items
            # Simplified structure check
            items_locator = page.locator('div[role="listitem"]')
            count = await items_locator.count()
            logger.info(f"Found {count} notification items.")
            
            for i in range(count):
                item = items_locator.nth(i)
                text = await item.inner_text()
                
                # Check if it's a reply or mention
                if any(k in text for k in ["Reply", "Trả lời", "mentioned", "nhắc đến"]):
                    # Extract identifying info
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if not lines: continue
                    
                    username = lines[0].split(" ")[0]
                    content_snippet = " ".join(lines[1:3])
                    
                    # Dedupe key
                    thread_id = hashlib.md5(f"{username}_{content_snippet[:50]}".encode()).hexdigest()
                    
                    # Check DB
                    exists = db.query(ThreadsInteraction).filter(
                        ThreadsInteraction.account_id == account.id,
                        ThreadsInteraction.thread_id == thread_id
                    ).first()
                    
                    if exists:
                        logger.debug(f"Already replied to {username} ({thread_id}). Skipping.")
                        continue
                        
                    logger.info(f"New interaction from {username}: {content_snippet[:50]}...")
                    
                    # Generate AI response
                    prompt = f"Bạn là một người dùng Threads thân thiện, hài hước và tinh tế. Hãy viết một câu trả lời ngắn gọn (dưới 20 từ) cho bình luận sau: '{content_snippet}'. Hãy dùng ngôn ngữ tự nhiên, trẻ trung."
                    ai_reply = GeminiAPIService().ask(prompt)
                    
                    if not ai_reply:
                        ai_reply = "Cảm ơn bạn đã chia sẻ nhé! 😊"
                    
                    # Clean AI reply (remove quotes if any)
                    ai_reply = ai_reply.strip().strip('"').strip("'")
                    
                    # Click Reply
                    reply_button = item.locator('span:has-text("Reply"), div:has-text("Reply"), span:has-text("Trả lời")').first
                    if await reply_button.count() > 0:
                        await reply_button.click(force=True)
                        await asyncio.sleep(8)
                        
                        # Handle Thread Detail Page
                        # Check for bubble icon if editor not visible
                        editor = page.locator('div[role="textbox"], div[aria-label*="Reply"], div[aria-label*="Bình luận"]').first
                        if await editor.count() == 0:
                            bubble = page.locator('div[role="button"] svg[aria-label="Reply"], div[role="button"] svg[aria-label="Trả lời"]').first
                            if await bubble.count() > 0:
                                await bubble.click(force=True)
                                await asyncio.sleep(3)
                                editor = page.locator('div[role="textbox"], div[aria-label*="Reply"], div[aria-label*="Bình luận"]').first
                        
                        if await editor.count() > 0:
                            await editor.fill(ai_reply)
                            await asyncio.sleep(2)
                            post_button = page.locator('div[role="button"]:has-text("Post"), button:has-text("Post"), div[role="button"]:has-text("Đăng")').first
                            if await post_button.count() > 0:
                                await post_button.click(force=True)
                                await asyncio.sleep(5)
                                
                                # Record in DB
                                interaction = ThreadsInteraction(
                                    account_id=account.id,
                                    thread_id=thread_id,
                                    username=username,
                                    content=ai_reply
                                )
                                db.add(interaction)
                                db.commit()
                                logger.info(f"✅ Successfully replied to {username}")
                                
                        # Back to notifications
                        await page.goto("https://www.threads.net/notifications", wait_until="load")
                        await asyncio.sleep(5)
                        # Re-locate items as the page refreshed
                        items_locator = page.locator('div[role="listitem"]')
                        
        except Exception as e:
            logger.error(f"Error processing account {account.name}: {e}")
        finally:
            await context.close()

def run_loop():
    logger.info("Threads Auto-Reply Worker loop started.")
    while True:
        try:
            with SessionLocal() as db:
                accounts = db.query(Account).filter(
                    Account.is_active == True,
                    Account.platform.contains("threads")
                ).all()
                
                if not accounts:
                    logger.info("No Threads-enabled accounts found.")
                
                for account in accounts:
                    asyncio.run(process_account(account, db))
                    
            logger.info("Finished batch. Sleeping for 15 minutes...")
            time.sleep(900)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.exception(f"Unhandled loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_loop()
