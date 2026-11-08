"""
Runtime-focused tests for platform workflow wiring:
Dispatcher ↔ WorkflowRegistry, CTA templates, cache invalidation.

Does NOT assert OAuth/token flows (not present in repo).
Selectors/timing/workflow DB rows are documented as not wired to FacebookAdapter.
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch


from app.adapters.dispatcher import DummyAdapter, get_adapter


# --- A. Adapter resolution (dispatcher.get_adapter) ---


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_uses_registry_instance_for_non_facebook(mock_ga):
    """Valid registry adapter for a non-facebook platform must be returned as-is."""
    custom = DummyAdapter()
    mock_ga.return_value = custom
    assert get_adapter("future_platform") is custom








@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_unknown_platform_stays_dummy_when_registry_returns_dummy(mock_ga):
    mock_ga.return_value = DummyAdapter()
    a = get_adapter("no_such_platform")
    assert isinstance(a, DummyAdapter)


# --- B. CTA workflow (FacebookAdapter._wrap_with_cta) ---










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


@patch("app.adapters.dispatcher.WorkflowRegistry.get_adapter")
def test_dispatcher_buffer_and_removed_platforms(mock_ga):
    """PLAN-166: buffer vẫn có adapter riêng; facebook (đã gỡ đăng trực tiếp) rơi về DummyAdapter."""
    from app.features.buffer.adapter import BufferAdapter

    mock_ga.return_value = DummyAdapter()
    assert isinstance(get_adapter("buffer"), BufferAdapter)
    assert isinstance(get_adapter("facebook"), DummyAdapter)
    mock_ga.side_effect = RuntimeError("db down")
    assert isinstance(get_adapter("facebook"), DummyAdapter)
