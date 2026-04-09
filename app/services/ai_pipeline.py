import os
import json
import time
import re
import threading
import requests
import base64
import io
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field, ValidationError, validator

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
    hashtags: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    affiliate_keyword: str = ""
    reasoning: str = ""

    class Config:
        allow_population_by_field_name = True

    @validator('caption')
    @classmethod
    def check_generic_caption(cls, v: str) -> str:
        lower_v = v.strip().lower()
        if lower_v in ["video hay quá!", "tuyệt vời", "hay quá"]:
            raise ValueError("Caption is too generic")
        return v


class AICaptionPipeline:
    CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/config/9router_config.json"))
    RUNTIME_STATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/config/9router_runtime.json"))

    def __init__(self):
        self._config_lock = threading.Lock()
        self.circuit_breaker = CircuitBreaker(failure_ttl=1800, success_ttl=60, max_failures=3)
        
        # Load initial config
        self.enabled = True
        self.base_url = "http://localhost:20128/v1"
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
            base_url = str(data.get("base_url", "http://localhost:20128/v1"))
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
        if not has_image:
            return True
            
        VISION_SUPPORTED_PREFIXES = ["gemini-1.5", "claude-3", "gpt-4o", "gpt-4-turbo"]
        model_lower = model.lower()
        if any(prefix in model_lower for prefix in VISION_SUPPORTED_PREFIXES):
            return True
            
        # Fail fast for pure text models if we know they definitely lack vision
        if "kimi-k2" in model_lower:
            return False
            
        # If unknown, assume NOT supported to fail fast and prevent wasted requests.
        return False

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
            "max_tokens": 1500,
            "temperature": 0.5,
            "stream": False,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60.0)
            
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

    def generate_caption(self, prompt: str, image_path: Optional[str] = None) -> Tuple[Optional[CaptionPayload], dict]:
        with self._config_lock:
            is_enabled = self.enabled

        meta = {
            "status": "ok",
            "provider": "9router",
            "model": "N/A",
            "latency_ms": 0,
            "fail_reason": FailReason.NONE.value
        }

        if not is_enabled:
            meta.update({
                "status": "error",
                "provider": "native",
                "fail_reason": "router_disabled"
            })
            self._update_runtime_state("native", "N/A", 0, "disabled")
            return None, meta

        if not self.circuit_breaker.allow_request():
            meta.update({
                "status": "error",
                "provider": "poorman",
                "fail_reason": FailReason.CIRCUIT_OPEN.value
            })
            self._update_runtime_state("poorman", "N/A", 0, "circuit_open")
            return None, meta
            
        start_time = time.perf_counter()
        
        raw_text, actual_model, fail_reason = self._call_9router(prompt, image_path)
        latency = time.perf_counter() - start_time
        meta["model"] = actual_model
        meta["latency_ms"] = int(latency * 1000)
        
        if fail_reason != FailReason.NONE:
            self.circuit_breaker.record_failure()
            meta.update({
                "status": "error",
                "provider": "poorman",
                "fail_reason": fail_reason.value
            })
            self._update_runtime_state("poorman", actual_model, meta["latency_ms"], fail_reason.value)
            return None, meta
            
        self.circuit_breaker.record_success()

        parsed_payload = self._extract_and_parse_json(raw_text)
        
        if not parsed_payload:
            meta.update({
                "status": "error",
                "provider": "poorman",
                "fail_reason": FailReason.INVALID_OUTPUT.value
            })
            self._update_runtime_state("poorman", actual_model, meta["latency_ms"], "validation_failed")
            return None, meta

        self._update_runtime_state("9router", actual_model, meta["latency_ms"], "none")
        return parsed_payload, meta

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
