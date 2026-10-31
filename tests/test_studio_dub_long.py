"""
PLAN-118 — lồng tiếng video dài: Demucs tách theo khúc (RAM cỡ một khúc), dùng lời thoại của bước phân tích khi Demucs hỏng,
chỉ lưu cố định kết quả chắc chắn, nút «Lồng tiếng lại». Model Demucs giả (không tải model), ffmpeg thật, không mạng.
"""
from __future__ import annotations

import wave

import numpy as np
import pytest

from app.features.studio.dub import engine, separate as sep
from app.features.studio.dub.engine import DubTracks
from tests.test_studio_pipeline import db, media  # noqa: F401 — fixture

SR = sep.SAMPLE_RATE


def _write(path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).T.copy().tobytes())


def _read(path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).reshape(-1, 2).T.astype(np.float32) / 32768


class _Model:
    sources = ["drums", "bass", "other", "vocals"]
    calls: list[int] = []

    def eval(self):
        return self


def _fake_apply(model, mix, device, **kw):
    """«Giọng» = đúng tín hiệu vào, 3 lớp còn lại = 0 → sau khi bỏ chuẩn hoá giọng ra phải bằng tín hiệu vào."""
    import torch

    _Model.calls.append(mix.shape[-1])
    out = torch.zeros((1, 4, *mix.shape[1:]))
    out[0, 3] = mix[0]
    return out


@pytest.mark.parametrize("seconds", [0.3, 2.35])  # ngắn hơn 1 khúc / nhiều khúc + khúc cuối lẻ
def test_tach_theo_khuc_ghep_lien_mach_dung_do_dai(tmp_path, monkeypatch, seconds):
    monkeypatch.setattr(sep, "get_model", lambda name: _Model())
    monkeypatch.setattr(sep, "apply_model", _fake_apply)
    monkeypatch.setattr(sep, "CHUNK_SEC", 0.5)
    monkeypatch.setattr(sep, "OVERLAP_SEC", 0.1)
    _Model.calls.clear()
    t = np.arange(int(seconds * SR)) / SR
    audio = np.stack([0.4 * np.sin(2 * np.pi * 220 * t), 0.3 * np.sin(2 * np.pi * 330 * t)]).astype(np.float32)
    _write(tmp_path / "in.wav", audio)
    sep.separate(str(tmp_path / "in.wav"), str(tmp_path / "v.wav"), str(tmp_path / "b.wav"))
    vocals, background = _read(tmp_path / "v.wav"), _read(tmp_path / "b.wav")
    assert vocals.shape == background.shape == audio.shape  # không thừa / thiếu mẫu nào ở chỗ nối
    assert np.abs(vocals - audio).max() < 2e-3  # crossfade hai bản giống nhau = chính nó
    assert max(_Model.calls) <= int(0.6 * SR) + 1  # mỗi lần chỉ đưa một khúc (+ phần chồng) vào model
    assert len(_Model.calls) == int(np.ceil(seconds / 0.5))


def _tracks_env(monkeypatch, tmp_path, *, separated: bool, heard: list[dict]):
    calls = {"transcribe": 0, "translate": []}
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 6.0)
    monkeypatch.setattr(engine, "_extract_audio", lambda src, dst: _write(dst, np.zeros((2, SR), np.float32)) or True)

    def fake_separate(audio, vocals, background, duration=0.0):
        if separated:
            _write(vocals, np.zeros((2, SR), np.float32))
            _write(background, np.zeros((2, SR), np.float32))
        return separated

    def fake_transcribe(path, **kw):
        calls["transcribe"] += 1
        return heard, ("zh" if heard else None)

    monkeypatch.setattr(engine, "separate", fake_separate)
    monkeypatch.setattr(engine.speech, "transcribe", fake_transcribe)
    return calls


HINT = [{"start": 1.0, "end": 2.5, "text": "你好"}, {"start": 3.0, "end": 4.0, "text": "谢谢"}]


@pytest.mark.parametrize(("separated", "heard", "whisper_calls"), [
    (False, [], 0),  # Demucs hỏng → dùng luôn lời của bước phân tích, không nghe lại
    (True, [], 1),  # tách được nhưng nghe lại ra rỗng → lùi về lời của bước phân tích
])
def test_make_tracks_dung_loi_thoai_goi_y(tmp_path, monkeypatch, separated, heard, whisper_calls):
    calls = _tracks_env(monkeypatch, tmp_path, separated=separated, heard=heard)

    def translate(prompt):
        calls["translate"].append(prompt)
        return None  # dừng ở bước dịch — đủ để biết đã qua chỗ «không có lời thoại»

    res = engine.make_tracks("in.mp4", str(tmp_path), translate=translate, synthesize=lambda *a: False,
                             hint_segments=HINT, hint_lang="zh")
    assert isinstance(res, DubTracks) and res.source_lang == "zh"
    assert res.reason == "dịch hỏng" and calls["translate"]
    assert calls["transcribe"] == whisper_calls


