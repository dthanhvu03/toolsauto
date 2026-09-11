"""
Menu "/" trong Telegram phải là chính bảng lệnh trong code — hai chiều.

2026-09-11: menu BotFather cài tay quảng cáo /done, /failed (không tồn tại → "Lệnh không hỗ
trợ"), thiếu /sansang /moi /nguon /dadang /tai /caidat — những lệnh dùng hằng ngày.
"""
from __future__ import annotations

import re

from app.features.telegram_bot.command_handler import TelegramCommandHandler


class _Client:
    def __init__(self):
        self.msgs, self.commands = [], None

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)

    def set_my_commands(self, commands):
        self.commands = commands
        return True


def test_moi_lenh_trong_menu_deu_ton_tai():
    handler = TelegramCommandHandler(_Client())
    real = set(handler.handler_map())

    for item in handler.menu():
        assert item["command"] in real, f"menu quảng cáo /{item['command']} mà bot không có"


def test_moi_lenh_that_deu_co_trong_menu():
    handler = TelegramCommandHandler(_Client())
    in_menu = {c for c, _ in handler.MENU}

    thieu = set(handler.handler_map()) - in_menu - {"start"}  # /start là bí danh của /help
    assert not thieu, f"lệnh có mà menu không kể: {thieu}"


def test_dinh_dang_theo_gioi_han_telegram():
    for item in TelegramCommandHandler.menu():
        assert re.fullmatch(r"[a-z0-9_]{1,32}", item["command"]), item
        assert 3 <= len(item["description"]) <= 256, item


def test_lenh_hang_ngay_dung_dau():
    dau = [c for c, _ in TelegramCommandHandler.MENU[:4]]

    assert dau == ["sansang", "moi", "nguon", "dadang"], "thứ Owner dùng mỗi ngày phải lên đầu"


def test_poller_dang_ky_menu_luc_khoi_dong(monkeypatch):
    from app.features.telegram_bot import poller as pm

    client = _Client()
    monkeypatch.setattr(pm, "TelegramClient", lambda token, chat: client, raising=False)
    p = pm.TelegramPoller.__new__(pm.TelegramPoller)
    p.client = client
    p.command_handler = TelegramCommandHandler(client)

    p._register_menu()

    assert client.commands == TelegramCommandHandler.menu()


def test_dang_ky_menu_hong_khong_lam_chet_poller():
    from app.features.telegram_bot import poller as pm

    class _Broken(_Client):
        def set_my_commands(self, commands):
            raise RuntimeError("mạng hỏng")

    p = pm.TelegramPoller.__new__(pm.TelegramPoller)
    p.client = _Broken()
    p.command_handler = TelegramCommandHandler(p.client)

    p._register_menu()  # không ném


def test_help_sinh_tu_MENU_khong_bo_sot_lenh_nao():
    """/help và menu '/' từng là hai bản chép tay lệch nhau — nay cùng một nguồn."""
    c = _Client()
    TelegramCommandHandler(c).handle_command("help")
    text = c.msgs[0]

    for cmd, _ in TelegramCommandHandler.MENU:
        assert f"/{cmd}" in text, f"/help thiếu /{cmd}"
    assert text.index("/sansang") < text.index("/status") < text.index("/jobs"), "luồng video trước, Job sau"
    assert "Luồng video" in text and "cần tài khoản Facebook" in text
