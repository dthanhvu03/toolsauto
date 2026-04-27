"""Shared helpers for all model modules in this package.

Re-exports `Base` from `app.database.core` so domain modules don't have to
reach across packages. Keep this file minimal — no domain models here.
"""
import time

from app.database.core import Base  # noqa: F401  (re-exported)


def now_ts() -> int:
    return int(time.time())
