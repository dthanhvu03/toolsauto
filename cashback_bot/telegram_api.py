"""Client Telegram tối thiểu cho bot cashback. Không dùng token bot đăng bài."""

from __future__ import annotations

import logging

import requests

from cashback_bot.messages import BOT_COMMANDS
from cashback_bot.redact import error_brief, redact

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
            params={"offset": offset, "timeout": 30, "allowed_updates": '["message","callback_query"]'},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise requests.RequestException("telegram getUpdates not ok")
        result = payload.get("result")
        return result if isinstance(result, list) else []

    def _post_ok(self, method: str, body: dict) -> bool:
        response = requests.post(f"{self._base}/{method}", json=body, timeout=self._timeout)
        if response.status_code >= 400:
            logger.error("[Cashback] %s http=%s", method, response.status_code)
            return False
        payload = response.json()
        return bool(payload.get("ok"))

    def set_my_commands(self, commands=BOT_COMMANDS, scope: dict | None = None) -> bool:
        body: dict = {
            "commands": [{"command": command, "description": description} for command, description in commands]
        }
        if scope:
            body["scope"] = scope
        return self._post_ok("setMyCommands", body)

    def set_my_description(self, description: str) -> bool:
        return self._post_ok("setMyDescription", {"description": description})

    def set_my_short_description(self, short_description: str) -> bool:
        return self._post_ok("setMyShortDescription", {"short_description": short_description})

    def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            requests.post(
                f"{self._base}/sendChatAction",
                json={"chat_id": chat_id, "action": action},
                timeout=self._timeout,
            )
        except requests.RequestException:
            logger.error("[Cashback] sendChatAction failed")

    def send_message(
        self,
        chat_id: int,
        html: str,
        reply_markup: dict | None = None,
        disable_notification: bool = False,
    ) -> None:
        body: dict = {
            "chat_id": chat_id,
            "text": html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            body["reply_markup"] = reply_markup
        if disable_notification:
            body["disable_notification"] = True
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

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        html: str,
        reply_markup: dict | None = None,
    ) -> bool:
        body: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            body["reply_markup"] = reply_markup
        try:
            response = requests.post(
                f"{self._base}/editMessageText",
                json=body,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            # Chuỗi lỗi của requests chứa URL /bot<TOKEN>/…: chỉ log bản đã che (P1-8).
            logger.error("[Cashback] editMessageText network error: %s", error_brief(exc))
            return False
        if response.status_code == 400:
            try:
                payload = response.json()
                desc = str(payload.get("description", ""))
                if "message is not modified" in desc.lower():
                    return True
            except Exception:
                pass
            logger.warning("[Cashback] editMessageText http=400: %s", redact(response.text)[:200])
            return False
        if response.status_code >= 400:
            logger.error("[Cashback] editMessageText http=%s: %s", response.status_code, redact(response.text)[:200])
            return False
        try:
            payload = response.json()
            return bool(payload.get("ok"))
        except ValueError:
            return False

    def answer_callback(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> None:
        body: dict = {"callback_query_id": callback_query_id}
        if text:
            body["text"] = text
            body["show_alert"] = show_alert
        try:
            requests.post(
                f"{self._base}/answerCallbackQuery",
                json=body,
                timeout=self._timeout,
            )
        except requests.RequestException:
            logger.error("[Cashback] answerCallback failed")

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        body: dict = {"chat_id": chat_id, "message_id": message_id}
        try:
            response = requests.post(
                f"{self._base}/deleteMessage",
                json=body,
                timeout=self._timeout,
            )
            if response.status_code >= 400:
                logger.warning("[Cashback] deleteMessage http=%s: %s", response.status_code, redact(response.text)[:200])
                return False
            payload = response.json()
            return bool(payload.get("ok"))
        except requests.RequestException as exc:
            logger.error("[Cashback] deleteMessage network error: %s", error_brief(exc))
            return False

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str | None = None) -> bool:
        body: dict = {"chat_id": chat_id}
        if caption:
            body["caption"] = caption
        try:
            response = requests.post(
                f"{self._base}/sendDocument",
                data=body,
                files={"document": (filename, data)},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("[Cashback] sendDocument network error: %s", type(exc).__name__)
            return False
        if response.status_code >= 400:
            logger.warning("[Cashback] sendDocument http=%s", response.status_code)
            return False
        return bool(response.json().get("ok"))

    def send_photo(self, chat_id: int, filename: str, data: bytes, caption: str | None = None) -> bool:
        body: dict = {"chat_id": chat_id}
        if caption:
            body["caption"] = caption
        try:
            response = requests.post(
                f"{self._base}/sendPhoto",
                data=body,
                files={"photo": (filename, data, "image/png")},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("[Cashback] sendPhoto network error: %s", type(exc).__name__)
            return False
        if response.status_code >= 400:
            logger.warning("[Cashback] sendPhoto http=%s", response.status_code)
            return False
        return bool(response.json().get("ok"))
