"""The persistent CapCut watcher reads Store data and dispatches only new aggregate events."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.features.threads.growth import capcut_supervisor as supervisor
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE

BASE = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)


def make_store(path):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE users(user_id INTEGER PRIMARY KEY, created_at TEXT, last_seen_at TEXT);
            CREATE TABLE state(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, price INTEGER, description TEXT, active INTEGER,
                upstream_id INTEGER, upstream_available INTEGER, upstream_cost INTEGER, upstream_stock INTEGER, synced_at TEXT);
            CREATE TABLE topups(id INTEGER PRIMARY KEY, user_id INTEGER, intent_product_id INTEGER, status TEXT,
                created_at TEXT, resolved_at TEXT);
            CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, total INTEGER,
                refunded INTEGER, status TEXT, created_at TEXT, updated_at TEXT);
            INSERT INTO products VALUES (2,'CapCut Pro',34000,'BHF',1,30,1,31360,20,'2026-11-18T09:00:00Z');
        """)
    return path


def add_user(path, user_id, source=CAPCUT_TRIAL_SOURCE, joined=BASE):
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO users VALUES (?,?,?)", (user_id, joined.isoformat(), joined.isoformat()))
        if source is not None:
            conn.execute("INSERT INTO state VALUES (?,?)", (f"src:{user_id}", source))


def report_no_ids(report):
    encoded = json.dumps(report, ensure_ascii=False)
    assert '"user_id"' not in encoded and '"username"' not in encoded
    assert "901" not in encoded


def test_baseline_is_quiet_exact_source_and_source_written_late(tmp_path, monkeypatch):
    source_db = make_store(tmp_path / "store.sqlite")
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    add_user(source_db, 901, "threads_ai_cc18_anlinh_p1_other")
    add_user(source_db, 902, None)
    calls = []

    def generator(prompt, *, purpose):
        calls.append((prompt, purpose))
        return "specialist summary", {"ok": True, "model": "fake"}

    monkeypatch.setattr(supervisor, "REPORT_DIR", tmp_path / "reports")
    since = BASE - timedelta(seconds=1)
    first = supervisor.tick(source_db, state_db, (), since, BASE + timedelta(days=1), generator)
    assert first["status"] == "baseline"
    assert calls == []

    with sqlite3.connect(source_db) as conn:
        conn.execute("INSERT INTO state VALUES (?,?)", ("src:902", CAPCUT_TRIAL_SOURCE))
    current = BASE + timedelta(days=1, seconds=2)
    event = supervisor.tick(source_db, state_db, (), since, current, generator)
    assert event["status"] == "event"
    assert event["current"]["new_users"] == 1
    assert event["current"]["product_markers"] == 0
    assert event["dispatch"]["status"] == "debouncing"
    with sqlite3.connect(source_db) as conn:
        conn.execute("INSERT INTO state VALUES (?,?)", ("step:product:902", f"2@{(current + timedelta(seconds=2)).isoformat()}"))
    second = supervisor.detect_once(source_db, state_db, (), since, current + timedelta(seconds=3))
    assert second["status"] == "event" and second["changed"] == ["product_markers"]
    dispatch = supervisor.dispatch_once(state_db, current + timedelta(seconds=13), generator, cooldown=0)
    assert dispatch["status"] == "done"
    assert dispatch["coalesced_event_count"] == 2
    assert len(calls) == 3
    event["dispatch"] = dispatch
    assert event["dispatch"]["roles"] == ["measurement", "conversion", "content"]
    assert len(calls) == 3
    report_no_ids(event["current"])
    with sqlite3.connect(state_db) as conn:
        stored = conn.execute("SELECT status,specialist_json FROM events ORDER BY observed_at").fetchall()
    assert all(row[0] == "done" and len(json.loads(row[1])) == 3 for row in stored)

    unchanged = supervisor.tick(source_db, state_db, (), since, current + timedelta(seconds=5), generator)
    assert unchanged["status"] == "unchanged"
    assert len(calls) == 3


