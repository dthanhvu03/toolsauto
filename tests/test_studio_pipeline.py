"""
ADR-061 — quy trình Studio chạy thật: SQLite tạm, ffmpeg thật trên clip tạo bằng lavfi.
Chỉ Whisper, AI caption và lồng tiếng bị thay (nạp model mất hàng chục giây, AI / TTS cần mạng).
Không gọi mạng.
"""
from __future__ import annotations

import io
import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as app_config
from app.constants import JobStatus, ViralStatus
from app.core.database.models import (
    Base,
    Job,
    StudioAnalysis,
    StudioAsset,
    StudioChannel,
    StudioProject,
    StudioTask,
    StudioTemplate,
    ViralMaterial,
)
from app.core.media.ffmpeg_path import ffmpeg_available
from app.core.notifier.service import NotifierService
from app.features.studio import analyze, caption, dub, entry, paths, pipeline, queue, worker
from app.features.studio.contracts import Lane, ProjectStatus, StageError, TaskStatus
from app.features.studio.dub.engine import DubTracks
from app.features.studio.publish import status as publish_status
from app.features.viral_intake.service import ViralService

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="cần ffmpeg")

STUDIO_TABLES = [m.__table__ for m in (StudioAsset, StudioAnalysis, StudioTemplate, StudioChannel, StudioProject, StudioTask,
                                        ViralMaterial, Job)]  # 2 bảng cuối: cầu nối Buffer (P3)


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=120)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("studio_src")
    clip = d / "ngang.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(clip))
    mute = d / "khong_tieng.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=25:duration=3", "-c:v", "libx264", "-preset", "ultrafast", str(mute))
    logo = d / "logo.png"
    _ff("-f", "lavfi", "-i", "color=c=red:size=200x200", "-frames:v", "1", str(logo))
    music = d / "nhac.mp3"
    _ff("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(music))
    return {"clip": clip, "mute": mute, "logo": logo, "music": music}


class _FakeCaptioner:
    calls: list = []
    fail = False

    def generate_caption(self, video_path, **kw):
        type(self).calls.append((video_path, kw))
        if type(self).fail:
            raise RuntimeError("Gemini 503")
        return {"caption": "Mẹo nhỏ hôm nay", "hashtags": ["meo", "#doisong", "  "]}


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'studio.sqlite'}")
    Base.metadata.create_all(engine, tables=STUDIO_TABLES)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(paths, "ROOT", tmp_path / "studio")
    monkeypatch.setattr(app_config, "REUP_DIR", tmp_path / "reup")
    # import app.main ở test khác có thể đã đăng ký Telegram thật — không bao giờ gửi tin từ test
    monkeypatch.setattr(NotifierService, "_channels", [])
    monkeypatch.setattr(
        analyze.speech, "transcribe",
        lambda path, **kw: ([{"start": 0.5, "end": 2.0, "text": "xin chào các bạn", "no_speech_prob": 0.1},
                             {"start": 2.5, "end": 4.5, "text": "hôm nay làm mẹo nhỏ"}], "vi"),
    )
    monkeypatch.setattr(caption, "ContentOrchestrator", _FakeCaptioner)
    monkeypatch.setattr(caption.runtime_settings, "get_str", lambda key, default="", db=None: default)
    _FakeCaptioner.calls.clear()
    _FakeCaptioner.fail = False
    session = factory()
    session.factory = factory
    yield session
    session.close()
    engine.dispose()


def _drain(db, lanes=(Lane.HEAVY, Lane.LIGHT), limit=50) -> int:
    n = 0
    while n < limit:
        task = queue.claim(db, lanes=list(lanes), worker_id="test")
        if task is None:
            return n
        pipeline.run_task(db, task)
        n += 1
    raise AssertionError("hàng việc không cạn")


def _channel(db, **kw) -> StudioChannel:
    ch = StudioChannel(buffer_channel_id=kw.pop("buffer_channel_id", "buf-1"), name="Uyển Nhi", **kw)
    db.add(ch)
    db.commit()
    return ch


def _brand(db, path) -> int:
    pipeline.start(db, "brand", payload={"path": str(path), "origin": "brand"})
    _drain(db)
    return db.query(StudioAsset).order_by(StudioAsset.id.desc()).first().id


