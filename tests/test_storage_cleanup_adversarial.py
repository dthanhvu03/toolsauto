"""
test_storage_cleanup_adversarial.py — Empirical Challenger Stress Test Suite.

Adversarially challenges Milestone 1 features:
1. `prune_media`:
   - Boundary retention periods: negative values (-1, -0.5), zero days (0), fractional days (0.5, 3.25, 7.5).
   - Active jobs shielding: PENDING, RUNNING, AI_PROCESSING, DRAFT, AWAITING_STYLE must NEVER be pruned.
   - Future mtime files: files with future timestamps (tomorrow, year 2038) must NEVER be pruned.
   - Stale files with no active job: properly deleted, status updated.
   - Non-media files and directories preservation.
2. `prune_logs_and_backups`:
   - Corrupted `.sql` files: 0-byte dumps, arbitrary non-UTF8/binary junk, malformed headers.
   - Streaming gzip compression: memory efficiency and round-trip verification (`gzip.decompress(data) == original`).
   - Mtime preservation on compressed `.sql.gz`.
   - 7 daily snapshot retention logic: multi-day rotation, intraday duplicate pruning, protection of current day's snapshots.
   - Temporary file handling (.tmp.gz / .tmp.sql cleanup).
3. Typer CLI commands (`manage.py`):
   - `storage audit` output, error isolation, exit code.
   - `storage cleanup --dry-run` invariance (zero files deleted, dry-run reported).
   - CLI parameter validation (negative retention, custom retention periods, purge-obsolete flag).
"""
from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.constants import JobStatus, ViralStatus
from app.features.maintenance.storage_cleanup_service import (
    SessionIntegrityViolationError,
    StorageCleanupResult,
    StorageCleanupService,
)
from manage import app as cli_app


