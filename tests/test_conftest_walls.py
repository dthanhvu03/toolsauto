"""Hai bức tường trong conftest phải đứng — test không được chạm thế giới thật của Owner."""
from __future__ import annotations

import os


def test_telegram_khong_co_kenh_that_trong_test():
    import app.config as config
    from app.core.notifier.service import NotifierService

    assert config.TELEGRAM_BOT_TOKEN == "" and config.TELEGRAM_CHAT_ID == "", ".env không được lọt vào test"
    assert NotifierService._channels == [], "kênh Telegram thật đã bị đăng ký — tin giả sẽ bay vào chat Owner"


def test_httpx_cua_telegram_client_bi_chan():
    from app.core.notifier import telegram_client

    try:
        telegram_client.httpx.post("https://api.telegram.org/botX/sendMessage", json={})
    except AssertionError as exc:
        assert "Telegram THẬT" in str(exc)
    else:
        raise AssertionError("httpx.post trong telegram_client phải bị chặn")


def test_log_dir_la_thu_muc_tam():
    import app.config as config

    assert os.path.abspath(os.environ["LOG_DIR"]) != os.path.abspath(str(config.LOGS_DIR))
