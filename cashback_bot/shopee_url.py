"""Chỉ nhận URL sản phẩm Shopee hoặc link rút gọn của Shopee."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_BARE_RE = re.compile(
    r"(?:s\.shopee\.vn|vn\.shp\.ee|shopee\.vn)/[^\s<>\"']+",
    re.IGNORECASE,
)
_PRODUCT_PATH = re.compile(r"^/product/(\d+)/(\d+)/?$")
_I_PATH = re.compile(r"-i\.(\d+)\.(\d+)(?:/|$)")
_SHORT_HOSTS = {"s.shopee.vn", "vn.shp.ee"}
_PRODUCT_HOSTS = {"shopee.vn", "www.shopee.vn"}
# Link chia sẻ ShopeeFood (đồ ăn): không phải sản phẩm sàn, bot không có giá / hoa hồng để báo hoàn tiền.
_FOOD_HOSTS = {"spf.shopee.vn", "shopeefood.vn", "www.shopeefood.vn"}


@dataclass(frozen=True)
class ShopeeTarget:
    original_url: str
    item_id: int | None
    shop_id: int | None
    short_url: str | None


def _strip_tail(raw: str) -> str:
    return raw.rstrip(".,;:!?)]}>\"'")


def _candidate_urls(text: str) -> list[str]:
    found = [_strip_tail(match.group(0)) for match in _URL_RE.finditer(text or "")]
    if found:
        return found
    bare = _BARE_RE.search(text or "")
    if not bare:
        return []
    return ["https://" + _strip_tail(bare.group(0))]


def parse_shopee_target(text: str) -> ShopeeTarget | None:
    for raw in _candidate_urls(text):
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in {"http", "https"} or parsed.username or parsed.password:
            continue
        https_url = raw if parsed.scheme.lower() == "https" else "https://" + raw.split("://", 1)[1]
        host = (parsed.hostname or "").lower()
        if host in _SHORT_HOSTS and parsed.path not in {"", "/"}:
            return ShopeeTarget(raw, None, None, https_url.split("?")[0])
        if host not in _PRODUCT_HOSTS:
            continue
        product = _PRODUCT_PATH.match(parsed.path)
        if product:
            shop_id = int(product.group(1))
            item_id = int(product.group(2))
            return ShopeeTarget(raw, item_id, shop_id, None)
        inline = _I_PATH.search(parsed.path)
        if inline:
            shop_id = int(inline.group(1))
            item_id = int(inline.group(2))
            return ShopeeTarget(raw, item_id, shop_id, None)
    return None


def is_shopee_food_link(text: str) -> bool:
    """Tin có link ShopeeFood (không có link sản phẩm sàn nào): để trả lời đúng thay vì «chưa nhận ra link»."""
    return any((urlparse(raw).hostname or "").lower() in _FOOD_HOSTS for raw in _URL_RE.findall(text or ""))


def canonical_product_url(shop_id: int, item_id: int) -> str:
    return f"https://shopee.vn/product/{shop_id}/{item_id}"


def is_canonical_product_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "shopee.vn":
        return False
    if parsed.query or parsed.fragment or parsed.username:
        return False
    return _PRODUCT_PATH.match(parsed.path) is not None
