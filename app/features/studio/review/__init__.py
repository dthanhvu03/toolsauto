"""
Bước ``review`` — đúng một việc: cổng duyệt.

Kênh bật ``auto_approve`` và dự án đã có caption → APPROVED, quy trình đi tiếp sang ``publish``. Còn lại
→ REVIEW, báo Telegram (``notify``) và dừng; người duyệt (``entry.approve`` — web / Telegram) mới đẩy tiếp.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.database.models import StudioChannel, StudioProject, StudioTask
from app.features.studio import notify
from app.features.studio.contracts import ProjectStatus, StageError, StageResult


def run(db: Session, task: StudioTask) -> StageResult:
    project = db.get(StudioProject, task.project_id) if task.project_id else None
    if project is None:
        raise StageError(f"không có dự án #{task.project_id}", retryable=False)
    if project.status == ProjectStatus.REVIEW and project.output_path:
        # Lưu spec 2 lần liền → 2 lượt rerender; lượt trước đã đưa vào chờ duyệt (và đã báo Telegram).
        return StageResult(project_id=project.id, stop=True, note="đã ở chờ duyệt")
    if project.status != ProjectStatus.RENDERED or not project.output_path:
        raise StageError(f"dự án #{project.id} chưa render xong ({project.status})", retryable=False)

    channel = db.get(StudioChannel, project.channel_id) if project.channel_id else None
    if channel is not None and channel.auto_approve and (project.caption or "").strip():
        project.status = ProjectStatus.APPROVED
        project.approved_at = int(time.time())
        db.commit()
        return StageResult(project_id=project.id, note="tự duyệt")

    project.status = ProjectStatus.REVIEW
    db.commit()
    notify.review_ready(db, project)
    return StageResult(project_id=project.id, stop=True, note="chờ duyệt")
