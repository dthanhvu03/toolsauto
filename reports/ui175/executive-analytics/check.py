"""Offline browser proof for PLAN-175 analytics. All URLs are fulfilled or blocked."""
import json
import mimetypes
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

BUILD = Path("/tmp/toolsauto-executive-analytics-dist")
OUT = Path(__file__).resolve().parent
PROOF = {"widths": [320, 390, 768, 1440], "requests": [], "page_errors": [], "unexpected": [], "checks": []}
mode = "normal"


def fixture(days):
    last = date(2026, 11, 18)
    points = []
    for index in range(7 if days == 7 else 5):
        day = last - timedelta(days=((6-index) if days == 7 else (4-index)*7))
        points.append({"day": day.isoformat(), "label": day.isoformat() if days == 7 else f"{day-timedelta(days=6)} – {day}",
                       "revenue": 100000 + index*25000, "net_profit": -20000 if index == 0 else 7000+index*3000})
    products = [{"name": "Canva Pro gói cá nhân với mô tả dài và chữliền"*2, "sold": 25, "revenue": 120000, "gross_profit": 18000},
                {"name": "API AI", "sold": 4, "revenue": 80000, "gross_profit": -2000}]
    return {"generated_at": "2026-11-18T01:00:00Z", "errors": {},
            "store": {"orders": 29, "revenue": 200000, "cost": 160000, "profit": 30000, "external_expense": 10000,
                      "pending_orders": 1, "pending_topups": 2, "period": f"{days} ngày lịch Việt Nam",
                      "trend": points, "top_sellers": products, "top_profit": products,
                      "money_position": {"customer_wallet": 950000, "capital_recorded": 2000000, "capital_used": 500000, "waiting_order_cost": 70000}},
            "cashback": {"orders": 9, "net_commission": 60000, "customer_share": 30000, "reserve": 5000, "margin": 25000,
                         "period": f"{days} ngày lịch Việt Nam", "trend": [{"day": p["day"], "label": p["label"], "net_commission": p["revenue"]//10, "margin": p["net_profit"]//10} for p in points],
                         "money_position": {"settled_owner_received": 80000, "upcoming_owner": None, "upcoming_owner_known": False,
                                            "customer_waiting": 30000, "customer_wallet": 45000, "payout_reserved": 15000,
                                            "payout_paid": 70000, "fund_available": None, "fund_verified": False, "open_adjustments": 1}},
            "studio": {"projects": {"REVIEW": 3}, "tasks": {"QUEUED": 4}}, "threads": {"counts": {"posted": 55}, "period": "Từ đầu"}}


def intercept(route):
    url = urlparse(route.request.url)
    path = url.path
    if route.request.method != "GET":
        PROOF["unexpected"].append(route.request.method + " " + path)
        route.abort()
        return
    if path == "/api/admin/executive":
        days = int(parse_qs(url.query).get("days", ["7"])[0])
        PROOF["requests"].append({"days": days, "mode": mode})
        data = fixture(days)
        if mode == "unavailable":
            data["store"] = None
            data["errors"]["store"] = "Chưa đọc được nguồn dữ liệu"
        if mode == "empty":
            data["store"]["trend"] = []
            data["store"]["top_sellers"] = []
            data["store"]["top_profit"] = []
            data["cashback"]["trend"] = []
        if mode == "zeros":
            for key in ("store", "cashback"):
                for point in data[key]["trend"]:
                    for field in tuple(point):
                        if field not in ("day", "label"):
                            point[field] = 0
        if mode == "legacy":
            for key in ("store", "cashback"):
                data[key].pop("trend")
                data[key].pop("money_position")
        if mode == "http_error":
            route.fulfill(status=503, json={"detail": "Unavailable"})
        else:
            route.fulfill(json=data)
        return
    if path == "/api/admin/overview":
        route.fulfill(json={"generated_at": 1, "channels": [], "jobs_24h": {}, "materials_7d": {},
                            "failed_jobs": {"count": 0, "latest": []}, "disk": {"free_gb": 10, "used_gb": 2, "total_gb": 12,
                            "pause_below_gb": 2, "below_pause": False}})
        return
    if path == "/api/admin/processes":
        route.fulfill(json={"apps": [{"name": "Web_Dashboard", "label": "Web", "status": "online"}], "services": [], "error": None, "services_error": None})
        return
    if path == "/bot-users/api/report":
        route.fulfill(json={"bots": [], "errors": []})
        return
    file = BUILD / path.removeprefix("/static/admin/") if path.startswith("/static/admin/") else BUILD / "index.html"
    if url.hostname == "executive.local" and file.is_file() and (path.startswith("/static/admin/") or path == "/app"):
        route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream")
    else:
        PROOF["unexpected"].append(path)
        route.abort()


def layout(page):
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), page.viewport_size
    for svg in page.locator("[data-chart] svg").all():
        geometry = svg.evaluate("""node => ({width:node.getBoundingClientRect().width, height:node.getBoundingClientRect().height,
            viewWidth:node.viewBox.baseVal.width, circles:[...node.querySelectorAll('circle')].map(c=>Number(c.getAttribute('cy')))})""")
        assert abs(geometry["width"] - geometry["viewWidth"]) < 2, geometry
        assert all(0 <= cy <= geometry["height"] for cy in geometry["circles"]), geometry


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: PROOF["page_errors"].append(str(error)))
        page.route("**/*", intercept)
        for days in (7, 30):
            for width in PROOF["widths"]:
                page.set_viewport_size({"width": width, "height": 844})
                page.goto("http://executive.local/app", wait_until="networkidle")
                page.get_by_role("button", name=f"{days} ngày", exact=True).click()
                page.get_by_role("heading", name=f"AI Pass Store · {days} ngày", exact=True).wait_for()
                page.get_by_role("heading", name="Top 5 món bán nhiều", exact=True).wait_for()
                page.wait_for_timeout(100)
                layout(page)
                assert page.get_by_text("Chưa xác minh", exact=True).count() >= 2
                selects = page.locator("[data-chart] select")
                assert selects.count() == 2
                first = fixture(days)["store"]["trend"][0]
                selects.first.select_option(first["day"])
                assert page.locator("[data-chart]").first.get_by_text("-20.000đ", exact=True).is_visible()
                PROOF["checks"].append({"days": days, "width": width, "geometry": "PASS", "negative_point": "PASS"})
                if width in (390, 1440) and days == 7:
                    page.screenshot(path=str(OUT / f"overview-{width}.png"), full_page=True)
        for scenario in ("empty", "zeros", "unavailable", "legacy", "http_error"):
            mode = scenario
            page.set_viewport_size({"width": 320, "height": 844})
            page.goto("http://executive.local/app", wait_until="networkidle")
            if scenario == "empty":
                page.get_by_text("Chưa có dữ liệu trong kỳ.", exact=True).first.wait_for()
            elif scenario == "zeros":
                page.get_by_text("Chưa ghi nhận giá trị trong kỳ này.", exact=True).first.wait_for()
            elif scenario == "unavailable":
                page.get_by_text("Chưa đọc được nguồn dữ liệu", exact=True).wait_for()
                page.get_by_role("heading", name="Tiền Cashback hiện tại", exact=True).wait_for()
            elif scenario == "legacy":
                page.get_by_text("Dữ liệu biểu đồ chưa khả dụng.", exact=True).first.wait_for()
            else:
                page.get_by_role("alert").wait_for(timeout=20000)
            layout(page)
            PROOF["checks"].append({"scenario": scenario, "width": 320, "result": "PASS"})
        assert not PROOF["page_errors"] and not PROOF["unexpected"], PROOF
        PROOF["status"] = "PASS"
        (OUT / "proof.json").write_text(json.dumps(PROOF, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(PROOF, ensure_ascii=False))
    finally:
        browser.close()
