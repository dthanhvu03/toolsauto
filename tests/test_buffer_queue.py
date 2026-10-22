"""Nút page Buffer trên tin video + xếp hàng chờ, không đụng publisher Facebook."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.contracts import PublishResult
from app.constants import JobStatus
from app.core.database.models import Base, Job, ViralMaterial
from app.core.notifier import formatting as nf
from app.features.buffer.queue_job import queue_reup, schedule_reup, sweep_unscheduled_ready, taken_slots


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


def test_double_tap_running_job_blocks_duplicate(db, monkeypatch):
    calls = []
    class Fake:
        def publish(self, job):
            calls.append(job.id)
            return PublishResult(ok=True, external_post_id="buf_2")

    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", Fake)
    mat = ViralMaterial(platform="tiktok", url="https://t/double", ai_caption="Demo")
    db.add(mat)
    db.commit()

    # Pre-insert a RUNNING job simulating concurrent click
    running_job = Job(
        platform="buffer",
        caption="Demo",
        viral_material_id=mat.id,
        target_page=CHANNELS[0]["id"],
        status=JobStatus.RUNNING,
    )
    db.add(running_job)
    db.commit()

    ok, msg = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok is False
    assert "Đang xử lý" in msg
    assert len(calls) == 0


def test_http_429_fails_job_and_frees_video(db, monkeypatch):
    class Fake429:
        def publish(self, job):
            return PublishResult(ok=False, error="Buffer HTTP 429. Rate limit exceeded.")

    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", Fake429)
    mat = ViralMaterial(platform="tiktok", url="https://t/429", ai_caption="Demo 429")
    db.add(mat)
    db.commit()

    ok, msg = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok is False
    assert "429" in msg
    job = db.query(Job).filter(Job.viral_material_id == mat.id).one()
    assert job.status == JobStatus.FAILED
    assert job.schedule_ts == 0
    assert not (job.external_post_id or "").strip()


def test_http_429_schedule_keeps_slot_and_allows_retry(db, monkeypatch):
    when_ts = int(time.time()) + 3600

    class Fake429:
        def publish(self, job):
            return PublishResult(ok=False, error="Buffer HTTP 429. Vui lòng thử lại sau 54000s.")

    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", Fake429)
    monkeypatch.setattr("app.features.buffer.queue_job._quota_block", lambda *a, **k: None)
    mat = ViralMaterial(platform="tiktok", url="https://t/429s", ai_caption="Demo 429 slot")
    db.add(mat)
    db.commit()

    ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], when_ts)
    assert ok is False
    assert "429" in msg
    job = db.query(Job).one()
    assert job.status == JobStatus.FAILED
    assert job.schedule_ts == when_ts
    assert when_ts not in taken_slots(db, CHANNELS[0]["id"])

    ok2, _msg2 = schedule_reup(db, mat.id, CHANNELS[0]["id"], when_ts)
    assert ok2 is False
    assert db.query(Job).count() == 2


def test_sweep_stops_whole_pass_on_429(db, monkeypatch):
    calls = []

    def fake_auto(_db, material_id):
        calls.append(material_id)
        return False, "Buffer HTTP 429. Vui lòng thử lại sau 54000s."

    monkeypatch.setattr("app.features.buffer.queue_job._channel_blocked_quietly", lambda _cid: None)
    monkeypatch.setattr("app.features.buffer.queue_job.auto_schedule_ready", fake_auto)
    for idx, channel in enumerate(CHANNELS):
        db.add(
            ViralMaterial(
                platform="tiktok",
                url=f"https://t/sweep-{idx}",
                status="READY",
                target_page=channel["id"],
                ai_caption="Sẵn",
            )
        )
    db.commit()

    assert sweep_unscheduled_ready(db, limit=4) == 0
    assert len(calls) == 1


def test_sweep_skips_locked_channel_and_schedules_next(db, monkeypatch):
    calls = []

    def fake_block(channel_id):
        if channel_id == CHANNELS[0]["id"]:
            return "Key của kênh đang cooldown."
        return None

    def fake_auto(_db, material_id):
        calls.append(material_id)
        return True, "đã hẹn"

    monkeypatch.setattr("app.features.buffer.queue_job._channel_blocked_quietly", fake_block)
    monkeypatch.setattr("app.features.buffer.queue_job.auto_schedule_ready", fake_auto)
    for idx, channel in enumerate(CHANNELS):
        db.add(
            ViralMaterial(
                platform="tiktok",
                url=f"https://t/skip-{idx}",
                status="READY",
                target_page=channel["id"],
                ai_caption="Sẵn",
            )
        )
    db.commit()

    assert sweep_unscheduled_ready(db, limit=4) == 1
    mats = db.query(ViralMaterial).order_by(ViralMaterial.id).all()
    assert calls == [mats[1].id]
