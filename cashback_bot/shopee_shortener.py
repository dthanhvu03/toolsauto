"""Client tích hợp Shopee MCP bridge (cổng 9224) để tạo link rút gọn Shopee Affiliate (s.shopee.vn/XXXXX).

Bridge sử dụng phiên làm việc đăng nhập sẵn trên máy để gọi GraphQL batchCustomLink nội bộ,
đảm bảo link tạo ra mang đầy đủ subId và affiliate_id của hệ thống.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 5000
_CACHE: dict[tuple[str, str], str] = {}
_LAST_BRIDGE_FAIL: float = 0.0
FAIL_COOLDOWN_SEC = 30.0  # Circuit breaker: nếu bridge lỗi/tắt, không chờ timeout mà fallback ngay trong 30s


def get_bridge_host() -> str:
    """Xác định IP của Windows host từ trong WSL2."""
    env_host = os.environ.get("SHOPEE_BRIDGE_HOST")
    if env_host:
        return env_host
    try:
        with open("/proc/net/route") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    return socket.inet_ntoa(bytes.fromhex(parts[2])[::-1])
    except Exception:
        pass
    return "127.0.0.1"


def get_bridge_url() -> str:
    port = os.environ.get("SHOPEE_BRIDGE_PORT", "9224")
    return f"http://{get_bridge_host()}:{port}"


def shorten_shopee_url(url: str, sub_id: str = "AUTOSALE", timeout: float = 1.5) -> Optional[str]:
    """Tạo link s.shopee.vn/XXXXX qua shopee-mcp bridge.

    Trả về URL rút gọn nếu thành công, None nếu bridge offline / lỗi / timeout / test mode.
    Timeout mặc định 1.5s và có Circuit Breaker 30s để không bao giờ làm nghẽn luồng render tin nhắn.
    """
    global _LAST_BRIDGE_FAIL

    if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("SHOPEE_SHORTENER_LIVE"):
        return None

    key = (url, sub_id)
    if key in _CACHE:
        return _CACHE[key]

    # Circuit breaker: nếu vừa gặp lỗi bridge, bỏ qua để phản hồi ngay 0ms
    now = time.time()
    if now - _LAST_BRIDGE_FAIL < FAIL_COOLDOWN_SEC:
        return None

    bridge_url = get_bridge_url()
    query = urllib.parse.urlencode({"url": url, "sub_id": sub_id})
    endpoint = f"{bridge_url}/api/generate_shortlink?{query}"

    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "CashbackBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                short_link = data.get("short_link")
                if short_link and short_link.startswith("https://s.shopee.vn/"):
                    # Quản lý giới hạn bộ nhớ cache FIFO
                    if len(_CACHE) >= MAX_CACHE_SIZE:
                        _CACHE.pop(next(iter(_CACHE)))
                    _CACHE[key] = short_link
                    _LAST_BRIDGE_FAIL = 0.0
                    return short_link
    except Exception as exc:
        _LAST_BRIDGE_FAIL = time.time()
        logger.debug("[ShopeeShortener] Bridge error for %s: %s (circuit breaker active 30s)", url, exc)

    return None


def shorten_if_an_redir(url: str, timeout: float = 1.5) -> str:
    """Nếu URL là an_redir cho kênh sale / voucher (AUTOSALE, VOUCHERS), rút gọn thành s.shopee.vn/XXXXX."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in {"s.shopee.vn", "shp.ee", "shope.ee"} and parsed.path.rstrip("/") == "/an_redir":
            qs = urllib.parse.parse_qs(parsed.query)
            origin = qs.get("origin_link", [None])[0]
            sub_id = qs.get("sub_id", ["AUTOSALE"])[0]
            if origin and sub_id in {"AUTOSALE", "VOUCHERS"}:
                short = shorten_shopee_url(origin, sub_id=sub_id, timeout=timeout)
                if short:
                    return short
    except Exception:
        pass
    return url
