"""Client Telegram tối thiểu cho bot cashback. Không dùng token bot đăng bài."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger("cashback_bot")


class TelegramDeliveryError(Exception):
    """Lỗi gửi tin. kind không chứa nội dung tin hay token."""

    def __init__(self, kind: str, retry_after: int | None = None, status_code: int | None = None):
        self.kind = kind
        self.retry_after = retry_after
        self.status_code = status_code
        super().__init__(kind)


def _retry_after_seconds(response: requests.Response) -> int | None:
    raw = (response.headers.get("Retry-After") or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def classify_delivery_error(exc: BaseException) -> tuple[str, int | None]:
    if isinstance(exc, TelegramDeliveryError):
        return exc.kind, exc.retry_after
    if isinstance(exc, requests.Timeout):
        return "ambiguous", None
    if isinstance(exc, requests.ConnectionError):
        return "ambiguous", None
    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None:
        code = response.status_code
        if code == 429:
            return "rate_limited", _retry_after_seconds(response)
        if 400 <= code < 500:
            return "permanent", None
        return "transient", None
    return "transient", None


class TelegramApi:
    def __init__(self, token: str, timeout: float = 35):
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout

    def get_updates(self, offset: int) -> list[dict]:
        response = requests.get(
            f"{self._base}/getUpdates",
            params={"offset": offset, "timeout": 30, "allowed_updates": '["message"]'},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise requests.RequestException("telegram getUpdates not ok")
        result = payload.get("result")
        return result if isinstance(result, list) else []

    def set_my_commands(self) -> bool:
        response = requests.post(
            f"{self._base}/setMyCommands",
            json={
                "commands": [
                    {"command": "start", "description": "Bắt đầu"},
                    {"command": "huongdan", "description": "Cách nhận hoàn tiền"},
                ]
            },
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            logger.error("[Cashback] setMyCommands http=%s", response.status_code)
            return False
        payload = response.json()
        return bool(payload.get("ok"))

    def send_message(self, chat_id: int, html: str, reply_markup: dict | None = None) -> None:
        body: dict = {
            "chat_id": chat_id,
            "text": html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            body["reply_markup"] = reply_markup
        try:
            response = requests.post(
                f"{self._base}/sendMessage",
                json=body,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise TelegramDeliveryError("ambiguous") from exc
        except requests.RequestException as exc:
            raise TelegramDeliveryError("ambiguous") from exc
        if response.status_code == 429:
            logger.error("[Cashback] sendMessage http=429")
            raise TelegramDeliveryError("rate_limited", retry_after=_retry_after_seconds(response), status_code=429)
        if response.status_code >= 500:
            logger.error("[Cashback] sendMessage http=%s", response.status_code)
            raise TelegramDeliveryError("transient", status_code=response.status_code)
        if response.status_code >= 400:
            logger.error("[Cashback] sendMessage http=%s", response.status_code)
            raise TelegramDeliveryError("permanent", status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramDeliveryError("transient") from exc
        if not payload.get("ok"):
            raise TelegramDeliveryError("permanent", status_code=response.status_code)