@pytest.fixture
def adv_env(tmp_path: Path):
    """Provides a fresh isolated storage tree with media, profiles, logs, and backups."""
    storage_root = tmp_path / "storage"
    logs_root = tmp_path / "logs"
    quarantine_root = tmp_path / "quarantine"

    storage_root.mkdir(parents=True, exist_ok=True)
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
        "service": service,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. ADVERSARIAL MEDIA PRUNING TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialMediaPruning:
    """Stress-tests prune_media against boundaries, active jobs, and temporal anomalies."""

    @pytest.mark.parametrize("invalid_retention", [-1, -0.01, -100])
    def test_negative_retention_days_raises_value_error(self, adv_env, invalid_retention):
        svc: StorageCleanupService = adv_env["service"]
        with pytest.raises(ValueError, match="retention_days must be >= 0"):
            svc.prune_media(retention_days=invalid_retention)

    def test_zero_retention_days_pruning(self, adv_env):
        """retention_days=0 should prune any file older than current time, but NOT future mtime."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        # File from 5 seconds ago
        past_file = media_dir / "viral_10_past.mp4"
        past_file.write_bytes(b"PAST_MEDIA_BYTES" * 100)
        os.utime(past_file, (now - 5, now - 5))

        # File with future mtime (1 hour in future)
        future_file = media_dir / "viral_11_future.mp4"
        future_file.write_bytes(b"FUTURE_MEDIA_BYTES" * 100)
        os.utime(future_file, (now + 3600, now + 3600))

        reclaimed = svc.prune_media(retention_days=0, dry_run=False)

        assert reclaimed == len(b"PAST_MEDIA_BYTES" * 100)
        assert not past_file.exists(), "Past file should be pruned when retention_days=0"
        assert future_file.exists(), "Future mtime file must NEVER be pruned"

    def test_fractional_retention_days(self, adv_env):
        """Verify fractional retention (e.g. 0.5 days = 12 hours)."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        # File older than 12 hours (14 hours old)
        stale_file = media_dir / "viral_20_14h.mp4"
        stale_file.write_bytes(b"STALE_14H" * 100)
        os.utime(stale_file, (now - 14 * 3600, now - 14 * 3600))

        # File younger than 12 hours (10 hours old)
        fresh_file = media_dir / "viral_21_10h.mp4"
        fresh_file.write_bytes(b"FRESH_10H" * 100)
        os.utime(fresh_file, (now - 10 * 3600, now - 10 * 3600))

        reclaimed = svc.prune_media(retention_days=0.5, dry_run=False)

        assert reclaimed == len(b"STALE_14H" * 100)
        assert not stale_file.exists(), "14-hour old file must be pruned with 0.5-day retention"
        assert fresh_file.exists(), "10-hour old file must be kept with 0.5-day retention"

    def test_future_mtime_files_survive_all_retention_thresholds(self, adv_env):
        """Files with clock skew or future mtime must never be pruned."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "facebook"
        media_dir.mkdir(parents=True, exist_ok=True)

        # Tomorrow mtime
        tomorrow_file = media_dir / "viral_30_tomorrow.mp4"
        tomorrow_file.write_bytes(b"TOMORROW" * 100)
        os.utime(tomorrow_file, (now + 86400, now + 86400))

        # Far future mtime (year 2038 / 2099)
        far_future_file = media_dir / "viral_31_far_future.mp4"
        far_future_file.write_bytes(b"FAR_FUTURE" * 100)
        os.utime(far_future_file, (now + 365 * 86400 * 5, now + 365 * 86400 * 5))

        svc.prune_media(retention_days=7, dry_run=False)

        assert tomorrow_file.exists()
        assert far_future_file.exists()

    @pytest.mark.parametrize("status", [
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.AI_PROCESSING,
        JobStatus.DRAFT,
        JobStatus.AWAITING_STYLE,
    ])
    def test_active_jobs_shield_stale_media_from_pruning(self, adv_env, status):
        """Active jobs in any active status must NEVER have their media files deleted."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        # File is 60 days old — would normally be pruned
        stale_file = media_dir / f"viral_active_{status.value}.mp4"
        stale_file.write_bytes(b"ACTIVE_JOB_MEDIA" * 100)
        os.utime(stale_file, (now - 60 * 86400, now - 60 * 86400))

        # Mock DB querying active jobs to return this path
        norm_target = os.path.normpath(str(stale_file)).lower()
        with patch.object(svc, "_get_active_job_media_paths", return_value={norm_target}):
            reclaimed = svc.prune_media(retention_days=7, dry_run=False)

            assert reclaimed == 0
            assert stale_file.exists(), f"File protected by active status {status} must NOT be pruned"

    def test_completed_or_failed_jobs_do_not_shield_stale_media(self, adv_env):
        """Only ACTIVE jobs shield files; COMPLETED, FAILED, CANCELLED do not shield."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        stale_file = media_dir / "viral_inactive_done.mp4"
        stale_file.write_bytes(b"INACTIVE_DONE_MEDIA" * 100)
        os.utime(stale_file, (now - 30 * 86400, now - 30 * 86400))

        # Empty active set (because job is DONE or FAILED)
        with patch.object(svc, "_get_active_job_media_paths", return_value=set()):
            reclaimed = svc.prune_media(retention_days=7, dry_run=False)

            assert reclaimed > 0
            assert not stale_file.exists(), "File associated with non-active job must be pruned"

    def test_active_job_path_normalization_and_case_insensitivity(self, adv_env):
        """Path comparison must be immune to trailing slashes, ./, and case variations."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        file_path = media_dir / "VIRAL_MIXED_Case.MP4"
        file_path.write_bytes(b"MIXED_CASE_MEDIA" * 100)
        os.utime(file_path, (now - 30 * 86400, now - 30 * 86400))

        # Active path supplied with redundant ./ and ../ references and uppercase extension
        redundant_active_path = f"{file_path.parent}/../tiktok/./VIRAL_MIXED_Case.MP4"
        normalized_active = os.path.normpath(redundant_active_path).lower()

        with patch.object(svc, "_get_active_job_media_paths", return_value={normalized_active}):
            reclaimed = svc.prune_media(retention_days=7, dry_run=False)
            assert reclaimed == 0
            assert file_path.exists()

    def test_da_dang_posted_retention_days(self, adv_env):
        """Test posted_retention_days parameter for da-dang directory."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        da_dang = adv_env["storage_root"] / "media" / "reup" / "facebook" / "da-dang"
        da_dang.mkdir(parents=True, exist_ok=True)

        f_old_posted = da_dang / "old_posted.mp4"
        f_old_posted.write_bytes(b"OLD_POSTED" * 50)
        os.utime(f_old_posted, (now - 10 * 86400, now - 10 * 86400))

        f_recent_posted = da_dang / "recent_posted.mp4"
        f_recent_posted.write_bytes(b"RECENT_POSTED" * 50)
        os.utime(f_recent_posted, (now - 2 * 86400, now - 2 * 86400))

        # posted_retention_days=5: old should be deleted, recent kept
        svc.prune_media(retention_days=7, dry_run=False, posted_retention_days=5)

        assert not f_old_posted.exists()
        assert f_recent_posted.exists()

    def test_non_video_files_in_reup_preserved(self, adv_env):
        """Non-video files (e.g. metadata .json, .txt) must not be pruned by video pruner."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "tiktok"
        media_dir.mkdir(parents=True, exist_ok=True)

        meta_json = media_dir / "meta_config.json"
        meta_json.write_text('{"important": true}')
        os.utime(meta_json, (now - 30 * 86400, now - 30 * 86400))

        notes_txt = media_dir / "readme.txt"
        notes_txt.write_text("Do not delete")
        os.utime(notes_txt, (now - 30 * 86400, now - 30 * 86400))

        svc.prune_media(retention_days=7, dry_run=False)

        assert meta_json.exists(), "Metadata json must be preserved"
        assert notes_txt.exists(), "Readme txt must be preserved"


