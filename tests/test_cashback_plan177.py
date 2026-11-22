"""PLAN-177 Phase 1: degraded unquoted + deadline + flags (không live Shopee/ALT)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from cashback_bot.affiliate import is_valid_sub_id
from cashback_bot.config import load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import DEGRADED_UNQUOTED, STALE
from cashback_bot.product_data import ProductDataError
from cashback_bot.service import CashbackService
from tests.test_cashback_bot import FakeClient, payload, settings


NOW = datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc)


def repo(tmp_path) -> TrackingRepository:
    store = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    store.migrate()
    return store


def test_degraded_when_product_data_timeout(tmp_path):
    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=True),
        repo(tmp_path),
        FakeClient(error=ProductDataError("timeout")),
    )
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=17701, now=NOW)
    assert reply.text == DEGRADED_UNQUOTED
    assert reply.button_url
    query = parse_qs(urlparse(reply.button_url).query)
    assert is_valid_sub_id(query["sub_id"][0])
    assert query["origin_link"] == ["https://shopee.vn/product/9/8"]
    # Không bịa số hoàn / giá
    assert "Hoàn dự kiến" not in reply.text
    assert "14.000" not in reply.text
    assert "250.000" not in reply.text

    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    row = conn.execute(
        "SELECT link_status, estimated_commission, estimated_cashback, item_id, shop_id, sub_id FROM link_requests"
    ).fetchone()
    assert row[0] == "created"
    assert row[1] is None and row[2] is None
    assert row[3] == 8 and row[4] == 9
    snap = conn.execute("SELECT quote_source, quote_cashback_vnd FROM link_policy_snapshots").fetchone()
    assert snap is not None
    assert snap[0] == "degraded_unquoted"
    assert snap[1] is None


def test_rollback_flag_keeps_stale(tmp_path):
    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=False),
        repo(tmp_path),
        FakeClient(error=ProductDataError("timeout")),
    )
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=17702, now=NOW)
    assert reply.text == STALE
    assert reply.button_url is None


def test_stale_payload_degraded_no_fake_numbers(tmp_path):
    stale = payload(
        last_update="2026-10-05 02:50:09",
        warning="Using cached data - API fetch failed",
        price=145820,
        commission=8021,
        productName="Gối chữ U",
    )
    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=True),
        repo(tmp_path),
        FakeClient(stale),
    )
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=17703, now=NOW)
    assert reply.text == DEGRADED_UNQUOTED
    assert "8.021" not in reply.text
    assert "145.820" not in reply.text


def test_deadline_skips_short_when_expired(tmp_path, monkeypatch):
    calls = []

    def fake_shorten(*_a, **_k):
        calls.append("shorten")
        return "https://s.shopee.vn/SHORT"

    monkeypatch.setattr("cashback_bot.service.shorten_shopee_url", fake_shorten)
    # Deadline đã hết trước khi build URL phụ.
    clock = {"t": 1000.0}
    monkeypatch.setattr("cashback_bot.service.time.monotonic", lambda: clock["t"])

    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=True, product_quote_deadline_sec=20.0),
        repo(tmp_path),
        FakeClient(error=ProductDataError("transport")),
    )
    # handle_text set deadline = monotonic()+20 = 1020; bump clock past it before build.
    original = bot._degraded_unquoted_link

    def wrap(*args, **kwargs):
        clock["t"] = 1021.0
        return original(*args, **kwargs)

    monkeypatch.setattr(bot, "_degraded_unquoted_link", wrap)
    # Actually wrap inside: after resolve, expire before _build_affiliate_url
    def degraded(*args, **kwargs):
        # Call real but force deadline already passed by patching build
        kwargs = dict(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(bot, "_degraded_unquoted_link", original)

    # Simpler: call _build_affiliate_url with expired deadline
    url, source = bot._build_affiliate_url(
        "https://shopee.vn/product/9/8", "deadsub1", deadline=999.0, item_id=8,
    )
    assert "an_redir" in url
    assert source == "an_redir"
    assert calls == []


def test_deadline_budget_is_forwarded_and_expiry_skips_remaining_calls(tmp_path, monkeypatch):
    """Contract only; real delayed HTTP deadline checks live in Step 2.3 tests."""
    budget = 0.25
    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=True, product_quote_deadline_sec=budget,
                 alt_shopee_link_fallback=True),
        repo(tmp_path),
        FakeClient(error=ProductDataError("timeout")),
    )
    clock = {"t": 1000.0}
    monkeypatch.setattr("cashback_bot.service.time.monotonic", lambda: clock["t"])
    calls = []

    def slow_shorten(url, sub_id="AUTOSALE", timeout=6.0, *, deadline=None):
        calls.append((url, sub_id, timeout, deadline))
        assert deadline == 1000.0 + budget
        assert 0 < timeout <= deadline - clock["t"]
        clock["t"] = deadline  # The provider uses its entire allowed budget.
        return None

    class Unexpected:
        def create_short(self, *args, **kwargs):
            raise AssertionError("ALT must not run after the shared deadline")

        def sign_tracking_only(self, *args, **kwargs):
            raise AssertionError("AffiPad must not run after the shared deadline")

    bot.alt_shopee_link = bot.affipad = Unexpected()
    monkeypatch.setattr("cashback_bot.service.shorten_shopee_url", slow_shorten)
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=17704, now=NOW)
    assert reply.button_url and "an_redir" in reply.button_url
    assert len(calls) == 1
    assert calls[0][0] == "https://shopee.vn/product/9/8"
    assert clock["t"] == 1000.0 + budget


def test_alt_flag_default_off_and_mock_contract(tmp_path):
    cfg = load_settings(
        {
            "CASHBACK_BOT_TOKEN": "123:abc",
            "SHOPEE_AFFILIATE_ID": "17300001",
            "ADDLIVETAG_API_KEY": "k",
            "CASHBACK_RATE_PERCENT": "70",
            "PRODUCT_MAX_AGE_HOURS": "3",
            "CUSTOMER_ACCESS_ENABLED": "false",
            "CASHBACK_ALLOWED_TELEGRAM_IDS": "111",
        }
    )
    assert cfg.product_quote_allow_degraded is True
    assert cfg.alt_shopee_link_fallback is False

    class MockAlt:
        def __init__(self):
            self.calls = []

        def create_short(self, product_url, sub_id, *, timeout):
            self.calls.append((product_url, sub_id, timeout))
            return "https://s.shopee.vn/ALTMOCK"

    bot = CashbackService(
        settings(tmp_path, product_quote_allow_degraded=True, alt_shopee_link_fallback=True),
        repo(tmp_path),
        FakeClient(error=ProductDataError("http_error")),
    )
    mock = MockAlt()
    bot.alt_shopee_link = mock
    # Không có bridge trong pytest → fallback alt khi flag bật
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=17705, now=NOW)
    assert reply.button_url == "https://s.shopee.vn/ALTMOCK"
    assert mock.calls and mock.calls[0][0] == "https://shopee.vn/product/9/8"
