"""
PLAN-106 P4.1 — biến thể A/B cho video của mình: lật gương, tông màu LUT, montage xáo đoạn.
Phần thuần: lệnh ffmpeg + mẫu. Phần chạy thật: ffmpeg trên clip lavfi, SQLite tạm, không mạng.
Video reup không nhận lật / LUT ngẫu nhiên / xáo đoạn / biến thể (ADR-061 mục 11).
"""
from __future__ import annotations

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database.core import get_db
from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.core.notifier.service import NotifierService
from app.features.studio import editor, notify, paths, pipeline, store, taskqueue
from app.features.studio.compose.templates import ComposeInput, ab_montage, basic, scene_segments
from app.features.studio.render.graph import Media, build
from app.features.studio.router import router
from app.features.studio.spec import Canvas, ProjectSpec
from tests.test_studio_pipeline import _FakeCaptioner, _channel, _drain, _ff, db, media  # noqa: F401 — fixture

MEDIA = {1: Media(path="/v/a.mp4", kind="video", duration=30.0, has_audio=True)}
SCENES = [3.0, 6.5, 7.0, 11.0, 15.0, 20.0, 24.0]  # 7.0 cách 6.5 chỉ 0,5 s → gộp


def _graph(spec: dict, **kw) -> str:
    plan = build(ProjectSpec.model_validate(spec), MEDIA, output="/o.mp4", workdir="/w", font_file="/f/B.ttf",
                 fonts_dir="/f", **kw)
    return plan.argv[plan.argv.index("-filter_complex") + 1]


def _inp(**kw) -> ComposeInput:
    base = dict(asset_id=1, duration=30.0, has_audio=True, has_transcript=False, scenes=SCENES,
                lut_names=["Am.cube", "Lanh.cube"])
    return ComposeInput(**{**base, **kw})


# ── lệnh ffmpeg ──


@pytest.mark.parametrize("fit", ["blur_pad", "crop", "pad"])
def test_hflip_dung_truoc_khi_khop_khung(fit):
    g = _graph({"canvas": {"fit": fit}, "clips": [{"asset": 1, "end": 5, "hflip": True}, {"asset": 1, "start": 5}]})
    assert g.startswith("[0:v]hflip[hf0];[hf0]")
    assert "[1:v]hflip" not in g, "chỉ đoạn có cờ mới lật"


def test_lut3d_nhuom_truoc_phu_de_chu_va_ghi_nguon():
    g = _graph({"clips": [{"asset": 1, "end": 5}], "texts": [{"text": "hook", "end": 2}], "credit": "Nguồn: x"},
               lut_file="/l/Tông ấm (v2).cube")
    assert "[vcat]lut3d=file='/l/Tông ấm (v2).cube',drawtext" in g
    assert _graph({"clips": [{"asset": 1}]}).count("lut3d") == 0


def test_canvas_lut_chi_nhan_ten_file_cube():
    assert Canvas(lut="Teal Orange (1).cube").lut == "Teal Orange (1).cube"
    for bad in ("../x.cube", "a/b.cube", "x.png", "x.CUBE", ""):
        with pytest.raises(ValidationError):
            Canvas(lut=bad)


# ── mẫu ──


def test_mirror_va_lut_theo_seed_ghi_vao_spec():
    on = basic(_inp(params={"mirror": "on", "lut": "Am.cube"}))
    assert on.clips[0].hflip is True and on.canvas.lut == "Am.cube"
    a = basic(_inp(params={"mirror": "random", "lut": "random", "seed": 7}))
    b = basic(_inp(params={"mirror": "random", "lut": "random", "seed": 7}))
    assert a == b, "cùng seed → cùng bản"
    picks = {basic(_inp(params={"mirror": "random", "lut": "random", "seed": s})).canvas.lut for s in range(30)}
    assert picks == {"Am.cube", "Lanh.cube"}
    assert basic(_inp(params={"lut": "KhongCo.cube"})).canvas.lut is None
    assert basic(_inp(params={"lut": "random"}, lut_names=[])).canvas.lut is None, "không có LUT → màu gốc"


