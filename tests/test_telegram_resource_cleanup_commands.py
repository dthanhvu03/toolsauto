"""
Tests for Telegram commands /tainguyen and /donrac.
Ensures remote monitoring and safe on-demand storage cleanup work without regressions.
"""
from __future__ import annotations

import time
import pytest
from app.features.telegram_bot.command_handler import TelegramCommandHandler
from app.features.telegram_bot.event_router import TelegramEventRouter


class StubClient:
    def __init__(self):
        self.msgs: list[str] = []
        self.markups: list[dict | None] = []
        self.callbacks: list[tuple[str, str]] = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)
        self.markups.append(reply_markup)

    def answer_callback_query(self, callback_id: str, text: str = "", **kw):
        self.callbacks.append((callback_id, text))

    @property
    def text(self) -> str:
        return " ".join(self.msgs)


def test_cmd_tainguyen_returns_clean_telemetry():
    client = StubClient()
    handler = TelegramCommandHandler(client)

    handler.handle_command("tainguyen")

    assert len(client.msgs) == 1
    msg = client.msgs[0]
    assert "BÁO CÁO TÀI NGUYÊN HỆ THỐNG" in msg
    assert "RAM:" in msg
    assert "CPU:" in msg
    assert "Ổ đĩa:" in msg
    assert "storage/" in msg
    assert "logs/" in msg
    assert "PM2" in msg


def test_cmd_donrac_audit_mode():
    client = StubClient()
    handler = TelegramCommandHandler(client)

    handler.handle_command("donrac")

    assert len(client.msgs) == 1
    msg = client.msgs[0]
    assert "KIỂM TRA RÁC Ổ ĐĨA" in msg
    assert "Có thể giải phóng:" in msg
    assert "Cam kết an toàn:" in msg
    assert "Cookies" in msg

    # Verify inline keyboard
    markup = client.markups[0]
    assert markup is not None
    assert "inline_keyboard" in markup
    buttons = markup["inline_keyboard"][0]
    assert any(b.get("callback_data") == "donrac:now" for b in buttons)


def test_cmd_donrac_execute_subcommand():
    client = StubClient()
    handler = TelegramCommandHandler(client)

    handler.handle_command("donrac", ["don"])

    # First message: in-flight notice
    assert len(client.msgs) >= 1
    assert "Đang tiến hành dọn rác" in client.msgs[0]

    # Wait briefly for daemon thread to complete
    timeout = 5.0
    start = time.time()
    while len(client.msgs) < 2 and (time.time() - start) < timeout:
        time.sleep(0.1)

    assert len(client.msgs) >= 2
    done_msg = client.msgs[1]
    assert "Dọn rác hoàn tất" in done_msg
    assert "Profile & Cookies: 100% nguyên vẹn an toàn" in done_msg


def test_callback_donrac_now():
    client = StubClient()
    handler = TelegramCommandHandler(client)
    router = TelegramEventRouter(client, handler)

    update = {
        "callback_query": {
            "id": "cb_999",
            "data": "donrac:now",
            "from": {"first_name": "Vu"},
            "message": {"message_id": 42},
        }
    }

    router.dispatch(update)

    assert any(cb[0] == "cb_999" for cb in client.callbacks)
    assert any("Đang tiến hành dọn rác" in m for m in client.msgs)

    # Wait for completion message
    timeout = 5.0
    start = time.time()
    while len(client.msgs) < 2 and (time.time() - start) < timeout:
        time.sleep(0.1)

    assert any("Dọn rác hoàn tất" in m for m in client.msgs)
