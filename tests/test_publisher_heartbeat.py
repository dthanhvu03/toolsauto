"""
Every exit path of process_single_job that starts a heartbeat must stop it —
including the early returns (AI marker, media gate, compliance block).
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.constants import JobStatus, JobType
from app.core.queue.job import JobService
from app.features.facebook.workers import publisher


class _FakeAccount:
    id = 1
    name = "acc1"


class _FakeJob:
    def __init__(self, media_path="photo.png", caption="hello"):
        # Deliberately not a plausible production id.
        self.id = 999_000_006
        self.platform = "facebook"
        self.media_path = media_path
        self.resolved_media_path = media_path
        self.resolved_processed_media_path = None
        self.caption = caption
        self.job_type = JobType.POST
        self.status = JobStatus.RUNNING
        self.tries = 0
        self.max_tries = 3
        self.error_type = ""
        self.account = _FakeAccount()


class _FakeDB:
    def commit(self):
        pass

    def rollback(self):
        pass

    def refresh(self, _obj):
        pass


@pytest.fixture
def wired(monkeypatch):
    """Drive process_single_job with a claimed job and a real heartbeat thread."""
    # The worker module logs to the shared logs/app.log on import. Without this,
    # the test's fake "Job-6" writes ERROR lines an operator would read as a real
    # production failure.
    monkeypatch.setattr(publisher, "logger", logging.getLogger("tests.publisher_probe"))
    logging.getLogger("tests.publisher_probe").addHandler(logging.NullHandler())
    logging.getLogger("tests.publisher_probe").propagate = False

    state = {"job": _FakeJob(), "stopped": None, "thread": None, "marked": []}

    def fake_start_heartbeat(job_id, stop_event, interval=60, logger=None):
        state["stopped"] = stop_event
        thread = threading.Thread(target=stop_event.wait, daemon=True)
        thread.start()
        state["thread"] = thread
        return thread

    monkeypatch.setattr(publisher, "claim_precheck", lambda *a, **k: True)
    monkeypatch.setattr(
        publisher, "claim_next_job_respecting_daily", lambda *a, **k: (state["job"], None)
    )
    monkeypatch.setattr(publisher, "postpone_if_sleeping", lambda *a, **k: False)
    monkeypatch.setattr(publisher, "start_heartbeat_thread", fake_start_heartbeat)
    monkeypatch.setattr(
        publisher.JobService,
        "mark_failed_or_retry",
        staticmethod(
            lambda db, job, error_msg, is_fatal, error_type=None: state["marked"].append(
                {"msg": error_msg, "is_fatal": is_fatal, "error_type": error_type}
            )
        ),
    )
    return state


def test_media_gate_early_return_stops_heartbeat(wired):
    assert publisher.process_single_job(_FakeDB()) is True

    assert wired["stopped"] is not None, "heartbeat was never started"
    assert wired["stopped"].is_set(), "heartbeat thread left running after early return"
    wired["thread"].join(timeout=2)
    assert not wired["thread"].is_alive()


def test_media_gate_failure_is_validation_not_account_fatal(wired):
    publisher.process_single_job(_FakeDB())

    assert len(wired["marked"]) == 1
    marked = wired["marked"][0]
    assert marked["error_type"] == JobService.ERROR_TYPE_VALIDATION
    assert "chỉ nhận video" in marked["msg"]


def test_ai_marker_early_return_stops_heartbeat(wired):
    from app.constants import AI_GENERATE_MARKER

    wired["job"] = _FakeJob(media_path="clip.mp4", caption=f"{AI_GENERATE_MARKER} viết hộ")

    assert publisher.process_single_job(_FakeDB()) is True
    assert wired["stopped"].is_set()
    assert wired["job"].status == JobStatus.DRAFT
    assert wired["marked"] == []