def test_intro_outro_khong_bi_lat():
    spec = basic(_inp(params={"mirror": "on"}, intro_asset_id=9, outro_asset_id=8))
    assert [c.hflip for c in spec.clips] == [False, True, False]


def test_reup_khong_lat_khong_lut_ngau_nhien_nhung_giu_lut_co_dinh():
    spec = basic(_inp(origin="reup", params={"mirror": "on", "lut": "random"}))
    assert spec.clips[0].hflip is False and spec.canvas.lut is None
    assert basic(_inp(origin="reup", params={"lut": "Lanh.cube"})).canvas.lut == "Lanh.cube"


def test_moc_doi_canh_thanh_doan_lien_nhau_gop_doan_ngan():
    segs = scene_segments(30.0, SCENES)
    assert segs == [(0.0, 3.0), (3.0, 7.0), (7.0, 11.0), (11.0, 15.0), (15.0, 20.0), (20.0, 24.0), (24.0, 30.0)]
    assert scene_segments(10.0, [0.3, 5.0]) == [(0.0, 5.0), (5.0, 10.0)], "đoạn đầu quá ngắn gộp sang sau"


def test_ab_montage_giu_hook_xao_doan_giua_theo_seed_va_cat_theo_max_len():
    specs = [ab_montage(_inp(params={"seed": s})) for s in range(6)]
    for spec in specs:
        clips = [(c.start, c.end) for c in spec.clips]
        assert clips[0] == (0.0, 3.0), "giữ đoạn đầu làm hook"
        assert all(e > s for s, e in clips)
        assert sorted(clips) == scene_segments(30.0, SCENES), "đủ đoạn, không lặp, không mất"
    assert len({tuple((c.start, c.end) for c in s.clips) for s in specs}) > 1, "seed khác → thứ tự khác"
    assert ab_montage(_inp(params={"seed": 3})) == ab_montage(_inp(params={"seed": 3}))

    short = ab_montage(_inp(params={"seed": 1, "max_len": 10}))
    total = sum(c.end - c.start for c in short.clips)
    assert total == pytest.approx(10.0) and all(c.end > c.start for c in short.clips)


def test_ab_montage_reup_hoac_it_canh_thi_nhu_basic():
    assert [(c.start, c.end) for c in ab_montage(_inp(origin="reup")).clips] == [(0.0, None)]
    assert [(c.start, c.end) for c in ab_montage(_inp(scenes=[10.0])).clips] == [(0.0, None)]


# ── chạy thật ──


def _red_lut(path):
    rows = "\n".join("1.0 0.0 0.0" for _ in range(8))
    path.write_text(f"LUT_3D_SIZE 2\n{rows}\n")


def _pixel_rgb(video) -> tuple[int, int, int]:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(video), "-vf", "scale=1:1", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True,
    ).stdout
    return out[0], out[1], out[2]


def test_render_that_co_lut_nhuom_mau_thieu_file_thi_bo_qua(db, media, tmp_path, monkeypatch):  # noqa: F811
    luts = tmp_path / "luts"
    luts.mkdir()
    _red_lut(luts / "Do.cube")
    monkeypatch.setattr(paths, "luts_dir", lambda: luts)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "params": {"lut": "Do.cube", "mirror": "on"}})
    _drain(db)
    project = db.query(StudioProject).one()
    assert project.spec["canvas"]["lut"] == "Do.cube" and project.spec["clips"][0]["hflip"] is True
    r, g, b = _pixel_rgb(project.output_path)
    assert r > 200 and g < 40 and b < 40, (r, g, b)

    (luts / "Do.cube").unlink()
    pipeline.start(db, "rerender", project_id=project.id)
    _drain(db)
    db.refresh(project)
    assert project.status == "REVIEW"
    r, g, b = _pixel_rgb(project.output_path)
    assert not (r > 200 and g < 40 and b < 40), "không còn LUT → màu gốc"


