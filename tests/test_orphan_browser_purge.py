"""
Orphan ToolsAuto browser purge must never touch a live worker's browser, another
project's Chromium, or a process it cannot attribute (PLAN-048 hardening).
"""
from __future__ import annotations

import app.config as config
from app.core.observability.system_monitor import (
    ORPHAN_MIN_AGE_SEC,
    SystemMonitorService,
    count_chrome_processes,
)
from app.core.process_scan import ProcInfo, ProcessSnapshot

PROFILES = str(config.PROFILES_DIR)
NOW = 10_000.0
OLD = NOW - ORPHAN_MIN_AGE_SEC - 60


def _worker(pid, cmdline, ppid=0):
    return ProcInfo.build(pid=pid, ppid=ppid, name="python.exe", cmdline=cmdline, create_time=OLD)


def _chrome(pid, ppid, user_data_dir=None, create_time=OLD, name="chrome.exe"):
    cmd = ["chrome.exe"]
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")
    return ProcInfo.build(pid=pid, ppid=ppid, name=name, cmdline=cmd, create_time=create_time)


def _orphans(procs):
    snap = ProcessSnapshot(procs)
    return {p.pid for p in SystemMonitorService().find_orphan_toolsauto_browsers(snap, now=NOW)}


def test_live_publisher_browser_is_protected():
    """PM2 spells the worker as a script path — it must still be recognised."""
    procs = [
        _worker(10, ["python", "app/features/facebook/workers/publisher.py"]),
        _chrome(50, 10, f"{PROFILES}/acc_1"),
    ]
    assert _orphans(procs) == set()


def test_live_publisher_started_with_dash_m_is_protected():
    procs = [
        _worker(10, ["python", "-m", "app.features.facebook.workers.publisher"]),
        _chrome(50, 10, f"{PROFILES}/acc_1"),
    ]
    assert _orphans(procs) == set()


def test_threads_and_ai_generator_browsers_are_protected():
    procs = [
        _worker(10, ["python", "app/features/threads/workers/publisher.py"]),
        _chrome(50, 10, f"{PROFILES}/threads_1"),
        _worker(20, ["python", "app/features/viral_intake/workers/ai_generator.py"]),
        _chrome(60, 20, f"{PROFILES}/ai_1"),
    ]
    assert _orphans(procs) == set()


def test_web_login_browser_is_protected():
    procs = [
        _worker(10, ["python", "manage.py", "serve", "--no-reload"]),
        _worker(11, ["python", "-c", "from multiprocessing.spawn import spawn_main"], ppid=10),
        _chrome(50, 11, f"{PROFILES}/acc_login"),
    ]
    assert _orphans(procs) == set()


def test_true_orphan_is_reported():
    procs = [_chrome(50, 1, f"{PROFILES}/acc_1")]
    assert _orphans(procs) == {50}


def test_other_project_chromium_is_left_alone():
    procs = [
        ProcInfo.build(
            pid=60,
            ppid=1,
            name="chrome.exe",
            cmdline=[
                "C:/Users/Admin/AppData/Local/ms-playwright/chromium-1084/chrome.exe",
                "--user-data-dir=C:/other-project/storage/profiles/acc",
            ],
            create_time=OLD,
        )
    ]
    assert _orphans(procs) == set()


def test_unknown_browser_process_is_left_alone():
    procs = [ProcInfo.build(pid=70, ppid=1, name="chrome.exe", cmdline=[], create_time=OLD)]
    assert _orphans(procs) == set()


def test_personal_chrome_is_left_alone():
    procs = [
        ProcInfo.build(
            pid=80,
            ppid=1,
            name="chrome.exe",
            cmdline=["chrome.exe", "--user-data-dir=C:/Users/Admin/AppData/Local/Google/Chrome/User Data"],
            create_time=OLD,
        )
    ]
    assert _orphans(procs) == set()


def test_freshly_started_browser_is_left_alone():
    procs = [_chrome(50, 1, f"{PROFILES}/acc_1", create_time=NOW - 1)]
    assert _orphans(procs) == set()


def test_browser_tree_shared_by_two_live_workers_is_protected():
    """
    If a root browser is reachable from any live ToolsAuto worker, no part of
    that tree may be purged — killing the root would take the other job with it.
    """
    procs = [
        _worker(10, ["python", "app/features/facebook/workers/publisher.py"]),
        _worker(11, ["python", "-m", "app.features.threads.workers.publisher"], ppid=10),
        _chrome(50, 11, f"{PROFILES}/acc_shared"),
        _chrome(51, 50, f"{PROFILES}/acc_shared"),
    ]
    assert _orphans(procs) == set()


