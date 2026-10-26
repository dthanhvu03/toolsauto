"""Nhận link sản phẩm TikTok Shop (PLAN-085 A1). Link khác giữ luồng Shopee.

Nhận: link rút gọn `vt.tiktok.com/…`, `vm.tiktok.com/…`, `www.tiktok.com/t/…` và trang sản phẩm
`(www|shop).tiktok.com/view/product/<id>`. RioHub `/product-links` nhận thẳng các link này, bot không tự mở link.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
# Zalo hay biến link thành thẻ xem trước; khách được dặn xoá «https://» nên link có thể không có scheme.
_BARE_RE = re.compile(r"(?:vt\.tiktok\.com|vm\.tiktok\.com|(?:www\.|shop\.)?tiktok\.com)/[^\s<>\"']+", re.IGNORECASE)
_SHORT_HOSTS = {"vt.tiktok.com", "vm.tiktok.com"}
_PAGE_HOSTS = {"www.tiktok.com", "tiktok.com", "shop.tiktok.com"}
_SHORT_PATH = re.compile(r"^/t/[A-Za-z0-9_-]+/?$")
_PRODUCT_PATH = re.compile(r"^/view/product/\d{6,25}/?$")


def _strip_tail(raw: str) -> str:
    return raw.rstrip(".,;:!?)]}>\"'")


def parse_tiktok_target(text: str) -> str | None:
    """URL https của link sản phẩm TikTok Shop đầu tiên trong tin, hoặc None."""
    candidates = [_strip_tail(m.group(0)) for m in _URL_RE.finditer(text or "")]
    if not candidates and (bare := _BARE_RE.search(text or "")):
        candidates = ["https://" + _strip_tail(bare.group(0))]
    for raw in candidates:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in {"http", "https"} or parsed.username or parsed.password:
            continue
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        if (host in _SHORT_HOSTS and len(path.strip("/")) >= 4) or (
            host in _PAGE_HOSTS and (_SHORT_PATH.match(path) or _PRODUCT_PATH.match(path))
        ):
            return "https://" + raw.split("://", 1)[1]
    return None
