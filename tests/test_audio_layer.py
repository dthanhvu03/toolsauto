"""Tests cho app/features/viral_intake/audio_layer.py (ADR-016). Không mạng, không ffmpeg thật."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.features.viral_intake import audio_layer


def _fake_run_writes_output(record: list):
    """subprocess.run giả: ghi lại lệnh, tạo file ra (đối số cuối) đủ lớn."""

    def _run(cmd, *args, **kwargs):
        record.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"\0" * 4096)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return _run


# ---------------------------------------------------------------------------
# (a) pick_music
# ---------------------------------------------------------------------------

def test_pick_music_empty_dir_returns_none(tmp_path):
    assert audio_layer.pick_music(str(tmp_path)) is None
    assert audio_layer.pick_music(str(tmp_path / "missing")) is None
    assert audio_layer.pick_music(None) is None


def test_pick_music_returns_one_of_files(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.m4a").write_bytes(b"x")
    (tmp_path / "c.WAV").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    allowed = {str(tmp_path / n) for n in ("a.mp3", "b.m4a", "c.WAV")}
    for seed in range(10):
        picked = audio_layer.pick_music(str(tmp_path), seed=seed)
        assert picked in allowed
    assert audio_layer.pick_music(str(tmp_path)) in allowed


# ---------------------------------------------------------------------------
# (b) mix_voice / mix_music build đúng lệnh ffmpeg
# ---------------------------------------------------------------------------

def test_mix_voice_builds_amix_command(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio_layer.subprocess, "run", _fake_run_writes_output(calls))
    monkeypatch.setattr(
        audio_layer, "_probe", lambda _p: {"duration": 10.0, "has_audio": True},
    )
    out = str(tmp_path / "out.mp4")
    ok = audio_layer.mix_voice("in.mp4", "voice.mp3", out, original_volume=0.25, voice_volume=1.0)
    assert ok is True
    assert len(calls) == 1
    cmd = calls[0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2:duration=first" in fc
    assert "[0:a]volume=0.250" in fc
    assert "[1:a]volume=1.000" in fc
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[-1] == out


def test_mix_voice_without_original_audio_maps_voice_only(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio_layer.subprocess, "run", _fake_run_writes_output(calls))
    monkeypatch.setattr(
        audio_layer, "_probe", lambda _p: {"duration": 10.0, "has_audio": False},
    )
    ok = audio_layer.mix_voice("in.mp4", "voice.mp3", str(tmp_path / "o.mp4"))
    assert ok is True
    fc = calls[0][calls[0].index("-filter_complex") + 1]
    assert "amix" not in fc
    assert "[1:a]volume=" in fc
    assert "-shortest" in calls[0]
    assert "copy" in calls[0]


def test_mix_music_builds_loop_fade_amix(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(audio_layer.subprocess, "run", _fake_run_writes_output(calls))
    monkeypatch.setattr(
        audio_layer, "_probe", lambda _p: {"duration": 20.0, "has_audio": True},
    )
    ok = audio_layer.mix_music(
        "in.mp4", "song.mp3", str(tmp_path / "o.mp4"), music_volume=0.12, fade_sec=1.5,
    )
    assert ok is True
    cmd = calls[0]
    # nhạc lặp vô hạn, cắt theo video
    loop_idx = cmd.index("-stream_loop")
    assert cmd[loop_idx + 1] == "-1"
    assert cmd[loop_idx + 2] == "-i" and cmd[loop_idx + 3] == "song.mp3"
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2:duration=first" in fc
    assert "[1:a]volume=0.120" in fc
    assert "afade=t=out:st=18.500:d=1.500" in fc
    assert cmd[cmd.index("-t") + 1] == "20.000"
    assert cmd[cmd.index("-c:v") + 1] == "copy"


def test_mix_returns_false_when_ffmpeg_fails(tmp_path, monkeypatch):
    def _fail(cmd, *a, **k):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr(audio_layer.subprocess, "run", _fail)
    monkeypatch.setattr(
        audio_layer, "_probe", lambda _p: {"duration": 5.0, "has_audio": True},
    )
    out = str(tmp_path / "o.mp4")
    assert audio_layer.mix_voice("in.mp4", "v.mp3", out) is False
    assert audio_layer.mix_music("in.mp4", "m.mp3", out) is False
    assert not os.path.exists(out)


# ---------------------------------------------------------------------------
# (c) synthesize_voice: edge lỗi → piper; cả hai hỏng → False, không raise
# ---------------------------------------------------------------------------

def test_synthesize_voice_falls_back_to_piper(tmp_path, monkeypatch):
    seen: list[str] = []

    def _edge(text, out_path, voice, rate):
        seen.append("edge")
        raise RuntimeError("edge blocked")

    def _piper(text, out_path, rate, model_name=audio_layer.DEFAULT_PIPER_MODEL):
        seen.append("piper")
        Path(out_path).write_bytes(b"\0" * 4096)
        return True

    monkeypatch.setattr(audio_layer, "_synth_edge", _edge)
    monkeypatch.setattr(audio_layer, "_synth_piper", _piper)
    out = str(tmp_path / "v.mp3")
    assert audio_layer.synthesize_voice("Xin chào", out, engine="auto") is True
    assert seen == ["edge", "piper"]


def test_synthesize_voice_edge_exception_inside_asyncio(tmp_path, monkeypatch):
    """edge_tts.Communicate ném lỗi thật (không mock _synth_edge) → rơi về piper."""

    class _BrokenCommunicate:
        def __init__(self, *a, **k):
            raise ConnectionError("no network")

    class _FakeEdge:
        Communicate = _BrokenCommunicate

    monkeypatch.setattr(audio_layer, "edge_tts", _FakeEdge)
    called = []
    monkeypatch.setattr(
        audio_layer, "_synth_piper",
        lambda text, out_path, rate, model_name=None: called.append(text) or True,
    )
    assert audio_layer.synthesize_voice("Xin chào", str(tmp_path / "v.mp3")) is True
    assert called == ["Xin chào"]


def test_synthesize_voice_all_engines_fail_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_layer, "_synth_edge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(audio_layer, "_synth_piper", lambda *a, **k: (_ for _ in ()).throw(OSError("y")))
    assert audio_layer.synthesize_voice("Xin chào", str(tmp_path / "v.mp3")) is False


def test_synthesize_voice_engine_edge_does_not_try_piper(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_layer, "_synth_edge", lambda *a, **k: False)
    piper_called = []
    monkeypatch.setattr(audio_layer, "_synth_piper", lambda *a, **k: piper_called.append(1) or True)
    assert audio_layer.synthesize_voice("Xin chào", str(tmp_path / "v.mp3"), engine="edge") is False
    assert piper_called == []


def test_synthesize_voice_normalizes_and_truncates(tmp_path, monkeypatch):
    captured: dict = {}

    def _edge(text, out_path, voice, rate):
        captured["text"] = text
        return True

    monkeypatch.setattr(audio_layer, "_synth_edge", _edge)
    long_text = "Tiếng Việt " * 400  # ~4400 ký tự
    assert audio_layer.synthesize_voice(long_text, str(tmp_path / "v.mp3")) is True
    assert len(captured["text"]) <= audio_layer.MAX_TEXT_CHARS
    assert audio_layer.synthesize_voice("   ", str(tmp_path / "v.mp3")) is False


# ---------------------------------------------------------------------------
# (d)/(e) apply
# ---------------------------------------------------------------------------

def test_apply_without_voice_and_music_returns_false_no_output(tmp_path, monkeypatch):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"\0" * 4096)
    out = tmp_path / "out.mp4"
    empty_music = tmp_path / "music"
    empty_music.mkdir()

    def _boom(*a, **k):
        raise AssertionError("ffmpeg must not be called")

    monkeypatch.setattr(audio_layer.subprocess, "run", _boom)
    assert audio_layer.apply(str(src), str(out), voice_text=None, music_dir=str(empty_music)) is False
    assert audio_layer.apply(str(src), str(out), voice_text="", music_dir=None) is False
    assert not out.exists()
    assert src.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_apply_voice_fails_music_ok_returns_true(tmp_path, monkeypatch):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"\0" * 4096)
    out = tmp_path / "out.mp4"
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").write_bytes(b"x")

    monkeypatch.setattr(audio_layer, "synthesize_voice", lambda *a, **k: False)
    mixed: list[tuple] = []

    def _mix_music(input_video, music_path, output_path, **kw):
        mixed.append((input_video, music_path))
        Path(output_path).write_bytes(b"\0" * 8192)
        return True

    monkeypatch.setattr(audio_layer, "mix_music", _mix_music)
    monkeypatch.setattr(audio_layer, "mix_voice", lambda *a, **k: pytest.fail("mix_voice must not run"))

    ok = audio_layer.apply(str(src), str(out), voice_text="Xin chào", music_dir=str(music_dir))
    assert ok is True
    assert out.exists() and out.stat().st_size == 8192
    # music trộn lên input gốc vì voice đã fail
    assert mixed == [(str(src), str(music_dir / "song.mp3"))]
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_apply_voice_then_music_chains_on_previous_step(tmp_path, monkeypatch):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"\0" * 4096)
    out = tmp_path / "out.mp4"
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").write_bytes(b"x")

    def _synth(text, out_path, **kw):
        Path(out_path).write_bytes(b"\0" * 2048)
        return True

    order: list[str] = []

    def _mix_voice(input_video, voice_path, output_path, **kw):
        order.append("voice:" + os.path.basename(input_video))
        Path(output_path).write_bytes(b"\0" * 4096)
        return True

    def _mix_music(input_video, music_path, output_path, **kw):
        order.append("music:" + os.path.basename(input_video))
        Path(output_path).write_bytes(b"\0" * 4096)
        return True

    monkeypatch.setattr(audio_layer, "synthesize_voice", _synth)
    monkeypatch.setattr(audio_layer, "mix_voice", _mix_voice)
    monkeypatch.setattr(audio_layer, "mix_music", _mix_music)

    assert audio_layer.apply(str(src), str(out), voice_text="Xin chào", music_dir=str(music_dir)) is True
    assert order == ["voice:in.mp4", "music:out.mp4.voice.tmp.mp4"]
    assert out.exists()
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_apply_missing_input_returns_false(tmp_path):
    assert audio_layer.apply(str(tmp_path / "nope.mp4"), str(tmp_path / "o.mp4"), voice_text="x") is False
