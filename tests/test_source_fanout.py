"""
ADR-020 — một nguồn nối nhiều Page: nhân bản 1 video ra mỗi Page một Job.

Kiểm ở TẦNG CODE: ``target_pages_list``, ``add_source``/``scan_source`` ghi danh sách Page,
vòng lặp tạo job trong ``processor``, và guard nới đúng một nấc bằng ``sibling_material_id``.

LƯU Ý: chạy trên SQLite tạm nên **không có** hai UNIQUE partial index của Postgres
(``idx_jobs_viral_material_active``, ``idx_jobs_platform_content_hash_active`` với
``COALESCE(target_page,'')``) — tầng chặn cứng ở DB chỉ chứng minh được trên Postgres thật
(xem proof trong handoff/PLAN). Ở đây chỉ chứng minh phần code quyết định tạo mấy job.

Mock yt-dlp (subprocess.run) + ReupProcessor như tests/test_viral_ready_without_account.py:
không mạng, không ffmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import JobStatus, ViralStatus
from app.core.database.models import Account, Job, RuntimeSetting, ViralMaterial, ViralSource
from app.core.media.content_hash import assert_media_not_blocked
from app.features.viral_intake import processor, reup_processor, reup_variants, sources
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService
from app.features.viral_intake.sources import SourceService

PAGE_A = "https://www.facebook.com/page_a"
PAGE_B = "https://www.facebook.com/page_b"


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fanout.sqlite'}")
    for model in (Account, ViralMaterial, ViralSource, Job, RuntimeSetting):
        model.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _no_sleep_no_ratelimit(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sources, "_load_rate_limits", lambda: {})
    monkeypatch.setattr(sources, "_save_rate_limits", lambda tracker: None)


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    """yt-dlp + ReupProcessor giả: tạo file thật trên đĩa tạm, không mạng, không ffmpeg."""
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)

    from app.core.notifier.service import NotifierService

    notified: list[int] = []
    monkeypatch.setattr(
        NotifierService, "notify_style_selection", staticmethod(lambda job: notified.append(job.id))
    )

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            info = {"title": "demo", "view_count": 1234, "formats": [{"vcodec": "h264", "ext": "mp4"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        template = argv[argv.index("-o") + 1]
        out = template.replace("%(id)s", "src").replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 2048)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)

    def fake_reup(input_path, platform="unknown", **kwargs):
        out = input_path.replace(".mp4", "_reup.mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={"preset": kwargs.get("preset")})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))
    return notified


@pytest.fixture
def fake_yt_dlp_scan(monkeypatch):
    """yt-dlp --flat-playlist giả cho SourceService.scan_source (1 video đạt view)."""
    rows = [{"id": "7001", "uploader": "mrwork93", "title": "Big one", "view_count": 5_000_000}]
    stdout = "\n".join(json.dumps(r) for r in rows) + "\n"

    def fake_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess([str(c) for c in cmd], 0, stdout=stdout, stderr="")

    monkeypatch.setattr(sources.subprocess, "run", fake_run)


def _active_account(session_factory, name: str = "fb_acc") -> None:
    with session_factory() as db:
        db.add(Account(name=name, platform="facebook", is_active=True, login_status="ACTIVE"))
        db.commit()


def _material(session_factory, url: str, *, pages: list[str] | None = None, target_page: str | None = None) -> int:
    with session_factory() as db:
        mat = ViralMaterial(platform="facebook", url=url, title="", views=0, status=ViralStatus.NEW)
        if pages is not None:
            mat.target_pages_list = pages
        elif target_page:
            mat.target_page = target_page
        db.add(mat)
        db.commit()
        return mat.id


# ---------------------------------------------------------------------------
# (a) target_pages_list — 3 thứ tự ưu tiên
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model", [ViralSource, ViralMaterial])
def test_target_pages_list_priority(model):
    obj = model()
    # 3. không có gì → []
    assert obj.target_pages_list == []
    # 2. chỉ có target_page legacy → [target_page]
    obj.target_page = PAGE_A
    assert obj.target_pages_list == [PAGE_A]
    # 1. có target_pages → ưu tiên danh sách, kể cả khi target_page lệch
    obj.target_pages = json.dumps([PAGE_B, PAGE_A])
    assert obj.target_pages_list == [PAGE_B, PAGE_A]
    # JSON hỏng / không phải list → lùi về legacy
    obj.target_pages = "{khong-phai-json"
    assert obj.target_pages_list == [PAGE_A]


def test_target_pages_setter_normalizes_and_keeps_legacy_column():
    src = ViralSource()
    src.target_pages_list = [f"  {PAGE_B}  ", PAGE_A, PAGE_B, "", "   "]
    assert json.loads(src.target_pages) == [PAGE_B, PAGE_A]  # strip + dedup + giữ thứ tự
    assert src.target_page == PAGE_B  # legacy = Page đầu tiên
    src.target_pages_list = []
    assert src.target_pages is None and src.target_page is None


# ---------------------------------------------------------------------------
# (b) add_source nhận nhiều Page
# ---------------------------------------------------------------------------
def test_add_source_stores_multiple_pages(session_factory):
    with session_factory() as db:
        ok, _, sid = SourceService.add_source(
            db,
            "https://www.tiktok.com/@mrwork93",
            min_views=1000,
            max_videos=1,
            target_pages=[PAGE_A, f" {PAGE_B} ", PAGE_A, ""],
        )
        assert ok
        src = db.get(ViralSource, sid)
        assert json.loads(src.target_pages) == [PAGE_A, PAGE_B]
        assert src.target_pages_list == [PAGE_A, PAGE_B]
        assert src.target_page == PAGE_A  # tương thích ngược


def test_add_source_legacy_single_target_page_still_works(session_factory):
    with session_factory() as db:
        ok, _, sid = SourceService.add_source(db, "https://www.tiktok.com/@abc", target_page=PAGE_A)
        assert ok
        src = db.get(ViralSource, sid)
        assert src.target_page == PAGE_A
        assert src.target_pages_list == [PAGE_A]

        ok2, _, sid2 = SourceService.add_source(db, "https://www.tiktok.com/@xyz")
        assert ok2
        src2 = db.get(ViralSource, sid2)
        assert src2.target_page is None and src2.target_pages is None
        assert src2.target_pages_list == []


# ---------------------------------------------------------------------------
# (c) scan_source chép danh sách Page sang material
# ---------------------------------------------------------------------------
def test_scan_source_copies_target_pages_to_material(session_factory, fake_yt_dlp_scan):
    with session_factory() as db:
        _, _, sid = SourceService.add_source(
            db, "https://www.tiktok.com/@mrwork93", min_views=1000, max_videos=1,
            target_pages=[PAGE_A, PAGE_B],
        )
        found, _, error = SourceService.scan_source(db, db.get(ViralSource, sid))
        assert (found, error) == (1, None)
        mat = db.query(ViralMaterial).one()
        assert mat.target_pages_list == [PAGE_A, PAGE_B]
        assert mat.target_page == PAGE_A  # chỗ đọc `mat.target_page` cũ không vỡ


# ---------------------------------------------------------------------------
# (d) fan-out: 1 material 2 Page → 2 Job
# ---------------------------------------------------------------------------
def test_fanout_two_pages_creates_two_jobs(session_factory, fake_pipeline):
    _active_account(session_factory)
    mid = _material(session_factory, "https://www.facebook.com/reel/100", pages=[PAGE_A, PAGE_B])

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.DRAFTED

        jobs = db.query(Job).order_by(Job.id.asc()).all()
        assert len(jobs) == 2
        assert [j.target_page for j in jobs] == [PAGE_A, PAGE_B]
        assert jobs[0].content_hash and jobs[0].content_hash == jobs[1].content_hash
        assert {j.viral_material_id for j in jobs} == {mid}
        assert {j.status for j in jobs} == {JobStatus.AWAITING_STYLE}
        assert {j.media_path for j in jobs} == {jobs[0].media_path}
        # ADR-020 mục 5: job thứ 2 lệch giờ ≥ 1800s so với job 1 (chống đăng trùng một phút)
        assert jobs[1].schedule_ts - jobs[0].schedule_ts >= 1800
        # notify_style_selection gọi cho TỪNG job
        assert sorted(fake_pipeline) == sorted(j.id for j in jobs)


# ---------------------------------------------------------------------------
# (e) không có target_pages → đường cũ, đúng 1 job
# ---------------------------------------------------------------------------
def test_material_without_target_pages_keeps_single_job(session_factory, fake_pipeline):
    _active_account(session_factory)
    mid = _material(session_factory, "https://www.facebook.com/reel/101")

    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.DRAFTED
        jobs = db.query(Job).all()
        assert len(jobs) == 1
        assert jobs[0].viral_material_id == mid
        assert len(fake_pipeline) == 1


# ---------------------------------------------------------------------------
# (f) guard — sibling_material_id nới đúng một nấc
# ---------------------------------------------------------------------------
def test_guard_sibling_passes_but_other_material_still_blocked(session_factory, tmp_path):
    with session_factory() as db:
        acc = Account(name="acc", platform="facebook", is_active=True, login_status="ACTIVE")
        db.add(acc)
        mat_a = ViralMaterial(platform="facebook", url="https://x/1", status=ViralStatus.DRAFTED)
        mat_b = ViralMaterial(platform="facebook", url="https://x/2", status=ViralStatus.NEW)
        db.add_all([mat_a, mat_b])
        db.commit()
        db.add(
            Job(
                platform="facebook",
                account_id=acc.id,
                media_path=str(tmp_path / "v.mp4"),
                status=JobStatus.AWAITING_STYLE,
                target_page=PAGE_A,
                content_hash="hash-abc",
                viral_material_id=mat_a.id,
            )
        )
        db.commit()

        # Cùng material → cho qua khi khai báo sibling
        assert_media_not_blocked(
            db, platform="facebook", content_hash="hash-abc",
            viral_material_id=mat_a.id, sibling_material_id=mat_a.id,
        )

        # Mặc định (không sibling) → vẫn chặn y như PLAN-041
        with pytest.raises(ValueError):
            assert_media_not_blocked(db, platform="facebook", content_hash="hash-abc", viral_material_id=mat_a.id)

        # Material KHÁC nhưng cùng hash → vẫn chặn, kể cả khi khai báo sibling của chính nó
        with pytest.raises(ValueError, match="same media hash"):
            assert_media_not_blocked(
                db, platform="facebook", content_hash="hash-abc",
                viral_material_id=mat_b.id, sibling_material_id=mat_b.id,
            )


def test_guard_still_blocks_manual_job_without_material(session_factory, tmp_path):
    """Job upload tay (viral_material_id NULL) cùng hash vẫn phải chặn — không được lọt vì lọc sibling."""
    with session_factory() as db:
        acc = Account(name="acc", platform="facebook", is_active=True, login_status="ACTIVE")
        db.add(acc)
        mat = ViralMaterial(platform="facebook", url="https://x/3", status=ViralStatus.NEW)
        db.add(mat)
        db.commit()
        db.add(
            Job(
                platform="facebook",
                account_id=acc.id,
                media_path=str(tmp_path / "v2.mp4"),
                status=JobStatus.PENDING,
                content_hash="hash-manual",
                viral_material_id=None,
            )
        )
        db.commit()
        with pytest.raises(ValueError, match="same media hash"):
            assert_media_not_blocked(
                db, platform="facebook", content_hash="hash-manual",
                viral_material_id=mat.id, sibling_material_id=mat.id,
            )


# ---------------------------------------------------------------------------
# (g) ADR-018 vẫn nguyên: 0 account → READY, 0 job
# ---------------------------------------------------------------------------
def test_no_account_still_ready_without_job_even_with_pages(session_factory, fake_pipeline):
    mid = _material(session_factory, "https://www.facebook.com/reel/102", pages=[PAGE_A, PAGE_B])
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY
        assert db.query(Job).count() == 0
        assert fake_pipeline == []
