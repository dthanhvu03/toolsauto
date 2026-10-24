"""Che bí mật trước khi ghi log hoặc lưu bản ghi lỗi (hardening P1-8).

Lỗi của `requests` thường chứa URL đầy đủ, ví dụ `.../bot<TOKEN>/editMessageText`. Mọi chuỗi
lỗi đi qua `redact` trước khi ra log; formatter của process cũng che lại lần nữa (phòng sót).
"""

from __future__ import annotations

import logging
import re

MASK = "***"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Token Telegram: <bot id>:<35 ký tự>, có hoặc không có tiền tố /bot.
    (re.compile(r"(/bot)?\d{6,12}:[A-Za-z0-9_-]{30,}"), r"\1" + MASK),
    # Cookie Shopee (SPC_EC, SPC_ST, …) và mọi header Cookie / Set-Cookie.
    (re.compile(r"\b(SPC_[A-Z0-9_]+)=[^;\s'\"]+"), r"\1=" + MASK),
    (re.compile(r"(?i)\b((?:set-)?cookie)\s*[:=]\s*[^\r\n]+"), r"\1: " + MASK),
    # Authorization, API key trong header hoặc query string.
    (re.compile(r"(?i)\b(authorization)\s*[:=]\s*[^\r\n,]+"), r"\1: " + MASK),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|access[_-]?token|token|secret)=([^&\s'\"]+)"), r"\1=" + MASK),
)


def redact(text: object) -> str:
    """Chuỗi đã che token, cookie, API key. Không bao giờ ném lỗi."""
    try:
        value = str(text)
    except Exception:
        return "<unprintable>"
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def error_brief(exc: BaseException, limit: int = 200) -> str:
    """`Loại lỗi: thông điệp đã che`, cắt ngắn. Dùng cho log và bản ghi update lỗi."""
    message = redact(exc)[:limit]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


class RedactingFormatter(logging.Formatter):
    """Che bí mật trên dòng log cuối cùng, kể cả traceback."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return redact(super().format(record))
        except Exception:
            return f"{record.levelname} <log format failed>"
