"""
ADR-061 / PLAN-106 P2 — lõi lồng tiếng của Studio: ffmpeg thật, Demucs / Whisper / AI / TTS giả.
Không gọi mạng.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import wave

import pytest

from app.core.media import speech
from app.core.media.ffmpeg_path import ffmpeg_available
from app.features.studio.dub import engine

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="cần ffmpeg")

SEGMENTS = [{"start": 0.5, "end": 2.0, "text": "你好"}, {"start": 3.0, "end": 5.0, "text": "今天"}]


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=120)


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("dub_src") / "zh.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path))
    return str(path)


@pytest.fixture
def fakes(monkeypatch):
    state = {"separate": True, "segments": list(SEGMENTS), "lang": "zh", "speech_src": None}

    def separate(audio, vocals, background, duration=0.0):
        if not state["separate"]:
            return False
        shutil.copy(audio, vocals)
        shutil.copy(audio, background)
        return True

    def transcribe(path, model=None, language="vi"):
        assert language is None
        state["speech_src"] = path.rsplit("/", 1)[-1]
        return list(state["segments"]), state["lang"]

    monkeypatch.setattr(engine, "separate", separate)
    monkeypatch.setattr(engine.speech, "transcribe", transcribe)
    return state


def _translate(prompt: str) -> str:
    n = len(json.loads(prompt.split("Lines:\n", 1)[1]))
    return json.dumps([f"câu {i}" for i in range(n)], ensure_ascii=False)


def _synth(text: str, out: str, voice: str) -> bool:
    _ff("-f", "lavfi", "-i", "sine=frequency=880:duration=1", out)
    return True


def _seconds(path: str) -> float:
    with wave.open(path, "rb") as f:
        return f.getnframes() / f.getframerate()


def test_ra_hai_file_tieng_dai_bang_video_va_cau_da_dich(tmp_path, video, fakes):
    res = engine.make_tracks(video, str(tmp_path), target_lang="vi", translate=_translate, synthesize=_synth)
    assert res.ok, res.reason
    assert res.source_lang == "zh" and res.background_volume == 1.0
    assert fakes["speech_src"] == "vocals.wav"
    assert [x["text"] for x in res.lines] == ["câu 0", "câu 1"] and res.lines[0]["start"] == 0.5
    assert _seconds(res.voice_wav) == pytest.approx(6.0, abs=0.1)
    assert res.background_wav.endswith("background.wav")


def test_khong_tach_duoc_giong_thi_nen_la_tieng_goc_ha_nho(tmp_path, video, fakes):
    fakes["separate"] = False
    res = engine.make_tracks(video, str(tmp_path), translate=_translate, synthesize=_synth)
    assert res.ok and res.background_volume == engine.FALLBACK_BACKGROUND_VOLUME
    assert fakes["speech_src"] == "background.wav"


@pytest.mark.parametrize("change, reason", [({"lang": "vi"}, "đã đúng ngôn ngữ đích"), ({"segments": []}, "không có lời thoại")])
def test_khong_can_long(tmp_path, video, fakes, change, reason):
    fakes.update(change)
    res = engine.make_tracks(video, str(tmp_path), translate=_translate, synthesize=_synth)
    assert not res.ok and res.reason == reason


def test_dich_hoac_doc_hong_bao_ly_do_de_thu_lai(tmp_path, video, fakes):
    res = engine.make_tracks(video, str(tmp_path), translate=lambda p: None, synthesize=_synth)
    assert not res.ok and res.reason == "dịch hỏng"
    res = engine.make_tracks(video, str(tmp_path), translate=_translate, synthesize=lambda t, o, v: False)
    assert not res.ok and res.reason.startswith("đọc hỏng")


def test_khong_bao_gio_nem_loi(tmp_path, video, fakes, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("whisper OOM")

    monkeypatch.setattr(engine.speech, "transcribe", boom)
    res = engine.make_tracks(video, str(tmp_path), translate=_translate, synthesize=_synth)
    assert not res.ok and "whisper OOM" in res.reason
    assert not engine.make_tracks(video, str(tmp_path), target_lang="xx", translate=_translate, synthesize=_synth).ok


def test_bo_loc_cau_bia_port_sang_core_van_chay():
    assert speech.clean_hallucinations_from_text("Hãy đăng ký kênh Ghiền Mì Gõ nhé") == ""
    kept = speech.keep_speech_segments([
        {"start": 0, "end": 1, "text": "Xin chào các bạn"},
        {"start": 1, "end": 2, "text": "nhạc", "no_speech_prob": 0.9},
        {"start": 2, "end": 3, "text": "Bấm like và share nhé"},
    ])
    assert [x["text"] for x in kept] == ["Xin chào các bạn"]
