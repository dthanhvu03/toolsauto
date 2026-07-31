"""
Process identification shared by the local supervisor and the system monitor (PLAN-048).

Why a shared module: a ToolsAuto worker can be launched two different ways —

    PM2 / start.sh    → python app/features/facebook/workers/publisher.py
    local supervisor  → python -m app.features.facebook.workers.publisher

so every match must accept both the script-path and the dotted-module spelling.
Matching only one of them made the supervisor spawn duplicates and made the
orphan purge treat live worker browsers as orphans.

Attribution rules for browsers (deliberately conservative):
  * a browser belongs to ToolsAuto only when its --user-data-dir lives under a
    canonical profile root / the project root, or when one of its ancestors is a
    known ToolsAuto process;
  * a process we cannot read (no cmdline, access denied) is NEVER attributed —
    unknown ownership means hands off.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import app.config as config

# Every long-running python entrypoint of the project. Used both to protect
# browsers owned by these processes and to detect "already running" instances.
WORKER_MODULES: tuple[str, ...] = (
    "app.features.facebook.workers.publisher",
    "app.features.system_panel.workers.maintenance",
    "app.features.system_panel.workers.ai_reporter",
    "app.features.threads.workers.publisher",
    "app.features.threads.workers.auto_reply",
    "app.features.threads.workers.news_worker",
    "app.features.threads.workers.verifier",
    "app.features.viral_intake.workers.ai_generator",
    "app.platform.local_supervisor",
)

# Token groups (all tokens must be present in the cmdline) for entrypoints that
# are not plain modules: the web server and the supervisor CLI.
ENTRYPOINT_TOKEN_GROUPS: tuple[tuple[str, ...], ...] = (
    ("manage.py", "serve"),
    ("manage.py", "stack"),
    ("uvicorn", "app.main"),
)

BROWSER_NAME_HINTS: tuple[str, ...] = ("chrome", "chromium", "msedge", "playwright")

# Only these executables can be a ToolsAuto entrypoint, so only these are worth
# reading a cmdline for. Reading ppid/cmdline for every process on Windows costs
# seconds (measured: ~8s for 500 processes) — far too slow for the supervisor
# loop and the publisher claim gate, which both scan continuously.
INTERPRETER_NAME_HINTS: tuple[str, ...] = ("python", "pythonw", "py.exe", "pypy", "uvicorn", "node")

_USER_DATA_DIR_FLAG = "--user-data-dir"


# ── text / path helpers ───────────────────────────────────────────────────────


def normalize_path_text(text: str | os.PathLike[str] | None) -> str:
    """Lower-cased, forward-slash form so Windows and POSIX spellings compare equal."""
    if not text:
        return ""
    return str(text).replace("\\", "/").strip().lower()


def cmdline_blob(cmdline: Sequence[str] | None) -> str:
    """Single normalized string for substring matching (empty when unreadable)."""
    if not cmdline:
        return ""
    return normalize_path_text(" ".join(str(part) for part in cmdline))


def module_cmdline_variants(module: str) -> tuple[str, str]:
    """('app.features.x.worker', 'app/features/x/worker.py') — both launch spellings."""
    dotted = module.strip().lower()
    script = dotted.replace(".", "/") + ".py"
    return dotted, script


def cmdline_matches_module(blob: str, module: str) -> bool:
    """True when a normalized cmdline runs `module`, as -m or as a script path."""
    if not blob:
        return False
    return any(variant in blob for variant in module_cmdline_variants(module))


def cmdline_matches_tokens(blob: str, tokens: Iterable[str]) -> bool:
    """True when every token appears in the normalized cmdline."""
    if not blob:
        return False
    token_list = [normalize_path_text(t) for t in tokens]
    if not token_list:
        return False
    return all(t in blob for t in token_list)


@dataclass(frozen=True)
class Entrypoint:
    """
    What a command line actually *runs* — as opposed to what it merely mentions.

    `git diff app/features/facebook/workers/publisher.py` and
    `python -m compileall app/features/.../publisher.py` both contain the worker
    path; neither is the worker. Substring matching treated them as a running
    publisher, which made the supervisor skip spawning the real one.
    """

    module: str = ""   # from `-m <module>`
    script: str = ""   # first positional argument, normalized
    args: tuple[str, ...] = ()

    def head_matches(self, head: str) -> bool:
        head_n = normalize_path_text(head)
        if not head_n:
            return False
        if self.script and (self.script == head_n or self.script.endswith("/" + head_n)):
            return True
        if self.module and (self.module == head_n or self.module.rsplit(".", 1)[-1] == head_n):
            return True
        return False

    def has_arg(self, token: str) -> bool:
        token_n = normalize_path_text(token)
        return any(token_n in arg for arg in self.args)

    def runs_module(self, module: str) -> bool:
        dotted, script = module_cmdline_variants(module)
        if self.module == dotted:
            return True
        return bool(self.script) and (self.script == script or self.script.endswith("/" + script))


# Interpreter flags that consume the following argument.
_FLAGS_WITH_VALUE = ("-x", "-w", "--check-hash-based-pycs")


def parse_entrypoint(cmdline: Sequence[str] | None, exe_name: str | None = None) -> Entrypoint:
    """
    Extract the module / script a command line executes.

    Returns an empty Entrypoint when neither argv[0] nor the OS-reported
    executable name is an interpreter: `code app/.../publisher.py` opens the
    worker in an editor, it does not run it. argv[0] alone is not trusted —
    a launcher can rewrite it — so the real process name counts too.
    """
    parts = [str(p) for p in (cmdline or ())]
    if len(parts) < 2:
        return Entrypoint()
    executable = normalize_path_text(parts[0]).rsplit("/", 1)[-1]
    if not is_interpreter_name(executable) and not is_interpreter_name(exe_name):
        return Entrypoint()

    rest = parts[1:]
    index = 0
    while index < len(rest):
        token = rest[index].strip()
        low = token.lower()
        if low in ("-m", "--module"):
            if index + 1 >= len(rest):
                return Entrypoint()
            return Entrypoint(
                module=normalize_path_text(rest[index + 1]),
                args=tuple(normalize_path_text(a) for a in rest[index + 2:]),
            )
        if low in ("-c", "--command"):
            # An inline program is never one of our entrypoints.
            return Entrypoint()
        if low in _FLAGS_WITH_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return Entrypoint(
            script=normalize_path_text(token),
            args=tuple(normalize_path_text(a) for a in rest[index + 1:]),
        )
    return Entrypoint()


def entrypoint_matches_spec(entry: Entrypoint, spec: str | Sequence[str]) -> bool:
    """
    True when the parsed entrypoint runs `spec`.

    A string spec is a dotted module (matched as `-m pkg.mod` or `pkg/mod.py`);
    a sequence is (head, *required args), e.g. ("manage.py", "serve").
    """
    if isinstance(spec, str):
        return entry.runs_module(spec)
    tokens = [t for t in spec if t]
    if not tokens:
        return False
    if not entry.head_matches(tokens[0]):
        return False
    return all(entry.has_arg(t) for t in tokens[1:])


def cmdline_matches_spec(
    cmdline: Sequence[str] | None, spec: str | Sequence[str], exe_name: str | None = None
) -> bool:
    """True when the command line runs `spec`."""
    return entrypoint_matches_spec(parse_entrypoint(cmdline, exe_name), spec)


def is_toolsauto_entrypoint(cmdline: Sequence[str] | None, exe_name: str | None = None) -> bool:
    """True when the command line runs one of the project's own long-running entrypoints."""
    entry = parse_entrypoint(cmdline, exe_name)
    if not entry.module and not entry.script:
        return False
    if any(entry.runs_module(mod) for mod in WORKER_MODULES):
        return True
    return any(entrypoint_matches_spec(entry, group) for group in ENTRYPOINT_TOKEN_GROUPS)


