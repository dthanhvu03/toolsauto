"""Nút page Buffer trên tin video + xếp hàng chờ, không đụng publisher Facebook."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.contracts import PublishResult
from app.constants import JobStatus
from app.core.database.models import Base, Job, ViralMaterial
from app.core.notifier import formatting as nf
from app.features.buffer.queue_job import queue_reup


CHANNELS = [
    {"id": "6ab38f18ea19ca0bdec2d72d", "name": "Sống Nhẹ Tuổi 40"},
    {"id": "6ab38f18ea19ca0bdec2d72e", "name": "Mê Câu Cá"},
]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_nut_page_nam_tren_nut_da_dang(monkeypatch):
    monkeypatch.setattr(nf, "_buffer_channels", lambda: CHANNELS)
    buttons = nf.material_ready_buttons(SimpleNamespace(id=12))
    flat = [b for row in buttons for b in row]
    assert flat[-1]["callback_data"] == "dadang:12"
    assert flat[0]["callback_data"] == "bq:12:6ab38f18ea19ca0bdec2d72d"
    assert all(len(b["callback_data"].encode()) <= 64 for b in flat)


def test_khong_co_caption_thi_khong_goi_buffer(db, monkeypatch):
    called = {"n": 0}

    class Fake:
        def publish(self, job):
            called["n"] += 1
            return PublishResult(ok=True, external_post_id="x")

    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", Fake)
    mat = ViralMaterial(platform="tiktok", url="https://t/1", ai_caption=None)
    db.add(mat)
    db.commit()
    ok, msg = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok is False
    assert "caption" in msg.lower()
    assert called["n"] == 0
    assert db.query(Job).count() == 0


def test_xep_hang_mot_lan(db, monkeypatch):
    class Fake:
        def publish(self, job):
            assert job.caption.startswith("Câu hay")
            assert "#ca" in job.caption
            assert job.media_path is None
            assert job.viral_material_id
            assert job.target_page == CHANNELS[0]["id"]
            assert job.schedule_ts == 0
            return PublishResult(ok=True, external_post_id="buf_1", details={"dueAt": "2026-09-24T10:00:00.000Z"})

    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", Fake)
    mat = ViralMaterial(
        platform="tiktok",
        url="https://t/2",
        ai_caption="Câu hay",
        ai_hashtags='["#ca"]',
    )
    db.add(mat)
    db.commit()
    ok, msg = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok is True
    assert "Sống Nhẹ Tuổi 40" in msg
    job = db.query(Job).one()
    assert job.status == JobStatus.DONE
    assert job.external_post_id == "buf_1"
    assert job.platform == "buffer"
    db.refresh(mat)
    assert mat.target_page == CHANNELS[0]["id"]

    ok2, msg2 = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok2 is True
    assert "rồi" in msg2
    assert db.query(Job).count() == 1
