"""Browser fixtures for executive overview and customer pagination; no live network."""

import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

BUILD = Path("/tmp/toolsauto-ceo-ui-dist")
OUT = Path("/tmp/toolsauto-ceo-ui-proof")
PROOF = Path("reports/ui175/followup/proof.json")
OUT.mkdir(exist_ok=True)
calls, errors = [], []
broken_buffer = False
broken_growth = False
bots = ["cashbot_tg", "cashbot_zalo", "ai_store"]


def intercept(route):
    url = urlparse(route.request.url)
    path = url.path
    if path == "/api/admin/overview":
        if broken_buffer:
            route.fulfill(status=503, json={})
            return
        route.fulfill(json={"generated_at": 1, "channels": [], "jobs_24h": {}, "materials_7d": {},
                            "failed_jobs": {"count": 0, "latest": []},
                            "disk": {"free_gb": 10, "used_gb": 20, "total_gb": 30, "pct": 66,
                                     "label": "disk", "pause_below_gb": 2, "below_pause": False}})
        return
    if path == "/api/admin/executive":
        route.fulfill(json={"generated_at": "2026-11-17T15:00:00Z", "errors": {},
                            "cashback": {"orders": 4, "net_commission": 20000, "customer_share": 14000,
                                         "reserve": 1000, "margin": 5000, "period": "7 ngày"},
                            "store": {"orders": 3, "revenue": 100000, "cost": 60000, "profit": 40000,
                                      "pending_orders": 1, "pending_topups": 2, "period": "7 ngày lịch VN"},
                            "studio": {"projects": {"REVIEW": 3}, "tasks": {"QUEUED": 5}},
                            "threads": {"counts": {"posted": 50}, "period": "Từ đầu"}})
        return
    if path == "/api/admin/processes":
        route.fulfill(json={"apps": [{"name": "Web_Dashboard", "label": "Web", "status": "online"},
                                      {"name": "DB_Backup", "label": "Sao lưu DB", "status": "stopped"}],
                            "services": [], "error": None, "services_error": None})
        return
    if path == "/bot-users/api/report":
        qs = parse_qs(url.query)
        summary = qs.get("summary_only", ["false"])[0] == "true"
        per = int(qs.get("per_page", ["25"])[0])
        page = int(qs.get("page", ["1"])[0])
        filtered = bool(qs.get("q") or qs.get("bot"))
        count = 1 if filtered else 30
        calls.append({"summary_only": summary, "page": page, "filtered": filtered})
        people = [{"bot": "cashbot_tg", "user_id": i, "name": f"Khach {i}", "joined_at": None,
                   "last_seen_at": None, "last_used_at": None, "source": "tu vao", "uses": 0, "orders": 0,
                   "active": False, "balance": None, "spent": None} for i in range(1, count + 1)]
        route.fulfill(json={"generated_at": "2026-11-17", "active_days": 7,
                            "bots": [{"bot": bot, "label": bot, "total": 100, "new_24h": 2, "new_7d": 10,
                                      "active_7d": 30, "buyers": 5, "available": not broken_growth} for bot in bots],
                            "total": {"bot": "all", "label": "Tong", "total": 300, "new_24h": 6,
                                      "new_7d": 30, "active_7d": 90, "buyers": 15},
                            "days": [], "sources": {bot: [] for bot in bots}, "matched": count,
                            "page": page, "per_page": per, "total_pages": 1 if filtered else 2,
                            "people": [] if summary else people[(page - 1) * per : page * per],
                            "errors": ["Cashbot: không đọc được DB"] if broken_growth else []})
        return
    file = BUILD / path.removeprefix("/static/admin/") if path.startswith("/static/admin/") else BUILD / "index.html"
    if file.is_file() and (path.startswith("/static/admin/") or path.startswith("/app")):
        route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream")
    else:
        route.abort()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", intercept)
        page.goto("http://ui.local/app", wait_until="networkidle")
        for title in ["Kết quả kinh doanh & hàng việc", "Sức khỏe dịch vụ", "Tăng trưởng theo bot", "Vận hành nội dung · Buffer"]:
            page.get_by_role("heading", name=title, exact=True).wait_for()
        assert page.get_by_text("Cần xem:", exact=False).count() == 0
        assert page.get_by_text("1/1", exact=True).is_visible()
        widths = [320, 390, 768, 1440]
        for width in widths:
            page.set_viewport_size({"width": width, "height": 844})
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), width
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(OUT / "overview.png"), full_page=True)
        page.goto("http://ui.local/app/go/bot-users", wait_until="networkidle")
        page.locator("a:visible").filter(has_text="Khach 1").first.wait_for()
        page.get_by_role("button", name="Sau", exact=True).first.click()
        page.locator("a:visible").filter(has_text="Khach 26").first.wait_for()
        assert calls[-1]["page"] == 2
        page.get_by_placeholder("Tên, @username, ID hoặc mã nguồn").fill("Khach 1")
        page.get_by_placeholder("Tên, @username, ID hoặc mã nguồn").press("Enter")
        page.get_by_text("1–1 / 1 khách khớp", exact=True).wait_for()
        assert calls[-1]["page"] == 1 and calls[-1]["filtered"]
        assert page.get_by_role("button", name="Sau", exact=True).first.is_disabled()
        broken_buffer = True
        broken_growth = True
        page.goto("http://ui.local/app", wait_until="networkidle")
        page.get_by_text("Chưa đọc được dữ liệu bot này.").first.wait_for()
        assert page.get_by_text("Cashback · kết quả 7 ngày →", exact=True).is_visible()
        assert page.get_by_role("heading", name="Sức khỏe dịch vụ").is_visible()
        assert not errors, errors
        proof = {"status": "PASS", "widths": widths, "bot_next_page": 2, "search_resets_page": True,
                 "summary_only_requested": any(call["summary_only"] for call in calls),
                 "buffer_failure_isolated": True, "missing_bot_not_shown_as_zero": True,
                 "scheduled_backup_not_alerted": True, "page_errors": errors}
        (OUT / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
        PROOF.write_text(json.dumps(proof, indent=2) + "\n")
        print(json.dumps(proof))
    finally:
        browser.close()