@pytest.fixture
def api(db):  # noqa: F811
    app = FastAPI()
    app.include_router(router)

    def _db():
        s = db.factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_bien_the_moi_ban_mot_kieu_khac_that(db, media, api, tmp_path, monkeypatch):  # noqa: F811
    luts = tmp_path / "luts"
    luts.mkdir()
    for name in ("A.cube", "B.cube"):
        _red_lut(luts / name)
    monkeypatch.setattr(paths, "luts_dir", lambda: luts)
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    _drain(db)
    own = db.query(StudioProject).one()
    _tasks, note = editor.make_variants(db, own.id, 3)
    assert "3 biến thể" in note
    _drain(db)
    variants = db.query(StudioProject).filter(StudioProject.id != own.id).order_by(StudioProject.id).all()
    looks = [(p.spec["clips"][0]["hflip"], p.spec["canvas"]["lut"]) for p in variants]
    assert looks == [(False, "A.cube"), (False, "B.cube"), (True, None)], "không trùng bản gốc (không lật, màu gốc)"
    _tasks, note = editor.make_variants(db, own.id, 5)  # còn (lật, A), (lật, B)
    assert "2 biến thể" in note and "chỉ còn 2" in note
    _drain(db)
    with pytest.raises(editor.EditError, match="tối đa 5"):
        editor.make_variants(db, own.id, 1)


def test_bien_the_dung_chung_caption_khong_goi_ai_va_gan_nhom(db, media, api):  # noqa: F811
    ch = _channel(db)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    own = db.query(StudioProject).one()
    calls = len(_FakeCaptioner.calls)
    r = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 3})
    assert r.status_code == 200 and len(r.json()["task_ids"]) == 1, "không LUT, mẫu basic: chỉ còn kiểu «lật»"
    assert "chưa có file LUT" in r.json()["note"]
    busy = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 1})
    assert busy.status_code == 400 and "đang dựng" in busy.json()["detail"], "bấm 2 lần không ra 2 lô"
    _drain(db)
    variant = db.query(StudioProject).filter(StudioProject.id != own.id).one()
    assert variant.parent_project_id == own.id and variant.caption == own.caption and variant.hashtags == own.hashtags
    assert len(_FakeCaptioner.calls) == calls, "biến thể không gọi AI viết caption"
    assert variant.channel_id == ch.id and variant.spec["clips"][0]["hflip"] is True
    done = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 1})
    assert done.status_code == 400 and "hết kiểu" in done.json()["detail"]
    group = api.get(f"/studio/api/projects/{variant.id}").json()["group"]
    assert group["root_id"] == own.id and [m["id"] for m in group["members"]] == [own.id, variant.id]
    assert api.get("/studio/api/projects").json()["projects"][0]["parent_project_id"] == own.id


def test_duyet_mot_ban_thi_cac_ban_khac_tu_bo_va_chan_bien_the_moi(db, media, api, tmp_path, monkeypatch):  # noqa: F811
    luts = tmp_path / "luts"
    luts.mkdir()
    _red_lut(luts / "A.cube")
    monkeypatch.setattr(paths, "luts_dir", lambda: luts)
    ch = _channel(db)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    own = db.query(StudioProject).one()
    editor.make_variants(db, own.id, 2)
    _drain(db)
    a, b = db.query(StudioProject).filter(StudioProject.id != own.id).order_by(StudioProject.id).all()
    assert api.post(f"/studio/api/projects/{b.id}/approve", json={}).status_code == 200
    _drain(db)
    for p in (own, a, b):
        db.refresh(p)
    assert (own.status, a.status) == ("REJECTED", "REJECTED") and own.error == f"đã chọn bản #{b.id}"
    assert b.status == "APPROVED" and b.viral_material_id, "bản được chọn sang Buffer"
    no = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 1})
    assert no.status_code == 400 and "sang Buffer" in no.json()["detail"]


