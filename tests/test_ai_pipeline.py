import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.observability.ai_pipeline import AICaptionPipeline, CircuitState


class DummyResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _pipeline(monkeypatch) -> AICaptionPipeline:
    pipeline = AICaptionPipeline()
    pipeline.enabled = True
    pipeline.base_url = "http://router.test/v1"
    pipeline.api_key = "test-key"
    pipeline.default_model = "if/test-model"
    monkeypatch.setattr(pipeline, "_update_runtime_state", lambda *args, **kwargs: None)
    return pipeline


def _disable_native_fallback(monkeypatch):
    """Stub native fallback to a fixed failure — used by tests that do NOT
    want to exercise the fallback path. Returns the call counter so tests can
    assert whether the fallback was invoked."""
    calls = {"count": 0}

    def fake_native(prompt: str):
        calls["count"] += 1
        return None, {
            "provider": "native_gemini",
            "model": "N/A",
            "latency_ms": 0,
            "ok": False,
            "fail_reason": "no_api_key",
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini", fake_native
    )
    return calls


def test_generate_text_http_200_returns_text_and_ok_meta(monkeypatch):
    pipeline = _pipeline(monkeypatch)
    native_calls = _disable_native_fallback(monkeypatch)

    def fake_post(url, headers, json, timeout):
        assert url == "http://router.test/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "if/test-model"
        assert json["messages"][0]["content"][0]["text"] == "hello"
        assert timeout == 120.0
        return DummyResponse(
            200,
            {
                "model": "if/mock-model",
                "choices": [{"message": {"content": "mock response"}}],
            },
        )

    monkeypatch.setattr("app.services.ai_pipeline.requests.post", fake_post)

    text, meta = pipeline.generate_text("hello")

    assert text == "mock response"
    assert meta["ok"] is True
    assert meta["model"] == "if/mock-model"
    assert meta["provider"] == "9router"
    assert meta["fallback_used"] is False
    assert meta["primary_fail_reason"] is None
    assert pipeline.circuit_breaker.consecutive_failures == 0
    # ADR-006 contract: native fallback must NOT be called when 9Router succeeds.
    assert native_calls["count"] == 0


def test_generate_text_http_429_records_circuit_failure_and_invokes_fallback(monkeypatch):
    """ADR-006: 9Router 429 → triggers native fallback. With native disabled
    (no API key) we should still get a unified failure meta with both flags."""
    pipeline = _pipeline(monkeypatch)
    native_calls = _disable_native_fallback(monkeypatch)
    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *args, **kwargs: DummyResponse(429, text="rate limited"),
    )

    text, meta = pipeline.generate_text("hello")

    assert text is None
    assert meta["ok"] is False
    assert meta["fallback_used"] is True
    assert meta["fallback_failed"] is True
    assert meta["primary_fail_reason"] == "rate_limited"
    assert meta["fail_reason"] == "no_api_key"  # from stubbed native
    # 9Router still recorded its own failure for circuit breaker.
    assert pipeline.circuit_breaker.consecutive_failures == 1
    assert pipeline.circuit_breaker.state == CircuitState.CLOSED
    assert native_calls["count"] == 1


def test_generate_text_disabled_still_tries_native_fallback(monkeypatch):
    """Even when 9Router is disabled, native fallback gets a chance per ADR-006."""
    pipeline = _pipeline(monkeypatch)
    pipeline.enabled = False
    native_calls = _disable_native_fallback(monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("requests.post must not be called when router is disabled")

    monkeypatch.setattr("app.services.ai_pipeline.requests.post", fail_if_called)

    text, meta = pipeline.generate_text("hello")

    assert text is None
    assert meta["ok"] is False
    assert meta["fallback_used"] is True
    assert meta["primary_fail_reason"] == "router_disabled"
    assert native_calls["count"] == 1


def test_generate_text_9router_fail_native_success_marks_fallback_used(monkeypatch):
    """ADR-006 happy fallback path: 9Router fails, native succeeds → caller gets
    text + fallback_used=True so UI/Telegram can surface the FALLBACK badge."""
    pipeline = _pipeline(monkeypatch)
    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *args, **kwargs: DummyResponse(500, text="upstream error"),
    )

    def fake_native(prompt: str):
        assert prompt == "hello"
        return "native-generated text", {
            "provider": "native_gemini",
            "model": "gemini-2.5-flash",
            "latency_ms": 42,
            "ok": True,
            "fail_reason": None,
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini", fake_native
    )

    text, meta = pipeline.generate_text("hello")

    assert text == "native-generated text"
    assert meta["ok"] is True
    assert meta["fallback_used"] is True
    assert meta["provider"] == "native_gemini"
    assert meta["model"] == "gemini-2.5-flash"
    assert meta["primary_fail_reason"] == "temporary_network_error"
    # Should NOT have fallback_failed when native succeeded.
    assert "fallback_failed" not in meta


def test_generate_text_circuit_open_does_not_call_9router_but_tries_native(monkeypatch):
    """Circuit breaker open → skip 9Router, still try native (ADR-006 cap 2 tier)."""
    pipeline = _pipeline(monkeypatch)
    # Force the circuit open
    pipeline.circuit_breaker.state = CircuitState.OPEN
    pipeline.circuit_breaker.last_failure_time = 9_999_999_999  # far future

    def fail_if_called(*args, **kwargs):
        raise AssertionError("requests.post must NOT be called when circuit is OPEN")

    monkeypatch.setattr("app.services.ai_pipeline.requests.post", fail_if_called)

    def fake_native(prompt: str):
        return "fallback ok", {
            "provider": "native_gemini",
            "model": "gemini-2.5-flash",
            "latency_ms": 10,
            "ok": True,
            "fail_reason": None,
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini", fake_native
    )

    text, meta = pipeline.generate_text("hello")

    assert text == "fallback ok"
    assert meta["fallback_used"] is True
    assert meta["primary_fail_reason"] == "circuit_open"


