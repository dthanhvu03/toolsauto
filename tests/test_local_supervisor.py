"""
Local supervisor: single instance regardless of cwd, no duplicate workers
(PLAN-048 hardening).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import app.config as config
from app.core.process_scan import ProcInfo, ProcessSnapshot
from app.platform import local_supervisor as ls


def _proc(pid, cmdline, name="python.exe"):
    return ProcInfo.build(pid=pid, ppid=1, name=name, cmdline=cmdline, create_time=1000.0)


# ── runtime paths ─────────────────────────────────────────────────────────────


def test_state_and_lock_live_in_runtime_config_dir():
    runtime = Path(config.RUNTIME_CONFIG_DIR).resolve()
    assert ls.STATE_PATH.resolve().parent == runtime
    assert ls.LOCK_PATH.resolve().parent == runtime


def test_state_and_lock_paths_are_absolute_and_cwd_independent(tmp_path, monkeypatch):
    before = (ls.STATE_PATH, ls.LOCK_PATH)
    assert before[0].is_absolute() and before[1].is_absolute()
    monkeypatch.chdir(tmp_path)
    # Absolute paths cannot be re-anchored by a different working directory.
    assert (ls.STATE_PATH, ls.LOCK_PATH) == before
    assert not (tmp_path / "storage").exists()


# ── single instance ───────────────────────────────────────────────────────────


@pytest.fixture()
def temp_lock(tmp_path, monkeypatch):
    lock = tmp_path / "config" / "local_stack.lock"
    monkeypatch.setattr(ls, "LOCK_PATH", lock)
    monkeypatch.setattr(ls, "STATE_PATH", tmp_path / "config" / "local_stack.json")
    return lock


def test_second_supervisor_from_another_cwd_cannot_acquire_lock(temp_lock, tmp_path, monkeypatch):
    assert ls._acquire_lock() is True
    assert json.loads(temp_lock.read_text(encoding="utf-8"))["pid"] == os.getpid()

    # Second instance: different cwd, same absolute lock, holder still alive.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ls, "_lock_holder_alive", lambda: 424242)
    assert ls._acquire_lock() is False


def test_stale_lock_is_recovered(temp_lock, monkeypatch):
    temp_lock.parent.mkdir(parents=True, exist_ok=True)
    temp_lock.write_text(json.dumps({"pid": 999999, "started_at": 1}), encoding="utf-8")
    monkeypatch.setattr(ls, "_lock_holder_alive", lambda: None)

    assert ls._acquire_lock() is True
    assert json.loads(temp_lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_recycled_pid_does_not_keep_the_lock(temp_lock, monkeypatch):
    """A dead supervisor's PID reused by another process must read as stale."""
    temp_lock.parent.mkdir(parents=True, exist_ok=True)
    temp_lock.write_text(
        json.dumps({"pid": os.getpid(), "started_at": 1, "create_time": 1.0}),
        encoding="utf-8",
    )

    class _Proc:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 999999.0  # started long after the lock was written

        def cmdline(self):
            return ["python", "manage.py", "stack"]

    monkeypatch.setattr(ls, "_lock_holder_alive", ls._lock_holder_alive)
    fake_psutil = type("psutil", (), {"Process": _Proc, "Error": Exception})
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    # Lock claims our own pid, so force a different one for the check.
    monkeypatch.setattr(os, "getpid", lambda: 12345)

    assert ls._lock_holder_alive() is None


def test_live_supervisor_with_matching_create_time_holds_the_lock(temp_lock, monkeypatch):
    temp_lock.parent.mkdir(parents=True, exist_ok=True)
    temp_lock.write_text(
        json.dumps({"pid": 4242, "started_at": 1, "create_time": 500.0}), encoding="utf-8"
    )

    class _Proc:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 500.0

        def cmdline(self):
            return ["python", "manage.py", "stack", "--host", "127.0.0.1"]

    fake_psutil = type("psutil", (), {"Process": _Proc, "Error": Exception})
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    assert ls._lock_holder_alive() == 4242


