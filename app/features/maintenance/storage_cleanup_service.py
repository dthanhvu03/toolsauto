"""
Storage Cleanup & Retention Service for 24/7 Operations.
Implements Milestone 1 (Features 1, 2, 3, 4, 5) per PROJECT.md interface contracts.
"""
from __future__ import annotations

import dataclasses
import fcntl
import gzip
import json
import logging
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, Set

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

import app.config as config

logger = logging.getLogger(__name__)

# Bài Buffer quá giờ hẹn bấy nhiêu giây thì thôi giữ video (Buffer có thể đăng trễ, hoặc đăng lại).
BUFFER_FETCH_GRACE_SEC = 2 * 86400
_VIRAL_ID_RE = re.compile(r"viral_(\d+)_", re.IGNORECASE)


class SessionIntegrityViolationError(Exception):
    """Raised immediately when a protected session file or directory is targeted for deletion."""
    pass


@dataclasses.dataclass
class StorageCleanupResult:
    reclaimed_bytes: int = 0
    media_files_deleted: int = 0
    profiles_cleaned: int = 0
    logs_cleaned: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)


class hybridmethod:
    """Descriptor enabling a method to be called either on an instance or on the class."""

    def __init__(self, func: Callable):
        self.func = func
        self.__doc__ = func.__doc__
        self.__name__ = func.__name__

    def __get__(self, instance, owner=None):
        if instance is None:
            @wraps(self.func)
            def wrapper(*args, **kwargs):
                return self.func(owner(), *args, **kwargs)
            return wrapper

        @wraps(self.func)
        def wrapper(*args, **kwargs):
            return self.func(instance, *args, **kwargs)
        return wrapper


