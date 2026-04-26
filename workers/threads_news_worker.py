import time
import logging
import sys
import os
from pathlib import Path

# Repo root on sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.utils.logger import setup_shared_logger
setup_shared_logger("app")
logger = setup_shared_logger("threads_news_worker")

from app.services.news_scraper import NewsScraper
from app.services.threads_news import ThreadsNewsService
from app.database.core import SessionLocal
from app.database.models import RuntimeSetting

def _get_scrape_cycle_seconds():
    """Read THREADS_SCRAPE_CYCLE_MIN from DB, default 30 min."""
    try:
        db = SessionLocal()
        s = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_SCRAPE_CYCLE_MIN").first()
        db.close()
        if s:
            return int(s.value) * 60
    except Exception:
        pass
    return 1800  # 30 min default

def run_loop():
    logger.info("Threads News Worker started.")
    scraper = NewsScraper()
    service = ThreadsNewsService()
    
    while True:
        try:
            logger.info("--- Starting News Cycle ---")
            
            # 1. Scrape latest news
            logger.info("Scraping latest news...")
            scraper.scrape_all()
            
            # 2. Process news to Threads jobs
            logger.info("Processing news to Threads...")
            service.process_news_to_threads()
            
            sleep_sec = _get_scrape_cycle_seconds()
            logger.info(f"Cycle complete. Sleeping for {sleep_sec // 60} minutes...")
            time.sleep(sleep_sec)
            
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.exception(f"Unhandled error in Threads news worker: {e}")
            time.sleep(300)

if __name__ == "__main__":
    run_loop()
