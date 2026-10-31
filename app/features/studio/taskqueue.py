"""
ADR-061 — hàng việc ``studio_tasks``: xếp, nhận, xong, lỗi, trả việc treo.

Nhận việc bằng ``SELECT … FOR UPDATE SKIP LOCKED`` (Postgres) nên chạy nhiều worker không lấy
trùng; SQLite (test) bỏ qua mệnh đề này. Mỗi hàm tự ``commit``.
"""
from __future__ import annotations

import time

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.core.database.models import StudioTask
from app.features.studio.contracts import STAGE_RANK, Lane, Stage, TaskStatus, lane_for

STALE_AFTER_SEC = 30 * 60
_BACKOFF_BASE_SEC = 60


def enqueue(
    db: Session,
    *,
    flow: str,
    stage: Stage | str,
    asset_id: int | None = None,
    project_id: int | None = None,
    payload: dict | None = None,
    parent_id: int | None = None,
    delay_sec: int = 0,
    max_attempts: int = 3,
) -> StudioTask:
    task = StudioTask(
        flow=flow,
        stage=str(Stage(stage)),
        lane=str(lane_for(stage)),
        status=TaskStatus.QUEUED,
        asset_id=asset_id,
        project_id=project_id,
        parent_id=parent_id,
        payload=dict(payload or {}),
        attempts=0,
        max_attempts=max_attempts,
        run_after=int(time.time()) + max(0, int(delay_sec)),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def claim(db: Session, *, lanes: list[Lane | str], worker_id: str) -> StudioTask | None:
    now = int(time.time())
    task = (
        db.query(StudioTask)
        .filter(
            StudioTask.status == TaskStatus.QUEUED,
            StudioTask.lane.in_([str(x) for x in lanes]),
            StudioTask.run_after <= now,
        )
        .order_by(case(STAGE_RANK, value=StudioTask.stage, else_=0).desc(), StudioTask.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if task is None:
        db.rollback()
        return None
    task.status = TaskStatus.RUNNING
    task.attempts = int(task.attempts or 0) + 1
    task.claimed_by = worker_id
    task.claimed_at = now
    db.commit()
    db.refresh(task)
    return task


def done(db: Session, task_id: int, note: str = "") -> None:
    task = db.get(StudioTask, task_id)
    task.status = TaskStatus.DONE
    task.error = note or None
    task.finished_at = int(time.time())
    db.commit()


def fail(db: Session, task_id: int, error: str, *, retryable: bool = True) -> bool:
    """Trả ``True`` khi đây là lần hỏng cuối (không thử lại nữa)."""
    task = db.get(StudioTask, task_id)
    task.error = (error or "")[:4000]
    final = not retryable or int(task.attempts or 0) >= int(task.max_attempts or 1)
    if final:
        task.status = TaskStatus.FAILED
        task.finished_at = int(time.time())
    else:
        task.status = TaskStatus.QUEUED
        task.run_after = int(time.time()) + _BACKOFF_BASE_SEC * 2 ** max(0, int(task.attempts) - 1)
    db.commit()
    return final


def requeue_stale(db: Session, *, older_than_sec: int = STALE_AFTER_SEC) -> int:
    """Việc RUNNING quá lâu (worker chết giữa chừng) → về QUEUED. Lượt đó vẫn tính vào ``attempts``."""
    cutoff = int(time.time()) - older_than_sec
    n = (
        db.query(StudioTask)
        .filter(StudioTask.status == TaskStatus.RUNNING, StudioTask.claimed_at < cutoff)
        .update({StudioTask.status: TaskStatus.QUEUED, StudioTask.claimed_by: None}, synchronize_session=False)
    )
    db.commit()
    return int(n or 0)