def _probe_duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def test_upload_chay_het_quy_trinh_va_dung_o_cho_duyet(db, media):
    logo_id = _brand(db, media["logo"])
    music_id = _brand(db, media["music"])
    tpl = StudioTemplate(name="Mẹo", kind="basic",
                         params={"hook": "Mẹo 3 giây", "music_asset_id": music_id, "max_len": 5, "trim_head": 0.5})
    db.add(tpl)
    db.commit()
    ch = _channel(db, template_id=tpl.id, logo_asset_id=logo_id)

    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "channel_id": ch.id, "credit": "@tacgia"})
    assert _drain(db) == 7

    project = db.query(StudioProject).one()
    assert project.status == ProjectStatus.REVIEW
    assert project.channel_id == ch.id and project.template_id == tpl.id
    assert project.spec["subtitles"]["enabled"] is True
    assert project.spec["credit"] == "Nguồn: @tacgia"
    assert project.spec["clips"] == [{"asset": project.asset_id, "start": 0.5, "end": 5.5, "audio": [], "hflip": False}]
    assert _probe_duration(project.output_path) == pytest.approx(5.0, abs=0.15)
    assert project.duration == pytest.approx(5.0, abs=0.15)
    assert project.caption == "Mẹo nhỏ hôm nay" and project.hashtags == ["#meo", "#doisong"]
    assert _FakeCaptioner.calls[0][0] == project.output_path
    assert _FakeCaptioner.calls[0][1]["page_name"] == "Uyển Nhi"

    asset = db.get(StudioAsset, project.asset_id)
    assert (asset.width, asset.height, asset.has_audio) == (640, 360, True)
    kinds = {r.kind for r in db.query(StudioAnalysis).filter_by(asset_id=asset.id)}
    assert kinds == {"probe", "transcript", "silences", "scenes"}  # mẫu basic: không lồng tiếng
    transcript = db.query(StudioAnalysis).filter_by(asset_id=asset.id, kind="transcript").one().data
    assert transcript["lang"] == "vi" and transcript["lines"][0] == {"start": 0.5, "end": 2.0, "text": "xin chào các bạn"}

    tasks = db.query(StudioTask).filter_by(flow="upload").order_by(StudioTask.id).all()
    assert [(t.stage, t.status, t.lane) for t in tasks] == [
        ("intake", "DONE", "light"), ("analyze", "DONE", "heavy"), ("dub", "DONE", "heavy"),
        ("compose", "DONE", "light"), ("render", "DONE", "heavy"), ("caption", "DONE", "heavy"),
        ("review", "DONE", "light"),
    ]
    assert [t.parent_id for t in tasks] == [None] + [t.id for t in tasks[:-1]]
    assert not any((paths.ROOT / "work").iterdir()), "thư mục work phải trống sau render"
    assert not list(paths.renders_dir().glob("*.tmp.mp4"))


def test_kenh_tu_duyet_thi_approved(db, media):
    ch = _channel(db, auto_approve=True)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    project = db.query(StudioProject).one()
    assert project.status == ProjectStatus.APPROVED and project.approved_at
    # video không tiếng: không phụ đề, tiếng gốc 0 — vẫn render ra file có audio im lặng
    assert project.spec["subtitles"]["enabled"] is False and project.spec["audio"]["original"] == 0.0
    assert _probe_duration(project.output_path) == pytest.approx(3.0, abs=0.15)


def test_reup_trung_noi_dung_dung_lai_khong_tao_du_an_thu_hai(db, media):
    for _ in range(2):
        pipeline.start(db, "reup", payload={"path": str(media["mute"]), "origin": "reup"})
        _drain(db)
    assert db.query(StudioAsset).count() == 1
    assert db.query(StudioProject).count() == 1
    last_intake = db.query(StudioTask).filter_by(stage="intake").order_by(StudioTask.id.desc()).first()
    assert last_intake.status == TaskStatus.DONE and "trùng" in last_intake.error


