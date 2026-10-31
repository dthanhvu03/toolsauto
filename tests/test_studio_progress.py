"""
PLAN-114 — tiến trình từng video: chuỗi bước theo ``parent_id``, trạng thái từng bước + một câu tóm tắt.
SQLite tạm; chuỗi bước dựng tay (không chạy ffmpeg) để kiểm đủ mọi trạng thái, cộng một lượt pipeline thật.
"""
from __future__ import annotations

from app.core.database.models import StudioTask
from app.features.studio import pipeline, progress
from app.features.studio.contracts import ProjectStatus
from tests.test_studio_api import api  # noqa: F401 — fixture
from tests.test_studio_pipeline import _drain, db, media  # noqa: F401 — fixture

NOW = 2_000_000_000


def _chain(db, flow, stages, *, last_status="DONE", notes=None, payload=None, project_id=None, **last):  # noqa: F811
    """Chuỗi việc ``stages`` của ``flow``: các bước trước DONE, bước cuối ``last_status`` (+ cột ``last``)."""
    notes = notes or {}
    parent = None
    for i, stage in enumerate(stages):
        final = i == len(stages) - 1
        t = StudioTask(flow=flow, stage=stage, lane="light", status=last_status if final else "DONE",
                       parent_id=parent.id if parent else None, payload=payload if parent is None else None,
                       error=notes.get(stage), project_id=project_id if stage in ("compose", "render", "caption", "review", "publish") else None,
                       created_at=NOW - 100 + i, claimed_at=NOW - 50 + i, finished_at=None if final and last_status != "DONE" else NOW - 40 + i)
        if final:
            for k, v in last.items():
                setattr(t, k, v)
        db.add(t)
        db.flush()
        parent = t
        if i == 0:
            root = t
    db.commit()
    return root


def _one(db, **kw):  # noqa: F811
    return progress.jobs(db, now=NOW, **kw)["jobs"]


def test_dang_render_bo_qua_long_tieng_va_buoc_sau_chua_toi(db):  # noqa: F811
    root = _chain(db, "link", ["fetch", "intake", "analyze", "dub", "compose", "render"], last_status="RUNNING",
                  notes={"fetch": "đã tải 7.6 MB", "dub": "mẫu không lồng tiếng"},
                  payload={"url": "https://www.tiktok.com/@a/video/1", "title": "Mẹo gấp áo"})
    r = progress.jobs(db, now=NOW)
    assert r["active"] == 1
    job = r["jobs"][0]
    assert (job["id"], job["source"], job["title"], job["state"]) == (root.id, "TikTok", "Mẹo gấp áo", "running")
    assert job["summary"] == "Đang render" and job["current"] == "render"
    status = {s["stage"]: s["status"] for s in job["steps"]}
    assert status == {"fetch": "done", "intake": "done", "analyze": "done", "dub": "skipped", "compose": "done",
                      "render": "running", "caption": "pending", "review": "pending", "publish": "pending"}
    assert job["steps"][0]["note"] == "đã tải 7.6 MB"


def test_cho_thu_lai_va_loi_han(db):  # noqa: F811
    _chain(db, "link", ["fetch"], last_status="QUEUED", attempts=1, max_attempts=3, error="tải hỏng: Connection reset",
           run_after=NOW + 60, payload={"url": "u1"})
    _chain(db, "link", ["fetch"], last_status="FAILED", attempts=1, error="tải hỏng: video is private", payload={"url": "u2"})
    failed, retry = _one(db)  # mới nhất trước
    assert retry["state"] == "retry" and "thử lại (lần 1/3)" in retry["summary"]
    assert retry["steps"][0]["status"] == "retry" and retry["steps"][0]["run_after"] == NOW + 60
    assert failed["state"] == "failed" and failed["summary"] == "Tải về hỏng: tải hỏng: video is private"


def test_xong_cho_duyet_buoc_dang_la_cho(db, media):  # noqa: F811
    pipeline.start(db, "upload", payload={"path": str(media["clip"]), "title": "Clip tự quay"})
    _drain(db)
    job = progress.jobs(db)["jobs"][0]  # pipeline thật ghi giờ thật
    assert job["state"] == "review" and job["summary"] == "Xong — chờ anh duyệt"
    assert job["project_status"] == ProjectStatus.REVIEW and job["project_id"]
    status = {s["stage"]: s["status"] for s in job["steps"]}
    assert (status["review"], status["publish"]) == ("waiting", "pending")  # «Duyệt» = chờ anh bấm, chưa phải đã duyệt
    assert job["title"] == "Clip tự quay"


def test_ten_viec_gui_dang_la_du_an_va_dang_tay(db, media):  # noqa: F811
    from app.core.database.models import StudioProject

    pipeline.start(db, "upload", payload={"path": str(media["clip"])})
    _drain(db)
    project = db.query(StudioProject).one()
    root = _chain(db, "publish", ["publish"], last_status="RUNNING", project_id=project.id)
    job = progress.jobs(db, ids=[root.id])["jobs"][0]
    assert job["title"] == f"Dự án #{project.id}" and job["summary"] == "Đang ghi nhận đăng tay (không qua Buffer)"


def test_dung_som_vi_trung_va_loc_theo_ids(db):  # noqa: F811
    a = _chain(db, "link", ["fetch", "intake"], notes={"intake": "trùng asset #3 (dự án #2)"}, payload={"url": "u"})
    b = _chain(db, "upload", ["intake"], last_status="QUEUED", payload={"path": "/x/inbox/upload-1.mp4"})
    stopped = _one(db, ids=[a.id])
    assert len(stopped) == 1 and stopped[0]["state"] == "stopped"
    assert stopped[0]["summary"] == "Dừng ở Nhận file: trùng asset #3 (dự án #2)"
    queued = _one(db, ids=[b.id])[0]
    assert queued["state"] == "queued" and queued["title"] == "upload-1.mp4" and queued["source"] == "Tải lên"


def test_bo_viec_cu_va_nguyen_lieu(db):  # noqa: F811
    old = _chain(db, "upload", ["intake"], payload={"path": "/a.mp4"})
    old.created_at = NOW - progress.WINDOW_SEC - 10
    _chain(db, "brand", ["intake", "analyze"], payload={"path": "/logo.png"})
    db.commit()
    assert _one(db) == []
    assert len(_one(db, ids=[old.id])) == 1  # hỏi đích danh thì vẫn trả


def test_api_jobs(api, db):  # noqa: F811
    root = _chain(db, "link", ["fetch"], last_status="RUNNING", payload={"url": "u"})
    r = api.get(f"/studio/api/jobs?ids={root.id},abc").json()
    assert [j["id"] for j in r["jobs"]] == [root.id] and r["active"] == 1 and "now" in r
    assert api.get("/studio/api/jobs").status_code == 200
