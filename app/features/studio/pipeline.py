"""
ADR-061 — bản đồ quy trình Studio. Đây là module **duy nhất** biết thứ tự các bước.

Một flow là danh sách bước. Bước chạy xong thì ``advance`` xếp bước kế tiếp vào ``studio_tasks``
với asset / dự án mà bước vừa trả ra, payload gộp dần (``channel_id`` đi suốt quy trình).

Thêm nguồn mới = thêm một flow. Thêm bước mới = viết package bước + đăng ký vào ``STAGES``.
"""
from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy.orm import Session

from app.core.database.models import StudioProject, StudioTask
from app.features.studio import analyze, caption, compose, dub, intake, publish, queue, render, review
from app.features.studio.contracts import ProjectStatus, Stage, StageError, StageResult

logger = logging.getLogger(__name__)

StageFn = Callable[[Session, StudioTask], StageResult]

STAGES: dict[Stage, StageFn] = {
    Stage.INTAKE: intake.run,
    Stage.ANALYZE: analyze.run,
    Stage.DUB: dub.run,
    Stage.COMPOSE: compose.run,
    Stage.RENDER: render.run,
    Stage.CAPTION: caption.run,
    Stage.REVIEW: review.run,
    Stage.PUBLISH: publish.run,
}

# dub tự bỏ qua khi mẫu không lồng tiếng; caption tự bỏ qua khi dự án đã có caption.
# review dừng ở REVIEW khi chưa duyệt; duyệt tay thì entry.approve bắt đầu flow ``publish``.
_EDIT = [Stage.INTAKE, Stage.ANALYZE, Stage.DUB, Stage.COMPOSE, Stage.RENDER, Stage.CAPTION, Stage.REVIEW, Stage.PUBLISH]
FLOWS: dict[str, list[Stage]] = {
    "reup": _EDIT,  # video hệ cũ tải + chống trùng xong, kênh đã chuyển sang Studio (entry.take_reup)
    "upload": _EDIT,  # video anh tự quay: web / hộp thư Drive (entry)
    "brand": [Stage.INTAKE, Stage.ANALYZE],  # intro / outro / logo / nhạc: chỉ vào kho, không thành dự án
    "rerender": [Stage.RENDER, Stage.CAPTION, Stage.REVIEW, Stage.PUBLISH],  # sau khi sửa spec trên trình edit
    "publish": [Stage.PUBLISH],
    # đổi mẫu trên trình edit: dựng lại spec từ asset đã có (không intake / phân tích lại)
    "recompose": [Stage.COMPOSE, Stage.RENDER, Stage.CAPTION, Stage.REVIEW, Stage.PUBLISH],  # duyệt tay xong → sang Buffer (P3, cầu nối viral_materials)
}


def start(
    db: Session,
    flow: str,
    *,
    asset_id: int | None = None,
    project_id: int | None = None,
    payload: dict | None = None,
) -> StudioTask:
    if flow not in FLOWS:
        raise ValueError(f"không có flow {flow!r}")
    return queue.enqueue(db, flow=flow, stage=FLOWS[flow][0], asset_id=asset_id, project_id=project_id, payload=payload)


def next_stage(flow: str, stage: Stage | str) -> Stage | None:
    steps = FLOWS.get(flow) or []
    stage = Stage(stage)
    if stage not in steps:
        return None
    i = steps.index(stage)
    return steps[i + 1] if i + 1 < len(steps) else None


def advance(db: Session, task: StudioTask, result: StageResult) -> StudioTask | None:
    if result.stop:
        return None
    nxt = next_stage(task.flow, task.stage)
    if nxt is None:
        return None
    return queue.enqueue(
        db,
        flow=task.flow,
        stage=nxt,
        asset_id=result.asset_id or task.asset_id,
        project_id=result.project_id or task.project_id,
        payload={**(task.payload or {}), **(result.payload or {})},
        parent_id=task.id,
    )


def _mark_project_failed(db: Session, project_id: int | None, error: str) -> None:
    if not project_id:
        return
    project = db.get(StudioProject, project_id)
    if project is not None:
        project.status = ProjectStatus.FAILED
        project.error = error[:4000]
        db.commit()


def run_task(db: Session, task: StudioTask) -> StageResult | None:
    """Chạy một việc đã nhận: gọi bước → ghi xong / lỗi → xếp bước sau. Không ném lỗi của bước ra ngoài."""
    task_id, project_id, stage = task.id, task.project_id, task.stage
    fn = STAGES.get(Stage(stage))
    try:
        if fn is None:
            raise StageError(f"bước {stage!r} chưa đăng ký", retryable=False)
        result = fn(db, task)
    except StageError as exc:
        db.rollback()
        logger.warning("[STUDIO] việc #%s (%s) lỗi: %s", task_id, stage, exc)
        if queue.fail(db, task_id, str(exc), retryable=exc.retryable):
            _mark_project_failed(db, project_id, str(exc))
        return None
    except Exception as exc:  # lỗi không lường trước: vẫn cho thử lại theo max_attempts
        db.rollback()
        logger.exception("[STUDIO] việc #%s (%s) hỏng bất ngờ", task_id, stage)
        error = f"{type(exc).__name__}: {exc}"
        if queue.fail(db, task_id, error):
            _mark_project_failed(db, project_id, error)
        return None
    queue.done(db, task_id, result.note)
    advance(db, db.get(StudioTask, task_id), result)
    return result
