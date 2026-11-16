"""PLAN-172 T4: sau đơn Store done mời Cashbot. Không gọi mạng."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from store_bot import cashbot_invite
from store_bot.bot import StoreBot
from store_bot.config import BankAccount, Settings
from store_bot.db import StoreRepository
from store_bot.fulfill import Fulfiller

ADMIN = 1
BUYER = 2
BUYER2 = 3
NOW = datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)


class FakeTelegram:
    def __init__(self, blocked=()):
        self.sent = []
        self.broadcasts = []
        self.blocked_ids = set(blocked)
        self._next_id = 100

    def send_broadcast(self, chat_id, html, reply_markup=None):
        if chat_id in self.blocked_ids:
            return "blocked", 0
        self.broadcasts.append((chat_id, html, reply_markup))
        return "ok", 0

    def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
        self._next_id += 1
        self.sent.append((chat_id, html, reply_markup))
        return self._next_id

    def edit_message_text(self, chat_id, message_id, html, reply_markup=None):
        return True

    def answer_callback(self, callback_query_id, text=None, show_alert=False):
        return None

    def send_document(self, chat_id, filename, data, caption=None):
        return True


def _settings(**extra) -> Settings:
    base = dict(
        bot_token="t", admin_ids=frozenset({ADMIN}), shop_name="Test Shop",
        bank=BankAccount("970422", "0123456789", "NGUYEN VAN A", "MB"),
        cashbot_username="zt_shopee_bot",
    )
    base.update(extra)
    return Settings(**base)


def _repo(tmp_path) -> StoreRepository:
    repo = StoreRepository(str(tmp_path / "store.sqlite"))
    repo.migrate()
    for uid, name in ((ADMIN, "boss"), (BUYER, "khach"), (BUYER2, "khach2")):
        repo.touch_user(uid, name, name)
    return repo


def _done_order(repo: StoreRepository, user_id: int, product_id: int) -> None:
    with sqlite3.connect(repo.path) as conn:
        conn.execute(
            "INSERT INTO orders (user_id, product_id, product_name, quantity, unit_price, total, source, "
            "created_at, status) VALUES (?, ?, 'Canva', 1, 1100, 1100, 'bot', ?, 'done')",
            (user_id, product_id, NOW.isoformat()),
        )


def test_targets_chi_khach_done_chua_moi(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    pid = repo.add_product("Canva", 1100, "")
    repo.add_stock(pid, ["a"])
    _done_order(repo, BUYER, pid)
    _done_order(repo, BUYER2, pid)
    repo.set_state(cashbot_invite.state_key(BUYER2), NOW.isoformat())
    monkeypatch.setattr(cashbot_invite, "_already_on_cashbot", lambda: set())
    assert cashbot_invite.targets(repo) == [BUYER]


def test_targets_bo_khach_da_tao_link_cashbot(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    pid = repo.add_product("Canva", 1100, "")
    _done_order(repo, BUYER, pid)
    _done_order(repo, BUYER2, pid)
    monkeypatch.setattr(cashbot_invite, "_already_on_cashbot", lambda: {BUYER})
    assert cashbot_invite.targets(repo) == [BUYER2]


def test_send_one_lan_va_co_link_store_xsell(tmp_path):
    repo = _repo(tmp_path)
    tg = FakeTelegram()
    assert cashbot_invite.send_one(repo, tg, BUYER) == "ok"
    assert len(tg.broadcasts) == 1
    _uid, html, markup = tg.broadcasts[0]
    assert "hoàn tiền" in html.lower() or "Hoàn" in html
    assert markup["inline_keyboard"][0][0]["url"] == "https://t.me/zt_shopee_bot?start=store_xsell"
    assert cashbot_invite.send_one(repo, tg, BUYER) == "skipped"
    assert len(tg.broadcasts) == 1


def test_after_sale_moi_khi_don_bot_co_hang(tmp_path):
    repo = _repo(tmp_path)
    pid = repo.add_product("Canva", 1100, "")
    repo.add_stock(pid, ["https://x"])
    repo.adjust_balance(BUYER, 5_000, "test", "admin")
    tg = FakeTelegram()
    bot = StoreBot(_settings(), repo, tg, "test_store_bot", fulfiller=Fulfiller(repo, None))
    order = repo.buy(BUYER, pid, 1, client_ref="tg:t4")
    assert order.status == "done" and order.items
    bot.after_sale(order, repo.get_user(BUYER))
    assert len(tg.broadcasts) == 1
    assert "store_xsell" in tg.broadcasts[0][2]["inline_keyboard"][0][0]["url"]
    bot.after_sale(order, repo.get_user(BUYER))
    assert len(tg.broadcasts) == 1, "một lần / khách"


def test_after_sale_bo_qua_don_api(tmp_path):
    repo = _repo(tmp_path)
    pid = repo.add_product("Canva", 1100, "")
    repo.add_stock(pid, ["https://x"])
    repo.adjust_balance(BUYER, 5_000, "test", "admin")
    tg = FakeTelegram()
    bot = StoreBot(_settings(), repo, tg, "test_store_bot", fulfiller=Fulfiller(repo, None))
    order = repo.buy(BUYER, pid, 1, client_ref="api:key", source="api")
    assert order.source == "api" and order.items
    bot.after_sale(order, repo.get_user(BUYER))
    assert tg.broadcasts == []


def test_tat_bang_state_off(tmp_path):
    repo = _repo(tmp_path)
    repo.set_state(cashbot_invite.OFF_KEY, "1")
    tg = FakeTelegram()
    assert cashbot_invite.send_one(repo, tg, BUYER) == "skipped"
