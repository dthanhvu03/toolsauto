"""Lấy hàng FatCat cho đơn đang chờ và đồng bộ danh sách sản phẩm. Bot và API dùng chung.

Một đơn FatCat: bot trừ tiền khách và ghi đơn 'pending' trước (db.buy), rồi mới gọi FatCat.
- FatCat giao đủ/thiếu → complete_upstream (thiếu thì hoàn phần thiếu).
- FatCat từ chối chắc chắn → fail_upstream (hoàn đủ).
- Chưa rõ (timeout, 202, 5xx…) → để nguyên 'pending'; luồng nền gọi lại cùng request_id tới khi rõ.
"""

from __future__ import annotations

import logging

from store_bot.db import Order, Product, StoreRepository
from store_bot.upstream import DELIVERED, REJECTED, BuyResult, FatCatClient, UpstreamError, retail_price

logger = logging.getLogger("store_bot")


class Fulfiller:
    def __init__(self, repo: StoreRepository, client: FatCatClient | None, discount_bps: int = 200):
        self.repo = repo
        self.client = client
        self.discount_bps = discount_bps

    def attempt(self, order_id: int) -> tuple[Order | None, BuyResult | None, bool]:
        """Gọi FatCat một lần. Trả (đơn, kết quả FatCat, đơn vừa được chốt ở lượt này không)."""
        job = self.repo.upstream_job(order_id)
        if job is None or self.client is None:
            return self.repo.get_order(order_id), None, False
        upstream_id, quantity, request_id = job
        result = self.client.buy(upstream_id, quantity, request_id)
        if result.kind == DELIVERED:
            order, newly = self.repo.complete_upstream(order_id, result.items, result.upstream_order_id)
        elif result.kind == REJECTED:
            order, newly = self.repo.fail_upstream(order_id, f"FatCat {result.status_code}: {result.message}")
        else:
            return self.repo.get_order(order_id), result, False
        return order, result, newly

    def sync(self) -> tuple[list[tuple[Product, int]], int | None]:
        """Đồng bộ sản phẩm + số dư ví FatCat. Trả (món vừa tăng hàng, số dư). Lỗi mạng ném UpstreamError."""
        if self.client is None:
            return [], None
        restocked = self.repo.sync_upstream(self.client.products(), self.discount_bps, retail_price)
        try:
            balance = self.client.balance()
        except UpstreamError:
            logger.warning("[Store] không đọc được số dư FatCat")
            balance = None
        if balance is not None:
            self.repo.set_state("upstream_balance", str(balance))
        return restocked, balance
