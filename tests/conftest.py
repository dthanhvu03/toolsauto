"""
Cấu hình chung cho toàn bộ test.

Hai bức tường, cùng một lý do: **test không được chạm vào thế giới thật của Owner.**

1. ``LOG_DIR`` ra thư mục tạm — 2026-09-11 sáng, lần log tìm lỗi quét TikTok thì gặp toàn dòng
   ``@a: ERROR: boom`` do test sinh ra.
2. Telegram bị cắt hẳn — 2026-09-11 chiều, Owner nhận liên tiếp "Video sẵn sàng đăng tay
   #1 · 1,234 lượt xem · 4 KB" kèm nút Đã đăng: test import ``app.main`` ⇒ đăng ký kênh
   Telegram THẬT từ ``.env`` ⇒ mọi ``notify_*`` sau đó bắn thẳng vào chat Owner, kể cả file
   giả 4096 byte. Chặn ở HAI tầng: token rỗng trước khi ``app.config`` đọc ``.env``, và autouse
   fixture xoá kênh + chặn ``httpx`` trong ``telegram_client`` — phòng test nào đó tự
   ``register`` hay DB test có token.
"""
import os
import tempfile

import pytest

os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="toolsauto-test-logs-"))
# `load_dotenv(override=False)` ⇒ đặt trước là .env không đè được.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""


@pytest.fixture(autouse=True)
def _khong_gui_telegram_that(monkeypatch):
    from app.core.notifier import telegram_client
    from app.core.notifier.service import NotifierService

    monkeypatch.setattr(NotifierService, "_channels", [])

    def _chan(*a, **k):
        raise AssertionError("Test đang cố gọi Telegram THẬT — mock NotifierService/TelegramClient lại.")

    monkeypatch.setattr(telegram_client.httpx, "post", _chan)
    monkeypatch.setattr(telegram_client.httpx, "get", _chan)
