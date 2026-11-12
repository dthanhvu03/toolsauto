"""Kéo khách sang món hoàn cao (PLAN-169). Công tắc admin ở 🔥 Deal hời.

- C: thẻ link món có phần shop góp (XTRA) thêm một dòng nhắc mua đúng món, đúng shop — khách mua món / shop khác thì
  phần shop góp mất, chỉ còn hoa hồng Shopee ~2,5% (đối chiếu đơn 10–11/2026: 4/9 đơn có link mất XTRA vì vậy).
- B: 🔥 Deal hời xếp theo tổng tiết kiệm, món hoàn cao có nhãn (deals.py).
"""

from __future__ import annotations

from cashback_bot.db import TrackingRepository

XTRA_NOTE_KEY = "xtra_card_note_enabled"  # chưa có = bật; admin tắt thì "0"


def xtra_note_enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(XTRA_NOTE_KEY) != "0"


def shows_xtra_note(seller_commission_vnd: int | None, cashback_vnd: int) -> bool:
    """Thẻ có hoàn và có phần shop góp mới nhắc; món chỉ có hoa hồng Shopee giữ thẻ như cũ."""
    return cashback_vnd > 0 and (seller_commission_vnd or 0) > 0


# B: 🔥 Deal hời xếp theo tổng tiết kiệm = (giá thường − giá nay) + số hoàn, chia giá thường; món hoàn từ 4% giá có
# nhãn. Hoa hồng Shopee thường (2,5%) chia khách chỉ ~1,5% giá, nên ≥ 4% gần như chắc là món có XTRA.
SAVING_RANK_KEY = "deals_rank_by_saving"  # chưa có = bật; admin tắt thì "0" (xếp lại theo % rẻ hơn như cũ)
HIGH_CASHBACK_BPS = 400
HIGH_BADGE = " · 🔥 hoàn cao"


def saving_rank_enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(SAVING_RANK_KEY) != "0"


def deal_rank(deal: dict, by_saving: bool) -> float:
    """Khoá sắp xếp, nhỏ trước. by_saving: tổng tiết kiệm cao trước; không thì giá / giá thường thấp trước."""
    usual = deal["usual"] or 1
    if by_saving:
        return -(usual - deal["price"] + deal.get("cashback", 0)) / usual
    return deal["price"] / usual


def high_cashback(deal: dict) -> bool:
    return deal["price"] > 0 and deal.get("cashback", 0) * 10_000 >= deal["price"] * HIGH_CASHBACK_BPS
