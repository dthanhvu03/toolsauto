"""Threads feature package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.threads.adapter import ThreadsAdapter, ThreadsSessionInvalidError

__all__ = ["ThreadsAdapter", "ThreadsSessionInvalidError"]


def __getattr__(name: str):
    if name in {"ThreadsAdapter", "ThreadsSessionInvalidError"}:
        from app.features.threads import adapter as _adapter
        return getattr(_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
