"""The one-post operational trial uses a temporary DB and fake browser/PM2 only."""
import importlib.util
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "reports/zt-blackfriday-20261120/threads_trial.py"
SPEC = importlib.util.spec_from_file_location("bf_threads_trial_runtime", PATH)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)
PERMALINK = "https://www.threads.com/@us28qt/post/trial181"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    link = "https://t.me/+BlackFridayTest"
    body = "Chuẩn bị săn Black Friday 27/11: theo dõi mã và món trong ZT báo mã.\n" + link + "\nCó link tiếp thị liên kết."
    m = {"plan": "PLAN-181", "account": "us28qt", "account_handle": "us28qt",
         "slot": "zt-bf26-threads-p1", "source": "zt_bf26_guide", "prepared_at": now.isoformat(),
         "text": body, "text_sha256": hashlib.sha256(body.encode()).hexdigest(), "invite_url": link,
         "invite_expire_at": "2026-11-30T16:59:59+00:00"}
    channel = {"plan": "PLAN-181", "invite": {"status": "done", "invite_link": link,
               "expire_date": int(trial.stamp(m["invite_expire_at"]).timestamp())},
               "guide": {"status": "done", "message_id": 123, "text": "Guide"},
               "pin": {"status": "verified", "message_id": 123}}
    (tmp_path / "channel-state.json").write_text(json.dumps(channel))
    db = tmp_path / "growth.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""CREATE TABLE growth_posts(account TEXT,status TEXT,posted_at TEXT);
            CREATE TABLE own_posts(id INTEGER PRIMARY KEY,slot TEXT UNIQUE,kind TEXT,ref TEXT,text TEXT,
            status TEXT,created_at TEXT,account TEXT,post_url TEXT,error_message TEXT);""")
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"phase": "waiting", "heartbeat_at": now.isoformat()}))
    monkeypatch.setattr(trial, "AGENT_STATUS", status)
    role = SimpleNamespace(enabled=True, own_posts=True, max_per_hour=3, max_per_day=20, serves=lambda bot: True)
    cfg = SimpleNamespace(enabled=True, quiet_hours="")
    monkeypatch.setattr(trial, "load_account_roles", lambda: {"us28qt": role})
    monkeypatch.setattr(trial, "load_worker_config", lambda: cfg)
    monkeypatch.setattr(trial, "load_limits", lambda: SimpleNamespace(min_delay_sec=180))
    monkeypatch.setattr(trial, "login_active", lambda: True)
    monkeypatch.setattr(trial, "profile_locked", lambda path: False)
    monkeypatch.setattr(trial.time, "sleep", lambda seconds: None)
    state, actions, created, closed = {trial.WORKER: {"status": "online", "pid": 123, "restarts": 0}}, [], [], []

    def action(command):
        actions.append(command)
        state[trial.WORKER]["status"] = "stopped" if command == "stop" else "online"

    monkeypatch.setattr(trial, "pm2_state", lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(trial, "pm2_action", action)
    monkeypatch.setattr(trial, "verify_browser", lambda *args: PERMALINK)

    class Browser:
        handle = "us28qt"
        result = PERMALINK
        error = None

        def __init__(self, path):
            self.adapter = SimpleNamespace(_discover_own_handle=lambda: self.handle)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def create_post(self, text):
            created.append(text)
            proof = json.loads((tmp_path / "trial-publication.json").read_text())
            assert proof["create_post_called"] is True and proof["status"] == "unknown"
            if self.error:
                raise self.error
            return self.result

    return SimpleNamespace(m=m, db=db, folder=tmp_path, now=now, role=role, cfg=cfg, status=status,
                           actions=actions, created=created, closed=closed, browser=Browser)


def test_pm2_snapshot_accepts_stopped_unrelated_entry_without_pid(monkeypatch):
    monkeypatch.setattr(trial.subprocess, "check_output", lambda *_a, **_k: json.dumps([
        {"name": "DB_Backup", "pm2_env": {"status": "stopped", "restart_time": 0}},
        {"name": trial.WORKER, "pid": 123, "pm2_env": {"status": "online", "restart_time": 0}},
    ]))
    snapshot = trial.pm2_state()
    assert snapshot["DB_Backup"]["pid"] is None and snapshot[trial.WORKER]["pid"] == 123


def run(s, mode="publish"):
    return trial.execute(s.m, mode=mode, db_path=s.db, folder=s.folder, browser_factory=s.browser)


def test_default_preflight_has_no_browser_process_or_database_writes(setup):
    s = setup
    before = s.db.read_bytes()
    assert run(s, "preflight")["blocked"] == []
    assert s.db.read_bytes() == before
    assert s.actions == s.created == s.closed == []


def test_single_post_fence_survives_second_invocation(setup):
    s = setup
    result = run(s)
    assert result["status"] == "posted" and result["worker_restored"]
    assert s.actions == ["stop", "start"] and len(s.created) == len(s.closed) == 1
    assert run(s)["status"] == "blocked"
    assert len(s.created) == 1
    with sqlite3.connect(s.db) as conn:
        assert conn.execute("SELECT status,post_url FROM own_posts").fetchall() == [("posted", PERMALINK)]


def test_unknown_requires_readonly_verification_never_second_publish(setup, monkeypatch):
    s = setup
    s.browser.result = None
    monkeypatch.setattr(trial, "verify_browser", lambda *args: None)
    assert run(s)["status"] == "unknown"
    assert run(s)["status"] == "blocked"
    before = s.db.read_bytes()
    assert run(s, "verify")["status"] == "unknown"
    assert s.db.read_bytes() == before
    monkeypatch.setattr(trial, "verify_browser", lambda *args: PERMALINK)
    assert run(s, "verify")["status"] == "posted"
    assert len(s.created) == 1 and s.actions == ["stop", "start"] * 3


def test_verification_rejects_changed_manifest_without_browser_or_row_change(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(trial, "verify_browser", lambda *args: None)
    run(s)
    before = s.db.read_bytes()
    s.m["text"] += " Mới."
    s.m["text_sha256"] = hashlib.sha256(s.m["text"].encode()).hexdigest()
    with pytest.raises(ValueError, match="Manifest changed"):
        run(s, "verify")
    assert s.db.read_bytes() == before and len(s.created) == len(s.closed) == 1


def test_identity_mismatch_is_fenced_and_restores_worker(setup):
    s = setup
    s.browser.handle = "different_account"
    result = run(s)
    assert result["status"] == "not_published" and result["create_post_called"] is False
    assert s.created == [] and s.closed == [True] and s.actions == ["stop", "start"]
    assert run(s)["status"] == "blocked"


def test_quiet_boundary_after_opening_browser_prevents_create_and_restores(setup, monkeypatch):
    s = setup
    checks = iter([False, False, True])
    monkeypatch.setattr(trial, "in_quiet_hours", lambda *args: next(checks))
    result = run(s)
    assert result["status"] == "not_published" and result["create_post_called"] is False
    assert s.created == [] and s.closed == [True] and s.actions == ["stop", "start"]


def test_role_disabled_during_browser_open_prevents_create(setup):
    s = setup
    original = s.browser.__enter__

    def enter(self):
        s.role.enabled = False
        return original(self)

    s.browser.__enter__ = enter
    result = run(s)
    assert result["status"] == "not_published" and s.created == []
    assert s.closed == [True] and s.actions == ["stop", "start"]


def test_keyboard_interrupt_after_attempt_still_closes_and_restores(setup):
    s = setup
    s.browser.error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(s)
    proof = json.loads((s.folder / "trial-publication.json").read_text())
    assert proof["status"] == "unknown" and proof["worker_restored"] is True
    assert s.closed == [True] and s.actions == ["stop", "start"]


@pytest.mark.parametrize("blocked", ["role", "account_active", "profile_unlocked", "worker_idle", "outside_quiet_hours"])
def test_preflight_boundaries_prevent_any_action(setup, monkeypatch, blocked):
    s = setup
    if blocked == "role":
        s.role.enabled = False
    elif blocked == "account_active":
        monkeypatch.setattr(trial, "login_active", lambda: False)
    elif blocked == "profile_unlocked":
        monkeypatch.setattr(trial, "profile_locked", lambda path: True)
    elif blocked == "worker_idle":
        s.status.write_text(json.dumps({"phase": "working", "heartbeat_at": s.now.isoformat()}))
    else:
        monkeypatch.setattr(trial, "in_quiet_hours", lambda *args: True)
    result = run(s)
    assert blocked in result["preflight"]["blocked"]
    assert s.actions == s.created == []


def test_quota_counts_originals_and_replies_together(setup):
    s = setup
    when = (s.now - timedelta(minutes=10)).isoformat()
    with sqlite3.connect(s.db) as conn:
        conn.execute("INSERT INTO growth_posts VALUES('us28qt','posted',?)", (when,))
        conn.executemany("INSERT INTO own_posts(slot,status,created_at,account) VALUES(?,'posted',?,'us28qt')",
                         [("old1", when), ("old2", when)])
    result = run(s)
    assert "hour_budget" in result["preflight"]["blocked"]
    assert result["preflight"]["combined_public_last_hour"] == 3
    assert s.actions == s.created == []


@pytest.mark.parametrize("change", ["link", "hash", "pin", "pin_pending", "invite_mismatch", "expired", "offer", "extra_url"])
def test_manifest_rejects_unverified_or_unsupported_inputs(setup, change):
    s = setup
    if change == "link":
        s.m["invite_url"] = "https://evil.example/item"
    elif change == "hash":
        s.m["text_sha256"] = "0" * 64
    elif change in ("pin", "pin_pending", "invite_mismatch"):
        p = s.folder / "channel-state.json"
        channel = json.loads(p.read_text())
        if change == "pin":
            channel["pin"]["message_id"] = 999
        elif change == "pin_pending":
            channel["pin"]["status"] = "done"
        else:
            channel["invite"]["invite_link"] = "https://t.me/+different"
        p.write_text(json.dumps(channel))
    elif change == "expired":
        s.m["invite_expire_at"] = (s.now - timedelta(hours=1)).isoformat()
    else:
        s.m["text"] += " Giảm 90%." if change == "offer" else " https://other.example/test"
        s.m["text_sha256"] = hashlib.sha256(s.m["text"].encode()).hexdigest()
    with pytest.raises(ValueError):
        run(s)
    assert s.actions == s.created == []
