"""Ô giờ theo kênh và tự hẹn khi video đã có page. Không gọi mạng."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus
from app.core.database.models import Base, Job, ViralMaterial
from app.features.buffer.queue_job import auto_schedule_ready
from app.features.buffer.slots import channel_hours, next_free_slot
from app.features.buffer.when import ICT

NOW = datetime(2026, 9, 24, 9, 0, tzinfo=ICT)
UYEN = "chan-uyen"
CHANNELS = [{"id": UYEN, "name": "Uyển Nhi"}]


def test_gio_kenh_khop_ten():
    assert channel_hours("Uyển Nhi") == [(8, 0), (15, 30), (19, 30)]
    assert channel_hours("Sống Nhẹ Tuổi 40") == [(7, 30), (11, 30), (14, 30), (17, 30), (20, 30)]
    assert channel_hours("Mê Câu Cá") == [(11, 0), (16, 30), (20, 0)]
    assert channel_hours("Kênh lạ") == [(9, 0), (14, 0), (19, 0)]


def test_o_ke_bo_gio_da_qua_va_o_da_giu():
    ts, err = next_free_slot("Uyển Nhi", set(), now=NOW)
    assert err is None
    assert datetime.fromtimestamp(ts, ICT).strftime("%H:%M %d/%m") == "15:30 24/09"

    taken = {ts}
    later, err = next_free_slot("Uyển Nhi", taken, now=NOW)
    assert err is None
    assert datetime.fromtimestamp(later, ICT).strftime("%H:%M %d/%m") == "19:30 24/09"

    full_day = {
        int(datetime(2026, 9, 24, 8, 0, tzinfo=ICT).timestamp()),
        int(datetime(2026, 9, 24, 10, 0, tzinfo=ICT).timestamp()),
        int(datetime(2026, 9, 24, 11, 0, tzinfo=ICT).timestamp()),
    }
    nxt, err = next_free_slot("Uyển Nhi", full_day, now=NOW)
    assert err is None
    assert datetime.fromtimestamp(nxt, ICT).strftime("%H:%M %d/%m") == "08:00 25/09"


def test_du_3_bai_thi_sang_ngay_sau():
    """Ba bài lệch giờ vẫn khoá cả ngày, dù ô 15:30 còn trống."""
    taken = [
        int(datetime(2026, 9, 24, 8, 0, tzinfo=ICT).timestamp()),
        int(datetime(2026, 9, 24, 15, 30, tzinfo=ICT).timestamp()),
        int(datetime(2026, 9, 24, 19, 30, tzinfo=ICT).timestamp()),
    ]
    ts, err = next_free_slot("Uyển Nhi", taken, now=datetime(2026, 9, 24, 7, 0, tzinfo=ICT))
    assert err is None
    assert datetime.fromtimestamp(ts, ICT).strftime("%d/%m") == "25/09"


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


def _mat(db, page=UYEN, caption="Áo dài này nhìn là mê"):
    mat = ViralMaterial(
        platform="tiktok",
        url="https://www.tiktok.com/@a/video/1",
        title="ao dai",
        status="READY",
        target_page=page,
        ai_caption=caption,
        ai_hashtags="[]",
    )
    db.add(mat)
    db.commit()
    return mat


def test_tin_tele_noi_lich_de_quyet():
    from types import SimpleNamespace

    from app.core.notifier import formatting as nf

    mat = SimpleNamespace(
        id=12,
        platform="tiktok",
        title="Áo dài",
        views=10,
        ai_caption="Nhìn là mê",
        ai_hashtags_list=["#aodai"],
        ai_caption_error=None,
        schedule_report="Đã hẹn Uyển Nhi lúc 15:30 05/10.",
    )
    msg = nf.material_ready_message(mat, "/x/a.mp4")
    assert "Video đã xếp lịch" in msg
    assert "Đã hẹn Uyển Nhi lúc 15:30 05/10." in msg
    assert "Nhìn là mê" in msg
    buttons = nf.material_ready_buttons(mat)
    labels = [b["text"] for row in buttons for b in row]
    assert labels == ["Đổi giờ", "Hủy lịch", "✅ Đã đăng"]

    mat.schedule_report = "Chưa tự đăng: Hết suất tuần."
    warn = nf.material_ready_message(mat, "/x/a.mp4")
    assert "Video sẵn sàng đăng tay" in warn
    assert "Hết suất tuần" in warn


def test_khong_page_thi_khong_hen(db, monkeypatch):
    mat = _mat(db, page=None)
    called = []
    monkeypatch.setattr(
        "app.features.buffer.queue_job.schedule_reup",
        lambda *a, **k: called.append(1) or (True, "no"),
    )
    ok, msg = auto_schedule_ready(db, mat.id)
    assert ok is False
    assert msg == ""
    assert called == []


def test_da_co_lich_thi_khong_goi_lai(db, monkeypatch):
    mat = _mat(db)
    db.add(
        Job(
            platform="buffer",
            viral_material_id=mat.id,
            target_page=UYEN,
            status=JobStatus.DONE,
            schedule_ts=1,
            caption="x",
        )
    )
    db.commit()
    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    called = []
    monkeypatch.setattr(
        "app.features.buffer.queue_job.schedule_reup",
        lambda *a, **k: called.append(a),
    )
    ok, msg = auto_schedule_ready(db, mat.id)
    assert ok is True
    assert msg.startswith("Đã có lịch")
    assert called == []


def test_tu_hen_dung_o_ke(db, monkeypatch):
    mat = _mat(db)
    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    seen = {}

    def fake_schedule(_db, material_id, channel_id, when_ts):
        seen.update(material_id=material_id, channel_id=channel_id, when_ts=when_ts)
        return True, "đã hẹn"

    monkeypatch.setattr("app.features.buffer.queue_job.schedule_reup", fake_schedule)
    monkeypatch.setattr(
        "app.features.buffer.slots.next_free_slot",
        lambda name, taken, now=None, skip_days=None: (1_800_000_000, None),
    )
    ok, msg = auto_schedule_ready(db, mat.id)
    assert ok is True
    assert seen == {"material_id": mat.id, "channel_id": UYEN, "when_ts": 1_800_000_000}
    assert msg == "đã hẹn"


def test_het_suat_hom_nay_thi_lay_ngay_mai(db, monkeypatch):
    mat = _mat(db)
    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    calls = []

    def fake_schedule(_db, material_id, channel_id, when_ts):
        calls.append(when_ts)
        if len(calls) == 1:
            return False, "Hết suất hôm nay."
        return True, "đã hẹn ngày mai"

    monkeypatch.setattr("app.features.buffer.queue_job.schedule_reup", fake_schedule)
    ok, msg = auto_schedule_ready(db, mat.id)
    assert ok is True
    assert msg == "đã hẹn ngày mai"
    assert len(calls) == 2
    first = datetime.fromtimestamp(calls[0], ICT).date()
    second = datetime.fromtimestamp(calls[1], ICT).date()
    assert second > first


def test_buffer_429_thi_dung(db, monkeypatch):
    mat = _mat(db)
    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    calls = []

    def fake_schedule(_db, material_id, channel_id, when_ts):
        calls.append(when_ts)
        return False, "Buffer HTTP 429."

    monkeypatch.setattr("app.features.buffer.queue_job.schedule_reup", fake_schedule)
    ok, msg = auto_schedule_ready(db, mat.id)
    assert ok is False
    assert "429" in msg
    assert len(calls) == 1
