"""
POST done → auto COMMENT job + queue claim. sqlite :memory: only.

Run from repo root:
  PYTHONPATH=. venv/bin/python -m unittest checks.unittest_jobs_comment_flow -v
"""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Account, Job, now_ts
from app.services.job import JobService
from app.services.queue import QueueService


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestPostDoneCommentFlow(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "db"):
            self.db.close()

    def test_mark_done_creates_comment_job_when_text_and_url(self):
        self.db = _make_session()
        acc = Account(
            name="flow_test_acc",
            platform="facebook",
            profile_path="/tmp/fake_profile_flow",
            is_active=True,
            login_status="ACTIVE",
            cooldown_seconds=0,
        )
        self.db.add(acc)
        self.db.flush()
        post = Job(
            account_id=acc.id,
            platform="facebook",
            job_type="POST",
            media_path="/tmp/x.mp4",
            caption="cap",
            schedule_ts=now_ts(),
            status="RUNNING",
            auto_comment_text="Cảm ơn bạn đã xem [LINK]",
        )
        self.db.add(post)
        self.db.commit()

        url = "https://www.facebook.com/reel/999888777666"
        JobService.mark_done(self.db, post, post_url=url)
        self.db.refresh(post)

        self.assertEqual(post.status, "DONE")
        self.assertEqual(post.post_url, url)
        kids = (
            self.db.query(Job)
            .filter(Job.parent_job_id == post.id, Job.job_type == "COMMENT")
            .all()
        )
        self.assertEqual(len(kids), 1)
        cj = kids[0]
        self.assertEqual(cj.auto_comment_text, post.auto_comment_text)
        self.assertEqual(cj.post_url, url)
        self.assertEqual(cj.status, "PENDING")
        self.assertIsNotNone(cj.scheduled_at)
        self.assertGreater(cj.scheduled_at, now_ts() - 400)
        self.assertGreater(now_ts() + 400, cj.scheduled_at)

    def test_mark_done_no_comment_without_auto_comment_text(self):
        self.db = _make_session()
        acc = Account(
            name="flow_test_acc2",
            platform="facebook",
            profile_path="/tmp/fake_profile_flow2",
            is_active=True,
            login_status="ACTIVE",
            cooldown_seconds=0,
        )
        self.db.add(acc)
        self.db.flush()
        post = Job(
            account_id=acc.id,
            platform="facebook",
            job_type="POST",
            media_path="/tmp/y.mp4",
            caption="cap",
            schedule_ts=now_ts(),
            status="RUNNING",
            auto_comment_text=None,
        )
        self.db.add(post)
        self.db.commit()

        JobService.mark_done(
            self.db, post, post_url="https://www.facebook.com/reel/111"
        )
        kids = (
            self.db.query(Job)
            .filter(Job.parent_job_id == post.id, Job.job_type == "COMMENT")
            .all()
        )
        self.assertEqual(len(kids), 0)

    def test_queue_claims_comment_after_scheduled_at(self):
        self.db = _make_session()
        acc = Account(
            name="flow_test_acc3",
            platform="facebook",
            profile_path="/tmp/fake_profile_flow3",
            is_active=True,
            login_status="ACTIVE",
            cooldown_seconds=0,
            last_post_ts=None,
        )
        self.db.add(acc)
        self.db.flush()
        post = Job(
            account_id=acc.id,
            platform="facebook",
            job_type="POST",
            media_path="/tmp/z.mp4",
            caption="cap",
            schedule_ts=now_ts(),
            status="RUNNING",
            auto_comment_text="test",
        )
        self.db.add(post)
        self.db.commit()
        JobService.mark_done(
            self.db, post, post_url="https://www.facebook.com/reel/222"
        )
        cj = (
            self.db.query(Job)
            .filter(Job.parent_job_id == post.id, Job.job_type == "COMMENT")
            .one()
        )
        past = now_ts() - 60
        cj.scheduled_at = past
        cj.schedule_ts = past
        self.db.commit()

        claimed = QueueService.claim_next_job(self.db)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, cj.id)
        self.assertEqual(claimed.status, "RUNNING")


if __name__ == "__main__":
    unittest.main()
