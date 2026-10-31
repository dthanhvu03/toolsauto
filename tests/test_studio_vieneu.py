"""
PLAN-111 — giọng VieNeu cho bước dub: client ``tts`` engine ``vieneu`` + server ``vieneu_server`` (model giả).
Không gọi mạng: ``urlopen`` bị thay; server chỉ test hàm xử lý, không mở cổng.
"""
import io
import json
import urllib.error
import wave

import numpy as np
import pytest

from app.core.media import tts
from app.features.studio.dub import vieneu_server


def _wav_bytes(seconds: float = 0.5, rate: int = 48000) -> bytes:
    return vieneu_server.to_wav(np.zeros(int(seconds * rate), dtype=np.float32), rate)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def calls(monkeypatch):
    seen = {"vieneu": [], "edge": 0}

    def fake_urlopen(req, timeout):
        seen["vieneu"].append(json.loads(req.data))
        return _Resp(_wav_bytes())

    def fake_edge(text, out_path, voice, rate):
        seen["edge"] += 1
        with open(out_path, "wb") as f:
            f.write(b"\0" * 4096)
        return True

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tts, "_synth_edge", fake_edge)
    monkeypatch.delenv("VIENEU_TTS_URL", raising=False)
    return seen


def test_quy_giong_edge_viet_ve_giong_vieneu_cung_gioi():
    assert tts._vieneu_voice("vi-VN-HoaiMyNeural") == tts.VIENEU_FEMALE
    assert tts._vieneu_voice("vi-VN-NamMinhNeural") == tts.VIENEU_MALE
    assert tts._vieneu_voice("en-US-JennyNeural") is None
    assert tts._vieneu_voice("Quang Sơn") == "Quang Sơn"
    assert tts._vieneu_voice("") == tts.VIENEU_FEMALE


def test_auto_doc_bang_vieneu_truoc_khong_goi_edge(tmp_path, calls):
    out = tmp_path / "line.wav"
    assert tts.synthesize("Xin chào các bạn", str(out), voice="vi-VN-NamMinhNeural") is True
    assert calls["vieneu"] == [{"text": "Xin chào các bạn", "voice": tts.VIENEU_MALE}]
    assert calls["edge"] == 0
    with wave.open(str(out)) as w:
        assert w.getframerate() == 48000
    assert not list(tmp_path.glob("*.tmp.wav"))


def test_vieneu_ra_mp3_qua_ffmpeg_va_xoa_file_tam(tmp_path, calls):
    out = tmp_path / "line_000.mp3"
    assert tts.synthesize("Một câu", str(out), voice="vi-VN-HoaiMyNeural") is True
    assert out.stat().st_size > 0 and calls["edge"] == 0
    assert not list(tmp_path.glob("*.tmp.wav"))


def test_server_tat_thi_ve_edge(tmp_path, calls, monkeypatch):
    def refused(req, timeout):
        raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))

    monkeypatch.setattr(tts.urllib.request, "urlopen", refused)
    assert tts.synthesize("Xin chào", str(tmp_path / "a.mp3"), voice="vi-VN-HoaiMyNeural") is True
    assert calls["edge"] == 1


def test_server_bao_loi_thi_ve_edge(tmp_path, calls, monkeypatch):
    def bad(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {}, io.BytesIO(b'{"error":"doc hong"}'))

    monkeypatch.setattr(tts.urllib.request, "urlopen", bad)
    assert tts.synthesize("Xin chào", str(tmp_path / "a.mp3"), voice="vi-VN-HoaiMyNeural") is True
    assert calls["edge"] == 1


def test_giong_ngoai_ngu_va_url_rong_khong_goi_vieneu(tmp_path, calls, monkeypatch):
    assert tts.synthesize("Hello", str(tmp_path / "a.mp3"), voice="en-US-JennyNeural") is True
    monkeypatch.setenv("VIENEU_TTS_URL", "")
    assert tts.synthesize("Xin chào", str(tmp_path / "b.mp3"), voice="vi-VN-HoaiMyNeural") is True
    assert calls["vieneu"] == [] and calls["edge"] == 2


def test_engine_vieneu_rieng_khong_roi_xuong_edge(tmp_path, calls, monkeypatch):
    monkeypatch.setenv("VIENEU_TTS_URL", "")
    assert tts.synthesize("Xin chào", str(tmp_path / "a.mp3"), engine="vieneu") is False
    assert calls["edge"] == 0


class _FakeTTS:
    sample_rate = 48000

    def __init__(self, fail=False):
        self.fail = fail

    def infer(self, text, voice):
        if self.fail:
            raise RuntimeError("CUDA out of memory")
        return np.sin(np.linspace(0, 100, 4800)).astype(np.float32)


def test_server_doc_ra_wav_va_chan_dau_vao_sai():
    engine = vieneu_server.Engine(_FakeTTS(), ["Ngọc Huyền", "Hải Đăng"])
    code, ctype, data = vieneu_server.handle_tts(engine, json.dumps({"text": "Chào", "voice": "Ngọc Huyền"}).encode())
    assert (code, ctype) == (200, "audio/wav")
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 48000, 4800)

    def status(body: bytes) -> int:
        return vieneu_server.handle_tts(engine, body)[0]

    assert status(b"not json") == 400
    assert status(json.dumps({"text": " ", "voice": "Ngọc Huyền"}).encode()) == 400
    assert status(json.dumps({"text": "Chào", "voice": "Không Có"}).encode()) == 400
    assert status(json.dumps({"text": "a" * 1501, "voice": "Hải Đăng"}).encode()) == 400


def test_server_model_loi_tra_500_khong_chet():
    engine = vieneu_server.Engine(_FakeTTS(fail=True), ["Hải Đăng"])
    code, _ctype, data = vieneu_server.handle_tts(engine, json.dumps({"text": "Chào", "voice": "Hải Đăng"}).encode())
    assert code == 500 and "RuntimeError" in json.loads(data)["error"]
