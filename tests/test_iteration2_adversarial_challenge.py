"""
Adversarial Stress Test Suite for Iteration 2 Remediation (Empirical Challenger).
Covers:
1. Broken symlink removal in prune_obsolete_profiles(quarantine=False):
   - Dead symlinks (pointing to non-existent files or directories)
   - Chained dead symlinks (link1 -> link2 -> missing)
   - Circular symlinks (file-to-file cycle, self-referential symlinks, directory loops)
   - Deep nested broken symlinks (10+ levels deep)
   - Symlinks pointing outside storage root (verifying zero outside blast radius)
   - Stale Chromium SingletonLock vs dead symlinks
   - Dry run and quarantine modes under symlink anomalies
2. Dynamic DB accounts protection:
   - Non-hardcoded account IDs (e.g. 500, 9999, 123456) completely protected
   - Diverse platforms (facebook, threads, tiktok, instagram, custom)
   - Inactive DB accounts (is_active=False) protected from deletion
   - Custom profile paths and trailing slashes protected
   - End-to-end integration with prune_obsolete_profiles, audit(), and run_all()
   - Live SQLite database verification
3. Massive Scale Stress Harness:
   - High volume of dynamic accounts (100+) alongside complex obsolete profile graphs
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.database.core import Base, engine, SessionLocal
from app.core.database.models import Account
from app.features.maintenance.storage_cleanup_service import (
    StorageCleanupResult,
    StorageCleanupService,
)


@pytest.fixture
def challenge_env(tmp_path: Path):
    """Sets up an isolated filesystem environment for adversarial testing."""
    storage_root = tmp_path / "storage"
    logs_root = tmp_path / "logs"
    quarantine_root = tmp_path / "quarantine"

    profiles_dir = storage_root / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    quarantine_root.mkdir(parents=True, exist_ok=True)

    service = StorageCleanupService(
        storage_root=storage_root,
        logs_root=logs_root,
        quarantine_root=quarantine_root,
    )

    return {
        "storage_root": storage_root,
        "logs_root": logs_root,
        "quarantine_root": quarantine_root,
        "profiles_dir": profiles_dir,
        "service": service,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Broken Symlink Removal in prune_obsolete_profiles(quarantine=False)
# ═══════════════════════════════════════════════════════════════════════════

class TestBrokenSymlinkRemovalAdversarial:
    def test_dead_symlinks_single_and_multiple(self, challenge_env):
        """Tests that dead symlinks pointing to non-existent files or directories are deleted."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        dead_profile = profiles_dir / "obsolete_dead_symlinks"
        dead_profile.mkdir(parents=True, exist_ok=True)
        (dead_profile / "regular.txt").write_text("Hello World")

        # 1. Dead symlink to non-existent file
        dead_file_link = dead_profile / "link_to_nowhere.txt"
        dead_file_link.symlink_to("/nonexistent/path/never_existed_12345.bin")

        # 2. Dead symlink to non-existent directory
        dead_dir_link = dead_profile / "link_to_missing_dir"
        dead_dir_link.symlink_to("/nonexistent/directory/structure/deep")

        # 3. Dead symlink in subfolder
        sub = dead_profile / "subfolder"
        sub.mkdir()
        dead_sub_link = sub / "sub_dead_link"
        dead_sub_link.symlink_to(dead_profile / "deleted_file.dat")

        assert dead_profile.exists()
        assert dead_file_link.is_symlink()
        assert not dead_file_link.exists()  # Broken target

        # Execute permanent pruning
        reclaimed = service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert reclaimed > 0
        assert not dead_profile.exists(), "Profile with dead symlinks must be deleted completely"

    def test_chained_dead_symlinks(self, challenge_env):
        """Tests chained symlinks: A -> B -> C -> non_existent."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        chain_profile = profiles_dir / "obsolete_chain_symlinks"
        chain_profile.mkdir(parents=True, exist_ok=True)

        target_missing = chain_profile / "final_missing.txt"
        link_c = chain_profile / "link_c"
        link_b = chain_profile / "link_b"
        link_a = chain_profile / "link_a"

        link_c.symlink_to(target_missing)
        link_b.symlink_to(link_c)
        link_a.symlink_to(link_b)

        assert link_a.is_symlink()
        assert not link_a.exists()

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert not chain_profile.exists(), "Profile with chained dead symlinks must be deleted cleanly"

    def test_circular_file_symlinks_cycle(self, challenge_env):
        """Tests circular file symlinks: link_1 -> link_2 and link_2 -> link_1."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        circ_profile = profiles_dir / "obsolete_circ_files"
        circ_profile.mkdir(parents=True, exist_ok=True)

        link_1 = circ_profile / "cycle_1"
        link_2 = circ_profile / "cycle_2"

        # Point to each other
        link_1.symlink_to(link_2)
        link_2.symlink_to(link_1)

        # Self-referential symlink: self -> self
        self_link = circ_profile / "self_referential"
        self_link.symlink_to(self_link)

        assert link_1.is_symlink()
        assert link_2.is_symlink()
        assert self_link.is_symlink()

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert not circ_profile.exists(), "Profile with circular file symlinks must be deleted without hang"

    def test_circular_directory_symlinks(self, challenge_env):
        """Tests circular directory symlinks: dir / loop -> dir, and sub_b / loop -> sub_a."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        circ_dir_profile = profiles_dir / "obsolete_circ_dirs"
        circ_dir_profile.mkdir(parents=True, exist_ok=True)

        dir_a = circ_dir_profile / "dir_a"
        dir_a.mkdir()
        (dir_a / "dummy.txt").write_text("Dummy content")

        # 1. Circular symlink to self directory
        loop_self = dir_a / "loop_self"
        loop_self.symlink_to(dir_a)

        # 2. Multi-hop directory loop: sub_a / to_b -> sub_b and sub_b / to_a -> sub_a
        sub_a = circ_dir_profile / "sub_a"
        sub_b = circ_dir_profile / "sub_b"
        sub_a.mkdir()
        sub_b.mkdir()

        (sub_a / "to_b").symlink_to(sub_b)
        (sub_b / "to_a").symlink_to(sub_a)

        # 3. Directory symlink pointing to parent profile root
        (circ_dir_profile / "dir_a" / "to_parent").symlink_to(circ_dir_profile)

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert not circ_dir_profile.exists(), "Profile with circular directory symlinks must be deleted cleanly"

    def test_deep_nested_broken_symlinks(self, challenge_env):
        """Tests deeply nested directory hierarchy (12 levels) containing broken and circular symlinks."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        deep_profile = profiles_dir / "obsolete_deep_nested"
        curr = deep_profile
        for i in range(12):
            curr = curr / f"level_{i:02d}"
            curr.mkdir(parents=True, exist_ok=True)
            (curr / f"data_{i}.txt").write_text(f"Level {i} data")

            # Add dead symlink at each level
            dead = curr / f"dead_symlink_{i}"
            dead.symlink_to(f"/nonexistent/deep/target/{i}")

            # Add circular symlink at every 3rd level
            if i % 3 == 0 and i > 0:
                cycle = curr / f"cycle_{i}"
                cycle.symlink_to(curr)

        assert deep_profile.exists()

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert not deep_profile.exists(), "Deeply nested profile with broken symlinks must be pruned"

    def test_outside_symlink_preservation_zero_blast_radius(self, challenge_env, tmp_path: Path):
        """
        Adversarial test: profile contains symlinks pointing to external critical directories and files.
        Pruning obsolete profile MUST unlink the symlink node ONLY and NEVER delete or modify
        the external targets.
        """
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        # External critical directory and files
        external_dir = tmp_path / "critical_external_data"
        external_dir.mkdir(parents=True, exist_ok=True)
        secret_file = external_dir / "secret_passwords.kdbx"
        secret_file.write_bytes(b"CRITICAL_SYSTEM_VAULT" * 100)

        # Profile with symlinks targeting the external dir and file
        exploit_profile = profiles_dir / "obsolete_exploit_profile"
        exploit_profile.mkdir(parents=True, exist_ok=True)

        symlink_to_ext_dir = exploit_profile / "symlink_dir"
        symlink_to_ext_dir.symlink_to(external_dir)

        symlink_to_ext_file = exploit_profile / "symlink_file"
        symlink_to_ext_file.symlink_to(secret_file)

        assert symlink_to_ext_dir.exists()
        assert symlink_to_ext_file.exists()

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        # Obsolete profile must be deleted
        assert not exploit_profile.exists()

        # External data MUST BE 100% PRESERVED
        assert external_dir.exists(), "External directory must NOT be deleted by symlink unlinking!"
        assert secret_file.exists(), "External file must NOT be touched or deleted!"
        assert secret_file.read_bytes() == b"CRITICAL_SYSTEM_VAULT" * 100

    def test_stale_singletonlock_with_dead_symlinks_in_profile(self, challenge_env):
        """Profile with a stale Chromium SingletonLock (format: vps-pid with dead pid) and broken symlinks."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        stale_profile = profiles_dir / "obsolete_stale_singleton"
        stale_profile.mkdir(parents=True, exist_ok=True)
        (stale_profile / "cache.bin").write_bytes(b"CACHE" * 100)

        # Stale Chromium lock symlink with dead pid
        lock = stale_profile / "SingletonLock"
        lock.symlink_to("toolsauto-vps-9999998")

        # Broken symlinks inside
        (stale_profile / "broken.lnk").symlink_to("/nowhere")

        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=False,
        )

        assert not stale_profile.exists(), "Profile with stale SingletonLock and broken symlinks must be deleted"

    def test_quarantine_mode_with_broken_and_circular_symlinks(self, challenge_env):
        """Tests that quarantine=True safely moves directories containing broken/circular symlinks."""
        profiles_dir = challenge_env["profiles_dir"]
        quarantine_root = challenge_env["quarantine_root"]
        service = challenge_env["service"]

        q_profile = profiles_dir / "obsolete_quarantine_links"
        q_profile.mkdir(parents=True, exist_ok=True)
        (q_profile / "data.txt").write_text("Quarantine data")

        broken = q_profile / "broken_link"
        broken.symlink_to("/path/does/not/exist")

        loop = q_profile / "loop"
        loop.symlink_to(q_profile)

        # Prune with quarantine=True
        service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=True,
            dry_run=False,
        )

        assert not q_profile.exists()
        assert (quarantine_root / "obsolete_quarantine_links").exists()
        assert (quarantine_root / "obsolete_quarantine_links" / "broken_link").is_symlink()

    def test_dry_run_with_broken_and_circular_symlinks(self, challenge_env):
        """Tests that dry_run=True computes size without modifying files or crashing on circular symlinks."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        dry_profile = profiles_dir / "obsolete_dry_run_links"
        dry_profile.mkdir(parents=True, exist_ok=True)
        f_real = dry_profile / "real_file.bin"
        f_real.write_bytes(b"DATA" * 1024)

        # Broken and circular symlinks
        (dry_profile / "broken").symlink_to("/does/not/exist")
        (dry_profile / "loop").symlink_to(dry_profile)

        reclaimed = service.prune_obsolete_profiles(
            active_profile_names=set(),
            quarantine=False,
            dry_run=True,
        )

        assert reclaimed == 4096  # Only real file counted, symlinks safely skipped
        assert dry_profile.exists()
        assert f_real.exists()

    def test_idempotent_multiple_runs_on_broken_symlinks(self, challenge_env):
        """Tests running prune_obsolete_profiles consecutively multiple times."""
        profiles_dir = challenge_env["profiles_dir"]
        service = challenge_env["service"]

        p = profiles_dir / "obsolete_multi_run"
        p.mkdir(parents=True, exist_ok=True)
        (p / "broken").symlink_to("/nowhere")

        # First run deletes
        service.prune_obsolete_profiles(active_profile_names=set(), quarantine=False)
        assert not p.exists()

        # Second run should be a clean no-op
        r2 = service.prune_obsolete_profiles(active_profile_names=set(), quarantine=False)
        assert r2 == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dynamic DB Accounts Protection in _get_active_profile_names()
