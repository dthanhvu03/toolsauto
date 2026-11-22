"""Resolve short Shopee URL → shop/item an toàn (PLAN-177 Phase 1.1).

Max 3 hops (PROJECT.md VULN-SSRF). Mỗi chặng: scheme, allowlist host, DNS/IP
(chặn private/loopback/link-local/reserved/multicast/unspecified).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from cashback_bot.shopee_url import ShopeeTarget, canonical_product_url

logger = logging.getLogger("cashback_bot")

MAX_HOPS = 3
HOP_TIMEOUT = 3.0
TOTAL_RESOLVE_BUDGET = 8.0
_REDIRECTS = (301, 302, 303, 307, 308)

_ALLOWED_HOSTS = frozenset({
    "shopee.vn",
    "www.shopee.vn",
    "s.shopee.vn",
    "shp.ee",
    "vn.shp.ee",
    "shope.ee",
})
_SHORT_HOSTS = frozenset({"s.shopee.vn", "shp.ee", "vn.shp.ee", "shope.ee"})
_PRODUCT_HOSTS = frozenset({"shopee.vn", "www.shopee.vn"})

_PRODUCT_PATH = re.compile(r"^/product/(\d+)/(\d+)/?$")
_I_PATH = re.compile(r"-i\.(\d+)\.(\d+)(?:/|$)")
_OPAANLP_PATH = re.compile(r"^/opaanlp/(\d+)/(\d+)/?$")


@dataclass(frozen=True)
class ResolvedProduct:
    shop_id: int
    item_id: int
    product_url: str
    hops: int = 0


class ResolveError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _deadline_remaining(deadline: float | None) -> float:
    if deadline is None:
        return TOTAL_RESOLVE_BUDGET
    return max(0.0, deadline - time.monotonic())


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _public_host(hostname: str) -> bool:
    """Mọi địa chỉ DNS của host đều công khai; lỗi DNS → False."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    if not infos:
        return False
    for _, _, _, _, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if _is_blocked_ip(ip):
            return False
    return True


def _host_allowed(hostname: str | None, *, short_ok: bool) -> bool:
    if not hostname:
        return False
    host = hostname.lower()
    if host in _ALLOWED_HOSTS or host.endswith(".shopee.vn"):
        if host in _SHORT_HOSTS:
            return short_ok
        return host in _PRODUCT_HOSTS or host.endswith(".shopee.vn")
    return False


def is_safe_hop_url(url: str, *, allow_short: bool) -> bool:
    """Kiểm tra một URL hop: https, allowlist, không userinfo, DNS/IP sạch."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower()
    if not _host_allowed(host, short_ok=allow_short):
        return False
    return _public_host(host)


def _https(url: str) -> str:
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def _unwrap_an_redir(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in _SHORT_HOSTS and parsed.path.rstrip("/") == "/an_redir":
        origin = (parse_qs(parsed.query).get("origin_link") or [""])[0].strip()
        return origin or url
    return url


def parse_product_ids(url: str) -> tuple[int, int] | None:
    """Shop/item từ URL đích (product / -i. / opaanlp)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _PRODUCT_HOSTS:
        return None
    for pattern in (_PRODUCT_PATH, _OPAANLP_PATH):
        matched = pattern.match(parsed.path)
        if matched:
            return int(matched.group(1)), int(matched.group(2))
    inline = _I_PATH.search(parsed.path)
    if inline:
        return int(inline.group(1)), int(inline.group(2))
    return None


def from_target(target: ShopeeTarget) -> ResolvedProduct | None:
    """Khi đã có shop/item từ parse_shopee_target — không cần HTTP."""
    if target.shop_id and target.item_id:
        return ResolvedProduct(
            shop_id=int(target.shop_id),
            item_id=int(target.item_id),
            product_url=canonical_product_url(int(target.shop_id), int(target.item_id)),
            hops=0,
        )
    return None


def resolve_to_product(
    start_url: str,
    *,
    deadline: float | None = None,
    session: requests.Session | None = None,
    head: Callable[[str, float], requests.Response] | None = None,
) -> ResolvedProduct:
    """Follow tối đa MAX_HOPS; trả ResolvedProduct hoặc Raise ResolveError."""
    # Unit test mặc định không gọi Shopee live (cùng tinh thần shopee_shortener).
    if head is None and "PYTEST_CURRENT_TEST" in os.environ and not os.environ.get("SHOPEE_RESOLVE_LIVE"):
        raise ResolveError("test_no_live")

    budget_end = time.monotonic() + min(TOTAL_RESOLVE_BUDGET, _deadline_remaining(deadline) or 0.0)
    if deadline is not None:
        budget_end = min(budget_end, deadline)

    current = _https(start_url.strip())
    hops = 0
    http = session or requests.Session()
    do_head = head or (lambda u, t: http.head(u, allow_redirects=False, timeout=t))

    for _ in range(MAX_HOPS + 1):
        remaining = budget_end - time.monotonic()
        if remaining <= 0:
            raise ResolveError("deadline")
        current = _unwrap_an_redir(current)
        parsed = urlparse(current)
        host = (parsed.hostname or "").lower()
        if not is_safe_hop_url(current, allow_short=True):
            raise ResolveError("ssrf")
        ids = parse_product_ids(current)
        if ids is not None:
            shop_id, item_id = ids
            if not is_safe_hop_url(current, allow_short=False):
                raise ResolveError("ssrf")
            return ResolvedProduct(
                shop_id=shop_id,
                item_id=item_id,
                product_url=canonical_product_url(shop_id, item_id),
                hops=hops,
            )
        if host not in _SHORT_HOSTS:
            raise ResolveError("not_product")
        if hops >= MAX_HOPS:
            raise ResolveError("max_hops")
        hop_timeout = min(HOP_TIMEOUT, remaining)
        try:
            resp = do_head(current, hop_timeout)
        except Exception as exc:
            logger.info("[ShopeeResolve] HEAD fail url=%s err=%s", current, exc)
            raise ResolveError("transport") from exc
        if resp.status_code not in _REDIRECTS or "Location" not in resp.headers:
            raise ResolveError("no_redirect")
        nxt = urljoin(current, resp.headers["Location"].strip())
        current = _https(nxt)
        hops += 1
        if not is_safe_hop_url(current, allow_short=True):
            raise ResolveError("ssrf")

    raise ResolveError("max_hops")
