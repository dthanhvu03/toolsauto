import time
import logging
import os
import app.config as config
from PIL import Image
from google import genai
from google.genai import errors as genai_errors
from app.constants import JobStatus
from typing import Optional

logger = logging.getLogger(__name__)

# Tier list — verified available via genai.list_models()
GEMINI_TEXT_MODELS = [
    "gemini-2.5-flash",      # Fastest, latest
    "gemini-2.0-flash",      # Stable, reliable
    "gemini-2.0-flash-lite",  # Lightweight fallback
    "gemini-2.5-pro",        # Most capable
    "gemini-pro-latest",     # Legacy fallback
]

# Only multimodal-capable models
GEMINI_MULTIMODAL_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]

COOLDOWN_SECONDS = 60  # Skip rate-limited model for 60s

# Module-level cooldown state
_model_cooldowns: dict[str, float] = {}

def _is_available(model_name: str) -> bool:
    """Return True if model is not in cooldown."""
    return time.time() > _model_cooldowns.get(model_name, 0)

def _set_cooldown(model_name: str) -> None:
    """Mark model as rate-limited for COOLDOWN_SECONDS."""
    _model_cooldowns[model_name] = time.time() + COOLDOWN_SECONDS
    logger.warning(
        f"🔥 [Gemini Rotation] {model_name} rate-limited. "
        f"Cooldown until {COOLDOWN_SECONDS}s from now."
    )

def _get_available_models(model_list: list[str]) -> list[str]:
    """Return models not in cooldown. If all cooling down, return full list."""
    available = [m for m in model_list if _is_available(m)]
    if not available:
        logger.warning("⚠️ All Gemini models in cooldown. Resetting and retrying.")
        _model_cooldowns.clear()
        return model_list
    return available

