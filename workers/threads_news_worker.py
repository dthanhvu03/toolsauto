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
            
            logger.info("Cycle complete. Sleeping for 30 minutes...")
            time.sleep(1800)
            
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.exception(f"Unhandled error in Threads news worker: {e}")
            time.sleep(300)

if __name__ == "__main__":
    run_loop()
