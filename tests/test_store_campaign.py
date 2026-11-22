"""Product cohort analytics use temporary SQLite and never change customer state."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from cashback_bot import store_campaign

SINCE = datetime(2026, 11, 18, 2, tzinfo=timezone.utc)
UNTIL = SINCE + timedelta(days=2)


@pytest.fixture
def path(tmp_path):
    path = tmp_path / "store.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users(user_id INTEGER, created_at TEXT, username TEXT);
            CREATE TABLE state(key TEXT, value TEXT);
            CREATE TABLE products(id INTEGER, name TEXT, price INTEGER, description TEXT, active INTEGER,
                upstream_id INTEGER, upstream_available INTEGER, upstream_stock INTEGER, synced_at TEXT);
            CREATE TABLE topups(id INTEGER, user_id INTEGER, intent_product_id INTEGER, status TEXT,
                created_at TEXT, resolved_at TEXT);
            CREATE TABLE orders(user_id INTEGER, product_id INTEGER, total INTEGER, refunded INTEGER,
                status TEXT, created_at TEXT);
            INSERT INTO products VALUES(7,'CapCut',34000,'Catalog fact',1,55,1,20,'2026-11-18T02:00:00Z');
            INSERT INTO users VALUES
              (1,'2026-11-18T09:00:00+07:00','PRIVATE-ONE'),
              (2,'2026-11-19T22:00:00Z','PRIVATE-TWO'),
              (3,'2026-11-18T01:59:59Z','OLD'),
              (4,'2026-11-20T02:00:00Z','FUTURE'),
              (5,'2026-11-18T02:01:00Z','ADMIN'),
              (6,'2026-11-18T02:02:00Z','OTHER-SOURCE'),
              (7,'2026-11-18T02:03:00Z','EXACT24'),
              (8,'2026-11-18T02:04:00Z','LITERAL-PREFIX');
            INSERT INTO state VALUES
              ('src:1','threads_ai_price'),('src:2','threads_ai_price'),('src:3','threads_ai_price'),
              ('src:4','threads_ai_price'),('src:5','threads_ai_price'),('src:6','threadsXai_price'),
              ('src:7','threads_ai_auto'),('src:8','threads_%literal'),
              ('step:product:1','7@2026-11-18T03:00:00Z'),('step:confirm:1','7@2026-11-18T03:01:00Z'),
              ('step:product:2','8@2026-11-19T23:00:00Z'),('step:confirm:2','7@not_a_time'),
              ('step:product:7','7@2026-11-18T01:00:00Z');
            INSERT INTO topups VALUES
              (1,1,7,'paid','2026-11-18T04:00:00Z','2026-11-18T04:05:00Z'),
              (2,1,7,'cancelled','2026-11-18T03:00:00Z',NULL),
              (3,2,8,'paid','2026-11-19T23:00:00Z','2026-11-19T23:05:00Z'),
              (4,1,NULL,'paid','2026-11-18T05:00:00Z','2026-11-18T05:01:00Z'),
              (5,5,7,'paid','2026-11-18T05:00:00Z','2026-11-18T05:01:00Z'),
              (6,1,7,'paid','2026-11-18T05:00:00Z','2026-11-20T03:00:00Z');
            INSERT INTO orders VALUES
              (1,7,68000,34000,'partial','2026-11-18T05:10:00Z'),
              (1,8,1000,0,'done','2026-11-18T06:00:00Z'),
              (1,7,34000,34000,'done','2026-11-18T07:00:00Z'),
              (1,7,34000,0,'pending','2026-11-18T08:00:00Z'),
              (1,7,34000,0,'failed','2026-11-18T09:00:00Z'),
              (2,7,34000,0,'done','2026-11-20T01:00:00Z'),
              (3,7,34000,0,'done','2026-11-18T05:00:00Z'),
              (4,7,34000,0,'done','2026-11-20T03:00:00Z'),
              (5,7,34000,0,'done','2026-11-18T05:00:00Z'),
              (7,7,34000,0,'done','2026-11-19T02:03:00Z'),
              (1,7,34000,0,'done','2026-11-20T02:00:00Z');
        """)
    return path


def report(path, **kwargs):
    return store_campaign.report(SINCE, 7, UNTIL, path, exclude_user_ids=(5,), **kwargs)


def test_cohort_product_refunds_prefix_and_24h(path):
    rep = report(path, source_prefix="threads_ai_")
    assert rep["errors"] == []
    cohort = rep["cohort"]
    assert cohort["customers"] == 3 and cohort["not_yet_24h"] == 1
    selected = cohort["selected_product"]
    assert selected["stages"] == {"product": 1, "confirm": 1, "qr": 1, "paid": 1, "order": 3}
    assert selected["qr_requests_by_current_status"] == {"paid": 2, "cancelled": 1}
    assert selected["delivered_orders"] == 3 and selected["revenue_after_refunds"] == 102000
    assert (selected["mature_24h"], selected["converted_24h"], selected["not_converted_24h"]) == (2, 1, 1)
    assert selected["conversion_24h_pct"] == 50
    assert cohort["all_products"]["stages"]["product"] == 2
    assert cohort["all_products"]["stages"]["qr"] == 2
    assert cohort["all_products"]["revenue_after_refunds"] == 103000
    assert rep["product"]["price"] == 34000 and rep["product"]["stock_is_cached"] is True
    assert {row["source"] for row in rep["sources"]} == {"threads_ai_price", "threads_ai_auto"}
    output = json.dumps(rep)
    assert "PRIVATE" not in output and '"user_id"' not in output


def test_literal_prefix_no_sql_wildcards(path):
    rep = report(path, source_prefix="threads_%")
    assert rep["cohort"]["customers"] == 1
    assert rep["sources"][0]["source"] == "threads_%literal"
    assert report(path, source_prefix="no-match")["cohort"]["selected_product"]["conversion_24h_pct"] is None


def test_readonly_and_failure_never_claims_zero(path, tmp_path):
    before = path.read_bytes()
    report(path)
    assert path.read_bytes() == before
    with store_campaign._open(path) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM users")
    missing = tmp_path / "missing.sqlite"
    rep = report(missing)
    assert rep["errors"] and rep["cohort"] is None and not missing.exists()
    missing_product = store_campaign.report(SINCE, 999, UNTIL, path)
    assert missing_product["errors"] == ["ai_store: selected product not found"]


def test_timezone_and_validation(path):
    local = timezone(timedelta(hours=7))
    first = store_campaign.report(SINCE, 7, UNTIL, path)
    second = store_campaign.report(SINCE.astimezone(local), 7, UNTIL.astimezone(local), path)
    assert first == second
    with pytest.raises(ValueError):
        store_campaign.report(SINCE.replace(tzinfo=None), 7, UNTIL, path)
    with pytest.raises(ValueError):
        store_campaign.report(UNTIL, 7, SINCE, path)
    with pytest.raises(ValueError):
        store_campaign.report(SINCE, 0, UNTIL, path)


def test_cli_json_and_exit(path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["store_campaign", "--since", SINCE.isoformat(), "--until", UNTIL.isoformat(),
                                   "--product-id", "7", "--exclude-user-id", "5", "--store-db", str(path), "--json"])
    assert store_campaign.main() == 0
    assert json.loads(capsys.readouterr().out)["cohort"]["customers"] == 5
    monkeypatch.setattr("sys.argv", ["store_campaign", "--since", "2026-11-18", "--product-id", "7"])
    with pytest.raises(SystemExit) as error:
        store_campaign.main()
    assert error.value.code == 2
