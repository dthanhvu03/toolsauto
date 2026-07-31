"""
Local process supervisor for Windows/dev (PLAN-048).

Keeps exactly one of: web, maintenance, fb_publisher.
Does not auto-approve DRAFT or start AI/Threads workers.

Process matching goes through app.core.process_scan so that a worker started by
PM2 (`python app/features/facebook/workers/publisher.py`) and one started here
(`python -m app.features.facebook.workers.publisher`) are recognised as the same
app — otherwise the supervisor would spawn a duplicate publisher.

State/lock files are resolved from config.RUNTIME_CONFIG_DIR (absolute), so the
single-instance lock holds no matter which directory the supervisor is run from.
"""
from __future__ import annotations

import errno
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import app.config as config
from app.core.process_scan import ProcessSnapshot, cmdline_matches_spec

logger = logging.getLogger("local_supervisor")

STATE_PATH = Path(config.RUNTIME_CONFIG_DIR) / "local_stack.json"
LOCK_PATH = Path(config.RUNTIME_CONFIG_DIR) / "local_stack.lock"
POLL_SEC = 5.0
RESTART_BACKOFF_SEC = (2.0, 5.0, 15.0, 30.0)
STOP_GRACE_SEC = float(os.getenv("STACK_STOP_GRACE_SEC", "30"))
SUPERVISOR_SPEC: tuple[str, ...] = ("manage.py", "stack")


@dataclass
class AppSpec:
    name: str
    # Either a dotted module (matched as both `-m pkg.mod` and `pkg/mod.py`)
    # or an explicit token group that must all appear in the cmdline.
    match_spec: str | Sequence[str] = ""
    argv: list[str] = field(default_factory=list)
    owned_proc: subprocess.Popen | None = None
    restarts: int = 0
    external_pid: int | None = None
    # True only when the child was spawned into its own Windows process group;
    # CTRL_BREAK_EVENT is meaningless (and dangerous) otherwise.
    own_process_group: bool = False


@dataclass
class StackConfig:
    host: str = "127.0.0.1"
    port: int = 8002
    no_web: bool = False
    reload_web: bool = False


def _python() -> str:
    return sys.executable


def _ensure_state_dir() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _write_state(payload: dict[str, Any]) -> None:
    _ensure_state_dir()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _cmdline_of(pid: int) -> list[str]:
    try:
        import psutil

        return list(psutil.Process(pid).cmdline() or [])
    except Exception:
        return []


def find_matching_pids(
    match_spec: str | Sequence[str],
    *,
    exclude_pids: set[int] | None = None,
    snapshot: ProcessSnapshot | None = None,
) -> list[int]:
    """PIDs running `match_spec`, in either the -m or the script-path spelling."""
    excluded = set(exclude_pids or set())
    excluded.add(os.getpid())
    snap = snapshot or ProcessSnapshot.capture()
    return snap.find_pids(match_spec, exclude=excluded)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil

        return psutil.Process(pid).is_running()
    except Exception:
        return False


def build_apps(cfg: StackConfig) -> list[AppSpec]:
    apps: list[AppSpec] = [
        AppSpec(
            name="maintenance",
            match_spec="app.features.system_panel.workers.maintenance",
            argv=[_python(), "-m", "app.features.system_panel.workers.maintenance"],
        ),
        AppSpec(
            name="fb_publisher",
            match_spec="app.features.facebook.workers.publisher",
            argv=[_python(), "-m", "app.features.facebook.workers.publisher"],
        ),
    ]
    if not cfg.no_web:
        serve_argv = [
            _python(),
            str(Path(config.BASE_DIR) / "manage.py"),
            "serve",
            "--host",
            cfg.host,
            "--port",
            str(cfg.port),
        ]
        if cfg.reload_web:
            serve_argv.append("--reload")
        else:
            serve_argv.append("--no-reload")
        apps.insert(
            0,
            AppSpec(
                name="web",
                match_spec=("manage.py", "serve"),
                argv=serve_argv,
            ),
        )
    return apps


def _own_create_time() -> float:
    try:
        import psutil

        return float(psutil.Process(os.getpid()).create_time())
    except Exception:
        return 0.0


