"""
Human behavior simulation utilities for Playwright automation.
Provides natural typing, scrolling, and delay patterns to avoid bot detection.

Enhanced with:
- Bezier Curve mouse movement (anti-linear detection)
- Randomized click area (avoid center-pixel patterns)
- Stealth move/click helpers
"""
import math
import random
import time


# ---------------------------------------------------------------------------
# Core helpers (original)
# ---------------------------------------------------------------------------

def human_type(page, text: str):
    """
    Type text character-by-character with human-like delays.
    Uses insert_text() instead of type() for reliable emoji/UTF-8 handling.

    Timing: ~0.03-0.12s per char → 100 chars ≈ 3-12 seconds.
    """
    for char in text:
        page.keyboard.insert_text(char)
        time.sleep(random.uniform(0.03, 0.12))
    # Natural pause after finishing typing
    time.sleep(random.uniform(0.5, 1.5))


def human_scroll(page, direction: str = "down"):
    """
    Simulate a single casual scroll on the feed.
    Should be called AFTER login check, BEFORE opening composer.
    """
    delta = random.randint(300, 900) if direction == "down" else -random.randint(300, 900)
    page.mouse.wheel(0, delta)
    page.wait_for_timeout(random.randint(1000, 3000))


def pre_post_delay(page):
    """
    Simulate human hesitation before clicking the Post button.
    2-6 seconds of "thinking".
    """
    page.wait_for_timeout(random.randint(2000, 6000))


# ---------------------------------------------------------------------------
# Bezier Curve mouse movement  (Phase: Idle Engagement)
# ---------------------------------------------------------------------------

def _bezier_point(t: float, p0, p1, p2, p3):
    """Calculate a point on a cubic Bezier curve at parameter t (0..1)."""
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _generate_bezier_path(start, end, steps=25):
    """
    Generate a list of (x, y) points along a cubic Bezier curve
    from *start* to *end* with two random control points.
    Includes natural "overshoot" by pushing the last control
    point slightly past the target.
    """
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy

    # Control points: random offsets to create a natural arc
    cp1 = (sx + dx * random.uniform(0.15, 0.45) + random.randint(-60, 60),
            sy + dy * random.uniform(0.15, 0.45) + random.randint(-60, 60))
    cp2 = (sx + dx * random.uniform(0.55, 0.85) + random.randint(-40, 40),
            sy + dy * random.uniform(0.55, 0.85) + random.randint(-40, 40))

    # Slight overshoot on the end point
    overshoot = random.uniform(0.0, 0.08)
    end_os = (ex + dx * overshoot, ey + dy * overshoot)

    points = []
    for i in range(steps + 1):
        t = i / steps
        px, py = _bezier_point(t, (sx, sy), cp1, cp2, end_os)
        points.append((int(px), int(py)))

    # Correct back to exact target at the end
    points.append((int(ex), int(ey)))
    return points


def stealth_move(page, target_x: int, target_y: int):
    """
    Move the mouse from its current position to (target_x, target_y)
    along a Bezier curve with human-like speed variation.
    """
    # Get current mouse position (approximate via bounding box of viewport)
    # Playwright doesn't expose cursor pos directly, so we start from a
    # "last known" random spot if not tracked.  We move from (0, 0) for
    # the very first call – callers should seed the cursor first.
    start_x = random.randint(100, 400)
    start_y = random.randint(100, 400)

    path = _generate_bezier_path((start_x, start_y), (target_x, target_y))

    for px, py in path:
        page.mouse.move(px, py)
        # Variable speed: slower near target (deceleration)
        dist_to_target = math.hypot(target_x - px, target_y - py)
        if dist_to_target < 30:
            time.sleep(random.uniform(0.012, 0.035))
        else:
            time.sleep(random.uniform(0.004, 0.018))


