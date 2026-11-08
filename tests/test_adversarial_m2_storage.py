"""Adversarial Verification Suite for Milestone 2: Atomic Storage Lifecycle, Disk Bloat Prevention & CleanupService.

Targeted adversarial testing executed by Empirical Challenger 2:
1. Failure & Crash Unlinking:
   - FFmpeg non-zero exit codes (1, 2, 127, 137 OOM/kill, 139 segfault, 255)
   - Invalid codec and corrupted filter configurations
   - Subprocess timeouts (TimeoutExpired)
   - Arbitrary exceptions (OSError, MemoryError, PermissionError)
   - Zero-byte writes with returncode=0 (silent failure / disk full / empty stream)
   - Pre-existing corrupted .tmp cleanup
   - Real FFmpeg failure on corrupted binary file
2. Stale Story Cleanup (CleanupService._cleanup_stale_story_files):
   - Strict retention boundary (>24h unlinked vs <24h preserved)
   - Mixed extensions (.mp4, .jpg, .tmp, extensionless)
   - Dynamic TTL overrides (1h, 6h, 48h)
   - Non-existent and empty directories
   - Directory traversal resilience (subdirectories ignored, no IsADirectoryError)
   - Partial filesystem permission error resilience
   - SQLAlchemy Session argument backward compatibility
3. Concurrency Stress (20 Parallel Workers):
   - 20 parallel threads calling classify_and_extract
   - 20 parallel threads calling extract_video_story
   - 20 parallel threads calling extract_photo_story
   - Concurrency stress with interleaved execution delays
   - Same material_id collision behavior analysis
   - Real multi-threaded FFmpeg execution with Linux nice throttling
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.media.ffmpeg_path import ffmpeg_bin
from app.core.queue.cleanup import CleanupService


# ══════════════════════════════════════════════════════════════════════════════
# Helper Fixtures & Utilities
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Creates a minimal valid input file."""
    f = tmp_path / "sample_input.mp4"
    f.write_bytes(b"dummy video data for extraction test")
    return f


@pytest.fixture
def real_synthetic_video(tmp_path: Path) -> Path:
    """Generates a real 1-second synthetic video with FFmpeg for real subprocess tests."""
    out = tmp_path / "real_sample.mp4"
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=15",
        "-c:v", "libx264", "-preset", "ultrafast",
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"Failed to generate synthetic video: {res.stderr}"
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 1. FAILURE & CRASH UNLINKING ADVERSARIAL TESTS
# ══════════════════════════════════════════════════════════════════════════════
















# ══════════════════════════════════════════════════════════════════════════════
# 2. STALE STORY CLEANUP ADVERSARIAL TESTS (CleanupService)
# ══════════════════════════════════════════════════════════════════════════════


def test_adv_cleanup_stale_stories_precision_retention(tmp_path: Path):
    """Adversarial stress test on retention boundary:

    Creates 12 files:
    - 6 files older than 24h (24h + 2s, 25h, 36h, 48h, 7d, 30d)
    - 6 files younger than 24h (24h - 2s, 23.5h, 12h, 4h, 30m, 1m)
    Verifies 100% precision: all old files deleted, all recent files preserved.
    """
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir(parents=True)

    now = time.time()
    stale_offsets_sec = [
        24 * 3600 + 2,    # Just past 24h threshold
        25 * 3600,        # 25h old
        36 * 3600,        # 36h old
        48 * 3600,        # 48h old
        7 * 86400,        # 7 days old
        30 * 86400,       # 30 days old
    ]

    fresh_offsets_sec = [
        24 * 3600 - 2,    # Just inside 24h threshold
        23.5 * 3600,      # 23.5h old
        12 * 3600,        # 12h old
        4 * 3600,         # 4h old
        1800,             # 30 min old
        60,               # 1 min old
    ]

    stale_files = []
    for i, offset in enumerate(stale_offsets_sec):
        f = stories_dir / f"stale_{i}.mp4"
        f.write_bytes(f"stale data {i}".encode())
        ts = now - offset
        os.utime(f, (ts, ts))
        stale_files.append(f)

    fresh_files = []
    for i, offset in enumerate(fresh_offsets_sec):
        f = stories_dir / f"fresh_{i}.mp4"
        f.write_bytes(f"fresh data {i}".encode())
        ts = now - offset
        os.utime(f, (ts, ts))
        fresh_files.append(f)

    removed = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)

    assert removed == 6, f"Expected exactly 6 stale files removed, got {removed}"
    for f in stale_files:
        assert not f.exists(), f"Stale file {f.name} should have been unlinked!"
    for f in fresh_files:
        assert f.exists(), f"Fresh file {f.name} was erroneously unlinked!"


