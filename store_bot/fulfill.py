"""Lấy hàng FatCat cho đơn đang chờ và đồng bộ danh sách sản phẩm. Bot và API dùng chung.

Một đơn FatCat: bot trừ tiền khách và ghi đơn 'pending' trước (db.buy), rồi mới gọi FatCat.
- FatCat giao đủ/thiếu → complete_upstream (thiếu thì hoàn phần thiếu).
- FatCat từ chối chắc chắn → fail_upstream (hoàn đủ).
- Chưa rõ (timeout, 202, 5xx…) → để nguyên 'pending'; luồng nền gọi lại cùng request_id tới khi rõ.
"""

from __future__ import annotations

import logging

from store_bot import pricing
from store_bot.db import Order, Product, StoreRepository
from store_bot.pricing import Markup, PriceRow
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
        restocked = self.repo.sync_upstream(self.client.products(), self.price_for)
        try:
            balance = self.client.balance()
        except UpstreamError:
            logger.warning("[Store] không đọc được số dư FatCat")
            balance = None
        if balance is not None:
            self.repo.set_state("upstream_balance", str(balance))
        return restocked, balance

    # ---------- tăng giá bán (state `markup`, `markup:<upstream_id>`) ----------

    def global_markup(self) -> Markup:
        return pricing.decode(self.repo.get_state("markup")) or pricing.NO_MARKUP

    def own_markup(self, upstream_id: int) -> Markup | None:
        return pricing.decode(self.repo.get_state(f"markup:{upstream_id}"))

    def price_for(self, cost: int, upstream_id: int) -> int:
        return pricing.sell_price(cost, self.discount_bps, self.own_markup(upstream_id) or self.global_markup())

    def preview(self, markup: Markup | None, product_id: int | None = None, days: int = 30) -> list[PriceRow]:
        """Giá từng món FatCat nếu áp dụng `markup`: chung (product_id None, món có mức riêng giữ mức riêng)
        hoặc riêng một món (markup None = bỏ mức riêng, theo mức chung). Không ghi gì."""
        sales = self.repo.sales_by_product(days)
        rows = []
        for product in self.repo.list_products(include_inactive=True):
            if product.upstream_id is None or product.cost is None or not product.available:
                continue
            if product_id is not None and product.id != product_id:
                continue
            own = self.own_markup(product.upstream_id)
            rule = (own or markup if product_id is None else markup) or self.global_markup()
            sold, revenue, paid_cost = sales.get(product.id, (0, 0, 0))
            rows.append(PriceRow(product.id, product.name, product.cost, retail_price(product.cost, self.discount_bps),
                                 product.price, pricing.sell_price(product.cost, self.discount_bps, rule),
                                 own, sold, revenue, paid_cost))
        return rows

    def set_markup(self, markup: Markup | None, product_id: int | None = None) -> int:
        """Lưu mức tăng (chung, hoặc riêng một món; None = bỏ mức riêng) và đổi giá ngay. Trả số món đổi giá."""
        if product_id is None:
            self.repo.set_state("markup", (markup or pricing.NO_MARKUP).code)
        else:
            product = self.repo.get_product(product_id)
            if product is None or product.upstream_id is None:
                return 0
            if markup is None:
                self.repo.delete_state(f"markup:{product.upstream_id}")
            else:
                self.repo.set_state(f"markup:{product.upstream_id}", markup.code)
        return self.repo.reprice_upstream(self.price_for)