def stealth_click(page, locator):
    """
    Click an element using Bezier mouse movement + randomized click area.
    Moves cursor to a random point *inside* the element bounding box,
    then performs the click.

    Usage:
        stealth_click(page, page.locator("button[aria-label='Like']"))
    """
    box = locator.bounding_box()
    if not box:
        # Fallback: regular click if element has no visible bbox
        locator.click()
        return

    # Pick a random point inside the bbox (avoid dead-center)
    margin_x = box["width"] * 0.15
    margin_y = box["height"] * 0.15
    click_x = box["x"] + random.uniform(margin_x, box["width"] - margin_x)
    click_y = box["y"] + random.uniform(margin_y, box["height"] - margin_y)

    stealth_move(page, int(click_x), int(click_y))

    # Small hesitation before clicking
    time.sleep(random.uniform(0.08, 0.25))
    page.mouse.click(click_x, click_y)
    time.sleep(random.uniform(0.15, 0.4))


# ---------------------------------------------------------------------------
# Feed interaction helpers  (Phase: Idle Engagement)
# ---------------------------------------------------------------------------

def casual_scroll_feed(page, duration_seconds: int = 60):
    """
    Scroll News Feed for *duration_seconds* with natural pauses.
    Occasionally pauses longer (simulating reading), randomly
    scrolls back up a little bit (re-reading behaviour).
    """
    deadline = time.time() + duration_seconds
    while time.time() < deadline:
        # Scroll down by a random chunk
        delta = random.randint(250, 700)
        page.mouse.wheel(0, delta)
        
        # Reading pause – sometimes long
        if random.random() < 0.15:
            # "Got distracted" – long pause
            page.wait_for_timeout(random.randint(4000, 8000))
        elif random.random() < 0.25:
            # "Interested" – medium pause
            page.wait_for_timeout(random.randint(2000, 4000))
        else:
            # Quick glance
            page.wait_for_timeout(random.randint(800, 2000))

        # Occasionally scroll back up (re-read / missed something)
        if random.random() < 0.1:
            page.mouse.wheel(0, -random.randint(100, 350))
            page.wait_for_timeout(random.randint(1000, 2500))


def human_search(page, query: str):
    """
    Type a search query into the Facebook search bar with human-like behaviour.
    Includes: click search icon → type slowly → press Enter → wait for results.
    """
    # 1. Click search bar
    search_selectors = [
        "input[type='search']",
        "input[placeholder*='Tìm kiếm']",
        "input[placeholder*='Search']",
        "div[aria-label='Tìm kiếm trên Facebook']",
        "div[aria-label='Search Facebook']",
    ]

    search_box = None
    for sel in search_selectors:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            search_box = loc
            break

    if not search_box:
        # Try clicking the search icon first (mobile/compact layout)
        icon_selectors = [
            "a[aria-label='Tìm kiếm']",
            "a[aria-label='Search']",
            "svg[aria-label='Search']",
        ]
        for sel in icon_selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                stealth_click(page, loc)
                page.wait_for_timeout(random.randint(800, 1500))
                # Try again for the input
                for sel2 in search_selectors:
                    loc2 = page.locator(sel2).first
                    if loc2.count() > 0 and loc2.is_visible():
                        search_box = loc2
                        break
                break

    if not search_box:
        raise RuntimeError("Facebook search bar not found")

    stealth_click(page, search_box)
    page.wait_for_timeout(random.randint(500, 1000))

    # 2. Type query — word-by-word to preserve Vietnamese diacritics
    #    char-by-char insert_text() breaks composed chars (ờ, ạ, ế, ủ...)
    #    on Facebook's React autocomplete input.
    words = query.split(" ")
    for i, word in enumerate(words):
        page.keyboard.insert_text(word)
        time.sleep(random.uniform(0.15, 0.35))
        if i < len(words) - 1:
            page.keyboard.insert_text(" ")
            time.sleep(random.uniform(0.08, 0.20))
    time.sleep(random.uniform(0.3, 0.8))

    # 3. Press Enter
    page.wait_for_timeout(random.randint(300, 800))
    page.keyboard.press("Enter")
    page.wait_for_timeout(random.randint(2000, 4000))
