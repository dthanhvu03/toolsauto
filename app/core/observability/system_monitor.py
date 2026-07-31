"""
System health checks, queue-pressure alerts, temp cleanup (outputs/).
Extracted from workers/maintenance.py (TASK-20260329-05).
PLAN-048: ToolsAuto-scoped Chrome count + Windows orphan purge.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, NamedTuple

from sqlalchemy.orm import Session

import app.config as config
from app.core.notifier.service import NotifierService
from app.core.process_scan import ProcInfo, ProcessSnapshot, normalize_path_text, path_is_within
from app.constants import JobStatus, ViralStatus


logger = logging.getLogger(__name__)

ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))
ALERT_RAM_PCT_THRESHOLD = float(os.getenv("ALERT_RAM_PCT_THRESHOLD", "85"))
ALERT_CHROME_PROC_THRESHOLD = int(os.getenv("ALERT_CHROME_PROC_THRESHOLD", "20"))
CLEANUP_OUTPUTS_AFTER_DAYS = int(os.getenv("CLEANUP_OUTPUTS_AFTER_DAYS", "7"))
# Grace period before a ToolsAuto browser can be considered orphaned — protects
# a browser that was launched between the worker scan and the browser scan.
ORPHAN_MIN_AGE_SEC = float(os.getenv("ORPHAN_BROWSER_MIN_AGE_SEC", "120"))
# Browser counting walks the process tree; both pollers tolerate slightly stale data.
CHROME_COUNT_CACHE_SEC = float(os.getenv("CHROME_COUNT_CACHE_SEC", "30"))

_chrome_counts_cache: tuple[float, "ChromeProcessCounts"] | None = None
_chrome_counts_lock = threading.Lock()

_last_alert_ts: dict[str, float] = {}


def _get_runtime_int(db, key: str, fallback: int) -> int:
    try:
        from app.core import settings as runtime_settings

        return int(runtime_settings.get_effective(db, key))
    except Exception:
        return fallback


def _should_alert(key: str) -> bool:
    now = time.time()
    last = _last_alert_ts.get(key, 0)
    if (now - last) >= ALERT_COOLDOWN_SEC:
        _last_alert_ts[key] = now
        return True
    return False


class ChromeProcessCounts(NamedTuple):
    """
    Browser census. A NamedTuple so existing tuple unpacking keeps working while
    call sites can read the fields by name.
    """

    total_processes: int          # every chrome-like process on the machine
    toolsauto_instances: int      # root browsers attributable to ToolsAuto
    toolsauto_processes: int      # those roots plus their helper processes


def count_chrome_processes(
    snapshot: ProcessSnapshot | None = None, use_cache: bool = True
) -> ChromeProcessCounts:
    """
    Census of browser processes.

    `toolsauto_instances` counts root browser processes only (one Chromium
    instance spawns many helper processes); that is the number the publisher
    claim gate compares against worker.publisher.max_browser_instances.

    Attributing every browser costs ~1s on a busy Windows box and both callers
    (claim gate, supervisor loop) poll continuously, so the result is cached for
    CHROME_COUNT_CACHE_SEC. Pass a snapshot to bypass the cache.
    """
    global _chrome_counts_cache
    if snapshot is None and use_cache:
        with _chrome_counts_lock:
            cached = _chrome_counts_cache
        if cached is not None and (time.monotonic() - cached[0]) < CHROME_COUNT_CACHE_SEC:
            return cached[1]

    snap = snapshot or ProcessSnapshot.capture()
    total = 0
    instances = 0
    attributed = 0
    for info in snap.iter_browsers():
        total += 1
        if not snap.is_toolsauto_browser(info):
            continue
        attributed += 1
        if snap.is_browser_root(info):
            instances += 1
    result = ChromeProcessCounts(total, instances, attributed)
    if snapshot is None:
        with _chrome_counts_lock:
            _chrome_counts_cache = (time.monotonic(), result)
    return result


def reset_chrome_count_cache() -> None:
    """Drop the cached counts (tests, or right after a purge)."""
    global _chrome_counts_cache
    with _chrome_counts_lock:
        _chrome_counts_cache = None


class SystemMonitorService:
    """RAM/disk/process monitoring and Telegram alerts (best-effort)."""

    def check_health(self) -> dict[str, Any]:
        """Return RAM %, CPU %, disk %, total Chrome count, ToolsAuto Chrome count."""
        out: dict[str, Any] = {
            "ram_percent": None,
            "cpu_percent": None,
            "disk_percent": None,
            "chrome_playwright_count": None,
            "chrome_toolsauto_count": None,
            "chrome_toolsauto_process_count": None,
            "error": None,
        }
        try:
            import psutil

            vm = psutil.virtual_memory()
            out["ram_percent"] = float(vm.percent)
            out["cpu_percent"] = float(psutil.cpu_percent(interval=0.1))
            try:
                du = psutil.disk_usage(str(config.BASE_DIR))
                out["disk_percent"] = float(du.percent)
            except Exception:
                du = psutil.disk_usage("/")
                out["disk_percent"] = float(du.percent)
            total, instances, attributed = count_chrome_processes()
            out["chrome_playwright_count"] = total
            out["chrome_toolsauto_count"] = instances
            out["chrome_toolsauto_process_count"] = attributed
        except Exception as e:
            out["error"] = str(e)
        return out

    def send_alert(self, message: str) -> None:
        """Broadcast via Telegram if notifier is registered."""
        try:
            NotifierService._broadcast(message)
        except Exception:
            logger.debug("SystemMonitorService.send_alert failed", exc_info=True)

    def alert_toolsauto_browser_pressure(self, count: int, max_browsers: int) -> None:
        """Cooldown alert when publisher pauses due to ToolsAuto browser pressure."""
        if not _should_alert("toolsauto_browser"):
            return
        self.send_alert(
            "🧠 <b>ToolsAuto browser cao — Publisher pause claim</b>\n"
            f"• chrome_toolsauto: <b>{count}</b> (max {max_browsers})\n"
            "Gợi ý: đợi job xong, hoặc kiểm tra orphan Chromium trong storage/profiles."
        )

    def profiles_of_running_jobs(self, db: Session | None) -> set[str]:
        """
        Normalized profile paths of accounts that have a RUNNING job.

        Ancestry is the primary protection, but a browser can lose its parent
        while its job is still in flight (Playwright's node driver dies, or the
        launcher process exits and the browser is re-parented). A live RUNNING
        job is authoritative evidence that its profile must not be touched.
        """
        if db is None:
            return set()
        try:
            from app.core.database.models import Account, Job

            rows = (
                db.query(Account)
                .join(Job, Job.account_id == Account.id)
                .filter(Job.status == JobStatus.RUNNING)
                .distinct()
                .all()
            )
        except Exception:
            logger.warning(
                "[SystemMonitor] Could not read RUNNING jobs; skipping orphan purge to stay safe",
                exc_info=True,
            )
            return {"*"}  # sentinel: caller treats this as "protect everything"

        profiles: set[str] = set()
        for account in rows:
            path = getattr(account, "resolved_profile_path", None) or getattr(account, "profile_path", None)
            normalized = normalize_path_text(path)
            if normalized:
                profiles.add(normalized)
        return profiles

    def find_orphan_toolsauto_browsers(
        self,
        snapshot: ProcessSnapshot | None = None,
        now: float | None = None,
        db: Session | None = None,
    ) -> list[ProcInfo]:
        """
        Root browser processes that provably belong to ToolsAuto (profile under a
        canonical profile root) and have no live ToolsAuto worker/web ancestor.

        Anything we cannot attribute with certainty is left alone: a browser with
        an unreadable cmdline, a browser owned by another project, a browser whose
        owner is still running, and a browser whose profile belongs to a RUNNING
        job are all skipped.
        """
        snap = snapshot or ProcessSnapshot.capture()
        protected = snap.toolsauto_pids()
        busy_profiles = self.profiles_of_running_jobs(db)
        if "*" in busy_profiles:
            return []
        moment = time.time() if now is None else now
        orphans: list[ProcInfo] = []

        for info in snap.iter_browsers():
            attribution = snap.browser_attribution(info)
            if attribution is None:
                # Unknown or foreign ownership → never touch.
                continue
            if attribution != "profile":
                # Only a profile path under our own roots is hard evidence; an
                # ancestor-based attribution means the owner is alive anyway.
                continue
            if not snap.is_browser_root(info):
                # Killing the root takes the helper processes with it.
                continue
            if info.pid in protected or set(snap.ancestor_pids(info.pid)) & protected:
                continue
            profile_dir = snap.browser_profile_dir(info)
            if profile_dir and any(
                path_is_within(profile_dir, busy) or path_is_within(busy, profile_dir)
                for busy in busy_profiles
            ):
                logger.info(
                    "[SystemMonitor] Browser pid=%s belongs to a RUNNING job profile (%s) — not touching",
                    info.pid,
                    profile_dir,
                )
                continue
            age = moment - info.create_time if info.create_time else ORPHAN_MIN_AGE_SEC + 1
            if age < ORPHAN_MIN_AGE_SEC:
                # Just launched: its owner may not have been visible in this scan.
                logger.debug(
                    "[SystemMonitor] Skipping young ToolsAuto browser pid=%s age=%.1fs",
                    info.pid,
                    age,
                )
                continue
            orphans.append(info)
        return orphans

    def purge_orphan_toolsauto_browsers(self, db: Session | None = None) -> int:
        """
        Terminate orphan ToolsAuto browsers. Never kills normal user Chrome, and
        never touches a profile that a RUNNING job is using (pass `db`).
        """
        try:
            import psutil
        except ImportError:
            return 0

        killed = 0
        for info in self.find_orphan_toolsauto_browsers(db=db):
            logger.warning(
                "[SystemMonitor] Killing orphan ToolsAuto browser pid=%s name=%s",
                info.pid,
                info.name,
            )
            try:
                proc = psutil.Process(info.pid)
                # Guard against PID reuse between the scan and the kill.
                if info.create_time and abs(proc.create_time() - info.create_time) > 1.0:
                    logger.debug("[SystemMonitor] pid=%s was recycled, skipping", info.pid)
                    continue
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                killed += 1
            except psutil.Error as e:
                logger.debug("orphan kill failed pid=%s: %s", info.pid, e)
        if killed:
            logger.info("[SystemMonitor] purge_orphan_toolsauto_browsers killed=%s", killed)
        return killed

    def cleanup_temp_files(self) -> int:
        """
        Remove old files under OUTPUTS_DIR (default: project outputs/).
        Returns count of files removed.
        """
        removed = 0
        cutoff = time.time() - CLEANUP_OUTPUTS_AFTER_DAYS * 86400
        try:
            config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 0
        try:
            for path in config.OUTPUTS_DIR.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        except Exception as e:
            logger.warning("[SystemMonitor] cleanup_temp_files: %s", e)
        if removed:
            logger.info(
                "[SystemMonitor] cleanup_temp_files removed %d file(s) under %s",
                removed,
                config.OUTPUTS_DIR,
            )
        return removed

    def maybe_alert_queue_and_resources(self, db: Session) -> None:
        """Telegram alerts for queue congestion and RAM/Chrome pressure (cooldown)."""
        try:
            from app.core.database.models import Job, ViralMaterial

            pending = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
            drafts = db.query(Job).filter(Job.status == JobStatus.DRAFT).count()
            ai = db.query(Job).filter(Job.status == JobStatus.AI_PROCESSING).count()
            running = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
            viral_new = db.query(ViralMaterial).filter(ViralMaterial.status == ViralStatus.NEW).count()

            th_pending = _get_runtime_int(db, "ALERT_PENDING_THRESHOLD", config.ALERT_PENDING_THRESHOLD)
            th_drafts = _get_runtime_int(db, "ALERT_DRAFT_THRESHOLD", config.ALERT_DRAFT_THRESHOLD)
            th_viral = _get_runtime_int(db, "ALERT_VIRAL_NEW_THRESHOLD", config.ALERT_VIRAL_NEW_THRESHOLD)

            if pending >= th_pending or drafts >= th_drafts or viral_new >= th_viral:
                if _should_alert("queue"):
                    NotifierService._broadcast(
                        "🚦 <b>Queue đang cao</b>\n"
                        f"• PENDING: <b>{pending}</b>\n"
                        f"• RUNNING: <b>{running}</b>\n"
                        f"• DRAFT: <b>{drafts}</b>\n"
                        f"• AI_PROCESSING: <b>{ai}</b>\n"
                        f"• Viral NEW: <b>{viral_new}</b>\n"
                        "Gợi ý: /queue để xem tổng quan."
                    )
        except Exception:
            pass

        try:
            health = self.check_health()
            ram_pct = float(health.get("ram_percent") or 0)
            chrome_total = int(health.get("chrome_playwright_count") or 0)
            chrome_ta = int(health.get("chrome_toolsauto_count") or 0)

            if ram_pct >= ALERT_RAM_PCT_THRESHOLD or chrome_ta >= ALERT_CHROME_PROC_THRESHOLD:
                if _should_alert("resources"):
                    NotifierService._broadcast(
                        "🧠 <b>Áp lực tài nguyên cao</b>\n"
                        f"• RAM: <b>{ram_pct:.1f}%</b>\n"
                        f"• Chrome ToolsAuto: <b>{chrome_ta}</b>\n"
                        f"• Chrome tổng (máy): <b>{chrome_total}</b>\n"
                        "Gợi ý: giảm backlog, hoặc tắt idle engagement khi bận."
                    )
        except Exception:
            pass
