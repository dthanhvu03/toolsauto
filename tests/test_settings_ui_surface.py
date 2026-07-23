"""PLAN-038: Settings vs AI Studio UI surface guards."""

from app.core import settings as runtime_settings


STUDIO_KEYS = frozenset(runtime_settings.AI_STUDIO_TEMPLATE_KEYS)


def test_studio_only_keys_registered():
    assert len(STUDIO_KEYS) >= 10
    for key in STUDIO_KEYS:
        spec = runtime_settings.SETTINGS[key]
        assert spec.studio_only, key


def test_settings_ui_excludes_studio_keys():
    grouped = runtime_settings.list_specs_for_settings_ui()
    visible = {spec.key for specs in grouped.values() for spec in specs}
    overlap = visible & STUDIO_KEYS
    assert not overlap, f"studio keys leaked to settings UI: {sorted(overlap)}"


def test_threads_prompt_studio_only():
    spec = runtime_settings.SETTINGS["THREADS_AI_PROMPT"]
    assert spec.studio_only
    assert "THREADS_AI_PROMPT" in STUDIO_KEYS
