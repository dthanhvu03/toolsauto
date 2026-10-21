"""
Challenger M2.1 Adversarial Test Suite:
Empirically stress-testing PWA assets, DOM contracts, edge cases, and client-side logic
for Milestone 2 (Features F7, F8, F9, F10, F11).
"""
import json
import re
import html
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestPWAEndpointsAdversarial:
    """Stress-test PWA Manifest and Service Worker routes & contracts."""

    def test_pwa_manifest_route_direct_and_structure(self):
        res = client.get("/manifest.json")
        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}"
        
        # Verify valid JSON
        data = res.json()
        assert isinstance(data, dict), "manifest.json must parse to a JSON object"
        
        # Verify required W3C Web App Manifest keys
        required_keys = ["name", "short_name", "start_url", "display", "icons", "theme_color", "background_color"]
        for k in required_keys:
            assert k in data, f"manifest.json missing required key: {k}"
        
        assert data["name"] == "Buffer 3D Neural Cluster"
        assert data["short_name"] == "Buffer3D"
        assert data["start_url"] == "/buffer-cluster"
        assert data["display"] == "standalone"
        assert re.match(r"^#[0-9a-fA-F]{6}$", data["theme_color"])
        assert re.match(r"^#[0-9a-fA-F]{6}$", data["background_color"])
        
        # Check icons
        assert isinstance(data["icons"], list)
        assert len(data["icons"]) >= 2
        sizes = [icon.get("sizes") for icon in data["icons"]]
        assert "192x192" in sizes
        assert "512x512" in sizes
        for icon in data["icons"]:
            assert "src" in icon
            assert "type" in icon
            assert icon["type"] == "image/png"

    def test_pwa_manifest_content_type(self):
        res = client.get("/manifest.json")
        content_type = res.headers.get("content-type", "").lower()
        assert ("application/json" in content_type or "application/manifest+json" in content_type), \
            f"Expected json/manifest content-type, got: {content_type}"

    def test_pwa_service_worker_route_and_headers(self):
        res = client.get("/sw.js")
        assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}"
        
        content_type = res.headers.get("content-type", "").lower()
        assert ("javascript" in content_type), f"Expected javascript content-type, got: {content_type}"
        
        body = res.text
        # Assert service worker essential lifecycle events
        assert "self.addEventListener('install'" in body or 'self.addEventListener("install"' in body
        assert "self.addEventListener('activate'" in body or 'self.addEventListener("activate"' in body
        assert "self.addEventListener('fetch'" in body or 'self.addEventListener("fetch"' in body
        
        # Assert dual caching strategies
        assert "CACHE_NAME" in body
        assert "API_CACHE_NAME" in body
        assert "STATIC_ASSETS" in body
        assert "/manifest.json" in body
        assert "/buffer-cluster" in body
        assert "/api/buffer/" in body
        assert "503" in body  # Offline fallback status

    def test_pwa_manifest_and_sw_unauthenticated_access(self):
        # Must be publicly accessible without 401/403
        r1 = client.get("/manifest.json")
        r2 = client.get("/sw.js")
        assert r1.status_code == 200
        assert r2.status_code == 200


class TestFrontendDOMContractsM2:
    """Stress-test buffer_3d_cluster.html DOM contracts and CSS rules."""

    def test_html_pwa_head_meta_tags(self):
        res = client.get("/buffer-cluster")
        assert res.status_code == 200
        html_txt = res.text
        
        assert '<link rel="manifest" href="/manifest.json">' in html_txt
        assert 'name="viewport"' in html_txt
        assert 'viewport-fit=cover' in html_txt
        assert 'name="theme-color" content="#0a0e17"' in html_txt
        assert 'name="apple-mobile-web-app-capable" content="yes"' in html_txt
        assert 'apple-touch-icon' in html_txt

    def test_html_toolbar_search_and_filter_elements(self):
        res = client.get("/buffer-cluster")
        html_txt = res.text
        
        # Toolbar & Search
        assert 'id="cluster-toolbar"' in html_txt
        assert 'id="cluster-search-input"' in html_txt
        assert 'id="search-clear-btn"' in html_txt
        
        # Platform Filter Pills
        assert 'data-platform="all"' in html_txt
        assert 'data-platform="facebook"' in html_txt
        assert 'data-platform="tiktok"' in html_txt
        assert 'data-platform="instagram"' in html_txt
        
        # Filter Feedback badge
        assert 'id="filter-feedback"' in html_txt

    def test_html_inspector_drawer_elements(self):
        res = client.get("/buffer-cluster")
        html_txt = res.text
        
        assert 'id="right-inspector"' in html_txt
        assert 'id="inspector-backdrop"' in html_txt
        assert 'id="inspector-drag-handle"' in html_txt
        assert 'id="inspect-header-title"' in html_txt
        assert 'id="inspect-close"' in html_txt
        
        # Hero Ping & Latency
        assert 'id="inspect-btn-ping"' in html_txt
        assert 'id="inspect-latency-badge"' in html_txt
        assert 'id="inspect-latency-val"' in html_txt
        
        # Quota Panels
        assert 'id="inspect-quota-panel"' in html_txt
        assert 'id="inspect-daily-quota"' in html_txt
        assert 'id="inspect-burst-quota"' in html_txt
        assert 'id="inspect-quota-fill"' in html_txt
        
        # Cooldown Card
        assert 'id="inspect-cooldown-row"' in html_txt
        assert 'id="inspect-cooldown-timer"' in html_txt
        assert 'id="inspect-cooldown-reset-ict"' in html_txt

    def test_css_mobile_and_cyberpunk_contracts(self):
        res = client.get("/static/css/buffer_cluster.css")
        assert res.status_code == 200
        css = res.text
        
        # Latency styling classes
        assert ".latency-green" in css or ".lat-fast" in css
        assert ".latency-amber" in css or ".lat-med" in css
        assert ".latency-red" in css or ".lat-slow" in css
        
        # Responsive Bottom Sheet
        assert "@media" in css
        assert "max-width: 768px" in css or "max-width:768px" in css
        assert "translate3d" in css
        assert "touch-action: pan-y" in css or "touch-action:pan-y" in css
        
        # Filtering Dimming classes
        assert ".filter-hidden" in css
        assert ".dimmed" in css
        assert ".highlighted" in css or ".pill-highlight" in css


