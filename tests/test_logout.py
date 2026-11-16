"""Đăng xuất: nút giao diện mới (GET /logout) và nút Classic (POST), kể cả khi phiên đã hết hạn."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_logout_clears_cookie_and_redirects_to_login():
    client.cookies.set("session_token", "anything")
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    assert 'session_token=""' in resp.headers["set-cookie"] and "Max-Age=0" in resp.headers["set-cookie"]


def test_post_logout_works_without_valid_session():
    client.cookies.clear()
    resp = client.post("/logout", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "redirect": "/login"}


def test_other_pages_still_require_login():
    client.cookies.clear()
    assert client.post("/logoutx").status_code == 401
    assert client.get("/app", headers={"Accept": "text/html"}, follow_redirects=False).status_code in (302, 307)
