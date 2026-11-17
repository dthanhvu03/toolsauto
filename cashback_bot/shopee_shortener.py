"""Client tích hợp Shopee MCP bridge (cổng 9224) để tạo link rút gọn Shopee Affiliate (s.shopee.vn/XXXXX).

Bridge sử dụng phiên làm việc đăng nhập sẵn trên máy để gọi GraphQL batchCustomLink nội bộ,
đảm bảo link tạo ra mang đầy đủ subId và affiliate_id của hệ thống.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from cashback_bot.affipad import is_meta_signed

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 5000
_CACHE: dict[tuple[str, str], str] = {}
_PUBLIC_CACHE: dict[str, str] = {}
_LAST_BRIDGE_FAIL: float = 0.0
_LAST_PUBLIC_FAIL: float = 0.0
FAIL_COOLDOWN_SEC = 30.0  # Circuit breaker: nếu bridge lỗi/tắt, không chờ timeout mà fallback ngay trong 30s
# Gọi bridge lần lượt: relay mở link bằng 4 luồng, bridge (một phiên trình duyệt) phải xếp hàng thì link thứ 4 chờ cả
# 3 link trước, hết timeout dù bridge không lỗi. Thời gian chờ khoá không tính vào timeout.
_BRIDGE_LOCK = threading.Lock()
# Đo thật 2026-10-31: bridge trả mỗi link 2,1–4,5 s tuỳ tải, nâng lên 6.0s để không timeout hụt
DEFAULT_TIMEOUT = 6.0
# Zalo không có nút URL: Meta query ~1KB. Rút qua is.gd (302 về đúng URL Meta), chỉ để hiện cho khách.
PUBLIC_SHORT_TIMEOUT = 3.0
ZALO_META_INLINE_MAX = 120


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


def shorten_shopee_url(url: str, sub_id: str = "AUTOSALE", timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """Tạo link s.shopee.vn/XXXXX qua shopee-mcp bridge.

    Trả về URL rút gọn nếu thành công, None nếu bridge offline / lỗi / timeout / test mode.
    Timeout mặc định DEFAULT_TIMEOUT và có Circuit Breaker 30s để không bao giờ làm nghẽn luồng render tin nhắn.
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

    with _BRIDGE_LOCK:
        # Trong lúc chờ khoá, luồng khác có thể đã rút gọn link này hoặc vừa gặp lỗi bridge.
        if key in _CACHE:
            return _CACHE[key]
        if time.time() - _LAST_BRIDGE_FAIL < FAIL_COOLDOWN_SEC:
            return None
        return _call_bridge(url, sub_id, timeout)


def _call_bridge(url: str, sub_id: str, timeout: float) -> Optional[str]:
    global _LAST_BRIDGE_FAIL

    bridge_url = get_bridge_url()
    query = urllib.parse.urlencode({"url": url, "sub_id": sub_id})
    endpoint = f"{bridge_url}/api/generate_shortlink?{query}"
    started = time.monotonic()

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
                    _CACHE[(url, sub_id)] = short_link
                    _LAST_BRIDGE_FAIL = 0.0
                    # Ghi thời gian thật để biết timeout đủ chưa (chủ bot 2026-10-31).
                    logger.info("[ShopeeShortener] OK %.1fs (timeout %.1fs) %s", time.monotonic() - started, timeout,
                                short_link)
                    return short_link
        logger.warning("[ShopeeShortener] Bridge trả không có link sau %.1fs: %s", time.monotonic() - started, url)
    except Exception as exc:
        _LAST_BRIDGE_FAIL = time.time()
        logger.warning("[ShopeeShortener] Lỗi sau %.1fs (timeout %.1fs): %s (ngừng gọi 30s) %s",
                       time.monotonic() - started, timeout, exc, url)

    return None


def shorten_if_an_redir(url: str, timeout: float = DEFAULT_TIMEOUT, any_sub: bool = False) -> str:
    """Nếu URL là an_redir cho kênh sale / voucher (AUTOSALE, VOUCHERS), rút gọn thành s.shopee.vn/XXXXX.

    any_sub: rút gọn cả link mua riêng của khách (sub_id từng link) — Zalo in link ra chữ, link dài 6 dòng (chủ bot 12/11).
    Link ngắn tạo bằng batchCustomLink kèm đúng sub_id nên đơn vẫn về đúng link. Lỗi / cầu nối tắt: giữ link dài.
    PLAN-174: URL đã ký Meta (fb_content_id / sm_sig_id…) giữ nguyên — rút gọn bridge sẽ mất voucher FB."""
    try:
        if is_meta_signed(url):
            return url
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in {"s.shopee.vn", "shp.ee", "shope.ee"} and parsed.path.rstrip("/") == "/an_redir":
            qs = urllib.parse.parse_qs(parsed.query)
            origin = qs.get("origin_link", [None])[0]
            sub_id = qs.get("sub_id", ["AUTOSALE"])[0]
            if origin and (any_sub or sub_id in {"AUTOSALE", "VOUCHERS"}):
                short = shorten_shopee_url(origin, sub_id=sub_id, timeout=timeout)
                if short:
                    return short
    except Exception:
        pass
    return url


def public_shorten(url: str, timeout: float = PUBLIC_SHORT_TIMEOUT) -> Optional[str]:
    """Rút URL công khai qua is.gd (302 về đúng đích, giữ query Meta). Lỗi / pytest → None."""
    global _LAST_PUBLIC_FAIL

    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return None
    if target in _PUBLIC_CACHE:
        return _PUBLIC_CACHE[target]
    if "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("ZALO_SHORTEN_LIVE"):
        return None
    if time.time() - _LAST_PUBLIC_FAIL < FAIL_COOLDOWN_SEC:
        return None

    endpoint = "https://is.gd/create.php?" + urllib.parse.urlencode({"format": "simple", "url": target})
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "CashbackBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            short = (resp.read().decode("utf-8", errors="replace") or "").strip()
        if short.startswith("https://is.gd/") or short.startswith("http://is.gd/"):
            if len(_PUBLIC_CACHE) >= MAX_CACHE_SIZE:
                _PUBLIC_CACHE.pop(next(iter(_PUBLIC_CACHE)))
            _PUBLIC_CACHE[target] = short
            _LAST_PUBLIC_FAIL = 0.0
            return short
        logger.warning("[ShopeeShortener] is.gd trả không phải short: %s", short[:80])
    except Exception as exc:
        _LAST_PUBLIC_FAIL = time.time()
        logger.warning("[ShopeeShortener] is.gd lỗi: %s", type(exc).__name__)
    return None


def zalo_buy_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """URL hiện trên Zalo: an_redir → bridge short; Meta dài → is.gd (giữ đích); lỗi → URL gốc."""
    target = (url or "").strip()
    if not target:
        return target
    if is_meta_signed(target) and len(target) > ZALO_META_INLINE_MAX:
        return public_shorten(target) or target
    return shorten_if_an_redir(target, timeout=timeout, any_sub=True)
