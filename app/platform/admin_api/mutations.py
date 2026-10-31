"""JSON mutations for the React admin SPA — wraps existing services."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.constants import JobStatus
from app.core.database.core import SessionLocal, get_db
from app.core.database.models import Job, ViralMaterial, ViralSource
from app.core.queue.job import JobService
from app.features.viral_intake.service import ViralService

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "message": message, **extra}


def _fail(status: int, message: str) -> None:
    raise HTTPException(status_code=status, detail=message)


def _bg_process_material(material_id: int) -> None:
    try:
        with SessionLocal() as db:
            ok, msg = ViralService.process_material(db, material_id)
            logger.info("[ADMIN][viral][bg] #%s ok=%s — %s", material_id, ok, msg)
    except Exception:
        logger.exception("[ADMIN][viral][bg] Lỗi xử lý #%s", material_id)


def _bg_process_new_batch(limit: int) -> None:
    try:
        with SessionLocal() as db:
            ok, fail, msg = ViralService.process_new_batch(db, limit=limit)
            logger.info("[ADMIN][viral][bg] batch limit=%s ok=%s fail=%s — %s", limit, ok, fail, msg)
    except Exception:
        logger.exception("[ADMIN][viral][bg] Lỗi lô NEW limit=%s", limit)


def _bg_scan_source(source_id: int) -> None:
    try:
        from app.features.viral_intake.sources import SourceService

        with SessionLocal() as db:
            src = db.get(ViralSource, source_id)
            if not src:
                return
            found, skipped, err = SourceService.scan_source(db, src)
            logger.info(
                "[ADMIN][sources][bg] #%s found=%s skipped=%s err=%s",
                source_id,
                found,
                skipped,
                err,
            )
    except Exception:
        logger.exception("[ADMIN][sources][bg] Lỗi quét #%s", source_id)


# ── Jobs ────────────────────────────────────────────────────────────────────


@router.post("/jobs/{job_id}/retry")
def admin_job_retry(job_id: int, db: Session = Depends(get_db)):
    try:
        JobService.retry_job(db, job_id)
    except ValueError as e:
        _fail(400, str(e))
    return _ok(f"Job #{job_id} → PENDING", id=job_id)


@router.post("/jobs/{job_id}/cancel")
def admin_job_cancel(job_id: int, db: Session = Depends(get_db)):
    try:
        JobService.cancel_job(db, job_id)
    except ValueError as e:
        _fail(400, str(e))
    return _ok(f"Đã hủy job #{job_id}", id=job_id)


@router.post("/jobs/{job_id}/approve")
def admin_job_approve(job_id: int, db: Session = Depends(get_db)):
    JobService.approve_job(db, job_id)
    job = JobService.get_job_by_id(db, job_id)
    if not job:
        _fail(404, f"Không thấy job #{job_id}")
    return _ok(f"Job #{job_id} status={job.status}", id=job_id, status=job.status)


@router.post("/jobs/{job_id}/reset-draft")
def admin_job_reset_draft(job_id: int, db: Session = Depends(get_db)):
    try:
        JobService.reset_to_draft(db, job_id)
    except ValueError as e:
        _fail(400, str(e))
    return _ok(f"Job #{job_id} → DRAFT", id=job_id)


@router.post("/jobs/{job_id}/force-run")
def admin_job_force_run(job_id: int, db: Session = Depends(get_db)):
    try:
        JobService.force_run_job(db, job_id)
    except ValueError as e:
        _fail(400, str(e))
    return _ok(f"Job #{job_id} chạy ngay", id=job_id)


# ── Viral ───────────────────────────────────────────────────────────────────


class ViralAddLinkBody(BaseModel):
    url: str
    target_page: str = ""
    process_now: bool = False


class ViralProcessNewBody(BaseModel):
    limit: int = Field(3, ge=1, le=20)


@router.post("/viral/add-link")
def admin_viral_add_link(
    body: ViralAddLinkBody,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ok, msg, material_id = ViralService.add_material_from_url(
        db, body.url, target_page=body.target_page or None
    )
    if not ok:
        _fail(400, msg)
    if body.process_now and material_id:
        reason = ViralService.check_processable(db, material_id)
        if reason:
            return _ok(f"{msg} — chưa xử lý: {reason}", id=material_id)
        background.add_task(_bg_process_material, material_id)
        return _ok(f"{msg}, đang xử lý nền", id=material_id)
    return _ok(msg, id=material_id)


@router.post("/viral/process-new")
def admin_viral_process_new(
    background: BackgroundTasks,
    body: ViralProcessNewBody | None = None,
    db: Session = Depends(get_db),
):
    if not ViralService.ffmpeg_available():
        _fail(400, "Thiếu ffmpeg/ffprobe trên PATH — không thể reup.")
    limit = body.limit if body else 3
    new_count = db.query(ViralMaterial).filter(ViralMaterial.status == "NEW").count()
    if new_count == 0:
        _fail(400, "Không còn video NEW để xử lý.")
    background.add_task(_bg_process_new_batch, limit)
    return _ok(f"Đang xử lý nền tối đa {limit} video NEW")


@router.post("/viral/{material_id}/process")
def admin_viral_process(
    material_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
):
    reason = ViralService.check_processable(db, material_id)
    if reason:
        _fail(400, reason)
    background.add_task(_bg_process_material, material_id)
    return _ok(f"Đã nhận #{material_id}, đang xử lý nền", id=material_id)


@router.post("/viral/{material_id}/posted")
def admin_viral_posted(material_id: int, db: Session = Depends(get_db)):
    ok, msg = ViralService.mark_posted(db, material_id)
    if not ok:
        _fail(400, msg)
    return _ok(msg, id=material_id)


@router.post("/viral/{material_id}/unposted")
def admin_viral_unposted(material_id: int, db: Session = Depends(get_db)):
    ok, msg = ViralService.unmark_posted(db, material_id)
    if not ok:
        _fail(400, msg)
    return _ok(msg, id=material_id)


@router.post("/viral/{material_id}/delete")
def admin_viral_delete(material_id: int, db: Session = Depends(get_db)):
    ViralService.delete_material(db, material_id)
    return _ok(f"Đã xoá material #{material_id}", id=material_id)


# ── Viral sources ───────────────────────────────────────────────────────────


class SourceAddBody(BaseModel):
    url: str
    min_views: Optional[int] = None
    max_videos: Optional[int] = None
    target_page: str = ""


@router.post("/viral-sources")
def admin_source_add(body: SourceAddBody, db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    ok, msg, source_id = SourceService.add_source(
        db,
        body.url,
        min_views=body.min_views,
        max_videos=body.max_videos,
        target_page=body.target_page or None,
    )
    if not ok:
        _fail(400, msg)
    return _ok(msg, id=source_id)


class SourcePageBody(BaseModel):
    target_page: str = ""


@router.post("/viral-sources/{source_id}/page")
def admin_source_page(source_id: int, body: SourcePageBody, db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    src = db.get(ViralSource, source_id)
    if not src:
        _fail(404, f"Không thấy nguồn #{source_id}")
    page = (body.target_page or "").strip()
    ok, msg = SourceService.update_source(
        db,
        source_id,
        min_views=src.min_views if src.min_views is not None else "",
        max_videos=src.max_videos if src.max_videos is not None else "",
        target_pages=[page] if page else [],
    )
    if not ok:
        _fail(400, msg)
    return _ok(msg, id=source_id)


@router.post("/viral-sources/{source_id}/toggle")
def admin_source_toggle(source_id: int, db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    src = db.get(ViralSource, source_id)
    if not src:
        _fail(404, f"Không thấy nguồn #{source_id}")
    enabled = not bool(src.enabled)
    SourceService.set_enabled(db, source_id, enabled)
    return _ok(f"Nguồn #{source_id} → {'ON' if enabled else 'OFF'}", id=source_id, enabled=enabled)


@router.post("/viral-sources/{source_id}/scan")
def admin_source_scan(source_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    src = db.get(ViralSource, source_id)
    if not src:
        _fail(404, f"Không thấy nguồn #{source_id}")
    background.add_task(_bg_scan_source, source_id)
    return _ok(f"Đang quét nền nguồn #{source_id}", id=source_id)


@router.delete("/viral-sources/{source_id}")
def admin_source_delete(source_id: int, db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    if not SourceService.delete_source(db, source_id):
        _fail(404, f"Không thấy nguồn #{source_id}")
    return _ok(f"Đã xoá nguồn #{source_id}", id=source_id)


# ── AI / Syspanel / Database ────────────────────────────────────────────────


class AiStudioSaveBody(BaseModel):
    key: str
    value: str = ""


@router.post("/ai-studio/save")
def admin_ai_studio_save(body: AiStudioSaveBody, request: Request, db: Session = Depends(get_db)):
    from app.features.system_panel.ai_studio_service import AIStudioService

    updated_by = request.client.host if request.client else None
    try:
        AIStudioService.save_setting(db, key=body.key, value=body.value, updated_by=updated_by)
    except ValueError as e:
        _fail(400, str(e))
    return _ok(f"Đã lưu {body.key}")


@router.post("/syspanel/retry-failed")
def admin_syspanel_retry_failed(db: Session = Depends(get_db)):
    active_statuses = [
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.DONE,
        JobStatus.DRAFT,
        JobStatus.AI_PROCESSING,
        JobStatus.AWAITING_STYLE,
    ]
    active_pairs = db.query(Job.viral_material_id, Job.target_page).filter(
        Job.viral_material_id.isnot(None),
        Job.status.in_(active_statuses),
    ).all()
    active_keys = {(mid, (tp or "").strip()) for mid, tp in active_pairs if mid is not None}

    failed = (
        db.query(Job)
        .filter(Job.status == JobStatus.FAILED)
        .order_by(Job.id.desc())
        .all()
    )

    retried_count = 0
    seen_in_batch = set()
    for job in failed:
        if job.viral_material_id is not None:
            key = (job.viral_material_id, (job.target_page or "").strip())
            if key in active_keys or key in seen_in_batch:
                continue
            seen_in_batch.add(key)

        if job.platform == "buffer":
            if job.viral_material_id:
                from app.features.buffer.queue_job import auto_schedule_ready

                ok, _ = auto_schedule_ready(db, job.viral_material_id)
                if ok:
                    retried_count += 1
            continue

        job.status = JobStatus.PENDING
        job.tries = 0
        job.locked_at = None
        retried_count += 1

    db.commit()
    return _ok(f"Retried {retried_count} FAILED jobs", count=retried_count)


@router.post("/syspanel/cancel-stuck")
def admin_syspanel_cancel_stuck(db: Session = Depends(get_db)):
    import time

    cutoff = int(time.time()) - 600
    stuck = (
        db.query(Job)
        .filter(Job.status == JobStatus.RUNNING, Job.last_heartbeat_at < cutoff)
        .all()
    )
    count = len(stuck)
    for job in stuck:
        job.status = JobStatus.FAILED
        job.last_error = "Cancelled: no heartbeat for 10+ min (admin SPA)"
    db.commit()
    return _ok(f"Cancelled {count} job kẹt", count=count)


@router.post("/syspanel/worker/{action}")
def admin_syspanel_worker(action: str, db: Session = Depends(get_db)):
    from app.core.queue.worker import WorkerService

    if action == "pause":
        WorkerService.set_status(db, "PAUSED")
    elif action == "resume":
        WorkerService.set_status(db, JobStatus.RUNNING)
    elif action == "safe-mode":
        WorkerService.toggle_safe_mode(db)
    else:
        _fail(400, "action phải là pause | resume | safe-mode")
    return _ok(f"Worker {action}")


class SqlBody(BaseModel):
    sql: str
    confirmed: bool = False


@router.get("/database/tables/{table_name}")
def admin_database_table(table_name: str, limit: int = 50, q: str = ""):
    from app.core.db_admin.database_service import DatabaseService

    data = DatabaseService.get_table_data(table_name, limit, q)
    if not data:
        _fail(404, "Bảng không hợp lệ")
    return data


@router.post("/database/sql")
def admin_database_sql(body: SqlBody, request: Request, db: Session = Depends(get_db)):
    from app.core.db_admin.database_service import DatabaseService

    ip = request.client.host if request.client else "unknown"
    return DatabaseService.execute_sql(db, body.sql, body.confirmed, ip)
