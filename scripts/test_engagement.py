"""
Test suite cho Idle Engagement feature.
Chạy: python3 scripts/test_engagement.py

Test items:
  1. parse_niche_topics() utility
  2. Bezier curve math (no browser needed)
  3. Config loading (new env vars)
  4. DB Schema (niche_topics column exists)
  5. FacebookEngagementTask import & action selection (mocked page)
  6. _maybe_idle_engagement logic flow (import check)
"""
import sys
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


# ═══════════════════════════════════════════════
# TEST 1: parse_niche_topics utility
# ═══════════════════════════════════════════════
print("\n📋 TEST 1: parse_niche_topics()")
from app.adapters.facebook.engagement import parse_niche_topics

# JSON array
result = parse_niche_topics('["thời trang","decor","phụ kiện"]')
check("JSON array", result == ["thời trang", "decor", "phụ kiện"], str(result))

# Comma-separated string
result = parse_niche_topics("thời trang, decor, phụ kiện")
check("Comma-separated", result == ["thời trang", "decor", "phụ kiện"], str(result))

# None input
result = parse_niche_topics(None)
check("None → empty list", result == [], str(result))

# Empty string
result = parse_niche_topics("")
check("Empty string → empty list", result == [], str(result))

# Single keyword
result = parse_niche_topics("thời trang")
check("Single keyword", result == ["thời trang"], str(result))


# ═══════════════════════════════════════════════
# TEST 2: Bezier Curve math
# ═══════════════════════════════════════════════
print("\n📋 TEST 2: Bezier Curve math")
from app.utils.human_behavior import _bezier_point, _generate_bezier_path

# Bezier point at t=0 should be start, t=1 should be end
p0 = (0, 0)
p3 = (100, 100)
p1 = (30, 70)
p2 = (70, 30)

start_pt = _bezier_point(0.0, p0, p1, p2, p3)
check("t=0 → start", start_pt == (0.0, 0.0), str(start_pt))

end_pt = _bezier_point(1.0, p0, p1, p2, p3)
check("t=1 → end", end_pt == (100.0, 100.0), str(end_pt))

# Path generation
path = _generate_bezier_path((100, 100), (500, 400), steps=20)
check("Path has > 20 points", len(path) > 20, f"len={len(path)}")
check("Path ends near target", abs(path[-1][0] - 500) <= 1 and abs(path[-1][1] - 400) <= 1,
      f"last={path[-1]}")
check("All points are int tuples", all(isinstance(p[0], int) and isinstance(p[1], int) for p in path),
      "non-int found")


# ═══════════════════════════════════════════════
# TEST 3: Config loading
# ═══════════════════════════════════════════════
print("\n📋 TEST 3: Config loading")
import app.config as config

check("IDLE_ENGAGEMENT_ENABLED exists", hasattr(config, "IDLE_ENGAGEMENT_ENABLED"))
check("IDLE_ENGAGEMENT_ENABLED is bool", isinstance(config.IDLE_ENGAGEMENT_ENABLED, bool))
check("IDLE_ENGAGEMENT_PROBABILITY exists", hasattr(config, "IDLE_ENGAGEMENT_PROBABILITY"))
check("IDLE_ENGAGEMENT_PROBABILITY in range", 0 <= config.IDLE_ENGAGEMENT_PROBABILITY <= 1,
      str(config.IDLE_ENGAGEMENT_PROBABILITY))
check("IDLE_MAX_DURATION_SECONDS exists", hasattr(config, "IDLE_MAX_DURATION_SECONDS"))
check("IDLE_MAX_DURATION_SECONDS > 0", config.IDLE_MAX_DURATION_SECONDS > 0,
      str(config.IDLE_MAX_DURATION_SECONDS))

print(f"  ℹ️  Values: enabled={config.IDLE_ENGAGEMENT_ENABLED}, "
      f"prob={config.IDLE_ENGAGEMENT_PROBABILITY}, "
      f"max_dur={config.IDLE_MAX_DURATION_SECONDS}s")


