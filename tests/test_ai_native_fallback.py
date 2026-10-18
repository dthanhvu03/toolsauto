"""Tests for app/services/ai_native_fallback.py.

We don't import google.genai directly in tests — instead we patch the lazy
imports inside `call_native_gemini` so the test never hits a live API.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from app.services import ai_native_fallback


@pytest.fixture(autouse=True)
def _reset_cooldowns():
    ai_native_fallback._model_cooldowns.clear()
    yield
    ai_native_fallback._model_cooldowns.clear()


def test_call_native_gemini_no_api_key_returns_disabled(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", None, raising=False)

    text, meta = ai_native_fallback.call_native_gemini("hello")

    assert text is None
    assert meta["ok"] is False
    assert meta["fail_reason"] == "no_api_key"
    assert meta["provider"] == "native_gemini"


def _stub_genai_module(generate_content_impl):
    """Build a fake `google.genai` module so the lazy import inside
    call_native_gemini resolves to it. Returns (genai_module, errors_module)."""
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

    class FakeModels:
        def generate_content(self, *, model, contents):
            return generate_content_impl(model, contents)

    class FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = FakeModels()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.errors = fake_errors

    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai

    return fake_google, fake_genai, fake_errors


def test_call_native_gemini_first_model_succeeds(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)

    def gen(model, contents):
        # Return on first call
        return types.SimpleNamespace(text=f"answer from {model}")

    fake_google, fake_genai, fake_errors = _stub_genai_module(gen)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)

    text, meta = ai_native_fallback.call_native_gemini("hello")

    assert text.startswith("answer from gemini-")
    assert meta["ok"] is True
    assert meta["model"] in ai_native_fallback.NATIVE_TEXT_MODELS
    assert meta["provider"] == "native_gemini"
    assert meta["fail_reason"] is None


def test_call_native_gemini_429_rotates_then_succeeds(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)

    call_log = []

    # Build error class first so we can raise it inside the closure.
    fake_google, fake_genai, fake_errors = _stub_genai_module(lambda m, c: None)
    ClientError = fake_errors.ClientError

    def gen(model, contents):
        call_log.append(model)
        if model == ai_native_fallback.NATIVE_TEXT_MODELS[0]:
            raise ClientError("quota exceeded", code=429)
        return types.SimpleNamespace(text="recovered")

    # Replace the FakeModels' generate_content with the new impl
    fake_genai.Client = type(
        "FakeClient",
        (),
        {
            "__init__": lambda self, api_key=None: setattr(self, "models", types.SimpleNamespace(generate_content=lambda *, model, contents: gen(model, contents))),
        },
    )

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)

    text, meta = ai_native_fallback.call_native_gemini("hello")

    assert text == "recovered"
    assert meta["ok"] is True
    # First model should have been put on cooldown after the 429
    assert ai_native_fallback.NATIVE_TEXT_MODELS[0] in ai_native_fallback._model_cooldowns
    # We tried at least 2 models
    assert len(call_log) >= 2


def _stub_pil_module(monkeypatch):
    """Inject a fake PIL.Image module so call_native_gemini_vision can lazy-import it."""
    class FakeImage:
        @staticmethod
        def open(path):
            return types.SimpleNamespace(_path=path, size=(640, 480))

    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = FakeImage
    fake_pil_image = types.ModuleType("PIL.Image")
    fake_pil_image.open = FakeImage.open
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image)


# ===================== Vision path tests =====================

def test_call_native_gemini_vision_no_api_key_returns_disabled(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", None, raising=False)

    text, meta = ai_native_fallback.call_native_gemini_vision("describe this", "/tmp/x.jpg")

    assert text is None
    assert meta["ok"] is False
    assert meta["fail_reason"] == "no_api_key"
    assert meta["provider"] == "native_gemini_vision"


def test_call_native_gemini_vision_image_not_found_returns_error(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)
    # Force _path_exists to return False
    monkeypatch.setattr(ai_native_fallback, "_path_exists", lambda p: False)

    text, meta = ai_native_fallback.call_native_gemini_vision("describe", "/nonexistent.jpg")

    assert text is None
    assert meta["ok"] is False
    assert meta["fail_reason"].startswith("image_not_found:")


def test_call_native_gemini_vision_first_model_succeeds(monkeypatch):
    """Happy path: vision-capable model returns text on first try, both prompt
    and image are forwarded to generate_content."""
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(ai_native_fallback, "_path_exists", lambda p: True)

    captured_calls = []

    def gen(model, contents):
        captured_calls.append((model, contents))
        return types.SimpleNamespace(text=f'{{"caption": "from {model}"}}')

    fake_google, fake_genai, fake_errors = _stub_genai_module(gen)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)
    _stub_pil_module(monkeypatch)

    text, meta = ai_native_fallback.call_native_gemini_vision(
        "describe the image", "/tmp/sample.jpg"
    )

    assert text is not None
    assert "caption" in text
    assert meta["ok"] is True
    assert meta["provider"] == "native_gemini_vision"
    # Vision must use a vision-capable model, not a text-only one
    assert meta["model"] in ai_native_fallback.NATIVE_VISION_MODELS
    # Verify both prompt and image were passed to generate_content
    model_used, contents = captured_calls[0]
    assert contents[0] == "describe the image"
    # contents[1] is the PIL Image stub
    assert getattr(contents[1], "_path", None) == "/tmp/sample.jpg"


def test_call_native_gemini_vision_429_rotates_to_next_vision_model(monkeypatch):
    """429 on vision-model[0] → cooldown + try next vision-capable model."""
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(ai_native_fallback, "_path_exists", lambda p: True)

    fake_google, fake_genai, fake_errors = _stub_genai_module(lambda m, c: None)
    ClientError = fake_errors.ClientError
    call_log = []

    def gen(model, contents):
        call_log.append(model)
        if model == ai_native_fallback.NATIVE_VISION_MODELS[0]:
            raise ClientError("quota", code=429)
        return types.SimpleNamespace(text='{"caption": "recovered"}')

    fake_genai.Client = type(
        "FakeClient",
        (),
        {
            "__init__": lambda self, api_key=None: setattr(
                self, "models",
                types.SimpleNamespace(generate_content=lambda *, model, contents: gen(model, contents))
            ),
        },
    )
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)
    _stub_pil_module(monkeypatch)

    text, meta = ai_native_fallback.call_native_gemini_vision("p", "/tmp/x.jpg")

    assert text == '{"caption": "recovered"}'
    assert meta["ok"] is True
    assert ai_native_fallback.NATIVE_VISION_MODELS[0] in ai_native_fallback._model_cooldowns
    # Verify it actually rotated to a different model
    assert meta["model"] != ai_native_fallback.NATIVE_VISION_MODELS[0]
    assert len(call_log) >= 2


def test_call_native_gemini_all_models_fail(monkeypatch):
    monkeypatch.setattr(ai_native_fallback.config, "GEMINI_API_KEY", "test-key", raising=False)

    fake_google, fake_genai, fake_errors = _stub_genai_module(lambda m, c: None)
    ClientError = fake_errors.ClientError

    def gen(model, contents):
        raise ClientError("server error", code=500)

    fake_genai.Client = type(
        "FakeClient",
        (),
        {
            "__init__": lambda self, api_key=None: setattr(self, "models", types.SimpleNamespace(generate_content=lambda *, model, contents: gen(model, contents))),
        },
    )
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)

    text, meta = ai_native_fallback.call_native_gemini("hello")

    assert text is None
    assert meta["ok"] is False
    assert meta["fail_reason"].startswith("native_error:")
    assert meta["provider"] == "native_gemini"
