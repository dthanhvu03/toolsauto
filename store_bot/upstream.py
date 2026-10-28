"""Client API FatCat Store (nguồn hàng). Tài liệu: https://api.fatcatstore.click/docs

Quy tắc an toàn tiền theo tài liệu FatCat:
- Mỗi lượt mua gửi một request_id riêng. Gọi lại cùng request_id không bao giờ bị trừ tiền lần hai.
- Timeout, lỗi mạng, 429, 5xx, 202 đều KHÔNG có nghĩa là thất bại: để đơn ở trạng thái chờ và gọi lại
  cùng request_id. Chỉ 400/401/402/404/409 mới là bị từ chối chắc chắn (FatCat không trừ tiền).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

logger = logging.getLogger("store_bot")

DELIVERED = "delivered"
PENDING = "pending"
REJECTED = "rejected"
# Mã HTTP mà FatCat cam kết là từ chối nguyên lượt, không trừ tiền.
REJECT_STATUSES = {400, 401, 402, 404, 409}


@dataclass(frozen=True)
class BuyResult:
    kind: str
    items: list[str] = field(default_factory=list)
    upstream_order_id: str | None = None
    price: int | None = None
    status_code: int | None = None
    message: str = ""


class UpstreamError(Exception):
    pass


def retail_price(cost: int, discount_bps: int) -> int:
    """Giá lẻ FatCat = giá FatCat cho đại lý ÷ (1 − mức giảm đại lý), làm tròn tới đồng.
    151.900 ÷ 0,98 = 155.000 · 20.253 ÷ 0,98 = 20.666 (khớp giá kênh FatCat)."""
    base = 10_000 - discount_bps
    return (cost * 10_000 + base // 2) // base


class FatCatClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 40):
        # FatCat giữ kết nối mua tối đa 25 giây rồi trả 202: chờ ngắn hơn 30 giây là mất cả 202 lẫn hàng.
        self._base = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key}
        self._timeout = timeout

    def _get(self, path: str) -> dict:
        try:
            response = requests.get(f"{self._base}{path}", headers=self._headers, timeout=20)
        except requests.RequestException as exc:
            raise UpstreamError(type(exc).__name__) from exc
        if response.status_code != 200:
            raise UpstreamError(f"http {response.status_code}: {_message(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("không phải JSON") from exc

    def products(self) -> list[dict]:
        products = self._get("/api/products").get("products")
        if not isinstance(products, list):
            raise UpstreamError("thiếu products")
        return products

    def balance(self) -> int:
        return int(self._get("/api/balance").get("balance_vnd") or 0)

    def buy(self, product_id: int, quantity: int, request_id: str) -> BuyResult:
        body = {"product_id": product_id, "quantity": quantity, "request_id": request_id}
        try:
            response = requests.post(f"{self._base}/api/buy", json=body, headers=self._headers,
                                     timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("[Store] FatCat buy %s lỗi mạng: %s", request_id, type(exc).__name__)
            return BuyResult(PENDING, message=type(exc).__name__)
        code = response.status_code
        if code in REJECT_STATUSES:
            return BuyResult(REJECTED, status_code=code, message=_message(response))
        if code not in (200, 202):
            # 429, 5xx: chưa biết đơn đã tạo chưa → gọi lại cùng request_id sau.
            return BuyResult(PENDING, status_code=code, message=_message(response))
        try:
            order = response.json().get("order") or {}
        except ValueError:
            return BuyResult(PENDING, status_code=code, message="không phải JSON")
        items = [str(item) for item in order.get("items") or []]
        fulfillment = order.get("fulfillment") or ("complete" if code == 200 else "pending")
        if code == 202 or fulfillment == "pending":
            return BuyResult(PENDING, items, order.get("id"), order.get("price"), code)
        return BuyResult(DELIVERED, items, order.get("id"), order.get("price"), code, fulfillment)


def _message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    return str(payload.get("message") or payload.get("detail") or "")[:200]
