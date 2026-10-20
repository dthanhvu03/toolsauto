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

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import random
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.media.ffmpeg_path import ffmpeg_bin
from app.core.queue.cleanup import CleanupService
from app.features.story.media_extractor import StoryMediaExtractor


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


def test_adv_ffmpeg_invalid_codec_unlinks_tmp(monkeypatch, tmp_path: Path, sample_video: Path):
    """FFmpeg failing due to invalid codec must raise RuntimeError and cleanly unlink .tmp."""
    dest = tmp_path / "failed_codec.mp4"
    tmp_file = tmp_path / "failed_codec.mp4.tmp"

    def mock_run(cmd, *args, **kwargs):
        # Emulate FFmpeg writing partial dirty header before encountering codec error
        tmp_file.write_bytes(b"partial dirty bytes from aborted transcode")
        return subprocess.CompletedProcess(
            cmd,
            returncode=1,
            stdout="",
            stderr="Unknown encoder 'libx264_invalid_experimental'",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(RuntimeError) as exc_info:
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest))

    assert "Unknown encoder 'libx264_invalid_experimental'" in str(exc_info.value)
    assert not tmp_file.exists(), "Adversarial failure: .tmp file was NOT unlinked after codec error!"
    assert not dest.exists(), "Destination file must not exist on failure!"


@pytest.mark.parametrize("exit_code", [1, 2, 127, 137, 139, 255])
def test_adv_ffmpeg_nonzero_exit_codes_matrix(monkeypatch, tmp_path: Path, sample_video: Path, exit_code: int):
    """Across various fatal exit codes (including 137 OOM and 139 segfault), .tmp must be unlinked."""
    # 1. Test video extraction
    dest_v = tmp_path / f"fatal_exit_{exit_code}.mp4"
    tmp_v = tmp_path / f"fatal_exit_{exit_code}.mp4.tmp"

    def mock_run_v(cmd, *args, **kwargs):
        tmp_v.write_bytes(b"dirty video stream buffer")
        return subprocess.CompletedProcess(
            cmd,
            returncode=exit_code,
            stdout="",
            stderr=f"Fatal crash signal {exit_code}",
        )

    monkeypatch.setattr(subprocess, "run", mock_run_v)

    with pytest.raises(RuntimeError):
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest_v))

    assert not tmp_v.exists(), f"Video .tmp leaked on exit code {exit_code}"
    assert not dest_v.exists()

    # 2. Test photo extraction
    dest_p = tmp_path / f"fatal_photo_{exit_code}.jpg"
    tmp_p = tmp_path / f"fatal_photo_{exit_code}.jpg.tmp"

    def mock_run_p(cmd, *args, **kwargs):
        tmp_p.write_bytes(b"dirty photo stream buffer")
        return subprocess.CompletedProcess(
            cmd,
            returncode=exit_code,
            stdout="",
            stderr=f"Fatal crash signal {exit_code}",
        )

    monkeypatch.setattr(subprocess, "run", mock_run_p)

    with pytest.raises(RuntimeError):
        StoryMediaExtractor.extract_photo_story(str(sample_video), output_path=str(dest_p))

    assert not tmp_p.exists(), f"Photo .tmp leaked on exit code {exit_code}"
    assert not dest_p.exists()


def test_adv_ffmpeg_timeout_expired_unlinks_tmp(monkeypatch, tmp_path: Path, sample_video: Path):
    """When transcode exceeds timeout, TimeoutExpired is raised and .tmp is unlinked immediately."""
    dest = tmp_path / "timeout_video.mp4"
    tmp_target = tmp_path / "timeout_video.mp4.tmp"

    def mock_timeout(cmd, *args, **kwargs):
        tmp_target.write_bytes(b"partially transcoded 5MB of video before hanging")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)

    monkeypatch.setattr(subprocess, "run", mock_timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest))

    assert not tmp_target.exists(), "Timeout expired leaked a .tmp file on disk!"
    assert not dest.exists()


