"""
Process identification / browser attribution (PLAN-048 hardening).

Covers the two launch spellings (PM2 script path vs `python -m`), browser
ownership evidence, and the "never touch what you cannot attribute" rule.
"""
from __future__ import annotations

import os

import app.config as config
from app.core import process_scan
from app.core.process_scan import (
    ProcInfo,
    ProcessSnapshot,
    cmdline_matches_spec,
    extract_user_data_dir,
    is_absolute_elsewhere,
    is_toolsauto_entrypoint,
    parse_entrypoint,
    path_is_within,
)

PUBLISHER = "app.features.facebook.workers.publisher"
PROFILES = str(config.PROFILES_DIR)


def _proc(pid, cmdline, *, ppid=0, name="python.exe", create_time=1000.0):
    return ProcInfo.build(pid=pid, ppid=ppid, name=name, cmdline=cmdline, create_time=create_time)


def _chrome(pid, ppid, user_data_dir=None, *, name="chrome.exe", create_time=1000.0):
    cmd = ["chrome.exe", "--type=browser"]
    if user_data_dir:
        cmd.append(f"--user-data-dir={user_data_dir}")
    return ProcInfo.build(pid=pid, ppid=ppid, name=name, cmdline=cmd, create_time=create_time)


# ── cmdline matching ──────────────────────────────────────────────────────────


def test_dotted_module_and_script_path_match_same_worker():
    """PM2 runs the script path; the supervisor runs `-m`. Both are the worker."""
    assert cmdline_matches_spec(["python", "-m", PUBLISHER], PUBLISHER)
    assert cmdline_matches_spec(
        ["python", "app/features/facebook/workers/publisher.py"], PUBLISHER
    )
    assert cmdline_matches_spec(
        [r"C:\proj\venv\python.exe", r"app\features\facebook\workers\publisher.py"], PUBLISHER
    )
    assert cmdline_matches_spec(
        ["/srv/toolsauto/venv/bin/python", "/srv/toolsauto/app/features/facebook/workers/publisher.py"],
        PUBLISHER,
    )


def test_unrelated_cmdline_does_not_match():
    assert not cmdline_matches_spec(["python", "-m", "http.server"], PUBLISHER)


def test_command_that_only_mentions_the_worker_is_not_the_worker():
    """
    A grep/compile/editor command carrying the worker path in argv must never be
    mistaken for a running worker — that would stop the supervisor spawning it.
    """
    mentions = [
        ["python", "-m", "compileall", "-q", "app/features/facebook/workers/publisher.py"],
        ["python", "-m", "pytest", "tests/", "app/features/facebook/workers/publisher.py"],
        ["git", "diff", "--", "app/features/facebook/workers/publisher.py"],
        ["python", "-c", "import app.features.facebook.workers.publisher"],
        ["code", "app/features/facebook/workers/publisher.py"],
        ["rg", "publisher", "app/features/facebook/workers/publisher.py"],
    ]
    for cmdline in mentions:
        assert not cmdline_matches_spec(cmdline, PUBLISHER), cmdline
        assert not is_toolsauto_entrypoint(cmdline), cmdline


def test_threads_and_ai_generator_workers_are_known_entrypoints():
    for cmdline in (
        ["python", "app/features/threads/workers/publisher.py"],
        ["python", "-m", "app.features.threads.workers.auto_reply"],
        ["python", "app/features/threads/workers/news_worker.py"],
        ["python", "app/features/viral_intake/workers/ai_generator.py"],
        ["python", "manage.py", "serve", "--no-reload"],
        ["python", "-m", "uvicorn", "app.main:app", "--port", "8002"],
    ):
        assert is_toolsauto_entrypoint(cmdline), cmdline


def test_foreign_process_is_not_a_toolsauto_entrypoint():
    assert not is_toolsauto_entrypoint(["node", "server.js"])
    assert not is_toolsauto_entrypoint([])
    assert not is_toolsauto_entrypoint(["python"])