def test_lock_payload_records_create_time(temp_lock):
    assert ls._acquire_lock() is True
    data = json.loads(temp_lock.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["create_time"] > 0
    ls._release_lock()


@pytest.mark.skipif(
    not hasattr(__import__("signal"), "CTRL_BREAK_EVENT"),
    reason="CTRL_BREAK_EVENT is Windows-only; POSIX always uses SIGTERM",
)
def test_ctrl_break_only_when_process_group_was_created(monkeypatch):
    """CTRL_BREAK without a dedicated group would hit the supervisor's own console."""
    sent = []

    class _Proc:
        pid = 1
        def poll(self):
            return None
        def send_signal(self, sig):
            sent.append(("signal", sig))
        def terminate(self):
            sent.append(("terminate", None))

    monkeypatch.setattr(os, "name", "nt")

    grouped = ls.AppSpec(name="w", owned_proc=_Proc(), own_process_group=True)
    ls._signal_owned(grouped)
    assert sent[-1][0] == "signal"

    ungrouped = ls.AppSpec(name="w", owned_proc=_Proc(), own_process_group=False)
    ls._signal_owned(ungrouped)
    assert sent[-1] == ("terminate", None)


def test_release_lock_only_removes_own_lock(temp_lock):
    assert ls._acquire_lock() is True
    ls._release_lock()
    assert not temp_lock.exists()

    temp_lock.write_text(json.dumps({"pid": 999999}), encoding="utf-8")
    ls._release_lock()
    assert temp_lock.exists()


# ── duplicate worker detection ────────────────────────────────────────────────


def test_running_pm2_publisher_is_detected_not_respawned(monkeypatch):
    snapshot = ProcessSnapshot(
        [_proc(10, ["python", "app/features/facebook/workers/publisher.py"])]
    )
    spawned: list[str] = []
    monkeypatch.setattr(ls, "_spawn", lambda app: spawned.append(app.name))

    app = ls.AppSpec(
        name="fb_publisher",
        match_spec="app.features.facebook.workers.publisher",
        argv=["python", "-m", "app.features.facebook.workers.publisher"],
    )
    status = ls._ensure_app(app, set(), snapshot)

    assert status == "external"
    assert app.external_pid == 10
    assert spawned == []


def test_running_web_is_detected_not_respawned(monkeypatch):
    snapshot = ProcessSnapshot([_proc(20, ["python", "manage.py", "serve", "--no-reload"])])
    spawned: list[str] = []
    monkeypatch.setattr(ls, "_spawn", lambda app: spawned.append(app.name))

    app = ls.AppSpec(name="web", match_spec=("manage.py", "serve"), argv=["python", "manage.py", "serve"])
    assert ls._ensure_app(app, set(), snapshot) == "external"
    assert spawned == []


def test_missing_worker_is_spawned(monkeypatch):
    snapshot = ProcessSnapshot([_proc(30, ["python", "-m", "http.server"])])
    spawned: list[str] = []
    monkeypatch.setattr(ls, "_spawn", lambda app: spawned.append(app.name))

    app = ls.AppSpec(
        name="fb_publisher",
        match_spec="app.features.facebook.workers.publisher",
        argv=["python", "-m", "app.features.facebook.workers.publisher"],
    )
    assert ls._ensure_app(app, set(), snapshot) == "started"
    assert spawned == ["fb_publisher"]


def test_supervisor_itself_is_not_mistaken_for_the_web_app():
    """`manage.py stack` must not satisfy the `manage.py serve` match."""
    snapshot = ProcessSnapshot([_proc(40, ["python", "manage.py", "stack"])])
    assert snapshot.find_pids(("manage.py", "serve")) == []


def test_build_apps_uses_module_specs():
    apps = {a.name: a for a in ls.build_apps(ls.StackConfig(port=8002))}
    assert apps["fb_publisher"].match_spec == "app.features.facebook.workers.publisher"
    assert apps["maintenance"].match_spec == "app.features.system_panel.workers.maintenance"
    assert tuple(apps["web"].match_spec) == ("manage.py", "serve")