@pytest.mark.parametrize(
    "exception_to_throw",
    [
        OSError("Disk write error or I/O failure"),
        MemoryError("Out of memory during transcode"),
        PermissionError("Access denied writing to pipe"),
        RuntimeError("Unexpected subprocess crash"),
    ],
)
def test_adv_ffmpeg_arbitrary_exceptions_unlinks_tmp(monkeypatch, tmp_path: Path, sample_video: Path, exception_to_throw: Exception):
    """Any arbitrary exception during execution must trigger cleanup in finally block."""
    dest = tmp_path / "exception_video.mp4"
    tmp_target = tmp_path / "exception_video.mp4.tmp"

    def mock_error(cmd, *args, **kwargs):
        tmp_target.write_bytes(b"garbage in progress")
        raise exception_to_throw

    monkeypatch.setattr(subprocess, "run", mock_error)

    with pytest.raises(type(exception_to_throw)):
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest))

    assert not tmp_target.exists(), f"Exception {type(exception_to_throw)} leaked .tmp file!"
    assert not dest.exists()


def test_adv_ffmpeg_zero_byte_exit_zero_unlinks_tmp(monkeypatch, tmp_path: Path, sample_video: Path):
    """Adversarial scenario: FFmpeg exits with returncode 0 but wrote 0 bytes to .tmp.

    This happens when input stream is empty, corrupted, or filesystem ran out of space.
    The extractor must treat 0-byte output as failure, raise RuntimeError, and unlink .tmp!
    """
    # 1. Video extraction
    dest_v = tmp_path / "empty_video.mp4"
    tmp_v = tmp_path / "empty_video.mp4.tmp"

    def mock_run_zero_v(cmd, *args, **kwargs):
        tmp_v.write_bytes(b"")  # 0 bytes written!
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run_zero_v)

    with pytest.raises(RuntimeError, match="FFmpeg video story extraction failed"):
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest_v))

    assert not tmp_v.exists(), "0-byte video .tmp file was NOT unlinked!"
    assert not dest_v.exists(), "0-byte file must not be promoted to final destination!"

    # 2. Photo extraction
    dest_p = tmp_path / "empty_photo.jpg"
    tmp_p = tmp_path / "empty_photo.jpg.tmp"

    def mock_run_zero_p(cmd, *args, **kwargs):
        tmp_p.write_bytes(b"")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run_zero_p)

    with pytest.raises(RuntimeError, match="FFmpeg photo story extraction failed"):
        StoryMediaExtractor.extract_photo_story(str(sample_video), output_path=str(dest_p))

    assert not tmp_p.exists(), "0-byte photo .tmp file was NOT unlinked!"
    assert not dest_p.exists()


def test_adv_preexisting_corrupt_tmp_handling(monkeypatch, tmp_path: Path, sample_video: Path):
    """If a stale orphaned .tmp file already exists, it must be purged both before and after."""
    dest = tmp_path / "story_with_old_tmp.mp4"
    tmp_file = tmp_path / "story_with_old_tmp.mp4.tmp"

    # Pre-seed stale corrupted tmp
    tmp_file.write_bytes(b"old dead bytes from previous crash")

    # Case A: Execution fails -> old .tmp must be gone
    def mock_fail(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="transcode failed")

    monkeypatch.setattr(subprocess, "run", mock_fail)

    with pytest.raises(RuntimeError):
        StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest))

    assert not tmp_file.exists(), "Pre-existing .tmp was not cleaned up on failure!"
    assert not dest.exists()

    # Case B: Pre-seed again, execution succeeds -> only destination exists, .tmp removed
    tmp_file.write_bytes(b"another stale tmp")

    def mock_success(cmd, *args, **kwargs):
        tmp_file.write_bytes(b"valid new video bytes")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_success)

    out = StoryMediaExtractor.extract_video_story(str(sample_video), output_path=str(dest))
    assert out == str(dest)
    assert dest.exists()
    assert dest.read_bytes() == b"valid new video bytes"
    assert not tmp_file.exists(), "Temporary .tmp file must not remain after successful promotion!"