# ═══════════════════════════════════════════════════════════════════════════
# 2. ADVERSARIAL BACKUP & LOG PRUNING TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialLogsAndBackups:
    """Stress-tests prune_logs_and_backups on corrupted files, round-trip compression, and snapshot retention."""

    def test_corrupted_empty_sql_file_handling(self, adv_env):
        """0-byte .sql dump should compress into valid 0-byte payload gzip without crash."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        empty_sql = backups_dir / "toolsauto_db_20261019_000000.sql"
        empty_sql.write_bytes(b"")

        svc.prune_logs_and_backups(dry_run=False)

        gz_file = empty_sql.with_suffix(".sql.gz")
        assert gz_file.exists(), "0-byte SQL file should be converted to .sql.gz"
        assert not empty_sql.exists()

        # Decompress round-trip check
        with gzip.open(gz_file, "rb") as f:
            data = f.read()
            assert data == b"", "Decompressed 0-byte file must be empty bytes"

    def test_corrupted_binary_junk_sql_roundtrip(self, adv_env):
        """Arbitrary non-UTF8 binary noise in .sql must be compressed losslessly."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        # Generate 128KB of pseudo-random binary data (including invalid UTF8 sequences)
        junk_data = bytes((i * 37 + 13) % 256 for i in range(128 * 1024))
        junk_hash = hashlib.sha256(junk_data).hexdigest()

        corrupt_sql = backups_dir / "toolsauto_db_20261019_010000.sql"
        corrupt_sql.write_bytes(junk_data)

        svc.prune_logs_and_backups(dry_run=False)

        gz_file = corrupt_sql.with_suffix(".sql.gz")
        assert gz_file.exists()
        assert not corrupt_sql.exists()

        # Verify round-trip lossless decompression
        decompressed_data = gzip.decompress(gz_file.read_bytes())
        assert hashlib.sha256(decompressed_data).hexdigest() == junk_hash
        assert decompressed_data == junk_data

    def test_streaming_large_sql_compression_and_mtime_preservation(self, adv_env):
        """Large SQL dump (2MB+) streams properly, achieves compression, and preserves mtime."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        # 2MB of repetitive SQL inserts (highly compressible)
        large_sql_text = ("INSERT INTO viral_materials (id, title) VALUES (1, 'Video viral test');\n" * 30000).encode("utf-8")
        orig_hash = hashlib.sha256(large_sql_text).hexdigest()

        large_sql = backups_dir / "toolsauto_db_20261019_020000.sql"
        large_sql.write_bytes(large_sql_text)

        # Specific fixed timestamp 5 days ago
        fixed_mtime = time.time() - 5 * 86400
        os.utime(large_sql, (fixed_mtime, fixed_mtime))

        orig_size = large_sql.stat().st_size
        assert orig_size > 2 * 1024 * 1024

        reclaimed = svc.prune_logs_and_backups(dry_run=False)

        gz_file = large_sql.with_suffix(".sql.gz")
        assert gz_file.exists()
        assert not large_sql.exists()

        compressed_size = gz_file.stat().st_size
        assert compressed_size < orig_size * 0.1, "Repetitive SQL should compress by > 90%"
        assert reclaimed >= (orig_size - compressed_size)

        # Verify mtime preserved within 1 second
        gz_mtime = gz_file.stat().st_mtime
        assert abs(gz_mtime - fixed_mtime) < 2.0

        # Verify decompress round-trip
        decompressed = gzip.decompress(gz_file.read_bytes())
        assert hashlib.sha256(decompressed).hexdigest() == orig_hash

    def test_7_daily_snapshot_retention_and_intraday_deduplication(self, adv_env):
        """
        Adversarial multi-day scenario:
        - 10 distinct days: day 1 to day 10.
        - Days 1 to 3: older than 7 days -> must be completely pruned.
        - Days 4 to 9 (past 6 days): multiple snapshots per day -> only newest intraday snapshot kept.
        - Day 10 (today): multiple snapshots -> ALL of today's snapshots kept.
        """
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now()
        created_files: dict[str, list[Path]] = {}

        for days_ago in range(10):
            day_dt = today - timedelta(days=days_ago)
            d_str = day_dt.strftime("%Y%m%d")
            created_files[d_str] = []

            # Create 3 snapshots for each day
            for hour in ("030000", "120000", "210000"):
                f = backups_dir / f"toolsauto_db_{d_str}_{hour}.sql.gz"
                f.write_bytes(b"GZIP_MOCK_DATA" * 50)
                # Assign mtimes reflecting creation sequence
                h_int = int(hour[:2])
                mtime = (day_dt.replace(hour=h_int, minute=0, second=0)).timestamp()
                os.utime(f, (mtime, mtime))
                created_files[d_str].append(f)

        assert len(list(backups_dir.glob("*.sql.gz"))) == 30

        # Execute retention
        svc._retain_daily_backups(backups_dir, keep_days=7, dry_run=False)

        sorted_days = sorted(created_files.keys(), reverse=True)
        retained_days = set(sorted_days[:7])
        pruned_days = set(sorted_days[7:])

        # 1. Pruned days (days older than 7 days) must have 0 files left
        for d in pruned_days:
            for f in created_files[d]:
                assert not f.exists(), f"Older day {d} snapshot {f.name} should have been pruned"

        # 2. Retained historical days must retain only 1 file (the newest intraday snapshot)
        today_key = today.strftime("%Y%m%d")
        for d in retained_days:
            if d != today_key:
                surviving = [f for f in created_files[d] if f.exists()]
                assert len(surviving) == 1, f"Historical day {d} should retain exactly 1 newest snapshot, got {len(surviving)}"
                # Newest was 210000
                assert "210000" in surviving[0].name
            else:
                # 3. Today must retain all 3 snapshots
                surviving_today = [f for f in created_files[d] if f.exists()]
                assert len(surviving_today) == 3, f"Today {d} must retain all intraday snapshots"

    def test_tmp_sql_and_tmp_gz_handling(self, adv_env):
        """Temporary files like .tmp.sql or orphaned .tmp.gz should be cleaned up or ignored."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        tmp_sql = backups_dir / "dump_in_progress.tmp.sql"
        tmp_sql.write_bytes(b"INCOMPLETE_SQL")

        valid_sql = backups_dir / "toolsauto_db_20261019_040000.sql"
        valid_sql.write_bytes(b"VALID_SQL" * 100)

        svc.prune_logs_and_backups(dry_run=False)

        # .tmp.sql should NOT be compressed or renamed to .sql.gz
        assert tmp_sql.exists(), ".tmp.sql in progress must not be touched"
        assert not (backups_dir / "dump_in_progress.tmp.sql.gz").exists()
        assert (backups_dir / "toolsauto_db_20261019_040000.sql.gz").exists()

    def test_sql_compression_when_gz_already_exists(self, adv_env):
        """If target .sql.gz already exists, atomic replace should safely overwrite it without corruption."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        sql_file = backups_dir / "toolsauto_db_20261019_050000.sql"
        sql_file.write_bytes(b"NEW_CONTENT_TO_COMPRESS" * 100)

        existing_gz = backups_dir / "toolsauto_db_20261019_050000.sql.gz"
        with gzip.open(existing_gz, "wb") as f:
            f.write(b"OLD_STALE_CONTENT")

        svc.prune_logs_and_backups(dry_run=False)

        assert not sql_file.exists()
        assert existing_gz.exists()
        # Verify it now decompresses to the NEW content
        decompressed = gzip.decompress(existing_gz.read_bytes())
        assert decompressed == b"NEW_CONTENT_TO_COMPRESS" * 100

    def test_unreadable_sql_file_error_isolation(self, adv_env):
        """An unreadable SQL file (permission 000) must be logged and not crash the process."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        unreadable_sql = backups_dir / "toolsauto_db_20261019_060000.sql"
        unreadable_sql.write_bytes(b"SECRET_CANNOT_READ")

        with patch("builtins.open", side_effect=PermissionError("Mock Permission Denied")):
            # Should catch exception internally and not raise
            reclaimed = svc.prune_logs_and_backups(dry_run=False)
            assert isinstance(reclaimed, int)
            assert unreadable_sql.exists()

    def test_nonstandard_backup_filenames_in_retention(self, adv_env):
        """Backups without standard date formats fall back to mtime gracefully and prune past 7 daily snapshots."""
        svc: StorageCleanupService = adv_env["service"]
        backups_dir = adv_env["storage_root"] / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        now = time.time()
        # Create nonstandard backups across 9 different days
        created_legacy = []
        for d in range(9):
            legacy_file = backups_dir / f"custom_backup_day_{d}.sql.gz"
            legacy_file.write_bytes(f"LEGACY_{d}".encode())
            mtime = now - d * 86400
            os.utime(legacy_file, (mtime, mtime))
            created_legacy.append(legacy_file)

        # 9 days present. keep_days=7 should keep the 7 newest (days 0..6) and prune the oldest 2 (days 7, 8)
        svc._retain_daily_backups(backups_dir, keep_days=7, dry_run=False)

        for d in range(7):
            assert created_legacy[d].exists(), f"Day {d} should be retained among the 7 newest"

        assert not created_legacy[7].exists(), "Day 7 should be pruned as 8th day"
        assert not created_legacy[8].exists(), "Day 8 should be pruned as 9th day"

    def test_malformed_viral_material_filenames_in_prune_media(self, adv_env):
        """Files without standard viral_<id>_ prefix must not crash DB material update."""
        svc: StorageCleanupService = adv_env["service"]
        now = time.time()

        media_dir = adv_env["storage_root"] / "media" / "reup" / "facebook"
        media_dir.mkdir(parents=True, exist_ok=True)

        non_standard = media_dir / "random_video_name_no_id.mp4"
        non_standard.write_bytes(b"RAW_VIDEO" * 100)
        os.utime(non_standard, (now - 15 * 86400, now - 15 * 86400))

        reclaimed = svc.prune_media(retention_days=7, dry_run=False)
        assert reclaimed > 0
        assert not non_standard.exists()


