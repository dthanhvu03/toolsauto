"""
Hàng đợi phải nhặt được mọi loại job, không chỉ POST/COMMENT (PLAN-052).

Bug gốc: `claim_next_job` liệt kê cứng hai job_type trong SQL nên job FEED nằm
PENDING vĩnh viễn. Test cũ chỉ soi chuỗi trong source nên không bắt được — nên
test này chạy thẳng câu SQL thật trên Postgres.

Cô lập: mỗi ca dùng một `platform` riêng (`__pytest_q_*`), và câu claim lọc theo
`j.platform = :platform`, nên không bao giờ chạm vào job production.
"""
from __future__ import annotations

import time
import uuid

import pytest

pytestmark = pytest.mark.integration

TAG_PREFIX = "__pytest_q_"


def _db_or_skip():
    try:
        from app.core.database.core import SessionLocal

        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return db
    except Exception as e:  # pragma: no cover - phụ thuộc môi trường
        pytest.skip(f"Không có Postgres để chạy test hàng đợi: {e}")


@pytest.fixture()
def db():
    session = _db_or_skip()
    created_account_ids: list[int] = []
    try:
        yield session, created_account_ids
    finally:
        from sqlalchemy import text

        session.rollback()
        if created_account_ids:
            session.execute(
                text("DELETE FROM job_events WHERE job_id IN (SELECT id FROM jobs WHERE account_id = ANY(:ids))"),
                {"ids": created_account_ids},
            )
            session.execute(
                text("DELETE FROM jobs WHERE account_id = ANY(:ids)"), {"ids": created_account_ids}
            )
            session.execute(
                text("DELETE FROM accounts WHERE id = ANY(:ids)"), {"ids": created_account_ids}
            )
            session.commit()
        session.close()


def _make_case(session, created_ids, *, job_type: str, schedule_ts=None, scheduled_at=None):
    """Tạo 1 account + 1 job PENDING trên một platform tag riêng. Trả về (tag, job_id)."""
    from app.core.database.models import Account, Job

    tag = f"{TAG_PREFIX}{uuid.uuid4().hex[:8]}"
    account = Account(
        name=f"{tag}_acc",
        platform="facebook",
        is_active=True,
        login_status="ACTIVE",
        cooldown_seconds=0,
    )
    session.add(account)
    session.flush()
    created_ids.append(account.id)

    job = Job(
        platform=tag,
        account_id=account.id,
        job_type=job_type,
        status="PENDING",
        caption="pytest queue guard",
        schedule_ts=schedule_ts,
        scheduled_at=scheduled_at,
    )
    session.add(job)
    session.commit()
    return tag, job.id


def _claim(session, tag):
    from app.core.queue.queue import QueueService

    return QueueService.claim_next_job(session, platform=tag)


@pytest.mark.parametrize("job_type", ["POST", "COMMENT", "FEED", "STORY"])
def test_due_job_of_any_type_is_claimed(db, job_type):
    session, created = db
    past = int(time.time()) - 60
    # COMMENT đặt cả hai mốc như mark_done đang làm; các loại khác chỉ có schedule_ts.
    scheduled_at = past if job_type == "COMMENT" else None
    tag, job_id = _make_case(
        session, created, job_type=job_type, schedule_ts=past, scheduled_at=scheduled_at
    )

    claimed = _claim(session, tag)

    assert claimed is not None, f"job {job_type} đến hạn nhưng không được claim"
    assert claimed.id == job_id
    assert claimed.status == "RUNNING"


@pytest.mark.parametrize("job_type", ["POST", "COMMENT", "FEED", "STORY"])
def test_future_job_is_not_claimed(db, job_type):
    session, created = db
    future = int(time.time()) + 3600
    scheduled_at = future if job_type == "COMMENT" else None
    tag, _ = _make_case(
        session, created, job_type=job_type, schedule_ts=future, scheduled_at=scheduled_at
    )

    assert _claim(session, tag) is None, f"job {job_type} chưa tới hạn mà vẫn bị claim"


def test_comment_delay_still_gates_even_when_schedule_ts_is_past(db):
    """
    mark_done đặt cả schedule_ts lẫn scheduled_at. Nếu chỉ xét schedule_ts thì
    COMMENT sẽ chạy sớm hơn delay đã hẹn — cổng phải xét mốc muộn hơn.
    """
    session, created = db
    now = int(time.time())
    tag, _ = _make_case(
        session, created, job_type="COMMENT", schedule_ts=now - 600, scheduled_at=now + 1800
    )

    assert _claim(session, tag) is None, "COMMENT bị claim trước hạn scheduled_at"
