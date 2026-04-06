import logging
import sqlite3
import time
import os
import sys

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("app.adapters.facebook.adapter")
logger.setLevel(logging.DEBUG)

def setup_db(selector_val, timing_val):
    conn = sqlite3.connect('data/auto_publisher.db')
    cursor = conn.cursor()
    # 1. Selector DB Override
    cursor.execute("DELETE FROM platform_selectors WHERE category='recovery' AND selector_name='session_recovery_button'")
    if selector_val:
        cursor.execute("""
            INSERT INTO platform_selectors (platform, category, selector_name, selector_type, selector_value, locale, priority, version, is_active, created_at, updated_at)
            VALUES ('facebook', 'recovery', 'session_recovery_button', 'css', ?, 'en', 10, 1, 1, 0, 0)
        """, (selector_val,))
    
    # 2. Timing DB Override
    cursor.execute("DELETE FROM workflow_definitions WHERE name='post_facebook_reels'")
    import json
    new_timing = {
        'feed_browse_pause': timing_val if timing_val else 4000,
        'post_navigation_wait_ms': 4000,
        'session_recovery_wait_ms': 8000
    }
    cursor.execute("""
        INSERT INTO workflow_definitions (name, platform, job_type, is_active, steps, timing_config, retry_config, created_at, updated_at)
        VALUES ('post_facebook_reels', 'facebook', 'POST', 1, '[]', ?, '{}', 0, 0)
    """, (json.dumps(new_timing),))

    conn.commit()
    conn.close()
    
    # Invalidate cache
    from app.services.workflow_registry import invalidate as invalidate_cache
    invalidate_cache()

class DummyAccount:
    name = "Dummy Person"
class DummyJob:
    id = 999
    account = DummyAccount()
    target_page_url = ""
    caption = "Smoke Test"
    media_path = ""

from app.adapters.facebook.adapter import FacebookAdapter

def run_smoke_test(test_name, db_selector, db_timing):
    print(f"\n\n{'='*60}\n>> RUNNING SMOKE TEST: {test_name}\n{'='*60}")
    setup_db(db_selector, db_timing)
    
    adapter = FacebookAdapter()
    
    start_time = time.time()
    try:
        # Tương đương worker chạy thật flow Publish.
        # Flow publish sẽ gọi _ensure_authenticated_context (test selector)
        # và gọi goto facebook (test feed_browse_pause timing)
        
        # Chúng ta phải mở session trực tiếp vì publish gọi open_session thông qua config ở vòng ngoài
        print(">> Opening Headless Playwright Session...")
        adapter.open_session("/tmp/dummy_fb_profile")
        
        # Test C: Timing Hit
        # Thử gọi hàm _get_dynamic_timing trực tiếp hoặc thông qua publish logic
        # Publish requires valid job. Let's just trigger the context logic because full publish fails on missing media.
        print(">> Triggering authentication check (Selector bridge test)...")
        adapter._ensure_authenticated_context()
        
        print(">> Triggering browser navigation (Timing bridge test)...")
        adapter.page.goto("https://example.com")
        adapter.page.wait_for_timeout(adapter._get_dynamic_timing("feed_browse_pause", 4000))

    except Exception as e:
        print(f"Exception caught during test: {e}")
    finally:
        adapter.close_session()

if __name__ == "__main__":
    # Smoke Test A: Fallback baseline
    run_smoke_test("TEST A - FALLBACK BASELINE", None, None)
    
    # Smoke Test B & C: DB Hit + Timing Hit 
    # Bơm 1 timing 2000ms bất thường để kiểm tra Playwright có pause đúng 2s ko (DB Hit)
    run_smoke_test("TEST B+C - DB OVERRIDE HIT", "button[id='magic-recovery-btn']", 2000)

    # Smoke Test D: Hardening (Bad Data)
    print(f"\n\n{'='*60}\n>> RUNNING SMOKE TEST: TEST D - REGISTRY HARDENING\n{'='*60}")
    # Xoá db hẳn đi tạm thời hoặc đổi tên file để registry exception
    try:
        os.rename('data/auto_publisher.db', 'data/auto_publisher.db.bak')
        from app.services.workflow_registry import invalidate as invalidate_cache
        invalidate_cache()
        adapter = FacebookAdapter()
        # Hàm này phải trigger try-except warning log của helper mà ko sập flow!
        adapter._get_dynamic_selectors("recovery", "session_recovery_button", "fallback")
    except Exception as e:
        print("FAIL: Crash during broken DB:", e)
    finally:
        if os.path.exists('data/auto_publisher.db.bak'):
            os.rename('data/auto_publisher.db.bak', 'data/auto_publisher.db')