def test_catalog_sync_noise_does_not_dispatch(tmp_path, monkeypatch):
    source_db = make_store(tmp_path / "store.sqlite")
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    add_user(source_db, 901, joined=BASE - timedelta(minutes=1))
    monkeypatch.setattr(supervisor, "REPORT_DIR", tmp_path / "reports")
    since = BASE - timedelta(seconds=1)
    supervisor.detect_once(source_db, state_db, (), since, BASE)
    with sqlite3.connect(source_db) as conn:
        conn.execute("UPDATE products SET upstream_stock=17,synced_at=? WHERE id=2", ((BASE + timedelta(seconds=5)).isoformat(),))
    event = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(seconds=5))
    assert event["status"] == "unchanged"
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_delivered_order_and_refund_changes_create_new_aggregate_events(tmp_path, monkeypatch):
    source_db = make_store(tmp_path / "store.sqlite")
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    add_user(source_db, 901)
    since = BASE - timedelta(seconds=1)
    monkeypatch.setattr(supervisor, "REPORT_DIR", tmp_path / "reports")
    supervisor.detect_once(source_db, state_db, (), since, BASE)
    with sqlite3.connect(source_db) as conn:
        conn.execute("INSERT INTO orders VALUES (1,901,2,34000,0,'pending',?,?)",
                     (BASE.isoformat(), BASE.isoformat()))
        conn.execute("UPDATE orders SET status='done',updated_at=? WHERE id=1", ((BASE + timedelta(minutes=1)).isoformat(),))
    delivered = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(minutes=1))
    assert delivered["status"] == "event"
    assert delivered["current"]["delivered_orders"] == 1
    assert "delivered_orders" in delivered["changed"]
    with sqlite3.connect(source_db) as conn:
        conn.execute("UPDATE orders SET status='partial',refunded=10000,updated_at=? WHERE id=1",
                     ((BASE + timedelta(minutes=2)).isoformat(),))
    refunded = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(minutes=2))
    assert refunded["status"] == "event"
    assert refunded["current"]["revenue_after_refunds"] == 24000


def test_sidecar_restart_dedupes_and_ai_cooldown_preserves_queue(tmp_path, monkeypatch):
    source_db = make_store(tmp_path / "store.sqlite")
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    add_user(source_db, 901)
    monkeypatch.setattr(supervisor, "REPORT_DIR", tmp_path / "reports")
    since = BASE - timedelta(seconds=1)
    supervisor.detect_once(source_db, state_db, (), since, BASE)
    with sqlite3.connect(source_db) as conn:
        conn.execute("INSERT INTO state VALUES (?,?)", ("step:product:901", f"2@{(BASE + timedelta(minutes=1)).isoformat()}"))
    first = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(minutes=1, seconds=2))
    assert first["status"] == "event"
    with sqlite3.connect(state_db) as conn:
        conn.execute("UPDATE state SET value=? WHERE key='last_ai_started'",
                     ((BASE + timedelta(seconds=30)).isoformat(),))
    calls = []

    def generator(prompt, *, purpose):
        calls.append(prompt)
        return "summary", {"ok": True}

    cooled = supervisor.dispatch_once(state_db, BASE + timedelta(minutes=1, seconds=13), generator, cooldown=3600)
    assert cooled["status"] == "cooldown" and calls == []
    supervisor.initialize(state_db)  # daemon restart must preserve queued event and baseline
    done = supervisor.dispatch_once(state_db, BASE + timedelta(hours=2), generator, cooldown=3600)
    assert done["status"] == "done" and len(calls) == 3
    repeated = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(hours=2, seconds=3))
    assert repeated["status"] == "unchanged", repeated
    report = json.loads(next((tmp_path / "reports").glob("*.json")).read_text())
    report_no_ids(report)
    assert report["suggest_only"] and report["customer_or_public_actions"] == 0


def test_source_database_is_read_only_and_failure_does_not_become_zero(tmp_path):
    source_db = make_store(tmp_path / "store.sqlite")
    before = source_db.read_bytes()
    result = store_campaign_report(source_db)
    assert result["cohort"]["customers"] == 0
    assert source_db.read_bytes() == before
    assert report_no_ids(result) is None


def test_missing_store_database_does_not_create_zero_baseline(tmp_path):
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    missing = tmp_path / "missing.sqlite"
    try:
        supervisor.detect_once(missing, state_db, (), BASE)
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("missing input must not be mistaken for a zero cohort")
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT value FROM state WHERE key='baseline'").fetchone()[0] == ""
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_old_empty_qr_baseline_does_not_trigger_an_event(tmp_path):
    source_db = make_store(tmp_path / "store.sqlite")
    state_db = tmp_path / "sidecar.sqlite"
    supervisor.initialize(state_db)
    since = BASE - timedelta(seconds=1)
    old_baseline = supervisor.snapshot(source_db, (), since, BASE)
    del old_baseline["qr_requests_by_current_status"]
    with sqlite3.connect(state_db) as conn:
        conn.execute("UPDATE state SET value=? WHERE key='baseline'", (json.dumps(old_baseline),))
    result = supervisor.detect_once(source_db, state_db, (), since, BASE + timedelta(seconds=5))
    assert result["status"] == "unchanged"
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def store_campaign_report(path):
    return supervisor.store_campaign.report(BASE, 2, BASE + timedelta(seconds=1), path,
                                            source_prefix=CAPCUT_TRIAL_SOURCE,
                                            source_exact=True)
