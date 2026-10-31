"""
PLAN-111 — giọng VieNeu cho bước dub: client ``tts`` engine ``vieneu`` + server ``vieneu_server`` (model giả).
PLAN-112 — giọng theo kênh: danh sách giọng, lưu ở kênh, bước dub dùng, API nghe thử.
Không gọi mạng: ``urlopen`` bị thay; server chỉ test hàm xử lý, không mở cổng.
"""
import io
import json
import urllib.error
import wave

import numpy as np
import pytest

from app.core.media import tts
from app.features.studio import dub, setup
from app.features.studio.dub import vieneu_server
from tests.test_studio_api import api  # noqa: F401 — fixture
from tests.test_studio_pipeline import _channel, db  # noqa: F401 — fixture

CATALOG = [
    {"name": "Ngọc Huyền", "gender": "female", "region": "Bắc", "description": "Nữ · Bắc"},
    {"name": "Hải Đăng", "gender": "male", "region": "Bắc", "description": "Nam · Bắc"},
    {"name": "Thái Sơn", "gender": "male", "region": "Nam", "description": "Nam · Nam"},
]


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
    engine = vieneu_server.Engine(_FakeTTS(), CATALOG)
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
    engine = vieneu_server.Engine(_FakeTTS(fail=True), CATALOG)
    code, _ctype, data = vieneu_server.handle_tts(engine, json.dumps({"text": "Chào", "voice": "Hải Đăng"}).encode())
    assert code == 500 and "RuntimeError" in json.loads(data)["error"]


# ── PLAN-112: giọng theo kênh ────────────────────────────────────────────────


def test_server_liet_ke_giong_kem_gioi_va_vung():
    class Model:
        _preset_voices = {
            "Ngọc Huyền": {"gender": "female", "region": "Bắc", "description": "Nữ · Bắc", "codes": "[...]"},
            "Thái Sơn": {"gender": "male", "description": "Nam · Nam · Phong cách tự nhiên"},  # thiếu region
        }

        def list_preset_voices(self):
            return [("⭐ Ngọc Huyền", "Ngọc Huyền"), ("Thái Sơn", "Thái Sơn"), ("Lạ", "Lạ")]

    assert vieneu_server.voice_catalog(Model()) == [
        {"name": "Ngọc Huyền", "gender": "female", "region": "Bắc", "description": "Nữ · Bắc"},
        {"name": "Thái Sơn", "gender": "male", "region": "Nam", "description": "Nam · Nam · Phong cách tự nhiên"},
        {"name": "Lạ", "gender": "", "region": "", "description": ""},
    ]


@pytest.fixture
def server(monkeypatch):
    """Server VieNeu giả: ``state["online"]`` bật / tắt; ghi lại giọng của mỗi lần đọc."""
    state = {"online": True, "read": []}

    def fake_urlopen(req, timeout):
        if not state["online"]:
            raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))
        if isinstance(req, str):
            assert req.endswith("/health")
            return _Resp(json.dumps({"ok": True, "voices": CATALOG}).encode())
        state["read"].append(json.loads(req.data)["voice"])
        return _Resp(_wav_bytes())

    monkeypatch.setattr(tts.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("VIENEU_TTS_URL", raising=False)
    setup._previews.clear()
    return state


def test_danh_sach_giong_server_tat_thi_rong(server):
    assert [v["name"] for v in tts.vieneu_voices()] == ["Ngọc Huyền", "Hải Đăng", "Thái Sơn"]
    server["online"] = False
    assert tts.vieneu_voices() == []


def test_synthesize_doc_dung_giong_chi_dinh(tmp_path, server):
    assert tts.synthesize("Chào", str(tmp_path / "a.wav"), voice="vi-VN-HoaiMyNeural", vieneu_voice="Thái Sơn")
    assert server["read"] == ["Thái Sơn"]


def test_kenh_luu_giong_chan_giong_la_server_tat_van_luu(db, server):  # noqa: F811
    ch = _channel(db)
    s = db.factory()
    assert setup.channel_row(setup.save_channel(s, {"dub_voice": " Thái Sơn "}, ch.id))["dub_voice"] == "Thái Sơn"
    with pytest.raises(setup.SetupError):
        setup.save_channel(s, {"dub_voice": "Không Có"}, ch.id)
    s.rollback()
    server["online"] = False
    assert setup.save_channel(s, {"dub_voice": "Giọng Mới"}, ch.id).dub_voice == "Giọng Mới"
    assert setup.save_channel(s, {"dub_voice": ""}, ch.id).dub_voice is None


def test_dub_lay_giong_kenh_va_gioi_cho_edge_du_phong(db, server):  # noqa: F811
    ch = _channel(db, dub_voice="Thái Sơn")
    assert dub._voice(ch, {"dub_voice": "female"}) == ("Thái Sơn", "male")
    assert dub._voice(None, {"dub_voice": "male"}) == (None, "male")
    server["online"] = False  # không biết giới của giọng → theo mẫu
    assert dub._voice(ch, {"dub_voice": "female"}) == ("Thái Sơn", "female")


def test_dub_giong_kenh_chi_cho_tieng_viet(tmp_path, server, monkeypatch):
    edge = []
    monkeypatch.setattr(tts, "_synth_edge", lambda text, out, voice, rate: edge.append(voice) or open(out, "wb").write(b"\0" * 4096))
    assert dub._synthesizer("vi", "Thái Sơn")("Chào", str(tmp_path / "a.wav"), "vi-VN-HoaiMyNeural")
    assert dub._synthesizer("en", "Thái Sơn")("Hi", str(tmp_path / "b.mp3"), "en-US-JennyNeural")
    assert server["read"] == ["Thái Sơn"] and edge == ["en-US-JennyNeural"]


def test_api_giong_va_nghe_thu(api, server):  # noqa: F811
    r = api.get("/studio/api/voices").json()
    assert r["online"] is True and len(r["voices"]) == 3
    r = api.post("/studio/api/voices/preview", json={"voice": "Hải Đăng"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
    api.post("/studio/api/voices/preview", json={"voice": "Hải Đăng"})
    assert server["read"] == ["Hải Đăng"]  # lần hai lấy bản đã đọc
    assert api.post("/studio/api/voices/preview", json={"voice": "Không Có"}).status_code == 400
    server["online"] = False
    assert api.get("/studio/api/voices").json() == {"online": False, "voices": []}
    assert api.post("/studio/api/voices/preview", json={"voice": "Thái Sơn"}).status_code == 400
