"""Authenticated read-only dashboard smoke; saves no customer data or credentials."""

import hashlib
import json
import random
import socket
import subprocess
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import sync_playwright

from app import config

BASE = "http://127.0.0.1:8000"
OUT = Path("reports/ui175/followup/live-proof.json")
proof = {"checked_at": datetime.now(timezone.utc).isoformat(), "http": {}, "widths": [], "page_errors": [], "blocked_requests": []}


def safe_route(route):
    parsed = urlparse(route.request.url)
    if parsed.hostname != "127.0.0.1" or (route.request.method != "GET" and parsed.path != "/login"):
        proof["blocked_requests"].append({"method": route.request.method, "path": parsed.path})
        route.abort()
    else:
        route.continue_()


class CustomerLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.in_customer_list = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "ul" and values.get("aria-label") == "Khách Cashback":
            self.in_customer_list = True
        if self.in_customer_list and tag == "a" and values.get("href", "").startswith("/cashback/users/"):
            self.count += 1

    def handle_endtag(self, tag):
        if tag == "ul" and self.in_customer_list:
            self.in_customer_list = False


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        context = browser.new_context()
        login = context.request.post(f"{BASE}/login", form={"username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD})
        proof["login_status"] = login.status
        assert login.status == 200
        for path in ["/health", "/app", "/cashback/users?page=1", "/api/admin/executive", "/api/admin/processes", "/bot-users/api/report?summary_only=true"]:
            response = context.request.get(f"{BASE}{path}")
            proof["http"][path] = response.status
            assert response.status == 200, path
            if path == "/api/admin/executive":
                data = response.json()
                proof["executive_sources"] = {key: data.get(key) is not None for key in ["cashback", "store", "studio", "threads"]}
                proof["executive_errors"] = sorted(data["errors"])
                assert all(proof["executive_sources"].values()) and not data["errors"]
            if path.startswith("/bot-users"):
                assert response.json()["people"] == []
        customer_page = context.request.get(f"{BASE}/bot-users/api/report")
        customer_data = customer_page.json()
        proof["bot_customer_page"] = {"returned": len(customer_data["people"]), "page": customer_data["page"], "per_page": customer_data["per_page"]}
        assert customer_page.status == 200 and len(customer_data["people"]) <= 25 and customer_data["page"] == 1

        expected = hashlib.sha256(Path("/tmp/toolsauto-ceo-ui-dist/index.html").read_bytes()).hexdigest()
        shell = context.request.get(f"{BASE}/app").body()
        assert hashlib.sha256(shell).hexdigest() == expected
        proof["index_sha256"] = expected
        page = context.new_page()
        page.on("pageerror", lambda error: proof["page_errors"].append(type(error).__name__))
        page.route("**/*", safe_route)
        for path in ["/app", "/app/go/bot-users"]:
            page.goto(f"{BASE}{path}", wait_until="networkidle")
            if path == "/app":
                page.get_by_role("heading", name="Kết quả kinh doanh & hàng việc", exact=True).wait_for()
                page.get_by_text("Cashback · kết quả 7 ngày →", exact=True).wait_for()
            else:
                page.get_by_role("button", name="Sau", exact=True).first.wait_for()
            for width in [320, 390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 844})
                time.sleep(random.uniform(0.1, 0.2))
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), (path, width)
                proof["widths"].append({"path": path, "width": width, "overflow": False})
        cashback_html = context.request.get(f"{BASE}/cashback/users?page=1").text()
        counter = CustomerLinks()
        counter.feed(cashback_html)
        proof["cashback_customer_page"] = {"returned": counter.count, "max_per_page": 50}
        assert counter.count <= 50
        assert not proof["page_errors"] and not proof["blocked_requests"]
    finally:
        browser.close()

apps = json.loads(subprocess.run(["pm2", "jlist"], capture_output=True, text=True, check=True).stdout)
web = next(row for row in apps if row["name"] == "Web_Dashboard")
proof["dashboard"] = {"status": web["pm2_env"]["status"], "restarts": web["pm2_env"]["restart_time"]}
assert proof["dashboard"]["status"] == "online"
tailnet_host = "laptop-t2hf25cd.tail15ebd5.ts.net"
tailnet_ip = "100.102.93.11"
original_getaddrinfo = socket.getaddrinfo


def resolve_tailnet(host, *args, **kwargs):
    return original_getaddrinfo(tailnet_ip if host == tailnet_host else host, *args, **kwargs)


socket.getaddrinfo = resolve_tailnet
try:
    opener = build_opener(ProxyHandler({}))
    tailnet_base = f"https://{tailnet_host}:8443"
    login_request = Request(f"{tailnet_base}/login", data=urlencode({
        "username": config.ADMIN_USERNAME, "password": config.ADMIN_PASSWORD,
    }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    with opener.open(login_request, timeout=15) as response:
        tailnet_login = response.status
        cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
    assert tailnet_login == 200 and cookie.startswith("session_token=")
    executive_request = Request(f"{tailnet_base}/api/admin/executive", headers={"Cookie": cookie})
    with opener.open(executive_request, timeout=20) as response:
        tailnet_executive = json.load(response)
        tailnet_status = response.status
    assert tailnet_status == 200 and not tailnet_executive["errors"]
    proof["tailnet"] = {"login": tailnet_login, "executive": tailnet_status, "tls_verified": True}
finally:
    socket.getaddrinfo = original_getaddrinfo
proof["status"] = "PASS"
OUT.write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof))
