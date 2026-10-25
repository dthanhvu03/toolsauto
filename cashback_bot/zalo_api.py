"""Client Zalo Bot Platform tối thiểu (PLAN-082). Token nằm trong URL: log chỉ ghi mã lỗi, không ghi URL.

API giống Telegram: https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>, trả {"ok", "result", "error_code"}.
- getUpdates trả một update mỗi lần (đã thử thật 2026-10-24); hết giờ chờ là error_code 408. Zalo không giữ tin
  gửi lúc không có ai nhận, nên tiến trình phải chạy liên tục.
- Lỗi gửi dùng lại TelegramDeliveryError để Dispatcher (PLAN-079) phân loại như kênh Telegram.
"""

from __future__ import annotations

import logging

import requests

from cashback_bot.telegram_api import TelegramDeliveryError, never_sent

logger = logging.getLogger("cashback_bot")

API_BASE = "https://bot-api.zaloplatforms.com"
POLL_TIMEOUT_SEC = 30
TIMEOUT_CODE = 408


class ZaloApi:
    def __init__(self, token: str, timeout: float = 45):
        self._base = f"{API_BASE}/bot{token}"
        self._timeout = timeout

    def get_updates(self, timeout_sec: int = POLL_TIMEOUT_SEC) -> list[dict]:
        """Chờ tin mới tối đa timeout_sec. Không có tin: []. Lỗi mạng ném requests.RequestException."""
        response = requests.post(f"{self._base}/getUpdates", json={"timeout": str(timeout_sec)}, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            if payload.get("error_code") == TIMEOUT_CODE:
                return []
            raise requests.RequestException(f"zalo getUpdates error_code={payload.get('error_code')}")
        result = payload.get("result")
        if isinstance(result, dict):
            return [result]
        return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    def get_me(self) -> dict:
        response = requests.post(f"{self._base}/getMe", json={}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise requests.RequestException(f"zalo getMe error_code={payload.get('error_code')}")
        return payload.get("result") or {}

    def send_message(self, chat_id: str, text: str, styles: list[dict] | None = None) -> str | None:
        """Gửi một tin chữ thuần, định dạng bằng text_styles (zalo_render). Trả message_id Zalo."""
        body: dict = {"chat_id": chat_id, "text": text}
        if styles:
            body["text_styles"] = styles
        try:
            response = requests.post(f"{self._base}/sendMessage", json=body, timeout=self._timeout)
        except requests.RequestException as exc:
            raise TelegramDeliveryError("offline" if never_sent(exc) else "ambiguous") from exc
        code = response.status_code
        try:
            payload = response.json()
        except ValueError as exc:
            if code == 429:
                raise TelegramDeliveryError("rate_limited", status_code=429) from exc
            raise TelegramDeliveryError("transient" if code >= 500 or code < 400 else "permanent", status_code=code) from exc
        if code < 400 and payload.get("ok"):
            result = payload.get("result")
            message_id = result.get("message_id") if isinstance(result, dict) else None
            return message_id if isinstance(message_id, str) else None
        error_code = payload.get("error_code") if isinstance(payload.get("error_code"), int) else code
        logger.error("[Cashback] zalo sendMessage http=%s error_code=%s", code, error_code)
        if code == 429 or error_code == 429:
            raise TelegramDeliveryError("rate_limited", status_code=429)
        if code >= 500 or error_code >= 500:
            raise TelegramDeliveryError("transient", status_code=error_code)
        if styles:
            # Zalo từ chối định dạng thì gửi lại một lần chữ thuần: khách vẫn nhận được nội dung.
            logger.warning("[Cashback] zalo sendMessage bỏ text_styles, gửi lại chữ thuần")
            return self.send_message(chat_id, text)
        # 4xx (khách chặn bot, chat không tồn tại…): Dispatcher chỉ đánh dấu khách đã chặn khi 403.
        raise TelegramDeliveryError("permanent", status_code=error_code if 400 <= error_code < 500 else None)

    def send_chat_action(self, chat_id: str, action: str = "typing") -> None:
        requests.post(f"{self._base}/sendChatAction", json={"chat_id": chat_id, "action": action}, timeout=10)
