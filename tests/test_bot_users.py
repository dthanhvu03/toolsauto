"""PLAN-168: tổng khách mọi bot (cashback_bot.all_users), API web /bot-users và lệnh admin /users."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.bot_users.router import router as bot_users_router
from cashback_bot import all_users
from store_bot.db import StoreRepository
from tests.test_cashback_wallet import ADMIN, NOW as WALLET_NOW, USER, _bot, _link, _order

STORE_BUYER, STORE_NEW = 501, 502


def _store(tmp_path, now: datetime):
    path = tmp_path / "store.sqlite"
    repo = StoreRepository(str(path))
    repo.migrate()
    repo.touch_user(STORE_BUYER, "mua_hang", "Mua")
    repo.touch_user(STORE_NEW, None, "Mới")
    repo.set_state(f"src:{STORE_BUYER}", "threads_ai_price")
    old = (now - timedelta(days=10)).isoformat()
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE users SET created_at = ?, balance = 9900 WHERE user_id = ?", (old, STORE_BUYER))
        conn.execute(
            "INSERT INTO orders (user_id, product_id, product_name, quantity, unit_price, total, source, created_at, status)"
            " VALUES (?, 1, 'Canva', 1, 1100, 1100, 'bot', ?, 'done')", (STORE_BUYER, (now - timedelta(days=1)).isoformat()))
        conn.execute(
            "INSERT INTO orders (user_id, product_id, product_name, quantity, unit_price, total, source, created_at, status)"
            " VALUES (?, 1, 'Canva', 1, 1100, 1100, 'bot', ?, 'failed')", (STORE_NEW, now.isoformat()))
    return path


def _cashback(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, cid="a")
    _order(bot, sub, status="CANCELLED", cid="b")
    with bot.repo.connect() as conn:
        conn.execute("INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) VALUES (-5, NULL, ?, ?)",
                     ("2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z"))
        conn.execute("INSERT INTO channel_identities (internal_user_id, channel, external_id, display_name, created_at)"
                     " VALUES (-5, 'zalo', 'z1', 'Chị Zalo', '2026-10-01T00:00:00Z')")
    bot.repo.set_state(f"src:{USER}", "threads_cb_save")
    return bot


def test_report_dem_dung_tung_bot(tmp_path):
    bot = _cashback(tmp_path)
    now = WALLET_NOW + timedelta(hours=1)
    rep = all_users.report(now, cashback_path=bot.repo.path, store_path=_store(tmp_path, now))
    assert not rep.errors
    by = {s.bot: s for s in rep.bots}
    tg, zalo, store = by["cashbot_tg"], by["cashbot_zalo"], by["ai_store"]
    assert tg.total >= 1 and tg.buyers == 1 and tg.active_7d >= 1, "đơn huỷ không tính, có link = đang dùng"
    assert (zalo.total, zalo.active_7d, zalo.buyers) == (1, 0, 0)
    assert (store.total, store.buyers, store.active_7d, store.new_7d) == (2, 1, 1, 1), "đơn failed không tính có đơn"
    assert rep.total.total == tg.total + zalo.total + store.total
    buyer = next(p for p in rep.people if p.user_id == STORE_BUYER)
    assert (buyer.name, buyer.source, buyer.orders, buyer.spent, buyer.balance) == ("@mua_hang", "threads_ai_price", 1, 1100, 9900)
    assert next(p for p in rep.people if p.user_id == -5).name == "Chị Zalo"
    assert ("threads_cb_save", 1) in rep.sources["cashbot_tg"] and rep.sources["cashbot_zalo"] == [(all_users.NO_SOURCE, 1)]
    assert len(rep.days) == all_users.DAYS and sum(d["ai_store"] for _day, d in rep.days) == 1
    assert [p.user_id for p in all_users.search(rep.people, "@MUA")] == [STORE_BUYER]
    assert all(p.bot == "cashbot_zalo" for p in all_users.search(rep.people, bot="cashbot_zalo"))


def test_report_thieu_db_store_van_tra_cashbot(tmp_path):
    bot = _cashback(tmp_path)
    rep = all_users.report(WALLET_NOW, cashback_path=bot.repo.path, store_path=tmp_path / "khong_co.sqlite")
    assert rep.errors and rep.errors[0].startswith("AI Pass Store")
    assert {s.bot: s.total for s in rep.bots}["ai_store"] == 0 and rep.total.total > 0


def test_api_report(tmp_path, monkeypatch):
    bot = _cashback(tmp_path)
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    monkeypatch.setenv("STORE_DB_PATH", str(_store(tmp_path, datetime.now(timezone.utc))))
    app = FastAPI()
    app.include_router(bot_users_router)
    body = TestClient(app).get("/bot-users/api/report", params={"q": "mua", "bot": "ai_store"}).json()
    assert [b["bot"] for b in body["bots"]] == list(all_users.BOTS)
    assert body["matched"] == 1 and body["people"][0]["user_id"] == STORE_BUYER
    assert len(body["days"]) == all_users.DAYS and "ai_store" in body["days"][0]


def test_lenh_users_admin(tmp_path, monkeypatch):
    bot = _cashback(tmp_path)
    monkeypatch.setenv("STORE_DB_PATH", str(_store(tmp_path, WALLET_NOW)))
    reply = bot.handle_text(ADMIN, "admin", "/users", update_id=90, now=WALLET_NOW)
    assert "Khách các bot" in reply.text and "AI Pass Store" in reply.text and "Tổng" in reply.text
    found = bot.handle_text(ADMIN, "admin", "/users Chị Zalo", update_id=91, now=WALLET_NOW)
    assert "Chị Zalo" in found.text and "c:in:d:-5" in str(found.inline_keyboard)
    store = bot.handle_text(ADMIN, "admin", f"/users {STORE_BUYER}", update_id=92, now=WALLET_NOW)
    assert "@mua_hang" in store.text and "c:in:d:" not in str(store.inline_keyboard[0]), "khách Store không có hồ sơ Cashbot"
    assert "Khách các bot" not in bot.handle_text(USER, "buyer", "/users", update_id=93, now=WALLET_NOW).text