def test_parse_entrypoint_skips_interpreter_flags():
    entry = parse_entrypoint(["python", "-u", "-X", "utf8", "manage.py", "serve"])
    assert entry.script.endswith("manage.py")
    assert entry.args == ("serve",)


def test_argv0_is_not_trusted_alone():
    """A launcher may rewrite argv[0]; the OS process name is a second signal."""
    renamed = ["FB_Publisher_1", "app/features/facebook/workers/publisher.py"]
    assert not cmdline_matches_spec(renamed, PUBLISHER)
    assert cmdline_matches_spec(renamed, PUBLISHER, exe_name="python.exe")
    assert is_toolsauto_entrypoint(renamed, exe_name="python3.11")
    # An editor is still not the worker, whatever its argv[0] says.
    assert not is_toolsauto_entrypoint(renamed, exe_name="code.exe")


def test_snapshot_uses_process_name_for_matching():
    thin = ProcInfo.build(pid=10, name="python.exe", hydrated=False)

    def loader(info):
        return ProcInfo.build(
            pid=10, ppid=1, name="python.exe",
            cmdline=["FB_Publisher_1", "app/features/facebook/workers/publisher.py"],
        )

    snap = ProcessSnapshot([thin], hydrator=loader)
    assert snap.find_pids(PUBLISHER) == [10]


def test_browser_profile_dir_reads_from_root():
    snap = ProcessSnapshot(
        [
            _chrome(50, 1, f"{PROFILES}/acc_1"),
            ProcInfo.build(pid=51, ppid=50, name="chrome.exe", cmdline=["chrome", "--type=renderer"]),
        ]
    )
    assert snap.browser_profile_dir(snap.get(51)) == f"{PROFILES}/acc_1".replace("\\", "/").lower()


def test_venv_launcher_stub_counts_as_one_instance():
    """
    A PyManager-style venv python.exe re-execs the real interpreter as a child
    with the same cmdline. That is one worker, not two.
    """
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "-m", PUBLISHER], ppid=1, create_time=100.0),
            _proc(11, ["python", "-m", PUBLISHER], ppid=10, create_time=101.0),
        ]
    )
    assert snap.find_pids(PUBLISHER) == [10]


def test_two_independent_workers_are_still_two():
    """Sibling processes (e.g. PM2 FB_Publisher_1 and _2) must both be reported."""
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "-m", PUBLISHER], ppid=1),
            _proc(20, ["python", "app/features/facebook/workers/publisher.py"], ppid=1),
        ]
    )
    assert snap.find_pids(PUBLISHER) == [10, 20]


def test_find_pids_matches_both_spellings():
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "-m", PUBLISHER]),
            _proc(11, ["python", "app/features/facebook/workers/publisher.py"]),
            _proc(12, ["python", "-m", "app.features.system_panel.workers.maintenance"]),
        ]
    )
    assert snap.find_pids(PUBLISHER) == [10, 11]
    assert snap.find_pids(PUBLISHER, exclude={10}) == [11]


# ── paths ─────────────────────────────────────────────────────────────────────


def test_path_is_within_respects_directory_boundary():
    assert path_is_within("C:/proj/storage/profiles/acc1", "C:/proj/storage/profiles")
    assert path_is_within(r"C:\proj\storage\profiles\acc1", "C:/proj/storage/profiles")
    assert not path_is_within("C:/proj/storage/profiles-other/acc1", "C:/proj/storage/profiles")
    assert not path_is_within("", "C:/proj")


def test_extract_user_data_dir_both_forms():
    assert extract_user_data_dir(["chrome", "--user-data-dir=C:/x/y"]) == "C:/x/y"
    assert extract_user_data_dir(["chrome", "--user-data-dir", "C:/x/y"]) == "C:/x/y"
    assert extract_user_data_dir(["chrome", "--headless"]) is None


# ── browser attribution ───────────────────────────────────────────────────────


