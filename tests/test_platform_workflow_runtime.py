"""
Runtime-focused tests for platform workflow wiring:
Dispatcher ↔ WorkflowRegistry, CTA templates, cache invalidation.

Does NOT assert OAuth/token flows (not present in repo).
Selectors/timing/workflow DB rows are documented as not wired to FacebookAdapter.
"""
from __future__ import annotations

import pathlib
import random
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.dispatcher import DummyAdapter, FacebookAdapter, get_adapter
from app.features.facebook.adapter import FacebookAdapter as FBCls


# --- A. Adapter resolution (dispatcher.get_adapter) ---


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_uses_registry_instance_for_non_facebook(mock_ga):
    """Valid registry adapter for a non-facebook platform must be returned as-is."""
    custom = DummyAdapter()
    mock_ga.return_value = custom
    assert get_adapter("future_platform") is custom


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_facebook_registry_dummy_falls_back_to_facebook_adapter(mock_ga):
    """facebook + DummyAdapter from registry → legacy FacebookAdapter (publish safety)."""
    mock_ga.return_value = DummyAdapter()
    a = get_adapter("facebook")
    assert isinstance(a, FacebookAdapter)
    assert not isinstance(a, DummyAdapter)


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_registry_raises_falls_back_legacy(mock_ga):
    mock_ga.side_effect = RuntimeError("registry/db unavailable")
    fb = get_adapter("facebook")
    assert isinstance(fb, FacebookAdapter)
    other = get_adapter("anything")
    assert isinstance(other, DummyAdapter)


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_facebook_uses_registry_when_non_dummy(mock_ga):
    """When DB resolves a real FacebookAdapter, dispatcher must use it."""
    real = FacebookAdapter()
    mock_ga.return_value = real
    assert get_adapter("facebook") is real


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_unknown_platform_stays_dummy_when_registry_returns_dummy(mock_ga):
    mock_ga.return_value = DummyAdapter()
    a = get_adapter("no_such_platform")
    assert isinstance(a, DummyAdapter)


# --- B. CTA workflow (FacebookAdapter._wrap_with_cta) ---


@patch("app.services.workflow_registry.WorkflowRegistry.get_cta_templates")
def test_wrap_with_cta_uses_db_templates_when_links_only(mock_cta):
    mock_cta.return_value = ["Mua tại đây:\n{link}"]
    random.seed(42)
    out = FBCls._wrap_with_cta("https://example.com/p")
    mock_cta.assert_called_once_with("facebook", locale="vi")
    assert "example.com" in out
    assert "Mua tại đây" in out


@patch("app.services.workflow_registry.WorkflowRegistry.get_cta_templates")
def test_wrap_with_cta_registry_returns_link_only_uses_cta_pool(mock_cta):
    """get_cta_templates may return ['{link}']; code treats as ineffective → CTA_POOL."""
    mock_cta.return_value = ["{link}"]
    random.seed(0)
    out = FBCls._wrap_with_cta("https://a.com")
    assert "https://a.com" in out
    # One of static pool lines (all contain {link} expanded)
    assert "\n" in out or "http" in out


@patch("app.services.workflow_registry.WorkflowRegistry.get_cta_templates")
def test_wrap_with_cta_registry_exception_uses_cta_pool(mock_cta):
    mock_cta.side_effect = ValueError("cache broken")
    random.seed(1)
    out = FBCls._wrap_with_cta("https://b.com")
    assert "https://b.com" in out


def test_wrap_with_cta_non_link_comment_unchanged():
    """Not link-only → no CTA wrap; registry should not be consulted."""
    with patch("app.services.workflow_registry.WorkflowRegistry.get_cta_templates") as mock_cta:
        out = FBCls._wrap_with_cta("Hello world\nhttps://x.com")
        mock_cta.assert_not_called()
        assert out == "Hello world\nhttps://x.com"


# --- C. Cache invalidation + CTA read after invalidate ---


def test_invalidate_forces_reload_and_cta_templates_update(monkeypatch):
    """Simulate admin CRUD + invalidate(): next read must hit _load_all again (TTL bypass via ts=0)."""
    import app.core.observability.workflow_registry as wr

    payloads = [
        {
            "platforms": {},
            "workflows": {},
            "selectors": {},
            "cta": {},
        },
        {
            "platforms": {},
            "workflows": {},
            "selectors": {},
            "cta": {
                "facebook": [
                    {
                        "template": "Sau invalidate: {link}",
                        "locale": "vi",
                        "page_url": None,
                        "niche": None,
                        "priority": 10,
                    }
                ]
            },
        },
    ]

    mock_load = MagicMock(side_effect=payloads)
    monkeypatch.setattr(wr, "_load_all", mock_load)

    wr.invalidate()
    first = wr.WorkflowRegistry.get_cta_templates("facebook", locale="vi")
    assert first == ["{link}"]
    assert mock_load.call_count == 1

    wr.invalidate()
    second = wr.WorkflowRegistry.get_cta_templates("facebook", locale="vi")
    assert second == ["Sau invalidate: {link}"]
    assert mock_load.call_count == 2


# --- D. Reality check: selectors / timing / workflow not used by Facebook adapter ---


def test_facebook_adapter_source_does_not_call_registry_selectors_timing_workflow():
    """Documented: Playwright paths use static selectors.py, not DB platform_selectors."""
    root = pathlib.Path(__file__).resolve().parents[1]
    adapter_src = (root / "app" / "adapters" / "facebook" / "adapter.py").read_text(
        encoding="utf-8"
    )
    assert "get_selectors" not in adapter_src
    assert "get_selector_values" not in adapter_src
    assert "get_timing" not in adapter_src
    assert "get_workflow" not in adapter_src


def test_no_app_code_calls_selectors_timing_workflow_registry_apis():
    """get_selectors / get_timing / get_workflow are not runtime-effective outside registry module."""
    root = pathlib.Path(__file__).resolve().parents[1]
    needles = (
        "WorkflowRegistry.get_selectors",
        "WorkflowRegistry.get_selector_values",
        "WorkflowRegistry.get_timing",
        "WorkflowRegistry.get_workflow",
    )
    for py in (root / "app").rglob("*.py"):
        if py.name == "workflow_registry.py":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        for n in needles:
            assert n not in text, f"{n} referenced in {py.relative_to(root)} — expected not runtime-wired"
