from __future__ import annotations


from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus
from app.core.database.core import get_db
from app.core.database.models import Account, Base, Job, ViralMaterial, ViralSource
from app.platform.admin_api.router import router


def _client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _db
    return engine, factory, TestClient(app)


def test_admin_viral_sources_lists_channel(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            db.add(
                ViralSource(
                    platform="tiktok",
                    url="https://www.tiktok.com/@kenh",
                    handle="kenh",
                    enabled=True,
                    last_found=3,
                )
            )
            db.commit()
        r = c.get("/api/admin/viral-sources")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["handle"] == "kenh"
        assert body["items"][0]["platform"] == "tiktok"
    finally:
        engine.dispose()


def test_admin_ai_studio_lists_personas(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        r = c.get("/api/admin/ai-studio")
        assert r.status_code == 200
        body = r.json()
        assert len(body["personas"]) >= 1
        assert body["personas"][0]["key"]
        assert "preview" in body["personas"][0]
    finally:
        engine.dispose()


def test_admin_logs_empty_events(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        r = c.get("/api/admin/logs")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["events"] == []
    finally:
        engine.dispose()


def test_admin_job_cancel_pending(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            acc = Account(name="Ops Acc", platform="facebook")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            job = Job(account_id=acc.id, platform="facebook", status="PENDING", caption="hi")
            db.add(job)
            db.commit()
            db.refresh(job)
            jid = job.id
        r = c.post(f"/api/admin/jobs/{jid}/cancel")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        with factory() as db:
            assert db.get(Job, jid).status == "CANCELLED"
    finally:
        engine.dispose()


def test_admin_viral_add_link(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        r = c.post(
            "/api/admin/viral/add-link",
            json={"url": "https://www.tiktok.com/@kenh/video/1234567890123456789"},
        )
        assert r.status_code == 200, r.text
        mid = r.json()["id"]
        with factory() as db:
            mat = db.get(ViralMaterial, mid)
            assert mat is not None
            assert mat.status == "NEW"
    finally:
        engine.dispose()


def test_admin_sql_select(tmp_path, monkeypatch):
    engine, factory, c = _client(tmp_path)
    try:
        from app.core.db_admin import database_service as dbs

        monkeypatch.setattr(dbs, "engine", engine)
        r = c.post("/api/admin/database/sql", json={"sql": "SELECT 1 AS n", "confirmed": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in ("success", "error", "require_confirm")
    finally:
        engine.dispose()


def test_admin_overview_theo_kenh_buffer(tmp_path, monkeypatch):
    """PLAN-108: tổng quan đếm theo kênh Buffer, chỉ đọc DB."""
    import time

    from app.features.buffer import queue_job

    monkeypatch.setattr(queue_job, "_channels", lambda: [{"id": "ch1", "name": "Uyển Nhi"}, {"id": "ch2", "name": "Sống Nhẹ"}])
    now = int(time.time())
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            mats = [ViralMaterial(url=f"https://t/{i}", status="READY", target_page="ch2") for i in range(3)]
            db.add_all(mats)
            db.commit()
            db.add_all([
                # video 0 đã lên Buffer, hẹn ngày mai → không còn "chờ"
                Job(platform="buffer", status=JobStatus.DONE, viral_material_id=mats[0].id, target_page="ch2",
                    schedule_ts=now + 86400, caption="a"),
                Job(platform="buffer", status=JobStatus.DONE, target_page="ch1", schedule_ts=now - 3600, caption="b"),
                Job(platform="buffer", status=JobStatus.FAILED, target_page="ch1", last_error="limit 10/10",
                    finished_at=now - 60, caption="c"),
            ])
            db.commit()
        r = c.get("/api/admin/overview")
        assert r.status_code == 200, r.text
        d = r.json()
        by = {ch["id"]: ch for ch in d["channels"]}
        assert by["ch2"] == {"id": "ch2", "name": "Sống Nhẹ", "ready_waiting": 2, "scheduled": 1,
                             "next_at": now + 86400, "posted_7d": 0}
        assert by["ch1"]["posted_7d"] == 1 and by["ch1"]["scheduled"] == 0
        assert d["jobs_24h"] == {"DONE": 2, "FAILED": 1}
        assert d["failed_jobs"]["latest"][0]["channel"] == "Uyển Nhi"
        assert d["materials_7d"]["READY"] == 3 and d["disk"]["pause_below_gb"] == 2
    finally:
        engine.dispose()
