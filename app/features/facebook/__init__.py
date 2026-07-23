"""Facebook feature — publish, pages UI, media prep, engagement, strategic boost (via core)."""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.facebook.adapter import FacebookAdapter, PageMismatchError
    from app.features.facebook.media_processor import MediaProcessor

__all__ = [
    "FacebookAdapter",
    "PageMismatchError",
    "MediaProcessor",
    "pages_router",
    "manual_job_router",
]


def __getattr__(name: str):
    if name in {"FacebookAdapter", "PageMismatchError"}:
        _adapter = importlib.import_module("app.features.facebook.adapter")
        return getattr(_adapter, name)
    if name == "MediaProcessor":
        _mp = importlib.import_module("app.features.facebook.media_processor")
        return _mp.MediaProcessor
    if name == "pages_router":
        return importlib.import_module("app.features.facebook.pages_router")
    if name == "manual_job_router":
        return importlib.import_module("app.features.facebook.manual_job_router")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