def test_upload_trung_dung_lai_asset_va_van_ra_du_an_moi(db, media):
    for _ in range(2):
        pipeline.start(db, "upload", payload={"path": str(media["mute"])})
        _drain(db)
    assert db.query(StudioAsset).count() == 1
    assert db.query(StudioProject).count() == 2


def test_render_lai_sau_khi_sua_spec_tren_trinh_edit(db, media):
    pipeline.start(db, "upload", payload={"path": str(media["clip"])})
    _drain(db)
    project = db.query(StudioProject).one()
    spec = dict(project.spec)
    spec["clips"] = [{"asset": project.asset_id, "start": 1.0, "end": 3.0}]
    spec["subtitles"] = {**spec["subtitles"], "edits": {"0": "Chào cả nhà"}}
    project.spec = spec
    db.commit()

    pipeline.start(db, "rerender", project_id=project.id)
    assert _drain(db) == 3
    db.refresh(project)
    assert project.status == ProjectStatus.REVIEW
    assert _probe_duration(project.output_path) == pytest.approx(2.0, abs=0.15)
    assert len(_FakeCaptioner.calls) == 1, "render lại không viết lại caption"


def test_file_khong_co_thi_hong_ngay_khong_thu_lai(db):
    task = pipeline.start(db, "upload", payload={"path": "/khong/co/file.mp4"})
    _drain(db)
    db.refresh(task)
    assert task.status == TaskStatus.FAILED and task.attempts == 1 and "không thấy file" in task.error


def test_spec_tro_toi_asset_mat_thi_du_an_failed(db, media):
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    _drain(db)
    project = db.query(StudioProject).one()
    project.spec = {**project.spec, "clips": [{"asset": 999}]}
    db.commit()
    pipeline.start(db, "rerender", project_id=project.id)
    _drain(db)
    db.refresh(project)
    assert project.status == ProjectStatus.FAILED and "999" in project.error


def test_loi_bat_ngo_thu_lai_co_gian_cach_roi_moi_failed(db, monkeypatch):
    calls = []

    def boom(_db, _task):
        calls.append(1)
        raise RuntimeError("ổ đĩa đầy")

    monkeypatch.setitem(pipeline.STAGES, pipeline.Stage.INTAKE, boom)
    task = pipeline.start(db, "upload", payload={"path": "x"})
    _drain(db)
    db.refresh(task)
    assert task.status == TaskStatus.QUEUED and task.run_after > time.time() + 30

    for _ in range(2):  # hết giờ chờ → chạy lại
        task.run_after = 0
        db.commit()
        _drain(db)
        db.refresh(task)
    assert len(calls) == 3 and task.status == TaskStatus.FAILED and "ổ đĩa đầy" in task.error


def test_lam_heavy_khong_nhan_viec_light_va_nguoc_lai(db):
    pipeline.start(db, "upload", payload={"path": "x"})
    assert queue.claim(db, lanes=[Lane.HEAVY], worker_id="h") is None
    assert queue.claim(db, lanes=[Lane.LIGHT], worker_id="l").stage == "intake"


def test_viec_treo_tra_ve_hang(db):
    task = pipeline.start(db, "upload", payload={"path": "x"})
    queue.claim(db, lanes=[Lane.LIGHT], worker_id="chet")
    task = db.get(StudioTask, task.id)
    task.claimed_at = int(time.time()) - 3600
    db.commit()
    assert queue.requeue_stale(db) == 1
    db.refresh(task)
    assert task.status == TaskStatus.QUEUED and task.claimed_by is None


def test_stage_error_khong_thu_lai_khi_retryable_false(db, monkeypatch):
    def bad(_db, _task):
        raise StageError("spec sai", retryable=False)

    monkeypatch.setitem(pipeline.STAGES, pipeline.Stage.INTAKE, bad)
    task = pipeline.start(db, "upload", payload={})
    _drain(db)
    db.refresh(task)
    assert task.status == TaskStatus.FAILED and task.attempts == 1