# ═══════════════════════════════════════════════════════════════════════════

class TestDynamicDBAccountsProtectionAdversarial:
    def test_dynamic_accounts_mock_db_coverage(self, challenge_env):
        """
        Adversarial test: DB contains accounts with non-hardcoded IDs, diverse platforms,
        custom profile paths, and inactive status (is_active=False).
        All must be 100% shielded from deletion and quarantine.
        """
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        # Synthetic dynamic DB accounts
        mock_accounts = [
            # (profile_path, id, platform)
            (None, 500, "tiktok"),
            (None, 9999, "threads"),
            (None, 1234567, "facebook"),
            (None, 8888, "instagram"),
            (None, 77777, "youtube"),
            (str(profiles_dir / "custom_brand_vip"), 101, "facebook"),
            (str(profiles_dir / "unconventional_folder_name"), 102, None),  # platform=None -> facebook
            (str(profiles_dir / "slash_ending_profile/"), 103, "facebook"),  # trailing slash
            (None, 303, ""),  # empty platform string
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = mock_accounts

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db
            names = service._get_active_profile_names()

            # 1. Verify standard static profiles exist
            assert "facebook_15" in names
            assert "facebook_20" in names
            assert "facebook_scanner" in names
            assert "common" in names

            # 2. Verify non-hardcoded dynamic account IDs
            assert "tiktok_500" in names
            assert "facebook_500" in names
            assert "threads_500" in names

            assert "threads_9999" in names
            assert "facebook_9999" in names

            assert "facebook_1234567" in names
            assert "threads_1234567" in names

            assert "instagram_8888" in names
            assert "facebook_8888" in names

            assert "youtube_77777" in names

            # 3. Verify custom profile path resolution
            assert "custom_brand_vip" in names
            assert "unconventional_folder_name" in names
            assert "slash_ending_profile" in names

            # 4. Empty platform handling
            assert "facebook_303" in names

    def test_dynamic_accounts_filesystem_protection_quarantine_false(self, challenge_env):
        """
        Empirically verifies that active profile directories belonging to dynamic DB accounts
        are strictly preserved when prune_obsolete_profiles(quarantine=False) runs,
        while obsolete profile directories are completely deleted.
        """
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        # Create directories for dynamic DB accounts
        dyn_p1 = profiles_dir / "facebook_9999"
        dyn_p1.mkdir(parents=True, exist_ok=True)
        (dyn_p1 / "session.json").write_text("CRITICAL_SESSION_9999")

        dyn_p2 = profiles_dir / "threads_500"
        dyn_p2.mkdir(parents=True, exist_ok=True)
        (dyn_p2 / "session.json").write_text("CRITICAL_SESSION_500")

        dyn_p3 = profiles_dir / "custom_brand_vip"
        dyn_p3.mkdir(parents=True, exist_ok=True)
        (dyn_p3 / "session.json").write_text("CRITICAL_SESSION_CUSTOM")

        # Create obsolete profile directories (NOT in DB)
        obs_p1 = profiles_dir / "gemini_bot"
        obs_p1.mkdir(parents=True, exist_ok=True)
        (obs_p1 / "junk.txt").write_text("DEAD_TEST_DATA_1")

        obs_p2 = profiles_dir / "gemini_test_uc"
        obs_p2.mkdir(parents=True, exist_ok=True)
        (obs_p2 / "junk.txt").write_text("DEAD_TEST_DATA_2")
        (obs_p2 / "broken_link").symlink_to("/nowhere")

        obs_p3 = profiles_dir / "unregistered_account_11111"
        obs_p3.mkdir(parents=True, exist_ok=True)
        (obs_p3 / "data.bin").write_bytes(b"DATA")

        # Mock DB returns the 3 dynamic accounts
        mock_accounts = [
            (None, 9999, "facebook"),
            (None, 500, "threads"),
            (str(dyn_p3), 101, "facebook"),
        ]
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = mock_accounts

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db
            service.prune_obsolete_profiles(quarantine=False, dry_run=False)

        # 1. Assert obsolete profiles are gone
        assert not obs_p1.exists(), "Obsolete profile gemini_bot must be deleted"
        assert not obs_p2.exists(), "Obsolete profile gemini_test_uc with broken link must be deleted"
        assert not obs_p3.exists(), "Obsolete unregistered profile must be deleted"

        # 2. Assert dynamic DB accounts are 100% PRESERVED
        assert dyn_p1.exists(), "Dynamic DB account facebook_9999 must NOT be deleted!"
        assert (dyn_p1 / "session.json").read_text() == "CRITICAL_SESSION_9999"

        assert dyn_p2.exists(), "Dynamic DB account threads_500 must NOT be deleted!"
        assert (dyn_p2 / "session.json").read_text() == "CRITICAL_SESSION_500"

        assert dyn_p3.exists(), "Dynamic DB account custom_brand_vip must NOT be deleted!"
        assert (dyn_p3 / "session.json").read_text() == "CRITICAL_SESSION_CUSTOM"

    def test_dynamic_accounts_inactive_accounts_protected(self, challenge_env):
        """
        Verifies that even if an account has is_active=False in the database,
        its profile is still protected so login sessions are not destroyed.
        """
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        inactive_dir = profiles_dir / "facebook_700"
        inactive_dir.mkdir(parents=True, exist_ok=True)
        (inactive_dir / "session.json").write_text("INACTIVE_ACCOUNT_SESSION")

        # Mock DB returns account with id=700 (is_active would be false in DB, but query selects profile_path, id, platform)
        mock_accounts = [
            (None, 700, "facebook"),
        ]
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = mock_accounts

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db
            service.prune_obsolete_profiles(quarantine=False, dry_run=False)

        assert inactive_dir.exists(), "Inactive account facebook_700 must be protected from deletion"

    def test_live_sqlite_database_account_retrieval(self, challenge_env):
        """
        Direct integration with SQLite database:
        Inserts temporary Account records into database, verifies _get_active_profile_names()
        retrieves them live via SQLAlchemy session without any mocking.
        """
        service = challenge_env["service"]

        # Ensure Account table exists in engine
        Base.metadata.create_all(bind=engine)

        test_acc_id_1 = 98765
        test_acc_id_2 = 98766

        with SessionLocal() as db:
            # Clean up if already exists
            db.query(Account).filter(Account.id.in_([test_acc_id_1, test_acc_id_2])).delete(synchronize_session=False)
            db.commit()

            acc1 = Account(
                id=test_acc_id_1,
                name=f"challenger_test_{test_acc_id_1}",
                platform="facebook",
                profile_path=f"/home/vu/toolsauto/storage/profiles/facebook_{test_acc_id_1}",
                is_active=True,
            )
            acc2 = Account(
                id=test_acc_id_2,
                name=f"challenger_test_{test_acc_id_2}",
                platform="threads",
                profile_path="/custom/path/to/challenger_threads_custom",
                is_active=False,
            )
            db.add_all([acc1, acc2])
            db.commit()

        try:
            # Query active profile names LIVE without mock
            names = service._get_active_profile_names()

            assert f"facebook_{test_acc_id_1}" in names
            assert f"threads_{test_acc_id_1}" in names

            assert f"threads_{test_acc_id_2}" in names
            assert f"facebook_{test_acc_id_2}" in names
            assert "challenger_threads_custom" in names

        finally:
            # Cleanup test records
            with SessionLocal() as db:
                db.query(Account).filter(Account.id.in_([test_acc_id_1, test_acc_id_2])).delete(synchronize_session=False)
                db.commit()

    def test_dynamic_accounts_audit_and_run_all_integration(self, challenge_env):
        """
        Verifies that StorageCleanupService.audit() and run_all()
        properly protect dynamic DB accounts and correctly count only obsolete profiles.
        """
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        # Dynamic account profile
        dyn_p = profiles_dir / "facebook_7777"
        dyn_p.mkdir(parents=True, exist_ok=True)
        (dyn_p / "data.bin").write_bytes(b"DYNAMIC_DATA" * 1024)

        # Obsolete profile
        obs_p = profiles_dir / "obsolete_gemini_scratch"
        obs_p.mkdir(parents=True, exist_ok=True)
        (obs_p / "junk.bin").write_bytes(b"OBSOLETE_DATA" * 1024)

        mock_accounts = [(None, 7777, "facebook")]
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = mock_accounts

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db

            # 1. audit()
            audit_res = service.audit()
            assert "reclaimable_bytes" in audit_res

            # 2. run_all(include_obsolete=True, quarantine=False)
            res: StorageCleanupResult = service.run_all(
                dry_run=False,
                include_obsolete=True,
                quarantine=False,
            )

            assert dyn_p.exists(), "Dynamic DB account profile must remain intact after run_all"
            assert not obs_p.exists(), "Obsolete profile must be deleted after run_all"
            assert len(res.errors) == 0, f"Unexpected errors during run_all: {res.errors}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Massive Scale Adversarial Stress Harness
# ═══════════════════════════════════════════════════════════════════════════

class TestMassiveScaleStressHarness:
    def test_massive_scale_100_dynamic_accounts_and_100_obsolete_profiles(self, challenge_env):
        """
        Stress harness:
        - 100 dynamic active DB accounts with profile directories.
        - 100 obsolete profile directories, each populated with:
          * 5-10 dead symlinks
          * Circular directory and file symlinks
          * Deeply nested subfolders
          * Stale SingletonLock symlinks
        - Measure execution time (< 15 seconds) and verify 100% preservation & 100% cleanup.
        """
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        # 1. Create 100 dynamic DB accounts
        mock_accounts = []
        dyn_dirs = []
        for i in range(1, 101):
            acc_id = 10000 + i
            platform = "facebook" if i % 2 == 0 else "threads"
            p_name = f"{platform}_{acc_id}"
            p_dir = profiles_dir / p_name
            p_dir.mkdir(parents=True, exist_ok=True)
            (p_dir / "session.cookie").write_text(f"COOKIE_FOR_{acc_id}")
            dyn_dirs.append(p_dir)
            mock_accounts.append((str(p_dir), acc_id, platform))

        # 2. Create 100 obsolete profiles with complex symlink graphs
        obs_dirs = []
        for j in range(1, 101):
            obs_name = f"obsolete_profile_stress_{j:03d}"
            obs_dir = profiles_dir / obs_name
            obs_dir.mkdir(parents=True, exist_ok=True)
            obs_dirs.append(obs_dir)

            # Add real file
            (obs_dir / "cache.bin").write_bytes(b"STRESS_DATA" * 50)

            # Add stale SingletonLock
            lock = obs_dir / "SingletonLock"
            lock.symlink_to(f"vps-dead-{800000 + j}")

            # Add 5 dead symlinks
            for k in range(5):
                dead_lnk = obs_dir / f"dead_{k}.lnk"
                dead_lnk.symlink_to(f"/dev/null/nonexistent_{j}_{k}")

            # Add circular file symlink pair
            c1 = obs_dir / "cycle_a"
            c2 = obs_dir / "cycle_b"
            c1.symlink_to(c2)
            c2.symlink_to(c1)

            # Add nested directory with directory loop
            nested = obs_dir / "sub_deep" / "level2"
            nested.mkdir(parents=True, exist_ok=True)
            dir_loop = nested / "dir_loop"
            dir_loop.symlink_to(obs_dir)

        assert len(dyn_dirs) == 100
        assert len(obs_dirs) == 100

        # Execute prune_obsolete_profiles(quarantine=False)
        cleanup_start = time.time()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = mock_accounts

        with patch("app.core.database.core.SessionLocal") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_db
            reclaimed = service.prune_obsolete_profiles(quarantine=False, dry_run=False)

        cleanup_duration = time.time() - cleanup_start

        # Performance assertion: 100 complex directories pruned within 15 seconds
        assert cleanup_duration < 15.0, f"Pruning took too long: {cleanup_duration:.2f}s"

        # Verification: All 100 dynamic accounts PRESERVED
        for p_dir in dyn_dirs:
            assert p_dir.exists(), f"Dynamic account directory {p_dir.name} was erroneously deleted!"
            assert (p_dir / "session.cookie").exists(), f"Session in {p_dir.name} was lost!"

        # Verification: All 100 obsolete profiles DELETED
        for obs_dir in obs_dirs:
            assert not obs_dir.exists(), f"Obsolete profile {obs_dir.name} was not deleted!"

        assert reclaimed > 0

    def test_special_characters_and_relative_symlinks(self, challenge_env):
        """Tests handling of symlinks with spaces, unicode characters, and relative paths."""
        service = challenge_env["service"]
        profiles_dir = challenge_env["profiles_dir"]

        special_profile = profiles_dir / "obsolete_special_names"
        special_profile.mkdir(parents=True, exist_ok=True)

        # 1. Space in symlink name
        s1 = special_profile / "broken link with space.txt"
        s1.symlink_to("/nonexistent/file with spaces.txt")

        # 2. Unicode in symlink name and target
        s2 = special_profile / "liên_kết_hỏng_🔥.dat"
        s2.symlink_to("/tmp/đường_dẫn_không_tồn_tại_❌")

        # 3. Relative path symlink escaping outside
        s3 = special_profile / "relative_dead"
        s3.symlink_to("../../some/relative/nonexistent/path")

        assert s1.is_symlink()
        assert s2.is_symlink()
        assert s3.is_symlink()

        service.prune_obsolete_profiles(active_profile_names=set(), quarantine=False)

        assert not special_profile.exists(), "Profile with special character symlinks must be deleted"
