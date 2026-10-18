import sys
import os
import logging
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.features.facebook.adapter import FacebookAdapter

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("test_multi_account")

def test_switching():
    adapter = FacebookAdapter()
    
    test_data = [
        {
            "account_name": "Hoang Khoa",
            "profile_path": "/home/vu/toolsauto/content/profiles/facebook_3",
            "target_page": "Da Đẹp Lì Tu",
            "url": "https://www.facebook.com/kids0810"
        },
        {
            "account_name": "Nguyen Ngoc Vi",
            "profile_path": "/home/vu/toolsauto/content/profiles/facebook_4",
            "target_page": "Thu Uyên",
            "url": "https://www.facebook.com/maymacenter"
        }
    ]

    for i, data in enumerate(test_data):
        logger.info(f"\n{'='*50}\nSTEP {i+1}: Testing Account '{data['account_name']}'\n{'='*50}")
        
        # 1. Open Session
        logger.info(f"Opening session for profile: {data['profile_path']}")
        if not adapter.open_session(data['profile_path']):
            logger.error(f"Failed to open session for {data['account_name']}")
            continue
            
        try:
            # 1b. Ensure navigation to FB and wait for idle
            logger.info("Navigating to www.facebook.com and waiting for networkidle...")
            adapter.page.goto("https://www.facebook.com", wait_until="load", timeout=60000)
            
            # 2. Reset to Personal Profile
            logger.info(f"Resetting to personal profile '{data['account_name']}'...")
            adapter._switch_to_personal_profile(data['account_name'])
            
            # 3. Switch to Target Fanpage
            logger.info(f"Switching to fanpage '{data['target_page']}'...")
            switched = adapter._switch_to_page_context(data['target_page'], target_page_url=data['url'])
            
            if switched:
                logger.info(f"SUCCESS: Successfully switched to '{data['target_page']}'")
                safe_name = data['target_page'].replace(" ", "_").lower()
                adapter.page.screenshot(path=f"/home/vu/toolsauto/tests/multi_switch_success_{i}_{safe_name}.png")
            else:
                logger.error(f"FAILURE: Could not switch to '{data['target_page']}'")
                adapter.page.screenshot(path=f"/home/vu/toolsauto/tests/multi_switch_failed_{i}.png")
                
        finally:
            # 4. Close Session
            logger.info(f"Closing session for {data['account_name']}\n")
            adapter.close_session()

if __name__ == "__main__":
    test_switching()
