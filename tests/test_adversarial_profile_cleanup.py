"""
Adversarial Stress Test Suite for Profile Cache Pruning and Session Preservation.
Empirical verification for Milestone 1 (M1) challenger review.

Tests:
1. Real Chromium profile session preservation (SQLite Cookies, Local State JSON,
   Preferences, Local Storage leveldb, IndexedDB, Login Data, Web Data).
2. Adversarial session file and symlink injection attacks into disposable cache paths.
3. Concurrency locking via SingletonLock (active test PID vs dead PID vs malformed symlink),
   fcntl.flock, and psutil process cmdline.
4. Corruption detection & fail-safe skipping (0-byte Cookies, corrupt JSON Local State).
5. Flat profile structures (no Default/ subdirectory).
"""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.maintenance.storage_cleanup_service import (
    SessionIntegrityViolationError,
    StorageCleanupService,
)


def create_realistic_chromium_profile(profile_dir: Path, has_default: bool = True) -> dict[str, Path]:
    """Creates a realistic Chromium profile structure with real SQLite databases and session files."""
    target_dir = profile_dir / "Default" if has_default else profile_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Real SQLite Cookies database (Chromium v115+ schema)
    cookies_path = target_dir / "Cookies"
    conn = sqlite3.connect(cookies_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE cookies (
            creation_utc INTEGER NOT NULL,
            host_key TEXT NOT NULL,
            top_frame_site_key TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            encrypted_value BLOB NOT NULL,
            path TEXT NOT NULL,
            expires_utc INTEGER NOT NULL,
            is_secure INTEGER NOT NULL,
            is_httponly INTEGER NOT NULL,
            last_access_utc INTEGER NOT NULL,
            has_expires INTEGER NOT NULL,
            is_persistent INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            samesite INTEGER NOT NULL,
            source_scheme INTEGER NOT NULL,
            source_port INTEGER NOT NULL,
            is_same_party INTEGER NOT NULL
        )
    """)
    cookies_data = [
        (13350000000000000, ".facebook.com", "", "c_user", "100088991234567", b"", "/", 13390000000000000, 1, 0, 13350000000000000, 1, 1, 1, 1, 2, 443, 0),
        (13350000000000001, ".facebook.com", "", "xs", "45%3Asuper_secret_session%3A2%3A1", b"", "/", 13390000000000000, 1, 1, 13350000000000000, 1, 1, 1, 1, 2, 443, 0),
        (13350000000000002, ".facebook.com", "", "fr", "0rEaL_fAcEbOoK_fR_tOkEn", b"", "/", 13360000000000000, 1, 1, 13350000000000000, 1, 1, 1, 1, 2, 443, 0),
        (13350000000000003, ".facebook.com", "", "datr", "dAtR_IdEnTiFiEr_sEsSiOn", b"", "/", 13410000000000000, 1, 1, 13350000000000000, 1, 1, 1, 1, 2, 443, 0),
        (13350000000000004, ".facebook.com", "", "sb", "sB_bRoWsEr_sTaTe_KeY", b"", "/", 13410000000000000, 1, 1, 13350000000000000, 1, 1, 1, 1, 2, 443, 0),
        (13350000000000005, ".facebook.com", "", "presence", "EDvF3EtimeF1729000000", b"", "/", 0, 1, 0, 13350000000000000, 0, 0, 1, 1, 2, 443, 0),
    ]
    cur.executemany("INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cookies_data)
    conn.commit()
    conn.close()

    # 2. Local State JSON in profile root
    local_state_path = profile_dir / "Local State"
    local_state_data = {
        "os_crypt": {"encrypted_key": "RFBBUEkBAAAA0Iyd3wEV0RGMegDAT8kx6wEAAAA..."},
        "profile": {"info_cache": {"Default": {"name": "Test Facebook 18", "is_using_default_name": False}}},
        "browser": {"enabled_labs_experiments": []},
    }
    local_state_path.write_text(json.dumps(local_state_data, indent=2))

    # 3. Preferences JSON in target_dir
    prefs_path = target_dir / "Preferences"
    prefs_data = {
        "account_id_migration_state": 2,
        "profile": {"name": "Test Facebook 18"},
        "session": {"restore_on_startup": 1},
    }
    prefs_path.write_text(json.dumps(prefs_data, indent=2))

    # 4. Local Storage leveldb
    ls_dir = target_dir / "Local Storage" / "leveldb"
    ls_dir.mkdir(parents=True, exist_ok=True)
    (ls_dir / "000003.log").write_bytes(b"LEVELDB_LOG_SESSION_STORAGE_RECORDS_MOCK")
    (ls_dir / "CURRENT").write_text("MANIFEST-000001\n")
    (ls_dir / "MANIFEST-000001").write_bytes(b"MANIFEST_DATA")

    # 5. IndexedDB
    idb_dir = target_dir / "IndexedDB" / "https_www.facebook.com_0.indexeddb.leveldb"
    idb_dir.mkdir(parents=True, exist_ok=True)
    (idb_dir / "000001.ldb").write_bytes(b"INDEXED_DB_ENTRIES_FOR_FACEBOOK")

    # 6. Login Data & Web Data SQLite
    login_data_path = target_dir / "Login Data"
    conn_lg = sqlite3.connect(login_data_path)
    conn_lg.execute("CREATE TABLE logins (origin_url TEXT, username_value TEXT, password_value BLOB)")
    conn_lg.execute("INSERT INTO logins VALUES ('https://www.facebook.com', 'user18', x'deadbeef')")
    conn_lg.commit()
    conn_lg.close()

    web_data_path = target_dir / "Web Data"
    conn_wd = sqlite3.connect(web_data_path)
    conn_wd.execute("CREATE TABLE autofill (name TEXT, value TEXT)")
    conn_wd.execute("INSERT INTO autofill VALUES ('test', 'value')")
    conn_wd.commit()
    conn_wd.close()

    # 7. Disposable Caches
    cache_dir = target_dir / "Cache" / "Cache_Data"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "data_0").write_bytes(b"BLOCK_CACHE_0" * 2048)
    (cache_dir / "data_1").write_bytes(b"BLOCK_CACHE_1" * 4096)
    (cache_dir / "index").write_bytes(b"CACHE_INDEX" * 512)
    (cache_dir / "f_000001").write_bytes(b"MEDIA_RESOURCE_CACHE" * 8192)

    code_cache_dir = target_dir / "Code Cache" / "js"
    code_cache_dir.mkdir(parents=True, exist_ok=True)
    (code_cache_dir / "0123456789abcdef_0").write_bytes(b"V8_BYTECODE_CACHE" * 4096)

    gpu_cache_dir = target_dir / "GPUCache"
    gpu_cache_dir.mkdir(parents=True, exist_ok=True)
    (gpu_cache_dir / "data_0").write_bytes(b"GPU_SHADER_CACHE" * 1024)

    dawn_cache_dir = target_dir / "DawnGraphiteCache"
    dawn_cache_dir.mkdir(parents=True, exist_ok=True)
    (dawn_cache_dir / "data_0").write_bytes(b"DAWN_CACHE" * 1024)

    gr_cache_dir = target_dir / "GrShaderCache"
    gr_cache_dir.mkdir(parents=True, exist_ok=True)
    (gr_cache_dir / "gr_shader.bin").write_bytes(b"GR_SHADER" * 1024)

    pma_spare = target_dir / "BrowserMetrics-spare.pma"
    pma_spare.write_bytes(b"PMA_SPARE_METRICS" * 512)

    return {
        "profile_dir": profile_dir,
        "target_dir": target_dir,
        "cookies": cookies_path,
        "local_state": local_state_path,
        "prefs": prefs_path,
        "local_storage": ls_dir,
        "indexeddb": idb_dir,
        "login_data": login_data_path,
        "web_data": web_data_path,
        "cache": cache_dir,
        "code_cache": code_cache_dir,
        "gpu_cache": gpu_cache_dir,
        "dawn_cache": dawn_cache_dir,
        "gr_cache": gr_cache_dir,
        "pma_spare": pma_spare,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite: Empirical Adversarial Challenge
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialProfileCleanup:

    def test_realistic_profile_cache_pruning_zero_session_loss(self, tmp_path: Path):
        """Stress-tests real Chromium profile with complete SQLite cookies and session stores."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        # Pre-cleanup sanity
        assert nodes["cookies"].stat().st_size > 0
        assert nodes["cache"].exists()
        assert nodes["gpu_cache"].exists()

        # Execute pruning
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed > 0, "Expected reclaimed bytes from disposable caches"

        # 1. Verify ALL disposable caches are purged
        assert not (nodes["target_dir"] / "Cache").exists()
        assert not (nodes["target_dir"] / "Code Cache").exists()
        assert not (nodes["target_dir"] / "GPUCache").exists()
        assert not (nodes["target_dir"] / "DawnGraphiteCache").exists()
        assert not (nodes["target_dir"] / "GrShaderCache").exists()
        assert not nodes["pma_spare"].exists()

        # 2. Verify 100% preservation of Cookies SQLite database & records
        assert nodes["cookies"].exists()
        conn = sqlite3.connect(f"file:{nodes['cookies']}?mode=ro", uri=True)
        cur = conn.cursor()
        rows = cur.execute("SELECT name, value, host_key FROM cookies ORDER BY name").fetchall()
        cur.close()
        conn.close()

        expected_cookies = {
            "c_user": "100088991234567",
            "xs": "45%3Asuper_secret_session%3A2%3A1",
            "fr": "0rEaL_fAcEbOoK_fR_tOkEn",
            "datr": "dAtR_IdEnTiFiEr_sEsSiOn",
            "sb": "sB_bRoWsEr_sTaTe_KeY",
            "presence": "EDvF3EtimeF1729000000",
        }
        actual_cookies = {name: val for name, val, host in rows}
        assert actual_cookies == expected_cookies, "Cookie records were modified or lost!"

        # 3. Verify Local State JSON content is intact
        assert nodes["local_state"].exists()
        with open(nodes["local_state"], "r", encoding="utf-8") as f:
            ls_data = json.load(f)
        assert "os_crypt" in ls_data
        assert ls_data["profile"]["info_cache"]["Default"]["name"] == "Test Facebook 18"

        # 4. Verify Preferences JSON is intact
        assert nodes["prefs"].exists()
        with open(nodes["prefs"], "r", encoding="utf-8") as f:
            p_data = json.load(f)
        assert p_data["profile"]["name"] == "Test Facebook 18"

        # 5. Verify Local Storage leveldb & IndexedDB
        assert nodes["local_storage"].exists()
        assert (nodes["local_storage"] / "000003.log").read_bytes() == b"LEVELDB_LOG_SESSION_STORAGE_RECORDS_MOCK"
        assert nodes["indexeddb"].exists()
        assert (nodes["indexeddb"] / "000001.ldb").read_bytes() == b"INDEXED_DB_ENTRIES_FOR_FACEBOOK"

        # 6. Verify Login Data & Web Data SQLite tables
        assert nodes["login_data"].exists()
        conn_lg = sqlite3.connect(f"file:{nodes['login_data']}?mode=ro", uri=True)
        assert conn_lg.execute("SELECT count(*) FROM logins").fetchone()[0] == 1
        conn_lg.close()

        assert nodes["web_data"].exists()
        conn_wd = sqlite3.connect(f"file:{nodes['web_data']}?mode=ro", uri=True)
        assert conn_wd.execute("SELECT count(*) FROM autofill").fetchone()[0] == 1
        conn_wd.close()

        # 7. Final integrity check returns True
        assert service.assert_session_integrity(profile_dir) is True

    def test_flat_profile_structure_without_default_dir(self, tmp_path: Path):
        """Tests profiles that store session and cache files directly in profile root (no Default/)."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "common"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=False)

        service = StorageCleanupService(storage_root=storage_root)

        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed > 0

        # Caches gone
        assert not (profile_dir / "Cache").exists()
        assert not (profile_dir / "GPUCache").exists()

        # Flat session files preserved
        assert nodes["cookies"].exists()
        assert nodes["local_state"].exists()
        assert nodes["prefs"].exists()
        assert service.assert_session_integrity(profile_dir) is True

    def test_adversarial_injection_simulated_session_file_in_cache_dir(self, tmp_path: Path):
        """Simulates adversarial or accidental placement of a protected session file inside Cache/."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        # Inject protected file inside Cache/
        injected = nodes["target_dir"] / "Cache" / "Cache_Data" / "injected_cookies.tmp"
        injected.write_text("ADVERSARIAL_INJECTION_TRYING_TO_DELETE_COOKIE_SESSION")

        with pytest.raises(SessionIntegrityViolationError, match="ABSOLUTE ZERO REGRESSION VIOLATION"):
            service.prune_profile_caches(dry_run=False)

        # Verify the injected file was NOT deleted and abortion happened
        assert injected.exists()
        # Verify Cookies was NOT touched
        assert nodes["cookies"].exists()

    def test_adversarial_injection_local_state_in_code_cache(self, tmp_path: Path):
        """Simulates injection of Local State filename in disposable Code Cache."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        injected = nodes["target_dir"] / "Code Cache" / "Local State"
        injected.write_text("MALICIOUS_LOCAL_STATE_INJECTION")

        with pytest.raises(SessionIntegrityViolationError, match="ABSOLUTE ZERO REGRESSION VIOLATION"):
            service.prune_profile_caches(dry_run=False)

        assert injected.exists()

    def test_adversarial_symlink_inside_cache_pointing_to_cookies(self, tmp_path: Path):
        """Adversarial attack: a symlink inside Cache/ pointing to real Cookies database."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        symlink_in_cache = nodes["target_dir"] / "Cache" / "harmless_looking_file.bin"
        symlink_in_cache.symlink_to(nodes["cookies"])

        # When pruning, _assert_not_protected_session_file resolves symlink target!
        with pytest.raises(SessionIntegrityViolationError, match="ABSOLUTE ZERO REGRESSION VIOLATION"):
            service.prune_profile_caches(dry_run=False)

        # Cookies must be 100% intact
        assert nodes["cookies"].exists()
        assert nodes["cookies"].stat().st_size > 0

    def test_adversarial_symlink_pointing_to_external_profile_session(self, tmp_path: Path):
        """Adversarial attack: symlink inside Cache pointing outside current profile to another profile's Cookies."""
        storage_root = tmp_path / "storage"
        p1 = storage_root / "profiles" / "facebook_18"
        p2 = storage_root / "profiles" / "facebook_19"
        nodes1 = create_realistic_chromium_profile(p1, has_default=True)
        nodes2 = create_realistic_chromium_profile(p2, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        external_symlink = nodes1["target_dir"] / "GPUCache" / "leak.dat"
        external_symlink.symlink_to(nodes2["cookies"])

        with pytest.raises(SessionIntegrityViolationError, match="ABSOLUTE ZERO REGRESSION VIOLATION"):
            service.prune_profile_caches(dry_run=False)

        assert nodes1["cookies"].exists()
        assert nodes2["cookies"].exists()

    def test_profile_root_or_default_dir_deletion_hard_block(self, tmp_path: Path):
        """Verifies hard assertion blocks direct targeting of profile root or Default dir."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        default_dir = profile_dir / "Default"
        default_dir.mkdir(parents=True, exist_ok=True)

        service = StorageCleanupService(storage_root=storage_root)

        with pytest.raises(SessionIntegrityViolationError, match="Attempted to delete profile root"):
            service._assert_not_protected_session_file(profile_dir, profile_dir)

        with pytest.raises(SessionIntegrityViolationError, match="Attempted to delete Default directory"):
            service._assert_not_protected_session_file(default_dir, profile_dir)

    def test_active_concurrency_singletonlock_with_current_test_pid(self, tmp_path: Path):
        """Active concurrency: Chromium SingletonLock points to currently running test PID."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        # Create active SingletonLock symlink pointing to our current PID
        lock_file = profile_dir / "SingletonLock"
        lock_file.symlink_to(f"test-vps-server-{os.getpid()}")

        # Verify lock detector returns True
        assert service.is_profile_locked(profile_dir) is True

        # Run prune_profile_caches() -> profile MUST be skipped
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed == 0, "Locked profile must be completely skipped!"

        # All cache files must still exist
        assert nodes["cache"].exists()
        assert nodes["gpu_cache"].exists()
        assert nodes["pma_spare"].exists()

    def test_stale_concurrency_singletonlock_with_dead_pid(self, tmp_path: Path):
        """Stale concurrency: Chromium SingletonLock points to a dead PID (e.g. 9999999)."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        lock_file = profile_dir / "SingletonLock"
        lock_file.symlink_to("test-vps-server-9999999")

        assert service.is_profile_locked(profile_dir) is False

        # Should safely clean disposable caches
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed > 0
        assert not (nodes["target_dir"] / "Cache").exists()
        assert nodes["cookies"].exists()

    def test_malformed_singletonlock_treated_as_locked(self, tmp_path: Path):
        """Fail-safe: non-standard or malformed SingletonLock symlink defaults to LOCKED."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        lock_file = profile_dir / "SingletonLock"
        lock_file.symlink_to("arbitrary_non_pid_target")

        # Must fail safe and treat as locked
        assert service.is_profile_locked(profile_dir) is True
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed == 0
        assert nodes["cache"].exists()

    def test_singletonlock_regular_file_treated_as_locked(self, tmp_path: Path):
        """Fail-safe: SingletonLock created as regular file (not symlink) defaults to LOCKED."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        lock_file = profile_dir / "SingletonLock"
        lock_file.write_text("regular file lock")

        assert service.is_profile_locked(profile_dir) is True
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed == 0

    def test_fcntl_flock_concurrency_lock_detection(self, tmp_path: Path):
        """Concurrency: profile holds active fcntl.flock on a *.lock file."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        lock_path = profile_dir / "session.lock"
        with open(lock_path, "w") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

            assert service.is_profile_locked(profile_dir) is True
            reclaimed = service.prune_profile_caches(dry_run=False)
            assert reclaimed == 0

            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

        # After releasing lock, profile can be cleaned
        assert service.is_profile_locked(profile_dir) is False
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed > 0

    def test_psutil_cmdline_inspection_concurrency_lock(self, tmp_path: Path):
        """Concurrency: running process references profile dir in cmdline."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        # Mock psutil.process_iter to simulate a browser process with --user-data-dir
        fake_proc = type("Proc", (), {
            "info": {"pid": 55555, "cmdline": ["chromium", f"--user-data-dir={profile_dir}"]}
        })()

        with patch("psutil.process_iter", return_value=[fake_proc]):
            assert service.is_profile_locked(profile_dir) is True
            reclaimed = service.prune_profile_caches(dry_run=False)
            assert reclaimed == 0

    def test_corrupt_cookies_db_skipped_by_session_integrity(self, tmp_path: Path):
        """Integrity oracle: 0-byte or corrupted SQLite Cookies DB causes profile to be skipped."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        # Corrupt cookies database to 0 bytes
        nodes["cookies"].write_bytes(b"")

        assert service.assert_session_integrity(profile_dir) is False

        # prune_profile_caches skips profiles failing assert_session_integrity
        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed == 0
        assert nodes["cache"].exists()

    def test_corrupt_local_state_skipped_by_session_integrity(self, tmp_path: Path):
        """Integrity oracle: invalid JSON in Local State causes profile to be skipped."""
        storage_root = tmp_path / "storage"
        profile_dir = storage_root / "profiles" / "facebook_18"
        nodes = create_realistic_chromium_profile(profile_dir, has_default=True)

        service = StorageCleanupService(storage_root=storage_root)

        nodes["local_state"].write_text("{CORRUPTED_NON_JSON")

        assert service.assert_session_integrity(profile_dir) is False

        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed == 0
        assert nodes["cache"].exists()

    def test_multi_profile_mixed_state_isolation(self, tmp_path: Path):
        """
        Multi-profile stress test:
        - Profile 1 (facebook_15): Active lock (current PID) -> SKIPPED
        - Profile 2 (facebook_16): Cleanable with real cookies -> CLEANED, cookies 100% intact
        - Profile 3 (facebook_17): Corrupted Local State -> SKIPPED
        """
        storage_root = tmp_path / "storage"
        p1 = storage_root / "profiles" / "facebook_15"
        p2 = storage_root / "profiles" / "facebook_16"
        p3 = storage_root / "profiles" / "facebook_17"

        nodes1 = create_realistic_chromium_profile(p1, has_default=True)
        nodes2 = create_realistic_chromium_profile(p2, has_default=True)
        nodes3 = create_realistic_chromium_profile(p3, has_default=True)

        # Profile 1 has active lock
        (p1 / "SingletonLock").symlink_to(f"test-server-{os.getpid()}")

        # Profile 3 has corrupted local state
        nodes3["local_state"].write_text("CORRUPTED")

        service = StorageCleanupService(storage_root=storage_root)

        reclaimed = service.prune_profile_caches(dry_run=False)
        assert reclaimed > 0

        # Profile 1: untouched (locked)
        assert nodes1["cache"].exists()

        # Profile 2: cleaned, cookies intact
        assert not (nodes2["target_dir"] / "Cache").exists()
        assert nodes2["cookies"].exists()
        conn2 = sqlite3.connect(f"file:{nodes2['cookies']}?mode=ro", uri=True)
        assert conn2.execute("SELECT count(*) FROM cookies").fetchone()[0] == 6
        conn2.close()

        # Profile 3: untouched (corrupt)
        assert nodes3["cache"].exists()
