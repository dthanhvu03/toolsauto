"""PLAN-041: cross-account media publish guard."""
from __future__ import annotations

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
from app.core.database.models.jobs import Job
from app.core.database.models.viral import ViralMaterial
from app.core.media.content_hash import (
    assert_media_not_blocked,
    sha256_file,
)


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "plan041.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _account(db, name: str, platform: str = "facebook") -> Account:
    acc = Account(
        name=name,
        platform=platform,
        is_active=True,
        login_status="ACTIVE",
        profile_path=f"/tmp/{name}",
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def test_sha256_file_stable(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake-video-bytes-001")
    assert sha256_file(path) == sha256_file(path)
    assert sha256_file(path) != sha256_file(tmp_path / "missing.mp4")


def test_same_hash_blocked_across_accounts_same_platform(session_factory, tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"shared-bytes")
    digest = sha256_file(media)
    db = session_factory()
    a1 = _account(db, "acc1")
    a2 = _account(db, "acc2")
    db.add(
        Job(
            platform="facebook",
            account_id=a1.id,
            media_path=str(media),
            caption="one",
            status=JobStatus.DONE,
            schedule_ts=1,
            content_hash=digest,
        )
    )
    db.commit()
    with pytest.raises(ValueError, match="Cross-account guard"):
        assert_media_not_blocked(db, platform="facebook", content_hash=digest)
    # Different platform allowed
    assert_media_not_blocked(db, platform="threads", content_hash=digest)
    db.close()


def test_failed_job_does_not_block(session_factory, tmp_path):
    media = tmp_path / "b.mp4"
    media.write_bytes(b"retry-bytes")
    digest = sha256_file(media)
    db = session_factory()
    a1 = _account(db, "acc_fail")
    db.add(
        Job(
            platform="facebook",
            account_id=a1.id,
            media_path=str(media),
            caption="fail",
            status=JobStatus.FAILED,
            schedule_ts=1,
            content_hash=digest,
        )
    )
    db.commit()
    assert_media_not_blocked(db, platform="facebook", content_hash=digest)
    db.close()


def test_manual_high_priority_blocked_by_existing_hash(session_factory, tmp_path, monkeypatch):
    from app.core.queue.job import JobService

    media = tmp_path / "manual.mp4"
    media.write_bytes(b"manual-shared")
    digest = sha256_file(media)
    db = session_factory()
    a1 = _account(db, "m1")
    a2 = _account(db, "m2")
    db.add(
        Job(
            platform="facebook",
            account_id=a1.id,
            media_path=str(media),
            caption="first",
            status=JobStatus.DONE,
            schedule_ts=1,
            content_hash=digest,
        )
    )
    db.commit()

    def _noop_log(*_a, **_k):
        return None

    monkeypatch.setattr(JobService, "_log_event", staticmethod(_noop_log))
    with pytest.raises(ValueError, match="Cross-account guard"):
        JobService.create_high_priority_manual_job(
            db, a2.id, "https://facebook.com/page", "second", str(media)
        )
    db.close()


def test_viral_material_blocks_second_job(session_factory, tmp_path):
    db = session_factory()
    a1 = _account(db, "viral_acc")
    mat = ViralMaterial(platform="facebook", url="https://example.com/r/1", status="DRAFTED")
    db.add(mat)
    db.commit()
    db.refresh(mat)
    media = tmp_path / "v.mp4"
    media.write_bytes(b"viral-bytes")
    db.add(
        Job(
            platform="facebook",
            account_id=a1.id,
            media_path=str(media),
            caption="viral",
            status=JobStatus.AWAITING_STYLE,
            schedule_ts=1,
            viral_material_id=mat.id,
            content_hash=sha256_file(media),
        )
    )
    db.commit()
    with pytest.raises(ValueError, match="viral_material_id"):
        assert_media_not_blocked(db, platform="facebook", viral_material_id=mat.id)
    db.close()
