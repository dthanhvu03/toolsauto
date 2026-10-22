"""Product Data API và cửa kiểm tra cache. HTTP 200 chưa đủ để đưa số tiền."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading
import time

import requests

from cashback_bot.shopee_url import ShopeeTarget, canonical_product_url, is_canonical_product_url

_VALID_SOURCES = {"api", "db"}
_BROKEN_STATUS = {"stale", "skipped", "not_found", "error"}


class ProductDataError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProductQuote:
    item_id: int
    shop_id: int
    name: str
    price_vnd: int
    commission_vnd: int
    last_update: datetime
    data_source: str
    api_status: str
    product_url: str


def _whole_vnd(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _parse_last_update(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    return None


def quote_from_payload(payload: dict, now: datetime, max_age_hours: int) -> ProductQuote:
    if payload.get("status") != "success":
        raise ProductDataError("api_status")
    warning = payload.get("warning")
    if isinstance(warning, str) and warning.strip():
        raise ProductDataError("stale")
    info = payload.get("productInfo")
    if not isinstance(info, dict):
        raise ProductDataError("not_found")
    product_status = info.get("status")
    if isinstance(product_status, str) and product_status in _BROKEN_STATUS:
        raise ProductDataError("stale" if product_status == "stale" else product_status)
    if isinstance(product_status, str) and product_status not in {"success", ""}:
        raise ProductDataError("api_status")

    source = info.get("dataSource")
    if source not in _VALID_SOURCES:
        raise ProductDataError("stale")

    updated = _parse_last_update(info.get("lastUpdate"))
    if updated is None:
        raise ProductDataError("missing_last_update")
    if updated > now + timedelta(minutes=10):
        raise ProductDataError("missing_last_update")
    if now - updated > timedelta(hours=max_age_hours):
        raise ProductDataError("too_old")

    price = _whole_vnd(info.get("price"))
    if price is None or price <= 0:
        raise ProductDataError("missing_price")
    commission = _whole_vnd(info.get("commission"))
    if commission is None or commission < 0:
        raise ProductDataError("missing_commission")

    item_id = _whole_vnd(info.get("itemId"))
    shop_id = _whole_vnd(info.get("shopId"))
    name = info.get("productName")
    if item_id is None or item_id <= 0 or shop_id is None or shop_id <= 0:
        raise ProductDataError("not_found")
    if not isinstance(name, str) or not name.strip():
        raise ProductDataError("not_found")

    product_url = canonical_product_url(shop_id, item_id)
    reported = info.get("productLink") or info.get("originLink")
    if isinstance(reported, str) and is_canonical_product_url(reported.strip()):
        if reported.strip() != product_url:
            raise ProductDataError("bad_product_link")

    return ProductQuote(
        item_id=item_id,
        shop_id=shop_id,
        name=name.strip(),
        price_vnd=price,
        commission_vnd=commission,
        last_update=updated,
        data_source=source,
        api_status="success",
        product_url=product_url,
    )


class ProductDataClient:
    def __init__(self, api_key: str, url: str, timeout: float = 20, min_interval_sec: float = 0.35):
        self._api_key = api_key
        self._url = url
        self._timeout = timeout
        self._min_interval_sec = max(0.0, float(min_interval_sec))
        self._guard = threading.Lock()
        self._last_call_at = 0.0

    def _respect_rate_limit(self) -> None:
        if self._min_interval_sec <= 0:
            return
        with self._guard:
            now = time.monotonic()
            wait = self._min_interval_sec - (now - self._last_call_at)
            if wait > 0:
                time.sleep(wait)
            self._last_call_at = time.monotonic()

    def fetch(self, target: ShopeeTarget) -> dict:
        params: dict[str, str] = {}
        if target.item_id:
            params["item_id"] = str(target.item_id)
        elif target.short_url:
            params["url"] = target.short_url
        else:
            raise ProductDataError("invalid_link")
        try:
            self._respect_rate_limit()
            response = requests.get(
                self._url,
                params=params,
                headers={"X-API-Key": self._api_key},
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise ProductDataError("timeout") from exc
        except requests.RequestException as exc:
            raise ProductDataError("transport") from exc
        if response.status_code != 200:
            raise ProductDataError("http_error")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProductDataError("invalid_json") from exc
        if not isinstance(payload, dict):
            raise ProductDataError("invalid_json")
        return payload
