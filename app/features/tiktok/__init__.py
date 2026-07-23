"""TikTok feature — Playwright adapter (publish via dispatcher)."""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.tiktok.adapter import TiktokAdapter

__all__ = ["TiktokAdapter"]


def __getattr__(name: str):
    if name == "TiktokAdapter":
        _adapter = importlib.import_module("app.features.tiktok.adapter")
        return _adapter.TiktokAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