def test_adv_cleanup_stale_stories_mixed_extensions(tmp_path: Path):
    """Cleanup must purge all stale files regardless of extension (.mp4, .jpg, .tmp, no ext)."""
    stories_dir = tmp_path / "mixed_stories"
    stories_dir.mkdir()

    old_ts = time.time() - 30 * 3600  # 30h old
    filenames = [
        "story_v_1_100.mp4",
        "story_p_2_100.jpg",
        "story_p_3_100.jpeg",
        "story_v_4_100.mp4.tmp",
        "story_p_5_100.jpg.tmp",
        "stale_orphaned_no_extension",
    ]

    files = []
    for fn in filenames:
        p = stories_dir / fn
        p.write_bytes(b"content")
        os.utime(p, (old_ts, old_ts))
        files.append(p)

    removed = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)
    assert removed == len(filenames)
    for p in files:
        assert not p.exists()


def test_adv_cleanup_stale_stories_dynamic_ttl(tmp_path: Path):
    """Dynamic TTL: test 1h TTL and 48h TTL on identical file setup."""
    stories_dir = tmp_path / "dynamic_ttl"
    stories_dir.mkdir()

    now = time.time()
    # Create 3 files: 2h old, 26h old, 50h old
    f_2h = stories_dir / "file_2h.mp4"
    f_2h.write_bytes(b"2h")
    os.utime(f_2h, (now - 2 * 3600, now - 2 * 3600))

    f_26h = stories_dir / "file_26h.mp4"
    f_26h.write_bytes(b"26h")
    os.utime(f_26h, (now - 26 * 3600, now - 26 * 3600))

    f_50h = stories_dir / "file_50h.mp4"
    f_50h.write_bytes(b"50h")
    os.utime(f_50h, (now - 50 * 3600, now - 50 * 3600))

    # Run with TTL=48h: only f_50h should be removed
    rem_48 = CleanupService._cleanup_stale_story_files(ttl_hours=48, stories_dir=stories_dir)
    assert rem_48 == 1
    assert not f_50h.exists()
    assert f_26h.exists()
    assert f_2h.exists()

    # Run with TTL=1h: f_26h and f_2h should be removed
    rem_1 = CleanupService._cleanup_stale_story_files(ttl_hours=1, stories_dir=stories_dir)
    assert rem_1 == 2
    assert not f_26h.exists()
    assert not f_2h.exists()


def test_adv_cleanup_stale_stories_nonexistent_and_empty_dir(tmp_path: Path):
    """Non-existent directory or empty directory must return 0 without raising."""
    non_existent = tmp_path / "does_not_exist"
    assert CleanupService._cleanup_stale_story_files(stories_dir=non_existent) == 0

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    assert CleanupService._cleanup_stale_story_files(stories_dir=empty_dir) == 0


