"""
Test lớp phụ đề (ADR-016). Không gọi Whisper thật, không gọi ffmpeg thật
trừ khi có mock. Điểm nối `_apply_post_layers` với setting tắt phải trả về
đúng đường dẫn cũ và không đụng subtitle_layer.
"""
from __future__ import annotations

import os
import subprocess

import pysubs2

from app.features.viral_intake import subtitle_layer
from app.features.viral_intake.reup_processor import ReupProcessor


SEGMENTS = [
    {"start": 0.5, "end": 2.0, "text": "Xin chào các bạn"},
    {
        "start": 2.0,
        "end": 8.0,
        "text": "Hôm nay mình sẽ chia sẻ một mẹo nhỏ giúp da sáng mịn hơn chỉ sau ba ngày dùng thử",
    },
]


# ─── (a) build_ass ───


def test_build_ass_style_and_wrapping(tmp_path):
    out = tmp_path / "t.ass"
    path = subtitle_layer.build_ass(SEGMENTS, str(out), max_chars=22)
    assert path == str(out)
    assert out.is_file()

    subs = pysubs2.load(str(out))
    style = subs.styles["Default"]
    assert style.fontname == "Be Vietnam Pro"
    assert style.alignment == pysubs2.Alignment.BOTTOM_CENTER
    assert style.bold is True
    assert style.outline == 3.0
    assert style.shadow == 1.0
    assert style.marginv == 260
    assert subs.info["PlayResX"] == "1080"
    assert subs.info["PlayResY"] == "1920"

    events = list(subs.events)
    # Segment 1 nguyên vẹn, đúng thời gian
    assert events[0].text == "Xin chào các bạn"
    assert events[0].start == 500
    assert events[0].end == 2000

    # Mọi dòng ≤ max_chars, mỗi event ≤ 2 dòng
    for ev in events:
        lines = ev.text.split("\\N")
        assert 1 <= len(lines) <= 2
        for line in lines:
            assert len(line) <= 22, line

    # Segment 2 (79 ký tự) buộc phải tách nhiều event, chia đều 2.0→8.0 liên tục
    tail = events[1:]
    assert len(tail) >= 2
    assert tail[0].start == 2000
    assert tail[-1].end == 8000
    for prev, nxt in zip(tail, tail[1:]):
        assert prev.end == nxt.start
    joined = " ".join(ev.text.replace("\\N", " ") for ev in tail)
    assert joined == SEGMENTS[1]["text"]


def test_build_ass_normalizes_nfc(tmp_path):
    # "ệ" dạng tách (e + U+0302 + U+0323) phải thành một codepoint NFC (U+1EC7) trong file ASS
    decomposed = "Việt Nam"
    assert len(decomposed) == 10
    out = tmp_path / "nfc.ass"
    subtitle_layer.build_ass([{"start": 0, "end": 1, "text": decomposed}], str(out))
    subs = pysubs2.load(str(out))
    assert subs.events[0].text == "Việt Nam"


# ─── (b) escape path ───


def test_escape_filter_path_windows():
    assert subtitle_layer._escape_filter_path("C:\\a b\\x.ass") == "'C\\:/a b/x.ass'"
    assert subtitle_layer._escape_filter_path("/srv/x.ass") == "'/srv/x.ass'"


# ─── (c) apply với transcript rỗng ───


