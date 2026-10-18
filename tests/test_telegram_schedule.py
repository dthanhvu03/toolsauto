"""Hẹn giờ từ Telegram. Cơ sở nhớ tạm, nơi đăng giả, không gọi mạng."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.contracts import PublishResult
from app.constants import JobStatus
from app.core.database.models import Base, Job, ViralMaterial
from app.core.notifier import formatting as nf
from app.features.buffer.adapter import schedule_mode
from app.features.buffer.client import BufferClient
from app.features.buffer.queue_job import (
    cancel_schedule,
    queue_reup,
    reschedule_by_post,
    schedule_reup,
)
from app.features.buffer.when import (
    ICT,
    PRESETS,
    SAMPLE,
    format_ict,
    parse_when,
    preset_ts,
    quota_block_reason,
)
from app.features.telegram_bot.command_handler import TelegramCommandHandler
from app.features.telegram_bot.event_router import TelegramEventRouter

CHANNELS = [
    {"id": "6ab38f18ea19ca0bdec2d72d", "name": "Sống Nhẹ Tuổi 40"},
    {"id": "6ab38f18ea19ca0bdec2d72e", "name": "Mê Câu Cá"},
]
FIXED = datetime(2026, 9, 24, 9, 0, tzinfo=ICT)


class _Publish:
    def __init__(self):
        self.modes = []

    def publish(self, job):
        mode, due = schedule_mode(job)
        self.modes.append(mode)
        return PublishResult(ok=True, external_post_id=f"buf_{job.id}", details={"dueAt": due, "mode": mode})


class _Tg:
    def __init__(self):
        self.msgs = []

    def send_message(self, text, reply_markup=None, **kwargs):
        self.msgs.append(text)

    def answer_callback_query(self, callback_id, text="", **kwargs):
        self.msgs.append(text or "")


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


def _mat(db, caption="Câu hay", url="https://t/hen"):
    mat = ViralMaterial(platform="tiktok", url=url, ai_caption=caption, ai_hashtags='["#ca"]')
    db.add(mat)
    db.commit()
    return mat


def _arm(monkeypatch, publisher=None):
    pub = publisher or _Publish()
    monkeypatch.setattr("app.features.buffer.queue_job._channels", lambda: CHANNELS)
    monkeypatch.setattr("app.features.buffer.queue_job.BufferAdapter", lambda: pub)
    monkeypatch.setattr("app.features.buffer.queue_job._quota_block", lambda channel, ts: None)
    return pub


def _future(seconds=7200):
    return int(datetime.now(timezone.utc).timestamp()) + seconds


def test_hen_gio_hop_le_mot_bai_khong_dang_ngay(db, monkeypatch):
    pub = _arm(monkeypatch)
    mat = _mat(db)
    when = _future()
    ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], when)
    assert ok is True
    assert "Sống Nhẹ Tuổi 40" in msg
    assert format_ict(when) in msg
    assert pub.modes == ["customScheduled"]
    job = db.query(Job).one()
    assert job.status == JobStatus.DONE
    assert job.schedule_ts == when
    assert job.external_post_id


def test_thieu_loi_bai_va_kenh_la_khong_tao(db, monkeypatch):
    pub = _arm(monkeypatch)
    mat = _mat(db, caption=None)
    ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], _future())
    assert ok is False
    assert "lời bài" in msg
    assert pub.modes == []
    assert db.query(Job).count() == 0
    mat.ai_caption = "Có chữ"
    db.commit()
    ok, msg = schedule_reup(db, mat.id, "kenh-la", _future())
    assert ok is False
    assert "không có trong danh sách" in msg
    assert db.query(Job).count() == 0


def test_lan_hai_sua_dung_bai_khong_them_job(db, monkeypatch):
    pub = _arm(monkeypatch)
    edited = {}
    monkeypatch.setattr("app.features.buffer.queue_job._post_status", lambda pid: "scheduled")
    monkeypatch.setattr(
        "app.features.buffer.queue_job._edit_due",
        lambda pid, due: edited.update(pid=pid, due=due),
    )
    quota = {"n": 0}
    real_block = None

    def _count(channel, ts):
        quota["n"] += 1
        return None

    monkeypatch.setattr("app.features.buffer.queue_job._quota_block", _count)
    mat = _mat(db)
    first, second = _future(7200), _future(10800)
    assert schedule_reup(db, mat.id, CHANNELS[0]["id"], first)[0] is True
    assert schedule_reup(db, mat.id, CHANNELS[0]["id"], second)[0] is True
    assert db.query(Job).count() == 1
    job = db.query(Job).one()
    assert job.schedule_ts == second
    assert edited["pid"] == job.external_post_id
    assert pub.modes == ["customScheduled"]
    assert quota["n"] == 1
    assert real_block is None


def test_hai_kenh_hai_lich(db, monkeypatch):
    _arm(monkeypatch)
    mat = _mat(db)
    when = _future()
    assert schedule_reup(db, mat.id, CHANNELS[0]["id"], when)[0] is True
    assert schedule_reup(db, mat.id, CHANNELS[1]["id"], when)[0] is True
    assert db.query(Job).count() == 2


def test_het_suat_khong_tao(db, monkeypatch):
    pub = _arm(monkeypatch)
    mat = _mat(db)
    monkeypatch.setattr("app.features.buffer.queue_job._quota_block", lambda c, t: "Hết suất hôm nay.")
    ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], _future())
    assert ok is False and "Hết suất hôm nay" in msg
    monkeypatch.setattr("app.features.buffer.queue_job._quota_block", lambda c, t: "Hết suất tuần.")
    ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], _future())
    assert ok is False and "Hết suất tuần" in msg
    assert pub.modes == []
    assert db.query(Job).count() == 0


def test_huy_bai_chua_dang_va_tu_choi_bai_da_dang(db, monkeypatch):
    _arm(monkeypatch)
    deleted = []
    monkeypatch.setattr("app.features.buffer.queue_job._post_status", lambda pid: "scheduled")
    monkeypatch.setattr("app.features.buffer.queue_job._edit_due", lambda pid, due: None)
    monkeypatch.setattr("app.features.buffer.queue_job._delete_post", lambda pid: deleted.append(pid))
    mat = _mat(db)
    when = _future()
    schedule_reup(db, mat.id, CHANNELS[0]["id"], when)
    job = db.query(Job).one()
    ok, msg = cancel_schedule(db, job.external_post_id)
    assert ok is True and "không tự đăng" in msg
    assert deleted == [job.external_post_id]
    db.refresh(job)
    assert job.status == JobStatus.CANCELLED
    assert job.schedule_ts == 0

    other = _mat(db, url="https://t/hen-2")
    schedule_reup(db, other.id, CHANNELS[0]["id"], when)
    sent = db.query(Job).filter(Job.status == JobStatus.DONE).one()
    monkeypatch.setattr("app.features.buffer.queue_job._post_status", lambda pid: "sent")
    deleted.clear()
    ok, msg = reschedule_by_post(db, sent.external_post_id, _future(9000))
    assert ok is False and "đã đăng" in msg.lower()
    ok, msg = cancel_schedule(db, sent.external_post_id)
    assert ok is False and "đã đăng" in msg.lower()
    assert deleted == []
    db.refresh(sent)
    assert sent.schedule_ts == when


def test_huy_khi_dang_dua_di_khong_bao_thanh_cong(db, monkeypatch):
    from app.features.buffer.client import BufferError

    _arm(monkeypatch)
    monkeypatch.setattr("app.features.buffer.queue_job._post_status", lambda pid: "sending")

    def _boom(pid):
        raise BufferError("đang đưa đi đăng")

    monkeypatch.setattr("app.features.buffer.queue_job._delete_post", _boom)
    mat = _mat(db)
    schedule_reup(db, mat.id, CHANNELS[0]["id"], _future())
    job = db.query(Job).one()
    ok, msg = cancel_schedule(db, job.external_post_id)
    assert ok is False
    assert "hủy" not in msg.lower() or "không" in msg.lower()
    assert "Đã hủy" not in msg
    db.refresh(job)
    assert job.status == JobStatus.DONE


def test_gio_sai_khong_tao_va_gio_dung_sau_do_van_tao(db, monkeypatch):
    pub = _arm(monkeypatch)
    mat = _mat(db)
    past = int(datetime.now(timezone.utc).timestamp()) - 3600
    soon = int(datetime.now(timezone.utc).timestamp()) + 60
    far = int(datetime.now(timezone.utc).timestamp()) + 31 * 86400
    for ts in (past, soon, far):
        ok, msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], ts)
        assert ok is False
        assert db.query(Job).count() == 0
    assert "tương lai" in schedule_reup(db, mat.id, CHANNELS[0]["id"], past)[1]
    assert "10 phút" in schedule_reup(db, mat.id, CHANNELS[0]["id"], soon)[1]
    assert "30 ngày" in schedule_reup(db, mat.id, CHANNELS[0]["id"], far)[1]
    assert pub.modes == []
    ok, _msg = schedule_reup(db, mat.id, CHANNELS[0]["id"], _future())
    assert ok is True
    assert pub.modes == ["customScheduled"]


def test_gio_khong_doc_duoc_co_mau_va_khong_cong_nam(db, monkeypatch):
    _arm(monkeypatch)
    mat = _mat(db)
    ts, err = parse_when("chieu mai", now=FIXED)
    assert ts is None and SAMPLE in err
    ts, err = parse_when("31/02 10:00", now=FIXED)
    assert ts is None and SAMPLE in err
    ts, err = parse_when("23/09 20:00", now=FIXED)
    assert ts is None and "tương lai" in err
    client = _Tg()
    TelegramCommandHandler(client).handle_command("hen", ["buf_1"])
    assert SAMPLE in client.msgs[-1]
    called = {"n": 0}
    monkeypatch.setattr(
        "app.features.buffer.queue_job.reschedule_by_post",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    TelegramCommandHandler(client).handle_command("hen", ["buf_1", "khong-phai-gio"])
    assert called["n"] == 0
    assert db.query(Job).count() == 0
    ok, msg = reschedule_by_post(db, "khong-co", _future())
    assert ok is False and "Không thấy" in msg


def test_xep_hang_va_dang_ngay_khong_hoi_gio(db, monkeypatch):
    pub = _arm(monkeypatch)
    mat = _mat(db)
    ok, msg = queue_reup(db, mat.id, CHANNELS[0]["id"])
    assert ok is True
    assert db.query(Job).one().schedule_ts == 0
    assert "hàng chờ" in msg
    assert "Chọn giờ" not in msg
    assert pub.modes == ["addToQueue"]

    monkeypatch.setattr("app.config.BUFFER_API_KEY", "k")

    class _Now:
        def __init__(self, key):
            self.key = key

        def publish_now(self, pid):
            return {"sentAt": "x"}

    monkeypatch.setattr("app.features.buffer.client.BufferClient", _Now)
    tg = _Tg()
    TelegramEventRouter(tg, None)._handle_buffer_post("cb", "bnow", "post-1")
    assert any("Facebook" in m or "đăng" in m.lower() for m in tg.msgs)
    assert all("Chọn giờ" not in m for m in tg.msgs)


def test_nut_goi_y_ngoai_cua_so_khong_goi_hen(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        "app.features.buffer.queue_job.schedule_reup",
        lambda *a, **k: called.__setitem__("n", 1) or (True, "không được gọi"),
    )
    err = "Giờ phải cách hiện tại ít nhất 10 phút."
    tg = _Tg()
    router = TelegramEventRouter(tg, None)
    monkeypatch.setattr("app.features.buffer.when.preset_ts", lambda code, now=None: (None, err))
    router._handle_schedule_pick("cb", f"1:{CHANNELS[0]['id']}:t20")
    assert called["n"] == 0
    assert err in "".join(tg.msgs)


def test_preset_qua_gio_hom_nay_lay_ngay_mai():
    late = datetime(2026, 9, 24, 21, 0, tzinfo=ICT)
    ts, err = preset_ts("t20", now=late)
    assert err is None and ts is not None
    when = datetime.fromtimestamp(ts, ICT)
    assert when.day == 25 and when.hour == 20 and when.minute == 0
    ts08, err08 = preset_ts("t08", now=late)
    assert err08 is None and datetime.fromtimestamp(ts08, ICT).hour == 8
    ts15, _ = preset_ts("t15", now=datetime(2026, 9, 24, 10, 0, tzinfo=ICT))
    assert datetime.fromtimestamp(ts15, ICT).hour == 15 and datetime.fromtimestamp(ts15, ICT).minute == 30
    assert set(PRESETS) == {"t08", "t12", "t15", "t20"}


def test_edit_post_gui_kem_gio_va_chu(monkeypatch):
    seen = {}
    client = BufferClient.__new__(BufferClient)

    def execute(query):
        seen["q"] = query
        return {"editPost": {"post": {"id": "p1", "dueAt": "2026-09-25T13:00:00.000Z", "status": "scheduled"}}}

    client.execute = execute
    client.post_snapshot = lambda pid: {"id": pid, "text": "lời bài", "assets": [], "metadata": {"type": "post"}}
    client.edit_post("p1", mode="customScheduled", due_at="2026-09-25T13:00:00.000Z")
    assert "customScheduled" in seen["q"]
    assert "2026-09-25T13:00:00.000Z" in seen["q"]
    assert "lời bài" in seen["q"]


def test_nut_hen_gio_khong_pha_xep_hang(monkeypatch):
    monkeypatch.setattr(nf, "_buffer_channels", lambda: CHANNELS)
    buttons = nf.material_ready_buttons(SimpleNamespace(id=12))
    flat = [b for row in buttons for b in row]
    assert flat[0]["callback_data"].startswith("bq:")
    assert flat[-1]["callback_data"] == "dadang:12"
    assert any(b["callback_data"] == "hen:12" for b in flat)
    assert all(len(b["callback_data"].encode()) <= 64 for b in flat)
    board = nf.buffer_post_keyboard("buf_1")
    data = [b["callback_data"] for row in board["inline_keyboard"] for b in row]
    assert "bnow:buf_1" in data and "bhen:buf_1" in data


def test_lenh_hen_nam_trong_menu():
    handler = TelegramCommandHandler(_Tg())
    assert "hen" in handler.handler_map()
    assert any(cmd == "hen" for cmd, _desc in handler.MENU)


def test_cong_thuc_suat():
    now = FIXED
    later_today = now.replace(hour=20)
    tomorrow = now + timedelta(days=1)
    assert quota_block_reason(when=later_today, now=now, week_left=0, day_limit=5, day_sent=0, day_scheduled=0) == "Hết suất tuần."
    assert quota_block_reason(when=later_today, now=now, week_left=2, day_limit=1, day_sent=1, day_scheduled=0) == "Hết suất hôm nay."
    assert quota_block_reason(when=tomorrow, now=now, week_left=2, day_limit=1, day_sent=1, day_scheduled=0) is None
