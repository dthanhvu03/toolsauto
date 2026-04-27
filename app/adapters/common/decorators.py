from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

P = ParamSpec("P")
R = TypeVar("R")


def playwright_safe_action(
    *,
    default: R | None = None,
    catch: tuple[type[BaseException], ...] = (PlaywrightTimeoutError, PlaywrightError),
    logger_name: str | None = None,
    message: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R | None]]:
    """Return a safe wrapper for small Playwright helper actions."""

    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            try:
                return func(*args, **kwargs)
            except catch as exc:
                log = logging.getLogger(logger_name or func.__module__)
                log.debug(message or "%s failed: %s", func.__qualname__, exc)
                return default

        return wrapper

    return decorator