def _lock_payload() -> str:
    return json.dumps(
        {
            "pid": os.getpid(),
            "started_at": int(time.time()),
            # Recorded so a recycled PID can never be mistaken for the holder.
            "create_time": _own_create_time(),
        },
        indent=2,
    )


def _lock_holder_alive() -> int | None:
    """PID of a live supervisor holding the lock, or None when it is stale."""
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        old_pid = int(data.get("pid") or 0)
    except (OSError, ValueError, TypeError):
        return None
    if not old_pid or old_pid == os.getpid():
        return None
    try:
        import psutil
    except ImportError:
        # Without psutil we cannot prove staleness — assume the holder is alive.
        return old_pid
    try:
        proc = psutil.Process(old_pid)
        create_time = float(proc.create_time())
        cmdline = list(proc.cmdline() or [])
    except psutil.Error:
        return None

    recorded = data.get("create_time")
    if recorded:
        # PID reuse: same number, different process → the lock is stale.
        if abs(create_time - float(recorded)) > 1.0:
            logger.warning(
                "[STACK] Lock pid=%s was recycled (create_time differs) — treating as stale",
                old_pid,
            )
            return None
    is_stack = cmdline_matches_spec(cmdline, SUPERVISOR_SPEC) or cmdline_matches_spec(
        cmdline, "app.platform.local_supervisor"
    )
    return old_pid if is_stack else None


def _acquire_lock() -> bool:
    """
    Atomically claim the single-instance lock.

    O_CREAT|O_EXCL means two supervisors racing from different directories cannot
    both win; a lock left behind by a dead supervisor is recovered once.
    """
    _ensure_state_dir()
    for attempt in range(2):
        try:
            fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _lock_holder_alive()
            if holder:
                logger.error(
                    "[STACK] Another supervisor already running (pid=%s). Exit.", holder
                )
                return False
            if attempt == 0:
                logger.warning("[STACK] Removing stale lock at %s", LOCK_PATH)
                try:
                    LOCK_PATH.unlink(missing_ok=True)
                except OSError as e:
                    logger.error("[STACK] Cannot remove stale lock: %s", e)
                    return False
                continue
            logger.error("[STACK] Lock contention at %s. Exit.", LOCK_PATH)
            return False
        except OSError as e:  # pragma: no cover - unwritable runtime dir
            if e.errno == errno.EACCES:
                logger.error("[STACK] Cannot write lock %s: %s", LOCK_PATH, e)
                return False
            raise
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(_lock_payload())
            return True
    return False


def _release_lock() -> None:
    try:
        if LOCK_PATH.exists():
            data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                LOCK_PATH.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        pass


def _spawn(app: AppSpec) -> None:
    env = {**os.environ, "PYTHONPATH": str(config.BASE_DIR), "PYTHONUNBUFFERED": "1"}
    kwargs: dict[str, Any] = {}
    new_group = False
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        # Own process group so we can send CTRL_BREAK for a graceful shutdown
        # instead of TerminateProcess killing a publish mid-upload.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        new_group = True
    logger.info("[STACK] Starting %s: %s", app.name, " ".join(app.argv))
    app.owned_proc = subprocess.Popen(
        app.argv,
        cwd=str(config.BASE_DIR),
        env=env,
        stdout=None,
        stderr=None,
        **kwargs,
    )
    app.own_process_group = new_group
    app.external_pid = None


def _ensure_app(app: AppSpec, self_pids: set[int], snapshot: ProcessSnapshot) -> str:
    """Ensure one healthy instance. Returns status label."""
    if app.owned_proc is not None:
        code = app.owned_proc.poll()
        if code is None:
            return "ok"
        logger.warning("[STACK] %s exited code=%s — restarting", app.name, code)
        app.owned_proc = None
        backoff = RESTART_BACKOFF_SEC[min(app.restarts, len(RESTART_BACKOFF_SEC) - 1)]
        app.restarts += 1
        time.sleep(backoff)
        _spawn(app)
        return "restarted"

    # External instance already running (PM2, another shell, previous run)?
    matches = find_matching_pids(app.match_spec, exclude_pids=self_pids, snapshot=snapshot)
    if matches:
        app.external_pid = matches[0]
        if len(matches) > 1:
            logger.warning(
                "[STACK] %s has %d matching processes (pids=%s); using first, not spawning",
                app.name,
                len(matches),
                matches,
            )
        return "external"

    if app.external_pid and _pid_alive(app.external_pid):
        return "external"

    app.external_pid = None
    _spawn(app)
    return "started"


