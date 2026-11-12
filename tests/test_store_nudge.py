"""store_bot.nudge (12/11): nhắn một lần khách AI Pass Store chưa nạp / chưa mua. Không gọi mạng."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from store_bot import nudge
from store_bot.db import StoreRepository

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


class FakeTg:
    def __init__(self, blocked=()):
        self.sent, self.blocked = [], set(blocked)

    def send_broadcast(self, chat_id, html, markup=None):
        if chat_id in self.blocked:
            return "blocked", 0
        self.sent.append((chat_id, html, markup))
        return "ok", 0


def test_chi_nhan_khach_chua_nap_chua_mua_moi_nguoi_mot_lan(tmp_path):
    path = tmp_path / "store.sqlite"
    repo = StoreRepository(str(path))
    repo.migrate()
    for uid in (1, 2, 3, 4, 5, 6):
        repo.touch_user(uid, None, f"K{uid}")
    old = (NOW - timedelta(days=2)).isoformat()
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE users SET created_at = ?", (old,))
        conn.execute("UPDATE users SET created_at = ? WHERE user_id = 5", (NOW.isoformat(),))  # vừa vào
        conn.execute("UPDATE users SET notify_off = 1 WHERE user_id = 6")
        conn.execute("INSERT INTO orders (user_id, product_id, product_name, quantity, unit_price, total, source, created_at,"
                     " status) VALUES (2, 9, 'Canva', 1, 1100, 1100, 'bot', ?, 'done')", (old,))
    repo.create_topup(3, 10_000) if hasattr(repo, "create_topup") else None
    with sqlite3.connect(path) as conn:
        if conn.execute("SELECT COUNT(*) FROM topups WHERE user_id = 3").fetchone()[0]:
            conn.execute("UPDATE topups SET status = 'paid' WHERE user_id = 3")
    got = nudge.targets(repo, NOW)
    assert got == [1, 4], "2 đã mua, 3 đã nạp, 5 vừa vào, 6 tắt tin"
    tg = FakeTg(blocked={4})
    sent, blocked = nudge.send(repo, tg, got, pause=lambda s: None)
    assert blocked == 1 and [c for c, _h, _m in tg.sent] == [u for u in got if u != 4]
    _chat, html, markup = tg.sent[0]
    assert "1.100đ" in html and "p:9" in str(markup) and "noff" in str(markup)
    assert 1 not in nudge.targets(repo, NOW), "đã nhận thì không gửi lại"
