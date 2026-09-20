from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.core import get_db
from app.core.database.models import Account, AffiliateLink, Base, Job, ViralMaterial, ViralSource
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


def test_admin_affiliates_lists_keyword(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            db.add(
                AffiliateLink(
                    keyword="giày sneaker",
                    url="https://shope.ee/abc",
                    comment_template="Mua ở đây",
                    commission_rate=12.5,
                )
            )
            db.commit()
        r = c.get("/api/admin/affiliates")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["links"][0]["keyword"] == "giày sneaker"
        assert body["links"][0]["url"] == "https://shope.ee/abc"
    finally:
        engine.dispose()


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


def test_admin_tiktok_links_flattens_competitor_urls(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            db.add(
                Account(
                    name="Page A",
                    platform="facebook",
                    competitor_urls=json.dumps(
                        [{"url": "https://www.tiktok.com/@doi-thu", "target_page": None}]
                    ),
                )
            )
            db.commit()
        r = c.get("/api/admin/tiktok-links")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert any("@doi-thu" in (it.get("url") or "") for it in body["items"])
    finally:
        engine.dispose()


def test_admin_fb_pro_tasks_lists_scope(tmp_path, monkeypatch):
    from app.features.fb_pro_tasks import service as fb_pro

    monkeypatch.setattr(fb_pro, "CONFIG_PATH", tmp_path / "fb_pro_weekly_tasks.json")
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            db.add(
                Account(
                    name="FB Pro Page",
                    platform="facebook",
                    target_page="https://www.facebook.com/kids0810",
                )
            )
            db.commit()
        r = c.get("/api/admin/fb-pro-tasks")
        assert r.status_code == 200
        body = r.json()
        assert body["scope_key"]
        assert len(body["tasks"]) == 3
        assert {t["key"] for t in body["tasks"]} == {"posts", "reels", "interactions"}
        assert any("kids0810" in (o.get("label") or "") for o in body["scope_options"])
        assert body["overall_pct"] >= 0
    finally:
        engine.dispose()


def test_admin_threads_dashboard_stats(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            db.add(Account(name="Threads Acc", platform="facebook"))
            db.commit()
        r = c.get("/api/admin/threads")
        assert r.status_code == 200
        body = r.json()
        assert body["stats"]["pending"] == 0
        assert isinstance(body["articles"], list)
        assert isinstance(body["linked_accounts"], list)
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


def test_admin_account_create_and_toggle(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        r = c.post(
            "/api/admin/accounts",
            json={"name": "Page Native", "platform": "facebook", "daily_limit": 2},
        )
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        r2 = c.post(f"/api/admin/accounts/{aid}/toggle")
        assert r2.status_code == 200, r2.text
        with factory() as db:
            acc = db.get(Account, aid)
            assert acc is not None
            assert acc.is_active is False
    finally:
        engine.dispose()


def test_admin_affiliate_save(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        r = c.post(
            "/api/admin/affiliates",
            json={
                "keyword": "giày",
                "url": "https://shope.ee/xyz",
                "comment_template": "Mua ở đây nha",
            },
        )
        assert r.status_code == 200, r.text
        listed = c.get("/api/admin/affiliates").json()
        assert listed["total"] == 1
        lid = listed["links"][0]["id"]
        d = c.delete(f"/api/admin/affiliates/{lid}")
        assert d.status_code == 200
        assert c.get("/api/admin/affiliates").json()["total"] == 0
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


def test_admin_overview_cockpit(tmp_path):
    engine, factory, c = _client(tmp_path)
    try:
        with factory() as db:
            acc = Account(
                name="FB Acc",
                platform="facebook",
                login_error="Checkpoint detected during idle engagement",
            )
            db.add(acc)
            db.commit()
            db.refresh(acc)
            db.add(
                Job(
                    account_id=acc.id,
                    platform="facebook",
                    status="FAILED",
                    caption="fail 1",
                    last_error="publish timeout",
                    finished_at=1700000000,
                )
            )
            db.add(
                Job(
                    account_id=acc.id,
                    platform="facebook",
                    status="FAILED",
                    caption="fail 2",
                    last_error="Checkpoint URL unusual login",
                    finished_at=1700000100,
                )
            )
            db.commit()
        r = c.get("/api/admin/overview")
        assert r.status_code == 200, r.text
        ops = r.json()["ops"]
        assert ops["worker"]["status"] in ("RUNNING", "PAUSE", "SAFE")
        assert "free_gb" in ops["disk"]
        assert ops["disk"]["pause_below_gb"] == 2
        assert "open" in ops["gemini_circuit"]
        assert ops["failed_jobs"]["count"] == 2
        assert len(ops["failed_jobs"]["latest"]) == 2
        assert ops["failed_jobs"]["latest"][0]["error"]
        assert ops["checkpoint"]["count"] >= 1
        assert ops["checkpoint"]["accounts"] >= 1
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
