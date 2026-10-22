"""Shared test fixtures. Cashback DB trong test là bản giả lập, không phải production."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from experiments.shopee_conversion_v2.database import ConversionDatabase
from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader


@pytest.fixture
def tmp_db(tmp_path: Path) -> ConversionDatabase:
    db = ConversionDatabase(tmp_path / "test_conversion.sqlite")
    db.migrate()
    return db


@pytest.fixture
def cashback_db_path(tmp_path: Path) -> Path:
    db_path = tmp_path / "cashback.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE telegram_users (
            telegram_user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE link_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_update_id INTEGER UNIQUE,
            telegram_user_id INTEGER NOT NULL,
            sub_id TEXT UNIQUE,
            original_url TEXT NOT NULL,
            affiliate_url TEXT,
            item_id INTEGER,
            shop_id INTEGER,
            product_name TEXT,
            price_vnd INTEGER,
            estimated_commission INTEGER,
            estimated_cashback INTEGER,
            cashback_rate_percent INTEGER,
            api_status TEXT,
            data_source TEXT,
            product_last_update TEXT,
            link_status TEXT NOT NULL,
            reject_reason TEXT,
            delivery_status TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE bot_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO telegram_users VALUES (?, ?, ?, ?)",
        (111222333, "testuser", "2026-10-01T00:00:00Z", "2026-10-22T00:00:00Z"),
    )
    links = [
        (
            1, 1001, 111222333, "G3lkg1JK", "https://shopee.vn/product/1/1",
            "https://s.shopee.vn/an_redir?redacted", 12345678, 87654321,
            "Test Product A", 200000, 15000, 10500, 70, "ok", "api", None,
            "created", None, "sent", "2026-10-22T01:25:57Z",
        ),
        (
            2, 1002, 111222333, "6mnSXpbe", "https://shopee.vn/product/2/2",
            "https://s.shopee.vn/an_redir?redacted", 22222222, 88888888,
            "Test Product B", 500000, 25000, 17500, 70, "ok", "db", None,
            "created", None, "sent", "2026-10-22T01:25:41Z",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO link_requests (
            id, telegram_update_id, telegram_user_id, sub_id, original_url,
            affiliate_url, item_id, shop_id, product_name, price_vnd,
            estimated_commission, estimated_cashback, cashback_rate_percent,
            api_status, data_source, product_last_update, link_status,
            reject_reason, delivery_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        links,
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def cashback_reader(cashback_db_path: Path) -> CashbackDBReader:
    return CashbackDBReader(cashback_db_path)