def project_root() -> str:
    """Canonical, normalized project root."""
    try:
        return normalize_path_text(Path(config.BASE_DIR).resolve())
    except OSError:
        return normalize_path_text(config.BASE_DIR)


def profile_roots() -> tuple[str, ...]:
    """
    Canonical browser-profile roots, normalized and de-duplicated.

    Touches the filesystem (resolve) — callers must compute this once per scan,
    never once per process (see ProcessSnapshot).
    """
    candidates = [
        getattr(config, "PROFILES_DIR", None),
        getattr(config, "STORAGE_PROFILES_DIR", None),
        getattr(config, "LEGACY_PROFILES_DIR", None),
    ]
    roots: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        try:
            resolved = Path(str(candidate)).resolve()
        except OSError:
            resolved = Path(str(candidate))
        normalized = normalize_path_text(resolved)
        if normalized and normalized not in roots:
            roots.append(normalized)
    return tuple(roots)


def path_is_within(child: str | os.PathLike[str] | None, parent: str) -> bool:
    """Prefix check on normalized paths, respecting directory boundaries."""
    child_n = normalize_path_text(child).rstrip("/")
    parent_n = normalize_path_text(parent).rstrip("/")
    if not child_n or not parent_n:
        return False
    return child_n == parent_n or child_n.startswith(parent_n + "/")


