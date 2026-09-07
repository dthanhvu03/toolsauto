"""
Nút bấm tay ở /viral (process / retry / process-new) phải trả toast NGAY và đẩy pipeline
nặng (yt-dlp + ffmpeg) xuống BackgroundTasks — không treo request tới khi tải xong.

Dựng app FastAPI tối thiểu chỉ gồm viral router (bỏ auth middleware của app.main),
DB SQLite tạm, và monkeypatch ViralService.process_material / process_new_batch để
khẳng định hàm nặng được gọi qua task nền với đúng tham số + session riêng.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.constants import ViralStatus
from app.core.database.core import get_db
from app.core.database.models import Account, Job, ViralMaterial
from app.features.viral_intake import router as viral_router
from app.features.viral_intake.service import ViralService


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'viral_bg.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def client(session_factory, monkeypatch):
    app = FastAPI()
    app.include_router(viral_router.router)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # Task nền mở session riêng qua SessionLocal của router → trỏ về DB tạm.
    monkeypatch.setattr(viral_router, "SessionLocal", session_factory)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    return TestClient(app)


@pytest.fixture
def calls(monkeypatch):
    """Ghi lại mọi lời gọi hàm nặng thay vì chạy yt-dlp/ffmpeg thật."""
    recorded: list[tuple] = []

    def fake_process_material(db, material_id):
        recorded.append(("process_material", db, material_id))
        return True, f"fake ok #{material_id}"

    def fake_process_new_batch(db, limit=3):
        recorded.append(("process_new_batch", db, limit))
        return 1, 0, "fake batch"

    monkeypatch.setattr(ViralService, "process_material", staticmethod(fake_process_material))
    monkeypatch.setattr(ViralService, "process_new_batch", staticmethod(fake_process_new_batch))
    return recorded


def _material(session_factory, status: str, url: str = "https://t.tk/v1") -> int:
    with session_factory() as db:
        mat = ViralMaterial(platform="tiktok", url=url, title="x", views=1000, status=status)
        db.add(mat)
        db.commit()
        return mat.id


def _triggers(resp) -> dict:
    return json.loads(resp.headers["HX-Trigger"])


# ── process / retry ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("endpoint", ["process", "retry"])
@pytest.mark.parametrize("status", [ViralStatus.NEW, ViralStatus.REUP, ViralStatus.FAILED])
def test_accepts_immediately_and_runs_in_background(client, session_factory, calls, endpoint, status):
    mid = _material(session_factory, status)

    resp = client.post(f"/viral/{mid}/{endpoint}")

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert "đang xử lý nền" in trig["showMessage"]["msg"]
    assert trig["refreshViralTable"] is True
    assert trig["viralBackgroundStarted"] is True

    # TestClient chạy xong background task trước khi trả response → đã được gọi đúng 1 lần.
    assert [c[0] for c in calls] == ["process_material"]
    _, bg_db, called_id = calls[0]
    assert called_id == mid
    assert isinstance(bg_db, Session)


def test_background_uses_its_own_session_not_the_request_one(client, session_factory, calls, monkeypatch):
    mid = _material(session_factory, ViralStatus.NEW)
    request_sessions: list[Session] = []
    original_check = ViralService.check_processable

    def spy_check(db, material_id):
        request_sessions.append(db)
        return original_check(db, material_id)

    monkeypatch.setattr(ViralService, "check_processable", staticmethod(spy_check))

    client.post(f"/viral/{mid}/process")

    assert len(request_sessions) == 1 and len(calls) == 1
    assert calls[0][1] is not request_sessions[0]


def test_processing_material_is_rejected_synchronously(client, session_factory, calls):
    mid = _material(session_factory, ViralStatus.PROCESSING)

    resp = client.post(f"/viral/{mid}/process")

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "error"
    assert "PROCESSING" in trig["showMessage"]["msg"]
    assert "viralBackgroundStarted" not in trig
    assert calls == []


@pytest.mark.parametrize("status", [ViralStatus.DRAFTED, ViralStatus.BOOST_PENDING])
def test_non_processable_status_is_rejected_synchronously(client, session_factory, calls, status):
    mid = _material(session_factory, status)

    trig = _triggers(client.post(f"/viral/{mid}/retry"))

    assert trig["showMessage"]["type"] == "error"
    assert "chỉ xử lý NEW/REUP/FAILED" in trig["showMessage"]["msg"]
    assert calls == []


def test_missing_material_is_rejected_synchronously(client, calls):
    trig = _triggers(client.post("/viral/9999/process"))

    assert trig["showMessage"]["type"] == "error"
    assert "Không tìm thấy" in trig["showMessage"]["msg"]
    assert calls == []


def test_missing_ffmpeg_is_rejected_synchronously(client, session_factory, calls, monkeypatch):
    mid = _material(session_factory, ViralStatus.NEW)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: False))

    trig = _triggers(client.post(f"/viral/{mid}/process"))

    assert trig["showMessage"]["type"] == "error"
    assert "ffmpeg" in trig["showMessage"]["msg"]
    assert calls == []


def test_background_failure_is_logged_not_swallowed(client, session_factory, monkeypatch, caplog):
    mid = _material(session_factory, ViralStatus.NEW)

    def boom(db, material_id):
        raise RuntimeError("yt-dlp exploded")

    monkeypatch.setattr(ViralService, "process_material", staticmethod(boom))

    with caplog.at_level(logging.ERROR, logger=viral_router.__name__):
        resp = client.post(f"/viral/{mid}/process")

    assert resp.status_code == 204
    assert _triggers(resp)["showMessage"]["type"] == "success"
    rec = [r for r in caplog.records if "Lỗi xử lý nền" in r.getMessage()]
    assert rec and rec[0].exc_info and "yt-dlp exploded" in str(rec[0].exc_info[1])


# ── process-new ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("limit", [1, 3])
def test_process_new_accepts_immediately_with_limit(client, session_factory, calls, limit):
    _material(session_factory, ViralStatus.NEW, url="https://t.tk/a")
    _material(session_factory, ViralStatus.NEW, url="https://t.tk/b")

    resp = client.post("/viral/process-new", data={"limit": str(limit)})

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert "đang xử lý nền" in trig["showMessage"]["msg"]
    assert trig["viralBackgroundStarted"] is True
    assert [(c[0], c[2]) for c in calls] == [("process_new_batch", limit)]
    assert isinstance(calls[0][1], Session)


def test_process_new_without_new_materials_is_rejected_synchronously(client, session_factory, calls):
    _material(session_factory, ViralStatus.DRAFTED)

    trig = _triggers(client.post("/viral/process-new", data={"limit": "3"}))

    assert trig["showMessage"]["type"] == "error"
    assert "Không còn video mới" in trig["showMessage"]["msg"]
    assert "viralBackgroundStarted" not in trig
    assert calls == []


def test_process_new_without_ffmpeg_is_rejected_synchronously(client, session_factory, calls, monkeypatch):
    _material(session_factory, ViralStatus.NEW)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: False))

    trig = _triggers(client.post("/viral/process-new", data={"limit": "3"}))

    assert trig["showMessage"]["type"] == "error"
    assert "ffmpeg" in trig["showMessage"]["msg"]
    assert calls == []


# ── service: check_processable tách ra không đổi hành vi process_material ────


def test_process_material_still_rejects_processing(session_factory, monkeypatch):
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    mid = _material(session_factory, ViralStatus.PROCESSING)
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
    assert ok is False and "PROCESSING" in msg