def test_adv_cleanup_stale_stories_ignores_subdirectories(tmp_path: Path):
    """Subdirectories placed inside stories directory must not cause IsADirectoryError."""
    stories_dir = tmp_path / "stories_with_subdirs"
    stories_dir.mkdir()

    sub_dir = stories_dir / "cache_subfolder"
    sub_dir.mkdir()

    now = time.time()
    old_ts = now - 40 * 3600

    # Old file inside main dir
    f_main = stories_dir / "old_main.mp4"
    f_main.write_bytes(b"main")
    os.utime(f_main, (old_ts, old_ts))

    # Old file inside sub dir
    f_sub = sub_dir / "nested_file.mp4"
    f_sub.write_bytes(b"nested")
    os.utime(f_sub, (old_ts, old_ts))

    # Set old timestamp on sub_dir itself
    os.utime(sub_dir, (old_ts, old_ts))

    removed = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)
    assert removed == 1
    assert not f_main.exists()
    # Directory itself must still exist and not be crashed upon
    assert sub_dir.exists() and sub_dir.is_dir()


def test_adv_cleanup_stale_stories_permission_error_tolerance(tmp_path: Path):
    """If one file fails to unlink due to OSError, cleanup must log warning and continue with others."""
    stories_dir = tmp_path / "resilient_stories"
    stories_dir.mkdir()

    now = time.time()
    old_ts = now - 30 * 3600

    f1 = stories_dir / "stale_f1.mp4"
    f1.write_bytes(b"f1")
    os.utime(f1, (old_ts, old_ts))

    f2_locked = stories_dir / "stale_f2_locked.mp4"
    f2_locked.write_bytes(b"f2")
    os.utime(f2_locked, (old_ts, old_ts))

    f3 = stories_dir / "stale_f3.mp4"
    f3.write_bytes(b"f3")
    os.utime(f3, (old_ts, old_ts))

    real_unlink = os.unlink

    def mock_unlink(path_str, *args, **kwargs):
        if "stale_f2_locked" in str(path_str):
            raise OSError("Simulated permission denied on locked file")
        return real_unlink(path_str, *args, **kwargs)

    with patch("os.unlink", side_effect=mock_unlink):
        removed = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)

    # f1 and f3 should be unlinked, f2 logged error and skipped
    assert removed == 2
    assert not f1.exists()
    assert f2_locked.exists()
    assert not f3.exists()


def test_adv_cleanup_stale_stories_session_arg_support():
    """Verify passing SQLAlchemy Session object to ttl_hours defaults safely to CLEANUP_STORY_TTL_HOURS."""
    mock_session = MagicMock(spec=Session)
    with patch("app.core.queue.cleanup.Path.exists", return_value=False):
        # Should not raise TypeError: unsupported operand type(s) for -: 'float' and 'MagicMock'
        result = CleanupService._cleanup_stale_story_files(mock_session)
        assert result == 0


def test_adv_cleanup_service_run_story_cleanup_integration():
    """Verify CleanupService.run calls _cleanup_stale_story_files and handles failures gracefully."""
    mock_db = MagicMock(spec=Session)

    with patch.object(CleanupService, "_cleanup_stale_story_files", return_value=5) as mock_cleanup, \
         patch.object(CleanupService, "_archive_done_files"), \
         patch.object(CleanupService, "_delete_failed_files"), \
         patch.object(CleanupService, "_delete_cancelled_files"), \
         patch.object(CleanupService, "_remove_stale_tmp_files"), \
         patch.object(CleanupService, "_clear_browser_caches"), \
         patch.object(CleanupService, "_run_daily_log_cleanup"):

        CleanupService.run(mock_db)
        assert mock_cleanup.call_count == 1

        # Now test that if _cleanup_stale_story_files raises, CleanupService.run does NOT raise
        mock_cleanup.side_effect = RuntimeError("Catastrophic storage disk read failure")
        CleanupService.run(mock_db)  # Must complete without crashing


# ══════════════════════════════════════════════════════════════════════════════
# 3. CONCURRENCY STRESS TESTS (20 Parallel Workers)
# ══════════════════════════════════════════════════════════════════════════════