def test_worker_once_chay_het_hang_roi_thoat(db, media, monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", db.factory)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)  # không đè Ctrl+C của pytest
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    assert worker.main(["--lanes", "heavy,light", "--once"]) == 0
    db.expire_all()
    assert db.query(StudioProject).one().status == ProjectStatus.REVIEW


# ── P2: lồng tiếng, caption, cửa vào ──


def _dub_template(db, **params) -> StudioTemplate:
    tpl = StudioTemplate(name="Lồng tiếng", kind="reup_dub", params=params)
    db.add(tpl)
    db.commit()
    return tpl


def _fake_tracks(calls: list, result: str = "ok"):
    def make_tracks(path, workdir, **kw):
        calls.append(kw["target_lang"])
        if result != "ok":
            return DubTracks(False, result, source_lang="zh")
        voice, bg = f"{workdir}/voice.wav", f"{workdir}/background.wav"
        _ff("-f", "lavfi", "-i", "sine=frequency=660:duration=6", "-ac", "2", voice)
        _ff("-f", "lavfi", "-i", "sine=frequency=110:duration=6", "-ac", "2", bg)
        return DubTracks(True, "zh→vi, 1/1 câu", source_lang="zh", voice_wav=voice, background_wav=bg,
                         background_volume=1.0, lines=[{"start": 1.0, "end": 3.0, "text": "xin chào"}])
    return make_tracks


def test_reup_dub_tao_hai_asset_audio_va_spec_lay_tieng_long(db, media, monkeypatch):
    monkeypatch.setattr(analyze.speech, "transcribe", lambda path, **kw: ([{"start": 1, "end": 3, "text": "你好"}], "zh"))
    calls = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls))
    ch = _channel(db, template_id=_dub_template(db, background_volume=0.5).id)

    pipeline.start(db, "reup", payload={"path": str(media["clip"]), "origin": "reup", "channel_id": ch.id})
    _drain(db)

    project = db.query(StudioProject).one()
    assert project.status == ProjectStatus.REVIEW and calls == ["vi"]
    data = db.query(StudioAnalysis).filter_by(asset_id=project.asset_id, kind="dub").one().data
    assert data["ok"] and data["source_lang"] == "zh" and data["lines"][0]["text"] == "xin chào"
    voice, bg = db.get(StudioAsset, data["voice_asset"]), db.get(StudioAsset, data["background_asset"])
    assert (voice.kind, voice.origin, bg.origin) == ("audio", "dub", "dub")
    assert voice.path.endswith(".flac") and bg.path.endswith(".flac")
    clip = project.spec["clips"][0]
    assert clip["audio"] == [{"asset": voice.id, "volume": 1.0}, {"asset": bg.id, "volume": 0.5}]
    assert project.spec["subtitles"]["source"] == "dub" and project.spec["subtitles"]["enabled"] is True
    assert _probe_duration(project.output_path) == pytest.approx(6.0, abs=0.15)
    assert not any((paths.ROOT / "work").iterdir())


def test_dub_bo_qua_khi_da_la_tieng_viet_khong_chay_demucs(db, media, monkeypatch):
    calls = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls))
    ch = _channel(db, template_id=_dub_template(db).id)
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "channel_id": ch.id})
    _drain(db)
    project = db.query(StudioProject).one()
    assert calls == []
    data = db.query(StudioAnalysis).filter_by(asset_id=project.asset_id, kind="dub").one().data
    assert data == {"ok": False, "target_lang": "vi", "reason": "đã đúng ngôn ngữ đích", "source_lang": "vi"}
    assert project.spec["clips"][0]["audio"] == [] and project.spec["subtitles"]["source"] == "transcript"


def test_dub_dich_hong_thu_lai_roi_giu_tieng_goc(db, media, monkeypatch):
    monkeypatch.setattr(analyze.speech, "transcribe", lambda path, **kw: ([{"start": 1, "end": 3, "text": "hi"}], "en"))
    calls = []
    monkeypatch.setattr(dub.engine, "make_tracks", _fake_tracks(calls, "dịch hỏng"))
    ch = _channel(db, template_id=_dub_template(db).id)
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "channel_id": ch.id})
    _drain(db)
    dub_task = db.query(StudioTask).filter_by(stage="dub").one()
    assert dub_task.status == TaskStatus.QUEUED and dub_task.attempts == 1  # chờ thử lại

    for _ in range(2):
        dub_task.run_after = 0
        db.commit()
        _drain(db)
        db.refresh(dub_task)
    assert len(calls) == 3 and dub_task.status == TaskStatus.DONE
    project = db.query(StudioProject).one()
    assert project.status == ProjectStatus.REVIEW
    # tiếng Anh, không lồng được: giữ tiếng gốc, không đốt phụ đề tiếng Anh
    assert project.spec["clips"][0]["audio"] == [] and project.spec["subtitles"]["enabled"] is False


