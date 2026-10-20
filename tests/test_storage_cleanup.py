"""
Comprehensive unit tests for StorageCleanupService and Milestone 1 features.
Covers:
1. StorageCleanupResult & SessionIntegrityViolationError
2. Media pruning (da-dang, stale raw/reup, frames, thumbnails, active jobs, DB sync)
3. Profile cache pruning with 100% session preservation assertions & concurrency locks
4. Obsolete profiles quarantine and removal
5. Logs & database backup pruning and gzip compression
6. High-level audit() and run_all() orchestration
7. Typer CLI commands in manage.py
8. Periodic maintenance worker integration
"""
from __future__ import annotations

import fcntl
import gzip
import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.features.maintenance.storage_cleanup_service import (
    SessionIntegrityViolationError,
    StorageCleanupResult,
    StorageCleanupService,
)
from manage import app as cli_app


@pytest.fixture
def cleanup_env(tmp_path: Path):
    """Creates a temporary isolated storage and logs directory tree for tests."""
    storage_root = tmp_path / "storage"
    logs_root = tmp_path / "logs"

    # 1. Media structure
    da_dang_dir = storage_root / "media" / "reup" / "tiktok" / "da-dang"
    da_dang_dir.mkdir(parents=True, exist_ok=True)
    tiktok_dir = storage_root / "media" / "reup" / "tiktok"
    frames_dir = storage_root / "media" / "reup" / "frames" / "viral_101"
    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir = storage_root / "media" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()

    # Posted files
    f_posted_1 = da_dang_dir / "viral_101_tiktok_reup.mp4"
    f_posted_1.write_bytes(b"POSTED_MEDIA_1" * 1024)
    f_posted_2 = da_dang_dir / "viral_102_tiktok_reup.mp4"
    f_posted_2.write_bytes(b"POSTED_MEDIA_2" * 1024)

    # Fresh ready file (< 7 days)
    f_fresh = tiktok_dir / "viral_201_fresh_reup.mp4"
    f_fresh.write_bytes(b"FRESH_MEDIA" * 1024)
    os.utime(f_fresh, (now - 2 * 86400, now - 2 * 86400))

    # Stale raw and reup files (> 7 days)
    f_stale_raw = tiktok_dir / "viral_301_stale.mp4"
    f_stale_raw.write_bytes(b"STALE_RAW_MEDIA" * 1024)
    os.utime(f_stale_raw, (now - 14 * 86400, now - 14 * 86400))

    f_stale_reup = tiktok_dir / "viral_301_stale_reup.mp4"
    f_stale_reup.write_bytes(b"STALE_REUP_MEDIA" * 1024)
    os.utime(f_stale_reup, (now - 14 * 86400, now - 14 * 86400))

    # Stale frames & thumbnails
    f_frame = frames_dir / "frame_00.jpg"
    f_frame.write_bytes(b"FRAME_DATA" * 512)
    os.utime(f_frame, (now - 10 * 86400, now - 10 * 86400))
    os.utime(frames_dir, (now - 10 * 86400, now - 10 * 86400))

    f_thumb = thumbs_dir / "thumb_101.jpg"
    f_thumb.write_bytes(b"THUMB_DATA" * 512)
    os.utime(f_thumb, (now - 10 * 86400, now - 10 * 86400))

    f_collage = thumbs_dir / "hash123_collage.jpg"
    f_collage.write_bytes(b"COLLAGE_DATA" * 1024)
    os.utime(f_collage, (now - 2 * 86400, now - 2 * 86400))

    # 2. Profiles structure
    fb16_dir = storage_root / "profiles" / "facebook_16" / "Default"
    fb16_dir.mkdir(parents=True, exist_ok=True)

    # Session files
    cookies_path = fb16_dir / "Cookies"
    conn = sqlite3.connect(cookies_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE cookies (name TEXT, value TEXT, host_key TEXT)")
    cur.execute("INSERT INTO cookies VALUES ('c_user', '100012345678', '.facebook.com')")
    cur.execute("INSERT INTO cookies VALUES ('xs', 'secret_session_token', '.facebook.com')")
    cur.execute("INSERT INTO cookies VALUES ('datr', 'datr_token_unique', '.facebook.com')")
    conn.commit()
    conn.close()

    local_state_path = fb16_dir.parent / "Local State"
    local_state_path.write_text(json.dumps({"os_crypt": {"encrypted_key": "AQAAANCMnd8H..."}}))

    prefs_path = fb16_dir / "Preferences"
    prefs_path.write_text(json.dumps({"profile": {"name": "Facebook Account 16"}}))

    local_storage_dir = fb16_dir / "Local Storage" / "leveldb"
    local_storage_dir.mkdir(parents=True, exist_ok=True)
    f_ls = local_storage_dir / "000003.log"
    f_ls.write_bytes(b"LOCAL_STORAGE_STATE_DATA")

    # Disposable caches
    for cname in ("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "GrShaderCache", "ScriptCache"):
        cdir = fb16_dir / cname
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "data_0.bin").write_bytes(b"DISPOSABLE_CACHE_DATA" * 1024)

    pma_file = fb16_dir / "BrowserMetrics-spare.pma"
    pma_file.write_bytes(b"PMA_DATA" * 512)

    # Dead test profiles
    gemini_bot = storage_root / "profiles" / "gemini_bot" / "Default"
    gemini_bot.mkdir(parents=True, exist_ok=True)
    (gemini_bot / "Preferences").write_text("{}")
    (gemini_bot / "Cache").mkdir(parents=True, exist_ok=True)
    (gemini_bot / "Cache" / "huge.bin").write_bytes(b"OBSOLETE_DATA" * 2048)

    # 3. Logs & Backups
    fb_logs = logs_root / "fb"
    fb_logs.mkdir(parents=True, exist_ok=True)
    (fb_logs / "failure_dump_1.html").write_text("<html>Crash</html>" * 100)
    (fb_logs / "failure_shot_1.png").write_bytes(b"PNG_DATA" * 500)

    db_debug = storage_root / "db"
    db_debug.mkdir(parents=True, exist_ok=True)
    (db_debug / "debug_comment_123.png").write_bytes(b"DEBUG_PNG" * 200)

    db_backups = storage_root / "db" / "backups"
    db_backups.mkdir(parents=True, exist_ok=True)
    b1 = db_backups / "toolsauto_db_20261018_030000.sql"
    b1.write_text("CREATE TABLE test (id int);\n" * 500)
    os.utime(b1, (now - 86400, now - 86400))
    b2 = db_backups / "toolsauto_db_20261017_030000.sql"
    b2.write_text("CREATE TABLE test (id int);\n" * 500)
    os.utime(b2, (now - 2 * 86400, now - 2 * 86400))
    b3 = db_backups / "toolsauto_db_20261017_120000.sql"
    b3.write_text("CREATE TABLE test (id int);\n" * 500)
    os.utime(b3, (now - 2 * 86400 + 3600, now - 2 * 86400 + 3600))

    service = StorageCleanupService(storage_root=storage_root, logs_root=logs_root)

    return {
        "storage_root": storage_root,
        "logs_root": logs_root,
        "service": service,
        "files": {
            "posted_1": f_posted_1,
            "posted_2": f_posted_2,
            "fresh": f_fresh,
            "stale_raw": f_stale_raw,
            "stale_reup": f_stale_reup,
            "frame": f_frame,
            "thumb": f_thumb,
            "collage": f_collage,
            "cookies": cookies_path,
            "local_state": local_state_path,
            "prefs": prefs_path,
            "local_storage": f_ls,
            "pma": pma_file,
            "gemini_bot": storage_root / "profiles" / "gemini_bot",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Data Structures & Exceptions
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupDataStructures:
    def test_storage_cleanup_result_defaults(self):
        result = StorageCleanupResult()
        assert result.reclaimed_bytes == 0
        assert result.media_files_deleted == 0
        assert result.profiles_cleaned == 0
        assert result.logs_cleaned == 0
        assert result.errors == []

    def test_storage_cleanup_result_custom_values(self):
        result = StorageCleanupResult(
            reclaimed_bytes=1024,
            media_files_deleted=5,
            profiles_cleaned=2,
            logs_cleaned=10,
            errors=["Warning 1"],
        )
        assert result.reclaimed_bytes == 1024
        assert result.media_files_deleted == 5
        assert result.profiles_cleaned == 2
        assert result.logs_cleaned == 10
        assert result.errors == ["Warning 1"]

    def test_session_integrity_violation_error(self):
        err = SessionIntegrityViolationError("Cookies file targeted")
        assert isinstance(err, Exception)
        assert "Cookies file targeted" in str(err)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Media Pruning
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupMediaPruning:
    def test_prune_media_deletes_posted_files(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        p1 = cleanup_env["files"]["posted_1"]
        p2 = cleanup_env["files"]["posted_2"]

        assert p1.exists()
        assert p2.exists()

        reclaimed = svc.prune_media(retention_days=7, dry_run=False)
        assert reclaimed > 0
        assert not p1.exists()
        assert not p2.exists()

    def test_prune_media_stale_files_vs_fresh_files(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fresh = cleanup_env["files"]["fresh"]
        stale_raw = cleanup_env["files"]["stale_raw"]
        stale_reup = cleanup_env["files"]["stale_reup"]

        assert fresh.exists()
        assert stale_raw.exists()
        assert stale_reup.exists()

        svc.prune_media(retention_days=7, dry_run=False)

        assert fresh.exists()
        assert not stale_raw.exists()
        assert not stale_reup.exists()

    def test_prune_media_orphan_frames_and_thumbnails(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        frame = cleanup_env["files"]["frame"]
        thumb = cleanup_env["files"]["thumb"]
        collage = cleanup_env["files"]["collage"]

        assert frame.exists()
        assert thumb.exists()
        assert collage.exists()

        svc.prune_media(retention_days=7, dry_run=False)

        assert not frame.exists()
        assert not thumb.exists()
        assert not collage.exists()

    def test_prune_media_protects_active_job_media_paths(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        stale_reup = cleanup_env["files"]["stale_reup"]

        with patch.object(svc, "_get_active_job_media_paths", return_value={os.path.normpath(str(stale_reup)).lower()}):
            svc.prune_media(retention_days=7, dry_run=False)
            assert stale_reup.exists()

    def test_prune_media_updates_db_material_status(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        stale_reup = cleanup_env["files"]["stale_reup"]

        with patch.object(svc, "_update_material_failed_if_stale") as mock_update:
            svc.prune_media(retention_days=7, dry_run=False)
            mock_update.assert_called_with(stale_reup, 7)

    def test_prune_media_negative_retention_days_raises_value_error(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        with pytest.raises(ValueError, match="retention_days must be >= 0"):
            svc.prune_media(retention_days=-1, dry_run=False)

    def test_prune_media_dry_run_preserves_files(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        p1 = cleanup_env["files"]["posted_1"]
        stale = cleanup_env["files"]["stale_raw"]

        reclaimed = svc.prune_media(retention_days=7, dry_run=True)
        assert reclaimed > 0
        assert p1.exists()
        assert stale.exists()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Profile Cache Pruning & Session Integrity
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupProfileCaches:
    def test_prune_profile_caches_purges_disposable_caches_and_pma(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_default = cleanup_env["storage_root"] / "profiles" / "facebook_16" / "Default"
        pma = cleanup_env["files"]["pma"]

        assert (fb16_default / "GPUCache").exists()
        assert pma.exists()

        reclaimed = svc.prune_profile_caches(dry_run=False)
        assert reclaimed > 0

        assert not (fb16_default / "GPUCache").exists()
        assert not (fb16_default / "Code Cache").exists()
        assert not pma.exists()

    def test_prune_profile_caches_strictly_preserves_session_files(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        cookies = cleanup_env["files"]["cookies"]
        local_state = cleanup_env["files"]["local_state"]
        prefs = cleanup_env["files"]["prefs"]
        ls = cleanup_env["files"]["local_storage"]

        svc.prune_profile_caches(dry_run=False)

        assert cookies.exists()
        assert local_state.exists()
        assert prefs.exists()
        assert ls.exists()

        # Check SQLite Cookies row values
        conn = sqlite3.connect(cookies)
        rows = conn.execute("SELECT name, value FROM cookies ORDER BY name").fetchall()
        conn.close()
        assert len(rows) == 3
        assert rows[0] == ("c_user", "100012345678")

    def test_session_integrity_violation_error_raised_if_session_component_targeted(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_dir = cleanup_env["storage_root"] / "profiles" / "facebook_16"
        cookies_path = fb16_dir / "Default" / "Cookies"

        with pytest.raises(SessionIntegrityViolationError, match="ABSOLUTE ZERO REGRESSION VIOLATION"):
            svc._assert_not_protected_session_file(cookies_path, fb16_dir)

    def test_profile_root_directory_targeted_raises_integrity_error(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_dir = cleanup_env["storage_root"] / "profiles" / "facebook_16"

        with pytest.raises(SessionIntegrityViolationError, match="FATAL: Attempted to delete profile root"):
            svc._assert_not_protected_session_file(fb16_dir, fb16_dir)

    def test_is_profile_locked_active_pid(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_dir = cleanup_env["storage_root"] / "profiles" / "facebook_16"
        lock_file = fb16_dir / "SingletonLock"
        lock_file.symlink_to(f"toolsauto-vps-{os.getpid()}")

        assert svc.is_profile_locked(fb16_dir) is True

    def test_is_profile_locked_stale_pid_can_clean(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_dir = cleanup_env["storage_root"] / "profiles" / "facebook_16"
        lock_file = fb16_dir / "SingletonLock"
        lock_file.symlink_to("toolsauto-vps-9999999")

        assert svc.is_profile_locked(fb16_dir) is False

    def test_is_profile_locked_fcntl_flock(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        fb16_dir = cleanup_env["storage_root"] / "profiles" / "facebook_16"
        lock_path = fb16_dir / "test.lock"

        with open(lock_path, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            assert svc.is_profile_locked(fb16_dir) is True
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def test_assert_session_integrity_detects_0_byte_cookies(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        cookies = cleanup_env["files"]["cookies"]
        cookies.write_bytes(b"")

        assert svc.assert_session_integrity(cookies.parent.parent) is False

    def test_assert_session_integrity_detects_corrupt_local_state(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        local_state = cleanup_env["files"]["local_state"]
        local_state.write_text("INVALID_JSON_CORRUPT{")

        assert svc.assert_session_integrity(local_state.parent) is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. Obsolete Profile Pruning
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupObsoleteProfiles:
    def test_prune_obsolete_profiles_quarantines_dead_profile(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        active = {"facebook_16"}

        assert (storage_root / "profiles" / "gemini_bot").exists()
        reclaimed = svc.prune_obsolete_profiles(active_profile_names=active, quarantine=True, dry_run=False)

        assert reclaimed > 0
        assert not (storage_root / "profiles" / "gemini_bot").exists()
        assert (storage_root / "quarantine" / "gemini_bot").exists()

    def test_prune_obsolete_profiles_permanent_deletion(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        active = {"facebook_16"}

        reclaimed = svc.prune_obsolete_profiles(active_profile_names=active, quarantine=False, dry_run=False)

        assert reclaimed > 0
        assert not (storage_root / "profiles" / "gemini_bot").exists()
        assert not (storage_root / "quarantine" / "gemini_bot").exists()

    def test_prune_obsolete_profiles_preserves_active_profiles(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        active = {"facebook_16"}

        svc.prune_obsolete_profiles(active_profile_names=active, quarantine=True, dry_run=False)
        assert (storage_root / "profiles" / "facebook_16").exists()

    def test_prune_obsolete_profiles_dry_run(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        active = {"facebook_16"}

        reclaimed = svc.prune_obsolete_profiles(active_profile_names=active, quarantine=True, dry_run=True)
        assert reclaimed > 0
        assert (storage_root / "profiles" / "gemini_bot").exists()

    def test_get_active_profile_names_queries_account_model_attributes(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        # Mock SessionLocal with diverse Account tuples (profile_path, id, platform)
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            ("/path/to/custom_account_profile", 42, "tiktok"),
            (None, 88, "facebook"),
            ("/path/to/threads_profile", 99, "threads"),
            (None, 105, None),  # platform is None, should default to facebook
        ]

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db
            names = svc._get_active_profile_names()

            # Verify known static active profiles
            assert "facebook_15" in names
            assert "facebook_16" in names

            # Verify dynamic accounts resolution
            assert "custom_account_profile" in names
            assert "tiktok_42" in names
            assert "facebook_42" in names
            assert "threads_42" in names

            assert "facebook_88" in names
            assert "threads_88" in names

            assert "threads_profile" in names
            assert "threads_99" in names
            assert "facebook_99" in names

            assert "facebook_105" in names
            assert "threads_105" in names

    def test_prune_obsolete_profiles_deletes_directory_with_broken_symlink(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        profiles_dir = storage_root / "profiles"

        # Create obsolete profile with broken Chromium SingletonLock symlink
        broken_profile = profiles_dir / "dead_profile_broken_lock"
        broken_profile.mkdir(parents=True, exist_ok=True)
        (broken_profile / "data.txt").write_text("SOME_DATA")
        broken_lock = broken_profile / "SingletonLock"
        broken_lock.symlink_to("vps-dead-999999")

        assert broken_profile.exists()
        assert broken_lock.is_symlink()
        assert not broken_lock.exists()  # Broken symlink target does not exist

        # Prune obsolete profiles with permanent deletion (quarantine=False)
        reclaimed = svc.prune_obsolete_profiles(active_profile_names={"facebook_15", "facebook_16"}, quarantine=False, dry_run=False)

        assert reclaimed > 0
        assert not broken_profile.exists(), "Directory with broken symlink must be deleted completely without OSError"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Logs & Database Backups Pruning
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupLogsAndBackups:
    def test_prune_logs_purges_failure_dumps_and_screenshots(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        logs_root = cleanup_env["logs_root"]
        storage_root = cleanup_env["storage_root"]

        fb_dump = logs_root / "fb" / "failure_dump_1.html"
        db_png = storage_root / "db" / "debug_comment_123.png"

        assert fb_dump.exists()
        assert db_png.exists()

        reclaimed = svc.prune_logs_and_backups(dry_run=False)
        assert reclaimed > 0

        assert not fb_dump.exists()
        assert not db_png.exists()

    def test_compress_sql_backups_with_gzip(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        backups_dir = storage_root / "db" / "backups"
        sql_file = backups_dir / "toolsauto_db_20261018_030000.sql"

        assert sql_file.exists()
        svc.prune_logs_and_backups(dry_run=False)

        assert not sql_file.exists()
        gz_file = backups_dir / "toolsauto_db_20261018_030000.sql.gz"
        assert gz_file.exists()

        # Verify gz is valid gzip and decodes to original text
        with gzip.open(gz_file, "rt") as f:
            content = f.read()
            assert "CREATE TABLE test" in content

    def test_backup_retention_purges_duplicate_intraday_snapshots(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        backups_dir = storage_root / "db" / "backups"

        b1 = backups_dir / "toolsauto_db_20261017_030000.sql"
        b2 = backups_dir / "toolsauto_db_20261017_120000.sql"

        # Give b2 newer mtime
        os.utime(b1, (1000, 1000))
        os.utime(b2, (2000, 2000))

        svc.prune_logs_and_backups(dry_run=False)

        # The older intraday snapshot (b1) should be purged, newest (b2) compressed and retained
        assert not (backups_dir / "toolsauto_db_20261017_030000.sql.gz").exists()
        assert (backups_dir / "toolsauto_db_20261017_120000.sql.gz").exists()

    def test_logs_and_backups_dry_run_preserves_files(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        logs_root = cleanup_env["logs_root"]
        fb_dump = logs_root / "fb" / "failure_dump_1.html"

        reclaimed = svc.prune_logs_and_backups(dry_run=True)
        assert reclaimed > 0
        assert fb_dump.exists()

    def test_prune_logs_and_backups_preserves_inflight_sql_backups(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        backups_dir = storage_root / "db" / "backups"

        now = time.time()
        # In-flight SQL backup written just now (< 300s)
        inflight_sql = backups_dir / "toolsauto_db_active_inflight.sql"
        inflight_sql.write_text("INSERT INTO accounts VALUES (1); -- active in-flight dump")
        os.utime(inflight_sql, (now - 10, now - 10))

        # Completed older backup written 10 minutes ago (> 300s)
        completed_sql = backups_dir / "toolsauto_db_completed_old.sql"
        completed_sql.write_text("CREATE TABLE completed (id int);")
        os.utime(completed_sql, (now - 600, now - 600))

        svc.prune_logs_and_backups(dry_run=False, min_age_seconds=300)

        # In-flight backup must be preserved uncompressed
        assert inflight_sql.exists(), "Active in-flight SQL dump must NOT be compressed or deleted"
        assert not (backups_dir / "toolsauto_db_active_inflight.sql.gz").exists()

        # Older backup must be compressed to .sql.gz and original unlinked
        assert not completed_sql.exists(), "Completed older SQL dump must be compressed"
        assert (backups_dir / "toolsauto_db_completed_old.sql.gz").exists()


# ═══════════════════════════════════════════════════════════════════════════
# 6. High-Level audit() and run_all()
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCleanupServiceOrchestration:
    def test_audit_breakdown_dictionary(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        data = svc.audit()

        assert "reclaimable_bytes" in data
        assert "media_files_count" in data
        assert "profiles_count" in data
        assert "logs_count" in data
        assert "errors" in data
        assert data["reclaimable_bytes"] > 0
        assert data["errors"] == []

    def test_run_all_success_aggregation(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        res = svc.run_all(dry_run=False, retention_days=7)

        assert isinstance(res, StorageCleanupResult)
        assert res.reclaimed_bytes > 0
        assert res.media_files_deleted == 1
        assert res.profiles_cleaned == 1
        assert res.logs_cleaned == 1
        assert res.errors == []

    def test_run_all_error_isolation(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]

        with patch.object(svc, "prune_media", side_effect=RuntimeError("Disk I/O Error")):
            res = svc.run_all(dry_run=False)
            assert len(res.errors) == 1
            assert "Disk I/O Error" in res.errors[0]
            # Other steps should still succeed
            assert res.profiles_cleaned == 1
            assert res.logs_cleaned == 1

    def test_classmethod_style_calling(self):
        # Calling on the class directly creates default instance and works
        with patch.object(StorageCleanupService, "run_all") as mock_run_all:
            mock_res = StorageCleanupResult(reclaimed_bytes=500)
            mock_run_all.return_value = mock_res
            res = StorageCleanupService.run_all(dry_run=True)
            assert res.reclaimed_bytes == 500


# ═══════════════════════════════════════════════════════════════════════════
# 7. Typer CLI Commands
# ═══════════════════════════════════════════════════════════════════════════

class TestStorageCLICommands:
    def test_cli_storage_audit_command(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "audit"])
        assert result.exit_code == 0
        assert "Auditing storage for reclaimable disk space" in result.output
        assert "Total reclaimable:" in result.output

    def test_cli_storage_cleanup_dry_run_command(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "cleanup", "--dry-run"])
        assert result.exit_code == 0
        assert "Starting storage cleanup [DRY-RUN]" in result.output
        assert "Cleanup completed" in result.output

    def test_cli_storage_cleanup_custom_retention(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "cleanup", "--retention-days", "14", "--dry-run"])
        assert result.exit_code == 0
        assert "retention_days=14" in result.output

    def test_cli_storage_cleanup_purge_obsolete_flag(self):
        runner = CliRunner()
        with patch("app.features.maintenance.storage_cleanup_service.StorageCleanupService.run_all") as mock_run:
            mock_run.return_value = StorageCleanupResult(reclaimed_bytes=2048, profiles_cleaned=1)
            result = runner.invoke(cli_app, ["storage", "cleanup", "--purge-obsolete", "--retention-days", "5"])
            assert result.exit_code == 0
            assert "purge_obsolete=True" in result.output
            mock_run.assert_called_once_with(
                dry_run=False,
                retention_days=5,
                include_obsolete=True,
                quarantine=False,
            )

    def test_run_all_with_purge_obsolete_permanently_deletes_profile(self, cleanup_env):
        svc: StorageCleanupService = cleanup_env["service"]
        storage_root = cleanup_env["storage_root"]
        dead_profile = storage_root / "profiles" / "dead_profile_to_purge"
        dead_profile.mkdir(parents=True, exist_ok=True)
        (dead_profile / "dummy.txt").write_text("DUMMY")

        res = svc.run_all(dry_run=False, include_obsolete=True, quarantine=False)
        assert res.reclaimed_bytes > 0
        assert not dead_profile.exists()
        assert not (storage_root / "quarantine" / "dead_profile_to_purge").exists()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Maintenance Worker Integration
# ═══════════════════════════════════════════════════════════════════════════

class TestMaintenanceWorkerStorageIntegration:
    @pytest.fixture(autouse=True)
    def preserve_logging_state(self):
        yield
        import logging
        logging.getLogger("app").propagate = True

    def test_run_storage_cleanup_invoked_and_throttled(self):
        import app.features.system_panel.workers.maintenance as maint

        maint._last_storage_cleanup_ts = 0

        with patch("app.features.maintenance.storage_cleanup_service.StorageCleanupService.run_all") as mock_run:
            mock_run.return_value = StorageCleanupResult(reclaimed_bytes=1024, media_files_deleted=2)
            maint._run_storage_cleanup()
            mock_run.assert_called_once_with(dry_run=False, retention_days=7)

            # Second call immediately after should be throttled
            mock_run.reset_mock()
            maint._run_storage_cleanup()
            mock_run.assert_not_called()

    def test_run_storage_cleanup_exception_isolated(self):
        import app.features.system_panel.workers.maintenance as maint

        maint._last_storage_cleanup_ts = 0

        with patch("app.features.maintenance.storage_cleanup_service.StorageCleanupService.run_all", side_effect=Exception("Database lock error")):
            # Must not raise exception
            maint._run_storage_cleanup()
