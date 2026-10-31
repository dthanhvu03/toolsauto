"""
PLAN-106 P4 — API Studio cho SPA (trình edit, kênh & mẫu, file) + Telegram (báo chờ duyệt, nút, nhận file).
SQLite tạm, ffmpeg thật; Whisper / AI / Telegram giả. Không gọi mạng.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import feature_hooks
from app.core.database.core import get_db
from app.core.database.models import StudioAsset, StudioProject, StudioTask, StudioTemplate
from app.core.notifier.service import NotifierService
from app.features.studio import entry, notify, pipeline, setup
from app.features.studio.contracts import ProjectStatus
from app.features.studio.router import router
from app.features.telegram_bot.event_router import TelegramEventRouter
from tests.test_studio_pipeline import _channel, _drain, _probe_duration, db, media  # noqa: F401 — fixture


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


def _project(db, media, **kw) -> StudioProject:  # noqa: F811
    ch = _channel(db, **kw)
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "channel_id": ch.id, "title": "Clip"})
    _drain(db)
    return db.query(StudioProject).order_by(StudioProject.id.desc()).first()


# ── bảng duyệt + trình edit ──


def test_bang_duyet_va_chi_tiet_cho_trinh_edit(db, media, api):  # noqa: F811
    project = _project(db, media)
    board = api.get("/studio/api/projects?status=review,failed").json()
    assert board["counts"] == {"REVIEW": 1} and board["projects"][0]["channel"] == "Uyển Nhi"
    assert board["projects"][0]["has_video"] and board["tasks_pending"] == 0

    d = api.get(f"/studio/api/projects/{project.id}").json()
    assert d["project"]["editable"] is True and d["asset"]["width"] == 640
    assert [x["text"] for x in d["subtitle_lines"]] == ["xin chào các bạn", "hôm nay làm mẹo nhỏ"]
    assert d["tasks"][0]["stage"] == "review"
    assert api.get("/studio/api/projects/999").status_code == 404


def test_luu_spec_render_lai_va_bo_sua_tay_khi_doi_doan_cat(db, media, api):  # noqa: F811
    project = _project(db, media)
    spec = api.get(f"/studio/api/projects/{project.id}").json()["spec"]
    spec["subtitles"]["edits"] = {"0": "Chào"}
    assert api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": spec}).status_code == 200
    db.refresh(project)
    assert project.spec["subtitles"]["edits"] == {"0": "Chào"} and project.status == ProjectStatus.DRAFT

    spec["clips"] = [{"asset": project.asset_id, "start": 1, "end": 3.5, "audio": []}]  # đổi đoạn cắt, giữ edits cũ
    assert api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": spec}).status_code == 200
    db.refresh(project)
    assert project.spec["subtitles"]["edits"] == {}, "số câu đã lệch — bỏ sửa tay"
    _drain(db)
    db.refresh(project)
    assert project.status == ProjectStatus.REVIEW and _probe_duration(project.output_path) == pytest.approx(2.5, abs=0.15)

    bad = api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": {"clips": []}})
    assert bad.status_code == 400 and "spec sai" in bad.json()["detail"]
    ghost = api.put(f"/studio/api/projects/{project.id}/spec", json={"spec": {"clips": [{"asset": 999}]}})
    assert ghost.status_code == 400 and "999" in ghost.json()["detail"]


def test_sua_caption_doi_kenh_va_khoa_khi_da_sang_buffer(db, media, api):  # noqa: F811
    project = _project(db, media)
    other = _channel(db, buffer_channel_id="buf-2")
    r = api.patch(f"/studio/api/projects/{project.id}", json={"caption": " Mới ", "hashtags": ["a", "#b"], "channel_id": other.id})
    assert r.status_code == 200
    db.refresh(project)
    assert (project.caption, project.hashtags, project.channel_id) == ("Mới", ["#a", "#b"], other.id)
    assert api.patch(f"/studio/api/projects/{project.id}", json={"channel_id": 999}).status_code == 400

    assert api.post(f"/studio/api/projects/{project.id}/approve", json={}).status_code == 200
    _drain(db)
    locked = api.patch(f"/studio/api/projects/{project.id}", json={"caption": "x"})
    assert locked.status_code == 400 and "Buffer" in locked.json()["detail"]


def test_doi_mau_tao_du_an_moi_tu_cung_asset(db, media, api):  # noqa: F811
    project = _project(db, media)
    tpl = StudioTemplate(name="Ngắn", kind="basic", params={"max_len": 2})
    db.add(tpl)
    db.commit()
    assert api.post(f"/studio/api/projects/{project.id}/recompose", json={"template_id": tpl.id}).status_code == 200
    _drain(db)
    db.refresh(project)
    new = db.query(StudioProject).order_by(StudioProject.id.desc()).first()
    assert project.status == ProjectStatus.REJECTED and new.id != project.id
    assert (new.asset_id, new.template_id, new.channel_id, new.status) == (project.asset_id, tpl.id, project.channel_id, "REVIEW")
    assert _probe_duration(new.output_path) == pytest.approx(2.0, abs=0.15)


def test_file_video_anh_bia_va_dai_khung_hinh(db, media, api):  # noqa: F811
    project = _project(db, media)
    v = api.get(f"/studio/api/projects/{project.id}/video", headers={"Range": "bytes=0-99"})
    assert v.status_code == 206 and len(v.content) == 100 and v.headers["content-type"] == "video/mp4"
    p = api.get(f"/studio/api/projects/{project.id}/poster.jpg")
    assert p.status_code == 200 and p.content[:2] == b"\xff\xd8"
    s = api.get(f"/studio/api/assets/{project.asset_id}/strip.jpg")
    assert s.status_code == 200 and s.content[:2] == b"\xff\xd8"
    assert api.get(f"/studio/api/assets/{project.asset_id}/file").status_code == 200
    assets = api.get("/studio/api/assets?kind=video").json()["assets"]
    assert [a["id"] for a in assets] == [project.asset_id]


# ── kênh & mẫu ──


def test_kenh_va_mau(db, media, api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(setup, "buffer_channels", lambda db=None: [{"id": "b1", "name": "Uyển Nhi"}, {"id": "b2", "name": "Sống Nhẹ"}])
    ov = api.get("/studio/api/setup").json()
    assert [b["id"] for b in ov["buffer_channels"]] == ["b1", "b2"]
    assert {k["kind"] for k in ov["template_kinds"]} == {"basic", "reup_dub", "own_footage"}

    ch = api.post("/studio/api/channels", json={"buffer_channel_id": "b1"}).json()
    assert ch["name"] == "Uyển Nhi" and ch["auto_approve"] is False and ch["take_reup"] is False
    assert api.post("/studio/api/channels", json={"buffer_channel_id": "b1"}).status_code == 400
    assert [b["id"] for b in api.get("/studio/api/setup").json()["buffer_channels"]] == ["b2"]

    tpl = api.post("/studio/api/templates", json={"name": "Lồng tiếng", "kind": "reup_dub", "params": {"dub_voice": "male"}}).json()
    assert api.post("/studio/api/templates", json={"name": "x", "kind": "khong_co"}).status_code == 400
    assert api.put(f"/studio/api/templates/{tpl['id']}", json={"name": "LT", "kind": "reup_dub", "params": {}}).json()["name"] == "LT"

    pipeline.start(db, "brand", payload={"path": str(media["logo"]), "origin": "brand"})
    _drain(db)
    logo = db.query(StudioAsset).filter_by(kind="image").one()
    r = api.patch(f"/studio/api/channels/{ch['id']}", json={"template_id": tpl["id"], "take_reup": True, "logo_asset_id": logo.id})
    assert r.status_code == 200 and r.json()["logo_asset_id"] == logo.id and r.json()["take_reup"] is True
    assert api.patch(f"/studio/api/channels/{ch['id']}", json={"intro_asset_id": logo.id}).status_code == 400


# ── Telegram ──


def test_vao_cho_duyet_thi_bao_telegram_kem_video_va_nut(db, media, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(NotifierService, "_broadcast_video", classmethod(lambda cls, path, msg, buttons: sent.append((path, msg, buttons))))
    monkeypatch.setattr(notify.runtime_settings, "get_str", lambda key, default="", db=None: "https://tool.example.com/")
    project = _project(db, media)
    path, msg, buttons = sent[0]
    assert path == project.output_path
    assert f"Studio #{project.id}" in msg and "Uyển Nhi" in msg and "Mẹo nhỏ hôm nay" in msg and "#meo" in msg
    assert buttons[0] == [{"text": "✅ Duyệt", "callback_data": f"sok:{project.id}"},
                          {"text": "🗑 Bỏ", "callback_data": f"sno:{project.id}"}]
    assert buttons[1][0]["url"] == f"https://tool.example.com/app/go/studio/{project.id}"


def test_thong_bao_hong_khong_lam_hong_buoc_duyet(db, media, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(NotifierService, "_broadcast_video", classmethod(boom))
    assert _project(db, media).status == ProjectStatus.REVIEW


def test_tin_dai_bi_cat_va_khong_co_nut_web_khi_chua_co_https():
    p = StudioProject(id=7, caption="x" * 2000, hashtags=[], duration=65)
    assert len(notify.review_message(p, "K")) <= notify.CAPTION_LIMIT
    assert "1:05" in notify.review_message(p, "K")
    assert len(notify.review_buttons(7, "http://lan")) == 1


class _FakeClient:
    MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

    def __init__(self, source=None):
        self.source, self.calls = source, []

    def answer_callback_query(self, cid, text="", show_alert=False):
        self.calls.append(("answer", text, show_alert))

    def edit_message_reply_markup(self, message_id, reply_markup=None):
        self.calls.append(("edit", message_id))

    def send_message(self, text, **kw):
        self.calls.append(("send", text))

    def download_file(self, file_id, dest):
        with open(dest, "wb") as fh:
            fh.write(self.source.read_bytes())
        return dest


@pytest.fixture
def hooks(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.core.database.core.SessionLocal", db.factory)
    for name, fn in {
        "studio.approve": lambda s, pid: (lambda: (entry.approve(s, pid), (True, "đã duyệt"))[1])(),
        "studio.reject": lambda s, pid: (entry.reject(s, pid), (True, "đã bỏ"))[1],
        "studio.accept_local_file": entry.accept_local_file,
    }.items():
        monkeypatch.setitem(feature_hooks._HOOKS, name, fn)


def test_nut_duyet_tren_telegram(db, media, hooks):  # noqa: F811
    project = _project(db, media)
    client = _FakeClient()
    TelegramEventRouter(client, None).dispatch(
        {"callback_query": {"id": "c1", "data": f"sok:{project.id}", "message": {"message_id": 55}}}
    )
    db.expire_all()
    assert db.get(StudioProject, project.id).status == ProjectStatus.APPROVED
    assert ("answer", "đã duyệt", False) in client.calls and ("edit", 55) in client.calls
    assert db.query(StudioTask).order_by(StudioTask.id.desc()).first().flow == "publish"


def test_gui_file_video_vao_bot_thanh_du_an_gan_kenh_theo_chu_kem_theo(db, media, hooks):  # noqa: F811
    ch = _channel(db)
    client = _FakeClient(source=media["mute"])
    TelegramEventRouter(client, None).dispatch({"message": {
        "video": {"file_id": "F1", "file_name": "quay.mp4", "mime_type": "video/mp4", "file_size": 1000},
        "caption": "uyển nhi",
    }})
    task = db.query(StudioTask).one()
    assert task.flow == "upload" and task.payload["channel_id"] == ch.id and task.payload["title"] == "quay"
    assert "Đã nhận vào Studio" in client.calls[-1][1]
    _drain(db)
    assert db.query(StudioProject).one().status == ProjectStatus.REVIEW

    big = _FakeClient(source=media["mute"])
    TelegramEventRouter(big, None).dispatch({"message": {"video": {"file_id": "F2", "file_size": 30 * 1024 * 1024}}})
    assert "20 MB" in big.calls[-1][1] and db.query(StudioTask).filter_by(stage="intake").count() == 1
