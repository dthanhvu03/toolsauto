"""Báo tiến độ xử lý video — tách khỏi Telegram (contextvar).

Ai quan tâm (Telegram, log, test) gắn callback qua ``progress_scope``.
Pipeline chỉ gọi ``report_stage("download")`` — không import notifier.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]

_progress_cb: ContextVar[Optional[ProgressCallback]] = ContextVar(
    "viral_process_progress", default=None
)

# Nhãn cố định — Owner đọc được; không phải % giả.
STAGE_LABELS: dict[str, str] = {
    "start": "chuẩn bị…",
    "download": "đang tải video…",
    "reup": "đang cắt / xử lý…",
    "caption": "đang viết caption…",
    "notify": "đang gửi video…",
    "done": "xong",
    "failed": "lỗi",
}


def report_stage(stage: str) -> None:
    """Gọi từ pipeline. Không có listener ⇒ no-op (worker nền / web)."""
    cb = _progress_cb.get()
    if cb is None:
        return
    try:
        cb(stage)
    except Exception:
        logger.debug("[progress] listener lỗi ở stage=%s", stage, exc_info=True)


@contextmanager
def progress_scope(callback: ProgressCallback) -> Iterator[None]:
    token = _progress_cb.set(callback)
    try:
        yield
    finally:
        _progress_cb.reset(token)
