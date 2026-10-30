"""Tăng giá bán hàng FatCat: admin chỉnh trong /admin → 💲 Tăng giá bán, không phải sửa code.

Giá bán = giá lẻ FatCat (giá đại lý ÷ 0,98) + phần tăng, không bao giờ dưới giá vốn.
- Tăng theo %: làm tròn lên cho giá đẹp: 1.000đ (20.666đ +10% → 23.000đ), món dưới 10.000đ thì 100đ
  (1.000đ +10% → 1.100đ, không bị nhảy gấp đôi).
- Tăng số tiền: cộng đúng số đó.
Mức chung lưu state `markup`, mức riêng từng món `markup:<upstream_id>` (bot và API đọc chung một DB).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from store_bot.upstream import retail_price

MAX_PCT_BPS = 20_000  # +200%
MAX_VND = 5_000_000
_PCT_RE = re.compile(r"\d+(?:[.,]\d{1,2})?")


@dataclass(frozen=True)
class Markup:
    kind: str  # "pct": value = phần vạn (1000 = 10%) · "vnd": value = đồng
    value: int

    def apply(self, base: int) -> int:
        if self.kind == "pct" and self.value:
            exact = base * (10_000 + self.value)  # × 10.000
            step = 1_000 if exact >= 10_000 * 10_000 else 100
            return -(-exact // (10_000 * step)) * step
        return base + (self.value if self.kind == "vnd" else 0)

    @property
    def code(self) -> str:
        """Dạng ngắn cho callback_data / state: p1000 = +10%, v5000 = +5.000đ."""
        return f"{self.kind[0]}{self.value}"


NO_MARKUP = Markup("vnd", 0)
PRESETS = (
    NO_MARKUP, Markup("pct", 500), Markup("pct", 1_000),
    Markup("pct", 1_500), Markup("pct", 2_000), Markup("pct", 3_000),
    Markup("vnd", 2_000), Markup("vnd", 5_000), Markup("vnd", 10_000),
)


def decode(code: str | None) -> Markup | None:
    if not code or code[0] not in "pv" or not code[1:].isdigit():
        return None
    markup = Markup("pct" if code[0] == "p" else "vnd", int(code[1:]))
    limit = MAX_PCT_BPS if markup.kind == "pct" else MAX_VND
    return markup if markup.value <= limit else None


def parse(text: str, parse_amount) -> Markup | None:
    """"10%" · "7,5%" · "10" (số ≤ 100 không đơn vị hiểu là %) · "5k" · "5000" · "+5.000đ". Sai / quá mức trả None."""
    raw = (text or "").strip().lower().replace(" ", "").lstrip("+")
    number = _PCT_RE.fullmatch(raw.removesuffix("%"))
    if number and (raw.endswith("%") or float(number.group().replace(",", ".")) <= 100):
        bps = round(float(number.group().replace(",", ".")) * 100)
        return Markup("pct", bps) if bps <= MAX_PCT_BPS else None
    amount = None if raw.endswith("%") else parse_amount(raw)
    return Markup("vnd", amount) if amount is not None and amount <= MAX_VND else None


def sell_price(cost: int, discount_bps: int, markup: Markup) -> int:
    return max(markup.apply(retail_price(cost, discount_bps)), cost)


@dataclass(frozen=True)
class PriceRow:
    """Một món trong màn xem trước: giá đang bán → giá nếu áp dụng mức mới."""
    product_id: int
    name: str
    cost: int
    base: int  # giá lẻ FatCat
    price: int  # đang bán
    new_price: int
    own: Markup | None  # mức riêng của món (None = theo mức chung)
    sold: int  # số món đã giao trong kỳ
    revenue: int  # tiền khách thực trả trong kỳ
    paid_cost: int  # tiền vốn đã trả FatCat trong kỳ


@dataclass(frozen=True)
class Projection:
    sold: int
    revenue: int
    profit: int
    new_revenue: int
    new_profit: int

    @staticmethod
    def of(rows: list[PriceRow]) -> Projection:
        """Nếu kỳ tới bán đúng số món như kỳ vừa qua thì doanh thu / lãi theo giá mới là bao nhiêu."""
        revenue = sum(r.revenue for r in rows)
        return Projection(
            sold=sum(r.sold for r in rows),
            revenue=revenue,
            profit=revenue - sum(r.paid_cost for r in rows),
            new_revenue=sum(r.sold * r.new_price for r in rows),
            new_profit=sum(r.sold * (r.new_price - r.cost) for r in rows),
        )