def test_bien_the_tu_video_cua_minh_va_chan_reup(db, media, api):  # noqa: F811
    ch = _channel(db)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    own = db.query(StudioProject).one()
    assert api.get(f"/studio/api/projects/{own.id}").json()["variants_allowed"] is True
    assert api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 9}).status_code == 400

    db.get(StudioAsset, own.asset_id).origin = "reup"
    db.commit()
    assert api.get(f"/studio/api/projects/{own.id}").json()["variants_allowed"] is False
    no = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 2})
    assert no.status_code == 400 and "reup" in no.json()["detail"]
    spec = dict(own.spec)
    spec["clips"] = [{**spec["clips"][0], "hflip": True}]
    flip = api.put(f"/studio/api/projects/{own.id}/spec", json={"spec": spec})
    assert flip.status_code == 400 and "lật gương" in flip.json()["detail"]
    with pytest.raises(editor.EditError):
        editor.make_variants(db, own.id, 1)


def test_chi_lat_guong_thi_giu_sua_tay_phu_de(db, media, api):  # noqa: F811
    pipeline.start(db, "upload", payload={"path": str(media["clip"])})
    _drain(db)
    project = db.query(StudioProject).one()
    spec = api.get(f"/studio/api/projects/{project.id}").json()["spec"]
    spec["subtitles"]["edits"] = {"0": "Chào"}
    api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": spec})
    _drain(db)
    spec["clips"][0]["hflip"] = True
    assert api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": spec}).status_code == 200
    db.refresh(project)
    assert project.spec["subtitles"]["edits"] == {"0": "Chào"} and project.spec["clips"][0]["hflip"] is True


# ── P4.2: hàng việc, dự án đã bỏ, Telegram theo lô, form upload ──


def test_hang_viec_lam_xong_tung_du_an_truoc(db, media):  # noqa: F811
    for _ in range(2):
        pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    order = []
    while (t := taskqueue.claim(db, lanes=["heavy", "light"], worker_id="t")):
        order.append((t.stage, t.payload.get("path") is not None and t.asset_id))
        pipeline.run_task(db, t)
    stages = [s for s, _ in order]
    first_review = stages.index("review")
    assert stages[:first_review].count("intake") >= 1 and "review" in stages[first_review:]
    assert stages.index("review") < len(stages) - 1, "dự án đầu xong (review) trước khi dự án sau xong hết"
    assert db.query(StudioProject).filter_by(status="REVIEW").count() == 2


def test_du_an_da_bo_luc_con_trong_hang_khong_render_khong_bi_de_trang_thai(db, media):  # noqa: F811
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    _drain(db)
    project = db.query(StudioProject).one()
    pipeline.start(db, "rerender", project_id=project.id)
    project.status = "REJECTED"
    db.commit()
    _drain(db)
    db.refresh(project)
    assert project.status == "REJECTED"
    render = db.query(StudioTask).filter_by(flow="rerender", stage="render").one()
    assert render.status == "DONE" and "đã bỏ" in render.error


def test_telegram_mot_tin_cho_ca_lo_bien_the(db, media, api, monkeypatch, tmp_path):  # noqa: F811
    luts = tmp_path / "luts"
    luts.mkdir()
    _red_lut(luts / "Am.cube")
    monkeypatch.setattr(paths, "luts_dir", lambda: luts)
    videos, texts = [], []
    monkeypatch.setattr(NotifierService, "_broadcast_video", classmethod(lambda cls, *a: videos.append(a)))
    monkeypatch.setattr(NotifierService, "_broadcast_with_buttons", classmethod(lambda cls, msg, buttons: texts.append((msg, buttons))))
    monkeypatch.setattr(notify.runtime_settings, "get_str", lambda key, default="", db=None: "https://x.example")
    ch = _channel(db)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    own = db.query(StudioProject).one()
    assert len(videos) == 1 and texts == []
    editor.make_variants(db, own.id, 3)
    _drain(db)
    assert len(videos) == 1, "biến thể không gửi video từng bản"
    assert len(texts) == 1, "một tin cho cả lô"
    msg, buttons = texts[0]
    ids = [p.id for p in db.query(StudioProject).order_by(StudioProject.id)]
    assert f"Studio #{own.id}" in msg and "4 bản để chọn" in msg and "lật" in msg and "Am" in msg
    assert [b["callback_data"] for row in buttons[:-1] for b in row] == [f"sok:{i}" for i in ids]
    assert buttons[-1][0]["url"].endswith(f"/app/go/studio/{own.id}")


