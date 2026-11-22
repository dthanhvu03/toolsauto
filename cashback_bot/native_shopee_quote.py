"""PLAN-177 native quote DTO: fixed-point money, exact identity, bounded bridge I/O.

``fetched_at`` measures retrieval only. Native has no source update timestamp;
``last_update`` is deliberately None and must stay NULL in link snapshots.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import math
import os
import re
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

from cashback_bot.product_data import ProductDataError, ProductQuote
from cashback_bot.shopee_shortener import get_bridge_url
from cashback_bot.shopee_url import ShopeeTarget, canonical_product_url

SCALE = 100_000
MAX_SQLITE_INTEGER = (1 << 63) - 1
MAX_RESPONSE_BYTES = 1024 * 1024
QUOTE_CONTEXT = "social_media_shop_existing"
_WHOLE = re.compile(r"[0-9]{1,24}\Z", re.ASCII)
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_PERCENT = re.compile(r"[0-9]+(?:[.,][0-9]+)?%\Z", re.ASCII)


class NativeQuoteError(ProductDataError):
    """Only locally chosen codes escape the bridge boundary, never raw errors."""


@dataclass(frozen=True, kw_only=True)
class NativeProductQuote(ProductQuote):
    last_update: None = None
    fetched_at: datetime
    price_min_vnd: int
    price_max_vnd: int
    price_basis: str
    seller_rate_raw: int
    platform_rate_raw: int
    platform_cap_vnd: int
    quote_source: str = "native_shopee"
    context: str = QUOTE_CONTEXT


def parse_percent(value: object) -> Decimal | None:
    """Display rate helper: missing != zero; no binary float conversion."""
    if not isinstance(value, str) or len(value) > 32 or not _PERCENT.fullmatch(value.strip()):
        return None
    try:
        rate = Decimal(value.strip()[:-1].replace(",", "."))
    except InvalidOperation:
        return None
    return rate if rate.is_finite() and 0 <= rate <= 100 else None


def _whole(value: object, *, positive: bool = False, rate: bool = False) -> int:
    if not isinstance(value, str) or not _WHOLE.fullmatch(value):
        raise NativeQuoteError("invalid_numeric")
    number = int(value)
    if positive and number <= 0 or rate and number > SCALE:
        raise NativeQuoteError("invalid_numeric")
    return number


def _target_ids(target: ShopeeTarget) -> tuple[str, str]:
    if type(target.shop_id) is not int or type(target.item_id) is not int:
        raise NativeQuoteError("unresolved_identity")
    shop, item = str(target.shop_id), str(target.item_id)
    if not _ID.fullmatch(shop) or not _ID.fullmatch(item) \
            or target.shop_id > MAX_SQLITE_INTEGER or target.item_id > MAX_SQLITE_INTEGER:
        raise NativeQuoteError("invalid_identity")
    return shop, item


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise NativeQuoteError("invalid_time")
    return value.astimezone(timezone.utc)


def native_quote_from_payload(
    payload: object, target: ShopeeTarget, *, now: datetime, max_fetch_age_seconds: float = 60,
) -> NativeProductQuote:
    """Validate schema-1 bridge DTO; reuse ProductQuote's existing sure policy."""
    now = _utc(now)
    if not math.isfinite(max_fetch_age_seconds) or max_fetch_age_seconds < 0:
        raise NativeQuoteError("invalid_configuration")
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise NativeQuoteError("bridge_rejected")
    data = payload.get("quote")
    if not isinstance(data, dict):
        raise NativeQuoteError("invalid_payload")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise NativeQuoteError("unsupported_schema")
    if data.get("source") != "native_shopee" or data.get("context") != QUOTE_CONTEXT:
        raise NativeQuoteError("unsupported_context")
    shop, item = _target_ids(target)
    if any(data.get(key) != expected for key, expected in (
        ("shop_id", shop), ("requested_shop_id", shop), ("item_id", item), ("requested_item_id", item),
    )):
        raise NativeQuoteError("identity_mismatch")
    if data.get("currency") != "VND" or type(data.get("status")) is not int or data["status"] != 1 \
            or data.get("item_status") != "normal":
        raise NativeQuoteError("unavailable_product")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 300 \
            or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise NativeQuoteError("invalid_name")
    stamp = data.get("fetched_at")
    try:
        if not isinstance(stamp, str) or len(stamp) > 40:
            raise ValueError
        fetched = _utc(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
    except (ValueError, NativeQuoteError):
        raise NativeQuoteError("invalid_fetched_at") from None
    age = (now - fetched).total_seconds()
    if age < -5 or age > max_fetch_age_seconds:
        raise NativeQuoteError("stale_retrieval")
    raw_price, low, high = (_whole(data.get(key), positive=True) for key in (
        "price_raw", "price_min_raw", "price_max_raw",
    ))
    if not low <= raw_price <= high or low // SCALE <= 0 or high // SCALE > MAX_SQLITE_INTEGER:
        raise NativeQuoteError("invalid_price")
    seller_rate = _whole(data.get("seller_rate_raw"), rate=True)
    platform_rate = _whole(data.get("platform_rate_raw"), rate=True)
    if seller_rate + platform_rate > SCALE:
        raise NativeQuoteError("invalid_numeric")
    cap_raw = _whole(data.get("platform_cap_raw"), positive=True)
    if cap_raw // SCALE > MAX_SQLITE_INTEGER:
        raise NativeQuoteError("invalid_numeric")
    start, end = data.get("period_start_time"), data.get("period_end_time")
    if any(type(value) is not int or not 0 <= value <= 32_503_680_000 for value in (start, end)):
        raise NativeQuoteError("invalid_period")
    if seller_rate == 0 and end == 0 and start <= now.timestamp():
        pass  # Captured non-XTRA has a historical start but no seller campaign end.
    elif not 0 < start <= now.timestamp() < end:
        raise NativeQuoteError("inactive_offer")
    price = low // SCALE  # Product-level link has no selected variant: quote the explicit minimum.
    seller = price * seller_rate // SCALE
    uncapped_platform = price * platform_rate // SCALE
    platform = min(uncapped_platform, cap_raw // SCALE)
    total_rate = seller_rate + platform_rate
    return NativeProductQuote(
        item_id=int(item), shop_id=int(shop), name=name.strip(), price_vnd=price,
        commission_vnd=seller + platform, data_source="native_shopee", api_status="success",
        product_url=canonical_product_url(int(shop), int(item)), fetched_at=fetched,
        seller_commission_vnd=seller, shopee_commission_vnd=platform,
        commission_rate_bps=total_rate // 10 if total_rate % 10 == 0 else None,
        is_xtra=seller_rate > 0, is_capped=uncapped_platform > cap_raw // SCALE,
        price_min_vnd=price, price_max_vnd=high // SCALE,
        price_basis="variant_min" if low != high else "single_price",
        seller_rate_raw=seller_rate, platform_rate_raw=platform_rate, platform_cap_vnd=cap_raw // SCALE,
    )


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if not math.isfinite(left) or left <= 0:
        raise NativeQuoteError("timeout")
    return left


def _http_get(url: str, deadline: float, limit: int) -> tuple[int, bytes]:
    """Single local bridge GET, no redirects; watchdog bounds even trickled HTTP."""
    parsed = urlsplit(url)
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host) if host != "localhost" else ipaddress.ip_address("127.0.0.1")
        if parsed.scheme != "http" or parsed.username or parsed.password or address.is_unspecified \
                or address.is_multicast or not (address.is_private or address.is_loopback):
            raise ValueError
        port = parsed.port or 80
    except (TypeError, ValueError):
        raise NativeQuoteError("invalid_bridge_url") from None
    connection = http.client.HTTPConnection(str(address), port, timeout=_remaining(deadline))
    expired = threading.Event()
    active_socket = None

    def abort() -> None:
        expired.set()
        # HTTPConnection may clear .sock after Connection: close headers while
        # HTTPResponse still owns the same descriptor. Keep that socket alive.
        sock = active_socket or connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    timer = threading.Timer(_remaining(deadline), abort)
    timer.daemon = True
    timer.start()
    response = None
    try:
        connection.connect()
        active_socket = connection.sock
        _remaining(deadline)
        connection.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""),
                           headers={"Accept": "application/json", "User-Agent": "CashbackBot/1.0"})
        _remaining(deadline)
        response = connection.getresponse()
        _remaining(deadline)
        if response.status != 200:
            return response.status, b""
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            raise NativeQuoteError("response_too_large")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise NativeQuoteError("unsupported_encoding")
        raw = response.read(limit + 1)
        _remaining(deadline)
        if len(raw) > limit:
            raise NativeQuoteError("response_too_large")
        return response.status, raw
    except NativeQuoteError:
        raise
    except Exception:
        raise NativeQuoteError("timeout" if expired.is_set() or time.monotonic() >= deadline else "transport") from None
    finally:
        timer.cancel()
        if response is not None:
            response.close()
        connection.close()