def test_browser_with_project_profile_is_attributed():
    snap = ProcessSnapshot([_chrome(50, 1, f"{PROFILES}/acc_1")])
    assert snap.browser_attribution(snap.get(50)) == "profile"


def test_browser_with_relative_profile_path_is_attributed(monkeypatch, tmp_path):
    """A relative --user-data-dir must still resolve back to our profile root."""
    profiles = tmp_path / "storage" / "profiles"
    (profiles / "acc_1").mkdir(parents=True)
    monkeypatch.setattr(process_scan, "profile_roots", lambda: (str(profiles).replace("\\", "/").lower(),))
    monkeypatch.chdir(tmp_path)

    snap = ProcessSnapshot(
        [ProcInfo.build(pid=50, ppid=1, name="chrome.exe", cmdline=["chrome", "--user-data-dir=storage/profiles/acc_1"])]
    )
    assert snap.browser_attribution(snap.get(50)) == "profile"


def test_browser_under_live_worker_is_attributed():
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "app/features/facebook/workers/publisher.py"]),
            _chrome(50, 10, "C:/somewhere/else"),
        ]
    )
    assert snap.browser_attribution(snap.get(50)) == "worker"


def test_threads_worker_browser_is_attributed():
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "app/features/threads/workers/publisher.py"]),
            _chrome(50, 10, "C:/tmp/pw-profile"),
        ]
    )
    assert snap.is_toolsauto_browser(snap.get(50))


def test_other_project_playwright_chromium_is_not_attributed():
    """A ms-playwright browser from another project must stay invisible to us."""
    other = ProcInfo.build(
        pid=60,
        ppid=1,
        name="chrome.exe",
        cmdline=[
            "C:/Users/Admin/AppData/Local/ms-playwright/chromium-1084/chrome.exe",
            "--user-data-dir=C:/other-project/storage/profiles/acc",
        ],
    )
    snap = ProcessSnapshot([other])
    assert snap.browser_attribution(snap.get(60)) is None


def test_browser_without_cmdline_is_never_attributed():
    blind = ProcInfo.build(pid=70, ppid=1, name="chrome.exe", cmdline=[])
    snap = ProcessSnapshot([blind])
    assert snap.browser_attribution(snap.get(70)) is None


def test_personal_chrome_is_not_attributed():
    personal = ProcInfo.build(
        pid=80,
        ppid=1,
        name="chrome.exe",
        cmdline=["chrome.exe", "--user-data-dir=C:/Users/Admin/AppData/Local/Google/Chrome/User Data"],
    )
    snap = ProcessSnapshot([personal])
    assert snap.browser_attribution(snap.get(80)) is None


def test_foreign_absolute_path_is_never_resolved_onto_our_cwd():
    """
    Regression: a --user-data-dir that only ANOTHER OS calls absolute must not be
    fed to Path.resolve(), which rebases it onto the current directory.

    On Linux "C:/Users/.../Chrome" is a *relative* path, so resolve() turned it
    into "<project_root>/C:/Users/.../Chrome" -- inside our project root -- and
    a stranger's browser was attributed to ToolsAuto, letting the orphan purge
    kill it. The mirror case is "/home/..." on Windows, which is drive-relative
    there. Both spellings must be rejected wherever they are not native.
    """
    windows_spelling = "C:/Users/Admin/AppData/Local/Google/Chrome/User Data"
    posix_spelling = "/home/someone/.config/chromium"

    if os.name == "nt":
        # Native here: safe to resolve. The foreign one is the POSIX spelling.
        assert not is_absolute_elsewhere(windows_spelling)
        assert is_absolute_elsewhere(posix_spelling)
    else:
        assert is_absolute_elsewhere(windows_spelling)
        assert not is_absolute_elsewhere(posix_spelling)

    # A genuinely relative path stays resolvable on both platforms -- that is the
    # case test_browser_with_relative_profile_path_is_attributed depends on.
    assert not is_absolute_elsewhere("storage/profiles/acc_1")
    assert not is_absolute_elsewhere(None)
    assert not is_absolute_elsewhere("")


