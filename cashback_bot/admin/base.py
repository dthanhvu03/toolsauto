"""Kiến trúc nền tảng cho hệ thống Quản trị (Admin) của Cashback Bot.

Cung cấp các hợp đồng cơ sở (Base Contracts):
- `AdminContext`: Chứa ngữ cảnh thực thi của phiên admin (user, thời gian, loại chat, message ID, hàm ghi log audit).
- `BaseAdminHandler`: Lớp trừu tượng cho mọi phân hệ nghiệp vụ admin (Wallet, Support, Policy, TikTok...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from cashback_bot.messages import BotReply


@dataclass(frozen=True)
class AdminContext:
    """Ngữ cảnh của một thao tác từ người quản trị."""
    user_id: int
    now: datetime
    chat_type: str = "private"
    message_id: int | None = None
    audit: Callable[[str, dict[str, Any], int], None] | None = None

    def log_audit(self, action: str, details: dict[str, Any]) -> None:
        if self.audit is not None:
            self.audit(action, details, self.user_id)


class BaseAdminHandler(ABC):
    """Lớp cơ sở cho các phân hệ tính năng của Admin Bot.
    
    Mỗi handler đại diện cho một domain nghiệp vụ độc lập:
    - Khai báo các tiền tố callback (`callback_prefixes`) nó chịu trách nhiệm.
    - Xử lý tương tác inline keyboard qua `route(...)`.
    - Xử lý văn bản người dùng nhập tự do qua `consume_text(...)` nếu đang ở trạng thái chờ.
    - Dọn dẹp trạng thái chờ nhập khi chuyển màn qua `clear_state(...)`.
    """

    name: str = "base"
    callback_prefixes: tuple[str, ...] = ()

    def can_handle(self, data: str) -> bool:
        """Kiểm tra callback_data có thuộc thẩm quyền xử lý của handler này không."""
        return any(data.startswith(prefix) for prefix in self.callback_prefixes)

    @abstractmethod
    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        """Điều hướng và trả về giao diện tương ứng với callback_data."""
        raise NotImplementedError

    def consume_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        """Tiếp nhận văn bản admin gõ tự do (khi handler đang ở trạng thái chờ nhập liệu)."""
        return None

    def clear_state(self, user_id: int) -> None:
        """Dọn dẹp các trạng thái chờ nhập của admin khi họ thoát hoặc đổi màn hình."""
        pass
