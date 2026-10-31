"""Kiến trúc nền tảng cho hệ thống Quản trị (Admin) của Cashback Bot.

Cung cấp các hợp đồng cơ sở (Base Contracts):
- `AdminContext`: Chứa ngữ cảnh thực thi của phiên admin (user, thời gian, loại chat, message ID, hàm ghi log audit).
- `BaseAdminHandler`: Lớp trừu tượng cho mọi phân hệ nghiệp vụ admin (Shopee, Mô phỏng, Chính sách, Ví…).
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
    - Khai báo callback nó chịu trách nhiệm: tiền tố (`callback_prefixes`) và/hoặc chuỗi đúng (`callback_exact`).
    - Xử lý tương tác inline keyboard qua `route(...)`.
    - Xử lý văn bản người dùng nhập tự do qua `consume_text(...)` nếu đang ở trạng thái chờ.
    - Giữ trạng thái chờ khi `keeps_state(data)` đúng; ngược lại router gọi `clear_state(...)`.
    """

    name: str = "base"
    callback_prefixes: tuple[str, ...] = ()
    callback_exact: tuple[str, ...] = ()

    def can_handle(self, data: str) -> bool:
        """Kiểm tra callback_data có thuộc thẩm quyền xử lý của handler này không."""
        return data in self.callback_exact or any(data.startswith(prefix) for prefix in self.callback_prefixes)

    def keeps_state(self, data: str) -> bool:
        """Bấm nút `data` mà vẫn giữ trạng thái chờ nhập. Mặc định: mọi nút của handler này."""
        return self.can_handle(data)

    @abstractmethod
    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        """Điều hướng và trả về giao diện tương ứng với callback_data."""
        raise NotImplementedError

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        """Tiếp nhận văn bản admin gõ tự do (khi handler đang ở trạng thái chờ nhập liệu). None: không phải của handler này."""
        return None

    def clear_state(self, user_id: int) -> None:
        """Dọn dẹp các trạng thái chờ nhập của admin khi họ thoát hoặc đổi màn hình."""
        pass
