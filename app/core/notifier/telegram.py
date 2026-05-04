"""Telegram channel adapter (Telegram Bot API via TelegramClient)."""
from typing import Optional

from .base import BaseNotifier


class TelegramNotifier(BaseNotifier):
    """Gửi tin nhắn qua Telegram Bot API dùng TelegramClient."""

    def __init__(self, bot_token: str, chat_id: str):
        from app.services.telegram_client import TelegramClient
        self.client = TelegramClient(bot_token, chat_id)
        self._chat_id = str(chat_id).strip()

    def channel_key(self) -> str:
        """Key để tránh đăng ký trùng (cùng 1 chat nhận 2 lần)."""
        return f"telegram:{self._chat_id}"

    def send(self, message: str) -> bool:
        result = self.client.send_message(message)
        return result is not None

    def send_photo(self, photo_path: str, caption: str) -> bool:
        result = self.client.send_photo(photo_path, caption)
        return result is not None

    def send_with_buttons(self, message: str, buttons: list) -> bool:
        """buttons = [[{"text": "Label", "callback_data": "action:id"}, ...]]"""
        reply_markup = {"inline_keyboard": buttons}
        result = self.client.send_message(message, reply_markup=reply_markup)
        return result is not None

    def send_video(self, video_path: str, caption: str = "", buttons: Optional[list] = None) -> bool:
        reply_markup = {"inline_keyboard": buttons} if buttons else None
        result = self.client.send_video(video_path, caption, reply_markup=reply_markup)
        return result is not None
