"""Instagram feature — Playwright adapter (publish via dispatcher)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.instagram.adapter import InstagramAdapter

__all__ = ["InstagramAdapter"]


def __getattr__(name: str):
    if name == "InstagramAdapter":
        from app.features.instagram import adapter as _adapter

        return _adapter.InstagramAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