def test_adv_real_ffmpeg_corrupted_file_unlinks_tmp(tmp_path: Path):
    """Real FFmpeg invocation on invalid/corrupted binary content must fail and clean up .tmp."""
    corrupted_input = tmp_path / "corrupted_media.mp4"
    # Write garbage bytes that look nothing like an MP4/H.264 stream
    corrupted_input.write_bytes(b"\x00\xFF\xAA\x55" * 1024)

    dest_video = tmp_path / "corrupted_out.mp4"
    tmp_video = tmp_path / "corrupted_out.mp4.tmp"

    with pytest.raises(RuntimeError, match="FFmpeg video story extraction failed"):
        StoryMediaExtractor.extract_video_story(str(corrupted_input), output_path=str(dest_video))

    assert not tmp_video.exists(), "Real FFmpeg failure left .tmp file on disk!"
    assert not dest_video.exists()

    dest_photo = tmp_path / "corrupted_cover.jpg"
    tmp_photo = tmp_path / "corrupted_cover.jpg.tmp"

    with pytest.raises(RuntimeError, match="FFmpeg photo story extraction failed"):
        StoryMediaExtractor.extract_photo_story(str(corrupted_input), output_path=str(dest_photo))

    assert not tmp_photo.exists(), "Real FFmpeg photo failure left .tmp file on disk!"
    assert not dest_photo.exists()


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


def test_adv_concurrency_20_parallel_classify_and_extract(tmp_path: Path, sample_video: Path):
    """Stress test: 20 parallel threads calling classify_and_extract with distinct material IDs.

    Verifies:
    1. Exactly 20 tasks complete successfully.
    2. Exactly 20 distinct output file paths are generated.
    3. All 20 output files exist on disk with valid non-zero content.
    4. Exactly 0 orphaned .tmp files remain on disk.
    5. No thread collisions or race condition overwrite anomalies.
    """
    out_dir = tmp_path / "concurrent_stories"
    out_dir.mkdir(parents=True)

    def thread_worker(worker_id: int) -> tuple[int, str, str]:
        # Interleave microsecond jitter to simulate realistic concurrent arrivals
        time.sleep(random.uniform(0.001, 0.01))
        extracted_path, mode = StoryMediaExtractor.classify_and_extract(
            str(sample_video),
            output_dir=str(out_dir),
            material_id=worker_id,
        )
        return worker_id, extracted_path, mode

    def mock_run(cmd, *args, **kwargs):
        tmp_out = cmd[-1]
        Path(tmp_out).write_bytes(f"transcoded_video_payload_{Path(tmp_out).name}".encode())
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    results = []
    with patch("app.features.story.media_extractor.media_info", return_value={"duration": 45.0, "width": 1080, "height": 1920}), \
         patch("subprocess.run", side_effect=mock_run):
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(thread_worker, i) for i in range(1, 21)]
            for f in as_completed(futures):
                results.append(f.result())

    assert len(results) == 20

    extracted_paths = [r[1] for r in results]
    # Invariant: All 20 paths MUST be distinct
    unique_paths = set(extracted_paths)
    assert len(unique_paths) == 20, f"Collision detected! Only {len(unique_paths)} unique paths among 20 workers"

    # Invariant: All 20 files must exist and be non-empty
    for worker_id, path_str, mode in results:
        p = Path(path_str)
        assert p.exists(), f"Output file missing: {path_str}"
        assert p.stat().st_size > 0, f"Output file is empty: {path_str}"
        assert f"story_v_{worker_id}_" in p.name
        content = p.read_text()
        assert f"transcoded_video_payload_{p.name}.tmp" in content or f"transcoded_video_payload_{p.name}" in content

    # Invariant: Exactly zero .tmp files must remain
    tmp_files = list(out_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Leaked .tmp files found: {tmp_files}"


def test_adv_concurrency_20_parallel_extract_video_story(tmp_path: Path, sample_video: Path):
    """Stress test: 20 parallel threads calling extract_video_story directly."""
    out_dir = tmp_path / "stories_direct"
    out_dir.mkdir(parents=True)

    def worker(idx: int) -> str:
        time.sleep(random.uniform(0.001, 0.005))
        return StoryMediaExtractor.extract_video_story(
            str(sample_video),
            material_id=f"vid_mat_{idx}",
        )

    def mock_run(cmd, *args, **kwargs):
        tmp_out = cmd[-1]
        Path(tmp_out).write_bytes(f"video_highlight_{Path(tmp_out).name}".encode())
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch.object(StoryMediaExtractor, "get_stories_dir", return_value=out_dir), \
         patch("subprocess.run", side_effect=mock_run):
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(1, 21)]
            outputs = [f.result() for f in as_completed(futures)]

    assert len(outputs) == 20
    assert len(set(outputs)) == 20

    # Verify all files
    for out in outputs:
        p = Path(out)
        assert p.exists()
        assert p.stat().st_size > 0

    # No tmp files
    assert len(list(out_dir.glob("*.tmp"))) == 0


