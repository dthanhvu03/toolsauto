"""Instagram feature — Playwright adapter (publish via dispatcher)."""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.instagram.adapter import InstagramAdapter

__all__ = ["InstagramAdapter"]


def __getattr__(name: str):
    if name == "InstagramAdapter":
        _adapter = importlib.import_module("app.features.instagram.adapter")
        return _adapter.InstagramAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
