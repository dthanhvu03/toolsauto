"""Executive dashboard reads real fixture schemas and keeps unavailable sources separate."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database.models import StudioProject, StudioTask
from app.platform.admin_api import executive
from tests.test_admin_api_lists import _client
from tests.test_bot_users import STORE_BUYER, _cashback, _store
from store_bot.db import StoreRepository


def test_executive_aggregates_and_read_only_store(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    bot = _cashback(tmp_path)
    store_path = _store(tmp_path, now)
    threads_path = tmp_path / "threads.sqlite"
    with sqlite3.connect(threads_path) as conn:
        conn.execute("CREATE TABLE growth_posts (status TEXT)")
        conn.executemany("INSERT INTO growth_posts VALUES (?)", [("posted",), ("posted",), ("pending",)])
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    monkeypatch.setenv("STORE_DB_PATH", str(store_path))
    monkeypatch.setenv("STORE_ADMIN_IDS", "99999")
    monkeypatch.setattr(executive, "THREADS_DB_PATH", threads_path)
    engine, factory, client = _client(tmp_path)
    try:
        with factory() as db:
            db.add(StudioProject(spec={}, status="REVIEW"))
            db.add(StudioTask(flow="upload", stage="render", status="QUEUED"))
            db.commit()
        before = [path.stat().st_mtime_ns for path in (store_path, threads_path)]
        response = client.get("/api/admin/executive")
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == {}
        assert data["threads"]["counts"] == {"pending": 1, "posted": 2}
        assert data["studio"]["projects"] == {"REVIEW": 1}
        assert data["studio"]["tasks"] == {"QUEUED": 1}
        assert data["store"]["revenue"] == 1100
        assert "net_commission" in data["cashback"]
        assert [path.stat().st_mtime_ns for path in (store_path, threads_path)] == before
        with executive.ReadOnlyStore(str(store_path))._read() as conn:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM users")

        monkeypatch.setenv("STORE_ADMIN_IDS", str(STORE_BUYER))
        assert client.get("/api/admin/executive").json()["store"]["revenue"] == 0
        monkeypatch.setenv("STORE_DB_PATH", str(tmp_path / "missing.sqlite"))
        partial = client.get("/api/admin/executive").json()
        assert partial["store"] is None and "store" in partial["errors"]
        assert partial["threads"] and partial["studio"] and partial["cashback"]
        assert not (tmp_path / "missing.sqlite").exists()
    finally:
        engine.dispose()


def test_executive_store_trends_products_refunds_and_admin_exclusion(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    store_path = tmp_path / "store-analytics.sqlite"
    repo = StoreRepository(str(store_path))
    repo.migrate()
    repo.touch_user(501, "buyer", "Buyer")
    repo.touch_user(502, "admin", "Admin")
    high_volume = repo.add_product("Bán nhiều", 100)
    high_margin = repo.add_product("Lãi cao", 100)
    admin_product = repo.add_product("Giao dịch admin", 500)
    volume_leader = repo.add_product("Volume leader", 100)
    no_cost_product = repo.add_product("Chưa có giá vốn", 100)
    low_margin_products = [repo.add_product(f"Món biên thấp {index}", 100) for index in range(5)]
    repo.adjust_balance(501, 9000, "test customer balance", "test")
    repo.add_capital(50_000, "test FatCat capital", "test")
    stamp = now.isoformat(timespec="seconds")
    old = (now - timedelta(days=9)).isoformat(timespec="seconds")
    with sqlite3.connect(store_path) as conn:
        delivered = [
            (501, high_volume, "Bán nhiều", 3, 100, 300, "bot", 270, 0, "done", stamp),
            (501, high_margin, "Lãi cao", 2, 100, 200, "bot", 10, 50, "partial", stamp),
            (502, admin_product, "Giao dịch admin", 10, 500, 5000, "bot", 0, 0, "done", stamp),
            (501, high_volume, "Bán nhiều", 1, 100, 100, "bot", 90, 0, "done", old),
            (501, volume_leader, "Volume leader", 6, 100, 600, "bot", 90, 0, "done", stamp),
            (501, no_cost_product, "Chưa có giá vốn", 1, 100, 100, "bot", None, 0, "done", stamp),
            *((501, product_id, f"Món biên thấp {index}", 1, 100, 100, "bot", 80, 0, "done", stamp)
              for index, product_id in enumerate(low_margin_products)),
        ]
        conn.executemany(
            "INSERT INTO orders(user_id, product_id, product_name, quantity, unit_price, total, source, "
            "unit_cost, refunded, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", delivered,
        )
        order_ids = [row[0] for row in conn.execute("SELECT id FROM orders ORDER BY id")]
        quantities = (3, 2, 10, 1, 6, 1, *(1 for _ in low_margin_products))
        for order_id, quantity in zip(order_ids, quantities):
            conn.executemany("INSERT INTO order_items(order_id, content) VALUES (?, ?)",
                             [(order_id, f"item-{order_id}-{index}") for index in range(quantity)])
        conn.execute(
            "INSERT INTO orders(user_id, product_id, product_name, quantity, unit_price, total, source, "
            "unit_cost, status, waiting_funds, created_at) VALUES (501, ?, 'Lãi cao', 2, 100, 200, 'bot', 10, "
            "'pending', 1, ?)", (high_margin, stamp),
        )
        conn.execute(
            "INSERT INTO topups(user_id, code, amount, status, created_at) VALUES (501, 'PENDING1', 200, 'pending', ?)",
            (stamp,),
        )
        conn.execute(
            "INSERT INTO orders(user_id, product_id, product_name, quantity, unit_price, total, source, "
            "unit_cost, status, waiting_funds, created_at) VALUES (502, ?, 'Admin pending', 1, 100, 100, 'bot', "
            "50, 'pending', 0, ?)", (admin_product, stamp),
        )
        conn.execute(
            "INSERT INTO topups(user_id, code, amount, status, created_at) VALUES (502, 'ADMINPENDING', 100, 'pending', ?)",
            (stamp,),
        )
        conn.execute(
            "INSERT INTO expenses(amount, note, created_by, created_at) VALUES (40, 'fixture expense', 'test', ?)",
            (stamp,),
        )

    bot = _cashback(tmp_path)
    threads_path = tmp_path / "threads-empty.sqlite"
    with sqlite3.connect(threads_path) as conn:
        conn.execute("CREATE TABLE growth_posts (status TEXT)")
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    monkeypatch.setenv("STORE_DB_PATH", str(store_path))
    monkeypatch.setenv("STORE_ADMIN_IDS", "502")
    monkeypatch.setattr(executive, "THREADS_DB_PATH", threads_path)
    engine, _factory, client = _client(tmp_path)
    try:
        seven_response = client.get("/api/admin/executive", params={"days": 7})
        assert seven_response.status_code == 200, seven_response.text
        seven = seven_response.json()
        assert seven["errors"] == {}
        store = seven["store"]
        assert store["revenue"] == 1650
        assert store["cost"] == 1770
        assert store["gross_profit"] == -120
        assert store["external_expense"] == 40
        assert store["profit"] == -160  # net profit = 1650 revenue - 1770 cost - 40 outside expenses
        assert store["top_sellers"][0] == {
            "name": "Volume leader", "sold": 6, "revenue": 600, "gross_profit": 60,
        }
        assert store["top_profit"][0] == {"name": "Lãi cao", "sold": 2, "revenue": 150, "gross_profit": 130}
        assert store["top_profit"][1] == {
            "name": "Chưa có giá vốn", "sold": 1, "revenue": 100, "gross_profit": 100,
        }
        assert len(store["top_sellers"]) == len(store["top_profit"]) == 5
        assert "giá vốn chưa ghi nhận" in store["cost_note"].lower()
        assert store["pending_orders"] == store["pending_topups"] == 1
        assert store["money_position"]["waiting_order_cost"] == 20
        assert store["money_position"]["customer_wallet"] == 9000
        assert store["money_position"]["capital_recorded"] == 50_000
        assert store["money_position"]["capital_used"] == 1860
        assert len(store["trend"]) == 7
        assert len(seven["cashback"]["trend"]) == 7
        with executive.ReadOnlyStore(str(store_path))._read() as conn:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM users")

        thirty = client.get("/api/admin/executive", params={"days": 30}).json()["store"]
        assert thirty["revenue"] == 1750  # includes the older delivered unit
        assert thirty["top_sellers"][0]["sold"] == 6
        assert thirty["trend"] and "–" in thirty["trend"][0]["label"]
        assert client.get("/api/admin/executive", params={"days": 14}).status_code == 422
    finally:
        engine.dispose()


def test_executive_cashback_trend_uses_same_local_period(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    bot = _cashback(tmp_path)
    entries = []
    for index, amount in enumerate((1000, 2500)):
        stamp = (now - timedelta(days=index + 1)).isoformat().replace("+00:00", "Z")
        entries.append((f"analytics-{index}", 111, amount, amount // 2, 0, 0, stamp, stamp, stamp))
    with bot.repo.connect() as conn:
        conn.executemany(
            "INSERT INTO cashback_entries(conversion_id, telegram_user_id, commission_vnd, cashback_vnd, "
            "fee_vnd, tax_vnd, status, purchase_time, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            [(cid, uid, commission, cashback, fee, tax, purchase, created, created)
             for cid, uid, commission, cashback, fee, tax, purchase, created, _ in entries],
        )
    store_path = _store(tmp_path, now)
    threads_path = tmp_path / "threads-empty.sqlite"
    with sqlite3.connect(threads_path) as conn:
        conn.execute("CREATE TABLE growth_posts (status TEXT)")
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    monkeypatch.setenv("STORE_DB_PATH", str(store_path))
    monkeypatch.setenv("STORE_ADMIN_IDS", "99999")
    monkeypatch.setattr(executive, "THREADS_DB_PATH", threads_path)
    engine, _factory, client = _client(tmp_path)
    try:
        response = client.get("/api/admin/executive", params={"days": 7})
        assert response.status_code == 200, response.text
        cashback = response.json()["cashback"]
        assert cashback["period_start"] <= cashback["trend"][0]["day"] <= cashback["period_end"]
        assert cashback["period_start"] <= cashback["trend"][-1]["day"] <= cashback["period_end"]
        assert len(cashback["trend"]) == 7
        assert cashback["net_commission"] == 3500
        assert cashback["customer_share"] == 1750
        assert cashback["money_position"]["customer_waiting"] == 1750
        assert cashback["money_position"]["settled_owner_received_known"] is True
        assert cashback["money_position"]["fund_verified"] is False
        assert cashback["money_position"]["fund_available"] is None
        assert client.get("/api/admin/executive", params={"days": 30}).status_code == 200
    finally:
        engine.dispose()
