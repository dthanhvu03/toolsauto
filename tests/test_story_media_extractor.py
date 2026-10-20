"""Unit and integration tests for StoryMediaExtractor & Storage Cleanup (Milestone 2: R2 & R3)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock

import pytest

from app.core.media.ffmpeg_path import ffmpeg_bin
from app.core.media.thumbnail import media_info
from app.core.queue.cleanup import CleanupService
from app.features.story.media_extractor import (
    STORY_SCALE_PAD_FILTER,
    StoryMediaExtractor,
    classify_story_mode,
)


# ── 1. Classification Tests ──────────────────────────────────────────────────


def test_classify_story_mode_short_video_defaults_to_photo():
    """Videos <= 30.0s default to photo story."""
    assert classify_story_mode(15.0) == "photo"
    assert classify_story_mode(30.0) == "photo"
    assert classify_story_mode(0.0) == "photo"


def test_classify_story_mode_long_video_defaults_to_video():
    """Videos > 30.0s default to video highlight story."""
    assert classify_story_mode(30.1) == "video"
    assert classify_story_mode(45.0) == "video"
    assert classify_story_mode(120.0) == "video"


def test_classify_story_mode_honors_preferred_mode_when_eligible():
    """When preferred_mode is given and duration >= 10s, honor it."""
    assert classify_story_mode(45.0, preferred_mode="photo") == "photo"
    assert classify_story_mode(20.0, preferred_mode="video") == "video"
    assert classify_story_mode(10.0, preferred_mode="video") == "video"
    assert classify_story_mode(10.0, preferred_mode="photo") == "photo"


def test_classify_story_mode_preferred_video_rejected_when_under_10s():
    """Cannot cut 10-15s highlight from video under 10s; must fallback to photo."""
    assert classify_story_mode(8.0, preferred_mode="video") == "photo"
    assert classify_story_mode(3.0, preferred_mode="video") == "photo"
    assert classify_story_mode(0.0, preferred_mode="video") == "photo"


def test_classify_story_mode_via_class_method():
    """StoryMediaExtractor.classify_story_mode delegates cleanly."""
    assert StoryMediaExtractor.classify_story_mode(60.0) == "video"
    assert StoryMediaExtractor.classify_story_mode(25.0) == "photo"
    assert StoryMediaExtractor.classify_story_mode(12.0, preferred_mode="video") == "video"


# ── 2. Deterministic Filename Generation ─────────────────────────────────────


def test_generate_story_filename():
    """Deterministic filenames matching story_{v|p}_{id}_{timestamp}.{mp4|jpg}."""
    fn_v = StoryMediaExtractor.generate_story_filename("video", material_id=42, timestamp=1700000000)
    assert fn_v == "story_v_42_1700000000.mp4"

    fn_p = StoryMediaExtractor.generate_story_filename("photo", material_id="vir_99", timestamp=1700000000)
    assert fn_p == "story_p_vir_99_1700000000.jpg"

    # Default fallback id when None or empty
    fn_empty = StoryMediaExtractor.generate_story_filename("video", material_id="", timestamp=1700000000)
    assert fn_empty == "story_v_0_1700000000.mp4"


# ── 3. Video Extraction FFmpeg Parameters & Clamping ─────────────────────────


def test_video_story_duration_clamping(monkeypatch, tmp_path):
    """Highlight duration must clamp strictly to [10.0, 15.0]."""
    fake_input = tmp_path / "dummy.mp4"
    fake_input.write_text("dummy")

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        tmp_file = cmd[-1]
        Path(tmp_file).write_bytes(b"dummy_video_bytes")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Test 1: Duration 5.0 -> clamped up to 10.0
    out1 = tmp_path / "out1.mp4"
    StoryMediaExtractor.extract_video_story(str(fake_input), output_path=str(out1), duration=5.0)
    cmd1 = captured_cmds[-1]
    t_idx1 = cmd1.index("-t")
    assert float(cmd1[t_idx1 + 1]) == 10.0

    # Test 2: Duration 25.0 -> clamped down to 15.0
    out2 = tmp_path / "out2.mp4"
    StoryMediaExtractor.extract_video_story(str(fake_input), output_path=str(out2), duration=25.0)
    cmd2 = captured_cmds[-1]
    t_idx2 = cmd2.index("-t")
    assert float(cmd2[t_idx2 + 1]) == 15.0

    # Test 3: Duration 12.5 -> preserved
    out3 = tmp_path / "out3.mp4"
    StoryMediaExtractor.extract_video_story(str(fake_input), output_path=str(out3), duration=12.5)
    cmd3 = captured_cmds[-1]
    t_idx3 = cmd3.index("-t")
    assert float(cmd3[t_idx3 + 1]) == 12.5


def test_video_story_ffmpeg_command_structure(monkeypatch, tmp_path):
    """Verify exact compliance with Facebook Story tech specs: 1080x1920, 9:16, H.264, AAC, throttling."""
    fake_input = tmp_path / "source.mp4"
    fake_input.write_text("data")
    dest_output = tmp_path / "final_story.mp4"

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        tmp_file = cmd[-1]
        Path(tmp_file).write_bytes(b"mp4_content")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = StoryMediaExtractor.extract_video_story(
        str(fake_input),
        output_path=str(dest_output),
        start_sec=3.5,
        duration=14.0,
    )
    assert res == str(dest_output)
    assert dest_output.exists()

    cmd = captured_cmds[0]

    # CPU throttling check
    assert cmd[0] == "nice"
    assert cmd[1] == "-n"
    assert cmd[2] == "19"

    # Start & duration
    assert "-ss" in cmd
    assert float(cmd[cmd.index("-ss") + 1]) == 3.5
    assert "-t" in cmd
    assert float(cmd[cmd.index("-t") + 1]) == 14.0

    # Resolution & 9:16 Canvas filter
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == STORY_SCALE_PAD_FILTER
    assert "1080:1920" in STORY_SCALE_PAD_FILTER

    # Streams mapping: video + audio fallback
    assert cmd.count("-map") == 2
    map_indices = [i for i, x in enumerate(cmd) if x == "-map"]
    maps = [cmd[i + 1] for i in map_indices]
    assert "0:v:0" in maps
    assert "0:a?" in maps

    # Video Codec
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-pix_fmt" in cmd
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "-crf" in cmd
    assert cmd[cmd.index("-crf") + 1] == "23"
    assert "-preset" in cmd
    assert cmd[cmd.index("-preset") + 1] == "fast"

    # Audio Codec
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-b:a" in cmd
    assert cmd[cmd.index("-b:a") + 1] == "128k"
    assert "-ar" in cmd
    assert cmd[cmd.index("-ar") + 1] == "44100"

    # Process and container flags
    assert "-threads" in cmd
    assert cmd[cmd.index("-threads") + 1] == "2"
    assert "-movflags" in cmd
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"

    # Final temp target
    assert cmd[-1] == f"{dest_output}.tmp"


# ── 4. Photo Extraction FFmpeg Parameters ────────────────────────────────────


def test_photo_story_ffmpeg_command_structure(monkeypatch, tmp_path):
    """Verify Photo Story parameters: 1080x1920 vertical canvas, JPEG, -q:v 2, -frames:v 1."""
    fake_input = tmp_path / "video_source.mp4"
    fake_input.write_text("data")
    dest_output = tmp_path / "final_photo.jpg"

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        tmp_file = cmd[-1]
        Path(tmp_file).write_bytes(b"jpg_content")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = StoryMediaExtractor.extract_photo_story(
        str(fake_input),
        output_path=str(dest_output),
        seek_sec=2.5,
    )
    assert res == str(dest_output)
    assert dest_output.exists()

    cmd = captured_cmds[0]

    # CPU throttling check
    assert cmd[0] == "nice"
    assert cmd[1] == "-n"
    assert cmd[2] == "19"

    # Seek
    assert "-ss" in cmd
    assert float(cmd[cmd.index("-ss") + 1]) == 2.5

    # Single frame extraction
    assert "-frames:v" in cmd
    assert cmd[cmd.index("-frames:v") + 1] == "1"

    # 9:16 vertical pad
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == STORY_SCALE_PAD_FILTER

    # High quality JPEG
    assert "-q:v" in cmd
    assert cmd[cmd.index("-q:v") + 1] == "2"

    assert cmd[-1] == f"{dest_output}.tmp"


# ── 5. Atomic .tmp File Writes & Cleanup on Failure (R3) ─────────────────────


def test_atomic_tmp_unlinked_on_ffmpeg_nonzero_exit(monkeypatch, tmp_path):
    """If FFmpeg exits with error code, .tmp must be unlinked immediately in finally."""
    fake_input = tmp_path / "corrupt.mp4"
    fake_input.write_text("bad data")
    dest_output = tmp_path / "wont_exist.mp4"
    tmp_target = tmp_path / "wont_exist.mp4.tmp"

    def fake_run(cmd, *args, **kwargs):
        # Emulate FFmpeg partially writing corrupted bytes before crashing
        tmp_target.write_bytes(b"partial corrupted bytes")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="Corrupt video stream")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="FFmpeg video story extraction failed"):
        StoryMediaExtractor.extract_video_story(str(fake_input), output_path=str(dest_output))

    # Anti-bloat check: .tmp must be unlinked and final destination must not exist
    assert not tmp_target.exists()
    assert not dest_output.exists()


def test_atomic_tmp_unlinked_on_exception_or_timeout(monkeypatch, tmp_path):
    """If FFmpeg raises TimeoutExpired or OS error, .tmp must be unlinked immediately."""
    fake_input = tmp_path / "sample.mp4"
    fake_input.write_text("data")
    dest_output = tmp_path / "timeout.mp4"
    tmp_target = tmp_path / "timeout.mp4.tmp"

    def fake_run(cmd, *args, **kwargs):
        tmp_target.write_bytes(b"unfinished bytes")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired):
        StoryMediaExtractor.extract_video_story(str(fake_input), output_path=str(dest_output))

    assert not tmp_target.exists()
    assert not dest_output.exists()


def test_photo_atomic_tmp_unlinked_on_failure(monkeypatch, tmp_path):
    """Photo extraction also strictly guarantees .tmp unlinking on failure."""
    fake_input = tmp_path / "sample.mp4"
    fake_input.write_text("data")
    dest_output = tmp_path / "photo_fail.jpg"
    tmp_target = tmp_path / "photo_fail.jpg.tmp"

    def fake_run(cmd, *args, **kwargs):
        tmp_target.write_bytes(b"broken jpg")
        return subprocess.CompletedProcess(cmd, returncode=2, stdout="", stderr="Decoder error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="FFmpeg photo story extraction failed"):
        StoryMediaExtractor.extract_photo_story(str(fake_input), output_path=str(dest_output))

    assert not tmp_target.exists()
    assert not dest_output.exists()


def test_missing_input_raises_filenotfound(tmp_path):
    """Non-existent inputs fail fast with FileNotFoundError before launching FFmpeg."""
    non_existent = str(tmp_path / "does_not_exist.mp4")
    with pytest.raises(FileNotFoundError):
        StoryMediaExtractor.extract_video_story(non_existent)

    with pytest.raises(FileNotFoundError):
        StoryMediaExtractor.extract_photo_story(non_existent)


# ── 6. Classify and Extract Orchestration ────────────────────────────────────


def test_classify_and_extract_routes_to_video(monkeypatch, tmp_path):
    """classify_and_extract correctly routes duration > 30s to video story extraction."""
    fake_input = tmp_path / "input.mp4"
    fake_input.write_text("data")

    monkeypatch.setattr(
        "app.features.story.media_extractor.media_info",
        lambda p: {"duration": 48.0, "width": 720, "height": 1280},
    )

    extracted_video_called = []

    def mock_extract_video(input_path, output_path=None, material_id=0):
        extracted_video_called.append((input_path, output_path))
        Path(output_path).write_text("video_done")
        return output_path

    monkeypatch.setattr(StoryMediaExtractor, "extract_video_story", mock_extract_video)

    out_path, mode = StoryMediaExtractor.classify_and_extract(
        str(fake_input),
        output_dir=str(tmp_path),
        material_id=101,
    )
    assert mode == "video"
    assert len(extracted_video_called) == 1
    assert "story_v_101_" in out_path


def test_classify_and_extract_routes_to_photo(monkeypatch, tmp_path):
    """classify_and_extract correctly routes duration <= 30s to photo story extraction."""
    fake_input = tmp_path / "input_short.mp4"
    fake_input.write_text("data")

    monkeypatch.setattr(
        "app.features.story.media_extractor.media_info",
        lambda p: {"duration": 18.0, "width": 1080, "height": 1920},
    )

    extracted_photo_called = []

    def mock_extract_photo(input_path, output_path=None, seek_sec=2.0, material_id=0):
        extracted_photo_called.append((input_path, output_path, seek_sec))
        Path(output_path).write_text("photo_done")
        return output_path

    monkeypatch.setattr(StoryMediaExtractor, "extract_photo_story", mock_extract_photo)

    out_path, mode = StoryMediaExtractor.classify_and_extract(
        str(fake_input),
        output_dir=str(tmp_path),
        material_id=202,
    )
    assert mode == "photo"
    assert len(extracted_photo_called) == 1
    assert "story_p_202_" in out_path
    # Seek should be ~ 18.0 * 0.15 = 2.7s
    assert abs(extracted_photo_called[0][2] - 2.7) < 0.01


# ── 7. Stale Story Media Cleanup (CleanupService R3) ──────────────────────────


def test_cleanup_stale_story_files(tmp_path):
    """CleanupService._cleanup_stale_story_files unlinks files older than ttl_hours."""
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir()

    now = time.time()
    stale_ts = now - 26 * 3600  # 26 hours old (> 24h TTL)
    fresh_ts = now - 2 * 3600   # 2 hours old (< 24h TTL)

    # 1. Stale completed video
    stale_video = stories_dir / "story_v_1_1000.mp4"
    stale_video.write_bytes(b"old video content")
    os.utime(stale_video, (stale_ts, stale_ts))

    # 2. Stale orphaned .tmp
    stale_tmp = stories_dir / "story_p_2_1000.jpg.tmp"
    stale_tmp.write_bytes(b"old tmp content")
    os.utime(stale_tmp, (stale_ts, stale_ts))

    # 3. Fresh video (< 24h)
    fresh_video = stories_dir / "story_v_3_2000.mp4"
    fresh_video.write_bytes(b"new video content")
    os.utime(fresh_video, (fresh_ts, fresh_ts))

    # Run cleanup with 24h TTL
    removed_count = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)

    assert removed_count == 2
    assert not stale_video.exists()
    assert not stale_tmp.exists()
    assert fresh_video.exists()


def test_cleanup_service_run_hooks_story_cleanup(monkeypatch):
    """CleanupService.run invokes _cleanup_stale_story_files non-fatally."""
    mock_cleanup_story = MagicMock()
    monkeypatch.setattr(CleanupService, "_cleanup_stale_story_files", mock_cleanup_story)
    monkeypatch.setattr(CleanupService, "_archive_done_files", MagicMock())
    monkeypatch.setattr(CleanupService, "_delete_failed_files", MagicMock())
    monkeypatch.setattr(CleanupService, "_delete_cancelled_files", MagicMock())
    monkeypatch.setattr(CleanupService, "_remove_stale_tmp_files", MagicMock())
    monkeypatch.setattr(CleanupService, "_clear_browser_caches", MagicMock())
    monkeypatch.setattr(CleanupService, "_run_daily_log_cleanup", MagicMock())

    dummy_db = MagicMock()
    CleanupService.run(dummy_db)

    assert mock_cleanup_story.call_count == 1


# ── 8. End-to-End Real FFmpeg Execution Integration Test ─────────────────────


def test_e2e_real_ffmpeg_video_and_photo_extraction(tmp_path):
    """
    End-to-end integration test creating a real synthetic video clip and running
    actual FFmpeg commands to produce genuine Facebook Story 9:16 artifacts.
    """
    source_clip = tmp_path / "raw_clip.mp4"
    # Create 6-second synthetic 1280x720 video with audio using lavfi
    create_cmd = [
        ffmpeg_bin(), "-y",
        "-f", "lavfi", "-i", "testsrc=duration=6:size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2",
        "-c:a", "aac",
        str(source_clip),
    ]
    sub_res = subprocess.run(create_cmd, capture_output=True, text=True, timeout=120)
    assert sub_res.returncode == 0, f"Failed to create synthetic test clip: {sub_res.stderr}"

    # 1. Real Video Story Extraction
    video_out = tmp_path / "story_output.mp4"
    res_video = StoryMediaExtractor.extract_video_story(
        str(source_clip),
        output_path=str(video_out),
        duration=10.0,
    )
    assert res_video == str(video_out)
    assert video_out.exists()
    assert video_out.stat().st_size > 1000

    # Probe real video metadata
    v_info = media_info(str(video_out))
    assert v_info["width"] == 1080
    assert v_info["height"] == 1920
    assert v_info["duration"] >= 5.0  # Input was 6s, output highlight covers it

    # Ensure no lingering .tmp file
    assert not Path(f"{video_out}.tmp").exists()

    # 2. Real Photo Story Extraction
    photo_out = tmp_path / "story_cover.jpg"
    res_photo = StoryMediaExtractor.extract_photo_story(
        str(source_clip),
        output_path=str(photo_out),
        seek_sec=1.5,
    )
    assert res_photo == str(photo_out)
    assert photo_out.exists()
    assert photo_out.stat().st_size > 1000

    # Probe real photo metadata
    p_info = media_info(str(photo_out))
    assert p_info["width"] == 1080
    assert p_info["height"] == 1920

    # Ensure no lingering .tmp file
    assert not Path(f"{photo_out}.tmp").exists()
