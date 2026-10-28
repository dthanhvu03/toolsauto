"""Client Telegram tối thiểu cho bot bán hàng. Lỗi chỉ log tên loại lỗi: URL của requests chứa token."""

from __future__ import annotations

import json as jsonlib
import logging

import requests

logger = logging.getLogger("store_bot")


class TelegramApi:
    def __init__(self, token: str, timeout: float = 35):
        self._base = f"https://api.telegram.org/bot{token}"
        self._file_base = f"https://api.telegram.org/file/bot{token}"
        self._timeout = timeout

    def _call(self, method: str, *, json: dict | None = None, data: dict | None = None,
              files: dict | None = None) -> dict | list | bool | None:
        try:
            response = requests.post(f"{self._base}/{method}", json=json, data=data, files=files,
                                     timeout=self._timeout)
        except requests.RequestException as exc:
            logger.error("[Store] %s network error: %s", method, type(exc).__name__)
            return None
        try:
            payload = response.json()
        except ValueError:
            logger.error("[Store] %s http=%s (không phải JSON)", method, response.status_code)
            return None
        if not payload.get("ok"):
            description = str(payload.get("description", ""))
            if "message is not modified" not in description.lower():
                logger.warning("[Store] %s http=%s: %s", method, response.status_code, description[:200])
            return None
        return payload.get("result")

    def get_updates(self, offset: int) -> list[dict]:
        """Lỗi mạng ném lên để vòng lặp nghỉ rồi thử lại."""
        response = requests.get(
            f"{self._base}/getUpdates",
            params={"offset": offset, "timeout": 30, "allowed_updates": '["message","callback_query"]'},
            timeout=self._timeout,
        )
        response.raise_for_status()
        result = response.json().get("result")
        return result if isinstance(result, list) else []

    def get_me(self) -> dict | None:
        result = self._call("getMe", json={})
        return result if isinstance(result, dict) else None

    def set_my_commands(self, commands: list[tuple[str, str]], scope: dict | None = None) -> bool:
        body: dict = {"commands": [{"command": c, "description": d} for c, d in commands]}
        if scope:
            body["scope"] = scope
        return self._call("setMyCommands", json=body) is True

    def send_message(self, chat_id: int | str, html: str, reply_markup: dict | None = None,
                     disable_notification: bool = False) -> int | None:
        body: dict = {"chat_id": chat_id, "text": html, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup:
            body["reply_markup"] = reply_markup
        if disable_notification:
            body["disable_notification"] = True
        result = self._call("sendMessage", json=body)
        return result.get("message_id") if isinstance(result, dict) else None

    def send_broadcast(self, chat_id: int, html: str, reply_markup: dict | None = None) -> tuple[str, int]:
        """Gửi tin hàng loạt. Trả ("ok" | "blocked" | "retry" | "error", số giây chờ khi bị giới hạn)."""
        body: dict = {"chat_id": chat_id, "text": html, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup:
            body["reply_markup"] = reply_markup
        try:
            response = requests.post(f"{self._base}/sendMessage", json=body, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("[Store] broadcast network error: %s", type(exc).__name__)
            return "error", 0
        if response.status_code == 200:
            return "ok", 0
        if response.status_code == 429:
            try:
                wait = int((response.json().get("parameters") or {}).get("retry_after") or 5)
            except ValueError:
                wait = 5
            return "retry", wait
        if response.status_code in (400, 403):
            # 403: khách chặn bot / xoá tài khoản; 400 chat not found: khách chưa từng mở được chat.
            return "blocked", 0
        return "error", 0

    def edit_message_text(self, chat_id: int, message_id: int, html: str, reply_markup: dict | None = None) -> bool:
        body: dict = {"chat_id": chat_id, "message_id": message_id, "text": html, "parse_mode": "HTML",
                      "disable_web_page_preview": True}
        if reply_markup:
            body["reply_markup"] = reply_markup
        return self._call("editMessageText", json=body) is not None

    def answer_callback(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> None:
        body: dict = {"callback_query_id": callback_query_id}
        if text:
            body.update(text=text, show_alert=show_alert)
        self._call("answerCallbackQuery", json=body)

    def send_photo(self, chat_id: int, data: bytes, caption: str, reply_markup: dict | None = None) -> bool:
        body: dict = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        if reply_markup:
            body["reply_markup"] = jsonlib.dumps(reply_markup, ensure_ascii=False)
        return self._call("sendPhoto", data=body, files={"photo": ("qr.png", data, "image/png")}) is not None

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str | None = None) -> bool:
        body: dict = {"chat_id": chat_id}
        if caption:
            body.update(caption=caption, parse_mode="HTML")
        return self._call("sendDocument", data=body, files={"document": (filename, data)}) is not None

    def download_file(self, file_id: str, max_bytes: int = 2_000_000) -> bytes | None:
        info = self._call("getFile", json={"file_id": file_id})
        if not isinstance(info, dict) or not info.get("file_path"):
            return None
        if int(info.get("file_size") or 0) > max_bytes:
            return None
        try:
            response = requests.get(f"{self._file_base}/{info['file_path']}", timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[Store] download file error: %s", type(exc).__name__)
            return None
        return response.content[:max_bytes]