def test_apply_returns_false_without_segments(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(subtitle_layer, "transcribe_words", lambda *a, **k: [])
    monkeypatch.setattr(
        subtitle_layer, "burn", lambda *a, **k: calls.append("burn") or True
    )
    out = tmp_path / "out.mp4"
    assert subtitle_layer.apply(str(tmp_path / "in.mp4"), str(out)) is False
    assert not out.exists()
    assert calls == []
    assert not (tmp_path / "out.sub.tmp.ass").exists()


# ─── (d) apply khi ffmpeg ném lỗi → False, không raise, không để rác ───


def test_apply_swallows_ffmpeg_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(subtitle_layer, "transcribe_words", lambda *a, **k: SEGMENTS)

    def _boom(*a, **k):
        raise OSError("ffmpeg exploded")

    monkeypatch.setattr(subprocess, "run", _boom)
    out = tmp_path / "out.mp4"
    assert subtitle_layer.apply(str(tmp_path / "in.mp4"), str(out), fonts_dir=str(tmp_path)) is False
    assert not out.exists()
    assert not (tmp_path / "out.sub.tmp.ass").exists()


def test_burn_returns_false_on_nonzero_exit(tmp_path, monkeypatch):
    class _R:
        returncode = 1
        stderr = "bad"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    ass = tmp_path / "x.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    assert subtitle_layer.burn(str(tmp_path / "in.mp4"), str(ass), str(tmp_path / "o.mp4"), fonts_dir=str(tmp_path)) is False


# ─── (e) điểm nối: setting tắt ⇒ đường đi cũ y nguyên ───


def test_post_layers_disabled_keeps_path_and_skips_layer(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: False)

    def _must_not_call(*a, **k):
        raise AssertionError("subtitle_layer.apply must not be called when disabled")

    monkeypatch.setattr(subtitle_layer, "apply", _must_not_call)
    monkeypatch.setattr(ReupProcessor, "_get_video_info", staticmethod(_must_not_call))

    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    result = ReupProcessor._apply_post_layers(current, current, page_url=None, metrics=metrics)
    assert result == current
    assert metrics == {"subtitle_enabled": False, "audio_voice_enabled": False, "audio_music_enabled": False}
    assert not os.path.exists(current + ".with_sub.tmp.mp4")


def test_post_layers_enabled_but_layer_fails_keeps_previous(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.subtitle_enabled")
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)
    monkeypatch.setattr(subtitle_layer, "apply", lambda *a, **k: False)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )

    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(current, current, metrics=metrics) == current
    assert metrics["subtitle_enabled"] is True
    assert metrics["subtitle_applied"] is False


def test_post_layers_enabled_success_promotes_tmp(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.subtitle_enabled")
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"old")

    def _fake_apply(inp, out, **kw):
        assert kw == {"font_size": 64, "margin_v": 260}
        with open(out, "wb") as fh:
            fh.write(b"x" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return True

    monkeypatch.setattr(subtitle_layer, "apply", _fake_apply)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    metrics: dict = {}
    result = ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics)
    assert result == str(current)
    assert metrics["subtitle_applied"] is True
    assert current.stat().st_size > 3  # đã bị thay bằng file có phụ đề
    assert not (tmp_path / "video_reup.mp4.with_sub.tmp.mp4").exists()


# ─── (f) lớp âm thanh nối cùng điểm ───


def test_post_layers_audio_reads_hook_text_and_promotes(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings
    from app.features.viral_intake import audio_layer

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.audio_voice_enabled")
    monkeypatch.setattr(runtime_settings, "get_str", lambda key, default="", db=None: default)
    monkeypatch.setattr(subtitle_layer, "apply", lambda *a, **k: (_ for _ in ()).throw(AssertionError("subtitle off")))

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"old")
    seen: dict = {}

    def _fake_audio(inp, out, **kw):
        seen.update(kw)
        with open(out, "wb") as fh:
            fh.write(b"x" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return True

    monkeypatch.setattr(audio_layer, "apply", _fake_audio)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    metrics: dict = {"hook_text": "Xem ngay nhé"}
    result = ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics)
    assert result == str(current)
    assert metrics["audio_applied"] is True
    assert seen["voice_text"] == "Xem ngay nhé"
    assert seen["music_dir"] is None  # nhạc tắt
    assert seen["voice_engine"] == "auto"
    assert not (tmp_path / "video_reup.mp4.with_audio.tmp.mp4").exists()


def test_post_layers_audio_fail_keeps_previous(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings
    from app.features.viral_intake import audio_layer

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.audio_music_enabled")
    monkeypatch.setattr(runtime_settings, "get_str", lambda key, default="", db=None: default)
    monkeypatch.setattr(audio_layer, "apply", lambda *a, **k: False)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(current, current, metrics=metrics) == current
    assert metrics["audio_applied"] is False
