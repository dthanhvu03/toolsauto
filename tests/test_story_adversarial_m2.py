"""Adversarial stress-testing suite for Milestone 2: Story Media Extraction & Storage Cleanup.

Executed by Empirical Challenger 1 to rigorously stress-test:
1. Aspect ratio preservation across 16:9, 1:1, 4:3, 9:16 inputs (video & photo):
   - Strict 1080x1920 (9:16) canvas dimensions.
   - Proper letterboxing/pillarboxing without aspect distortion.
   - Pixel-level verification of black padding vs. content bounding box.
2. Highlight duration clamping:
   - Inputs / requested durations of 5s, 12s, 25s, 45s, 120s.
   - Assert extracted highlight video is strictly clamped to [10.0s, 15.0s].
   - Duration classification thresholds in classify_story_mode.
3. Audio handling:
   - Videos without audio track: verify -map 0:a? executes cleanly without crash.
   - Videos with audio track: verify AAC codec, 44.1kHz, ~128kbps transcoding.
   - Videos with multiple audio streams.
4. Process throttling and container arguments:
   - CPU throttling via nice -n 19 and -threads 2.
   - Container optimization via -movflags +faststart (moov atom before mdat).
   - Video codec libx264, pix_fmt yuv420p, crf 23, preset fast.
5. Atomic temporary writes and anti-bloat cleanup (R3):
   - Immediate unlinking of .tmp files on crash, error, or timeout.
   - Stale media sweep by CleanupService.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from PIL import Image
import pytest

from app.core.media.ffmpeg_path import ffmpeg_bin, ffprobe_bin
from app.core.queue.cleanup import CleanupService
from app.features.story.media_extractor import (
    StoryMediaExtractor,
    classify_story_mode,
)


# ── Helpers for Empirical Media Inspection ───────────────────────────────────


def _probe_media_streams(file_path: str) -> dict:
    """Run ffprobe to get comprehensive stream and container format details."""
    res = subprocess.run(
        [
            ffprobe_bin(),
            "-v", "error",
            "-show_entries", "stream=index,codec_type,codec_name,width,height,sample_aspect_ratio,sample_rate,bit_rate",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0, f"ffprobe failed on {file_path}: {res.stderr}"
    return json.loads(res.stdout)


def _extract_frame_image(video_or_image_path: str, tmp_path: Path, seek_sec: float = 0.5) -> Image.Image:
    """Extract a single frame as a PIL Image to inspect pixel colors directly."""
    frame_png = tmp_path / "probe_frame.png"
    if frame_png.exists():
        frame_png.unlink()

    cmd = [
        ffmpeg_bin(), "-y",
        "-ss", f"{seek_sec:.3f}",
        "-i", str(video_or_image_path),
        "-frames:v", "1",
        str(frame_png),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"Failed to extract frame: {res.stderr}"
    return Image.open(str(frame_png))


def _is_black(pixel: tuple[int, ...], threshold: int = 20) -> bool:
    """Return True if RGB pixel is near black (within threshold)."""
    r, g, b = pixel[:3]
    return r <= threshold and g <= threshold and b <= threshold


def _is_colored(pixel: tuple[int, ...], threshold: int = 50) -> bool:
    """Return True if RGB pixel has significant color intensity."""
    r, g, b = pixel[:3]
    return max(r, g, b) >= threshold


# ── 1. Aspect Ratio Preservation & Canvas Normalization Tests ─────────────────


class TestAspectRatioPreservation:
    """Test 16:9, 1:1, 4:3, 9:16 inputs produce 1080x1920 with correct letterbox/pillarbox."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.tmp_dir = tmp_path
        self.output_dir = tmp_path / "stories"
        self.output_dir.mkdir()
        StoryMediaExtractor.stories_dir = self.output_dir

    def test_16_9_landscape_video_to_9_16_story(self):
        """16:9 landscape video (640x360 solid green) must scale to 1080x1920 with top/bottom letterbox."""
        src_16_9 = self.tmp_dir / "src_16_9.mp4"
        # Generate 2-second 640x360 solid green video with sine audio
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "color=c=green:s=640x360:d=2:r=15",
            "-f", "lavfi", "-i", "sine=frequency=800:duration=2",
            "-c:v", "libx264", "-c:a", "aac",
            str(src_16_9),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_video = self.tmp_dir / "out_16_9.mp4"
        StoryMediaExtractor.extract_video_story(
            str(src_16_9),
            output_path=str(out_video),
            duration=10.0,
        )

        probe = _probe_media_streams(str(out_video))
        video_streams = [s for s in probe["streams"] if s["codec_type"] == "video"]
        assert len(video_streams) == 1
        v_stream = video_streams[0]
        assert v_stream["width"] == 1080
        assert v_stream["height"] == 1920

        # Inspect pixels:
        # 16:9 scaled inside 1080x1920 has height 1080 * 9 / 16 = 608.
        # Letterbox top/bottom bars are ~656px each.
        # Top padding (540, 150): must be black.
        # Bottom padding (540, 1800): must be black.
        # Center active content (540, 960): must be green.
        frame_img = _extract_frame_image(str(out_video), self.tmp_dir, seek_sec=0.5)
        assert frame_img.size == (1080, 1920)
        assert _is_black(frame_img.getpixel((540, 150)))
        assert _is_black(frame_img.getpixel((540, 1800)))
        center_px = frame_img.getpixel((540, 960))
        assert center_px[1] > 100 and center_px[0] < 50 and center_px[2] < 50  # green

    def test_1_1_square_video_to_9_16_story(self):
        """1:1 square video (480x480 solid red) must scale to 1080x1920 with top/bottom letterbox."""
        src_1_1 = self.tmp_dir / "src_1_1.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "color=c=red:s=480x480:d=2:r=15",
            "-c:v", "libx264",
            str(src_1_1),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_video = self.tmp_dir / "out_1_1.mp4"
        StoryMediaExtractor.extract_video_story(
            str(src_1_1),
            output_path=str(out_video),
            duration=10.0,
        )

        probe = _probe_media_streams(str(out_video))
        v_stream = [s for s in probe["streams"] if s["codec_type"] == "video"][0]
        assert v_stream["width"] == 1080
        assert v_stream["height"] == 1920

        # 1:1 scaled inside 1080x1920 has height 1080.
        # Letterbox top/bottom bars are (1920 - 1080) / 2 = 420px each.
        # Top padding (540, 150): black.
        # Bottom padding (540, 1750): black.
        # Center content (540, 960): red.
        frame_img = _extract_frame_image(str(out_video), self.tmp_dir, seek_sec=0.5)
        assert frame_img.size == (1080, 1920)
        assert _is_black(frame_img.getpixel((540, 150)))
        assert _is_black(frame_img.getpixel((540, 1750)))
        center_px = frame_img.getpixel((540, 960))
        assert center_px[0] > 100 and center_px[1] < 50 and center_px[2] < 50  # red

    def test_4_3_standard_video_to_9_16_story(self):
        """4:3 standard video (640x480 solid blue) must scale to 1080x1920 with top/bottom letterbox."""
        src_4_3 = self.tmp_dir / "src_4_3.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=640x480:d=2:r=15",
            "-c:v", "libx264",
            str(src_4_3),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_video = self.tmp_dir / "out_4_3.mp4"
        StoryMediaExtractor.extract_video_story(
            str(src_4_3),
            output_path=str(out_video),
            duration=10.0,
        )

        probe = _probe_media_streams(str(out_video))
        v_stream = [s for s in probe["streams"] if s["codec_type"] == "video"][0]
        assert v_stream["width"] == 1080
        assert v_stream["height"] == 1920

        # 4:3 scaled inside 1080x1920 has height 1080 * 3 / 4 = 810.
        # Letterbox top/bottom bars are (1920 - 810) / 2 = 555px each.
        frame_img = _extract_frame_image(str(out_video), self.tmp_dir, seek_sec=0.5)
        assert frame_img.size == (1080, 1920)
        assert _is_black(frame_img.getpixel((540, 150)))
        assert _is_black(frame_img.getpixel((540, 1750)))
        center_px = frame_img.getpixel((540, 960))
        assert center_px[2] > 100 and center_px[0] < 50 and center_px[1] < 50  # blue

    def test_9_16_vertical_video_to_9_16_story(self):
        """9:16 vertical video (540x960 solid yellow) scales to 1080x1920 with zero letterbox bars."""
        src_9_16 = self.tmp_dir / "src_9_16.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "color=c=yellow:s=540x960:d=2:r=15",
            "-c:v", "libx264",
            str(src_9_16),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_video = self.tmp_dir / "out_9_16.mp4"
        StoryMediaExtractor.extract_video_story(
            str(src_9_16),
            output_path=str(out_video),
            duration=10.0,
        )

        probe = _probe_media_streams(str(out_video))
        v_stream = [s for s in probe["streams"] if s["codec_type"] == "video"][0]
        assert v_stream["width"] == 1080
        assert v_stream["height"] == 1920

        # 9:16 fills full canvas without letterbox:
        frame_img = _extract_frame_image(str(out_video), self.tmp_dir, seek_sec=0.5)
        assert frame_img.size == (1080, 1920)
        # All areas (top, center, bottom) are yellow
        top_px = frame_img.getpixel((540, 150))
        center_px = frame_img.getpixel((540, 960))
        bottom_px = frame_img.getpixel((540, 1750))
        for px in (top_px, center_px, bottom_px):
            assert px[0] > 150 and px[1] > 150 and px[2] < 50  # yellow

    def test_photo_story_aspect_ratios(self):
        """Photo story extraction across 16:9, 1:1, 4:3, 9:16 inputs strictly outputs 1080x1920 JPEG."""
        aspect_configs = [
            ("16_9", 640, 360, "magenta"),
            ("1_1", 500, 500, "cyan"),
            ("4_3", 640, 480, "white"),
            ("9_16", 540, 960, "red"),
        ]

        for name, w, h, col in aspect_configs:
            src_img = self.tmp_dir / f"src_{name}.jpg"
            # Create synthetic JPEG
            im = Image.new("RGB", (w, h), color=col)
            im.save(str(src_img), format="JPEG")

            out_photo = self.tmp_dir / f"story_{name}.jpg"
            res = StoryMediaExtractor.extract_photo_story(
                str(src_img),
                output_path=str(out_photo),
            )
            assert res == str(out_photo)
            assert out_photo.exists()

            # Verify image properties directly
            res_im = Image.open(str(out_photo))
            assert res_im.size == (1080, 1920), f"Aspect {name} produced incorrect resolution {res_im.size}"
            assert res_im.format == "JPEG"

            if name == "16_9":
                assert _is_black(res_im.getpixel((540, 100)))
                assert _is_black(res_im.getpixel((540, 1800)))
            elif name == "9_16":
                # Full vertical coverage
                assert _is_colored(res_im.getpixel((540, 100)))
                assert _is_colored(res_im.getpixel((540, 1800)))