class NativeShopeeQuoteClient:
    def __init__(
        self, *, timeout: float = 8, cooldown_seconds: float = 30, max_fetch_age_seconds: float = 60,
        transport: Callable[[str, float, int], tuple[int, bytes]] | None = None,
    ):
        if any(not math.isfinite(value) or value < 0 for value in (timeout, cooldown_seconds, max_fetch_age_seconds)) \
                or not 0 < timeout <= 20:
            raise NativeQuoteError("invalid_configuration")
        self.timeout = timeout
        self.cooldown_seconds = cooldown_seconds
        self.max_fetch_age_seconds = max_fetch_age_seconds
        self._transport = transport
        self._lock = threading.Lock()
        self._failed_until = 0.0

    def fetch_quote(self, target: ShopeeTarget, *, now: datetime, deadline: float) -> NativeProductQuote:
        shop, item = _target_ids(target)
        started = time.monotonic()
        call_end = min(deadline, started + self.timeout)
        if not self._lock.acquire(timeout=_remaining(call_end)):
            raise NativeQuoteError("timeout")
        try:
            if time.monotonic() < self._failed_until:
                raise NativeQuoteError("circuit_open")
            if self._transport is None and "PYTEST_CURRENT_TEST" in os.environ \
                    and os.environ.get("SHOPEE_NATIVE_QUOTE_LIVE") != "1":
                raise NativeQuoteError("test_no_live")
            budget_ms = math.floor(_remaining(call_end) * 1000)
            if budget_ms < 1:
                raise NativeQuoteError("timeout")
            url = get_bridge_url().rstrip("/") + "/api/product_quote?" + urlencode({
                "shop_id": shop, "item_id": item, "timeout_ms": budget_ms,
            })
            try:
                status, raw = (self._transport or _http_get)(url, call_end, MAX_RESPONSE_BYTES)
                _remaining(call_end)
                if status != 200:
                    raise NativeQuoteError("bridge_http_error")
                if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
                    raise NativeQuoteError("response_too_large")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError, RecursionError):
                    raise NativeQuoteError("invalid_json") from None
                quote = native_quote_from_payload(
                    payload, target, now=_utc(now) + timedelta(seconds=time.monotonic() - started),
                    max_fetch_age_seconds=self.max_fetch_age_seconds,
                )
                _remaining(call_end)
            except Exception as error:
                self._failed_until = time.monotonic() + self.cooldown_seconds
                if isinstance(error, NativeQuoteError):
                    raise
                raise NativeQuoteError("transport") from None
            self._failed_until = 0
            return quote
        finally:
            self._lock.release()
