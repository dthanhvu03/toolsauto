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
from app.features.studio import editor, paths, pipeline
from app.features.studio.compose.templates import ComposeInput, ab_montage, basic, scene_segments
from app.features.studio.render.graph import Media, build
from app.features.studio.router import router
from app.features.studio.spec import Canvas, ProjectSpec
from tests.test_studio_pipeline import _channel, _drain, _ff, db, media  # noqa: F401 — fixture

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


def test_bien_the_lan_luot_tung_lut(db, media, api, tmp_path, monkeypatch):  # noqa: F811
    luts = tmp_path / "luts"
    luts.mkdir()
    for name in ("A.cube", "B.cube"):
        _red_lut(luts / name)
    monkeypatch.setattr(paths, "luts_dir", lambda: luts)
    pipeline.start(db, "upload", payload={"path": str(media["mute"])})
    _drain(db)
    own = db.query(StudioProject).one()
    editor.make_variants(db, own.id, 3)
    _drain(db)
    variants = db.query(StudioProject).filter(StudioProject.id != own.id).order_by(StudioProject.id).all()
    assert [p.spec["canvas"]["lut"] for p in variants] == ["A.cube", "B.cube", "A.cube"]


def test_bien_the_tu_video_cua_minh_va_chan_reup(db, media, api):  # noqa: F811
    ch = _channel(db)
    pipeline.start(db, "upload", payload={"path": str(media["mute"]), "channel_id": ch.id})
    _drain(db)
    own = db.query(StudioProject).one()
    assert api.get(f"/studio/api/projects/{own.id}").json()["variants_allowed"] is True
    r = api.post(f"/studio/api/projects/{own.id}/variants", json={"n": 3})
    assert r.status_code == 200 and len(r.json()["task_ids"]) == 3
    _drain(db)
    projects = db.query(StudioProject).order_by(StudioProject.id).all()
    assert len(projects) == 4 and {p.asset_id for p in projects} == {own.asset_id}
    assert projects[0].status == "REVIEW", "dự án gốc giữ nguyên"
    tasks = db.query(StudioTask).filter_by(flow="recompose", stage="compose").order_by(StudioTask.id).all()
    assert [t.payload["params"]["mirror"] for t in tasks] == ["on", "off", "on"], "mẫu chưa đặt → chia đều lật / không"
    assert len({t.payload["params"]["seed"] for t in tasks}) == 3
    assert [p.spec["clips"][0]["hflip"] for p in projects[1:]] == [True, False, True]
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
