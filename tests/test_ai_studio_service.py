import asyncio

import pytest

from app.core.ai.brain_factory import BrainFactory
from app.core.ai.use_cases import AIUseCases
from app.features.system_panel.ai_studio_service import AIStudioService


def test_clean_json_blocks_accepts_plain_and_fenced_json():
    plain = '{"title": "ok", "hashtags": ["#a"]}'
    fence = chr(96) * 3
    fenced = f"{fence}json\n{plain}\n{fence}"

    assert BrainFactory.clean_json_blocks(plain) == plain
    assert BrainFactory.clean_json_blocks(fenced) == plain


def test_ai_studio_parses_plain_and_fenced_payloads(monkeypatch):
    fence = chr(96) * 3
    payloads = [
        '{"title": "plain", "hashtags": ["#a"]}',
        f'{fence}json\n{{"title": "fenced", "hashtags": ["#b"]}}\n{fence}',
    ]

    monkeypatch.setattr(BrainFactory, "build_caption_prompt", lambda *a, **k: "prompt")

    async def fake_generate_text_async(*args, **kwargs):
        return payloads.pop(0), {"ok": True}

    monkeypatch.setattr(AIUseCases, "generate_text_async", fake_generate_text_async)

    plain_result = asyncio.run(AIStudioService.run_test("prompt", "general"))
    fenced_result = asyncio.run(AIStudioService.run_test("prompt", "general"))

    assert plain_result == ({"title": "plain", "hashtags": ["#a"]}, None, None)
    assert fenced_result == ({"title": "fenced", "hashtags": ["#b"]}, None, None)


def test_ai_studio_malformed_json_keeps_existing_error_tuple(monkeypatch):
    fence = chr(96) * 3
    malformed = f"{fence}json\n{{bad json}}\n{fence}"
    monkeypatch.setattr(BrainFactory, "build_caption_prompt", lambda *a, **k: "prompt")

    async def fake_generate_text_async(*args, **kwargs):
        return malformed, {"ok": True}

    monkeypatch.setattr(AIUseCases, "generate_text_async", fake_generate_text_async)

    result = asyncio.run(AIStudioService.run_test("prompt", "general"))

    assert result == (None, malformed, None)


def test_ai_studio_pipeline_failure_keeps_exception_contract(monkeypatch):
    monkeypatch.setattr(BrainFactory, "build_caption_prompt", lambda *a, **k: "prompt")

    async def fail_generate_text_async(*args, **kwargs):
        raise RuntimeError("pipeline unavailable")

    monkeypatch.setattr(AIUseCases, "generate_text_async", fail_generate_text_async)

    with pytest.raises(RuntimeError, match="pipeline unavailable"):
        asyncio.run(AIStudioService.run_test("prompt", "general"))


def test_build_caption_prompt_uses_selected_persona_and_separate_test_data(
    monkeypatch,
):
    monkeypatch.setattr(
        BrainFactory, "get_visual_hook_instruction", lambda: "visual rule"
    )
    monkeypatch.setattr(
        BrainFactory, "get_engagement_secrets", lambda: "engagement rule"
    )

    prompt = BrainFactory.build_caption_prompt("SELECTED PERSONA", "beauty")

    assert "[SELECTED PERSONA]" in prompt
    assert "SELECTED PERSONA" in prompt
    assert "[SELECTED NICHE]" in prompt
    assert "beauty" in prompt
    assert "[SYNTHETIC TEST DATA — NOT PRODUCTION SOURCE]" in prompt
    assert "not a simulation" in prompt.lower()
    assert "production video/transcript pipeline" in prompt.lower()
    assert "Sản phẩm tốt nhất năm 2026! Đừng bỏ qua!" not in prompt
    assert '"title"' in prompt
    assert '"description"' in prompt
    assert '"hashtags"' in prompt


def test_ai_studio_passes_selected_persona_and_keeps_ui_result_fields(monkeypatch):
    seen = {}

    def fake_build_prompt(persona, niche):
        seen["persona"] = persona
        seen["niche"] = niche
        return "sandbox prompt"

    monkeypatch.setattr(BrainFactory, "build_caption_prompt", fake_build_prompt)

    async def fake_generate_text_async(prompt, **kwargs):
        assert prompt == "sandbox prompt"
        return (
            '{"title": "test title", "description": "test description", '
            '"hashtags": ["#test"]}',
            {"ok": True},
        )

    monkeypatch.setattr(AIUseCases, "generate_text_async", fake_generate_text_async)

    result = asyncio.run(
        AIStudioService.run_test("chosen persona", "fashion")
    )

    assert seen == {"persona": "chosen persona", "niche": "fashion"}
    assert result == (
        {"title": "test title", "description": "test description", "hashtags": ["#test"]},
        None,
        None,
    )