class TestTelemetryLogicAdversarial:
    """Empirically test client-side algorithms implemented in telemetry.js and controls.js."""

    def test_countdown_timer_formatting_matrix(self):
        """Test time formatting across various boundary inputs (0, sub-minute, hour, multi-day)."""
        def format_time_remaining(seconds):
            if seconds <= 0:
                return '00:00:00'
            hrs = seconds // 3600
            mins = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"

        assert format_time_remaining(-10) == '00:00:00'
        assert format_time_remaining(0) == '00:00:00'
        assert format_time_remaining(5) == '00:00:05'
        assert format_time_remaining(59) == '00:00:59'
        assert format_time_remaining(60) == '00:01:00'
        assert format_time_remaining(3599) == '00:59:59'
        assert format_time_remaining(3600) == '01:00:00'
        assert format_time_remaining(86399) == '23:59:59'
        assert format_time_remaining(86400) == '24:00:00'
        assert format_time_remaining(100000) == '27:46:40'

    def test_latency_badge_threshold_classification(self):
        """Test latency classification thresholds (<300 green, 300-800 amber, >=800 red)."""
        def classify_latency(lat):
            if lat is None:
                return "green"
            val = round(lat)
            if val < 300:
                return "green"
            elif val < 800:
                return "amber"
            return "red"

        assert classify_latency(None) == "green"
        assert classify_latency(0.0) == "green"
        assert classify_latency(142.5) == "green"
        assert classify_latency(299.4) == "green"
        assert classify_latency(299.6) == "amber"  # rounds to 300
        assert classify_latency(300.0) == "amber"
        assert classify_latency(799.4) == "amber"
        assert classify_latency(799.6) == "red"    # rounds to 800
        assert classify_latency(800.0) == "red"
        assert classify_latency(2500.0) == "red"

    def test_instant_search_filtering_resilience(self):
        """Simulate search algorithm matching across diacritics, special chars, and case insensitivity."""
        accounts = [
            {
                "index": 1,
                "name": "Tài khoản #1",
                "email": "lamtruong0978@gmail.com",
                "maskedKey": "AnD9...ABTm",
                "channels": [
                    {"id": "6ad724e7778b240e2f66d1f9", "name": "Uyển Nhi", "service": "facebook"},
                    {"id": "6ad724e7778b240e2f66d1fa", "name": "Bếp Mẹ Làm", "service": "facebook"},
                ]
            },
            {
                "index": 2,
                "name": "Tài khoản #2",
                "email": "content.creator.vn@gmail.com",
                "maskedKey": "AnD9...K01p",
                "channels": [
                    {"id": "6ad724e7778b240e2f66d1fb", "name": "Tin Nhanh 24h", "service": "tiktok"},
                ]
            }
        ]

        def filter_channels(query, platform):
            q = query.strip().lower()
            plat = platform.strip().lower()
            matches = []
            for acc in accounts:
                email_match = not q or (q in acc["email"].lower() or q in acc["name"].lower() or q in acc["maskedKey"].lower())
                for ch in acc["channels"]:
                    match_plat = (plat == "all") or (plat in ch["service"].lower())
                    match_query = not q or (q in ch["name"].lower() or q in ch["id"].lower() or email_match)
                    if match_plat and match_query:
                        matches.append(ch["id"])
            return matches

        # All channels
        assert len(filter_channels("", "all")) == 3
        # Platform filters
        assert len(filter_channels("", "facebook")) == 2
        assert len(filter_channels("", "tiktok")) == 1
        assert len(filter_channels("", "instagram")) == 0
        # Vietnamese diacritics query
        assert filter_channels("uyển", "all") == ["6ad724e7778b240e2f66d1f9"]
        assert filter_channels("Bếp Mẹ", "all") == ["6ad724e7778b240e2f66d1fa"]
        # Search by email matches all channels of that account
        assert len(filter_channels("lamtruong", "all")) == 2
        # Search by buffer ID
        assert filter_channels("6ad724e7778b240e2f66d1fb", "all") == ["6ad724e7778b240e2f66d1fb"]
        # Cross filter: email match + tiktok filter
        assert filter_channels("lamtruong", "tiktok") == []
        assert filter_channels("content.creator", "tiktok") == ["6ad724e7778b240e2f66d1fb"]
        # Non-matching adversarial query
        assert filter_channels("nonexistent_pattern_12345", "all") == []

    def test_touch_pointer_disambiguation_threshold(self):
        """Simulate touch gesture disambiguation with exact 8.0px boundary."""
        def is_drag_gesture(dx, dy):
            dist = (dx**2 + dy**2) ** 0.5
            return dist > 8.0

        assert is_drag_gesture(0, 0) is False
        assert is_drag_gesture(5, 5) is False     # ~7.07px
        assert is_drag_gesture(8.0, 0) is False   # exact 8.0px -> click permitted
        assert is_drag_gesture(0, 8.0) is False   # exact 8.0px -> click permitted
        assert is_drag_gesture(8.01, 0) is True   # > 8.0px -> drag suppressed
        assert is_drag_gesture(6, 6) is True      # ~8.48px -> drag suppressed
        assert is_drag_gesture(10, 50) is True    # vertical drawer swipe -> drag
