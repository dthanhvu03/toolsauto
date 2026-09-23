"""Tiến độ xử lý: contextvar + tin Telegram (mốc + heartbeat)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.core.progress_report import progress_scope, report_stage
from app.features.telegram_bot.process_progress import (
    HEARTBEAT_SEC,
    TelegramProcessProgress,
    _fmt_elapsed,
)


def test_report_stage_noop_without_listener():
    report_stage("download")  # không ném


def test_report_stage_calls_listener():
    seen = []
    with progress_scope(seen.append):
        report_stage("download")
        report_stage("reup")
    assert seen == ["download", "reup"]


def test_fmt_elapsed():
    assert _fmt_elapsed(12) == "12 giây"
    assert _fmt_elapsed(65) == "1 phút 5 giây"
    assert _fmt_elapsed(120) == "2 phút"


def test_telegram_progress_edits_on_stage():
    client = MagicMock()
    client.send_message.return_value = {"message_id": 42}
    client.edit_message_text.return_value = {"message_id": 42}

    progress = TelegramProcessProgress(client, 1015)
    with progress.running():
        report_stage("download")
        report_stage("reup")
        progress.done()

    client.send_message.assert_called_once()
    assert "1015" in client.send_message.call_args.args[0]
    # start render + download + reup + done
    assert client.edit_message_text.call_count >= 3
    last_text = client.edit_message_text.call_args.args[1]
    assert "xong" in last_text
    assert progress.message_id == 42


def test_telegram_progress_fail():
    client = MagicMock()
    client.send_message.return_value = {"message_id": 7}
    progress = TelegramProcessProgress(client, 9)
    with progress.running():
        progress.fail("thiếu ffmpeg")
    text = client.edit_message_text.call_args.args[1]
    assert "lỗi" in text.lower() or "⚠️" in text
    assert "ffmpeg" in text


def test_heartbeat_constant_in_range():
    assert 45 <= HEARTBEAT_SEC <= 60