def test_khong_co_goi_y_van_nghe_lai_nhu_cu(tmp_path, monkeypatch):
    calls = _tracks_env(monkeypatch, tmp_path, separated=False, heard=[])
    res = engine.make_tracks("in.mp4", str(tmp_path), translate=lambda p: None, synthesize=lambda *a: False)
    assert res.reason == "không có lời thoại" and calls["transcribe"] == 1


# ── lưu kết quả dub + «Lồng tiếng lại» (pipeline thật, dub giả) ─────────────────────────────────────


@pytest.fixture
def zh(monkeypatch):
    from app.features.studio import analyze

    monkeypatch.setattr(analyze.speech, "transcribe", lambda path, **kw: ([{"start": 1, "end": 3, "text": "你好"}], "zh"))


def test_dub_hong_hien_canh_bao_long_lai_giu_ky_thuat(db, media, zh, monkeypatch):  # noqa: F811
    from app.core.database.models import StudioAnalysis, StudioProject
    from app.features.studio import dub, editor, pipeline, progress
    from app.features.studio.contracts import ProjectStatus
    from tests.test_studio_pipeline import _drain, _fake_tracks

    calls: list = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls, "không có lời thoại"))
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "origin": "reup",
                                          "params": {"dub": True, "dub_lang": "vi", "hook": "Xem hết nha"}})
    _drain(db)
    old = db.query(StudioProject).one()
    job = progress.jobs(db)["jobs"][0]
    dub_step = next(s for s in job["steps"] if s["stage"] == "dub")
    assert dub_step["status"] == "warn" and "⚠ Lồng tiếng: không có lời thoại" in job["summary"]
    cached = db.query(StudioAnalysis).filter_by(asset_id=old.asset_id, kind="dub").one().data
    assert cached["retry"] is True  # hỏng không chắc chắn → không khoá cứng
    state = editor.detail(db, old.id)["dub"]
    assert state == {**state, "speech_lang": "zh", "dubbed": False, "can_redub": True, "reason": "không có lời thoại"}

    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls))
    editor.redub(db, old.id)
    _drain(db)
    db.refresh(old)
    new = db.query(StudioProject).order_by(StudioProject.id.desc()).first()
    assert old.status == ProjectStatus.REJECTED and new.id != old.id and new.status == ProjectStatus.REVIEW
    assert len(new.spec["clips"][0]["audio"]) == 2 and new.spec["subtitles"]["source"] == "dub"
    assert new.spec["texts"][0]["text"] == "Xem hết nha"  # giữ kỹ thuật cũ
    assert calls == ["vi", "vi"]
    assert db.query(StudioAnalysis).filter_by(asset_id=old.asset_id, kind="dub").count() == 1  # cập nhật, không thêm dòng
    assert editor.detail(db, new.id)["dub"]["dubbed"] is True


@pytest.mark.parametrize(("cached", "rerun"), [
    ({"ok": False, "reason": "không có lời thoại"}, True),  # bản lưu trước PLAN-118, mà phân tích có lời → chạy lại
    ({"ok": False, "reason": "dịch hỏng", "retry": True}, True),
    ({"ok": False, "reason": "đã đúng ngôn ngữ đích"}, False),
    ({"ok": False, "reason": "không có tiếng", "retry": False}, False),
])
def test_quy_tac_chay_lai_dub(db, media, zh, monkeypatch, cached, rerun):  # noqa: F811
    from app.core.database.models import StudioAnalysis
    from app.features.studio import dub, pipeline, store
    from tests.test_studio_pipeline import _drain, _fake_tracks

    asset, _ = store.add_asset(db, media["clip"], kind="video", origin="reup", has_audio=True, duration=6.0)
    db.add(StudioAnalysis(asset_id=asset.id, kind="dub", data=cached))
    db.commit()
    calls: list = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls))
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "origin": "reup", "params": {"dub": True}})
    _drain(db)
    assert bool(calls) is rerun


def test_lam_lai_bi_chan_khi_video_tieng_viet(db, media, monkeypatch):  # noqa: F811
    from app.core.database.models import StudioProject
    from app.features.studio import editor, pipeline
    from tests.test_studio_pipeline import _drain

    pipeline.start(db, "upload", payload={"path": str(media["clip"])})  # transcript giả của fixture: tiếng Việt
    _drain(db)
    p = db.query(StudioProject).one()
    assert editor.detail(db, p.id)["dub"]["can_redub"] is False
    with pytest.raises(editor.EditError, match="tiếng Việt"):
        editor.redub(db, p.id)