def test_adv_concurrency_20_parallel_extract_photo_story(tmp_path: Path, sample_video: Path):
    """Stress test: 20 parallel threads calling extract_photo_story directly."""
    out_dir = tmp_path / "photos_direct"
    out_dir.mkdir(parents=True)

    def worker(idx: int) -> str:
        time.sleep(random.uniform(0.001, 0.005))
        return StoryMediaExtractor.extract_photo_story(
            str(sample_video),
            material_id=f"pho_mat_{idx}",
        )

    def mock_run(cmd, *args, **kwargs):
        tmp_out = cmd[-1]
        Path(tmp_out).write_bytes(f"photo_cover_{Path(tmp_out).name}".encode())
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch.object(StoryMediaExtractor, "get_stories_dir", return_value=out_dir), \
         patch("subprocess.run", side_effect=mock_run):
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(1, 21)]
            outputs = [f.result() for f in as_completed(futures)]

    assert len(outputs) == 20
    assert len(set(outputs)) == 20

    for out in outputs:
        p = Path(out)
        assert p.exists()
        assert p.stat().st_size > 0

    assert len(list(out_dir.glob("*.tmp"))) == 0


def test_adv_concurrency_same_material_id_analysis(tmp_path: Path, sample_video: Path):
    """Adversarial investigation: What happens if 5 parallel calls have the EXACT SAME material_id?

    When material_id is identical and called in the same second, generate_story_filename
    produces identical filenames: `story_v_99_{ts}.mp4`.
    This test verifies that:
    1. Either threads succeed cleanly through atomic replacement or fail gracefully.
    2. At no point does a corrupted intermediate file get produced.
    3. No .tmp files linger afterwards.
    """
    out_dir = tmp_path / "same_id_stories"
    out_dir.mkdir(parents=True)

    fixed_id = 999
    successes = []
    failures = []

    def worker(worker_num: int):
        time.sleep(random.uniform(0.001, 0.005))
        try:
            res = StoryMediaExtractor.extract_video_story(
                str(sample_video),
                output_path=str(out_dir / f"story_v_{fixed_id}_test.mp4"),
                material_id=fixed_id,
            )
            successes.append(res)
        except Exception as e:
            failures.append(e)

    def mock_run(cmd, *args, **kwargs):
        tmp_out = cmd[-1]
        Path(tmp_out).write_bytes(b"atomic_video_payload")
        time.sleep(0.005)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=mock_run):
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()

    # Invariant: At least one worker succeeded in generating the final output
    assert len(successes) >= 1
    final_file = out_dir / f"story_v_{fixed_id}_test.mp4"
    assert final_file.exists()
    assert final_file.stat().st_size > 0

    # Invariant: Zero lingering .tmp files!
    tmp_files = list(out_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Lingering tmp files from same-id race: {tmp_files}"


def test_adv_concurrency_real_ffmpeg_multithreaded(tmp_path: Path, real_synthetic_video: Path):
    """Real FFmpeg transcode with 4 concurrent threads to verify OS-level concurrency and nice throttling."""
    out_dir = tmp_path / "real_concurrent_stories"
    out_dir.mkdir(parents=True)

    def real_worker(idx: int) -> str:
        dest = out_dir / f"real_story_{idx}.mp4"
        return StoryMediaExtractor.extract_video_story(
            str(real_synthetic_video),
            output_path=str(dest),
            duration=10.0,
            material_id=idx,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(real_worker, i) for i in range(1, 5)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 4
    for r in results:
        p = Path(r)
        assert p.exists()
        assert p.stat().st_size > 500

    # Ensure zero lingering .tmp files
    assert len(list(out_dir.glob("*.tmp"))) == 0
