"""Link an_redir một sub_id. Không ghép sub1-sub2."""

from __future__ import annotations

import re
import secrets
import string
from urllib.parse import urlencode, urlparse

from cashback_bot.shopee_url import food_url, is_canonical_product_url

_SUB_ID_RE = re.compile(r"^[A-Za-z0-9]{8}$")
_ALPHABET = string.ascii_letters + string.digits


def new_sub_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def is_valid_sub_id(value: str) -> bool:
    return _SUB_ID_RE.fullmatch(value) is not None


def build_an_redir(product_url: str, affiliate_id: str, sub_id: str) -> str:
    if not is_canonical_product_url(product_url):
        raise ValueError("product url")
    if not affiliate_id.isdigit():
        raise ValueError("affiliate id")
    if not is_valid_sub_id(sub_id):
        raise ValueError("sub id")
    query = urlencode(
        {
            "origin_link": product_url,
            "affiliate_id": affiliate_id,
            "sub_id": sub_id,
        }
    )
    return f"https://s.shopee.vn/an_redir?{query}"


# Link lưu mã giảm giá (PLAN-104): chung một sub_id, đơn mua sau khi lưu mã tính hoa hồng cho chủ bot, không gắn khách.
# Thử 30/10/2026: an_redir mở đúng trang mã, URL đích có utm_medium=affiliates.
VOUCHER_SUB_ID = "VOUCHERS"


def build_voucher_redir(link: str, affiliate_id: str) -> str:
    """Bọc link trang mã shopee.vn bằng an_redir. Link khác (rút gọn, sàn khác) thì ValueError."""
    parsed = urlparse(link)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "shopee.vn" or parsed.username or parsed.password:
        raise ValueError("voucher url")
    if not affiliate_id.isdigit():
        raise ValueError("affiliate id")
    query = urlencode({"origin_link": link, "affiliate_id": affiliate_id, "sub_id": VOUCHER_SUB_ID})
    return f"https://s.shopee.vn/an_redir?{query}"


def build_food_redir(link: str, affiliate_id: str, sub_id: str) -> str:
    """Link tiếp thị cho quán / món ShopeeFood. Thử 28/10/2026: an_redir mở đúng món trong app, Shopee ghi lượt
    click Food."""
    if food_url(link) != link:
        raise ValueError("food url")
    if not affiliate_id.isdigit():
        raise ValueError("affiliate id")
    if not is_valid_sub_id(sub_id):
        raise ValueError("sub id")
    query = urlencode({"origin_link": link, "affiliate_id": affiliate_id, "sub_id": sub_id})
    return f"https://s.shopee.vn/an_redir?{query}"