# ── 2. Highlight Duration Clamping Tests ──────────────────────────────────────


class TestHighlightDurationClamping:
    """Test inputs with 5s, 12s, 25s, 45s, 120s durations are strictly clamped to [10.0, 15.0]."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.tmp_dir = tmp_path
        self.output_dir = tmp_path / "stories"
        self.output_dir.mkdir()
        StoryMediaExtractor.stories_dir = self.output_dir

    def test_duration_parameter_clamping_logic(self, monkeypatch):
        """Exhaustive check of duration parameter clamping across adversarial values."""
        captured_cmds: list[list[str]] = []

        fake_input = self.tmp_dir / "fake.mp4"
        fake_input.write_text("fake")

        def mock_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            Path(cmd[-1]).write_bytes(b"dummy")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        cases = [
            (5.0, 10.0),    # Under min -> clamped to 10.0
            (0.0, 10.0),    # Zero -> clamped to 10.0
            (-10.0, 10.0),  # Negative -> clamped to 10.0
            (9.999, 10.0),  # Boundary below -> clamped to 10.0
            (10.0, 10.0),   # Lower bound exact -> 10.0
            (12.0, 12.0),   # In range -> 12.0
            (14.5, 14.5),   # In range -> 14.5
            (15.0, 15.0),   # Upper bound exact -> 15.0
            (15.001, 15.0), # Boundary above -> clamped to 15.0
            (25.0, 15.0),   # Over max -> clamped to 15.0
            (45.0, 15.0),   # Over max -> clamped to 15.0
            (120.0, 15.0),  # Over max -> clamped to 15.0
        ]

        for req_dur, expected_dur in cases:
            out_file = self.tmp_dir / f"out_dur_{req_dur}.mp4"
            StoryMediaExtractor.extract_video_story(
                str(fake_input),
                output_path=str(out_file),
                duration=req_dur,
            )
            cmd = captured_cmds[-1]
            t_idx = cmd.index("-t")
            actual_t = float(cmd[t_idx + 1])
            assert actual_t == expected_dur, (
                f"Requested {req_dur}s expected clamped to {expected_dur}s, but got {actual_t}s"
            )

    def test_classify_story_mode_duration_rules(self):
        """Verify duration-based mode classification against the 5 durations."""
        # 5s input: <10s cannot be video story -> always photo
        assert classify_story_mode(5.0) == "photo"
        assert classify_story_mode(5.0, preferred_mode="video") == "photo"

        # 12s input: <=30s defaults to photo; honors video preference
        assert classify_story_mode(12.0) == "photo"
        assert classify_story_mode(12.0, preferred_mode="video") == "video"

        # 25s input: <=30s defaults to photo; honors video preference
        assert classify_story_mode(25.0) == "photo"
        assert classify_story_mode(25.0, preferred_mode="video") == "video"

        # 45s input: >30s defaults to video
        assert classify_story_mode(45.0) == "video"
        assert classify_story_mode(45.0, preferred_mode="photo") == "photo"

        # 120s input: >30s defaults to video
        assert classify_story_mode(120.0) == "video"
        assert classify_story_mode(120.0, preferred_mode="photo") == "photo"


# ── 3. Audio Stream Handling Tests ───────────────────────────────────────────


class TestAudioHandling:
    """Test videos with and without audio track; verify -map 0:a? operates cleanly."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.tmp_dir = tmp_path
        self.output_dir = tmp_path / "stories"
        self.output_dir.mkdir()
        StoryMediaExtractor.stories_dir = self.output_dir

    def test_video_without_audio_stream_succeeds(self):
        """Real FFmpeg execution on silent video (0 audio tracks) must succeed without error."""
        silent_clip = self.tmp_dir / "silent_input.mp4"
        # Generate 2-second clip with NO audio
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
            "-c:v", "libx264",
            str(silent_clip),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        # Confirm source has 0 audio streams
        probe_src = _probe_media_streams(str(silent_clip))
        assert not any(s["codec_type"] == "audio" for s in probe_src["streams"])

        # Extract video story
        out_clip = self.tmp_dir / "silent_story.mp4"
        res = StoryMediaExtractor.extract_video_story(
            str(silent_clip),
            output_path=str(out_clip),
            duration=10.0,
        )
        assert res == str(out_clip)
        assert out_clip.exists()
        assert out_clip.stat().st_size > 500

        # Probe output: video stream is 1080x1920, audio stream is absent cleanly
        probe_out = _probe_media_streams(str(out_clip))
        v_streams = [s for s in probe_out["streams"] if s["codec_type"] == "video"]
        a_streams = [s for s in probe_out["streams"] if s["codec_type"] == "audio"]
        assert len(v_streams) == 1
        assert v_streams[0]["width"] == 1080
        assert v_streams[0]["height"] == 1920
        assert len(a_streams) == 0  # No audio stream generated, no ffmpeg error

    def test_video_with_audio_stream_transcodes_aac(self):
        """Real FFmpeg execution on video with audio stream transcodes to AAC 44100Hz."""
        audio_clip = self.tmp_dir / "audio_input.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-c:a", "mp3",  # source with mp3 audio
            str(audio_clip),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_clip = self.tmp_dir / "audio_story.mp4"
        StoryMediaExtractor.extract_video_story(
            str(audio_clip),
            output_path=str(out_clip),
            duration=10.0,
        )

        probe_out = _probe_media_streams(str(out_clip))
        a_streams = [s for s in probe_out["streams"] if s["codec_type"] == "audio"]
        assert len(a_streams) == 1
        a_info = a_streams[0]
        assert a_info["codec_name"] == "aac"
        assert int(a_info["sample_rate"]) == 44100

    def test_video_with_multiple_audio_streams(self):
        """Video with 2 audio streams extracts cleanly using -map 0:a? without collision."""
        multi_audio = self.tmp_dir / "multi_audio.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
            "-c:v", "libx264", "-c:a", "aac",
            str(multi_audio),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_clip = self.tmp_dir / "multi_story.mp4"
        StoryMediaExtractor.extract_video_story(
            str(multi_audio),
            output_path=str(out_clip),
            duration=10.0,
        )
        assert out_clip.exists()
        assert out_clip.stat().st_size > 500


