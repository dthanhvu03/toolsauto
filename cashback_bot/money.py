"""Tiền VND nguyên và tỷ lệ hoàn. Tỷ lệ do người gọi truyền vào."""

from __future__ import annotations


def estimated_cashback(commission_vnd: int, rate_percent: int) -> int:
    if commission_vnd < 0 or not 0 <= rate_percent <= 100:
        raise ValueError("commission hoặc tỷ lệ không hợp lệ")
    return (commission_vnd * rate_percent) // 100


def format_vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"
