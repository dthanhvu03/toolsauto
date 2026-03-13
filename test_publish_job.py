"""
Test harness to manually run Job 211 through FacebookAdapter.publish()
"""
import sys
import logging
import asyncio
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import Job, Account
from app.adapters.facebook.adapter import FacebookAdapter
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger("ManualTest")

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_publish.py <job_id>")
        return

    job_id = int(sys.argv[1])
    db = SessionLocal()
    
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found.")
            return

        acc = db.query(Account).filter(Account.id == job.account_id).first()
        if not acc:
            logger.error(f"Account {job.account_id} not found.")
            return

        logger.info(f"Targeting Job {job_id} on Account {acc.name}")
        logger.info(f"Is Page Post? {'YES: '+job.target_page if job.target_page else 'NO'}")

        # Instantiate adapter
        adapter = FacebookAdapter()
        
        # We need a Playwright page to pass into adapter.publish()
        # In the actual worker, adapter manages its own context. We call open_session first.
        if not adapter.open_session(acc.profile_path):
            logger.error("Failed to open browser session")
            return
            
        # Fix Job status if not DRAFT
        if job.status != 'DRAFT':
            job.status = 'DRAFT'
            db.commit()
            logger.info("Reset job status to DRAFT")

        # Run publish using the synchronous interface
        logger.info("Starting publish flow...")
        result = adapter.publish(job)
        
        logger.info(f"== RESULT ==")
        logger.info(f"OK: {result.ok}")
        if not result.ok:
            logger.info(f"Error: {result.error}")
            logger.info(f"Screenshot Path: {result.screenshot_path}")
        else:
            logger.info(f"Post URL: {result.post_url}")
            
    finally:
        db.close()

if __name__ == "__main__":
    main()
