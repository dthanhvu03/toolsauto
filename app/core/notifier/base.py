"""Abstract base for notification channels."""
from abc import ABC, abstractmethod
from typing import Optional


class BaseNotifier(ABC):
    """Interface cho mọi notification channel."""

    def channel_key(self) -> Optional[str]:
        """Optional: trả key để tránh đăng ký trùng (None = không dedup)."""
        return None

    @abstractmethod
    def send(self, message: str) -> bool:
        """Gửi tin nhắn text. Trả True nếu thành công."""
        ...

    def send_photo(self, photo_path: str, caption: str) -> bool:
        """Gửi ảnh + caption. Default: fallback to text."""
        return self.send(caption)

    def send_with_buttons(self, message: str, buttons: list) -> bool:
        """Gửi text + inline buttons. Default: fallback to text."""
        return self.send(message)

    def send_video(self, video_path: str, caption: str = "", buttons: Optional[list] = None) -> bool:
        """Gửi video + caption. Default: fallback to text+buttons."""
        if buttons:
            return self.send_with_buttons(caption, buttons)
        return self.send(caption)
