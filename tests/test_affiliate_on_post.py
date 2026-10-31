"""Cash register: affiliate comment after Reel post — sqlite memory, no live Facebook."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants import JobStatus, JobType
from app.core.database.core import get_db
from app.core.database.models import Account, Base, Job
from app.core.notifier.formatting import job_done_message, job_failed_message
from app.core.queue.job import JobService
from app.platform.admin_api.router import router


def _memory_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return engine, factory


def _client(factory):
    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


class _FakeAccount:
    name = "Page A"


class _FakeJob:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.platform = "facebook"
        self.caption = kw.get("caption", "")
        self.account = _FakeAccount()
        self.tries = kw.get("tries", 1)
        self.max_tries = kw.get("max_tries", 1)
        self.job_type = kw.get("job_type", JobType.POST)
        self.affiliate_url = kw.get("affiliate_url")
        self.parent_job_id = kw.get("parent_job_id")
        self.last_error = kw.get("last_error")


def test_mark_done_comment_job_max_tries_one_no_retry_spam():
    engine, factory = _memory_session()
    try:
        with factory() as db:
            acc = Account(name="Acc", platform="facebook")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            job = Job(
                account_id=acc.id,
                platform="facebook",
                job_type=JobType.POST,
                status=JobStatus.RUNNING,
                caption="reel",
                auto_comment_text="Mua ngay https://shp.ee/x",
                affiliate_url="https://shp.ee/x",
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            JobService.mark_done(db, job, post_url="https://www.facebook.com/reel/1")
            child = (
                db.query(Job)
                .filter(Job.parent_job_id == job.id, Job.job_type == JobType.COMMENT)
                .one()
            )
            assert child.max_tries == 1
            assert child.affiliate_url == "https://shp.ee/x"
            assert child.auto_comment_text.startswith("Mua ngay")
            assert job.status == JobStatus.DONE
    finally:
        engine.dispose()


def test_comment_fail_marks_failed_not_pending():
    engine, factory = _memory_session()
    try:
        with factory() as db:
            acc = Account(name="Acc", platform="facebook")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            cmt = Job(
                account_id=acc.id,
                platform="facebook",
                job_type=JobType.COMMENT,
                status=JobStatus.RUNNING,
                auto_comment_text="link",
                affiliate_url="https://shp.ee/x",
                max_tries=1,
                tries=0,
                parent_job_id=9,
            )
            db.add(cmt)
            db.commit()
            db.refresh(cmt)
            JobService.mark_failed_or_retry(
                db, cmt, "comment box not found", is_fatal=False, error_type="RETRYABLE"
            )
            db.refresh(cmt)
            assert cmt.status == JobStatus.FAILED
            assert cmt.tries == 1
    finally:
        engine.dispose()


def test_jobs_api_shows_posted_comment_ok_affiliate():
    engine, factory = _memory_session()
    try:
        with factory() as db:
            acc = Account(name="Acc", platform="facebook")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            parent = Job(
                account_id=acc.id,
                platform="facebook",
                job_type=JobType.POST,
                status=JobStatus.DONE,
                caption="reel kem",
                post_url="https://www.facebook.com/reel/99",
                affiliate_url="https://shp.ee/kem",
                auto_comment_text="Mua kem https://shp.ee/kem",
                schedule_ts=1,
            )
            db.add(parent)
            db.commit()
            db.refresh(parent)
            db.add(
                Job(
                    account_id=acc.id,
                    platform="facebook",
                    job_type=JobType.COMMENT,
                    status=JobStatus.DONE,
                    parent_job_id=parent.id,
                    post_url=parent.post_url,
                    affiliate_url=parent.affiliate_url,
                    auto_comment_text=parent.auto_comment_text,
                    schedule_ts=2,
                )
            )
            db.commit()
        c = _client(factory)
        r = c.get("/api/admin/jobs?status=DONE")
        assert r.status_code == 200, r.text
        posts = [j for j in r.json()["jobs"] if j["job_type"] == "POST"]
        assert len(posts) == 1
        row = posts[0]
        assert row["posted"] is True
        assert row["comment_ok"] == "ok"
        assert row["affiliate_url"] == "https://shp.ee/kem"
    finally:
        engine.dispose()


def test_telegram_comment_fail_says_video_still_up():
    msg = job_failed_message(
        _FakeJob(job_type=JobType.COMMENT, parent_job_id=12, affiliate_url="https://shp.ee/x"),
        "box missing",
    )
    assert "Comment affiliate lỗi" in msg
    assert "video vẫn đã lên" in msg
    assert "Không retry spam" in msg


def test_telegram_comment_ok_not_generic_publish():
    msg = job_done_message(
        _FakeJob(job_type=JobType.COMMENT, affiliate_url="https://shp.ee/x"),
        "https://www.facebook.com/reel/1",
    )
    assert "Comment affiliate OK" in msg
    assert "Đăng thành công" not in msg
