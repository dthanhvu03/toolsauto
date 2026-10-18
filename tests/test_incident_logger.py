import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database.core import SessionLocal
from app.core.database.models import IncidentGroup, IncidentLog
from app.core.observability.incident_logger import (
    IncidentLogger,
    build_error_signature,
    normalize_message,
    redact_context,
)


def test_redact_context_removes_sensitive_keys_and_masks_token_values():
    context = {
        "url": "https://example.test/post",
        "cookie": "c_user=secret",
        "nested": {
            "token": "secret-token",
            "headers": "Authorization: Bearer abc.def-ghi",
            "safe": "kept",
        },
        "items": [{"password": "secret"}, {"note": "Bearer xyz.abc"}],
        "proxy_auth": "user:pass",
    }

    redacted = redact_context(context)

    assert redacted["url"] == "https://example.test/post"
    assert "cookie" not in redacted
    assert "token" not in redacted["nested"]
    assert "proxy_auth" not in redacted
    assert redacted["nested"]["safe"] == "kept"
    assert "secret" not in str(redacted).lower()
    assert "[REDACTED]" in redacted["nested"]["headers"]
    assert redacted["items"][1]["note"] == "[REDACTED]"


def test_build_error_signature_uses_error_type_and_normalized_message():
    message = "Timeout selector .btn-123 for job 456 at 2026-04-26 12:34:56"
    expected = hashlib.sha1(
        f"TimeoutError:{normalize_message(message)}".encode("utf-8")
    ).hexdigest()[:16]

    assert build_error_signature("TimeoutError", message) == expected
    assert build_error_signature("TimeoutError", message) == build_error_signature(
        "TimeoutError",
        "Timeout selector .btn-999 for job 111 at 2026-04-26 12:34:56",
    )


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _delete_signature(db, signature: str) -> None:
    db.query(IncidentLog).filter(IncidentLog.error_signature == signature).delete(
        synchronize_session=False
    )
    db.query(IncidentGroup).filter(IncidentGroup.error_signature == signature).delete(
        synchronize_session=False
    )
    db.commit()


def test_log_incident_upserts_group_count(db_session):
    message = "TASK-021 synthetic timeout selector .codex-test-123"
    signature = build_error_signature("RuntimeError", message)
    _delete_signature(db_session, signature)

    try:
        first = IncidentLogger.log_incident(
            exception=RuntimeError(message),
            platform="pytest",
            feature="service-test-baseline",
            worker_name="pytest-worker",
            job_id="task-021-1",
            account_id="account-1",
            severity="warning",
            context={"token": "secret-token", "safe": "visible"},
            db=db_session,
        )
        second = IncidentLogger.log_incident(
            exception=RuntimeError(message),
            platform="pytest",
            feature="service-test-baseline",
            worker_name="pytest-worker",
            job_id="task-021-2",
            account_id="account-1",
            severity="error",
            context={"cookie": "secret-cookie", "safe": "visible"},
            db=db_session,
        )

        group = db_session.get(IncidentGroup, signature)
        logs = (
            db_session.query(IncidentLog)
            .filter(IncidentLog.error_signature == signature)
            .order_by(IncidentLog.id)
            .all()
        )

        assert first == signature
        assert second == signature
        assert group is not None
        assert group.occurrence_count == 2
        assert group.last_job_id == "task-021-2"
        assert group.severity_max == "error"
        assert len(logs) == 2
        assert logs[0].context_json == {"safe": "visible"}
        assert logs[1].context_json == {"safe": "visible"}
    finally:
        _delete_signature(db_session, signature)