def _chrome_ta_count() -> int | None:
    """ToolsAuto browser instances (cached by the monitor — the loop polls every 5s)."""
    try:
        from app.core.observability.system_monitor import count_chrome_processes

        _total, instances, _attributed = count_chrome_processes()
        return instances
    except Exception:
        return None


def _signal_owned(app: AppSpec) -> None:
    """Ask a child to shut down gracefully (CTRL_BREAK on Windows, SIGTERM elsewhere)."""
    proc = app.owned_proc
    if proc is None:
        return
    try:
        if os.name == "nt":
            if app.own_process_group and hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                # No dedicated group: CTRL_BREAK would hit our own console.
                proc.terminate()
        else:
            proc.terminate()
    except (OSError, ValueError) as e:
        logger.debug("[STACK] graceful signal to %s failed: %s", app.name, e)


def _stop_owned(apps: list[AppSpec]) -> None:
    """Signal every owned child, then wait once — parallel, not one-by-one."""
    live = [a for a in apps if a.owned_proc is not None and a.owned_proc.poll() is None]
    for app in live:
        logger.info("[STACK] Stopping %s (pid=%s)", app.name, app.owned_proc.pid)
        _signal_owned(app)

    deadline = time.monotonic() + STOP_GRACE_SEC
    for app in live:
        proc = app.owned_proc
        if proc is None:
            continue
        remaining = max(1.0, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            logger.warning("[STACK] %s did not exit in time — killing", app.name)
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception as e:
                logger.warning("[STACK] kill %s failed: %s", app.name, e)
        except Exception as e:
            logger.warning("[STACK] stop %s failed: %s", app.name, e)
        app.owned_proc = None


def _install_stop_handlers(handler) -> None:
    signal.signal(signal.SIGINT, handler)
    for name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, handler)


def supervisor_tick(apps: list[AppSpec], cfg: StackConfig) -> dict[str, Any]:
    """One supervision pass: ensure every app, then build the state payload."""
    self_pids = {os.getpid()}
    for app in apps:
        if app.owned_proc and app.owned_proc.pid:
            self_pids.add(app.owned_proc.pid)

    # One process-table scan per tick, shared by every check below.
    snapshot = ProcessSnapshot.capture()
    statuses = {app.name: _ensure_app(app, self_pids, snapshot) for app in apps}

    pids = {
        app.name: (
            app.owned_proc.pid
            if app.owned_proc and app.owned_proc.poll() is None
            else app.external_pid
        )
        for app in apps
    }
    return {
        "supervisor_pid": os.getpid(),
        "updated_at": int(time.time()),
        "statuses": statuses,
        "pids": pids,
        "chrome_toolsauto_count": _chrome_ta_count(),
        "config": {"host": cfg.host, "port": cfg.port, "no_web": cfg.no_web},
    }


def run_stack(cfg: StackConfig | None = None) -> int:
    """Blocking supervisor loop. Returns exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    cfg = cfg or StackConfig(port=int(getattr(config, "WEB_PORT", 8002) or 8002))
    if not _acquire_lock():
        return 1

    apps = build_apps(cfg)
    running = True

    def _handle_stop(signum, frame):  # noqa: ARG001
        nonlocal running
        logger.warning("[STACK] Signal %s — shutting down children", signum)
        running = False

    _install_stop_handlers(_handle_stop)
    logger.info(
        "[STACK] Supervisor started (web=%s port=%s, state=%s). Ctrl+C to stop owned children.",
        not cfg.no_web,
        cfg.port,
        STATE_PATH,
    )

    try:
        while running:
            state = supervisor_tick(apps, cfg)
            _write_state(state)
            logger.info(
                "[STACK] ensure %s chrome_ta=%s",
                " ".join(f"{k}={v}" for k, v in state["statuses"].items()),
                state["chrome_toolsauto_count"],
            )
            # Sleep in slices so Ctrl+C is responsive
            for _ in range(int(POLL_SEC * 2)):
                if not running:
                    break
                time.sleep(0.5)
    finally:
        _stop_owned(apps)
        _release_lock()
        logger.info("[STACK] Supervisor stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_stack())