class StorageCleanupService:
    """Centralized disk retention and cleanup service ensuring zero session regression."""

    CRITICAL_SESSION_FILES = {
        "Local State",
        "Preferences",
        "Secure Preferences",
        "Login Data",
        "Login Data-journal",
        "Web Data",
        "Web Data-journal",
        "Network Persistent State",
    }

    CRITICAL_SESSION_DIRS = {
        "Local Storage",
        "Session Storage",
        "Sessions",
        "IndexedDB",
        "Service Worker/Database",
    }

    PROTECTED_SESSION_SUBSTRINGS = (
        "cookies",
        "local state",
        "local storage",
        "session storage",
        "sessions",
        "indexeddb",
        "login data",
        "web data",
        "preferences",
        "secure preferences",
        "network persistent state",
        "service worker/database",
    )

    DISPOSABLE_CACHE_DIRS = {
        "Cache",
        "Code Cache",
        "GPUCache",
        "DawnGraphiteCache",
        "DawnWebGPUCache",
        "GraphiteDawnCache",
        "GrShaderCache",
        "ShaderCache",
        "ScriptCache",
        "Service Worker/CacheStorage",
        "Service Worker/ScriptCache",
        "Shared Dictionary/cache",
        "blob_storage",
        "optimization_guide_model_store",
        "Crashpad/completed",
        "Crashpad/pending",
        "Crashpad",
    }

    KNOWN_ACTIVE_PROFILES = {
        "facebook_15",
        "facebook_16",
        "facebook_17",
        "facebook_18",
        "facebook_19",
        "facebook_20",
        "facebook_scanner",
        "instagram_5",
        "common",
    }

    MAX_FB_LOGS_BYTES = 20 * 1024 * 1024  # 20 MB directory cap

    def __init__(
        self,
        storage_root: Optional[Path | str] = None,
        logs_root: Optional[Path | str] = None,
        quarantine_root: Optional[Path | str] = None,
    ):
        if storage_root is None:
            self.storage_root = Path(getattr(config, "STORAGE_DIR", Path(__file__).resolve().parents[3] / "storage"))
        else:
            self.storage_root = Path(storage_root)

        if logs_root is None:
            self.logs_root = Path(getattr(config, "LOGS_DIR", Path(__file__).resolve().parents[3] / "logs"))
        else:
            self.logs_root = Path(logs_root)

        self.media_root = self.storage_root / "media"
        self.profiles_root = self.storage_root / "profiles"

        if quarantine_root is None:
            self.quarantine_root = self.storage_root / "quarantine"
        else:
            self.quarantine_root = Path(quarantine_root)

    # ──────────────────────────────────────────────────────────────────────────
    # Safety & Integrity Checks
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Checks if a Linux process PID is currently active."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @hybridmethod
    def is_profile_locked(self, profile_dir: Path | str) -> bool:
        """
        Multi-tier concurrency lock detection:
        1. Chromium SingletonLock symlink pointing to active PID.
        2. Non-blocking fcntl.flock on profile .lock files.
        3. Running processes referencing profile directory in cmdline.
        """
        p_dir = Path(profile_dir)

        # 1. Chromium SingletonLock
        lock_file = p_dir / "SingletonLock"
        if lock_file.exists() or lock_file.is_symlink():
            try:
                target = os.readlink(str(lock_file))
                parts = target.split("-")
                if len(parts) >= 2 and parts[-1].isdigit():
                    pid = int(parts[-1])
                    if self._is_pid_alive(pid):
                        return True
                    # PID is dead -> stale lock, can proceed
                else:
                    # Broken symlink or non-standard -> fail-safe rule: treat as locked
                    return True
            except (OSError, ValueError):
                return True

        # 2. Non-blocking fcntl.flock on *.lock files
        for flk in p_dir.glob("*.lock"):
            try:
                with open(flk, "a") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (BlockingIOError, OSError):
                return True

        # 3. Process table inspection via psutil
        if psutil is not None:
            try:
                target_str = str(p_dir.resolve())
                for proc in psutil.process_iter(["pid", "cmdline"]):
                    try:
                        cmd = proc.info.get("cmdline") or []
                        if any(target_str in arg for arg in cmd):
                            return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception:
                pass

        return False

    @hybridmethod
    def assert_session_integrity(self, profile_dir: Path | str) -> bool:
        """
        Checks that critical session files or databases are not corrupted.
        Returns False if Cookies SQLite is 0 bytes or unreadable, or Local State is invalid JSON.
        """
        p_dir = Path(profile_dir)
        default_dir = p_dir / "Default"
        target_dir = default_dir if default_dir.exists() else p_dir

        cookies_db = target_dir / "Cookies"
        if cookies_db.exists():
            if cookies_db.stat().st_size == 0:
                return False
            try:
                conn = sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                cursor.close()
                conn.close()
            except sqlite3.Error:
                return False

        # Critical session files in target_dir or profile root
        for critical_file in self.CRITICAL_SESSION_FILES:
            for parent in (target_dir, p_dir):
                f = parent / critical_file
                if f.exists() and not f.is_file():
                    return False

        # Local State JSON integrity
        local_state = p_dir / "Local State"
        if local_state.exists():
            if not local_state.is_file():
                return False
            try:
                with open(local_state, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception:
                return False

        return True

    def _assert_not_protected_session_file(self, target_path: Path, profile_root: Path) -> None:
        """
        Hard assertion: raises SessionIntegrityViolationError immediately if target_path
        contains or resolves to any protected session component.
        """
        resolved_target = target_path.resolve()
        resolved_profile = profile_root.resolve()

        if resolved_target == resolved_profile:
            raise SessionIntegrityViolationError(
                f"FATAL: Attempted to delete profile root directory: {target_path}"
            )
        if resolved_target == resolved_profile / "Default":
            raise SessionIntegrityViolationError(
                f"FATAL: Attempted to delete Default directory: {target_path}"
            )

        try:
            rel_str = str(resolved_target.relative_to(resolved_profile)).lower().replace("\\", "/")
        except ValueError:
            rel_str = str(resolved_target).lower().replace("\\", "/")

        for protected in self.PROTECTED_SESSION_SUBSTRINGS:
            if protected in rel_str:
                raise SessionIntegrityViolationError(
                    f"ABSOLUTE ZERO REGRESSION VIOLATION: Path '{target_path}' contains "
                    f"protected session component '{protected}'. Aborting deletion immediately!"
                )

    def _get_active_job_media_paths(self) -> set[str]:
        """Queries active DB jobs to shield their media files from pruning."""
        protected: set[str] = set()
        try:
            from app.core.database.core import SessionLocal
            from app.core.database.models import Job
            from app.constants import JobStatus
            from app.core.storage_paths import resolve_media_path

            active_statuses = (
                JobStatus.PENDING,
                JobStatus.RUNNING,
                JobStatus.AI_PROCESSING,
                JobStatus.DRAFT,
                JobStatus.AWAITING_STYLE,
            )
            with SessionLocal() as db:
                rows = (
                    db.query(Job.media_path, Job.processed_media_path)
                    .filter(Job.status.in_(active_statuses))
                    .all()
                )
                for m_path, p_path in rows:
                    for p in (m_path, p_path):
                        if p:
                            resolved = resolve_media_path(p)
                            if resolved:
                                protected.add(os.path.normpath(str(resolved)).lower())
                            else:
                                protected.add(os.path.normpath(str(p)).lower())
        except Exception as exc:
            logger.debug("Active jobs query skipped/failed: %s", exc)
        return protected

    def _get_buffer_scheduled_material_ids(self) -> set[int]:
        """Material của bài đã hẹn trên Buffer — Buffer chỉ tải video lúc tới giờ đăng.

        Job Buffer DONE ngay khi hẹn và không có ``media_path``, nên ``_get_active_job_media_paths``
        không che được. 2026-10-23 20:10 vòng dọn xóa file material 1280 → bài 20:30 Buffer báo 404.
        """
        try:
            from app.core.database.core import SessionLocal
            from app.core.database.models import Job
            from app.constants import JobStatus

            since = time.time() - BUFFER_FETCH_GRACE_SEC
            with SessionLocal() as db:
                rows = (
                    db.query(Job.viral_material_id)
                    .filter(Job.platform == "buffer")
                    .filter(Job.viral_material_id.isnot(None), Job.external_post_id.isnot(None))
                    .filter(Job.status.notin_((JobStatus.FAILED, JobStatus.CANCELLED)))
                    .filter(Job.schedule_ts >= since)
                    .all()
                )
                return {int(mid) for (mid,) in rows}
        except Exception as exc:
            logger.debug("Buffer scheduled jobs query skipped/failed: %s", exc)
            return set()

    def _get_active_profile_names(self) -> set[str]:
        """Returns union of known active profiles and DB accounts."""
        active = set(self.KNOWN_ACTIVE_PROFILES)
        try:
            from app.core.database.core import SessionLocal
            from app.core.database.models import Account

            with SessionLocal() as db:
                accounts = db.query(Account.profile_path, Account.id, Account.platform).all()
                for p_path, acc_id, platform in accounts:
                    if p_path:
                        active.add(Path(p_path).name)
                    if acc_id:
                        prefix = platform if platform else "facebook"
                        active.add(f"{prefix}_{acc_id}")
                        active.add(f"facebook_{acc_id}")
                        active.add(f"threads_{acc_id}")
        except Exception as exc:
            logger.debug("Database accounts query skipped: %s", exc)
        return active

    def _update_material_failed_if_stale(self, file_path: Path, retention_days: int) -> None:
        """Updates ViralMaterial DB status to FAILED when stale READY video is pruned."""
        m = re.search(r"viral_(\d+)_", file_path.name, re.IGNORECASE)
        if not m:
            return
        material_id = int(m.group(1))
        try:
            from app.core.database.core import SessionLocal
            from app.core.database.models import ViralMaterial
            from app.constants import ViralStatus

            with SessionLocal() as db:
                mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
                if mat and mat.status == ViralStatus.READY:
                    mat.status = ViralStatus.FAILED
                    mat.process_tries = 3
                    mat.last_error = f"Đã dọn dẹp theo chính sách lưu trữ (hết hạn > {retention_days} ngày)"
                    db.commit()
        except Exception as exc:
            logger.debug("Failed to update material %s status: %s", material_id, exc)

    # ──────────────────────────────────────────────────────────────────────────
    # Core Pruning Operations
    # ──────────────────────────────────────────────────────────────────────────

    @hybridmethod
    def prune_media(
        self,
        retention_days: int = 7,
        dry_run: bool = False,
        posted_retention_days: int = 0,
    ) -> int:
        """
        Prunes:
        1. All files in `reup/*/da-dang/` (posted videos).
        2. Stale raw and reup videos older than `retention_days` (excluding active jobs).
        3. Orphan frame directories and stale collage thumbnails.
        """
        if retention_days < 0:
            raise ValueError(f"retention_days must be >= 0, got {retention_days}")

        if not self.media_root.exists():
            return 0

        reclaimed = 0
        now = time.time()
        cutoff_ts = now - (retention_days * 86400.0)
        posted_cutoff_ts = now - (posted_retention_days * 86400.0) if posted_retention_days > 0 else now + 86400.0
        protected_paths = self._get_active_job_media_paths()
        buffer_material_ids = self._get_buffer_scheduled_material_ids()

        # 1. Prune da-dang posted files
        for da_dang_dir in self.media_root.glob("reup/*/da-dang"):
            if not da_dang_dir.is_dir():
                continue
            for file_path in da_dang_dir.iterdir():
                if file_path.is_file():
                    if posted_retention_days <= 0 or file_path.stat().st_mtime <= posted_cutoff_ts:
                        size = file_path.stat().st_size
                        reclaimed += size
                        if not dry_run:
                            file_path.unlink()

        # 2. Prune stale raw and reup files older than retention_days
        for media_dir in self.media_root.glob("reup/*"):
            if not media_dir.is_dir() or media_dir.name in ("da-dang", "frames"):
                continue
            for file_path in media_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
                    norm_path = os.path.normpath(str(file_path)).lower()
                    if norm_path in protected_paths:
                        continue
                    id_match = _VIRAL_ID_RE.search(file_path.name)
                    if id_match and int(id_match.group(1)) in buffer_material_ids:
                        continue
                    mtime = file_path.stat().st_mtime
                    if mtime <= cutoff_ts:
                        size = file_path.stat().st_size
                        reclaimed += size
                        if not dry_run:
                            file_path.unlink()
                            self._update_material_failed_if_stale(file_path, retention_days)

        # 3. Prune orphan frames and stale thumbs
        frames_root = self.media_root / "reup" / "frames"
        if frames_root.is_dir():
            for frame_dir in frames_root.iterdir():
                if frame_dir.is_dir():
                    dir_mtime = frame_dir.stat().st_mtime
                    if dir_mtime <= cutoff_ts:
                        for frame_file in frame_dir.glob("*.jpg"):
                            size = frame_file.stat().st_size
                            reclaimed += size
                            if not dry_run:
                                frame_file.unlink()
                        if not dry_run:
                            try:
                                frame_dir.rmdir()
                            except OSError:
                                pass

        thumbs_root = self.media_root / "thumbs"
        if thumbs_root.is_dir():
            for thumb_file in thumbs_root.glob("*.jpg"):
                mtime = thumb_file.stat().st_mtime
                is_stale = mtime <= cutoff_ts
                is_collage = thumb_file.name.endswith("_collage.jpg") and (mtime <= now - 24 * 3600.0)
                if is_stale or is_collage:
                    size = thumb_file.stat().st_size
                    reclaimed += size
                    if not dry_run:
                        thumb_file.unlink()

        return reclaimed

    @hybridmethod
    def prune_profile_caches(self, dry_run: bool = False) -> int:
        """
        Prunes disposable browser caches while asserting 100% session preservation.
        Raises SessionIntegrityViolationError if any session file is targeted.
        """
        if not self.profiles_root.exists():
            return 0

        reclaimed = 0
        for profile_dir in self.profiles_root.iterdir():
            if not profile_dir.is_dir():
                continue

            if self.is_profile_locked(profile_dir):
                continue

            default_dir = profile_dir / "Default"
            target_dir = default_dir if default_dir.exists() else profile_dir

            if not self.assert_session_integrity(profile_dir):
                continue

            # Purge disposable cache directories
            for cache_name in self.DISPOSABLE_CACHE_DIRS:
                cache_path = target_dir / cache_name
                if cache_path.exists() and cache_path.is_dir():
                    self._assert_not_protected_session_file(cache_path, profile_dir)
                    for item in cache_path.rglob("*"):
                        self._assert_not_protected_session_file(item, profile_dir)
                        if item.is_file():
                            reclaimed += item.stat().st_size
                            if not dry_run:
                                try:
                                    item.unlink()
                                except OSError:
                                    pass
                    if not dry_run:
                        try:
                            for sub in sorted(cache_path.rglob("*"), reverse=True):
                                if sub.is_dir():
                                    sub.rmdir()
                            cache_path.rmdir()
                        except OSError:
                            pass

            # Purge disposable telemetry / scratch files (*.pma, crash dumps)
            for pma in target_dir.glob("*.pma"):
                self._assert_not_protected_session_file(pma, profile_dir)
                if pma.is_file():
                    reclaimed += pma.stat().st_size
                    if not dry_run:
                        pma.unlink(missing_ok=True)

            # Strict post-condition assertion
            if not dry_run:
                assert self.assert_session_integrity(profile_dir), (
                    f"CRITICAL SAFETY VIOLATION: Session integrity compromised for {profile_dir.name}"
                )

        return reclaimed

    @hybridmethod
    def prune_obsolete_profiles(
        self,
        active_profile_names: Optional[Set[str] | bool] = None,
        quarantine: bool = True,
        dry_run: bool = False,
    ) -> int:
        """
        Identifies obsolete profiles (e.g. gemini_bot), moves to quarantine or deletes.
        """
        if isinstance(active_profile_names, bool):
            dry_run = active_profile_names
            active_profile_names = None

        if not self.profiles_root.exists():
            return 0

        if active_profile_names is None:
            active_names = self._get_active_profile_names()
        else:
            active_names = set(active_profile_names)

        reclaimed = 0
        for profile_dir in self.profiles_root.iterdir():
            if not profile_dir.is_dir():
                continue
            if profile_dir.name in active_names:
                continue
            if self.is_profile_locked(profile_dir):
                continue

            size = 0
            for f in profile_dir.rglob("*"):
                try:
                    if f.is_file() and not f.is_symlink():
                        size += f.stat().st_size
                except OSError:
                    pass
            reclaimed += size

            if not dry_run:
                if quarantine:
                    self.quarantine_root.mkdir(parents=True, exist_ok=True)
                    dest = self.quarantine_root / profile_dir.name
                    if dest.exists():
                        dest = self.quarantine_root / f"{profile_dir.name}_{int(time.time())}"
                    os.rename(str(profile_dir), str(dest))
                else:
                    for f in sorted(profile_dir.rglob("*"), reverse=True):
                        if f.is_symlink() or f.is_file():
                            try:
                                f.unlink()
                            except OSError:
                                pass
                        elif f.is_dir():
                            try:
                                f.rmdir()
                            except OSError:
                                pass
                    try:
                        profile_dir.rmdir()
                    except OSError:
                        shutil.rmtree(profile_dir, ignore_errors=True)

        return reclaimed

    def _retain_daily_backups(
        self,
        backups_dir: Path,
        keep_days: int = 7,
        dry_run: bool = False,
    ) -> int:
        """Retains last keep_days daily backups, purging older dumps and redundant intraday dumps."""
        reclaimed = 0
        all_dumps = [
            f for f in backups_dir.iterdir()
            if f.is_file() and (f.name.endswith(".sql") or f.name.endswith(".sql.gz"))
        ]
        if not all_dumps:
            return 0

        def _sort_key(p: Path) -> tuple[str, float]:
            m = re.search(r"(\d{8})_(\d{6})", p.name)
            if m:
                return (f"{m.group(1)}_{m.group(2)}", p.stat().st_mtime)
            m_date = re.search(r"(\d{4}[-_]\d{2}[-_]\d{2})", p.name)
            if m_date:
                d = m_date.group(1).replace("-", "").replace("_", "")
                return (f"{d}_000000", p.stat().st_mtime)
            return ("", p.stat().st_mtime)

        by_date: dict[str, list[Path]] = {}
        for f in all_dumps:
            m = re.search(r"(\d{8})_\d{6}", f.name)
            if m:
                d_key = m.group(1)
            else:
                m_date = re.search(r"(\d{4}[-_]\d{2}[-_]\d{2})", f.name)
                if m_date:
                    d_key = m_date.group(1).replace("-", "").replace("_", "")
                else:
                    d_key = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y%m%d")
            by_date.setdefault(d_key, []).append(f)

        for d in by_date:
            by_date[d].sort(key=_sort_key, reverse=True)

        sorted_dates = sorted(by_date.keys(), reverse=True)
        retained_dates = set(sorted_dates[:keep_days])
        today_key = datetime.now().strftime("%Y%m%d")

        to_prune: list[Path] = []
        for d in sorted_dates[keep_days:]:
            to_prune.extend(by_date[d])

        for d in retained_dates:
            if d != today_key and len(by_date[d]) > 1:
                to_prune.extend(by_date[d][1:])

        for f in to_prune:
            try:
                st = f.stat()
                reclaimed += st.st_size
                if not dry_run:
                    f.unlink(missing_ok=True)
            except Exception as e:
                logger.debug("Failed to prune backup snapshot %s: %s", f, e)

        return reclaimed

    @hybridmethod
    def prune_logs_and_backups(self, dry_run: bool = False, min_age_seconds: int = 300) -> int:
        """Prunes DOM failure HTML/PNG captures and gzips SQL backups."""
        reclaimed = 0

        # 1. Prune failure DOM dumps and screenshots in logs/fb/
        if self.logs_root.exists():
            fb_logs = self.logs_root / "fb"
            if fb_logs.is_dir():
                for dump in fb_logs.iterdir():
                    if dump.is_file() and dump.suffix.lower() in (".html", ".png"):
                        size = dump.stat().st_size
                        reclaimed += size
                        if not dry_run:
                            dump.unlink(missing_ok=True)

            # Loose debug files in logs root
            for p in self.logs_root.glob("debug_*.*"):
                if p.is_file() and p.suffix.lower() in (".html", ".png"):
                    size = p.stat().st_size
                    reclaimed += size
                    if not dry_run:
                        p.unlink(missing_ok=True)

            # Debug screenshots
            screen_dir = self.logs_root / "screenshots"
            if screen_dir.is_dir():
                for p in screen_dir.glob("*.png"):
                    if p.is_file():
                        size = p.stat().st_size
                        reclaimed += size
                        if not dry_run:
                            p.unlink(missing_ok=True)

        # 2. Prune debug screenshots in storage/db/*.png
        db_dir = self.storage_root / "db"
        if db_dir.is_dir():
            for p in db_dir.glob("*.png"):
                if p.is_file():
                    size = p.stat().st_size
                    reclaimed += size
                    if not dry_run:
                        p.unlink(missing_ok=True)

        # 3. Compress uncompressed SQL backups and rotate
        db_backups = self.storage_root / "db" / "backups"
        if db_backups.is_dir():
            now = time.time()
            for sql_file in db_backups.glob("*.sql"):
                if sql_file.is_file() and not sql_file.name.endswith(".tmp.sql"):
                    try:
                        st_mtime = sql_file.stat().st_mtime
                    except OSError:
                        continue

                    file_age = now - st_mtime
                    m = re.search(r"(\d{8})_(\d{6})", sql_file.name)
                    if m:
                        try:
                            fn_dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
                            fn_age = now - fn_dt.timestamp()
                            file_age = max(file_age, fn_age)
                        except Exception:
                            pass

                    if file_age < min_age_seconds:
                        logger.debug("Skipping in-flight/recent SQL backup: %s (age=%.1fs < %ds)", sql_file.name, file_age, min_age_seconds)
                        continue

                    orig_size = sql_file.stat().st_size
                    orig_mtime = sql_file.stat().st_mtime
                    if not dry_run:
                        gz_path = sql_file.with_suffix(".sql.gz")
                        tmp_gz = sql_file.with_suffix(".tmp.gz")
                        try:
                            with open(sql_file, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=9) as f_out:
                                shutil.copyfileobj(f_in, f_out, length=64 * 1024)
                            if tmp_gz.exists() and tmp_gz.stat().st_size > 0:
                                tmp_gz.replace(gz_path)
                                try:
                                    os.utime(gz_path, (orig_mtime, orig_mtime))
                                except OSError:
                                    pass
                                new_size = gz_path.stat().st_size
                                sql_file.unlink(missing_ok=True)
                                reclaimed += max(0, orig_size - new_size)
                            else:
                                if tmp_gz.exists():
                                    tmp_gz.unlink(missing_ok=True)
                        except Exception as e:
                            logger.error("Failed to compress %s: %s", sql_file, e)
                    else:
                        # Estimated ~70% compression savings
                        reclaimed += int(orig_size * 0.7)

            # Apply 7-day snapshot retention
            reclaimed += self._retain_daily_backups(db_backups, keep_days=7, dry_run=dry_run)

        return reclaimed

    # ──────────────────────────────────────────────────────────────────────────
    # High-Level Orchestration: audit() and run_all()
    # ──────────────────────────────────────────────────────────────────────────

    @hybridmethod
    def audit(self) -> dict[str, Any]:
        """Calculates reclaimable bytes without deleting anything (dry-run)."""
        res = self.run_all(dry_run=True)
        return {
            "reclaimable_bytes": res.reclaimed_bytes,
            "media_files_count": res.media_files_deleted,
            "profiles_count": res.profiles_cleaned,
            "logs_count": res.logs_cleaned,
            "errors": res.errors,
        }

    @hybridmethod
    def run_all(
        self,
        dry_run: bool = False,
        retention_days: int = 7,
        include_obsolete: bool = False,
        quarantine: bool = True,
    ) -> StorageCleanupResult:
        """Executes full cleanup routine across all layers and logs results."""
        res = StorageCleanupResult()

        try:
            m_bytes = self.prune_media(retention_days=retention_days, dry_run=dry_run)
            res.reclaimed_bytes += m_bytes
            res.media_files_deleted = 1 if m_bytes > 0 else 0
        except Exception as e:
            res.errors.append(f"Media cleanup error: {e}")

        try:
            p_bytes = self.prune_profile_caches(dry_run=dry_run)
            res.reclaimed_bytes += p_bytes
            res.profiles_cleaned = 1 if p_bytes > 0 else 0
        except Exception as e:
            res.errors.append(f"Profile cache cleanup error: {e}")

        if include_obsolete:
            try:
                obs_bytes = self.prune_obsolete_profiles(quarantine=quarantine, dry_run=dry_run)
                res.reclaimed_bytes += obs_bytes
                if obs_bytes > 0:
                    res.profiles_cleaned += 1
            except Exception as e:
                res.errors.append(f"Obsolete profile cleanup error: {e}")

        try:
            l_bytes = self.prune_logs_and_backups(dry_run=dry_run)
            res.reclaimed_bytes += l_bytes
            res.logs_cleaned = 1 if l_bytes > 0 else 0
        except Exception as e:
            res.errors.append(f"Logs/backup cleanup error: {e}")

        return res
