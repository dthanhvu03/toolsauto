"""Native bridge contract tests: real scrubbed quotes plus local-only transport."""

from __future__ import annotations

import copy
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from cashback_bot.native_shopee_quote import (
    MAX_RESPONSE_BYTES,
    NativeProductQuote,
    NativeQuoteError,
    NativeShopeeQuoteClient,
    _http_get,
    native_quote_from_payload,
    parse_percent,
)
from cashback_bot.product_data import ProductQuote
from cashback_bot.shopee_url import ShopeeTarget

NOW = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)
FIXTURES = json.loads((Path(__file__).parent / "fixtures/native_shopee_quote_poc.json").read_text())["samples"]


def payload(**changes):
    result = copy.deepcopy(FIXTURES[0]["dto"])
    result["quote"].update(fetched_at=NOW.isoformat(), **changes)
    return result


def target(data=None):
    row = (data or payload())["quote"]
    shop, item = int(row["shop_id"]), int(row["item_id"])
    return ShopeeTarget(f"https://shopee.vn/product/{shop}/{item}", item, shop, None)


def parse(data):
    return native_quote_from_payload(data, target(), now=NOW)


@pytest.mark.parametrize("sample", FIXTURES, ids=lambda x: x["label"])
def test_real_poc_exact_price_split_and_sure(sample):
    data = sample["dto"]
    instant = datetime.fromisoformat(data["quote"]["fetched_at"].replace("Z", "+00:00"))
    quote = native_quote_from_payload(data, target(data), now=instant)
    assert isinstance(quote, ProductQuote)
    assert isinstance(quote, NativeProductQuote)
    assert quote.price_vnd == sample["expected_price_vnd"]
    assert quote.sure_commission_vnd == sample["expected_sure_vnd"]
    assert quote.is_xtra is sample["is_xtra"]
    assert quote.last_update is None
    assert quote.fetched_at == instant
    assert quote.quote_source == quote.data_source == "native_shopee"
    assert quote.product_url == target(data).original_url


def test_five_real_samples_disprove_default_as_total():
    assert sum(row["default_as_total"] > row["expected_sure_vnd"] for row in FIXTURES) == 5


@pytest.mark.parametrize("value,expected", [("4,5%", Decimal("4.5")), ("0%", Decimal(0)),
                                              (" 17.01% ", Decimal("17.01")), ("7.001%", Decimal("7.001"))])
def test_percent_parse_preserves_decimal(value, expected):
    assert parse_percent(value) == expected


@pytest.mark.parametrize("value", [None, "", True, 7, float("nan"), "NaN%", "Infinity%", "-1%",
                                   "101%", "7", "7%junk", "7,0.1%", "７%"])
def test_invalid_percent_is_missing_not_zero(value):
    assert parse_percent(value) is None


@pytest.mark.parametrize("key,value", [
    ("schema_version", True), ("schema_version", 2), ("source", "product_data"),
    ("context", "facebook_reels"), ("currency", "USD"), ("status", True), ("status", 0),
    ("item_status", "deleted"), ("name", ""), ("name", "a" * 301), ("name", "bad\nname"),
    ("seller_rate_raw", None), ("seller_rate_raw", ""), ("seller_rate_raw", True),
    ("platform_rate_raw", "NaN"), ("platform_rate_raw", "-1"), ("platform_rate_raw", "100001"),
    ("platform_cap_raw", "0"), ("platform_cap_raw", ""), ("platform_cap_raw", None),
    ("price_raw", 1), ("price_min_raw", "0"), ("price_max_raw", "1"),
    ("price_raw", "9" * 25), ("fetched_at", "2026-11-19T10:00:00"),
    ("fetched_at", "invalid"), ("fetched_at", None),
    ("period_start_time", True), ("period_end_time", "32503651199"),
])
def test_invalid_metadata_or_missing_numeric_fails_closed(key, value):
    data = payload()
    data["quote"][key] = value
    with pytest.raises(NativeQuoteError):
        parse(data)


@pytest.mark.parametrize("key", ["shop_id", "item_id", "requested_shop_id", "requested_item_id"])
def test_every_actual_and_requested_identity_must_match(key):
    data = payload()
    data["quote"][key] = "123"
    with pytest.raises(NativeQuoteError, match="identity_mismatch"):
        parse(data)


@pytest.mark.parametrize("shop,item", [(True, 1), (1, True), (None, None), (0, 1), (1, -2)])
def test_unresolved_or_invalid_input_identity_rejected(shop, item):
    with pytest.raises(NativeQuoteError):
        native_quote_from_payload(payload(), ShopeeTarget("unused", item, shop, None), now=NOW)


@pytest.mark.parametrize("age", [61, -6])
def test_fetched_age_bounds_do_not_forge_source_update(age):
    data = payload()
    data["quote"]["fetched_at"] = (NOW - timedelta(seconds=age)).isoformat()
    with pytest.raises(NativeQuoteError, match="stale_retrieval"):
        parse(data)


