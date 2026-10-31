"""
Bước ``publish`` — đúng một việc: dự án đã duyệt → một dòng ``viral_materials`` READY mà luồng Buffer
sẵn có đọc (PLAN-106 P3, cầu nối tạm tới P6). Không gọi Buffer, không sửa code Buffer.

Buffer cần ba thứ, bước này đặt đủ cả ba:
- file ``viral_<id>_*_reup.mp4`` trong ``REUP_DIR`` (``find_reup_path`` dò cả thư mục con) — ở đây là
  ``REUP_DIR/studio/``, nối cứng từ bản render nên không tốn thêm ổ;
- ``target_page`` = id kênh Buffer;
- ``ai_caption`` + ``ai_hashtags``.
Maintenance (``sweep_unscheduled_ready``) thấy dòng READY đủ ba thứ thì tự lấy ô giờ và hẹn lên Buffer.

Video reup do hệ cũ chuyển sang (material đang ``STUDIO``) thì dùng lại chính dòng đó; nguồn khác thì tạo
dòng mới ``platform="studio"``. Dòng đã có lịch trên Buffer thì không đổi file / caption nữa.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from sqlalchemy.orm import Session

import app.config as config
from app.constants import JobStatus, ViralStatus
from app.core.database.models import Job, StudioAsset, StudioChannel, StudioProject, StudioTask, ViralMaterial
from app.features.studio.contracts import ProjectStatus, StageError, StageResult

PLATFORM = "studio"


def studio_reup_dir() -> Path:
    path = Path(config.REUP_DIR) / PLATFORM
    path.mkdir(parents=True, exist_ok=True)
    return path


def _material(db: Session, project: StudioProject) -> ViralMaterial:
    if project.viral_material_id:
        mat = db.get(ViralMaterial, project.viral_material_id)
        if mat is not None:
            return mat
    asset = db.get(StudioAsset, project.asset_id) if project.asset_id else None
    if asset is not None and asset.viral_material_id:
        mat = db.get(ViralMaterial, asset.viral_material_id)
        if mat is not None and mat.status == ViralStatus.STUDIO:
            return mat
    mat = ViralMaterial(
        platform=PLATFORM,
        url=f"studio://project/{project.id}",
        title=((asset.title if asset else None) or f"Studio #{project.id}")[:500],
        views=0,
        status=ViralStatus.STUDIO,
    )
    db.add(mat)
    db.flush()
    return mat


def _place(src: Path, mat_id: int, project_id: int) -> Path:
    folder = studio_reup_dir()
    dest = folder / f"viral_{mat_id}_p{project_id}_reup.mp4"
    tmp = dest.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    try:
        os.link(src, tmp)  # cùng ổ: không tốn chỗ
    except OSError:
        shutil.copy2(src, tmp)
    tmp.replace(dest)
    for old in folder.glob(f"viral_{mat_id}_*_reup.mp4"):  # bản render trước của cùng video
        if old != dest:
            old.unlink(missing_ok=True)
    return dest


def run(db: Session, task: StudioTask) -> StageResult:
    project = db.get(StudioProject, task.project_id) if task.project_id else None
    if project is None:
        raise StageError(f"không có dự án #{task.project_id}", retryable=False)
    if project.status not in (ProjectStatus.APPROVED, ProjectStatus.SCHEDULED):
        raise StageError(f"dự án #{project.id} chưa duyệt ({project.status})", retryable=False)
    channel = db.get(StudioChannel, project.channel_id) if project.channel_id else None
    if channel is None:
        raise StageError(f"dự án #{project.id} chưa có kênh", retryable=False)
    caption = (project.caption or "").strip()
    if not caption:
        raise StageError(f"dự án #{project.id} chưa có caption", retryable=False)
    src = Path(project.output_path or "")
    if not src.is_file():
        raise StageError(f"dự án #{project.id} không còn file render", retryable=False)

    mat = _material(db, project)
    booked = (
        db.query(Job.id)
        .filter(Job.platform == "buffer", Job.viral_material_id == mat.id, Job.status == JobStatus.DONE)
        .first()
    )
    if booked is not None:
        raise StageError(
            f"material #{mat.id} đã có lịch Buffer (job #{booked.id}) — huỷ lịch rồi mới đổi bản render",
            retryable=False,
        )

    dest = _place(src, mat.id, project.id)
    mat.status = ViralStatus.READY
    mat.target_page = channel.buffer_channel_id
    mat.target_pages = None
    mat.ai_caption = caption
    mat.ai_hashtags = json.dumps(list(project.hashtags or []), ensure_ascii=False)
    mat.ai_caption_at = int(time.time())
    mat.ai_caption_error = None
    mat.last_error = None
    project.viral_material_id = mat.id
    db.commit()
    return StageResult(project_id=project.id, note=f"material #{mat.id} READY → {channel.name} ({dest.name})")