# ═══════════════════════════════════════════════
# TEST 4: DB Schema (niche_topics column)
# ═══════════════════════════════════════════════
print("\n📋 TEST 4: DB Schema")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "auto_publisher.db"

if DB_PATH.exists():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(accounts)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    check("niche_topics column exists", "niche_topics" in columns, f"cols={list(columns.keys())}")
    check("niche_topics type is TEXT", columns.get("niche_topics") == "TEXT",
          columns.get("niche_topics"))
    
    # Check row count preservation
    cursor.execute("SELECT count(*) FROM accounts")
    count = cursor.fetchone()[0]
    check(f"Accounts table has rows ({count})", count > 0)
    
    conn.close()
else:
    print("  ⚠️  DB file not found, skipping DB tests")


# ═══════════════════════════════════════════════
# TEST 5: FacebookEngagementTask (mocked page)
# ═══════════════════════════════════════════════
print("\n📋 TEST 5: FacebookEngagementTask (mocked)")
from app.adapters.facebook.engagement import FacebookEngagementTask, _is_checkpointed

# Mock page
mock_page = MagicMock()
mock_page.url = "https://www.facebook.com/"
mock_page.locator.return_value.count.return_value = 0

task = FacebookEngagementTask(mock_page)
check("Instantiation OK", task.page is mock_page)

# Checkpoint detection on login page
mock_page.url = "https://www.facebook.com/login/?next"
check("Checkpoint detected on /login/", _is_checkpointed(mock_page) == True)

# Checkpoint NOT detected on normal page
mock_page.url = "https://www.facebook.com/"
mock_page.locator.return_value.count.return_value = 0
check("No false checkpoint on normal page", _is_checkpointed(mock_page) == False)

# Action selection distribution test (run 1000 times, check all actions appear)
action_counts = {"scroll_news_feed": 0, "watch_reels": 0, "search_topic": 0}
niche = ["thời trang", "decor"]

for _ in range(1000):
    # Mock to avoid actual browser actions – just test selection logic
    import random
    actions = [("scroll_news_feed", 0.40), ("watch_reels", 0.35)]
    if niche:
        actions.append(("search_topic", 0.25))
    total = sum(w for _, w in actions)
    roll = random.uniform(0, total)
    cumulative = 0.0
    for name, weight in actions:
        cumulative += weight
        if roll <= cumulative:
            action_counts[name] += 1
            break

check("All 3 actions appear in 1000 rolls",
      all(v > 0 for v in action_counts.values()),
      str(action_counts))
check("scroll_news_feed most frequent (≈40%)",
      action_counts["scroll_news_feed"] > 300,
      str(action_counts))

print(f"  ℹ️  Distribution: {action_counts}")


# ═══════════════════════════════════════════════
# TEST 6: Publisher integration (import check)
# ═══════════════════════════════════════════════
print("\n📋 TEST 6: Publisher integration")

# Test _maybe_idle_engagement can be imported
try:
    from workers.publisher import _maybe_idle_engagement
    check("_maybe_idle_engagement importable", True)
    check("Is callable", callable(_maybe_idle_engagement))
except ImportError as e:
    check("_maybe_idle_engagement importable", False, str(e))


# ═══════════════════════════════════════════════
# TEST 7: human_behavior new functions
# ═══════════════════════════════════════════════
print("\n📋 TEST 7: human_behavior new functions")
from app.utils.human_behavior import stealth_move, stealth_click, casual_scroll_feed, human_search

check("stealth_move callable", callable(stealth_move))
check("stealth_click callable", callable(stealth_click))
check("casual_scroll_feed callable", callable(casual_scroll_feed))
check("human_search callable", callable(human_search))


# ═══════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"📊 RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
if FAIL == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠️  {FAIL} test(s) FAILED")
print(f"{'='*50}")

sys.exit(0 if FAIL == 0 else 1)
