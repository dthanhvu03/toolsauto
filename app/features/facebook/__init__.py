"""Facebook feature — publish, pages UI, media prep, engagement, strategic boost (via core)."""

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
        from app.features.facebook import adapter as _adapter

        return getattr(_adapter, name)
    if name == "MediaProcessor":
        from app.features.facebook import media_processor as _mp

        return _mp.MediaProcessor
    if name == "pages_router":
        from app.features.facebook import pages_router as _mod

        return _mod
    if name == "manual_job_router":
        from app.features.facebook import manual_job_router as _mod

        return _mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