# ===================== generate_caption (vision) — PLAN-025 =====================


def _disable_native_vision(monkeypatch):
    calls = {"count": 0}

    def fake_native_vision(prompt: str, image_path: str):
        calls["count"] += 1
        return None, {
            "provider": "native_gemini_vision",
            "model": "N/A",
            "latency_ms": 0,
            "ok": False,
            "fail_reason": "no_api_key",
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_vision", fake_native_vision
    )
    return calls


def _9router_caption_response(model: str = "if/vision-mock"):
    return DummyResponse(
        200,
        {
            "model": model,
            "choices": [
                {
                    "message": {
                        "content": (
                            '```json\n'
                            '{"caption": "9R caption", "hashtags": ["#a"], '
                            '"keywords": ["k"], "affiliate_keyword": null, '
                            '"reasoning": "ok"}\n'
                            '```'
                        )
                    }
                }
            ],
        },
    )


def test_generate_caption_9router_success_no_fallback(monkeypatch, tmp_path):
    pipeline = _pipeline(monkeypatch)
    native_calls = _disable_native_vision(monkeypatch)
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")  # minimal jpeg-ish bytes

    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *a, **kw: _9router_caption_response(),
    )
    # Bypass actual image-to-base64 conversion — we don't need real PIL roundtrip
    monkeypatch.setattr(pipeline, "_prepare_image", lambda p: "FAKE_B64")
    monkeypatch.setattr(pipeline, "_check_vision_compatibility", lambda m, has: True)

    payload, meta = pipeline.generate_caption("describe", str(img))

    assert payload is not None
    assert payload.caption == "9R caption"
    assert meta["status"] == "ok"
    assert meta["provider"] == "9router"
    assert meta["fallback_used"] is False
    assert meta["primary_fail_reason"] is None
    assert native_calls["count"] == 0


def test_generate_caption_9router_fail_native_vision_succeeds(monkeypatch, tmp_path):
    """ADR-006 + PLAN-025: 9Router fail → native vision returns parseable JSON."""
    pipeline = _pipeline(monkeypatch)
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")

    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *a, **kw: DummyResponse(500, text="upstream"),
    )
    monkeypatch.setattr(pipeline, "_prepare_image", lambda p: "FAKE_B64")
    monkeypatch.setattr(pipeline, "_check_vision_compatibility", lambda m, has: True)

    def fake_native_vision(prompt: str, image_path: str):
        assert prompt == "describe"
        assert image_path == str(img)
        return (
            '{"caption": "native vision caption", "hashtags": ["#x"], '
            '"keywords": ["k"], "affiliate_keyword": null, "reasoning": "fb"}'
        ), {
            "provider": "native_gemini_vision",
            "model": "gemini-2.5-flash",
            "latency_ms": 88,
            "ok": True,
            "fail_reason": None,
        }

    monkeypatch.setattr(
        "app.services.ai_native_fallback.call_native_gemini_vision", fake_native_vision
    )

    payload, meta = pipeline.generate_caption("describe", str(img))

    assert payload is not None
    assert payload.caption == "native vision caption"
    assert meta["status"] == "ok"
    assert meta["fallback_used"] is True
    assert meta["provider"] == "native_gemini_vision"
    assert meta["model"] == "gemini-2.5-flash"
    assert meta["primary_fail_reason"] == "temporary_network_error"
    assert "fallback_failed" not in meta


def test_generate_caption_both_tiers_fail_returns_error_meta(monkeypatch, tmp_path):
    pipeline = _pipeline(monkeypatch)
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")

    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *a, **kw: DummyResponse(429, text="rate limit"),
    )
    monkeypatch.setattr(pipeline, "_prepare_image", lambda p: "FAKE_B64")
    monkeypatch.setattr(pipeline, "_check_vision_compatibility", lambda m, has: True)
    _disable_native_vision(monkeypatch)

    payload, meta = pipeline.generate_caption("describe", str(img))

    assert payload is None
    assert meta["status"] == "error"
    assert meta["fallback_used"] is True
    assert meta["fallback_failed"] is True
    assert meta["primary_fail_reason"] == "rate_limited"
    assert meta["fail_reason"] == "no_api_key"


def test_generate_caption_no_image_skips_native_vision(monkeypatch):
    """Native vision is only sensible with an image. If caller passes no image and
    Tier 1 fails, do NOT try native vision — return primary failure verbatim."""
    pipeline = _pipeline(monkeypatch)
    native_calls = _disable_native_vision(monkeypatch)

    monkeypatch.setattr(
        "app.services.ai_pipeline.requests.post",
        lambda *a, **kw: DummyResponse(500, text="upstream"),
    )
    monkeypatch.setattr(pipeline, "_check_vision_compatibility", lambda m, has: True)

    payload, meta = pipeline.generate_caption("describe (no image)", image_path=None)

    assert payload is None
    assert meta["status"] == "error"
    assert meta["primary_fail_reason"] == "temporary_network_error"
    # Native vision must NOT be invoked when there is no image to send.
    assert native_calls["count"] == 0


def test_extract_and_parse_json_valid_and_invalid(monkeypatch):
    pipeline = _pipeline(monkeypatch)

    parsed = pipeline._extract_and_parse_json(
        '```json\n{"caption": "Nội dung tốt", "hashtags": null, "keywords": null}\n```'
    )
    invalid = pipeline._extract_and_parse_json("không có json hợp lệ")

    assert parsed is not None
    assert parsed.caption == "Nội dung tốt"
    assert parsed.hashtags is None
    assert parsed.keywords is None
    assert invalid is None
