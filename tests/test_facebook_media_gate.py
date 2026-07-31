"""
Facebook video-only media gate: validation stays an operator error, never an
account failure, and a rejected upload never leaves a file behind.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import JobStatus
from app.core.database.models.accounts import Account
from app.core.database.models.jobs import Job, JobEvent
from app.core.database.models.viral import ViralMaterial
from app.core.queue.job import JobService


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    JobEvent.__table__.create(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _account(db, name="acc1", platform="facebook"):
    acc = Account(
        name=name,
        platform=platform,
        is_active=True,
        login_status="ACTIVE",
        profile_path=f"/tmp/{name}",
        consecutive_fatal_failures=0,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


class _Upload:
    """Minimal stand-in for Starlette's UploadFile."""

    def __init__(self, filename: str, data: bytes = b"x" * 16):
        self.filename = filename
        self.file = __import__("io").BytesIO(data)


# ── extension policy ──────────────────────────────────────────────────────────


def test_video_extensions_are_a_subset_of_valid_extensions():
    """An error message must never advertise a format create_job rejects."""
    assert set(JobService.VIDEO_EXTENSIONS) <= set(JobService.VALID_EXTENSIONS)
    assert set(JobService.FACEBOOK_POST_VIDEO_EXTENSIONS) <= set(JobService.VALID_EXTENSIONS)


def test_avi_is_consistently_rejected():
    """.avi is not in VALID_EXTENSIONS, so it must not be offered as accepted."""
    assert ".avi" not in JobService.VALID_EXTENSIONS
    assert ".avi" not in JobService.FACEBOOK_POST_VIDEO_EXTENSIONS
    with pytest.raises(ValueError) as err:
        JobService.assert_facebook_post_media("facebook", "clip.avi")
    message = str(err.value)
    # The message may quote the rejected extension, but must not advertise it
    # as accepted alongside the supported ones.
    assert "/.avi" not in message
    assert JobService._fmt_extensions(JobService.VIDEO_EXTENSIONS) in message


def test_image_rejected_for_facebook_post():
    with pytest.raises(ValueError, match="chỉ nhận video"):
        JobService.assert_facebook_post_media("facebook", "photo.png")


def test_video_accepted_and_other_platforms_untouched():
    JobService.assert_facebook_post_media("facebook", "clip.mp4")
    JobService.assert_facebook_post_media("threads", "photo.png")
    JobService.assert_facebook_post_media("facebook", "photo.png", job_type="COMMENT")


def test_missing_media_only_rejected_when_required():
    JobService.assert_facebook_post_media("facebook", None)
    with pytest.raises(ValueError, match="Thiếu media"):
        JobService.assert_facebook_post_media("facebook", None, require_media=True)


# ── circuit breaker ───────────────────────────────────────────────────────────


