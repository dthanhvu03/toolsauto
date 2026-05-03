import os
import json
import time
import re
import threading
import asyncio
import requests
import httpx
import base64
import io
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field, ValidationError, field_validator, ConfigDict
from app import config

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class FailReason(str, Enum):
    NONE = "none"
    TEMPORARY_NETWORK = "temporary_network_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    VISION_NOT_SUPPORTED = "vision_not_supported"
    INVALID_OUTPUT = "invalid_output"
    CIRCUIT_OPEN = "circuit_open"

class CircuitBreaker:
    def __init__(self, failure_ttl: int = 15, success_ttl: int = 60, max_failures: int = 5):
        self._lock = threading.Lock()
        self.failure_ttl = failure_ttl
        self.success_ttl = success_ttl
        self.max_failures = max_failures
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0.0
        self.consecutive_failures = 0

    def allow_request(self) -> bool:
        with self._lock:
            now = time.time()
            if self.state == CircuitState.CLOSED:
                return True
                
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.failure_ttl:
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
                
            if self.state == CircuitState.HALF_OPEN:
                return False
                
            return False

    def record_success(self):
        with self._lock:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0

    def record_failure(self):
        with self._lock:
            self.consecutive_failures += 1
            self.last_failure_time = time.time()
            if self.consecutive_failures >= self.max_failures:
                self.state = CircuitState.OPEN


class CaptionPayload(BaseModel):
    caption: str
    hashtags: Optional[List[str]] = Field(default_factory=list)
    keywords: Optional[List[str]] = Field(default_factory=list)
    affiliate_keyword: Optional[str] = ""
    reasoning: Optional[str] = ""

    model_config = ConfigDict(populate_by_name=True)

    @field_validator('caption')
    @classmethod
    def check_generic_caption(cls, v: str) -> str:
        lower_v = v.strip().lower()
        if lower_v in ["video hay quá!", "tuyệt vời", "hay quá"]:
            raise ValueError("Caption is too generic")
        return v


