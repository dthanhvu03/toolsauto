"""PLAN-172: báo cáo tăng trưởng 8h sáng — một lần / ngày, đọc đúng số từ 2 DB bot."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from cashback_bot import growth_report

NOW = datetime(2026, 11, 17, 1, 30, tzinfo=timezone.utc)  # 08:30 VN 17/11


def _dbs(tmp_path):
    cb, st = tmp_path / "cb.sqlite", tmp_path / "st.sqlite"
    with sqlite3.connect(cb) as c:
        c.executescript("""
        CREATE TABLE telegram_users (telegram_user_id INTEGER, username TEXT, created_at TEXT, last_seen_at TEXT);
        CREATE TABLE channel_identities (internal_user_id INTEGER, display_name TEXT, created_at TEXT);
        CREATE TABLE bot_state (key TEXT, value TEXT);
        CREATE TABLE link_requests (telegram_user_id INTEGER, link_status TEXT, created_at TEXT);
        CREATE TABLE shopee_conversions (telegram_user_id INTEGER, order_sn TEXT, order_status TEXT);
        CREATE TABLE admin_notifications (event_type TEXT, created_at TEXT);
        INSERT INTO telegram_users VALUES (1, 'a', '2026-11-16T03:00:00Z', NULL), (2, 'b', '2026-11-01T03:00:00Z', NULL);
        INSERT INTO link_requests VALUES (1, 'created', '2026-11-16T04:00:00Z');
        INSERT INTO shopee_conversions VALUES (1, 'X', 'PAID');
        INSERT INTO admin_notifications VALUES ('CHAT_AI_ANSWER', '2026-11-16T05:00:00Z');
        """)
    with sqlite3.connect(st) as c:
        c.executescript("""
        CREATE TABLE users (user_id INTEGER, username TEXT, first_name TEXT, balance INTEGER, created_at TEXT, last_seen_at TEXT);
        CREATE TABLE state (key TEXT, value TEXT);
        CREATE TABLE orders (id INTEGER, user_id INTEGER, status TEXT, total INTEGER, refunded INTEGER, created_at TEXT);
        CREATE TABLE topups (user_id INTEGER, status TEXT, resolved_at TEXT);
        INSERT INTO users VALUES (10, 'x', 'X', 0, '2026-11-16T02:00:00+00:00', NULL),
                                 (11, 'y', 'Y', 0, '2026-11-16T02:10:00+00:00', NULL);
        INSERT INTO topups VALUES (10, 'paid', '2026-11-16T02:05:00+00:00');
        INSERT INTO state VALUES ('step:product:10', '1@x'), ('step:product:11', '1@x'), ('step:confirm:10', '1@x'),
                                 ('closed_manual', '1');
        INSERT INTO orders VALUES (1, 10, 'done', 21000, 0, '2026-11-16T02:06:00+00:00');
        """)
    return cb, st


def test_build_counts(tmp_path):
    cb, st = _dbs(tmp_path)
    text = growth_report.build(NOW, cb, st)
    assert "Báo cáo tăng trưởng 17/11" in text
    assert "Khách dùng thật 7 ngày: <b>2</b>" in text  # 1 Cashbot (link) + 1 Store (đơn)
    assert "AI Store: 2 khách mới · 1 đơn · 21.000đ" in text
    assert "Cashbot: 1 khách mới · 1 link" in text
    assert "AI Store: 2 vào → 2 xem món → 1 chọn số lượng → 1 tạo mã nạp (50%) → 1 có đơn (50%)" in text
    assert "ĐÓNG TAY" in text
    assert "Cashbot: 1 vào → 1 tạo link (100%) → 1 có đơn (100%)" in text
    assert "có đơn 1/2 (50%" in text and "hôm qua 1 câu" in text


class _Repo:
    def __init__(self):
        self.state, self.events = {}, []

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = value

    def enqueue_admin_event(self, **kw):
        self.events.append(kw)


class _Notifier:
    chat_id = "99"

    def _active(self):
        return True


def test_tick_once_per_day_after_8(tmp_path, monkeypatch):
    monkeypatch.setattr(growth_report, "build", lambda now: "body")
    repo = _Repo()
    assert not growth_report.tick(repo, _Notifier(), datetime(2026, 11, 17, 0, 30, tzinfo=timezone.utc))  # 07:30 VN
    assert growth_report.tick(repo, _Notifier(), NOW)
    assert not growth_report.tick(repo, _Notifier(), NOW)
    assert repo.events == [{"event_key": "growth_report:2026-11-17", "event_type": "GROWTH_REPORT",
                            "chat_id": 99, "message_html": "body"}]