def test_caption_hong_khong_lam_hong_du_an(db, media):
    _FakeCaptioner.fail = True
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    _drain(db)
    project = db.query(StudioProject).one()
    assert project.status == ProjectStatus.REVIEW and project.caption is None
    note = db.query(StudioTask).filter_by(stage="caption").one().error
    assert "viết tay" in note


def test_mau_tat_caption(db, media):
    tpl = StudioTemplate(name="Không caption", kind="basic", params={"caption": False})
    db.add(tpl)
    db.commit()
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "template_id": tpl.id})
    _drain(db)
    assert _FakeCaptioner.calls == [] and db.query(StudioProject).one().status == ProjectStatus.REVIEW


def test_reup_cung_video_hai_kenh_khac_nhau_ra_hai_du_an(db, media):
    a = _channel(db, buffer_channel_id="buf-a")
    b = _channel(db, buffer_channel_id="buf-b")
    for ch in (a, b, a):
        pipeline.start(db, "reup", payload={"path": str(media["mute"]), "origin": "reup", "channel_id": ch.id})
        _drain(db)
    assert sorted(p.channel_id for p in db.query(StudioProject)) == [a.id, b.id]


def test_take_reup_chi_nhan_kenh_bat_co_va_dung_mot_kenh(db, media, tmp_path):
    on = _channel(db, buffer_channel_id="buf-on", take_reup=True)
    _channel(db, buffer_channel_id="buf-off")
    _channel(db, buffer_channel_id="buf-tat", take_reup=True, active=False)
    src = tmp_path / "viral_9_x.mp4"

    def fresh():
        src.write_bytes(media["mute"].read_bytes())
        return str(src)

    for ids in (["buf-off"], ["buf-tat"], ["buf-on", "buf-off"], [], ["khong-co"]):
        assert entry.take_reup(db, channel_ids=ids, path=fresh()) is False
        assert src.exists()
    assert db.query(StudioTask).count() == 0

    url = "https://www.tiktok.com/@chu.kenh/video/123"
    assert entry.take_reup(db, channel_ids=["buf-on"], path=fresh(), url=url, title="Mẹo", material_id=9) is True
    assert not src.exists(), "file đã chuyển sang hộp thư Studio"
    task = db.query(StudioTask).one()
    assert (task.flow, task.payload["channel_id"], task.payload["credit"]) == ("reup", on.id, "@chu.kenh")
    _drain(db)
    project = db.query(StudioProject).one()
    assert project.spec["credit"] == "Nguồn: @chu.kenh"
    assert db.get(StudioAsset, project.asset_id).viral_material_id == 9
    assert not any(paths.inbox_dir().iterdir()), "intake dọn file trong hộp thư"


def test_credit_tu_url():
    assert entry.credit_from_url("https://www.tiktok.com/@a.b_c/video/1") == "@a.b_c"
    assert entry.credit_from_url("https://www.douyin.com/video/7") == "Douyin"
    assert entry.credit_from_url("https://example.com/x") is None and entry.credit_from_url(None) is None


