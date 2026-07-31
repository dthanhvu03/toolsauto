"""
ffmpeg/ffprobe must always be resolved (WinGet Links / PATH) before use — a bare
"ffmpeg" is WinError 2 on the Windows box this stack runs on.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.media import ffmpeg_path
from app.core.media.video_protector import VideoProtector
from app.features.facebook.media_processor import MediaProcessor

FAKE_FFMPEG = "C:/Fake/Links/ffmpeg.exe"


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(ffmpeg_path, "resolve_ffmpeg", lambda: FAKE_FFMPEG)
    monkeypatch.setattr(ffmpeg_path, "resolve_ffprobe", lambda: "C:/Fake/Links/ffprobe.exe")
    return FAKE_FFMPEG


def test_media_processor_resolves_ffmpeg(fake_ffmpeg):
    assert MediaProcessor._resolve_ffmpeg() == FAKE_FFMPEG


def test_extract_thumbnail_uses_resolved_ffmpeg(fake_ffmpeg, tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # Simulate ffmpeg writing the thumbnail.
        Path(cmd[-1]).write_bytes(b"jpegdata")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("app.features.facebook.media_processor.subprocess.run", fake_run)
    out = MediaProcessor.extract_thumbnail(str(video), job_id=7)

    assert captured["cmd"][0] == FAKE_FFMPEG
    assert out and os.path.exists(out)
    MediaProcessor.cleanup_thumbnail(out)


def test_extract_thumbnail_cleans_up_on_failure(fake_ffmpeg, tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"")  # zero-byte leftover
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("app.features.facebook.media_processor.subprocess.run", fake_run)
    thumb = os.path.join(__import__("tempfile").gettempdir(), "thumb_8.jpg")

    assert MediaProcessor.extract_thumbnail(str(video), job_id=8) is None
    assert not os.path.exists(thumb)


def test_generic_thumbnail_helper_uses_resolved_ffmpeg(fake_ffmpeg, tmp_path, monkeypatch):
    from app.core.media import thumbnail

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"jpegdata")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("app.core.media.thumbnail.subprocess.run", fake_run)
    out = thumbnail.extract_thumbnail(str(video), job_id=9)
    assert captured["cmd"][0] == FAKE_FFMPEG
    thumbnail.cleanup_thumbnail(out)


def test_build_ffmpeg_cmd_uses_resolved_binary_and_skips_nice_on_windows(fake_ffmpeg, monkeypatch):
    profile_cfg = {"vf": "scale=1080:-2", "crf": 23}
    cmd = MediaProcessor._build_ffmpeg_cmd("in.mp4", profile_cfg, "out.mp4")
    if os.name == "nt":
        assert cmd[0] == FAKE_FFMPEG
        assert "nice" not in cmd
    else:
        assert cmd[:3] == ["nice", "-n", "19"]
        assert cmd[3] == FAKE_FFMPEG


def test_orchestrator_run_ffmpeg_substitutes_binary(fake_ffmpeg, monkeypatch):
    from app.core.orchestrator import ContentOrchestrator

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("app.core.orchestrator.subprocess.run", fake_run)
    ContentOrchestrator._run_ffmpeg(["ffmpeg", "-i", "a.mp4"])
    assert captured["cmd"][0] == FAKE_FFMPEG

    ContentOrchestrator._run_ffmpeg(["ffprobe", "-i", "a.mp4"])
    assert captured["cmd"][0] == "C:/Fake/Links/ffprobe.exe"


def test_video_protector_uses_resolved_binaries(fake_ffmpeg, monkeypatch, tmp_path):
    captured: list = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="12.5", stderr="")

    monkeypatch.setattr("app.core.media.video_protector.subprocess.run", fake_run)
    assert VideoProtector._get_video_duration("clip.mp4") == 12.5
    assert captured[0][0].endswith("ffprobe.exe")


# ── drawtext font handling ────────────────────────────────────────────────────


def test_fontfile_arg_escapes_drive_letter(monkeypatch):
    monkeypatch.setattr(VideoProtector, "resolve_fontfile", classmethod(lambda cls: r"C:\Windows\Fonts\arial.ttf"))
    arg = VideoProtector.ffmpeg_fontfile_arg()
    assert arg == ":fontfile='C\\:/Windows/Fonts/arial.ttf'"


def test_fontfile_arg_empty_when_no_font(monkeypatch):
    monkeypatch.setattr(VideoProtector, "resolve_fontfile", classmethod(lambda cls: None))
    assert VideoProtector.ffmpeg_fontfile_arg() == ""
    # Filter still builds without a fontfile fragment.
    assert "fontfile" not in VideoProtector.get_dynamic_watermark_filter("z")


def test_private_fontfile_alias_still_works(monkeypatch):
    monkeypatch.setattr(VideoProtector, "resolve_fontfile", classmethod(lambda cls: None))
    assert VideoProtector._ffmpeg_fontfile_arg() == ""
