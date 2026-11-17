"""PLAN-173: cohort/24h/nguồn/returning trên DB tạm; không gọi dịch vụ bên ngoài."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from cashback_bot import growth_funnel, growth_report

NOW = datetime(2026, 11, 17, 1, tzinfo=timezone.utc)


@pytest.fixture
def dbs(tmp_path):
    cb, st = tmp_path / "cashback.sqlite", tmp_path / "store.sqlite"
    with sqlite3.connect(cb) as c:
        c.executescript("""
        CREATE TABLE telegram_users (telegram_user_id INTEGER, username TEXT, created_at TEXT, last_seen_at TEXT);
        CREATE TABLE bot_state (key TEXT, value TEXT);
        CREATE TABLE channel_identities (internal_user_id INTEGER, display_name TEXT, created_at TEXT);
        CREATE TABLE link_requests (id INTEGER, telegram_user_id INTEGER, sub_id TEXT, link_status TEXT, created_at TEXT);
        CREATE TABLE shopee_clicks (click_id TEXT, sub_id TEXT, click_time TEXT);
        CREATE TABLE shopee_conversions (conversion_id TEXT, order_sn TEXT, telegram_user_id INTEGER,
            order_status TEXT, validation_status TEXT, fraud_flag INTEGER, purchase_time TEXT);
        CREATE TABLE admin_notifications (event_type TEXT, created_at TEXT);
        INSERT INTO telegram_users VALUES
            (1,'private_name','2026-11-15T00:00:00Z',NULL),
            (2,NULL,'2026-11-16T00:00:00+00:00',NULL),
            (-3,NULL,'2026-11-16T15:00:00Z',NULL),
            (4,NULL,'2026-11-09T00:00:00Z',NULL),
            (5,NULL,'2026-11-17T01:00:00+00:00',NULL),
            (6,NULL,'2026-11-10T08:00:00+07:00',NULL);
        INSERT INTO bot_state VALUES ('src:1','threads_cb_save'),('src:2','threads_cb_save'),('src:-3','threads_cb_dm');
        INSERT INTO link_requests VALUES
            (1,1,'bad','rejected','2026-11-15T01:00:00Z'),
            (2,1,'a','created','2026-11-15T03:00:00Z'),
            (3,1,'b','created','2026-11-15T18:00:00Z'),
            (4,2,'c','created','2026-11-17T00:00:00Z'),
            (5,-3,'d','created','2026-11-16T16:00:00Z'),
            (6,4,'e','created','2026-11-16T16:00:00Z');
        INSERT INTO shopee_clicks VALUES
            ('1','a','2026-11-15T04:00:00Z'),('2','a','2026-11-15T05:00:00Z'),
            ('3','unknown','2026-11-15T04:00:00Z'),('4','bad','2026-11-15T04:00:00Z'),
            ('5','c','2026-11-16T23:00:00Z'),('6','b','invalid');
        INSERT INTO shopee_conversions VALUES
            ('a1','A',1,'PAID','UNKNOWN',0,'2026-11-15T04:00:00Z'),
            ('a2','A',1,'PAID','UNKNOWN',0,'2026-11-15T04:00:00Z'),
            ('b','B',2,'CANCELLED','UNKNOWN',0,'2026-11-16T01:00:00Z'),
            ('c','C',2,'PAID','FRAUD',0,'2026-11-16T01:00:00Z'),
            ('d','D',2,'PAID','UNKNOWN',1,'2026-11-16T01:00:00Z'),
            ('e','E',2,'PAID','REJECTED',0,'2026-11-16T01:00:00Z'),
            ('f','F',2,'PAID','UNKNOWN',0,NULL);
        """)
    with sqlite3.connect(st) as c:
        c.executescript("""
        CREATE TABLE users (user_id INTEGER, username TEXT, first_name TEXT, balance INTEGER,
            created_at TEXT, last_seen_at TEXT);
        CREATE TABLE state (key TEXT, value TEXT);
        CREATE TABLE topups (id INTEGER, user_id INTEGER, created_at TEXT, resolved_at TEXT,
            intent_product_id INTEGER, status TEXT);
        CREATE TABLE orders (id INTEGER, user_id INTEGER, created_at TEXT, status TEXT, total INTEGER, refunded INTEGER);
        INSERT INTO users VALUES
            (10,'private_store_name',NULL,0,'2026-11-15T00:00:00Z',NULL),
            (11,NULL,NULL,0,'2026-11-16T00:00:00+00:00',NULL),
            (12,NULL,NULL,0,'2026-11-16T12:00:00Z',NULL),
            (13,NULL,NULL,0,'2026-11-10T01:00:00Z',NULL),
            (14,NULL,NULL,0,'2026-11-10T00:59:59Z',NULL),
            (15,NULL,NULL,0,'2026-11-17T01:00:00Z',NULL),
            (16,NULL,NULL,0,'2026-11-15T01:00:00Z',NULL);
        INSERT INTO state VALUES ('src:10','threads_ai_price'),('src:11','threads_ai_price'),
            ('src:16','threads_ai_price'),('src:12','<b>&bad'),
            ('step:product:10','2@2026-11-15T01:00:00Z'),('step:confirm:10','2@2026-11-15T02:00:00Z'),
            ('step:product:11','2@not_a_time'),('step:product:12','2@2026-11-17T02:00:00Z');
        INSERT INTO topups VALUES
            (1,10,'2026-11-15T02:00:00Z','2026-11-15T03:00:00Z',2,'paid'),
            (2,11,'2026-11-16T02:00:00Z',NULL,NULL,'pending');
        INSERT INTO orders VALUES
            (1,10,'2026-11-15T23:59:59Z','done',1000,0),
            (2,10,'2026-11-16T02:00:00Z','partial',2000,1000),
            (3,11,'2026-11-16T02:00:00Z','failed',1000,0),
            (4,11,'2026-11-16T03:00:00Z','done',1000,1000),
            (5,12,'2026-11-16T13:00:00Z','done',1000,0),
            (6,13,'2026-11-09T12:00:00Z','done',1000,0),
            (7,16,'2026-11-16T01:00:00Z','done',1000,0),
            (8,14,'2026-11-16T01:00:00Z','done',1000,0),
            (9,15,'2026-11-17T01:00:00Z','done',1000,0),
            (10,11,'2026-11-17T02:00:00Z','done',1000,0);
        """)
    return cb, st


def _report(dbs, now=NOW):
    return growth_funnel.report(now, cashback_path=dbs[0], store_path=dbs[1])


def test_cohort_sources_stages_and_mature_24h(dbs):
    rep = _report(dbs)
    assert rep["errors"] == []
    bots = {r["bot"]: r for r in rep["bots"]}
    store = bots["ai_store"]
    assert store["customers"] == 5  # boundary included, old/future excluded
    assert store["stages"] == {"product": 1, "confirm": 1, "qr": 1, "paid": 1, "order": 3}
    assert (store["mature_24h"], store["converted_24h"], store["not_converted_24h"]) == (4, 1, 3)
    assert store["conversion_24h_pct"] == 25.0
    assert store["repeat_customers"] == 1  # partial counts; failed/full refund do not
    source = next(r for r in rep["sources"] if r["source"] == "threads_ai_price")
    assert (source["customers"], source["converted_24h"], source["mature_24h"]) == (3, 1, 3)
    assert source["conversion_24h_pct"] == 33.3
    assert bots["cashbot_tg"]["stages"] == {"link": 2, "click": 1, "order": 1}
    assert (bots["cashbot_tg"]["mature_24h"], bots["cashbot_tg"]["converted_24h"]) == (3, 1)
    assert bots["cashbot_tg"]["repeat_customers"] == 1  # 03Z and 18Z are different VN days
    assert bots["cashbot_zalo"]["customers"] == 1
    assert bots["cashbot_zalo"]["converted_24h"] == 0  # new successful user not in denominator yet
    assert bots["cashbot_zalo"]["conversion_24h_pct"] is None
    assert any(r["source"] == growth_funnel.NO_SOURCE for r in rep["sources"])
    assert "private_" not in json.dumps(rep) and "user_id" not in json.dumps(rep)


def test_same_instant_with_offset_and_naive_time(dbs):
    assert _report(dbs) == _report(dbs, NOW.astimezone(timezone(timedelta(hours=7))))
    assert _report(dbs) == _report(dbs, NOW.replace(tzinfo=None))


def test_report_is_readonly_and_missing_db_not_created(dbs, tmp_path):
    before = [p.read_bytes() for p in dbs]
    _report(dbs)
    assert [p.read_bytes() for p in dbs] == before
    with growth_funnel._open(dbs[0]) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO bot_state VALUES ('oops','oops')")
    missing = tmp_path / "missing.sqlite"
    rep = growth_funnel.report(NOW, cashback_path=missing, store_path=dbs[1])
    assert len(rep["errors"]) == 1 and not missing.exists()
    assert [b["bot"] for b in rep["bots"]] == ["ai_store"]


def test_broken_schema_keeps_other_bot_and_does_not_claim_zero(dbs):
    with sqlite3.connect(dbs[1]) as conn:
        conn.execute("DROP TABLE orders")  # temporary test DB only
    rep = _report(dbs)
    assert len(rep["errors"]) == 1
    assert {b["bot"] for b in rep["bots"]} == {"cashbot_tg", "cashbot_zalo"}


@pytest.mark.parametrize("days", [0, -1, 91])
def test_reject_invalid_window(days):
    with pytest.raises(ValueError):
        growth_funnel.report(days=days)


def test_summary_escapes_sources_and_build_includes_it(dbs):
    rep = _report(dbs)
    text = growth_funnel.summary(rep, limit=99)
    assert "&lt;b&gt;&amp;bad" in text and "<b>&bad" not in text
    assert "Cashbot · Zalo" in text and "chưa đủ 24h" in text
    built = growth_report.build(NOW, *dbs)
    assert "Báo cáo tăng trưởng 17/11" in built
    assert "Phễu theo nguồn" in built and "threads_ai_price" in built
    assert len(built) <= 4000


def test_summary_stays_bounded_with_many_sources(dbs):
    rep = _report(dbs)
    row = rep["sources"][0]
    rep["sources"] = [{**row, "source": "<" * 32} for _ in range(100)]
    assert growth_funnel.summary(rep).count("&lt;" * 32) == 3
    assert len(growth_funnel.summary(rep)) < 1600


def test_cli_json_and_error_exit(dbs, monkeypatch, capsys):
    snapshot = _report(dbs)
    monkeypatch.setattr(growth_funnel, "report", lambda **kw: snapshot)
    monkeypatch.setattr("sys.argv", ["growth_funnel", "--json"])
    assert growth_funnel.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert len(body["bots"]) == 3 and body["days"] == 7
    monkeypatch.setattr(growth_funnel, "report", lambda **kw: {"errors": ["missing"]})
    assert growth_funnel.main() == 1