class GeminiAPIService:
    """
    Stateless API service wrapper for Google's Generative AI.
    Used selectively when the primary RPA mechanism fails.
    """
    def __init__(self):
        try:
            if getattr(config, 'GEMINI_API_KEY', None):
                self.client = genai.Client(api_key=config.GEMINI_API_KEY)
                self.is_configured = True
            else:
                self.is_configured = False
                self.client = None
                logger.warning("GEMINI_API_KEY chưa được cài đặt trong .env. Tính năng dự phòng API Fallback bị vô hiệu hoá.")
        except Exception as e:
            self.is_configured = False
            self.client = None
            logger.warning(f"Lỗi khi khởi tạo Google Generative AI: {e}")

    def ask(self, prompt: str, **kwargs) -> str | None:
        """Send text prompt with automatic model rotation on 429."""
        if not self.is_configured or not self.client:
            logger.error("GeminiAPIService chưa sẵn sàng.")
            return None

        models = _get_available_models(GEMINI_TEXT_MODELS)
        last_error = None

        logger.info("🔥 [API Fallback] Đang gửi text prompt lên API (có rotation support)")
        t0 = time.time()

        for model_name in models:
            try:
                logger.info(f"[Gemini] Using model: {model_name}")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=kwargs
                )
                
                if response and response.text:
                    logger.info(f"🔥 [Gemini] Trả kết quả thành công qua {model_name} (%.1fs)", time.time() - t0)
                    return response.text
                return None

            except genai_errors.ClientError as e:
                # 429 = Resource Exhausted
                if e.status_code == 429:
                    logger.warning(
                        f"🔥 [Gemini Rotation] {model_name} quota exceeded. "
                        f"Switching to next model."
                    )
                    _set_cooldown(model_name)
                    last_error = e
                    continue
                # 404 = Not Found
                elif e.status_code == 404:
                    logger.warning(
                        f"⚠️ [Gemini] {model_name} not available (404), "
                        f"skipping to next model."
                    )
                    last_error = e
                    continue
                else:
                    logger.error(f"❌ [Gemini] {model_name} client error: {e}")
                    last_error = e
                    break

            except genai_errors.ServerError as e:
                logger.warning(f"⚠️ [Gemini] {model_name} server unavailable: {e}")
                last_error = e
                continue

            except Exception as e:
                logger.error(f"❌ [Gemini] {model_name} unexpected error: {e}")
                last_error = e
                break

        raise RuntimeError(f"Tất cả các model Gemini đều thất bại. Lỗi cuối cùng: {last_error}")

    async def ask_async(self, prompt: str, **kwargs) -> str | None:
        """Async version of ask(). Uses google.genai async client with rotation."""
        if not self.is_configured or not self.client:
            logger.error("GeminiAPIService chưa sẵn sàng.")
            return None

        models = _get_available_models(GEMINI_TEXT_MODELS)
        last_error = None

        logger.info("🔥 [API Fallback Async] Đang gửi text prompt lên API (có rotation support)")
        t0 = time.time()

        for model_name in models:
            try:
                logger.info(f"[Gemini Async] Using model: {model_name}")
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=kwargs
                )
                
                if response and response.text:
                    logger.info(f"🔥 [Gemini Async] Trả kết quả thành công qua {model_name} (%.1fs)", time.time() - t0)
                    return response.text
                return None

            except genai_errors.ClientError as e:
                if e.status_code == 429:
                    logger.warning(
                        f"🔥 [Gemini Rotation Async] {model_name} quota exceeded. "
                        f"Switching to next model."
                    )
                    _set_cooldown(model_name)
                    last_error = e
                    continue
                elif e.status_code == 404:
                    logger.warning(
                        f"⚠️ [Gemini Async] {model_name} not available (404), skipping..."
                    )
                    last_error = e
                    continue
                else:
                    logger.error(f"❌ [Gemini Async] {model_name} client error: {e}")
                    last_error = e
                    break

            except genai_errors.ServerError as e:
                logger.warning(f"⚠️ [Gemini Async] {model_name} server unavailable: {e}")
                last_error = e
                continue

            except Exception as e:
                logger.error(f"❌ [Gemini Async] {model_name} unexpected error: {e}")
                last_error = e
                break

        raise RuntimeError(f"Tất cả các model Gemini Async đều thất bại. Lỗi cuối cùng: {last_error}")

    def ask_with_file(self, prompt: str, file_path: str, **kwargs) -> str | None:
        """Send multimodal prompt with automatic model rotation on 429."""
        if not self.is_configured or not self.client:
            logger.error("GeminiAPIService chưa sẵn sàng.")
            return None

        if not os.path.exists(file_path):
            logger.error(f"File input không tồn tại: {file_path}")
            return None

        models = _get_available_models(GEMINI_MULTIMODAL_MODELS)
        last_error = None
        t0 = time.time()

        try:
            lower_path = file_path.lower()
            uploaded_content = None
            is_video = not lower_path.endswith(('.jpg', '.jpeg', '.png', '.webp'))
            
            if not is_video:
                # Images can be opened and passed
                uploaded_content = Image.open(file_path)
            else:
                # Video file must be uploaded once
                logger.info(f"[API Fallback] Đang upload video lên Google Cloud: {os.path.basename(file_path)}")
                uploaded_content = self.client.files.upload(path=file_path)
                
                # Wait for processing
                retry_count = 0
                while uploaded_content.state == 'PROCESSING' and retry_count < 30:
                    time.sleep(2)
                    uploaded_content = self.client.files.get(name=uploaded_content.name)
                    retry_count += 1
                
                if uploaded_content.state == 'FAILED':
                    raise Exception("Video processing thất bại trên máy chủ Google API")

            # Rotation loop
            for model_name in models:
                try:
                    logger.info(f"[Gemini] Multimodal using model: {model_name}")
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=[prompt, uploaded_content],
                        config=kwargs
                    )
                    
                    if response and response.text:
                        logger.info(f"🔥 [Gemini] Multimodal thành công {model_name} (%.1fs)", time.time() - t0)
                        return response.text
                    return None

                except genai_errors.ClientError as e:
                    if e.status_code == 429:
                        logger.warning(f"🔥 [Gemini Rotation] {model_name} quota exceeded (multimodal). Switching...")
                        _set_cooldown(model_name)
                        last_error = e
                        continue
                    elif e.status_code == 404:
                        logger.warning(f"⚠️ [Gemini] {model_name} not available (404, multimodal), skipping...")
                        last_error = e
                        continue
                    else:
                        logger.error(f"❌ [Gemini] {model_name} multimodal client error: {e}")
                        last_error = e
                        break
                except Exception as e:
                    logger.error(f"❌ [Gemini] {model_name} multimodal error: {e}")
                    last_error = e
                    break
            
            # Cleanup if video
            if is_video and uploaded_content:
                try:
                    self.client.files.delete(name=uploaded_content.name)
                except: pass

        except Exception as e:
            logger.error(f"🔥 [Gemini] Lỗi nghiêm trọng trong ask_with_file: {e}")
            last_error = e

        raise RuntimeError(f"Tất cả các model multimodal đều thất bại. Lỗi cuối cùng: {last_error}")