@pytest.mark.parametrize("start,end", [(0, 0), (0, 1), (1795082401, 32503651199), (1, 2)])
def test_positive_seller_requires_active_campaign(start, end):
    with pytest.raises(NativeQuoteError, match="inactive_offer"):
        parse(payload(period_start_time=start, period_end_time=end))


def test_explicit_zero_seller_and_zero_campaign_period_are_valid():
    quote = parse(payload(seller_rate_raw="0", platform_rate_raw="0", period_start_time=0, period_end_time=0))
    assert quote.sure_commission_vnd == quote.commission_vnd == 0
    assert quote.seller_commission_vnd == quote.shopee_commission_vnd == 0
    assert quote.is_xtra is False


def test_captured_nonxtra_historical_start_and_no_end_denotes_no_seller_campaign():
    quote = parse(payload(seller_rate_raw="0", period_start_time=1793466000, period_end_time=0))
    assert quote.is_xtra is False
    assert quote.seller_commission_vnd == 0


def test_identity_above_sqlite_integer_range_is_rejected_before_lookup():
    oversized = 1 << 63
    with pytest.raises(NativeQuoteError, match="invalid_identity"):
        native_quote_from_payload(payload(), ShopeeTarget("unused", oversized, oversized, None), now=NOW)


@pytest.mark.parametrize("key", ["price_max_raw", "platform_cap_raw"])
def test_raw_money_cannot_overflow_sqlite_vnd_columns(key):
    data = payload()
    data["quote"][key] = str((1 << 63) * 100000)
    with pytest.raises(NativeQuoteError):
        parse(data)


def test_absolute_cap_applies_before_existing_conservative_policy():
    quote = parse(payload(price_raw="200000000000", price_min_raw="200000000000", price_max_raw="200000000000",
                          seller_rate_raw="7000", platform_rate_raw="7000", platform_cap_raw="4000000000"))
    assert quote.seller_commission_vnd == 140_000
    assert quote.shopee_commission_vnd == 40_000
    assert quote.commission_vnd == quote.sure_commission_vnd == 180_000
    assert quote.is_capped is True


def test_component_rounding_and_beyond_bps_precision_are_not_float_rounded():
    quote = parse(payload(price_raw="9900000", price_min_raw="9900000", price_max_raw="9900000",
                          seller_rate_raw="7001", platform_rate_raw="2500"))
    assert quote.seller_commission_vnd == 6
    assert quote.shopee_commission_vnd == 2
    assert quote.sure_commission_vnd == 8
    assert quote.commission_rate_bps is None


def test_variant_minimum_is_explicit_and_keeps_range_metadata():
    quote = parse(payload(price_raw="20000000000", price_min_raw="10000000000", price_max_raw="30000000000"))
    assert quote.price_vnd == quote.price_min_vnd == 100_000
    assert quote.price_max_vnd == 300_000
    assert quote.price_basis == "variant_min"
    assert quote.commission_vnd == 9_500


def test_client_uses_resolved_bridge_host_and_remaining_budget(monkeypatch):
    calls = []
    monkeypatch.setattr("cashback_bot.native_shopee_quote.get_bridge_url", lambda: "http://192.168.112.1:9224")

    def transport(url, deadline, limit):
        calls.append((url, deadline, limit))
        return 200, json.dumps(payload()).encode()

    client = NativeShopeeQuoteClient(transport=transport)
    end = time.monotonic() + 0.5
    assert client.fetch_quote(target(), now=NOW, deadline=end).sure_commission_vnd == 128_630
    url, call_end, limit = calls[0]
    assert urlsplit(url).netloc == "192.168.112.1:9224"
    query = parse_qs(urlsplit(url).query)
    assert query["shop_id"] == [str(target().shop_id)]
    assert query["item_id"] == [str(target().item_id)]
    assert 1 <= int(query["timeout_ms"][0]) <= 500
    assert call_end <= end
    assert limit == MAX_RESPONSE_BYTES


def test_native_live_is_disabled_in_pytest_without_explicit_transport(monkeypatch):
    monkeypatch.delenv("SHOPEE_NATIVE_QUOTE_LIVE", raising=False)
    with pytest.raises(NativeQuoteError, match="test_no_live"):
        NativeShopeeQuoteClient().fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)


def test_transport_error_is_redacted_and_circuit_is_thread_safe():
    calls = []

    def broken(*args):
        calls.append(1)
        raise RuntimeError("secret-cookie-and-raw-response")

    client = NativeShopeeQuoteClient(transport=broken)
    with pytest.raises(NativeQuoteError, match="transport") as caught:
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    assert "secret" not in repr(caught.value)
    assert caught.value.__suppress_context__ is True
    with pytest.raises(NativeQuoteError, match="circuit_open"):
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    assert calls == [1]


def test_invalid_bridge_schema_opens_circuit_without_repeating_network():
    calls = []

    def malformed(*args):
        calls.append(1)
        data = payload(schema_version=2)
        return 200, json.dumps(data).encode()

    client = NativeShopeeQuoteClient(transport=malformed)
    with pytest.raises(NativeQuoteError, match="unsupported_schema"):
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    with pytest.raises(NativeQuoteError, match="circuit_open"):
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    assert calls == [1]


