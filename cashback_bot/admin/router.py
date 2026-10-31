"""Bộ điều phối trung tâm (Central Router / Dispatcher) cho Admin Bot.

Quản lý việc định tuyến các lệnh Callback Query và Tin nhắn văn bản (Text Input)
tới các handler nghiệp vụ tương ứng một cách tự động và nhất quán.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from cashback_bot.admin.base import BaseAdminHandler
    from cashback_bot.messages import BotReply


class AdminRouter:
    """Điều phối và phân phối các sự kiện tương tác của Admin Bot."""

    def __init__(self) -> None:
        self._handlers: list[BaseAdminHandler] = []

    def register(self, handler: BaseAdminHandler) -> None:
        """Đăng ký một phân hệ nghiệp vụ vào hệ thống điều phối."""
        self._handlers.append(handler)

    def dispatch_callback(self, user_id: int, data: str, now: datetime) -> BotReply | None:
        """Tìm handler phù hợp nhất dựa trên `callback_prefixes` và điều hướng."""
        for handler in self._handlers:
            if handler.can_handle(data):
                return handler.route(user_id, data, now)
        return None

    def dispatch_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        """Hỏi tuần tự các handler xem có handler nào đang chờ text từ admin không."""
        for handler in self._handlers:
            reply = handler.consume_text(user_id, text, now)
            if reply is not None:
                return reply
        return None

    def clear_states(self, user_id: int, current_data: str) -> None:
        """Dọn dẹp trạng thái chờ nhập của các handler khi người dùng bấm chuyển màn hình."""
        for handler in self._handlers:
            if not handler.can_handle(current_data):
                handler.clear_state(user_id)