def test_upload_su_tam_ghi_nguon_co_chu_san_va_bat_buoc_kenh(db, media, api):  # noqa: F811
    ch = _channel(db)
    with media["mute"].open("rb") as f:
        no = api.post("/studio/api/upload", files={"file": ("v.mp4", f, "video/mp4")})
    assert no.status_code == 400 and "chọn kênh" in no.json()["detail"]
    with media["clip"].open("rb") as f:
        r = api.post("/studio/api/upload", files={"file": ("v.mp4", f, "video/mp4")},
                     data={"channel_id": ch.id, "collected": "true", "credit": "@goc", "has_text": "true"})
    assert r.status_code == 200
    _drain(db)
    project = db.query(StudioProject).one()
    asset = db.get(StudioAsset, project.asset_id)
    assert (asset.origin, asset.credit) == ("reup", "@goc")
    assert project.spec["credit"] == "Nguồn: @goc" and project.spec["subtitles"]["enabled"] is False
    assert api.get(f"/studio/api/projects/{project.id}").json()["variants_allowed"] is False


def test_file_da_khai_cua_minh_upload_lai_dang_su_tam_thi_sit_lai(db, media, api):  # noqa: F811
    ch = _channel(db)
    for collected in ("false", "true"):
        with media["mute"].open("rb") as f:
            api.post("/studio/api/upload", files={"file": ("v.mp4", f, "video/mp4")},
                     data={"channel_id": ch.id, "collected": collected, "credit": "@goc"})
        _drain(db)
    asset = db.query(StudioAsset).one()
    assert (asset.origin, asset.credit) == ("reup", "@goc")


# ── nhãn kỹ thuật trên thẻ / trình edit ──


def test_nhan_ky_thuat_doc_tu_spec():
    spec = {
        "clips": [{"asset": 9}, {"asset": 1, "start": 1, "end": 4, "hflip": True, "audio": [{"asset": 5}]},
                  {"asset": 1, "start": 6, "hflip": True}, {"asset": 8}],
        "canvas": {"lut": "Am cinematic.cube"}, "subtitles": {"enabled": True, "source": "dub"},
        "texts": [{"text": "hook"}], "audio": {"tracks": [{"asset": 4}]}, "logo": {"asset": 3}, "credit": "Nguồn: @a",
    }
    assert store.techniques(spec, 1, origin="reup", template="Mẹo") == [
        "Sưu tầm", "Mẹo", "Cắt 2 đoạn", "Lật gương", "Màu Am cinematic", "Lồng tiếng", "Phụ đề dịch", "Hook",
        "Nhạc nền", "Intro", "Outro", "Logo", "Ghi nguồn",
    ]
    plain = {"clips": [{"asset": 1}], "canvas": {}, "subtitles": {"enabled": False}}
    assert store.techniques(plain, 1, origin="upload") == ["Của tôi", "Mẫu cơ bản"]
    trimmed = {"clips": [{"asset": 1, "start": 0.5, "end": 9}], "subtitles": {"enabled": True, "source": "transcript"}}
    assert store.techniques(trimmed, 1) == ["Của tôi", "Mẫu cơ bản", "Cắt đầu / cuối", "Phụ đề"]


def test_api_tra_nhan_ky_thuat_cho_the_va_trinh_edit(db, media, api):  # noqa: F811
    ch = _channel(db)
    with media["mute"].open("rb") as f:
        api.post("/studio/api/upload", files={"file": ("v.mp4", f, "video/mp4")},
                 data={"channel_id": ch.id, "collected": "true", "credit": "@goc"})
    _drain(db)
    row = api.get("/studio/api/projects").json()["projects"][0]
    assert row["tags"][:2] == ["Sưu tầm", "Mẫu cơ bản"] and "Ghi nguồn" in row["tags"]
    detail = api.get(f"/studio/api/projects/{row['id']}").json()
    assert detail["project"]["tags"] == row["tags"]
