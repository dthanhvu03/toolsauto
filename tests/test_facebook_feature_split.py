import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import JobStatus, JobType
from app.features.facebook.commenting.service import FacebookCommentingService
from app.features.facebook.engagement.service import FacebookEngagementService
from app.features.facebook.posting.service import FacebookPostingService
from app.schemas.facebook import (
    FBCommentCreate,
    FBEngageCreate,
    FBPostCreate,
    FacebookJobType,
)


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _DB:
    """Test double for SQLAlchemy Session.

    `query(model)` returns the same canned account/job. To support the cooldown query
    (which queries Job, not Account), pass `recent_job=` to simulate a recent COMMENT
    job for the same account. Default `recent_job=None` = no cooldown.
    """
    def __init__(self, account=None, recent_job=None):
        self.account = account
        self.recent_job = recent_job
        self.added = None
        self.commits = 0

    def query(self, model):
        # Account query → return account; Job query → return recent_job (None = no cooldown)
        from app.core.database.models import Account
        if model is Account:
            return _Query(self.account)
        return _Query(self.recent_job)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        obj.id = 123


def test_facebook_job_type_values_are_feature_specific():
    assert FacebookJobType.POST.value == "fb_post"
    assert FacebookJobType.COMMENT.value == "fb_comment"
    assert FacebookJobType.ENGAGE.value == "fb_engage"


def test_posting_service_creates_facebook_post_job(monkeypatch):
    monkeypatch.setattr("app.features.facebook.posting.service.JobService._log_event", lambda *a, **k: None)
    db = _DB(account=SimpleNamespace(id=7, name="test", is_active=True, platform="facebook"))

    job = FacebookPostingService.create_post_job(
        db,
        FBPostCreate(
            account_id=7,
            caption="hello",
            target_page="https://facebook.com/page",
            priority=True,
        ),
    )

    assert job.id == 123
    assert job.platform == "facebook"
    assert job.job_type == JobType.POST
    assert job.status == JobStatus.PENDING
    assert job.caption == "hello"
    assert db.added is job
    assert db.commits == 1


def test_commenting_service_creates_comment_job(monkeypatch):
    monkeypatch.setattr("app.features.facebook.commenting.service.JobService._log_event", lambda *a, **k: None)
    db = _DB(account=SimpleNamespace(id=8, name="test", is_active=True, platform="facebook"))

    job = FacebookCommentingService.create_comment_job(
        db,
        FBCommentCreate(
            account_id=8,
            post_url="https://facebook.com/reel/1",
            comment_text="comment",
            target_page="My Page",
            scheduled_at=1000,
            parent_job_id=42,
        ),
    )

    assert job.id == 123
    assert job.platform == "facebook"
    assert job.job_type == JobType.COMMENT
    assert job.post_url == "https://facebook.com/reel/1"
    assert job.auto_comment_text == "comment"
    assert job.target_page == "My Page"
    assert job.scheduled_at == 1000
    assert job.parent_job_id == 42


def test_commenting_service_requires_comment_text():
    db = _DB(account=SimpleNamespace(id=8, name="test", is_active=True, platform="facebook"))

    with pytest.raises(ValueError, match="comment_text"):
        FacebookCommentingService.create_comment_job(
            db,
            FBCommentCreate(
                account_id=8,
                post_url="https://facebook.com/reel/1",
                comment_text=" ",
            ),
        )


def test_commenting_service_rejects_within_cooldown(monkeypatch):
    """G4: refuse new COMMENT job if same account submitted one within cooldown window."""
    import time
    from app.features.facebook.commenting.service import COMMENT_COOLDOWN_SECONDS

    monkeypatch.setattr("app.features.facebook.commenting.service.JobService._log_event", lambda *a, **k: None)
    recent = SimpleNamespace(id=999, created_at=int(time.time()) - 5)  # 5s ago, within cooldown
    db = _DB(
        account=SimpleNamespace(id=8, name="test", is_active=True, platform="facebook"),
        recent_job=recent,
    )

    with pytest.raises(ValueError, match="cooldown"):
        FacebookCommentingService.create_comment_job(
            db,
            FBCommentCreate(account_id=8, post_url="https://facebook.com/reel/1", comment_text="hi"),
        )

    # Sanity: the constant is non-trivial (avoids regression where cooldown collapses to 0)
    assert COMMENT_COOLDOWN_SECONDS >= 5


def test_commenting_service_allows_after_cooldown(monkeypatch):
    """G4: allow new COMMENT job when no recent job exists."""
    monkeypatch.setattr("app.features.facebook.commenting.service.JobService._log_event", lambda *a, **k: None)
    db = _DB(
        account=SimpleNamespace(id=8, name="test", is_active=True, platform="facebook"),
        recent_job=None,  # no recent job
    )

    job = FacebookCommentingService.create_comment_job(
        db,
        FBCommentCreate(account_id=8, post_url="https://facebook.com/reel/1", comment_text="ok"),
    )
    assert job.job_type == JobType.COMMENT
    assert job.auto_comment_text == "ok"


def test_engagement_service_returns_skeleton_plan():
    db = _DB(account=SimpleNamespace(id=9, name="test", is_active=True, platform="facebook"))

    plan = FacebookEngagementService.plan_action(
        db,
        FBEngageCreate(account_id=9, action="click_like", target_url="https://facebook.com/post/1"),
    )

    assert plan["account_id"] == 9
    assert plan["action"] == "click_like"
    assert plan["execution"] == "skeleton"
