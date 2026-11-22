"""Runtime regressions use temporary Store/sidecar SQLite and a fake model only."""
import fcntl
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.features.threads.growth import capcut_supervisor as supervisor
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE

BASE = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)
SINCE = BASE - timedelta(seconds=1)


@pytest.mark.parametrize("event_status", ["idle", "error"])
def test_scheduled_strategy_runs_without_business_event_even_after_dispatch_error(tmp_path, monkeypatch, event_status):
    calls = []

    def dispatch(path):
        calls.append(("event", path))
        if event_status == "error":
            raise RuntimeError("dispatch failure")
        return {"status": "idle"}

    def review():
        calls.append(("strategy", None))
        return {"status": "already_attempted"}

    monkeypatch.setattr(supervisor, "dispatch_once", dispatch)
    monkeypatch.setattr(supervisor.strategy_review, "review_due", review)
    path = tmp_path / "sidecar.sqlite"
    result = supervisor._background_work(path)
    assert calls == [("event", path), ("strategy", None)]
    assert result["status"] == ("unavailable" if event_status == "error" else "idle")
    assert result["strategy_review"] == {"status": "already_attempted"}
    assert not path.exists()


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    store = tmp_path / "store.sqlite"
    sidecar = tmp_path / "sidecar.sqlite"
    with sqlite3.connect(store) as conn:
        conn.executescript("""
            CREATE TABLE users(user_id INTEGER PRIMARY KEY, created_at TEXT);
            CREATE TABLE state(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, price INTEGER,
                description TEXT, active INTEGER, upstream_id INTEGER,
                upstream_available INTEGER, upstream_cost INTEGER);
            CREATE TABLE topups(id INTEGER PRIMARY KEY, user_id INTEGER,
                intent_product_id INTEGER, status TEXT, created_at TEXT, resolved_at TEXT);
            CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER,
                product_id INTEGER, total INTEGER, refunded INTEGER, status TEXT,
                created_at TEXT, updated_at TEXT);
            INSERT INTO products VALUES(2,'CapCut',34000,'catalog',1,30,1,31360);
        """)
    supervisor.initialize(sidecar)
    monkeypatch.setattr(supervisor, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(supervisor, "BURST_COALESCE_SECONDS", 10)
    return store, sidecar, tmp_path / "reports"


def user(store, uid=77, source=CAPCUT_TRIAL_SOURCE):
    with sqlite3.connect(store) as conn:
        conn.execute("INSERT INTO users VALUES (?,?)", (uid, BASE.isoformat()))
        conn.execute("INSERT INTO state VALUES (?,?)", (f"src:{uid}", source))


def marker(store, stage, seconds):
    with sqlite3.connect(store) as conn:
        conn.execute("INSERT INTO state VALUES (?,?)",
                     (f"step:{stage}:77", f"2@{(BASE + timedelta(seconds=seconds)).isoformat()}"))


def event(runtime):
    store, sidecar, _ = runtime
    user(store)
    supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=1))
    marker(store, "product", 2)
    return supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=3))


def fake_generator(calls, ok=True):
    def generate(prompt, *, purpose):
        calls.append(json.loads(prompt.rsplit("\n\n", 1)[-1]))
        return ("fake specialist" if ok else None), {"ok": ok, "model": "fake"}
    return generate


