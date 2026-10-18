import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import ai_native_fallback
from app.core.observability.ai_pipeline import AICaptionPipeline, CircuitState, FailReason


def _pipeline(monkeypatch) -> AICaptionPipeline:
    pipeline = AICaptionPipeline()
    pipeline.enabled = True
    pipeline.base_url = "http://router.test/v1"
    pipeline.api_key = "test-key"
    pipeline.default_model = "if/test-model"
    monkeypatch.setattr(pipeline, "_update_runtime_state", lambda *args, **kwargs: None)
    return pipeline


@pytest.mark.asyncio
async def test_generate_text_async_9router_success_skips_native(monkeypatch):
    pipeline = _pipeline(monkeypatch)

    async def fake_9router(prompt: str):
        assert prompt == "hello"
        return "router text", "if/async-model", FailReason.NONE

    async def fail_native(prompt: str):
        raise AssertionError("native fallback must not run when 9Router succeeds")

    monkeypatch.setattr(pipeline, "_call_9router_async", fake_9router)
    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_async",
        fail_native,
    )

    text, meta = await pipeline.generate_text_async("hello")

    assert text == "router text"
    assert meta["ok"] is True
    assert meta["provider"] == "9router"
    assert meta["model"] == "if/async-model"
    assert meta["fallback_used"] is False
    assert meta["primary_fail_reason"] is None


@pytest.mark.asyncio
async def test_generate_text_async_9router_fail_native_success(monkeypatch):
    pipeline = _pipeline(monkeypatch)

    async def fake_9router(prompt: str):
        return None, "if/test-model", FailReason.RATE_LIMITED

    async def fake_native(prompt: str):
        assert prompt == "hello"
        return "native text", {
            "provider": "native_gemini",
            "model": "gemini-2.5-flash",
            "latency_ms": 25,
            "ok": True,
            "fail_reason": None,
        }

    monkeypatch.setattr(pipeline, "_call_9router_async", fake_9router)
    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_async",
        fake_native,
    )

    text, meta = await pipeline.generate_text_async("hello")

    assert text == "native text"
    assert meta["ok"] is True
    assert meta["provider"] == "native_gemini"
    assert meta["model"] == "gemini-2.5-flash"
    assert meta["fallback_used"] is True
    assert meta["primary_fail_reason"] == "rate_limited"
    assert "fallback_failed" not in meta
    assert pipeline.circuit_breaker.consecutive_failures == 1


@pytest.mark.asyncio
async def test_generate_text_async_circuit_open_skips_9router_and_tries_native(monkeypatch):
    pipeline = _pipeline(monkeypatch)
    pipeline.circuit_breaker.state = CircuitState.OPEN
    pipeline.circuit_breaker.last_failure_time = 9_999_999_999

    async def fail_9router(prompt: str):
        raise AssertionError("9Router must not run when circuit is open")

    async def fake_native(prompt: str):
        return "fallback ok", {
            "provider": "native_gemini",
            "model": "gemini-2.5-flash",
            "latency_ms": 10,
            "ok": True,
            "fail_reason": None,
        }

    monkeypatch.setattr(pipeline, "_call_9router_async", fail_9router)
    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_async",
        fake_native,
    )

    text, meta = await pipeline.generate_text_async("hello")

    assert text == "fallback ok"
    assert meta["ok"] is True
    assert meta["fallback_used"] is True
    assert meta["primary_fail_reason"] == "circuit_open"


@pytest.mark.asyncio
async def test_generate_text_async_both_tiers_fail_returns_error_meta(monkeypatch):
    pipeline = _pipeline(monkeypatch)
    pipeline.enabled = False

    async def fake_native(prompt: str):
        return None, {
            "provider": "native_gemini",
            "model": "N/A",
            "latency_ms": 0,
            "ok": False,
            "fail_reason": "no_api_key",
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_async",
        fake_native,
    )

    text, meta = await pipeline.generate_text_async("hello")

    assert text is None
    assert meta["ok"] is False
    assert meta["fallback_used"] is True
    assert meta["fallback_failed"] is True
    assert meta["primary_fail_reason"] == "router_disabled"
    assert meta["fail_reason"] == "no_api_key"


def _stub_genai_module_async(generate_content_impl):
    fake_errors = types.ModuleType("google.genai.errors")

    class ClientError(Exception):
        def __init__(self, message="", code=None):
            super().__init__(message)
            self.code = code
            self.status_code = code

    class ServerError(Exception):
        pass

    fake_errors.ClientError = ClientError
    fake_errors.ServerError = ServerError

    class FakeAsyncModels:
        async def generate_content(self, *, model, contents):
            return await generate_content_impl(model, contents)

    class FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.aio = types.SimpleNamespace(models=FakeAsyncModels())

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.errors = fake_errors

    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai

    return fake_google, fake_genai, fake_errors


@pytest.mark.asyncio
async def test_call_native_gemini_async_uses_client_aio(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)

    calls = []

    async def gen(model, contents):
        calls.append((model, contents))
        return types.SimpleNamespace(text=f"async answer from {model}")

    fake_google, fake_genai, fake_errors = _stub_genai_module_async(gen)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)

    text, meta = await ai_native_fallback.call_native_gemini_async("hello")

    assert text.startswith("async answer from gemini-")
    assert meta["ok"] is True
    assert meta["provider"] == "native_gemini"
    assert meta["model"] in ai_native_fallback.NATIVE_TEXT_MODELS
    assert calls[0][1] == "hello"