def test_browser_root_vs_renderer():
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "-m", PUBLISHER]),
            _chrome(50, 10, f"{PROFILES}/acc_1"),
            _chrome(51, 50, f"{PROFILES}/acc_1"),
        ]
    )
    assert snap.is_browser_root(snap.get(50))
    assert not snap.is_browser_root(snap.get(51))


def test_ancestors_survive_pid_reuse():
    """A recycled PID that started after the child cannot be its parent."""
    snap = ProcessSnapshot(
        [
            _proc(10, ["python", "-m", PUBLISHER], create_time=5000.0),
            _chrome(50, 10, f"{PROFILES}/acc_1", create_time=1000.0),
        ]
    )
    assert snap.ancestor_pids(50) == ()
    # Still attributed through its profile path, just not through the fake parent.
    assert snap.browser_attribution(snap.get(50)) == "profile"


def test_ancestor_walk_stops_on_cycles():
    snap = ProcessSnapshot([_proc(1, ["a"], ppid=2), _proc(2, ["b"], ppid=1)])
    assert set(snap.ancestor_pids(1)) == {2}


def test_hydration_is_lazy_and_selective():
    """
    Reading ppid/cmdline for every process costs seconds on Windows, so only
    browsers and interpreters may be hydrated — never the whole process table.
    """
    thin = [
        ProcInfo.build(pid=1, name="svchost.exe", hydrated=False),
        ProcInfo.build(pid=2, name="explorer.exe", hydrated=False),
        ProcInfo.build(pid=10, name="python.exe", hydrated=False),
        ProcInfo.build(pid=50, name="chrome.exe", hydrated=False),
    ]
    hydrated: list[int] = []

    def loader(info):
        hydrated.append(info.pid)
        if info.pid == 10:
            return ProcInfo.build(pid=10, ppid=1, name="python.exe", cmdline=["python", "-m", PUBLISHER])
        if info.pid == 50:
            return ProcInfo.build(pid=50, ppid=10, name="chrome.exe", cmdline=["chrome", f"--user-data-dir={PROFILES}/a"])
        return None

    snap = ProcessSnapshot(thin, hydrator=loader)
    browsers = list(snap.iter_browsers())
    assert [b.pid for b in browsers] == [50]
    assert snap.browser_attribution(browsers[0]) == "worker"

    # explorer.exe is neither a browser nor an interpreter and is not on any
    # ancestry chain we walk — it must never be touched.
    assert 2 not in hydrated
    assert set(hydrated) <= {1, 10, 50}


def test_hydration_result_is_cached():
    calls: list[int] = []

    def loader(info):
        calls.append(info.pid)
        return ProcInfo.build(pid=info.pid, ppid=1, name=info.name, cmdline=["python", "-m", PUBLISHER])

    snap = ProcessSnapshot([ProcInfo.build(pid=10, name="python.exe", hydrated=False)], hydrator=loader)
    for _ in range(5):
        snap.find_pids(PUBLISHER)
    assert calls == [10]


def test_unreadable_process_is_marked_unknown_not_retried():
    calls: list[int] = []

    def loader(info):
        calls.append(info.pid)
        return None  # access denied

    snap = ProcessSnapshot([ProcInfo.build(pid=50, name="chrome.exe", hydrated=False)], hydrator=loader)
    browser = list(snap.iter_browsers())[0]
    assert snap.browser_attribution(browser) is None
    snap.browser_attribution(browser)
    assert calls == [50]


def test_profile_roots_computed_once_per_snapshot(monkeypatch):
    """Filesystem work must be per-scan, not per-process (was O(procs * stat))."""
    calls = {"n": 0}
    real = process_scan.profile_roots

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(process_scan, "profile_roots", counting)
    snap = ProcessSnapshot([_chrome(pid, 1, f"{PROFILES}/acc") for pid in range(100, 140)])
    for info in snap.all():
        snap.browser_attribution(info)
    assert calls["n"] == 1
