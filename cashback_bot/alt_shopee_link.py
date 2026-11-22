"""Client AddLiveTag shopee-link.php — fallback rút gọn (PLAN-177 Phase 1.3).

Mặc định TẮT. Live chỉ sau Owner Gate A. Unit/contract dùng mock — không thay live proof.
"""

from __future__ import annotations

import json
import logging
import os
import time
from urllib.parse import urlencode
from typing import Protocol

import requests

from cashback_bot.deadline_http import request_bytes

logger = logging.getLogger("cashback_bot")

DEFAULT_URL = "https://api.addlivetag.com/v1/shopee-link.php"


class AltShopeeLinkClient(Protocol):
    def create_short(self, product_url: str, sub_id: str, *, timeout: float, deadline: float | None = None) -> str | None:
        """Trả short URL hoặc None khi lỗi / tắt."""


class HttpAltShopeeLinkClient:
    """HTTP thật — chỉ dựng khi ALT_SHOPEE_LINK_FALLBACK bật + có API key."""

    def __init__(self, api_key: str, url: str = DEFAULT_URL):
        self._api_key = api_key
        self._url = url

    def create_short(self, product_url: str, sub_id: str, *, timeout: float, deadline: float | None = None) -> str | None:
        if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("ALT_SHOPEE_LINK_LIVE"):
            return None
        if timeout <= 0:
            return None
        try:
            if deadline is not None:
                status, raw = request_bytes(
                    "GET", self._url + ("&" if "?" in self._url else "?") + urlencode({"url": product_url, "sub_id": sub_id}),
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    deadline=min(deadline, time.monotonic() + timeout),
                )
                if status != 200:
                    return None
                data = json.loads(raw)
            else:
                resp = requests.get(
                    self._url, params={"url": product_url, "sub_id": sub_id},
                    headers={"Authorization": f"Bearer {self._api_key}"}, timeout=timeout,
                )
                if resp.status_code != 200:
                    logger.info("[AltShopeeLink] http=%s", resp.status_code)
                    return None
                data = resp.json() if "application/json" in (resp.headers.get("Content-Type") or "") else {}
            link = None
            if isinstance(data, dict):
                link = data.get("short_link") or data.get("link") or data.get("url")
            if isinstance(link, str) and link.startswith("https://"):
                return link
        except Exception as exc:
            logger.info("[AltShopeeLink] fail: %s", type(exc).__name__)
        return None


class NullAltShopeeLinkClient:
    def create_short(self, product_url: str, sub_id: str, *, timeout: float, deadline: float | None = None) -> str | None:
        return None