def test_hop_thu_drive_nhan_file_dung_yen_theo_ten_kenh(db, media, tmp_path):
    ch = _channel(db)
    inbox = tmp_path / "drive" / "Studio" / "Inbox"
    (inbox / "uyển nhi").mkdir(parents=True)
    (inbox / "Kênh lạ").mkdir()
    (inbox / "_Kho").mkdir()
    old = inbox / "uyển nhi" / "quay1.mp4"
    old.write_bytes(media["mute"].read_bytes())
    new = inbox / "uyển nhi" / "dang_dong_bo.mp4"
    new.write_bytes(b"x")
    (inbox / "uyển nhi" / "ghi_chu.txt").write_text("bỏ qua")
    (inbox / "Kênh lạ" / "a.mp4").write_bytes(b"x")
    logo = inbox / "_Kho" / "logo.png"
    logo.write_bytes(media["logo"].read_bytes())
    now = time.time()
    for f in (old, logo, inbox / "Kênh lạ" / "a.mp4"):
        os.utime(f, (now - 600, now - 600))

    assert entry.scan_inbox(db, root=tmp_path / "drive", now=now) == 2
    assert not old.exists() and not logo.exists() and new.exists()
    assert (inbox / "Kênh lạ" / "a.mp4").exists()
    flows = {t.flow: t.payload for t in db.query(StudioTask)}
    assert flows["upload"]["channel_id"] == ch.id and flows["upload"]["title"] == "quay1"
    assert flows["brand"]["origin"] == "brand" and "channel_id" not in flows["brand"]
    assert entry.scan_inbox(db, root=tmp_path / "khong_co") == 0


def test_upload_web_ghi_vao_hop_thu_va_tu_choi_duoi_la(db, media):
    with media["mute"].open("rb") as f:
        task = entry.accept_file(db, f, "Clip của anh.MP4", channel_id=None)
    assert task.flow == "upload" and task.payload["move"] and task.payload["title"] == "Clip của anh"
    assert Path(task.payload["path"]).parent == paths.inbox_dir()
    with pytest.raises(ValueError):
        entry.accept_file(db, io.BytesIO(b"x"), "virus.exe")
    with media["logo"].open("rb") as f:
        assert entry.accept_file(db, f, "logo.png", brand=True).flow == "brand"


def test_own_footage_cat_khoang_lang_that_bang_silencedetect(db, tmp_path):
    talk = tmp_path / "tu_quay.mp4"  # nói 2,5 giây, im 1,5 giây, lặp 3 lần
    _ff("-f", "lavfi", "-i", "testsrc2=size=360x640:rate=25:duration=12",
        "-f", "lavfi", "-i", "aevalsrc=sin(2*PI*440*t)*lt(mod(t\\,4)\\,2.5):s=48000:d=12",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(talk))
    tpl = StudioTemplate(name="Tự quay", kind="own_footage", params={"pad": 0.12})
    db.add(tpl)
    db.commit()
    pipeline.start(db, "upload", payload={"path": str(talk), "template_id": tpl.id, "credit": "@ai_do"})
    _drain(db)
    project = db.query(StudioProject).one()
    assert len(project.spec["clips"]) == 3 and project.spec["credit"] is None
    assert _probe_duration(project.output_path) == pytest.approx(8.1, abs=0.35)


# ── P3: cầu nối Buffer ──


def _reviewed(db, media, **channel_kw) -> StudioProject:
    ch = _channel(db, **channel_kw)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id, "title": "Mẹo nhỏ"})
    _drain(db)
    return db.query(StudioProject).order_by(StudioProject.id.desc()).first()


def test_tu_duyet_thi_sang_buffer_bang_dong_ready_ma_buffer_tim_thay_file(db, media):
    project = _reviewed(db, media, auto_approve=True)
    assert project.status == ProjectStatus.APPROVED and project.viral_material_id
    mat = db.get(ViralMaterial, project.viral_material_id)
    assert (mat.status, mat.platform, mat.target_page) == (ViralStatus.READY, "studio", "buf-1")
    assert mat.url == f"studio://project/{project.id}" and mat.title == "Mẹo nhỏ"
    assert mat.ai_caption == "Mẹo nhỏ hôm nay" and mat.ai_hashtags_list == ["#meo", "#doisong"]
    found = ViralService.find_reup_path(mat.id, mat.platform)
    assert found and found.endswith(f"studio/viral_{mat.id}_p{project.id}_reup.mp4")
    assert os.path.samefile(found, project.output_path), "nối cứng, không chép thêm"
    stages = [t.stage for t in db.query(StudioTask).order_by(StudioTask.id)]
    assert stages[-2:] == ["review", "publish"]


