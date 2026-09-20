"""P0 checkpoint harden: detect + abort. Không hit Facebook thật."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import AccountStatus, JobStatus, JobType
from app.core.database.models import Account, Base, Job
from app.features.facebook.selectors import CHECKPOINT, looks_like_checkpoint


class _ZeroLocator:
    def count(self):
        return 0

    def is_visible(self):
        return False


class FakePage:
    def __init__(self, url: str, text: str = ""):
        self.url = url
        self._text = text
        self.goto_calls: list[str] = []
        self.screenshot_paths: list[str] = []

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)

    def inner_text(self, selector, timeout=None):
        return self._text

    def title(self):
        return ""

    def locator(self, selector):
        return _ZeroLocator()

    def screenshot(self, path=None, full_page=False):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
        self.screenshot_paths.append(str(p))

    def content(self):
        return f"<html><body>{self._text}</body></html>"


# ── markers ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url,text",
    [
        ("https://www.facebook.com/checkpoint/1501092823525282/", ""),
        ("https://www.facebook.com/login/?next=%2F", ""),
        ("https://www.facebook.com/login_attempt/?error=1", ""),
        ("https://www.facebook.com/?error=account_locked", ""),
        ("https://www.facebook.com/home.php", "unusual login"),
        ("https://www.facebook.com/", "Vui lòng xác nhận danh tính để tiếp tục"),
        ("https://www.facebook.com/checkpoint/?next=unusual_login", ""),
    ],
)
def test_looks_like_checkpoint_positive(url, text):
    assert looks_like_checkpoint(url, text) is True


def test_looks_like_checkpoint_negative_reel():
    assert looks_like_checkpoint("https://www.facebook.com/reel/1234567890", "Watch") is False


def test_checkpoint_dict_covers_required_markers():
    blob = " ".join(CHECKPOINT["url_markers"] + CHECKPOINT["text_markers"]).lower()
    for needle in (
        "checkpoint",
        "unusual login",
        "xác nhận danh tính",
        "/login/",
        "/checkpoint/",
        "login_attempt",
        "account_locked",
    ):
        assert needle in blob


def test_adapter_source_does_not_goto_home_on_checkpoint_url():
    src = (ROOT / "app" / "features" / "facebook" / "adapter.py").read_text(encoding="utf-8")
    assert 'if "login" in self.page.url or "checkpoint" in self.page.url' not in src
    assert "CHECKPOINT detected — aborting immediately" in src


# ── adapter abort, no navigation ──────────────────────────────────────────────


def test_adapter_aborts_checkpoint_without_goto_home(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.LOGS_DIR", tmp_path)
    monkeypatch.setattr("app.features.facebook.adapter.LOGS_DIR", tmp_path)

    from app.features.facebook.adapter import FacebookAdapter

    adapter = FacebookAdapter()
    page = FakePage("https://www.facebook.com/checkpoint/1501092823525282/")
    adapter.page = page
    job = SimpleNamespace(id=99, account=SimpleNamespace(id=3, name="acc-cp"))

    result = adapter._maybe_checkpoint_result(job, "personal", None)

    assert result is not None
    assert result.ok is False
    assert result.error_code == "CHECKPOINT"
    assert result.is_fatal is True
    assert result.details["checkpoint"] is True
    assert result.details["invalidate_account"] is True
    assert page.goto_calls == []
    assert any("checkpoint" in p and p.endswith(".png") for p in page.screenshot_paths)


@pytest.mark.parametrize(
    "url,text",
    [
        ("https://facebook.com/login/?next=/", ""),
        ("https://www.facebook.com/", "unusual login required"),
        ("https://www.facebook.com/home.php", "xác nhận danh tính"),
    ],
)
def test_adapter_aborts_text_and_login_markers(url, text, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.LOGS_DIR", tmp_path)
    monkeypatch.setattr("app.features.facebook.adapter.LOGS_DIR", tmp_path)

    from app.features.facebook.adapter import FacebookAdapter

    adapter = FacebookAdapter()
    adapter.page = FakePage(url, text)
    job = SimpleNamespace(id=7, account=SimpleNamespace(id=1, name="a"))
    result = adapter._maybe_checkpoint_result(job, "personal", None)
    assert result is not None
    assert result.error_code == "CHECKPOINT"
    assert adapter.page.goto_calls == []


def test_adapter_clean_feed_is_not_checkpoint():
    from app.features.facebook.adapter import FacebookAdapter

    adapter = FacebookAdapter()
    adapter.page = FakePage("https://www.facebook.com/", "News Feed")
    job = SimpleNamespace(id=1, account=SimpleNamespace(id=1, name="a"))
    assert adapter._maybe_checkpoint_result(job, "personal", None) is None
    assert adapter.page.goto_calls == []


def test_engagement_detects_expanded_markers():
    from app.features.facebook.engagement import _is_checkpointed

    assert _is_checkpointed(FakePage("https://www.facebook.com/checkpoint/1")) is True
    assert _is_checkpointed(FakePage("https://www.facebook.com/", "unusual login")) is True
    assert _is_checkpointed(FakePage("https://www.facebook.com/", "xác nhận danh tính")) is True
    assert _is_checkpointed(FakePage("https://www.facebook.com/reel/1", "ok")) is False


# ── publisher fail path ───────────────────────────────────────────────────────


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_publisher_sets_job_status_checkpoint(db, monkeypatch, tmp_path):
    from app.adapters.contracts import PublishResult
    from app.features.facebook.workers import publisher

    acc = Account(
        name="fb-cp",
        platform="facebook",
        is_active=True,
        login_status=AccountStatus.ACTIVE,
        profile_path=str(tmp_path / "prof"),
        consecutive_fatal_failures=0,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    job = Job(
        platform="facebook",
        account_id=acc.id,
        media_path="clip.mp4",
        caption="ok caption",
        status=JobStatus.RUNNING,
        tries=0,
        max_tries=3,
        job_type=JobType.POST,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job.account = acc

    broadcasts: list[str] = []
    monkeypatch.setattr(publisher, "claim_precheck", lambda *a, **k: True)
    monkeypatch.setattr(
        publisher, "claim_next_job_respecting_daily", lambda *a, **k: (job, None)
    )
    monkeypatch.setattr(publisher, "postpone_if_sleeping", lambda *a, **k: False)
    monkeypatch.setattr(
        publisher,
        "start_heartbeat_thread",
        lambda *a, **k: MagicMock(join=lambda timeout=None: None),
    )
    monkeypatch.setattr(publisher, "kill_if_stuck", lambda *a, **k: MagicMock(cancel=lambda: None))
    monkeypatch.setattr(
        publisher.Dispatcher,
        "dispatch",
        staticmethod(
            lambda job, db=None: PublishResult(
                ok=False,
                is_fatal=True,
                error_code="CHECKPOINT",
                error="CHECKPOINT detected. Aborted. url=https://www.facebook.com/checkpoint/1",
                details={"checkpoint": True, "invalidate_account": True},
            )
        ),
    )
    monkeypatch.setattr(
        publisher.NotifierService,
        "_broadcast",
        classmethod(lambda cls, msg: broadcasts.append(msg)),
    )
    monkeypatch.setattr(
        publisher.NotifierService,
        "notify_account_invalid",
        classmethod(lambda cls, *a, **k: None),
    )
    monkeypatch.setattr(
        "app.core.compliance.facebook_compliance.check_before_publish",
        lambda *a, **k: None,
    )

    assert publisher.process_single_job(db) is True
    db.refresh(job)
    db.refresh(acc)
    assert job.status == JobStatus.CHECKPOINT
    assert job.error_type == "CHECKPOINT"
    assert acc.login_status == AccountStatus.INVALID
    assert acc.is_active is False
    assert any("CHECKPOINT" in m for m in broadcasts)
    assert job.status != JobStatus.PENDING
    assert job.status != JobStatus.FAILED


def test_jobstatus_checkpoint_exists():
    assert JobStatus.CHECKPOINT == "CHECKPOINT"
    assert JobStatus.CHECKPOINT in JobStatus


def test_force_run_blocked_for_invalid_account(db, tmp_path):
    from app.core.queue.job import JobService

    acc = Account(
        name="fb-inv",
        platform="facebook",
        is_active=False,
        login_status=AccountStatus.INVALID,
        profile_path=str(tmp_path / "p2"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    job = Job(
        platform="facebook",
        account_id=acc.id,
        media_path="clip.mp4",
        caption="x",
        status=JobStatus.PENDING,
        job_type=JobType.POST,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    with pytest.raises(ValueError, match="INVALID/CHECKPOINT"):
        JobService.force_run_job(db, job.id)
