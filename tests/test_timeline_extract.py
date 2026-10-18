import os
import sys
import logging
from app.features.facebook.adapter import FacebookAdapter
from app.core.observability.job import Job
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# Gắn một job mock để adapter dùng
class MockJob:
    id = 9999
    caption = "Test footprint [ref:test1234]"

def test_timeline():
    adapter = FacebookAdapter()
    job = MockJob()
    
    print("Starting Playwright to check Timeline extraction...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/content/profiles/facebook_4",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=['--disable-dev-shm-usage', '--no-sandbox']
        )
        adapter.playwright = p
        adapter.context = context
        adapter.page = context.pages[0] if context.pages else context.new_page()
        adapter.page.set_default_timeout(15000)
        
        # Test directly extraction function
        res = adapter.check_published_state(job)
        
        print("\n=== RESULT ===")
        print(f"OK: {res.ok}")
        print(f"Error: {res.error}")
        print(f"Details: {res.details}")
        
        import time
        time.sleep(2)
        adapter.close_session()

if __name__ == "__main__":
    test_timeline()