def test_concurrent_failures_make_one_call_then_share_cooldown():
    calls = []
    errors = []

    def broken(*args):
        calls.append(1)
        time.sleep(0.02)
        raise RuntimeError("private upstream payload")

    client = NativeShopeeQuoteClient(transport=broken)

    def worker():
        try:
            client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
        except NativeQuoteError as exc:
            errors.append(exc.code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1)
    assert len(calls) == 1
    assert sorted(errors) == ["circuit_open"] * 7 + ["transport"]


def test_circuit_recovers_after_cooldown_without_background_retry():
    calls = []

    def changing(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("private")
        return 200, json.dumps(payload()).encode()

    client = NativeShopeeQuoteClient(transport=changing, cooldown_seconds=0.01)
    with pytest.raises(NativeQuoteError, match="transport"):
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    time.sleep(0.02)
    assert calls == [1]
    assert client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1).sure_commission_vnd == 128_630
    assert calls == [1, 1]


@pytest.mark.parametrize("status,body,code", [(302, b"secret", "bridge_http_error"),
                                              (200, b"{secret invalid", "invalid_json"),
                                              (200, b"x" * (MAX_RESPONSE_BYTES + 1), "response_too_large")])
def test_unsafe_http_and_response_failures_are_safe(status, body, code):
    client = NativeShopeeQuoteClient(transport=lambda *_: (status, body))
    with pytest.raises(NativeQuoteError, match=code) as caught:
        client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1)
    assert "secret" not in str(caught.value)


def test_waiting_for_client_lock_consumes_deadline():
    client = NativeShopeeQuoteClient(transport=lambda *_: pytest.fail("should not start HTTP"))
    client._lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(NativeQuoteError, match="timeout"):
            client.fetch_quote(target(), now=NOW, deadline=started + 0.08)
        assert time.monotonic() - started < 0.18
    finally:
        client._lock.release()


@pytest.fixture
def local_bridge():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # HTTPConnection clears .sock on these responses.

        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            try:
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/ok")
                    self.end_headers()
                    return
                if self.path.startswith("/slowheaders"):
                    self.wfile.write(b"HTTP/1.0 200 OK\r\nX-Slow: ")
                    self.wfile.flush()
                    for _ in range(100):
                        self.wfile.write(b"a")
                        self.wfile.flush()
                        time.sleep(0.02)
                    return
                self.send_response(200)
                if self.path.startswith("/oversize"):
                    self.send_header("Content-Length", str(MAX_RESPONSE_BYTES + 1))
                    self.end_headers()
                    return
                if self.path.startswith("/trickle"):
                    self.send_header("Content-Length", "200")
                    self.end_headers()
                    for _ in range(200):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.02)
                    return
                body = json.dumps(payload()).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


@pytest.mark.parametrize("path", ["/slowheaders", "/trickle"])
def test_real_http_total_deadline_bounds_slow_headers_and_body(local_bridge, path):
    base, _ = local_bridge
    started = time.monotonic()
    with pytest.raises(NativeQuoteError, match="timeout"):
        _http_get(base + path, started + 0.15, MAX_RESPONSE_BYTES)
    assert time.monotonic() - started < 0.3


def test_real_http_redirect_is_not_followed_and_oversize_is_rejected(local_bridge):
    base, calls = local_bridge
    assert _http_get(base + "/redirect", time.monotonic() + 1, MAX_RESPONSE_BYTES) == (302, b"")
    assert calls == ["/redirect"]
    with pytest.raises(NativeQuoteError, match="response_too_large"):
        _http_get(base + "/oversize", time.monotonic() + 1, MAX_RESPONSE_BYTES)


def test_client_parses_actual_local_http_response(monkeypatch, local_bridge):
    base, _ = local_bridge
    monkeypatch.setattr("cashback_bot.native_shopee_quote.get_bridge_url", lambda: base)
    client = NativeShopeeQuoteClient(transport=_http_get)
    assert client.fetch_quote(target(), now=NOW, deadline=time.monotonic() + 1).sure_commission_vnd == 128_630


def test_full_client_actual_http_deadline_bounds_trickled_response(local_bridge):
    base, _ = local_bridge
    client = NativeShopeeQuoteClient(transport=lambda _url, end, limit: _http_get(base + "/trickle", end, limit))
    started = time.monotonic()
    with pytest.raises(NativeQuoteError, match="timeout"):
        client.fetch_quote(target(), now=NOW, deadline=started + 0.15)
    assert time.monotonic() - started < 0.3


@pytest.mark.parametrize("base", ["https://127.0.0.1/", "http://8.8.8.8/", "http://user:secret@127.0.0.1/",
                                    "http://0.0.0.0/", "http://untrusted.test/"])
def test_transport_accepts_only_configured_numeric_local_http_bridge(base):
    with pytest.raises(NativeQuoteError, match="invalid_bridge_url") as caught:
        _http_get(base, time.monotonic() + 1, MAX_RESPONSE_BYTES)
    assert "secret" not in repr(caught.value)