def extract_user_data_dir(cmdline: Sequence[str] | None) -> Optional[str]:
    """Value of --user-data-dir (`=value` or next-argument form), unnormalized."""
    if not cmdline:
        return None
    parts = [str(p) for p in cmdline]
    for index, part in enumerate(parts):
        stripped = part.strip().strip('"')
        low = stripped.lower()
        if low.startswith(_USER_DATA_DIR_FLAG + "="):
            value = stripped.split("=", 1)[1].strip().strip('"')
            return value or None
        if low == _USER_DATA_DIR_FLAG and index + 1 < len(parts):
            value = parts[index + 1].strip().strip('"')
            return value or None
    return None


def is_browser_name(name: str | None) -> bool:
    """True for chrome/chromium/edge/playwright executables."""
    lowered = (name or "").lower()
    return any(hint in lowered for hint in BROWSER_NAME_HINTS)


def is_interpreter_name(name: str | None) -> bool:
    """True for executables that could be running a ToolsAuto entrypoint."""
    lowered = (name or "").lower()
    return any(hint in lowered for hint in INTERPRETER_NAME_HINTS)


# ── snapshot ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    ppid: int
    name: str
    cmdline: tuple[str, ...]
    create_time: float = 0.0
    blob: str = field(default="", compare=False)
    # False for a "thin" record holding only pid/name; ppid, cmdline and
    # create_time are then fetched on demand by the snapshot.
    hydrated: bool = field(default=True, compare=False)

    @staticmethod
    def build(
        pid: int,
        ppid: int = 0,
        name: str = "",
        cmdline: Sequence[str] | None = None,
        create_time: float = 0.0,
        hydrated: bool = True,
    ) -> "ProcInfo":
        parts = tuple(str(p) for p in (cmdline or ()))
        return ProcInfo(
            pid=int(pid),
            ppid=int(ppid or 0),
            name=name or "",
            cmdline=parts,
            create_time=float(create_time or 0.0),
            blob=cmdline_blob(parts),
            hydrated=hydrated,
        )


