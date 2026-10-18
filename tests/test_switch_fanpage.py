import logging
import sys
import os

# Ensure the app module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database.core import SessionLocal
from app.core.database.models import Account, Job
from app.features.facebook.adapter import FacebookAdapter

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

def test_switch():
    print("=== Testing Fanpage Context Switch ===")
    
    # Get the specific account "Nguyen Ngoc Vi"
    with SessionLocal() as db:
        account = db.query(Account).filter_by(name="Nguyen Ngoc Vi").first()
        if not account:
            print("Account 'Nguyen Ngoc Vi' not found in DB.")
            return
            
        adapter = FacebookAdapter()
        print(f"\nOpening session for profile: {account.profile_path}")
        
        try:
            if not adapter.open_session(account.profile_path):
                print("Failed to open browser session.")
                return
                
            # Go to Facebook Home
            print("\nNavigating to www.facebook.com ...")
            adapter.page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            adapter.page.wait_for_timeout(4000)

            print(f"\nAccount has {len(account.managed_pages_list)} managed pages. Testing switches...")
            for page_info in account.managed_pages_list:
                target_page_name = page_info.get("name")
                target_page_url = page_info.get("url")
                
                print(f"\n--- Testing Switch to Fanpage: '{target_page_name}' ---")
                
                # Define safe_name early
                safe_name = target_page_name.replace(' ', '_').lower()
                
                # 1. Switch back to Personal Profile first (reset state)
                print(f"Resetting context to personal profile '{account.name}'...")
                adapter._switch_to_personal_profile(account.name)
                adapter.page.wait_for_timeout(4000)
                
                # 2. Test the switch method
                print(f"Calling _switch_to_page_context('{target_page_name}')...")
                switched = adapter._switch_to_page_context(target_page_name)
                
                print(f"Switch result for '{target_page_name}': {switched}")
                import time
                safe_name = target_page_name.replace(' ', '_').lower()
                
                if switched:
                    adapter.page.wait_for_timeout(3000)
                    adapter.page.screenshot(path=f"/home/vu/toolsauto/tests/switch_success_{safe_name}.png")
                    print(f"Saved screenshot to switch_success_{safe_name}.png")
                else:
                    adapter.page.screenshot(path=f"/home/vu/toolsauto/tests/switch_failed_{safe_name}.png")
                    print(f"Saved screenshot to switch_failed_{safe_name}.png")
                    
        except Exception as e:
            print(f"Exception during test: {e}")
        finally:
            print("Closing session.")
            adapter.close_session()

if __name__ == "__main__":
    test_switch()
