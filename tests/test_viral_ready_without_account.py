"""
ADR-018: xưởng nội dung chạy được KHÔNG cần account Facebook.

Không có account ACTIVE → vẫn tải + reup, nhưng KHÔNG tạo Job; material về READY.
Có account ACTIVE facebook → đường cũ y nguyên: Job AWAITING_STYLE + material DRAFTED.

Chạy thẳng ``_process_viral_materials`` qua ``ViralService.process_material`` trên SQLite tạm,
mock yt-dlp (subprocess.run) và ReupProcessor để không cần mạng/ffmpeg.
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
from app.core.database.models import Account, Job, ViralMaterial
from app.features.viral_intake import processor
from app.features.viral_intake import reup_processor, reup_variants
from app.features.viral_intake.reup_processor import ReupResult
from app.features.viral_intake.service import ViralService


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'viral_ready.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    """yt-dlp + ReupProcessor giả: tạo file thật trên đĩa tạm, không mạng, không ffmpeg."""
    reup_dir = tmp_path / "reup"
    monkeypatch.setattr(config, "REUP_DIR", reup_dir)
    monkeypatch.setattr(processor, "_get_runtime_int", lambda db, key, fallback: fallback)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    monkeypatch.setattr(ViralService, "ensure_reup_thumbnail", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(reup_variants, "record_reup_variant", lambda **k: None)

    calls: dict[str, int] = {"preflight": 0, "download": 0, "reup": 0}

    def fake_run(cmd, *args, **kwargs):
        argv = [str(c) for c in cmd]
        if "--dump-single-json" in argv:
            calls["preflight"] += 1
            info = {"title": "demo", "view_count": 1234, "formats": [{"vcodec": "h264", "ext": "mp4"}]}
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(info), stderr="")
        calls["download"] += 1
        template = argv[argv.index("-o") + 1]
        out = template.replace("%(id)s", "src").replace("%(ext)s", "mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 2048)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(processor.subprocess, "run", fake_run)

    def fake_reup(input_path, platform="unknown", **kwargs):
        calls["reup"] += 1
        out = input_path.replace(".mp4", "_reup.mp4")
        with open(out, "wb") as fh:
            fh.write(b"\x01" * 4096)
        return ReupResult(success=True, output_path=out, metrics={"preset": kwargs.get("preset")})

    monkeypatch.setattr(reup_processor.ReupProcessor, "process", staticmethod(fake_reup))
    return calls


def _new_material(session_factory, url: str = "https://www.facebook.com/reel/1") -> int:
    with session_factory() as db:
        mat = ViralMaterial(platform="facebook", url=url, title="", views=0, status=ViralStatus.NEW)
        db.add(mat)
        db.commit()
        return mat.id


def test_ready_status_exists():
    assert ViralStatus.READY == "READY"
    assert ViralStatus.READY != ViralStatus.DRAFTED


def test_no_account_ends_in_ready_without_job(session_factory, fake_pipeline):
    mid = _new_material(session_factory)
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        assert "READY" in msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.READY
        assert mat.last_error is None
        assert mat.process_tries == 1
        assert db.query(Job).count() == 0
    # Tải + reup thật sự đã chạy (chứ không return sớm như trước ADR-018)
    assert fake_pipeline == {"preflight": 1, "download": 1, "reup": 1}
    assert ViralService.find_reup_path(mid, "facebook") is not None


def test_active_facebook_account_keeps_old_path_job_plus_drafted(session_factory, fake_pipeline, monkeypatch):
    from app.core.notifier.service import NotifierService

    monkeypatch.setattr(NotifierService, "notify_style_selection", staticmethod(lambda job: None))
    with session_factory() as db:
        db.add(Account(name="fb_acc", platform="facebook", is_active=True, login_status="ACTIVE"))
        db.commit()
    mid = _new_material(session_factory)
    with session_factory() as db:
        ok, msg = ViralService.process_material(db, mid)
        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.DRAFTED
        job = db.query(Job).filter(Job.viral_material_id == mid).one()
        assert job.status == JobStatus.AWAITING_STYLE
        assert job.platform == "facebook"
        assert job.media_path.endswith("_reup.mp4")
    assert fake_pipeline["reup"] == 1


def test_disabled_account_counts_as_no_account(session_factory, fake_pipeline):
    """Account bị vô hiệu (is_active=False) — đúng tình trạng thật 05/09 — không được tạo Job."""
    with session_factory() as db:
        db.add(Account(name="locked", platform="facebook", is_active=False, login_status="ACTIVE"))
        db.commit()
    mid = _new_material(session_factory)
    with session_factory() as db:
        ViralService.process_material(db, mid)
        assert db.get(ViralMaterial, mid).status == ViralStatus.READY
        assert db.query(Job).count() == 0


def test_check_processable_rejects_ready(session_factory):
    with session_factory() as db:
        mat = ViralMaterial(platform="facebook", url="https://www.facebook.com/reel/9", title="", views=0, status=ViralStatus.READY)
        db.add(mat)
        db.commit()
        reason = ViralService.check_processable(db, mat.id)
        assert reason is not None
        assert "READY" in reason and "Tải file" in reason


def test_process_new_batch_does_not_pick_ready(session_factory, monkeypatch):
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    with session_factory() as db:
        db.add(ViralMaterial(platform="facebook", url="https://www.facebook.com/reel/8", title="", views=0, status=ViralStatus.READY))
        db.commit()
        ok, fail, msg = ViralService.process_new_batch(db, limit=3)
        assert (ok, fail) == (0, 0)
        assert "Không còn video mới" in msg


def test_pipeline_banner_counts_ready(session_factory):
    with session_factory() as db:
        db.add(ViralMaterial(platform="facebook", url="https://www.facebook.com/reel/7", title="", views=0, status=ViralStatus.READY))
        db.commit()
        banner = ViralService.pipeline_banner(db)
        assert banner["ready_count"] == 1
        assert banner["status_counts"]["READY"] == 1
