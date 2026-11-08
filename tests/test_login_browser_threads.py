"""Script đăng nhập Threads không được coi trang xác minh là đã đăng nhập (07/11 checkpoint @us28qt)."""
from __future__ import annotations

import pytest

from app.scripts.login_browser import threads_checkpoint, threads_login_ok

CHALLENGE = "https://www.threads.com/auth_platform/challengepicker/?apc=abc"


@pytest.mark.parametrize("url", [
    CHALLENGE,
    "https://www.threads.com/login",
    "https://www.threads.com/checkpoint/123",
    "https://www.instagram.com/challenge/xyz",
])
def test_challenge_or_login_page_is_not_logged_in(url):
    assert threads_login_ok(url, has_session=True) is False


def test_home_with_session_is_logged_in():
    assert threads_login_ok("https://www.threads.com/", has_session=True) is True
    assert threads_login_ok("https://www.threads.com/@us28qt", has_session=True) is True


def test_home_without_session_is_not_logged_in():
    assert threads_login_ok("https://www.threads.com/", has_session=False) is False


def test_checkpoint_detection():
    assert threads_checkpoint(CHALLENGE) is True
    assert threads_checkpoint("https://www.threads.com/") is False


def test_parse_cookie_export_keeps_only_threads_instagram():
    import json

    from app.scripts.import_threads_cookies import parse_cookie_export

    raw = json.dumps([
        {"name": "sessionid", "value": "s", "domain": ".threads.com", "path": "/", "secure": True,
         "httpOnly": True, "sameSite": "no_restriction", "expirationDate": 1900000000},
        {"name": "csrftoken", "value": "c", "domain": ".instagram.com", "sameSite": "lax", "session": True},
        {"name": "SPC_EC", "value": "x", "domain": ".shopee.vn"},
        {"name": "bad"},
    ])
    out = parse_cookie_export(raw)
    assert [c["name"] for c in out] == ["sessionid", "csrftoken"]
    assert out[0]["sameSite"] == "None" and out[0]["secure"] and out[0]["expires"] == 1900000000
    assert "expires" not in out[1] and out[1]["sameSite"] == "Lax"
    assert parse_cookie_export(json.dumps({"cookies": raw and json.loads(raw)}))[0]["name"] == "sessionid"
