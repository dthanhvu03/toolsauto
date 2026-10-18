"""Buffer báo đã gửi thì gọi đúng đường đánh dấu đã đăng. Không gọi mạng, không dời file."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import JobStatus, ViralStatus
from app.core.database.models import Base, Job, ViralMaterial
from app.features.buffer.sync_posted import apply_sent, ready_post_ids


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _ready(db, url, post_id, status=ViralStatus.READY):
    mat = ViralMaterial(platform="tiktok", url=url, status=status, ai_caption="có chữ")
    db.add(mat)
    db.commit()
    db.add(
        Job(
            platform="buffer",
            viral_material_id=mat.id,
            external_post_id=post_id,
            status=JobStatus.DONE,
            schedule_ts=0,
            target_page="ch",
        )
    )
    db.commit()
    return mat


def test_bai_chua_gui_khong_danh_dau():
    db = _db()
    mat = _ready(db, "https://t/1", "p1")
    called = []

    def marker(session, material_id):
        called.append(material_id)
        return True, "đã đăng"

    done = apply_sent(db, ready_post_ids(db), lambda pid: "scheduled", marker)
    assert done == []
    assert called == []
    assert mat.status == ViralStatus.READY


def test_bai_da_gui_goi_dung_nut_va_chi_mot_lan():
    db = _db()
    mat = _ready(db, "https://t/2", "p2")

    def marker(session, material_id):
        row = session.query(ViralMaterial).filter(ViralMaterial.id == material_id).one()
        row.status = ViralStatus.POSTED
        session.commit()
        return True, f"✅ #{material_id} đã đăng"

    done = apply_sent(db, ready_post_ids(db), lambda pid: "sent", marker)
    assert done == [(mat.id, f"✅ #{mat.id} đã đăng")]
    assert ready_post_ids(db) == {}
    assert apply_sent(db, ready_post_ids(db), lambda pid: "sent", marker) == []


def test_loi_chua_gui_va_ma_gia_khong_tinh():
    db = _db()
    _ready(db, "https://t/3", "err")
    mat = ViralMaterial(platform="tiktok", url="https://t/4", status=ViralStatus.READY)
    db.add(mat)
    db.commit()
    db.add(
        Job(
            platform="buffer",
            viral_material_id=mat.id,
            external_post_id="safe_mode_dry_run",
            status=JobStatus.DONE,
        )
    )
    db.commit()
    called = []
    apply_sent(db, ready_post_ids(db), lambda pid: "error", lambda *a: called.append(a) or (True, "x"))
    assert called == []
    assert mat.id not in ready_post_ids(db)


def test_mot_kenh_da_gui_la_du_kenh_kia_con_lich():
    db = _db()
    mat = _ready(db, "https://t/5", "open")
    db.add(
        Job(
            platform="buffer",
            viral_material_id=mat.id,
            external_post_id="sent-1",
            status=JobStatus.DONE,
            target_page="ch2",
        )
    )
    db.commit()

    def status_of(pid):
        return "sent" if pid == "sent-1" else "scheduled"

    seen = []

    def marker(session, material_id):
        seen.append(material_id)
        row = session.query(ViralMaterial).filter(ViralMaterial.id == material_id).one()
        row.status = ViralStatus.POSTED
        session.commit()
        return True, "ok"

    done = apply_sent(db, ready_post_ids(db), status_of, marker)
    assert [mid for mid, _msg in done] == [mat.id]
    assert seen == [mat.id]


def test_khong_doc_duoc_bai_thi_chua_danh_dau():
    db = _db()
    _ready(db, "https://t/6", "mat-6")

    def status_of(pid):
        raise RuntimeError("mạng")

    called = []
    done = apply_sent(db, ready_post_ids(db), status_of, lambda *a: called.append(a) or (True, "x"))
    assert done == []
    assert called == []


def test_da_danh_dau_tay_thi_khong_nam_trong_hang():
    db = _db()
    mat = _ready(db, "https://t/7", "p7", status=ViralStatus.POSTED)
    assert mat.id not in ready_post_ids(db)


def test_sync_gap_429_thi_dung_khong_hoi_tiep(monkeypatch):
    import app.config as config
    import app.features.buffer.sync_posted as mod
    from app.features.buffer.client import BufferError

    db = _db()
    _ready(db, "https://t/429a", "p429a")
    _ready(db, "https://t/429b", "p429b")
    mod._last_sync_ts = 0
    mod._status_offset = 0
    monkeypatch.setattr(config, "BUFFER_API_KEY", "k")
    calls = []

    class Fake:
        def __init__(self, key):
            calls.append(key)

        def post_statuses(self, ids):
            calls.append(tuple(ids))
            raise BufferError("Buffer HTTP 429.", status_code=429)

    monkeypatch.setattr("app.features.buffer.client.BufferClient", Fake)
    marked = []
    monkeypatch.setattr(
        "app.features.viral_intake.service.ViralService.mark_posted",
        lambda *args, **kwargs: marked.append(args) or (True, "x"),
    )
    assert mod.sync_sent_marks(db, now=1_000_000, force=True) == []
    assert set(calls[1]) == {"p429a", "p429b"}
    assert marked == []
    assert mod.sync_sent_marks(db, now=1_000_000 + 60) == []
    assert len([item for item in calls if item != "k"]) == 1


def test_sync_mot_request_danh_dau_bai_da_gui(monkeypatch):
    import app.config as config
    import app.features.buffer.sync_posted as mod

    db = _db()
    mat = _ready(db, "https://t/sent", "psent")
    _ready(db, "https://t/wait", "pwait")
    mod._last_sync_ts = 0
    calls = []

    class Fake:
        def __init__(self, key):
            pass

        def post_statuses(self, ids):
            calls.append(tuple(ids))
            return {"psent": "sent", "pwait": "scheduled"}

    monkeypatch.setattr(config, "BUFFER_API_KEY", "k")
    monkeypatch.setattr("app.features.buffer.client.BufferClient", Fake)
    monkeypatch.setattr(
        "app.features.viral_intake.service.ViralService.mark_posted",
        lambda session, material_id: (True, f"#{material_id}"),
    )
    monkeypatch.setattr(
        "app.core.notifier.service.NotifierService._broadcast",
        lambda msg: None,
    )
    marked = mod.sync_sent_marks(db, now=2_000_000, force=True)
    assert marked == [mat.id]
    assert len(calls) == 1
    assert set(calls[0]) == {"psent", "pwait"}


def test_status_slice_xoay_tung_cum():
    import app.features.buffer.sync_posted as mod

    old = mod._STATUS_BATCH
    mod._STATUS_BATCH = 2
    mod._status_offset = 0
    try:
        ids = ["a", "b", "c", "d"]
        assert mod._status_slice(ids) == ["a", "b"]
        assert mod._status_slice(ids) == ["c", "d"]
        assert mod._status_slice(ids) == ["a", "b"]
    finally:
        mod._STATUS_BATCH = old
        mod._status_offset = 0


def test_apply_errors_marks_job_failed_and_calls_deleter():
    from app.features.buffer.sync_posted import apply_errors

    db = _db()
    mat = _ready(db, "https://t/err", "post_err")
    deleted = []

    def fake_deleter(pid):
        deleted.append(pid)

    errors = apply_errors(db, {mat.id: ["post_err"]}, lambda pid: "error", deleter=fake_deleter)
    assert len(errors) == 1
    assert errors[0][0] == mat.id
    assert deleted == ["post_err"]

    job = db.query(Job).filter(Job.external_post_id == "post_err").one()
    assert job.status == JobStatus.FAILED
    assert "Buffer" in job.last_error


def test_sync_multi_account_posted(monkeypatch):
    import time
    import app.features.buffer.sync_posted as mod
    from app.features.buffer.manager import BufferManager

    db = _db()
    mat1 = _ready(db, "https://t/multi1", "post_m1")
    mat2 = _ready(db, "https://t/multi2", "post_m2")
    job1 = db.query(Job).filter(Job.viral_material_id == mat1.id).first()
    job1.target_page = "ch1"
    job2 = db.query(Job).filter(Job.viral_material_id == mat2.id).first()
    job2.target_page = "ch2"
    db.commit()
    mod._last_sync_ts = 0

    class FakeClient1:
        def __init__(self):
            self._key = "key1"
        def post_statuses(self, ids):
            return {pid: "sent" for pid in ids if pid == "post_m1"}
        def delete_post(self, pid):
            pass

    class FakeClient2:
        def __init__(self):
            self._key = "key2"
        def post_statuses(self, ids):
            return {pid: "sent" for pid in ids if pid == "post_m2"}
        def delete_post(self, pid):
            pass

    c1 = FakeClient1()
    c2 = FakeClient2()
    mgr = BufferManager(clients=[c1, c2])
    mgr._channel_to_client = {"ch1": c1, "ch2": c2}
    mgr._channel_cache_ts = time.time() + 1000

    monkeypatch.setattr("app.features.buffer.manager.get_buffer_manager", lambda: mgr)
    monkeypatch.setattr(
        "app.features.viral_intake.service.ViralService.mark_posted",
        lambda session, material_id: (True, f"#{material_id}"),
    )
    monkeypatch.setattr("app.core.notifier.service.NotifierService._broadcast", lambda msg: None)

    marked = mod.sync_sent_marks(db, force=True)
    assert set(marked) == {mat1.id, mat2.id}

