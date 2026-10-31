"""
Đồng bộ ngược từ luồng Buffer về dự án (không gọi Buffer — chỉ đọc DB):

- material có job Buffer DONE (Buffer đã nhận, đã hẹn giờ) → dự án SCHEDULED;
- material POSTED (``sync_posted`` của Buffer hoặc anh bấm «Đã đăng») → dự án POSTED.

Worker làn light gọi định kỳ.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants import JobStatus, ViralStatus
from app.core.database.models import Job, StudioProject, ViralMaterial
from app.features.studio.contracts import ProjectStatus


def sync(db: Session) -> int:
    projects = (
        db.query(StudioProject)
        .filter(
            StudioProject.viral_material_id.isnot(None),
            StudioProject.status.in_([ProjectStatus.APPROVED, ProjectStatus.SCHEDULED]),
        )
        .all()
    )
    changed = 0
    for project in projects:
        mat = db.get(ViralMaterial, project.viral_material_id)
        if mat is None:
            continue
        if mat.status == ViralStatus.POSTED:
            new = ProjectStatus.POSTED
        elif (
            db.query(Job.id)
            .filter(Job.platform == "buffer", Job.viral_material_id == mat.id, Job.status == JobStatus.DONE)
            .first()
        ):
            new = ProjectStatus.SCHEDULED
        else:
            continue
        if project.status != new:
            project.status = new
            changed += 1
    if changed:
        db.commit()
    return changed
