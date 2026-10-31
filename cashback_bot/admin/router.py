"""Bộ điều phối trung tâm (Central Router / Dispatcher) cho Admin Bot.

Quản lý việc định tuyến các lệnh Callback Query và Tin nhắn văn bản (Text Input)
tới các handler nghiệp vụ tương ứng một cách tự động và nhất quán.

Thứ tự đăng ký là thứ tự ưu tiên khi admin gõ chữ: handler đăng ký trước được hỏi trước.
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

    @property
    def handlers(self) -> tuple[BaseAdminHandler, ...]:
        return tuple(self._handlers)

    def register(self, handler: BaseAdminHandler) -> None:
        """Đăng ký một phân hệ nghiệp vụ. Hai handler không được nhận chung một callback."""
        for other in self._handlers:
            shared = [p for p in handler.callback_prefixes + handler.callback_exact if other.can_handle(p)]
            shared += [p for p in other.callback_prefixes + other.callback_exact if handler.can_handle(p)]
            if shared:
                raise ValueError(f"{handler.name} và {other.name} trùng callback: {sorted(set(shared))}")
        self._handlers.append(handler)

    def dispatch_callback(self, user_id: int, data: str, now: datetime) -> BotReply | None:
        """Gửi callback tới handler nhận `data`. None: không handler nào nhận."""
        for handler in self._handlers:
            if handler.can_handle(data):
                return handler.route(user_id, data, now)
        return None

    def dispatch_text(
        self, user_id: int, text: str, now: datetime, message_id: int | None = None
    ) -> BotReply | None:
        """Hỏi tuần tự các handler (theo thứ tự đăng ký) xem có handler nào đang chờ text từ admin không."""
        for handler in self._handlers:
            reply = handler.consume_text(user_id, text, now, message_id)
            if reply is not None:
                return reply
        return None

    def clear_states(self, user_id: int, current_data: str) -> None:
        """Bấm nút `current_data`: handler nào không giữ trạng thái với nút này thì dọn trạng thái chờ."""
        for handler in self._handlers:
            if not handler.keeps_state(current_data):
                handler.clear_state(user_id)
