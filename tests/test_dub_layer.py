"""Tests cho app/features/viral_intake/dub_layer.py (ADR-060). Không mạng, không Demucs/Whisper/ffmpeg thật."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from app.features.viral_intake import dub_layer, subtitle_layer
from app.features.viral_intake.reup_processor import ReupProcessor

SR = dub_layer.SAMPLE_RATE
SEGMENTS = [
    {"start": 0.5, "end": 2.0, "text": "Xin chào các bạn"},
    {"start": 3.0, "end": 5.0, "text": "Hôm nay mình chia sẻ một mẹo nhỏ"},
]


# ─── (a) hàm thuần ───


def test_voice_for_gender_and_unknown_language():
    assert dub_layer.voice_for("en") == "en-US-AriaNeural"
    assert dub_layer.voice_for("en", "male") == "en-US-GuyNeural"
    assert dub_layer.voice_for("xx") == "vi-VN-HoaiMyNeural"


def test_slot_ends_reach_next_start_and_video_end():
    assert dub_layer.slot_ends(SEGMENTS, 8.0) == [3.0, 8.0]
    # Whisper trả end lố sang câu sau thì giữ end, không co lại
    overlap = [{"start": 0.0, "end": 4.0, "text": "a"}, {"start": 3.0, "end": 5.0, "text": "b"}]
    assert dub_layer.slot_ends(overlap, 6.0) == [4.0, 6.0]


def test_parse_translation_takes_json_array_with_exact_count():
    reply = 'Đây:\n```json\n["Hello friends", "  Today  I share a tip "]\n```'
    assert dub_layer.parse_translation(reply, 2) == ["Hello friends", "Today I share a tip"]
    assert dub_layer.parse_translation(reply, 3) is None
    assert dub_layer.parse_translation("không có json", 2) is None
    assert dub_layer.parse_translation('["", ""]', 2) is None
    assert dub_layer.parse_translation(None, 1) is None


def test_build_prompt_carries_languages_and_char_budget():
    prompt = dub_layer.build_translate_prompt([{"i": 0, "text": "Xin chào", "max_chars": 30}], "vi", "en")
    assert "from Vietnamese to English" in prompt
    assert "exactly 1 strings" in prompt
    assert '"max_chars": 30' in prompt


def test_translate_segments_batches_and_fails_whole_on_bad_batch(monkeypatch):
    monkeypatch.setattr(dub_layer, "TRANSLATE_BATCH", 1)
    prompts: list[str] = []

    def _ok(prompt):
        prompts.append(prompt)
        n = len(json.loads(prompt.split("Lines:\n", 1)[1]))
        return json.dumps(["x"] * n)

    ends = dub_layer.slot_ends(SEGMENTS, 8.0)
    assert dub_layer.translate_segments(SEGMENTS, ends, "vi", "en", _ok) == ["x", "x"]
    assert len(prompts) == 2
    # (khe 2,5 s − 0,25 s nghỉ) × 15 ký tự/giây tiếng Anh
    assert '"max_chars": 33' in prompts[0]

    calls = iter([json.dumps(["x"]), "lỗi"])
    assert dub_layer.translate_segments(SEGMENTS, ends, "vi", "en", lambda p: next(calls)) is None

    def _raise(_p):
        raise RuntimeError("AI down")

    assert dub_layer.translate_segments(SEGMENTS, ends, "vi", "en", _raise) is None


def test_tempo_capped_and_only_speeds_up():
    assert dub_layer.tempo_for(2.0, 3.0) == 1.0
    assert dub_layer.tempo_for(3.3, 3.0) == pytest.approx(1.1)
    assert dub_layer.tempo_for(9.0, 3.0) == dub_layer.MAX_SPEEDUP
    assert dub_layer.tempo_for(2.0, 0.0) == dub_layer.MAX_SPEEDUP  # đã trễ hết khe
    assert dub_layer.tempo_for(0.0, 0.0) == 1.0


def test_plan_line_keeps_gap_and_delays_instead_of_cutting():
    gap = dub_layer.GAP_SEC
    # vừa khe sau khi chừa nghỉ: không tăng tốc, bắt đầu đúng giờ gốc
    assert dub_layer.plan_line(1.0, 0.0, 5.0, 4.0 - gap) == (1.0, 1.0)
    # câu trước còn nói tới 2,0 s: lùi lại, khe ngắn đi nên tăng tốc nhẹ
    begin, tempo = dub_layer.plan_line(1.0, 2.0, 5.0, 3.0)
    assert begin == 2.0 and tempo == pytest.approx(3.0 / (3.0 - gap))


def test_fit_clip_trims_to_slot_with_fade():
    clip = np.ones((2, SR * 2), dtype=np.float32)
    assert dub_layer.fit_clip(clip, 3.0).shape[1] == SR * 2
    cut = dub_layer.fit_clip(clip, 1.0)
    assert cut.shape[1] == SR
    assert cut[0, -1] == 0.0 and cut[0, 0] == 1.0


def test_place_adds_at_offset_and_clips_overflow():
    track = np.zeros((2, SR * 2), dtype=np.float32)
    dub_layer.place(track, np.ones((2, SR), dtype=np.float32), 1.5)
    assert track[0, int(1.5 * SR)] == 1.0
    assert track[0, int(1.5 * SR) - 1] == 0.0
    dub_layer.place(track, np.ones((2, SR), dtype=np.float32), 5.0)  # ngoài track: không lỗi


# ─── (b) apply với mọi bước bên ngoài được giả lập ───


@pytest.fixture
def fake_media(monkeypatch):
    """ffmpeg/Demucs/Whisper giả; trả dict để test chỉnh hành vi."""
    state = {"separate": True, "segments": list(SEGMENTS), "lang": "vi", "speech_src": None}

    def _touch(path, size=4096):
        with open(path, "wb") as fh:
            fh.write(b"\0" * size)
        return True

    monkeypatch.setattr(dub_layer, "_probe_duration", lambda p: 8.0 if p.endswith(".mp4") else 1.0)
    monkeypatch.setattr(dub_layer, "_extract_audio", lambda v, w: _touch(w))
    monkeypatch.setattr(
        dub_layer, "separate",
        lambda a, v, b, duration=0.0: state["separate"] and _touch(v) and _touch(b),
    )

    def _transcribe(path, model=None, language="vi"):
        assert language is None  # thuyết minh luôn để Whisper tự nhận ngôn ngữ
        state["speech_src"] = os.path.basename(path)
        return list(state["segments"]), state["lang"]

    monkeypatch.setattr(subtitle_layer, "transcribe_segments", _transcribe)
    monkeypatch.setattr(dub_layer, "_decode", lambda p, f=None: np.full((2, SR * 8 if p.endswith(".wav") else SR), 0.1, dtype=np.float32))
    monkeypatch.setattr(dub_layer, "_mux", lambda v, a, out, d: _touch(out))
    return state


def _translate_all(prompt):
    n = len(json.loads(prompt.split("Lines:\n", 1)[1]))
    return json.dumps([f"line {i}" for i in range(n)])


def _synth_ok(text, out, voice):
    with open(out, "wb") as fh:
        fh.write(b"\0" * 4096)
    return True


def test_apply_success_returns_translated_segments(tmp_path, fake_media):
    out = str(tmp_path / "out.mp4")
    voices: list[str] = []

    def _synth(text, path, voice):
        voices.append(voice)
        return _synth_ok(text, path, voice)

    res = dub_layer.apply(
        "in.mp4", out, target_lang="en", translate=_translate_all, synthesize=_synth, voice_gender="male",
    )
    assert res.ok is True
    assert res.source_lang == "vi"
    assert [s["text"] for s in res.segments] == ["line 0", "line 1"]
    assert res.segments[0]["start"] == 0.5 and res.segments[0]["end"] == pytest.approx(1.5)
    assert voices == ["en-US-GuyNeural", "en-US-GuyNeural"]
    assert fake_media["speech_src"] == "vocals.wav"
    assert os.path.isfile(out)
    assert not [p for p in os.listdir(tmp_path) if p.startswith("dub_")]  # thư mục tạm đã xoá


def test_apply_without_demucs_dubs_over_original(tmp_path, fake_media):
    fake_media["separate"] = False
    res = dub_layer.apply("in.mp4", str(tmp_path / "out.mp4"), target_lang="en",
                          translate=_translate_all, synthesize=_synth_ok)
    assert res.ok is True
    assert fake_media["speech_src"] == "audio.wav"


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"lang": "en"}, "same language"),
        ({"segments": []}, "no speech"),
    ],
)
def test_apply_skips_without_output(tmp_path, fake_media, change, reason):
    fake_media.update(change)
    out = tmp_path / "out.mp4"
    res = dub_layer.apply("in.mp4", str(out), target_lang="en", translate=_translate_all, synthesize=_synth_ok)
    assert res.ok is False and res.reason == reason
    assert not out.exists()


def test_apply_translate_or_tts_failure_leaves_no_output(tmp_path, fake_media):
    out = tmp_path / "out.mp4"
    res = dub_layer.apply("in.mp4", str(out), target_lang="en", translate=lambda p: None, synthesize=_synth_ok)
    assert res.ok is False and res.reason == "translate failed"

    res = dub_layer.apply("in.mp4", str(out), target_lang="en", translate=_translate_all,
                          synthesize=lambda t, o, v: False)
    assert res.ok is False and res.reason.startswith("tts failed")
    assert not out.exists()


def test_apply_unknown_target_and_exceptions_never_raise(tmp_path, fake_media, monkeypatch):
    assert dub_layer.apply("in.mp4", str(tmp_path / "o.mp4"), target_lang="xx",
                           translate=_translate_all, synthesize=_synth_ok).ok is False

    def _boom(*a, **k):
        raise RuntimeError("whisper OOM")

    monkeypatch.setattr(subtitle_layer, "transcribe_segments", _boom)
    res = dub_layer.apply("in.mp4", str(tmp_path / "o.mp4"), target_lang="en",
                          translate=_translate_all, synthesize=_synth_ok)
    assert res.ok is False and "whisper OOM" in res.reason


# ─── (c) phụ đề nhận câu đã dịch ───


def test_subtitle_apply_uses_given_segments_without_whisper(tmp_path, monkeypatch):
    monkeypatch.setattr(subtitle_layer, "transcribe_words",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no whisper")))
    seen: dict = {}

    def _burn(inp, ass, out, fonts_dir):
        seen["ass"] = open(ass, encoding="utf-8").read()
        with open(out, "wb") as fh:
            fh.write(b"x" * 2048)
        return True

    monkeypatch.setattr(subtitle_layer, "burn", _burn)
    ok = subtitle_layer.apply("in.mp4", str(tmp_path / "o.mp4"),
                              segments=[{"start": 0.0, "end": 1.0, "text": "Hello friends"}])
    assert ok is True
    assert "Hello friends" in seen["ass"]


# ─── (d) điểm nối trong ReupProcessor ───


def test_post_layers_dub_then_subtitle_with_translated_segments(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    on = {"reup.dub_enabled", "reup.subtitle_enabled"}
    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key in on)
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)
    monkeypatch.setattr(runtime_settings, "get_str",
                        lambda key, default="", db=None: "en" if key == "reup.dub_target_lang" else default)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    translated = [{"start": 0.5, "end": 1.5, "text": "Hello"}]

    def _fake_dub(inp, out, **kw):
        assert kw["target_lang"] == "en"
        assert callable(kw["translate"]) and callable(kw["synthesize"])
        with open(out, "wb") as fh:
            fh.write(b"d" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return dub_layer.DubResult(True, "vi→en", "vi", translated)

    seen: dict = {}

    def _fake_sub(inp, out, **kw):
        seen["segments"] = kw["segments"]
        with open(out, "wb") as fh:
            fh.write(b"s" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return True

    monkeypatch.setattr(dub_layer, "apply", _fake_dub)
    monkeypatch.setattr(subtitle_layer, "apply", _fake_sub)

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"old")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics) == str(current)
    assert metrics["dub_applied"] is True and metrics["dub_source_lang"] == "vi"
    assert metrics["subtitle_applied"] is True
    assert seen["segments"] == translated


def test_post_layers_dub_skipped_subtitle_falls_back_to_whisper(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    on = {"reup.dub_enabled", "reup.subtitle_enabled"}
    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key in on)
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)
    monkeypatch.setattr(runtime_settings, "get_str", lambda key, default="", db=None: default)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    monkeypatch.setattr(dub_layer, "apply", lambda *a, **k: dub_layer.DubResult(False, "same language", "vi"))
    seen: dict = {}
    monkeypatch.setattr(subtitle_layer, "apply", lambda inp, out, **kw: seen.update(kw) or False)

    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(current, current, metrics=metrics) == current
    assert metrics["dub_applied"] is False and metrics["dub_reason"] == "same language"
    assert seen["segments"] is None