class ProcessSnapshot:
    """
    One pass over the process table.

    Profile roots and the ToolsAuto process set are computed once per snapshot,
    not once per process, and ancestry is memoized.
    """

    def __init__(self, procs: Iterable[ProcInfo] | None = None, hydrator=None) -> None:
        self._by_pid: dict[int, ProcInfo] = {}
        for info in procs or ():
            self._by_pid[info.pid] = info
        self._hydrator = hydrator
        self._profile_roots: tuple[str, ...] = profile_roots()
        self._project_root: str = project_root()
        self._ancestor_cache: dict[int, tuple[int, ...]] = {}
        self._attribution_cache: dict[int, Optional[str]] = {}
        self._toolsauto_pids: Optional[frozenset[int]] = None

    # -- construction ---------------------------------------------------------

    @classmethod
    def capture(cls) -> "ProcessSnapshot":
        """
        Snapshot the live process table.

        Only pid+name are read up front (milliseconds); ppid, cmdline and
        create_time are pulled per process as needed.
        """
        try:
            import psutil
        except ImportError:  # pragma: no cover - psutil is a hard dep in prod
            return cls([])

        collected: list[ProcInfo] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                pid = info.get("pid")
                if not pid:
                    continue
                collected.append(
                    ProcInfo.build(pid=pid, name=info.get("name") or "", hydrated=False)
                )
            except (psutil.Error, TypeError, ValueError):
                continue
        return cls(collected, hydrator=_psutil_hydrator)

    # -- basic access ---------------------------------------------------------

    def all(self) -> list[ProcInfo]:
        return list(self._by_pid.values())

    def get(self, pid: int | None) -> Optional[ProcInfo]:
        if not pid:
            return None
        return self._by_pid.get(int(pid))

    @property
    def profile_roots(self) -> tuple[str, ...]:
        return self._profile_roots

    def hydrate(self, info: ProcInfo | None) -> Optional[ProcInfo]:
        """Full record for `info`, fetching ppid/cmdline/create_time on first use."""
        if info is None:
            return None
        # Callers may still hold a thin record handed out before hydration;
        # always answer from the map so a process is fetched at most once.
        info = self._by_pid.get(info.pid, info)
        if info.hydrated:
            return info
        filled = None
        if self._hydrator is not None:
            filled = self._hydrator(info)
        if filled is None:
            # Process vanished or is unreadable: remember it as "unknown owner".
            filled = ProcInfo.build(pid=info.pid, name=info.name, hydrated=True)
        self._by_pid[info.pid] = filled
        return filled

    def _hydrated_get(self, pid: int | None) -> Optional[ProcInfo]:
        return self.hydrate(self.get(pid))

    # -- ancestry -------------------------------------------------------------

    def parent(self, info: ProcInfo) -> Optional[ProcInfo]:
        """
        Parent process, guarding against PID reuse: a recycled PID whose process
        started *after* the child cannot be its parent.
        """
        info = self.hydrate(info)
        if not info or not info.ppid or info.ppid == info.pid:
            return None
        parent = self._hydrated_get(info.ppid)
        if parent is None:
            return None
        if info.create_time and parent.create_time and parent.create_time > info.create_time:
            return None
        return parent

    def ancestor_pids(self, pid: int, limit: int = 16) -> tuple[int, ...]:
        """PIDs of all ancestors, nearest first (cycle- and reuse-safe)."""
        cached = self._ancestor_cache.get(pid)
        if cached is not None:
            return cached
        chain: list[int] = []
        seen: set[int] = {pid}
        current = self._hydrated_get(pid)
        for _ in range(limit):
            if current is None:
                break
            parent = self.parent(current)
            if parent is None or parent.pid in seen:
                break
            chain.append(parent.pid)
            seen.add(parent.pid)
            current = parent
        result = tuple(chain)
        self._ancestor_cache[pid] = result
        return result

    # -- ToolsAuto processes --------------------------------------------------

    def _entrypoint_candidates(self) -> list[ProcInfo]:
        """Processes worth reading a cmdline for (interpreters only)."""
        return [
            info
            for info in list(self._by_pid.values())
            if is_interpreter_name(info.name) or (info.hydrated and info.blob)
        ]

    def toolsauto_pids(self) -> frozenset[int]:
        """PIDs of ToolsAuto workers / web / supervisor found in this snapshot."""
        if self._toolsauto_pids is None:
            found: set[int] = set()
            for info in self._entrypoint_candidates():
                full = self.hydrate(info)
                if full and is_toolsauto_entrypoint(full.cmdline, full.name):
                    found.add(full.pid)
            self._toolsauto_pids = frozenset(found)
        return self._toolsauto_pids

    def find_pids(self, spec: str | Sequence[str], *, exclude: Iterable[int] = ()) -> list[int]:
        """
        PIDs actually running the spec — one entry per logical instance.

        A venv launcher stub (`venv/Scripts/python.exe` in a PyManager layout)
        re-executes the real interpreter as a child with an identical cmdline, so
        one worker shows up twice. Only the top-most process of such a chain is
        returned; genuine siblings (two PM2 publishers) are both kept.
        """
        excluded = {int(p) for p in exclude}
        found: list[int] = []
        for info in self._entrypoint_candidates():
            if info.pid in excluded:
                continue
            full = self.hydrate(info)
            if not full or not full.cmdline:
                continue
            if cmdline_matches_spec(full.cmdline, spec, full.name):
                found.append(full.pid)
        if len(found) > 1:
            matched = set(found)
            found = [pid for pid in found if not matched.intersection(self.ancestor_pids(pid))]
        return sorted(found)

    # -- browsers -------------------------------------------------------------

    def is_browser(self, info: ProcInfo) -> bool:
        return is_browser_name(info.name)

    def is_browser_root(self, info: ProcInfo) -> bool:
        """True when this browser process is not a child of another browser."""
        if not self.is_browser(info):
            return False
        parent = self.parent(info)
        return parent is None or not self.is_browser(parent)

    def browser_root(self, info: ProcInfo, limit: int = 16) -> ProcInfo:
        """Top-most browser process of this browser's own tree."""
        current = self.hydrate(info) or info
        for _ in range(limit):
            parent = self.parent(current)
            if parent is None or not self.is_browser(parent):
                return current
            current = parent
        return current

    def browser_attribution(self, info: ProcInfo) -> Optional[str]:
        """
        'profile' / 'worker' when the browser provably belongs to ToolsAuto,
        None when it belongs to someone else OR when ownership is unknown.

        Helper processes inherit the attribution of their root browser: only the
        root carries the --user-data-dir we can verify.
        """
        if not self.is_browser(info):
            return None
        root = self.browser_root(info)
        cached = self._attribution_cache.get(root.pid, "?")
        if cached != "?":
            return cached
        result = self._attribute_browser_root(root)
        self._attribution_cache[root.pid] = result
        return result

    def _attribute_browser_root(self, root: ProcInfo) -> Optional[str]:
        toolsauto = self.toolsauto_pids()
        if toolsauto:
            for ancestor in self.ancestor_pids(root.pid):
                if ancestor in toolsauto:
                    return "worker"

        full = self.hydrate(root)
        if not full or not full.blob:
            # No readable cmdline (access denied / system process): unknown owner.
            return None
        user_data_dir = extract_user_data_dir(full.cmdline)
        if not user_data_dir:
            return None
        # Compare the raw value first, then the resolved one so a relative path
        # or a symlinked profile dir is still recognised as ours.
        candidates = [user_data_dir]
        try:
            candidates.append(str(Path(user_data_dir).resolve()))
        except OSError:
            pass
        roots = (*self._profile_roots, self._project_root)
        for candidate in candidates:
            if any(path_is_within(candidate, root) for root in roots):
                return "profile"
        return None

    def browser_profile_dir(self, info: ProcInfo) -> Optional[str]:
        """Normalized --user-data-dir of this browser's root process, if readable."""
        root = self.hydrate(self.browser_root(info))
        if not root:
            return None
        return normalize_path_text(extract_user_data_dir(root.cmdline))

    def is_toolsauto_browser(self, info: ProcInfo) -> bool:
        return self.browser_attribution(info) is not None

    def iter_browsers(self) -> Iterator[ProcInfo]:
        for info in list(self._by_pid.values()):
            if self.is_browser(info):
                yield info


def _psutil_hydrator(info: ProcInfo) -> Optional[ProcInfo]:
    """Fill ppid/cmdline/create_time for one process (None when unreadable)."""
    try:
        import psutil

        proc = psutil.Process(info.pid)
        with proc.oneshot():
            return ProcInfo.build(
                pid=info.pid,
                ppid=proc.ppid(),
                name=info.name or proc.name(),
                cmdline=proc.cmdline(),
                create_time=proc.create_time(),
            )
    except Exception:
        return None