def test_tu_duyet_nhung_khong_co_caption_thi_dung_o_cho_duyet(db, media):
    _FakeCaptioner.fail = True
    project = _reviewed(db, media, auto_approve=True)
    assert project.status == ProjectStatus.REVIEW and project.viral_material_id is None


def test_duyet_tay_sua_caption_roi_publish(db, media):
    project = _reviewed(db, media)
    assert project.status == ProjectStatus.REVIEW
    task = entry.approve(db, project.id, caption="  Caption anh viết  ", hashtags=["xuhuong", "#meo", " "])
    assert task.flow == "publish"
    _drain(db)
    db.refresh(project)
    mat = db.get(ViralMaterial, project.viral_material_id)
    assert mat.ai_caption == "Caption anh viết" and mat.ai_hashtags_list == ["#xuhuong", "#meo"]
    with pytest.raises(entry.ReviewError):
        entry.approve(db, project.id)  # đã duyệt rồi


def test_duyet_khong_caption_va_bo_du_an(db, media):
    _FakeCaptioner.fail = True
    project = _reviewed(db, media)
    with pytest.raises(entry.ReviewError, match="caption"):
        entry.approve(db, project.id)
    entry.reject(db, project.id, reason="mờ")
    db.refresh(project)
    assert (project.status, project.error) == (ProjectStatus.REJECTED, "mờ")
    assert db.query(ViralMaterial).count() == 0


def test_reup_tu_he_cu_dung_lai_chinh_dong_material(db, media, tmp_path):
    mat = ViralMaterial(platform="tiktok", url="https://www.tiktok.com/@a/video/1", status=ViralStatus.STUDIO)
    db.add(mat)
    db.commit()
    _channel(db, buffer_channel_id="buf-on", take_reup=True)
    src = tmp_path / "viral_x.mp4"
    src.write_bytes(media["mute"].read_bytes())
    assert entry.take_reup(db, channel_ids=["buf-on"], path=str(src), url=mat.url, material_id=mat.id)
    _drain(db)
    project = db.query(StudioProject).one()
    entry.approve(db, project.id)
    _drain(db)
    db.refresh(project)
    db.refresh(mat)
    assert project.viral_material_id == mat.id and db.query(ViralMaterial).count() == 1
    assert (mat.status, mat.target_page, mat.platform) == (ViralStatus.READY, "buf-on", "tiktok")
    assert ViralService.find_reup_path(mat.id, mat.platform).endswith(f"viral_{mat.id}_p{project.id}_reup.mp4")


def test_dong_bo_scheduled_roi_posted(db, media):
    project = _reviewed(db, media, auto_approve=True)
    assert publish_status.sync(db) == 0
    db.add(Job(platform="buffer", status=JobStatus.DONE, viral_material_id=project.viral_material_id,
               target_page="buf-1", schedule_ts=int(time.time()) + 3600, caption="x"))
    db.commit()
    assert publish_status.sync(db) == 1
    db.refresh(project)
    assert project.status == ProjectStatus.SCHEDULED
    db.get(ViralMaterial, project.viral_material_id).status = ViralStatus.POSTED
    db.commit()
    assert publish_status.sync(db) == 1
    db.refresh(project)
    assert project.status == ProjectStatus.POSTED


def test_render_lai_thay_file_cu_nhung_khong_dong_vao_bai_da_hen(db, media):
    project = _reviewed(db, media, auto_approve=True)
    mat_id = project.viral_material_id
    project.spec = {**project.spec, "clips": [{"asset": project.asset_id, "start": 0, "end": 2}]}
    db.commit()
    pipeline.start(db, "rerender", project_id=project.id)
    _drain(db)
    files = list((app_config.REUP_DIR / "studio").glob(f"viral_{mat_id}_*_reup.mp4"))
    assert len(files) == 1 and _probe_duration(files[0]) == pytest.approx(2.0, abs=0.15)

    db.add(Job(platform="buffer", status=JobStatus.DONE, viral_material_id=mat_id, target_page="buf-1", caption="x"))
    db.commit()
    pipeline.start(db, "publish", project_id=project.id)
    _drain(db)
    last = db.query(StudioTask).order_by(StudioTask.id.desc()).first()
    assert last.status == TaskStatus.FAILED and "đã có lịch Buffer" in last.error

