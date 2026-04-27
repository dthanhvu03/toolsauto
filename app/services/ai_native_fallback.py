"""Native Gemini fallback used by AICaptionPipeline when 9Router is unavailable.

Per ADR-006: this is the ONLY place in the codebase that imports `google.genai`
for the canonical text path. `ai_pipeline.py` delegates here — it must NOT
import `google.genai` directly. Keeps the dual-SDK complexity isolated.

The module is text-only by design. Vision / async paths still live in
`gemini_api.py` (legacy, deprecated) and will be migrated separately.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import app.config as config

logger = logging.getLogger(__name__)

# Models tried in order. Tier list mirrors gemini_api.py for consistency.
NATIVE_TEXT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro",
    "gemini-pro-latest",
]

# Vision-capable subset (must support multimodal input).
NATIVE_VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]

COOLDOWN_SECONDS = 60

# Module-level cooldown state. Shared between text and vision paths because
# rate-limiting is per-model on Google's side regardless of modality.
_model_cooldowns: dict[str, float] = {}


def _is_available(model_name: str) -> bool:
    return time.time() > _model_cooldowns.get(model_name, 0)


def _set_cooldown(model_name: str) -> None:
    _model_cooldowns[model_name] = time.time() + COOLDOWN_SECONDS
    logger.warning(
        "[AI FALLBACK] %s rate-limited; cooldown %ss", model_name, COOLDOWN_SECONDS
    )


def _available_models() -> list[str]:
    avail = [m for m in NATIVE_TEXT_MODELS if _is_available(m)]
    if not avail:
        logger.warning("[AI FALLBACK] All models in cooldown; resetting")
        _model_cooldowns.clear()
        return list(NATIVE_TEXT_MODELS)
    return avail


def call_native_gemini(prompt: str) -> Tuple[Optional[str], dict]:
    """Send a text-only prompt to Google Gemini directly via google-genai.

    Returns (text, meta). Caller (AICaptionPipeline) is responsible for
    composing this into the unified meta with fallback_used=True.

    meta keys: provider, model, latency_ms, ok, fail_reason
    """
    meta: dict = {
        "provider": "native_gemini",
        "model": "N/A",
        "latency_ms": 0,
        "ok": False,
        "fail_reason": None,
    }

    api_key = getattr(config, "GEMINI_API_KEY", None)
    if not api_key:
        meta["fail_reason"] = "no_api_key"
        logger.warning("[AI FALLBACK] GEMINI_API_KEY not set; native fallback disabled")
        return None, meta

    try:
        # Lazy import — keeps top-level import time low and confirms google.genai
        # is only loaded when fallback actually fires.
        from google import genai
        from google.genai import errors as genai_errors
    except ImportError as exc:
        meta["fail_reason"] = f"sdk_not_installed:{exc}"
        logger.error("[AI FALLBACK] google.genai SDK not installed: %s", exc)
        return None, meta

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        meta["fail_reason"] = f"client_init_error:{exc}"
        logger.error("[AI FALLBACK] Failed to init genai.Client: %s", exc)
        return None, meta

    start = time.perf_counter()
    last_error: Optional[Exception] = None

    for model_name in _available_models():
        try:
            logger.info("[AI FALLBACK] Trying %s", model_name)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            if response and getattr(response, "text", None):
                meta["model"] = model_name
                meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
                meta["ok"] = True
                meta["fail_reason"] = None
                logger.info(
                    "[AI FALLBACK] %s succeeded in %dms", model_name, meta["latency_ms"]
                )
                return response.text, meta

            # Empty response → try next model
            last_error = RuntimeError(f"{model_name} returned empty response")
            continue

        except genai_errors.ClientError as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code == 429:
                _set_cooldown(model_name)
                last_error = exc
                continue
            if code == 404:
                last_error = exc
                continue
            last_error = exc
            break  # Auth or unknown client error — stop rotating
        except genai_errors.ServerError as exc:
            last_error = exc
            continue
        except Exception as exc:  # pragma: no cover (defensive)
            last_error = exc
            break

    meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
    meta["fail_reason"] = (
        "all_models_exhausted" if last_error is None else f"native_error:{last_error}"
    )
    logger.error(
        "[AI FALLBACK] All native models failed (last_error=%s)", last_error
    )
    return None, meta


async def call_native_gemini_async(prompt: str) -> Tuple[Optional[str], dict]:
    """Async text-only native Gemini fallback using google-genai client.aio.

    This mirrors call_native_gemini but awaits the SDK's async client path so
    async workers do not block the event loop while Tier 2 fallback runs.
    """
    meta: dict = {
        "provider": "native_gemini",
        "model": "N/A",
        "latency_ms": 0,
        "ok": False,
        "fail_reason": None,
    }

    api_key = getattr(config, "GEMINI_API_KEY", None)
    if not api_key:
        meta["fail_reason"] = "no_api_key"
        logger.warning("[AI FALLBACK ASYNC] GEMINI_API_KEY not set; native fallback disabled")
        return None, meta

    try:
        from google import genai
        from google.genai import errors as genai_errors
    except ImportError as exc:
        meta["fail_reason"] = f"sdk_not_installed:{exc}"
        logger.error("[AI FALLBACK ASYNC] google.genai SDK not installed: %s", exc)
        return None, meta

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        meta["fail_reason"] = f"client_init_error:{exc}"
        logger.error("[AI FALLBACK ASYNC] Failed to init genai.Client: %s", exc)
        return None, meta

    start = time.perf_counter()
    last_error: Optional[Exception] = None

    for model_name in _available_models():
        try:
            logger.info("[AI FALLBACK ASYNC] Trying %s", model_name)
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            if response and getattr(response, "text", None):
                meta["model"] = model_name
                meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
                meta["ok"] = True
                meta["fail_reason"] = None
                logger.info(
                    "[AI FALLBACK ASYNC] %s succeeded in %dms",
                    model_name,
                    meta["latency_ms"],
                )
                return response.text, meta

            last_error = RuntimeError(f"{model_name} returned empty response")
            continue

        except genai_errors.ClientError as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code == 429:
                _set_cooldown(model_name)
                last_error = exc
                continue
            if code == 404:
                last_error = exc
                continue
            last_error = exc
            break
        except genai_errors.ServerError as exc:
            last_error = exc
            continue
        except Exception as exc:  # pragma: no cover (defensive)
            last_error = exc
            break

    meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
    meta["fail_reason"] = (
        "all_models_exhausted" if last_error is None else f"native_error:{last_error}"
    )
    logger.error(
        "[AI FALLBACK ASYNC] All native models failed (last_error=%s)", last_error
    )
    return None, meta


def call_native_gemini_vision(
    prompt: str, image_path: str
) -> Tuple[Optional[str], dict]:
    """Send a multimodal prompt (text + image) to Google Gemini directly.

    Mirrors `call_native_gemini` for the vision path. Used by
    `AICaptionPipeline.generate_caption` as Tier 2 when 9Router fails.

    Returns (text, meta). Caller is responsible for parsing the JSON content
    from the returned text — this module returns raw text exactly like 9Router
    so the pipeline's `_extract_and_parse_json` can be reused.

    meta keys: provider, model, latency_ms, ok, fail_reason
    """
    meta: dict = {
        "provider": "native_gemini_vision",
        "model": "N/A",
        "latency_ms": 0,
        "ok": False,
        "fail_reason": None,
    }

    api_key = getattr(config, "GEMINI_API_KEY", None)
    if not api_key:
        meta["fail_reason"] = "no_api_key"
        logger.warning(
            "[AI FALLBACK VISION] GEMINI_API_KEY not set; native vision fallback disabled"
        )
        return None, meta

    if not image_path or not _path_exists(image_path):
        meta["fail_reason"] = f"image_not_found:{image_path}"
        logger.error("[AI FALLBACK VISION] Image not found: %s", image_path)
        return None, meta

    try:
        # Lazy imports — google.genai and PIL only loaded when fallback fires.
        # ADR-006 isolation rule: this is the ONLY module that imports google.genai
        # for the canonical vision path; ai_pipeline.py must not import it directly.
        from google import genai
        from google.genai import errors as genai_errors
        from PIL import Image
    except ImportError as exc:
        meta["fail_reason"] = f"sdk_not_installed:{exc}"
        logger.error("[AI FALLBACK VISION] SDK not installed: %s", exc)
        return None, meta

    try:
        image_obj = Image.open(image_path)
    except Exception as exc:
        meta["fail_reason"] = f"image_open_error:{exc}"
        logger.error("[AI FALLBACK VISION] Failed to open image %s: %s", image_path, exc)
        return None, meta

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        meta["fail_reason"] = f"client_init_error:{exc}"
        logger.error("[AI FALLBACK VISION] Failed to init genai.Client: %s", exc)
        return None, meta

    start = time.perf_counter()
    last_error: Optional[Exception] = None

    # Filter to vision-capable models, then drop any in cooldown.
    candidates = [m for m in NATIVE_VISION_MODELS if _is_available(m)]
    if not candidates:
        logger.warning(
            "[AI FALLBACK VISION] All vision models in cooldown; resetting"
        )
        for m in NATIVE_VISION_MODELS:
            _model_cooldowns.pop(m, None)
        candidates = list(NATIVE_VISION_MODELS)

    for model_name in candidates:
        try:
            logger.info("[AI FALLBACK VISION] Trying %s with %s", model_name, image_path)
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_obj],
            )

            if response and getattr(response, "text", None):
                meta["model"] = model_name
                meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
                meta["ok"] = True
                meta["fail_reason"] = None
                logger.info(
                    "[AI FALLBACK VISION] %s succeeded in %dms",
                    model_name,
                    meta["latency_ms"],
                )
                return response.text, meta

            last_error = RuntimeError(f"{model_name} returned empty response")
            continue

        except genai_errors.ClientError as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code == 429:
                _set_cooldown(model_name)
                last_error = exc
                continue
            if code == 404:
                last_error = exc
                continue
            last_error = exc
            break  # Auth or unknown client error — stop rotating
        except genai_errors.ServerError as exc:
            last_error = exc
            continue
        except Exception as exc:  # pragma: no cover (defensive)
            last_error = exc
            break

    meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
    meta["fail_reason"] = (
        "all_vision_models_exhausted"
        if last_error is None
        else f"native_vision_error:{last_error}"
    )
    logger.error(
        "[AI FALLBACK VISION] All vision models failed (last_error=%s)", last_error
    )
    return None, meta


def _path_exists(p: str) -> bool:
    """Tiny indirection so tests can monkeypatch path checks without touching os."""
    import os
    return os.path.exists(p)