def test_dispatch_lock_prevents_second_caller_and_model_calls(runtime):
    _, sidecar, _ = runtime
    event(runtime)
    calls = []
    with sidecar.with_suffix(".dispatch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = supervisor.dispatch_once(sidecar, BASE + timedelta(minutes=2), fake_generator(calls), cooldown=0)
    assert result == {"status": "busy"}
    assert calls == []
    with sqlite3.connect(sidecar) as conn:
        assert conn.execute("SELECT status FROM events").fetchone()[0] == "queued"


def test_exact_source_and_admin_filter_are_applied_before_export(runtime):
    store, _, _ = runtime
    user(store, 77)
    user(store, 88)  # excluded administrator
    user(store, 99, CAPCUT_TRIAL_SOURCE + "_collision")
    snapshot = supervisor.snapshot(store, (88,), SINCE, BASE + timedelta(minutes=1))
    assert snapshot["new_users"] == 1
    assert snapshot["product"]["recorded_catalog_unit_cost"] == 31360
    encoded = json.dumps(snapshot)
    assert '"user_id"' not in encoded and '"username"' not in encoded
    assert "_collision" not in encoded


def test_repeat_qr_and_cancelled_status_are_independent_signals(runtime):
    store, sidecar, _ = runtime
    user(store)
    with sqlite3.connect(store) as conn:
        conn.execute("INSERT INTO topups VALUES(1,77,2,'pending',?,NULL)",
                     ((BASE + timedelta(seconds=1)).isoformat(),))
    supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=2))
    with sqlite3.connect(store) as conn:
        conn.execute("INSERT INTO topups VALUES(2,77,2,'pending',?,NULL)",
                     ((BASE + timedelta(seconds=3)).isoformat(),))
    second = supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=4))
    assert second["changed"] == ["qr_requests_by_current_status"]
    assert second["current"]["qr_customers"] == 1
    assert second["current"]["qr_requests_by_current_status"] == {"pending": 2}
    with sqlite3.connect(store) as conn:
        conn.execute("UPDATE topups SET status='cancelled',resolved_at=? WHERE id=1",
                     ((BASE + timedelta(seconds=5)).isoformat(),))
    cancelled = supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=6))
    assert cancelled["changed"] == ["qr_requests_by_current_status"]
    assert cancelled["current"]["qr_requests_by_current_status"] == {"cancelled": 1, "pending": 1}
    supervisor.advance_without_ai(sidecar)
    with sqlite3.connect(sidecar) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events WHERE status='queued'").fetchone()[0] == 2


def test_once_tick_drains_debounced_queue_without_fresh_change(runtime):
    store, sidecar, reports = runtime
    user(store)
    calls = []
    generate = fake_generator(calls)
    supervisor.tick(store, sidecar, (), SINCE, BASE + timedelta(seconds=1), generate)
    marker(store, "product", 2)
    first = supervisor.tick(store, sidecar, (), SINCE, BASE + timedelta(seconds=3), generate)
    assert first["dispatch"]["status"] == "debouncing" and calls == []
    later = supervisor.tick(store, sidecar, (), SINCE, BASE + timedelta(seconds=14), generate)
    assert later["status"] == "unchanged" and later["dispatch"]["status"] == "done"
    assert len(calls) == 3 and len(list(reports.glob("*.json"))) == 1


def test_provider_false_is_reported_as_fallback_for_every_role(runtime):
    _, sidecar, reports = runtime
    event(runtime)
    calls = []
    result = supervisor.dispatch_once(sidecar, BASE + timedelta(minutes=1), fake_generator(calls, ok=False), cooldown=0)
    assert result["fallback_roles"] == list(supervisor.ROLES)
    assert len(calls) == 3
    output = json.loads(next(reports.glob("*.json")).read_text())
    assert all(role["status"] == "fallback" for role in output["specialists"].values())


def test_running_resume_does_not_mix_saved_role_with_new_queued_event(runtime):
    store, sidecar, reports = runtime
    first = event(runtime)
    saved = {"measurement": {"status": "suggestion", "text": "saved measurement for first event"}}
    with sqlite3.connect(sidecar) as conn:
        conn.execute("UPDATE events SET status='running',specialist_json=? WHERE event_key=?",
                     (json.dumps(saved), first["event_key"]))
    marker(store, "confirm", 4)
    second = supervisor.detect_once(store, sidecar, (), SINCE, BASE + timedelta(seconds=5))
    assert second["status"] == "event"
    calls = []
    first_result = supervisor.dispatch_once(sidecar, BASE + timedelta(seconds=20), fake_generator(calls), cooldown=0)
    assert first_result["coalesced_event_count"] == 1 and len(calls) == 2
    first_output = json.loads(next(reports.glob("*.json")).read_text())
    assert first_output["specialists"]["measurement"] == saved["measurement"]
    assert first_output["current"]["confirm_markers"] == 0
    assert all(call["current"]["confirm_markers"] == 0 for call in calls)
    with sqlite3.connect(sidecar) as conn:
        assert conn.execute("SELECT status,specialist_json FROM events WHERE event_key=?",
                            (second["event_key"],)).fetchone() == ("queued", "{}")
    next_result = supervisor.dispatch_once(sidecar, BASE + timedelta(seconds=21), fake_generator(calls), cooldown=0)
    assert next_result["coalesced_event_count"] == 1 and len(calls) == 5
    assert all(call["current"]["confirm_markers"] == 1 for call in calls[-3:])
    assert len(list(reports.glob("*.json"))) == 2