def _failing_job(db, account):
    job = Job(
        platform="facebook",
        account_id=account.id,
        media_path="photo.png",
        caption="hi",
        schedule_ts=0,
        status=JobStatus.RUNNING,
        tries=0,
        max_tries=3,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_media_validation_failure_does_not_trip_circuit_breaker(db):
    account = _account(db)
    for _ in range(3):
        job = _failing_job(db, account)
        JobService.mark_failed_or_retry(
            db, job, "ảnh không hợp lệ", is_fatal=True,
            error_type=JobService.ERROR_TYPE_VALIDATION,
        )
    db.refresh(account)
    assert account.consecutive_fatal_failures == 0
    assert account.is_active is True


def test_real_fatal_failures_still_trip_circuit_breaker(db):
    account = _account(db)
    for _ in range(3):
        job = _failing_job(db, account)
        JobService.mark_failed_or_retry(db, job, "browser dead", is_fatal=True)
    db.refresh(account)
    assert account.consecutive_fatal_failures == 3
    assert account.is_active is False


def test_validation_failure_is_terminal_not_retried(db):
    account = _account(db)
    job = _failing_job(db, account)
    JobService.mark_failed_or_retry(
        db, job, "ảnh không hợp lệ", is_fatal=True,
        error_type=JobService.ERROR_TYPE_VALIDATION,
    )
    assert job.status == JobStatus.FAILED


# ── manual jobs: caption-only kept, no orphan uploads ─────────────────────────


def test_caption_only_manual_job_is_still_created(db):
    account = _account(db)
    job = JobService.create_high_priority_manual_job(
        db, account.id, "https://fb.com/page", caption="chỉ caption", media_path=None
    )
    assert job.id is not None
    assert job.media_path is None


def test_manual_job_with_video_is_created(db, tmp_path, monkeypatch):
    account = _account(db)
    monkeypatch.setattr("app.config.CONTENT_DIR", tmp_path)
    job = JobService.create_manual_job_with_file(
        db, account.id, "https://fb.com/page", "caption", _Upload("clip.mp4")
    )
    assert job.media_path and os.path.exists(job.media_path)


def test_rejected_manual_upload_leaves_no_orphan_file(db, tmp_path, monkeypatch):
    account = _account(db)
    monkeypatch.setattr("app.config.CONTENT_DIR", tmp_path)
    manual_dir = tmp_path / "manual"

    with pytest.raises(ValueError, match="chỉ nhận video"):
        JobService.create_manual_job_with_file(
            db, account.id, "https://fb.com/page", "caption", _Upload("photo.png")
        )

    leftovers = list(manual_dir.glob("*")) if manual_dir.exists() else []
    assert leftovers == []


# ── bulk uploads: all-or-nothing ──────────────────────────────────────────────


def test_bulk_upload_with_one_image_leaves_no_orphan_files(db, tmp_path, monkeypatch):
    account = _account(db)
    media_dir = tmp_path / "media"
    monkeypatch.setattr("app.core.queue.job.CONTENT_MEDIA_DIR", media_dir)

    with pytest.raises(ValueError, match="chỉ nhận video"):
        JobService.bulk_create_jobs_from_uploads(
            db,
            account.id,
            [_Upload("a.mp4"), _Upload("b.png"), _Upload("c.mp4")],
            captions=["1", "2", "3"],
            schedule_times=["2030-01-01T10:00"] * 3,
            randomize_caption=False,
        )

    leftovers = list(media_dir.glob("*")) if media_dir.exists() else []
    assert leftovers == []
    assert db.query(Job).count() == 0


def test_bulk_upload_rejects_unsupported_extension_before_writing(db, tmp_path, monkeypatch):
    account = _account(db, platform="threads")
    media_dir = tmp_path / "media"
    monkeypatch.setattr("app.core.queue.job.CONTENT_MEDIA_DIR", media_dir)

    with pytest.raises(ValueError, match="không được hỗ trợ"):
        JobService.bulk_create_jobs_from_uploads(
            db,
            account.id,
            [_Upload("a.exe")],
            captions=["1"],
            schedule_times=["2030-01-01T10:00"],
            randomize_caption=False,
        )
    leftovers = list(media_dir.glob("*")) if media_dir.exists() else []
    assert leftovers == []


def test_failed_bulk_never_deletes_pre_existing_files(db, tmp_path, monkeypatch):
    """Rollback may only remove what this request wrote."""
    account = _account(db)
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True)
    survivor = media_dir / "someone_elses_upload.mp4"
    survivor.write_bytes(b"do-not-touch")
    monkeypatch.setattr("app.core.queue.job.CONTENT_MEDIA_DIR", media_dir)

    with pytest.raises(ValueError):
        JobService.bulk_create_jobs_from_uploads(
            db,
            account.id,
            [_Upload("a.mp4"), _Upload("b.png")],
            captions=["1", "2"],
            schedule_times=["2030-01-01T10:00"] * 2,
            randomize_caption=False,
        )

    assert survivor.exists()
    assert survivor.read_bytes() == b"do-not-touch"
    assert list(media_dir.glob("*")) == [survivor]


def test_discard_files_ignores_missing_and_none(tmp_path):
    real = tmp_path / "x.mp4"
    real.write_bytes(b"x")
    JobService._discard_files([None, str(tmp_path / "missing.mp4"), str(real)])
    assert not real.exists()


def test_bulk_upload_all_videos_succeeds(db, tmp_path, monkeypatch):
    account = _account(db)
    media_dir = tmp_path / "media"
    monkeypatch.setattr("app.core.queue.job.CONTENT_MEDIA_DIR", media_dir)

    batch_id = JobService.bulk_create_jobs_from_uploads(
        db,
        account.id,
        [_Upload("a.mp4", b"aaa"), _Upload("b.mov", b"bbb")],
        captions=["1", "2"],
        schedule_times=["2030-01-01T10:00", "2030-01-01T11:00"],
        randomize_caption=False,
    )
    assert batch_id
    assert db.query(Job).count() == 2
    assert len(list(media_dir.glob("*"))) == 2
