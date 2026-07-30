"""OpenRouter OpenAI-compatible fallback (free models via :free / openrouter/free).

Used when 9Router is off and native Gemini is unavailable (no key / quota).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
from typing import Optional, Tuple

import requests

import app.config as config

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    Image = None


def _resolve_api_key() -> str:
    key = (getattr(config, "OPENROUTER_API_KEY", None) or "").strip()
    if key:
        return key
    return (os.getenv("OPENROUTER_API_KEY") or "").strip()


def _base_url() -> str:
    return (
        getattr(config, "OPENROUTER_BASE_URL", None)
        or os.getenv("OPENROUTER_BASE_URL")
        or "https://openrouter.ai/api/v1"
    ).strip().rstrip("/")


def _model() -> str:
    return (
        getattr(config, "OPENROUTER_MODEL", None)
        or os.getenv("OPENROUTER_MODEL")
        or "openrouter/free"
    ).strip()


def _prepare_image_b64(image_path: str) -> Optional[str]:
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        if Image is None:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        with Image.open(image_path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.error("[OpenRouter] prepare image failed: %s", exc)
        return None


def call_openrouter(
    prompt: str, image_path: Optional[str] = None
) -> Tuple[Optional[str], dict]:
    """Chat completions via OpenRouter. Supports optional vision image."""
    meta: dict = {
        "provider": "openrouter",
        "model": "N/A",
        "latency_ms": 0,
        "ok": False,
        "fail_reason": None,
    }
    api_key = _resolve_api_key()
    if not api_key:
        meta["fail_reason"] = "no_api_key"
        logger.warning("[OpenRouter] OPENROUTER_API_KEY not set")
        return None, meta

    model = _model()
    meta["model"] = model
    content: list = [{"type": "text", "text": prompt}]
    if image_path:
        b64 = _prepare_image_b64(image_path)
        if b64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )

    url = f"{_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://toolsauto.local",
        "X-Title": "ToolsAuto",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
        "temperature": 0.5,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=(8.0, 120.0))
        meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            meta["model"] = data.get("model", model)
            if text:
                meta["ok"] = True
                meta["fail_reason"] = None
                logger.info(
                    "[OpenRouter] ok model=%s %dms", meta["model"], meta["latency_ms"]
                )
                return text, meta
            meta["fail_reason"] = "empty_response"
            return None, meta
        if resp.status_code == 429:
            meta["fail_reason"] = "rate_limited"
        elif resp.status_code in (401, 403):
            meta["fail_reason"] = "auth_error"
        else:
            meta["fail_reason"] = f"http_{resp.status_code}"
        logger.error(
            "[OpenRouter] %s: %s", meta["fail_reason"], (resp.text or "")[:240]
        )
        return None, meta
    except requests.Timeout:
        meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
        meta["fail_reason"] = "timeout"
        return None, meta
    except Exception as exc:
        meta["latency_ms"] = int((time.perf_counter() - start) * 1000)
        meta["fail_reason"] = f"error:{exc}"
        logger.error("[OpenRouter] request failed: %s", exc)
        return None, meta