# ── 4. Process Throttling & Encoder Arguments Tests ───────────────────────────


class TestThrottlingAndEncoderArguments:
    """Verify -threads 2, nice -n 19, -movflags +faststart, libx264, aac."""

    def test_ffmpeg_command_flags_strictly_present(self, tmp_path, monkeypatch):
        """Verify command list contains exact mandatory throttling & encoding flags."""
        fake_input = tmp_path / "test.mp4"
        fake_input.write_text("dummy")
        captured_cmd: list[str] = []

        def mock_run(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            Path(cmd[-1]).write_bytes(b"data")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        StoryMediaExtractor.extract_video_story(
            str(fake_input),
            output_path=str(tmp_path / "target.mp4"),
        )

        # 1. Throttling: nice -n 19
        assert captured_cmd[0:3] == ["nice", "-n", "19"]

        # 2. Throttling: -threads 2
        assert "-threads" in captured_cmd
        threads_val = captured_cmd[captured_cmd.index("-threads") + 1]
        assert threads_val == "2"

        # 3. Container: -movflags +faststart
        assert "-movflags" in captured_cmd
        movflags_val = captured_cmd[captured_cmd.index("-movflags") + 1]
        assert movflags_val == "+faststart"

        # 4. Video Codec: -c:v libx264
        assert "-c:v" in captured_cmd
        cv_val = captured_cmd[captured_cmd.index("-c:v") + 1]
        assert cv_val == "libx264"

        # 5. Audio Codec: -c:a aac
        assert "-c:a" in captured_cmd
        ca_val = captured_cmd[captured_cmd.index("-c:a") + 1]
        assert ca_val == "aac"

        # 6. Audio bitrate & sample rate
        assert "-b:a" in captured_cmd
        assert captured_cmd[captured_cmd.index("-b:a") + 1] == "128k"
        assert "-ar" in captured_cmd
        assert captured_cmd[captured_cmd.index("-ar") + 1] == "44100"

        # 7. Video scale & pad filter
        assert "-vf" in captured_cmd
        vf_val = captured_cmd[captured_cmd.index("-vf") + 1]
        assert "scale=1080:1920:force_original_aspect_ratio=decrease" in vf_val
        assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" in vf_val

    def test_faststart_moov_atom_placement(self, tmp_path):
        """Empirical check: -movflags +faststart places 'moov' atom before 'mdat' in MP4 file."""
        src_clip = tmp_path / "src_faststart.mp4"
        cmd = [
            ffmpeg_bin(), "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1:r=10",
            "-c:v", "libx264",
            str(src_clip),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        out_clip = tmp_path / "faststart_out.mp4"
        StoryMediaExtractor.extract_video_story(
            str(src_clip),
            output_path=str(out_clip),
            duration=10.0,
        )

        with open(out_clip, "rb") as f:
            header = f.read(4096)

        moov_pos = header.find(b"moov")
        mdat_pos = header.find(b"mdat")

        assert moov_pos != -1, "moov atom not found in header"
        # +faststart ensures moov atom precedes mdat atom for fast streaming
        if mdat_pos != -1:
            assert moov_pos < mdat_pos, "moov atom must appear before mdat atom with faststart"


# ── 5. Error Recovery, Atomic Writes & Anti-Bloat ─────────────────────────────


class TestErrorRecoveryAndAntiBloat:
    """Stress test error conditions, corrupt files, and temp file cleanup."""

    def test_corrupted_video_raises_and_cleans_tmp(self, tmp_path):
        """When input video is corrupt, RuntimeError is raised and NO .tmp is left behind."""
        corrupt_file = tmp_path / "corrupt_input.mp4"
        corrupt_file.write_bytes(b"\x00\x01\x02\x03\x04CORRUPTED_TRASH_DATA\xff\xfe")

        target_out = tmp_path / "never_created.mp4"
        target_tmp = tmp_path / "never_created.mp4.tmp"

        with pytest.raises(RuntimeError):
            StoryMediaExtractor.extract_video_story(
                str(corrupt_file),
                output_path=str(target_out),
            )

        assert not target_out.exists(), "Target output file should not exist on error"
        assert not target_tmp.exists(), "Temporary .tmp file must be unlinked immediately"

    def test_nonexistent_file_raises_filenotfound(self, tmp_path):
        """Non-existent inputs immediately raise FileNotFoundError before invoking FFmpeg."""
        missing = str(tmp_path / "ghost.mp4")
        with pytest.raises(FileNotFoundError):
            StoryMediaExtractor.extract_video_story(missing)
        with pytest.raises(FileNotFoundError):
            StoryMediaExtractor.extract_photo_story(missing)

    def test_cleanup_service_retention_sweep(self, tmp_path):
        """CleanupService._cleanup_stale_story_files deletes files older than TTL."""
        stories_dir = tmp_path / "stories"
        stories_dir.mkdir()

        now = 2000000000.0
        # 30 hours old (>24h TTL)
        old_file = stories_dir / "story_v_1_1999890000.mp4"
        old_file.write_bytes(b"old")
        os.utime(old_file, (now - 30 * 3600, now - 30 * 3600))

        # 5 hours old (<24h TTL)
        fresh_file = stories_dir / "story_p_2_1999980000.jpg"
        fresh_file.write_bytes(b"fresh")
        os.utime(fresh_file, (now - 5 * 3600, now - 5 * 3600))

        # Stale .tmp file (>24h TTL)
        stale_tmp = stories_dir / "story_v_3_1999890000.mp4.tmp"
        stale_tmp.write_bytes(b"stale_tmp")
        os.utime(stale_tmp, (now - 30 * 3600, now - 30 * 3600))

        # Monkeypatch time.time to 'now'
        import time
        orig_time = time.time
        try:
            time.time = lambda: now
            removed = CleanupService._cleanup_stale_story_files(ttl_hours=24, stories_dir=stories_dir)
            assert removed == 2
            assert not old_file.exists()
            assert not stale_tmp.exists()
            assert fresh_file.exists()
        finally:
            time.time = orig_time