# ═══════════════════════════════════════════════════════════════════════════
# 3. ADVERSARIAL TYPER CLI COMMANDS TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialStorageCLI:
    """Stress-tests manage.py storage CLI commands via CliRunner."""

    def test_cli_storage_audit_executes_cleanly(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "audit"])
        assert result.exit_code == 0
        assert "Auditing storage for reclaimable disk space (dry-run)..." in result.output
        assert "Total reclaimable:" in result.output
        assert "Media files:" in result.output
        assert "Profiles:" in result.output
        assert "Logs & Backups:" in result.output

    def test_cli_storage_audit_with_errors_encountered(self):
        """When StorageCleanupService.audit reports errors, CLI should display them with exit code 0."""
        runner = CliRunner()
        mock_audit_data = {
            "reclaimable_bytes": 1024,
            "media_files_count": 1,
            "profiles_count": 0,
            "logs_count": 0,
            "errors": ["Simulated disk read permission error"],
        }
        with patch("app.features.maintenance.storage_cleanup_service.StorageCleanupService.audit", return_value=mock_audit_data):
            result = runner.invoke(cli_app, ["storage", "audit"])
            assert result.exit_code == 0
            assert "Warnings/Errors encountered: 1" in result.output
            assert "Simulated disk read permission error" in result.output

    def test_cli_storage_cleanup_dry_run_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "cleanup", "--dry-run"])
        assert result.exit_code == 0
        assert "Starting storage cleanup [DRY-RUN]" in result.output
        assert "Cleanup completed" in result.output

    def test_cli_storage_cleanup_negative_retention_error_handling(self):
        """CLI passing negative retention should catch ValueError and report cleanly."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "cleanup", "--retention-days", "-3"])
        # Should report the error message in output
        assert "retention_days must be >= 0" in result.output or result.exit_code != 0

    def test_cli_storage_cleanup_all_flags_combination(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, [
            "storage", "cleanup",
            "--retention-days", "14",
            "--dry-run",
            "--purge-obsolete",
        ])
        assert result.exit_code == 0
        assert "retention_days=14" in result.output
        assert "purge_obsolete=True" in result.output
        assert "[DRY-RUN]" in result.output

    def test_cli_storage_help_page(self):
        runner = CliRunner()
        result = runner.invoke(cli_app, ["storage", "--help"])
        assert result.exit_code == 0
        assert "audit" in result.output
        assert "cleanup" in result.output

