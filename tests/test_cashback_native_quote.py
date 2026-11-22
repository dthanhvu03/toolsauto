"""PLAN-177 Step2.3: opt-in native ladder and actual local I/O deadlines."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from cashback_bot import shopee_shortener, terms
from cashback_bot.affipad import AffiPadClient, is_meta_signed, meta_channel
from cashback_bot.alt_shopee_link import HttpAltShopeeLinkClient
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.deadline_http import DeadlineHttpError, request_bytes
from cashback_bot.messages import DEGRADED_UNQUOTED
from cashback_bot.native_shopee_quote import NativeQuoteError, native_quote_from_payload
from cashback_bot.product_data import ProductDataClient, ProductDataError
from cashback_bot.service import CashbackService
from cashback_bot.shopee_resolve import ResolveError, ResolvedProduct
from cashback_bot.shopee_url import ShopeeTarget
from tests.test_cashback_bot import NOW, FakeClient, payload, repo, settings

URL = "https://shopee.vn/product/9/8"
TARGET = ShopeeTarget(URL, 8, 9, None)


def native_dto(**changes):
    quote = {
        "schema_version": 1, "source": "native_shopee", "context": "social_media_shop_existing",
        "requested_shop_id": "9", "requested_item_id": "8", "shop_id": "9", "item_id": "8",
        "name": "Native public product", "currency": "VND", "status": 1, "item_status": "normal",
        "price_raw": "25000000000", "price_min_raw": "25000000000", "price_max_raw": "25000000000",
        "seller_rate_raw": "7000", "platform_rate_raw": "7000", "platform_cap_raw": "4000000000",
        "period_start_time": int((NOW - timedelta(days=1)).timestamp()),
        "period_end_time": int((NOW + timedelta(days=1)).timestamp()), "fetched_at": NOW.isoformat(),
    }
    quote.update(changes)
    return {"success": True, "quote": quote}


class NativeClient:
    def __init__(self, dto=None, error=None, delay=0):
        self.dto = native_dto() if dto is None else dto
        self.error = error
        self.delay = delay
        self.targets = []

    def fetch_quote(self, target, *, now, deadline):
        self.targets.append(target)
        self.deadline = deadline
        if self.delay:
            time.sleep(min(self.delay, max(0, deadline - time.monotonic())))
        if self.error:
            raise self.error
        return native_quote_from_payload(self.dto, target, now=now)


def bot(tmp_path, pd=None, native=None, **changes):
    return CashbackService(
        settings(tmp_path, product_quote_primary="native", **changes), repo(tmp_path),
        pd or FakeClient(error=ProductDataError("transport")), native_client=native or NativeClient(),
    )


def stored(service):
    with service.repo.connect() as conn:
        link = dict(conn.execute("SELECT * FROM link_requests WHERE link_status='created'").fetchone())
        snap = dict(conn.execute("SELECT * FROM link_policy_snapshots").fetchone())
    return link, snap


def env():
    return {"CASHBACK_BOT_TOKEN": "123:test", "SHOPEE_AFFILIATE_ID": "17300001", "ADDLIVETAG_API_KEY": "test",
            "CASHBACK_RATE_PERCENT": "70", "PRODUCT_MAX_AGE_HOURS": "3"}


def test_primary_defaults_product_data_and_accepts_native():
    assert load_settings(env()).product_quote_primary == "product_data"
    assert load_settings({**env(), "PRODUCT_QUOTE_PRIMARY": "native"}).product_quote_primary == "native"
    with pytest.raises(ConfigError, match="PRODUCT_QUOTE_PRIMARY"):
        load_settings({**env(), "PRODUCT_QUOTE_PRIMARY": "automatic"})
    with pytest.raises(ConfigError, match="ADDLIVETAG_API_KEY"):
        load_settings({**env(), "PRODUCT_QUOTE_PRIMARY": "native", "ADDLIVETAG_API_KEY": ""})


def test_native_success_skips_pd_and_saves_truthful_snapshot(tmp_path):
    pd = FakeClient(payload())
    service = bot(tmp_path, pd=pd)
    reply = service.handle_text(111, "buyer", URL, 19001, now=NOW)
    link, snap = stored(service)
    assert reply.button_url and pd.calls == 0
    assert link["estimated_commission"] == 23750
    assert link["estimated_cashback"] == 16625
    assert link["data_source"] == snap["quote_source"] == "native_shopee"
    assert link["product_last_update"] is None
    assert "source_updated_at=unknown" in snap["note"]
    assert "fetched_at=" in snap["note"]
    assert parse_qs(urlparse(reply.button_url).query)["sub_id"] == [link["sub_id"]]
    assert snap["quote_commission_vnd"] == link["estimated_commission"]


def test_product_data_default_does_not_call_native(tmp_path):
    pd = FakeClient(payload())
    native = NativeClient(error=AssertionError("must not call"))
    service = CashbackService(settings(tmp_path), repo(tmp_path), pd, native_client=native)
    assert service.handle_text(111, "buyer", URL, 19002, now=NOW).button_url
    assert pd.calls == 1 and native.targets == []
    assert stored(service)[1]["quote_source"] == "product_data"


def test_native_error_falls_back_to_pd_with_expected_ids(tmp_path):
    pd = FakeClient(payload())
    service = bot(tmp_path, pd=pd, native=NativeClient(error=NativeQuoteError("auth_required")))
    assert service.handle_text(111, "buyer", URL, 19003, now=NOW).button_url
    link, snap = stored(service)
    assert pd.calls == 1
    assert pd.targets[0].shop_id == 9 and pd.targets[0].item_id == 8
    assert snap["quote_source"] == "product_data" and link["product_last_update"] is not None


@pytest.mark.parametrize("part,value", [("itemId", 77), ("shopId", 77)])
def test_pd_fallback_identity_mismatch_never_displays_other_item(tmp_path, part, value):
    wrong = payload(**{part: value, "productLink": ""})
    service = bot(tmp_path, pd=FakeClient(wrong), native=NativeClient(error=NativeQuoteError("transport")))
    reply = service.handle_text(111, "buyer", URL, 19004, now=NOW)
    link, snap = stored(service)
    assert reply.text == DEGRADED_UNQUOTED
    assert link["item_id"] == 8 and link["shop_id"] == 9
    assert link["estimated_cashback"] is None and snap["quote_source"] == "degraded_unquoted"


def test_native_zero_is_valid_quoted_zero_not_unquoted(tmp_path):
    service = bot(tmp_path, native=NativeClient(native_dto(seller_rate_raw="0", platform_rate_raw="0", period_start_time=0, period_end_time=0)))
    reply = service.handle_text(111, "buyer", URL, 19005, now=NOW)
    link, snap = stored(service)
    assert reply.text != DEGRADED_UNQUOTED
    assert link["estimated_commission"] == link["estimated_cashback"] == 0
    assert snap["quote_source"] == "native_shopee" and snap["quote_cashback_vnd"] == 0


def test_variant_minimum_basis_is_recorded_in_snapshot(tmp_path):
    service = bot(tmp_path, native=NativeClient(native_dto(price_raw="30000000000", price_max_raw="35000000000")))
    assert service.handle_text(111, "buyer", URL, 19006, now=NOW).button_url
    link, snap = stored(service)
    assert link["price_vnd"] == 250000
    assert "price_basis=variant_min" in snap["note"] and "price_max_vnd=350000" in snap["note"]


def test_short_resolved_once_and_both_providers_receive_exact_target(tmp_path, monkeypatch):
    calls = []
    def resolve(url, *, deadline):
        calls.append(url)
        return ResolvedProduct(9, 8, URL, 1)
    monkeypatch.setattr("cashback_bot.service.resolve_to_product", resolve)
    pd = FakeClient(payload())
    native = NativeClient(error=NativeQuoteError("timeout"))
    service = bot(tmp_path, pd=pd, native=native)
    reply = service.handle_text(111, "buyer", "https://s.shopee.vn/testing", 19007, now=NOW)
    assert reply.button_url and calls == ["https://s.shopee.vn/testing"]
    assert native.targets[0].short_url is None and pd.targets[0].short_url is None
    assert native.targets[0].shop_id == pd.targets[0].shop_id == 9
    assert stored(service)[1]["quote_source"] == "product_data"


def test_unsafe_resolution_never_hits_providers_or_creates_link(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise ResolveError("ssrf")
    monkeypatch.setattr("cashback_bot.service.resolve_to_product", reject)
    pd, native = FakeClient(payload()), NativeClient()
    service = bot(tmp_path, pd=pd, native=native)
    reply = service.handle_text(111, "buyer", "https://s.shopee.vn/testing", 19008, now=NOW)
    assert reply.button_url is None and pd.calls == 0 and native.targets == []
    with service.repo.connect() as conn:
        assert conn.execute("SELECT count(*) FROM link_policy_snapshots").fetchone()[0] == 0


def test_native_duplicate_and_terms_gates_keep_one_snapshot(tmp_path):
    native = NativeClient()
    service = bot(tmp_path, native=native)
    service.handle_text(111, "buyer", URL, 19009, now=NOW)
    service.handle_text(111, "buyer", URL, 19009, now=NOW)
    with service.repo.connect() as conn:
        assert conn.execute("SELECT count(*) FROM link_policy_snapshots").fetchone()[0] == 1
    assert len(native.targets) == 1


def test_native_respects_existing_terms_gate(tmp_path):
    native = NativeClient()
    service = bot(tmp_path, native=native, terms_required=True)
    with service.repo.connect() as conn:
        draft = terms.create_draft(conn, "native-test", "Test terms", [("scope", "Scope", "Test")], "test", NOW)
        live = terms.get(conn, draft)
        terms.publish(conn, draft, live.content_hash, "test", NOW)
    reply = service.handle_text(111, "buyer", URL, 19010, now=NOW)
    assert reply.button_url is None and native.targets == []


def test_affipad_signed_link_and_sub_id_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr("cashback_bot.service.shorten_shopee_url", lambda *a, **k: "https://s.shopee.vn/opaque")
    seen = []
    class Pad:
        def sign_tracking_only(self, url, *, preset, deadline):
            seen.append((url, deadline))
            return url + "?fb_content_id=sample&sm_sig_id=signature&channel_type=fb"
    service = bot(tmp_path)
    service.affipad = Pad()
    reply = service.handle_text(111, "buyer", URL, 19011, now=NOW)
    assert is_meta_signed(reply.button_url) and seen[0][0] == "https://s.shopee.vn/opaque"
    assert stored(service)[1]["quote_source"] == "native_shopee"


@contextmanager
def http_server(mode):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.answer()
        def do_POST(self):
            self.answer()
        def answer(self):
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requests.append({"path": self.path, "headers": dict(self.headers), "body": raw_body})
            if mode == "slow_headers":
                time.sleep(0.7)
            body = json.dumps(payload()).encode() if mode != "affipad" else json.dumps({"data": {"results": [{"link": URL + "?fb_content_id=a&sm_sig_id=b"}]}}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if mode == "trickle":
                    for byte in body:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.025)
                else:
                    self.wfile.write(body)
            except (OSError, ConnectionError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


@pytest.mark.parametrize("mode", ["slow_headers", "trickle"])
def test_pd_actual_http_total_deadline_stops_headers_and_body(mode):
    with http_server(mode) as (base, calls):
        client = ProductDataClient("api-key", base + "/product-data", min_interval_sec=0)
        started = time.monotonic()
        with pytest.raises(ProductDataError, match="timeout"):
            client.fetch(TARGET, deadline=started + 0.13)
        assert time.monotonic() - started < 0.28
        assert calls and parse_qs(urlparse(calls[0]["path"]).query) == {"item_id": ["8"]}
        assert calls[0]["headers"]["X-API-Key"] == "api-key"


def test_pd_rate_limit_lock_and_wait_are_bounded():
    client = ProductDataClient("key", "http://127.0.0.1", min_interval_sec=5)
    client._guard.acquire()
    started = time.monotonic()
    try:
        with pytest.raises(ProductDataError, match="timeout"):
            client.fetch(TARGET, deadline=started + 0.08)
    finally:
        client._guard.release()
    assert time.monotonic() - started < 0.18
    client._last_call_at = time.monotonic()
    started = time.monotonic()
    with pytest.raises(ProductDataError, match="timeout"):
        client.fetch(TARGET, deadline=started + 0.08)
    assert time.monotonic() - started < 0.1


def test_full_native_pd_timeout_returns_canonical_unquoted_inside_budget(tmp_path, monkeypatch, record_property):
    class RecordedPD(ProductDataClient):
        def fetch(self, target, *, deadline=None):
            try:
                return super().fetch(target, deadline=deadline)
            finally:
                self.external_finished = time.monotonic()
    def unexpected(*args, **kwargs):
        raise AssertionError("No external shortlink call after provider deadline")
    monkeypatch.setattr("cashback_bot.service.shorten_shopee_url", unexpected)
    with http_server("trickle") as (base, calls):
        pd = RecordedPD("key", base + "/pd", min_interval_sec=0)
        native = NativeClient(error=NativeQuoteError("transport"), delay=0.05)
        service = bot(tmp_path, pd=pd, native=native, product_quote_deadline_sec=0.5)
        started = time.monotonic()
        reply = service.handle_text(111, "buyer", URL, 19012, now=NOW)
        elapsed = time.monotonic() - started
        assert reply.text == DEGRADED_UNQUOTED and reply.button_url
        # The shared deadline bounds provider I/O, measured before snapshot
        # SQLite writes. Synchronous local DB work and scheduler pauses are not
        # hard-cancelled; record whole-handle latency instead of an arbitrary
        # DB wall-time guarantee. Slow-header/body transport tests remain timed.
        assert pd.external_finished - native.deadline < 0.12
        record_property("whole_handle_elapsed_seconds", elapsed)
        link, snap = stored(service)
        assert link["estimated_commission"] is None and snap["quote_cashback_vnd"] is None
        assert snap["quote_source"] == "degraded_unquoted"
        assert len(calls) == 1


@pytest.mark.parametrize("mode", ["slow_headers", "trickle"])
def test_affipad_actual_http_deadline_stops_headers_and_body(mode):
    with http_server(mode) as (base, calls):
        client = AffiPadClient("key", "tool", base_url=base)
        started = time.monotonic()
        assert client.sign_tracking_only(URL, deadline=started + 0.13) is None
        assert time.monotonic() - started < 0.28
        body = json.loads(calls[0]["body"])
        assert body["url"] == URL and body["trackingOnly"] is True
        assert calls[0]["headers"]["Authorization"] == "Bearer key"


def test_affipad_deadline_payload_and_valid_meta_result():
    with http_server("affipad") as (base, calls):
        client = AffiPadClient("key", "tool", base_url=base)
        assert is_meta_signed(client.sign_tracking_only(URL, deadline=time.monotonic() + 1))
        body = json.loads(calls[0]["body"])
        assert body == {"url": URL, "toolId": "tool", "trackingOnly": True, "useShortLink": False, "tracking": {"preset": "fb_reels"}}


@pytest.mark.parametrize("payload_value", [{"data": []}, {"results": [None]}, {"results": "wrong"}, {"results": [{"link": 1}]}])
def test_affipad_malformed_results_fail_safely(monkeypatch, payload_value):
    monkeypatch.setattr("cashback_bot.affipad.request_bytes", lambda *a, **k: (200, json.dumps(payload_value).encode()))
    assert AffiPadClient("key", "tool").sign_tracking_only(URL, deadline=time.monotonic() + 1) is None


def test_helper_invalid_configuration_is_safe():
    for url in ["http://[invalid", "ftp://example.test", "https://user:password@example.test"]:
        with pytest.raises(DeadlineHttpError, match="invalid_url"):
            request_bytes("GET", url, deadline=time.monotonic() + 1)


def test_pd_timeout_does_not_mutate_shared_client_timeout():
    client = ProductDataClient("key", "http://127.0.0.1", timeout=20, min_interval_sec=0)
    with pytest.raises(ProductDataError, match="timeout"):
        client.fetch(TARGET, deadline=time.monotonic() - 1)
    assert client._timeout == 20


def test_expired_link_budget_does_not_call_alt_or_affipad(tmp_path, monkeypatch):
    service = bot(tmp_path, alt_shopee_link_fallback=True)
    class Unexpected:
        def create_short(self, *args, **kwargs):
            raise AssertionError("expired ALT call")
        def sign_tracking_only(self, *args, **kwargs):
            raise AssertionError("expired AffiPad call")
    service.alt_shopee_link = service.affipad = Unexpected()
    link, source = service._build_affiliate_url(URL, "sub12345", time.monotonic() - 1, item_id=8)
    assert source == "an_redir" and "origin_link=" in link


def test_alt_optional_deadline_preserves_query_and_auth(monkeypatch):
    monkeypatch.setenv("ALT_SHOPEE_LINK_LIVE", "1")
    seen = []
    def request(method, url, **kwargs):
        seen.append((method, url, kwargs))
        return 200, b'{"short_link":"https://s.shopee.vn/test"}'
    monkeypatch.setattr("cashback_bot.alt_shopee_link.request_bytes", request)
    client = HttpAltShopeeLinkClient("key")
    assert client.create_short(URL, "sub1", timeout=1, deadline=time.monotonic() + 1) == "https://s.shopee.vn/test"
    assert parse_qs(urlparse(seen[0][1]).query) == {"url": [URL], "sub_id": ["sub1"]}
    assert seen[0][2]["headers"] == {"Authorization": "Bearer key"}


def test_signed_link_without_channel_type_is_safe():
    assert meta_channel("https://s.shopee.vn/opaque?fb_content_id=x&sm_sig_id=y") is None


def test_shortener_deadline_passes_remaining_to_bridge_without_mutating_url(monkeypatch):
    monkeypatch.setenv("SHOPEE_SHORTENER_LIVE", "1")
    monkeypatch.setattr(shopee_shortener, "_CACHE", {})
    monkeypatch.setattr(shopee_shortener, "_LAST_BRIDGE_FAIL", 0.0)
    seen = []
    def request(method, url, **kwargs):
        seen.append((url, kwargs))
        return 200, b'{"short_link":"https://s.shopee.vn/opaque"}'
    monkeypatch.setattr(shopee_shortener, "request_bytes", request)
    assert shopee_shortener.shorten_shopee_url(URL, "sub12345", deadline=time.monotonic() + 1) == "https://s.shopee.vn/opaque"
    query = parse_qs(urlparse(seen[0][0]).query)
    assert query["url"] == [URL] and query["sub_id"] == ["sub12345"]
    assert 1 <= int(query["timeout_ms"][0]) <= 1000
    assert seen[0][1]["deadline"] <= time.monotonic() + 1