class AICaptionPipeline:
    CONFIG_PATH = str(config.DATA_DIR / "config" / "9router_config.json")
    RUNTIME_STATE_PATH = str(config.DATA_DIR / "config" / "9router_runtime.json")

    def __init__(self):
        self._config_lock = threading.Lock()
        self.circuit_breaker = CircuitBreaker(failure_ttl=1800, success_ttl=60, max_failures=3)
        
        # Load initial config
        default_router_url = config.ROUTER_BASE_URL
        self.enabled = True
        self.base_url = default_router_url
        self.api_key = ""
        self.default_model = "if/gemini-1.5-flash"
        
        # Tracking states
        self.last_latency_ms = 0
        self.last_provider = "N/A"
        self.last_model = "N/A"
        self.last_fail_reason = "none"

        self.reload_config()

    def _get_masked_key(self) -> str:
        with self._config_lock:
            if not self.api_key:
                return ""
            if len(self.api_key) > 8:
                return self.api_key[:8] + "••••••••"
            return "••••••••"

    def reload_config(self) -> bool:
        if not os.path.exists(self.CONFIG_PATH):
            return False
            
        try:
            with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            enabled = bool(data.get("enabled", True))
            default_router_url = config.ROUTER_BASE_URL
            base_url = str(data.get("base_url", default_router_url))
            api_key = str(data.get("api_key", ""))
            default_model = str(data.get("default_model", "if/gemini-1.5-flash"))
            
            with self._config_lock:
                self.enabled = enabled
                self.base_url = base_url
                if api_key and not api_key.endswith("••••••••"):
                    self.api_key = api_key
                self.default_model = default_model
                
            return True
        except Exception:
            return False

    def test_connection(self, temp_base_url: str, temp_api_key: str, temp_model: str) -> dict:
        start_time = time.perf_counter()
        url = temp_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {temp_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": temp_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 10,
            "stream": False,
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10.0)
            latency = int((time.perf_counter() - start_time) * 1000)
            
            if resp.status_code == 200:
                data = resp.json()
                mdl = data.get("model", temp_model)
                # Write to shared file so Syspanel shows real data immediately
                self._update_runtime_state("9router", mdl, latency, "none")
                return {"ok": True, "message": "Connection successful", "latency_ms": latency, "model": mdl}
            elif resp.status_code in [401, 403]:
                self._update_runtime_state("9router", temp_model, 0, "auth_error")
                return {"ok": False, "message": "Authentication failed", "fail_reason": f"unauthorized (HTTP {resp.status_code})"}
            else:
                self._update_runtime_state("9router", temp_model, 0, f"http_{resp.status_code}")
                return {"ok": False, "message": f"Server responded with {resp.status_code}", "fail_reason": resp.text[:200]}
        except requests.Timeout:
            return {"ok": False, "message": "Connection timed out", "fail_reason": "timeout"}
        except Exception as e:
            return {"ok": False, "message": "Connection error", "fail_reason": str(e)}

    def _prepare_image(self, image_path: str) -> Optional[str]:
        if not image_path or not os.path.exists(image_path):
            return None
            
        if not Image:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
                
        try:
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error("Error preparing image base64: %s", e)
            return None

    def _check_vision_compatibility(self, model: str, has_image: bool) -> bool:
        # Cho phép mọi model thoải mái xử lý ảnh (bỏ cơ chế lọc theo yêu cầu của user)
        return True

    def _extract_and_parse_json(self, raw_text: str) -> Optional[CaptionPayload]:
        if not raw_text:
            return None
            
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        extracted_text = json_match.group(1) if json_match else raw_text
        
        start = extracted_text.find('{')
        end = extracted_text.rfind('}')
        if start == -1 or end == -1 or start >= end:
            return None
            
        clean_json_str = extracted_text[start:end+1]
        try:
            data_dict = json.loads(clean_json_str)
            return CaptionPayload(**data_dict)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("JSON Error parsing output: %s", e)
            return None

    def _call_9router(self, prompt: str, image_path: Optional[str] = None) -> Tuple[Optional[str], Optional[str], FailReason]:
        with self._config_lock:
            temp_model = self.default_model
            temp_api_key = self.api_key
            temp_base_url = self.base_url

        has_image = bool(image_path and os.path.exists(image_path))
        if not self._check_vision_compatibility(temp_model, has_image):
            return None, temp_model, FailReason.VISION_NOT_SUPPORTED
            
        messages = [{"role": "user", "content": []}]
        
        # 9Router OpenAI format: Text first, then images
        messages[0]["content"].append({"type": "text", "text": prompt})
        
        if has_image:
            b64_img = self._prepare_image(image_path)
            if b64_img:
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}"
                    }
                })

        url = temp_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {temp_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": temp_model,
            "messages": messages,
            "max_tokens": 4096,  # Reasoning models need extra budget for thinking tokens
            "temperature": 0.5,
            "stream": False,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120.0)
            
            if resp.status_code == 200:
                data = resp.json()
                raw_out = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                actual_model = data.get("model", temp_model)
                return raw_out, actual_model, FailReason.NONE
            elif resp.status_code == 429:
                return None, temp_model, FailReason.RATE_LIMITED
            elif resp.status_code in [401, 403]:
                return None, temp_model, FailReason.AUTH_ERROR
            else:
                logger.error("Server API returned %s: %s", resp.status_code, resp.text[:200])
                return None, temp_model, FailReason.TEMPORARY_NETWORK
        except requests.Timeout:
            return None, temp_model, FailReason.TIMEOUT
        except Exception as e:
            logger.error("Request generation error: %s", e)
            return None, temp_model, FailReason.TEMPORARY_NETWORK

    async def _call_9router_async(self, prompt: str) -> Tuple[Optional[str], Optional[str], FailReason]:
        with self._config_lock:
            temp_model = self.default_model
            temp_api_key = self.api_key
            temp_base_url = self.base_url

        url = temp_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {temp_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": temp_model,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "max_tokens": 4096,
            "temperature": 0.5,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                data = resp.json()
                raw_out = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                actual_model = data.get("model", temp_model)
                return raw_out, actual_model, FailReason.NONE
            if resp.status_code == 429:
                return None, temp_model, FailReason.RATE_LIMITED
            if resp.status_code in [401, 403]:
                return None, temp_model, FailReason.AUTH_ERROR

            logger.error("Server API returned %s: %s", resp.status_code, resp.text[:200])
            return None, temp_model, FailReason.TEMPORARY_NETWORK
        except httpx.TimeoutException:
            return None, temp_model, FailReason.TIMEOUT
        except Exception as e:
            logger.error("Async request generation error: %s", e)
            return None, temp_model, FailReason.TEMPORARY_NETWORK

    def generate_caption(self, prompt: str, image_path: Optional[str] = None) -> Tuple[Optional[CaptionPayload], dict]:
        """Generate caption JSON with 9Router → Native Gemini Vision fallback (PLAN-025).

        Tier 1: 9Router (canonical, multimodal).
        Tier 2: Native Gemini vision via `app.services.ai_native_fallback.call_native_gemini_vision`.
                Only fires when an image is provided AND Tier 1 fails (router disabled,
                circuit open, HTTP error, or output validation failure).
        Tier 3 does not exist — caller (orchestrator) decides what to do (RPA, poorman).

        meta always contains:
            status, provider, model, latency_ms, fail_reason,
            fallback_used, primary_fail_reason
        """
        with self._config_lock:
            is_enabled = self.enabled

        meta = {
            "status": "ok",
            "provider": "9router",
            "model": "N/A",
            "latency_ms": 0,
            "fail_reason": FailReason.NONE.value,
            "fallback_used": False,
            "primary_fail_reason": None,
        }

        # Try Tier 1 — 9Router. We track its outcome in `primary_fail_reason`
        # so we can switch to Tier 2 with full provenance.
        primary_fail: Optional[str] = None
        actual_model = "N/A"
        latency_ms = 0
        raw_text: Optional[str] = None

        if not is_enabled:
            primary_fail = "router_disabled"
        elif not self.circuit_breaker.allow_request():
            primary_fail = FailReason.CIRCUIT_OPEN.value
        else:
            start_time = time.perf_counter()
            raw_text, actual_model, fail_reason = self._call_9router(prompt, image_path)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            meta["model"] = actual_model
            meta["latency_ms"] = latency_ms

            if fail_reason != FailReason.NONE:
                self.circuit_breaker.record_failure()
                primary_fail = fail_reason.value
            else:
                self.circuit_breaker.record_success()
                parsed_payload = self._extract_and_parse_json(raw_text)
                if parsed_payload:
                    self._update_runtime_state("9router", actual_model, latency_ms, "none")
                    return parsed_payload, meta
                # 9Router responded but JSON parse failed — treat as primary fail
                # and let native vision try (it may produce a parseable response).
                primary_fail = FailReason.INVALID_OUTPUT.value

        # Tier 1 failed. Try native vision fallback only when an image is present —
        # text-only callers should use generate_text() which has its own fallback.
        if not image_path:
            self._update_runtime_state("poorman", actual_model, latency_ms, primary_fail or "no_image")
            meta.update({
                "status": "error",
                "provider": "poorman",
                "fail_reason": primary_fail or "no_image_for_vision_fallback",
                "primary_fail_reason": primary_fail,
            })
            return None, meta

        logger.warning(
            "[AI FALLBACK] generate_caption Tier 1 failed (reason=%s); switching to native vision",
            primary_fail,
        )
        # Lazy import — pipeline must NOT import google.genai directly (ADR-006).
        from app.services.ai_native_fallback import call_native_gemini_vision

        native_start = time.perf_counter()
        native_text, native_meta = call_native_gemini_vision(prompt, image_path)
        native_latency = native_meta.get("latency_ms") or int((time.perf_counter() - native_start) * 1000)

        if native_meta.get("ok") and native_text:
            parsed_payload = self._extract_and_parse_json(native_text)
            if parsed_payload:
                meta.update({
                    "status": "ok",
                    "provider": native_meta.get("provider", "native_gemini_vision"),
                    "model": native_meta.get("model", "N/A"),
                    "latency_ms": native_latency,
                    "fail_reason": FailReason.NONE.value,
                    "fallback_used": True,
                    "primary_fail_reason": primary_fail,
                })
                self._update_runtime_state(
                    "native_gemini_vision", meta["model"], native_latency, "fallback_ok"
                )
                return parsed_payload, meta
            # Native returned text but JSON invalid — treat as native failure.
            native_fail_reason = FailReason.INVALID_OUTPUT.value
        else:
            native_fail_reason = native_meta.get("fail_reason") or "native_vision_failed"

        # Both tiers failed.
        meta.update({
            "status": "error",
            "provider": "poorman",
            "model": native_meta.get("model", actual_model),
            "latency_ms": native_latency,
            "fail_reason": native_fail_reason,
            "fallback_used": True,
            "fallback_failed": True,
            "primary_fail_reason": primary_fail,
        })
        self._update_runtime_state(
            "poorman", meta["model"], native_latency, f"both_tiers_failed:{native_fail_reason}"
        )
        logger.error(
            "[AI FALLBACK] generate_caption both tiers failed (primary=%s, native=%s)",
            primary_fail,
            native_fail_reason,
        )
        return None, meta

    def _update_runtime_state(self, provider: str, model: str, latency: int, fail_reason: str):
        with self._config_lock:
            self.last_provider = provider
            self.last_model = model
            self.last_latency_ms = latency
            self.last_fail_reason = fail_reason

        # Persist to shared file so Web_Dashboard (separate PM2 process) can read it
        try:
            state = {
                "provider": provider,
                "model": model,
                "latency_ms": latency,
                "fail_reason": fail_reason,
                "circuit_state": self.circuit_breaker.state.value,
                "ts": int(time.time()),
            }
            os.makedirs(os.path.dirname(self.RUNTIME_STATE_PATH), exist_ok=True)
            tmp_path = self.RUNTIME_STATE_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.replace(tmp_path, self.RUNTIME_STATE_PATH)
        except Exception:
            pass  # Best-effort, don't crash the pipeline

    def generate_text(self, prompt: str) -> Tuple[Optional[str], dict]:
        """Call 9Router with native-Gemini fallback (per ADR-006).

        Tier 1: 9Router (canonical).
        Tier 2: Native Gemini via `app.services.ai_native_fallback` — only if
                Tier 1 fails AND fallback is permitted (router disabled,
                circuit open, or 9Router HTTP error all qualify).
        Tier 3 does not exist: if both fail, return error meta and let the
                caller decide what to do (worker may use RPA or poorman).

        meta always contains:
            ok, provider, model, latency_ms, fallback_used, primary_fail_reason
        And on failure:
            fail_reason, fallback_failed
        """
        with self._config_lock:
            is_enabled = self.enabled

        # Try Tier 1 — 9Router
        primary_fail_reason: Optional[str] = None
        primary_meta: dict = {
            "provider": "9router",
            "model": "N/A",
            "latency_ms": 0,
            "ok": True,
            "fallback_used": False,
            "primary_fail_reason": None,
        }

        if not is_enabled:
            primary_fail_reason = "router_disabled"
        elif not self.circuit_breaker.allow_request():
            primary_fail_reason = "circuit_open"
        else:
            start_time = time.perf_counter()
            raw_text, actual_model, fail_reason = self._call_9router(prompt)
            primary_meta["model"] = actual_model
            primary_meta["latency_ms"] = int((time.perf_counter() - start_time) * 1000)

            if fail_reason == FailReason.NONE:
                self.circuit_breaker.record_success()
                self._update_runtime_state("9router", actual_model, primary_meta["latency_ms"], "none")
                return raw_text, primary_meta

            self.circuit_breaker.record_failure()
            self._update_runtime_state("poorman", actual_model, primary_meta["latency_ms"], fail_reason.value)
            primary_fail_reason = fail_reason.value

        # Tier 1 failed. Log explicitly and try Tier 2.
        logger.warning(
            "[AI FALLBACK] 9Router failed (reason=%s); switching to native Gemini",
            primary_fail_reason,
        )
        # Lazy import to keep ai_pipeline.py free of google.genai (per ADR-006 isolation).
        from app.services.ai_native_fallback import call_native_gemini

        native_start = time.perf_counter()
        native_text, native_meta = call_native_gemini(prompt)
        # Compose unified meta — preserve primary failure reason for observability.
        merged: dict = {
            "provider": native_meta.get("provider", "native_gemini"),
            "model": native_meta.get("model", "N/A"),
            "latency_ms": native_meta.get("latency_ms", int((time.perf_counter() - native_start) * 1000)),
            "fallback_used": True,
            "primary_fail_reason": primary_fail_reason,
        }

        if native_meta.get("ok") and native_text:
            merged["ok"] = True
            self._update_runtime_state(
                "native_gemini", merged["model"], merged["latency_ms"], "fallback_ok"
            )
            return native_text, merged

        # Both tiers failed — final fail.
        merged["ok"] = False
        merged["fail_reason"] = native_meta.get("fail_reason") or "native_fallback_failed"
        merged["fallback_failed"] = True
        logger.error(
            "[AI FALLBACK] Both tiers failed (primary=%s, native=%s)",
            primary_fail_reason,
            merged["fail_reason"],
        )
        return None, merged

    async def generate_text_async(self, prompt: str) -> Tuple[Optional[str], dict]:
        """Async version of generate_text for background workers.

        Keeps the same 2-tier contract as generate_text:
        9Router -> native Gemini -> fail. No google.genai import lives in this
        module; native SDK calls stay isolated in ai_native_fallback.py.
        """
        with self._config_lock:
            is_enabled = self.enabled

        primary_fail_reason: Optional[str] = None
        primary_meta: dict = {
            "provider": "9router",
            "model": "N/A",
            "latency_ms": 0,
            "ok": True,
            "fallback_used": False,
            "primary_fail_reason": None,
        }

        if not is_enabled:
            primary_fail_reason = "router_disabled"
        elif not self.circuit_breaker.allow_request():
            primary_fail_reason = "circuit_open"
        else:
            start_time = time.perf_counter()
            raw_text, actual_model, fail_reason = await self._call_9router_async(prompt)
            primary_meta["model"] = actual_model
            primary_meta["latency_ms"] = int((time.perf_counter() - start_time) * 1000)

            if fail_reason == FailReason.NONE:
                self.circuit_breaker.record_success()
                await asyncio.to_thread(
                    self._update_runtime_state,
                    "9router",
                    actual_model,
                    primary_meta["latency_ms"],
                    "none",
                )
                return raw_text, primary_meta

            self.circuit_breaker.record_failure()
            await asyncio.to_thread(
                self._update_runtime_state,
                "poorman",
                actual_model,
                primary_meta["latency_ms"],
                fail_reason.value,
            )
            primary_fail_reason = fail_reason.value

        logger.warning(
            "[AI FALLBACK ASYNC] 9Router failed (reason=%s); switching to native Gemini",
            primary_fail_reason,
        )
        from app.services.ai_native_fallback import call_native_gemini_async

        native_start = time.perf_counter()
        native_text, native_meta = await call_native_gemini_async(prompt)
        merged: dict = {
            "provider": native_meta.get("provider", "native_gemini"),
            "model": native_meta.get("model", "N/A"),
            "latency_ms": native_meta.get("latency_ms", int((time.perf_counter() - native_start) * 1000)),
            "fallback_used": True,
            "primary_fail_reason": primary_fail_reason,
        }

        if native_meta.get("ok") and native_text:
            merged["ok"] = True
            await asyncio.to_thread(
                self._update_runtime_state,
                "native_gemini",
                merged["model"],
                merged["latency_ms"],
                "fallback_ok",
            )
            return native_text, merged

        merged["ok"] = False
        merged["fail_reason"] = native_meta.get("fail_reason") or "native_fallback_failed"
        merged["fallback_failed"] = True
        logger.error(
            "[AI FALLBACK ASYNC] Both tiers failed (primary=%s, native=%s)",
            primary_fail_reason,
            merged["fail_reason"],
        )
        return None, merged

    @classmethod
    def load_shared_runtime_state(cls) -> dict:
        """Read runtime state written by AI_Generator process (cross-PM2 IPC via file)."""
        try:
            if os.path.exists(cls.RUNTIME_STATE_PATH):
                with open(cls.RUNTIME_STATE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
