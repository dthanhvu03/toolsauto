"""Feature hooks registered from composition root (main.py).

Lets core/platform/maintenance call feature code without static imports
(ADR-007: core/platform must not import features/*).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_HOOKS: Dict[str, Callable[..., Any]] = {}


def register(name: str, fn: Callable[..., Any]) -> None:
    _HOOKS[name] = fn


def call(name: str, *args: Any, **kwargs: Any) -> Any:
    fn = _HOOKS.get(name)
    if fn is None:
        raise RuntimeError(f"Feature hook '{name}' is not registered")
    return fn(*args, **kwargs)


def call_optional(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    fn = _HOOKS.get(name)
    if fn is None:
        return default
    return fn(*args, **kwargs)


def get(name: str) -> Optional[Callable[..., Any]]:
    return _HOOKS.get(name)