def test_only_root_browser_is_killed_not_renderers():
    procs = [
        _chrome(50, 1, f"{PROFILES}/acc_1"),
        _chrome(51, 50, f"{PROFILES}/acc_1"),
        _chrome(52, 50, f"{PROFILES}/acc_1"),
    ]
    assert _orphans(procs) == {50}


class _FakeAccount:
    def __init__(self, profile_path):
        self.profile_path = profile_path
        self.resolved_profile_path = profile_path


class _FakeQuery:
    def __init__(self, rows, raises=False):
        self._rows = rows
        self._raises = raises

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def distinct(self):
        return self

    def all(self):
        if self._raises:
            raise RuntimeError("db down")
        return self._rows


class _FakeDB:
    def __init__(self, rows, raises=False):
        self._q = _FakeQuery(rows, raises)

    def query(self, *a, **k):
        return self._q


def test_browser_of_running_job_is_never_killed_even_without_ancestry():
    """
    Ancestry can break while a job is in flight (node driver dies, browser gets
    re-parented). A RUNNING job on that profile is authoritative: hands off.
    """
    procs = [_chrome(50, 1, f"{PROFILES}/acc_1")]
    snap = ProcessSnapshot(procs)
    db = _FakeDB([_FakeAccount(f"{PROFILES}/acc_1")])

    without_db = SystemMonitorService().find_orphan_toolsauto_browsers(snap, now=NOW)
    with_db = SystemMonitorService().find_orphan_toolsauto_browsers(snap, now=NOW, db=db)

    assert {p.pid for p in without_db} == {50}
    assert with_db == []


def test_other_profiles_still_purged_while_a_job_runs():
    procs = [
        _chrome(50, 1, f"{PROFILES}/acc_1"),   # busy account
        _chrome(60, 1, f"{PROFILES}/acc_2"),   # genuinely orphaned
    ]
    db = _FakeDB([_FakeAccount(f"{PROFILES}/acc_1")])
    found = SystemMonitorService().find_orphan_toolsauto_browsers(
        ProcessSnapshot(procs), now=NOW, db=db
    )
    assert {p.pid for p in found} == {60}


def test_db_failure_disables_the_purge_instead_of_guessing():
    procs = [_chrome(50, 1, f"{PROFILES}/acc_1")]
    db = _FakeDB([], raises=True)
    assert SystemMonitorService().find_orphan_toolsauto_browsers(
        ProcessSnapshot(procs), now=NOW, db=db
    ) == []


def test_counts_expose_named_fields_and_stay_tuple_compatible():
    procs = [
        _worker(10, ["python", "-m", "app.features.facebook.workers.publisher"]),
        _chrome(50, 10, f"{PROFILES}/acc_1"),
        _chrome(51, 50, f"{PROFILES}/acc_1"),
    ]
    counts = count_chrome_processes(ProcessSnapshot(procs))
    total, instances, attributed = counts  # old unpacking still works
    assert (total, instances, attributed) == (2, 1, 2)
    assert counts.total_processes == 2
    assert counts.toolsauto_instances == 1
    assert counts.toolsauto_processes == 2


def test_counts_are_cached_between_polls(monkeypatch):
    """Claim gate + supervisor poll continuously; the scan must not run per call."""
    from app.core.observability import system_monitor

    system_monitor.reset_chrome_count_cache()
    captures = {"n": 0}

    def fake_capture():
        captures["n"] += 1
        return ProcessSnapshot([_chrome(50, 1, f"{PROFILES}/acc_1")])

    monkeypatch.setattr(ProcessSnapshot, "capture", staticmethod(fake_capture))
    first = count_chrome_processes()
    for _ in range(5):
        assert count_chrome_processes() == first
    assert captures["n"] == 1

    system_monitor.reset_chrome_count_cache()
    count_chrome_processes()
    assert captures["n"] == 2


def test_explicit_snapshot_bypasses_cache(monkeypatch):
    from app.core.observability import system_monitor

    system_monitor.reset_chrome_count_cache()
    count_chrome_processes(ProcessSnapshot([_chrome(50, 1, f"{PROFILES}/acc_1")]))
    assert system_monitor._chrome_counts_cache is None


def test_counts_separate_instances_from_helper_processes():
    procs = [
        _worker(10, ["python", "-m", "app.features.facebook.workers.publisher"]),
        _chrome(50, 10, f"{PROFILES}/acc_1"),
        _chrome(51, 50, f"{PROFILES}/acc_1"),
        # Someone else's browser: counted in the machine total only.
        ProcInfo.build(
            pid=80,
            ppid=1,
            name="chrome.exe",
            cmdline=["chrome.exe", "--user-data-dir=C:/Users/Admin/personal"],
            create_time=OLD,
        ),
    ]
    total, instances, attributed = count_chrome_processes(ProcessSnapshot(procs))
    assert total == 3
    assert instances == 1
    assert attributed == 2
