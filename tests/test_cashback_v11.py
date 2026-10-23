"""V1.1: hàng đợi, rate limit, backup. Không đụng DB production và không gửi Telegram thật."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from cashback_bot.backup import backup_database, integrity_ok, restore_database
from cashback_bot.db import TrackingRepository
from cashback_bot.poller import flush_outbound, process_updates
from cashback_bot.telegram_api import TelegramDeliveryError
from tests.test_cashback_bot import FakeClient, payload, repo, service

NOW = datetime(2026, 10, 22, 4, 0, tzinfo=timezone.utc)
LIVE_DB = Path("/home/vu/toolsauto/data/cashback.sqlite")


def _update(update_id: int, user_id: int, text: str = "https://shopee.vn/product/9/8") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "chat": {"type": "private", "id": user_id},
            "from": {"id": user_id, "username": "buyer"},
            "text": text,
        },
    }


def _fresh(last_update: str | None = None):
    stamp = last_update or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return payload(last_update=stamp)


class _Admin:
    def __init__(self):
        self.failed = []
        self.link_sent = []

    def notify_request_failed(self, **kwargs):
        self.failed.append(kwargs)

    def notify_link_sent(self, update_id):
        self.link_sent.append(update_id)

    def flush_pending(self, limit=10):
        return None


class _FailUser:
    def __init__(self, blocked_id: int):
        self.blocked_id = blocked_id
        self.sent = []

    def send_message(self, chat_id, html, reply_markup=None):
        if chat_id == self.blocked_id:
            raise requests.ConnectionError("blocked")
        self.sent.append(chat_id)


def test_tin_dau_loi_khong_chan_nguoi_sau(tmp_path):
    store = repo(tmp_path)
    client = FakeClient(_fresh())
    bot = service(
        tmp_path,
        client,
        customer_access_enabled=True,
        allowed_telegram_ids=frozenset(),
        delivery_backoff_sec=30,
    )
    bot.repo = store
    telegram = _FailUser(111)
    process_updates(
        bot,
        telegram,
        store,
        [_update(1, 111), _update(2, 222), _update(3, 333)],
        _Admin(),
        now=NOW,
    )
    assert telegram.sent == [222, 333]
    assert store.get_offset() == 4
    rows = sqlite3.connect(store.path).execute(
        "SELECT telegram_user_id, sub_id, delivery_status FROM link_requests ORDER BY telegram_update_id"
    ).fetchall()
    assert [row[0] for row in rows] == [111, 222, 333]
    assert rows[0][2] != "sent"
    assert rows[1][2] == "sent"
    assert len({row[1] for row in rows}) == 3


def test_retry_khong_tao_sub_id_moi(tmp_path):
    store = repo(tmp_path)
    client = FakeClient(_fresh())
    bot = service(tmp_path, client, delivery_backoff_sec=0, delivery_max_attempts=4)
    bot.repo = store

    class Flaky:
        def __init__(self):
            self.calls = 0

        def send_message(self, chat_id, html, reply_markup=None):
            self.calls += 1
            if self.calls == 1:
                raise requests.Timeout("slow")

    telegram = Flaky()
    process_updates(bot, telegram, store, [_update(7, 111)], _Admin(), now=NOW)
    first = sqlite3.connect(store.path).execute("SELECT sub_id, delivery_status FROM link_requests").fetchone()
    assert first[1] == "ambiguous"
    flush_outbound(bot, telegram, store, _Admin(), now=NOW + timedelta(seconds=5))
    again = sqlite3.connect(store.path).execute("SELECT sub_id, delivery_status FROM link_requests").fetchall()
    assert again == [(first[0], "sent")]
    assert client.calls == 1


def test_telegram_429_khong_chan_user_sau(tmp_path):
    store = repo(tmp_path)
    client = FakeClient(_fresh())
    bot = service(tmp_path, client, customer_access_enabled=True, allowed_telegram_ids=frozenset(), delivery_backoff_sec=30)
    bot.repo = store

    class Limited:
        def __init__(self):
            self.sent = []

        def send_message(self, chat_id, html, reply_markup=None):
            if chat_id == 111:
                raise TelegramDeliveryError("rate_limited", retry_after=90, status_code=429)
            self.sent.append(chat_id)

    process_updates(bot, Limited(), store, [_update(1, 111), _update(2, 222)], _Admin(), now=NOW)
    row = sqlite3.connect(store.path).execute(
        "SELECT status, next_retry_at, last_error FROM outbound_messages WHERE telegram_update_id=1"
    ).fetchone()
    assert row[0] == "retry"
    assert row[2] == "rate_limited"
    due = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert due - NOW >= timedelta(seconds=90)
    assert store.get_offset() == 3


def test_qua_so_lan_thi_needs_review(tmp_path):
    store = repo(tmp_path)
    client = FakeClient(_fresh())
    bot = service(tmp_path, client, delivery_backoff_sec=0, delivery_max_attempts=2)
    bot.repo = store

    class AlwaysFail:
        def __init__(self):
            self.calls = 0

        def send_message(self, chat_id, html, reply_markup=None):
            self.calls += 1
            raise requests.ConnectionError("nope")

    telegram = AlwaysFail()
    admin = _Admin()
    process_updates(bot, telegram, store, [_update(9, 111)], admin, now=NOW)
    flush_outbound(bot, telegram, store, admin, now=NOW + timedelta(seconds=1))
    status = sqlite3.connect(store.path).execute(
        "SELECT delivery_status FROM link_requests"
    ).fetchone()[0]
    assert status == "needs_review"
    calls = telegram.calls
    flush_outbound(bot, telegram, store, admin, now=NOW + timedelta(hours=1))
    assert telegram.calls == calls
    assert client.calls == 1


def test_user_vuot_limit_khong_anh_huong_user_khac(tmp_path):
    client = FakeClient(payload(last_update="2026-10-22 03:30:00"))
    bot = service(
        tmp_path,
        client,
        customer_access_enabled=True,
        allowed_telegram_ids=frozenset(),
        user_rate_limit=2,
        user_rate_window_sec=600,
        user_cooldown_sec=300,
    )
    for index in (1, 2, 3):
        reply = bot.handle_text(111, "a", "https://shopee.vn/product/9/8", update_id=index, now=NOW)
    assert client.calls == 2
    assert "tạm dừng" in reply.text
    assert "5 phút" in reply.text
    guide = bot.handle_text(111, "a", "/huongdan", update_id=4, now=NOW)
    assert "HƯỚNG DẪN SỬ DỤNG" in guide.text
    other = bot.handle_text(222, "b", "https://shopee.vn/product/9/8", update_id=5, now=NOW)
    assert other.button_url
    assert client.calls == 3
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests WHERE telegram_user_id=111").fetchone()[0] == 2


def test_restart_van_gui_lai_dung_link(tmp_path):
    path = tmp_path / "cashback.sqlite"
    store = TrackingRepository(str(path))
    store.migrate()
    client = FakeClient(_fresh())
    bot = service(tmp_path, client, delivery_backoff_sec=60)
    bot.repo = store

    class Down:
        def send_message(self, chat_id, html, reply_markup=None):
            raise requests.ConnectionError("down")

    process_updates(bot, Down(), store, [_update(4, 111)], _Admin(), now=NOW)
    sub_id = sqlite3.connect(path).execute("SELECT sub_id FROM link_requests").fetchone()[0]
    restarted = TrackingRepository(str(path))
    restarted.migrate()

    class Up:
        def __init__(self):
            self.markup = None

        def send_message(self, chat_id, html, reply_markup=None):
            self.markup = reply_markup

    telegram = Up()
    flush_outbound(bot, telegram, restarted, _Admin(), now=NOW + timedelta(minutes=2))
    row = sqlite3.connect(path).execute("SELECT sub_id, delivery_status FROM link_requests").fetchone()
    assert row == (sub_id, "sent")
    assert "sub_id=" + sub_id in telegram.markup["inline_keyboard"][0][0]["url"]
    assert client.calls == 1


def test_backup_bo_qua_giao_dich_chua_commit(tmp_path):
    source = tmp_path / "cashback.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE link_requests (id INTEGER PRIMARY KEY, sub_id TEXT)")
    conn.execute("INSERT INTO link_requests (sub_id) VALUES ('abcdefgh')")
    conn.commit()
    other = sqlite3.connect(source)
    other.execute("INSERT INTO link_requests (sub_id) VALUES ('zzzzzzzz')")
    dest = backup_database(source, tmp_path / "backups", now=NOW, keep=5)
    assert integrity_ok(dest)
    seen = sqlite3.connect(dest).execute("SELECT sub_id FROM link_requests").fetchall()
    assert seen == [("abcdefgh",)]
    other.rollback()


def test_restore_ra_file_moi_va_tu_choi_de_len_db_that(tmp_path):
    source = tmp_path / "cashback.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE link_requests (id INTEGER PRIMARY KEY, sub_id TEXT)")
    conn.execute("INSERT INTO link_requests (sub_id) VALUES ('abcdefgh')")
    conn.commit()
    conn.close()
    backup = backup_database(source, tmp_path / "backups", now=NOW, keep=5)
    restored = tmp_path / "restored.sqlite"
    restore_database(backup, restored, protected=source)
    assert sqlite3.connect(restored).execute("SELECT sub_id FROM link_requests").fetchone()[0] == "abcdefgh"
    with pytest.raises(RuntimeError):
        restore_database(backup, source, protected=source)
    assert sqlite3.connect(source).execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 1


def test_backup_hong_khong_duoc_restore(tmp_path):
    bad = tmp_path / "cashback-broken.sqlite"
    bad.write_bytes(b"not a database")
    assert integrity_ok(bad) is False
    with pytest.raises(RuntimeError):
        restore_database(bad, tmp_path / "out.sqlite")
    assert not (tmp_path / "out.sqlite").exists()


def test_prune_backup_cu(tmp_path):
    source = tmp_path / "cashback.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    folder = tmp_path / "backups"
    first = backup_database(source, folder, now=NOW, keep=2)
    second = backup_database(source, folder, now=NOW + timedelta(seconds=1), keep=2)
    third = backup_database(source, folder, now=NOW + timedelta(seconds=2), keep=2)
    names = sorted(path.name for path in folder.glob("cashback-*.sqlite"))
    assert first.name not in names
    assert names == [second.name, third.name]


def test_production_db_khong_doi_va_khong_dong_conversion_sync():
    if not LIVE_DB.exists():
        return
    before = hashlib.md5(LIVE_DB.read_bytes()).hexdigest()
    assert before == hashlib.md5(LIVE_DB.read_bytes()).hexdigest()
    text = Path("/home/vu/toolsauto/cashback_bot/backup.py").read_text(encoding="utf-8")
    assert "shopee_conversion_v2" not in text
