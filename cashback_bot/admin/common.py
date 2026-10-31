"""Hằng số và hàm nhỏ dùng chung giữa AdminPanel và các handler /admin (không đọc DB)."""

from __future__ import annotations

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from cashback_bot.admin.handlers.reserve import ACCOUNT_KINDS, AppliedReserve, stamp
from cashback_bot.messages import BotReply
from cashback_bot.pricing import CashbackQuote

__all__ = [
    "AdminSafetyError",
    "CONFIRM_TTL",
    "DIRECTIONAL_BPS",
    "ICT",
    "NUMBER",
    "SAMPLE_VND",
    "TIERS",
    "TIER_EMOJI",
    "expired_button",
    "kind_label",
    "percent",
    "split",
    "stamp",
]

CONFIRM_TTL = timedelta(minutes=10)
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
TIERS = {"BRONZE": "Đồng", "SILVER": "Bạc", "GOLD": "Vàng"}
TIER_EMOJI = {"BRONZE": "🥉", "SILVER": "🥈", "GOLD": "🥇"}
DIRECTIONAL_BPS = {"BRONZE": 6_000, "SILVER": 6_500, "GOLD": 7_000}
SAMPLE_VND = 100_000
# Admin gõ phần trăm: "10", "0,98", "0.98", "62,5%". Lưu nội bộ bằng bps.
NUMBER = re.compile(r"^(\d{1,3})(?:[.,](\d{1,2}))?\s*%?$")


class AdminSafetyError(RuntimeError):
    pass


def percent(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def split(quote: CashbackQuote) -> tuple[int, int]:
    return quote.cashback_vnd, quote.remainder_vnd


def kind_label(reserve: AppliedReserve) -> str | None:
    return ACCOUNT_KINDS.get(reserve.account_kind or "")


def expired_button() -> BotReply:
    """Callback không khớp nút nào còn dùng (nút cũ, dữ liệu lạ)."""
    return BotReply("Nút này không còn hiệu lực.")
