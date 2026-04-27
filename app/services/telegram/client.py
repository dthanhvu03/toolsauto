"""
TelegramClient — Low-level Telegram Bot API wrapper.

Tách riêng API call khỏi business logic (NotifierService).
Chỉ chịu trách nhiệm: gọi HTTP → Telegram server → trả kết quả.

Dùng:
    from app.services.telegram_client import TelegramClient
    client = TelegramClient(bot_token, chat_id)
    client.send_message("Hello!")
    client.send_photo("/path/to/img.jpg", "Caption here")
"""
import httpx
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds
REQUEST_TIMEOUT = 30  # seconds


class TelegramClient:
    """Low-level Telegram Bot API wrapper with retry logic."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    # ─── Public API ───────────────────────────────

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
        reply_markup: Optional[dict] = None,
    ) -> Optional[dict]:
        """Gửi text message. Trả response dict hoặc None nếu thất bại."""
        import json as json_mod
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup:
            data["reply_markup"] = json_mod.dumps(reply_markup)
        return self._request("sendMessage", data=data)

    def send_photo(
        self,
        photo_path: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> Optional[dict]:
        """Gửi ảnh + caption. Trả response dict hoặc None nếu thất bại."""
        import json as json_mod
        data = {
            "chat_id": self.chat_id,
            "caption": caption[:1024],  # Telegram caption limit
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = json_mod.dumps(reply_markup)

        try:
            with open(photo_path, "rb") as f:
                files = {"photo": (photo_path.split("/")[-1], f, "image/jpeg")}
                return self._request("sendPhoto", data=data, files=files)
        except FileNotFoundError:
            logger.warning("Photo not found: %s — fallback to text", photo_path)
            return self.send_message(caption, parse_mode=parse_mode)

    def send_video(
        self,
        video_path: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> Optional[dict]:
        """Gửi video + caption. Trả response dict hoặc None nếu thất bại."""
        import json as json_mod
        data = {
            "chat_id": self.chat_id,
            "caption": caption[:1024],  # Telegram caption limit
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = json_mod.dumps(reply_markup)

        try:
            with open(video_path, "rb") as f:
                # Telegram supports mp4 and some other formats, mp4 is safest
                files = {"video": (video_path.split("/")[-1], f, "video/mp4")}
                # For video, increase timeout to 120s due to upload times
                return self._request("sendVideo", data=data, files=files, custom_timeout=120)
        except FileNotFoundError:
            logger.warning("Video not found: %s — fallback to text", video_path)
            return self.send_message(caption, parse_mode=parse_mode, reply_markup=reply_markup)

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False,
    ) -> Optional[dict]:
        """Trả lời callback query (khi user click inline button)."""
        data = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        return self._request("answerCallbackQuery", data=data)

    def edit_message_reply_markup(
        self,
        message_id: int,
        reply_markup: Optional[dict] = None,
    ) -> Optional[dict]:
        """Xóa hoặc thay inline keyboard sau khi user đã click."""
        import json as json_mod
        data = {
            "chat_id": self.chat_id,
            "message_id": message_id,
        }
        if reply_markup:
            data["reply_markup"] = json_mod.dumps(reply_markup)
        else:
            data["reply_markup"] = json_mod.dumps({"inline_keyboard": []})
        return self._request("editMessageReplyMarkup", data=data)

    def get_updates(self, offset: int = 0, timeout: int = 30) -> list:
        """
        Long-poll Telegram for new updates.
        Blocks up to `timeout` seconds waiting for new messages/callbacks.
        Returns list of update dicts. Empty list on error/timeout.
        """
        url = f"{self.base_url}/getUpdates"
        try:
            resp = httpx.get(url, params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["callback_query","message"]',
            }, timeout=timeout + 10)  # HTTP timeout > long-poll timeout
            if resp.status_code == 200:
                result = resp.json()
                if result.get("ok"):
                    return result.get("result", [])
            return []
        except Exception as e:
            logger.warning("getUpdates failed: %s", e)
            return []

    def delete_webhook(self) -> bool:
        """Xóa webhook để chuyển sang polling mode. Gọi 1 lần khi khởi động."""
        result = self._request("deleteWebhook", data={"drop_pending_updates": False})
        if result is not None:
            logger.info("Telegram webhook deleted — polling mode active")
            return True
        return False

    # ─── Internal ─────────────────────────────────

    def _request(
        self,
        method: str,
        data: dict,
        files: Optional[dict] = None,
        custom_timeout: Optional[int] = None,
    ) -> Optional[dict]:
        """HTTP POST to Telegram Bot API with retry logic."""
        url = f"{self.base_url}/{method}"
        actual_timeout = custom_timeout or REQUEST_TIMEOUT

        for attempt in range(MAX_RETRIES):
            try:
                if files:
                    resp = httpx.post(url, data=data, files=files, timeout=actual_timeout)
                else:
                    resp = httpx.post(url, json=data, timeout=actual_timeout)

                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("ok"):
                        return result.get("result")
                    logger.warning("Telegram API not ok: %s", result.get("description", ""))
                    return None

                # Rate limit → wait and retry
                if resp.status_code == 429:
                    retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                    logger.warning("Telegram rate limited. Retry after %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                logger.warning("Telegram %s error %s: %s", method, resp.status_code, resp.text[:200])
                return None

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Telegram %s attempt %d failed: %s — retry in %ds",
                                   method, attempt + 1, e, RETRY_DELAY)
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error("Telegram %s failed after %d attempts: %s",
                                 method, MAX_RETRIES, e)
                    return None

        return None
