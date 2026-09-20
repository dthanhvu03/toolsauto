"""JSON mutations for the React admin SPA — wraps existing services."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.constants import JobStatus
from app.core.account import AccountService
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


@router.post("/jobs/manual")
async def admin_job_manual(
    account_id: int = Form(...),
    target_page: str = Form(""),
    caption: str = Form(""),
    job_type: str = Form("POST"),
    media: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    caption_text = (caption or "").strip()
    if caption_text:
        from app.core.compliance.facebook_compliance import Severity, compliance_checker

        result = compliance_checker.check(caption_text)
        if result.status == Severity.VIOLATION:
            evidence = ", ".join([v.evidence for v in result.violations])
            _fail(400, f"Caption vi phạm Facebook ({evidence})")
    try:
        job = JobService.create_manual_job_with_file(
            db,
            account_id,
            (target_page or "").strip(),
            caption_text,
            media,
            job_type=job_type,
        )
    except Exception as e:
        logger.exception("[ADMIN][jobs] manual create")
        _fail(400, str(e))
    return _ok(f"Đã tạo job #{job.id}", id=job.id, status=job.status)


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


# ── Accounts ────────────────────────────────────────────────────────────────


class AccountCreateBody(BaseModel):
    name: str
    platform: str = "facebook"
    daily_limit: int = 3
    cooldown_seconds: int = Field(default=1800, ge=1800, le=86400)


class AccountRenameBody(BaseModel):
    name: str


@router.post("/accounts")
def admin_account_create(body: AccountCreateBody, db: Session = Depends(get_db)):
    name = (body.name or "").strip()
    if not name:
        _fail(400, "Tên tài khoản trống")
    platform = (body.platform or "facebook").strip().lower()
    if platform not in ("facebook", "instagram", "threads", "tiktok"):
        platform = "facebook"
    try:
        acc = AccountService.create_account(
            db,
            platform=platform,
            name=name,
            daily_limit=body.daily_limit,
            cooldown_seconds=body.cooldown_seconds,
        )
    except Exception as e:
        logger.exception("[ADMIN][accounts] create")
        _fail(400, str(e))
    return _ok(f"Đã tạo account #{acc.id}", id=acc.id, name=acc.name)


@router.post("/accounts/{account_id}/toggle")
def admin_account_toggle(account_id: int, db: Session = Depends(get_db)):
    try:
        acc = AccountService.toggle_account(db, account_id)
    except ValueError as e:
        _fail(400, str(e))
    if not acc:
        _fail(404, f"Không thấy account #{account_id}")
    return _ok(
        f"{acc.name} → {'ACTIVE' if acc.is_active else 'OFF'}",
        id=acc.id,
        is_active=bool(acc.is_active),
    )


@router.post("/accounts/{account_id}/rename")
def admin_account_rename(account_id: int, body: AccountRenameBody, db: Session = Depends(get_db)):
    acc = AccountService.rename_account(db, account_id, (body.name or "").strip())
    if not acc:
        _fail(404, f"Không thấy account #{account_id}")
    return _ok(f"Đã đổi tên #{account_id}", id=acc.id, name=acc.name)


@router.post("/accounts/{account_id}/delete")
def admin_account_delete(account_id: int, db: Session = Depends(get_db)):
    AccountService.delete_account(db, account_id)
    return _ok(f"Đã xoá account #{account_id}", id=account_id)


# ── Affiliates ──────────────────────────────────────────────────────────────


class AffiliateSaveBody(BaseModel):
    id: int = 0
    keyword: str
    url: str
    comment_template: str = ""
    commission_rate: Optional[float] = None


@router.post("/affiliates")
def admin_affiliate_save(body: AffiliateSaveBody, db: Session = Depends(get_db)):
    from app.features.affiliates.service import AffiliateService

    success, error_data = AffiliateService.save_link(
        db,
        body.id,
        body.keyword,
        body.url,
        body.comment_template,
        commission_rate=body.commission_rate,
    )
    if not success:
        _fail(int((error_data or {}).get("status_code") or 400), str((error_data or {}).get("error") or error_data))
    return _ok("Đã lưu affiliate")


@router.delete("/affiliates/{link_id}")
def admin_affiliate_delete(link_id: int, db: Session = Depends(get_db)):
    from app.features.affiliates.service import AffiliateService

    if not AffiliateService.delete_link(db, link_id):
        _fail(404, "Không tìm thấy link")
    return _ok(f"Đã xoá affiliate #{link_id}", id=link_id)


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


# ── AI Studio / FB tasks / Threads / Syspanel / Database ────────────────────


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


class FbProSaveBody(BaseModel):
    scope_key: str = ""
    notes: str = ""
    posts_override: str = ""
    reels_override: str = ""
    target_posts: Optional[int] = None
    target_reels: Optional[int] = None
    target_interactions: Optional[int] = None
    interactions: Optional[int] = None


@router.post("/fb-pro-tasks/save")
def admin_fb_pro_save(body: FbProSaveBody, db: Session = Depends(get_db)):
    from app.features.fb_pro_tasks import service as fb_pro_tasks

    payload: dict[str, Any] = {
        "scope_key": body.scope_key or None,
        "notes": body.notes,
        "posts_override": body.posts_override,
        "reels_override": body.reels_override,
    }
    if body.interactions is not None:
        payload["interactions"] = body.interactions
    if body.target_posts is not None:
        payload["target_posts"] = body.target_posts
    if body.target_reels is not None:
        payload["target_reels"] = body.target_reels
    if body.target_interactions is not None:
        payload["target_interactions"] = body.target_interactions
    fb_pro_tasks.update_from_form(payload, db)
    return _ok("Đã lưu nhiệm vụ tuần")


@router.post("/fb-pro-tasks/reset-week")
def admin_fb_pro_reset(body: FbProSaveBody | None = None, db: Session = Depends(get_db)):
    from app.features.fb_pro_tasks import service as fb_pro_tasks

    key = (body.scope_key if body else "") or None
    fb_pro_tasks.reset_week_now(db, key=key)
    return _ok("Đã reset tuần")


@router.post("/threads/toggle-auto")
def admin_threads_toggle_auto(db: Session = Depends(get_db)):
    from app.features.threads.dashboard import ThreadsService

    ThreadsService.toggle_auto_mode(db)
    return _ok("Đã đảo auto Threads")


@router.post("/threads/trigger-scrape")
def admin_threads_scrape(db: Session = Depends(get_db)):
    from app.features.threads.dashboard import ThreadsService

    ThreadsService.trigger_news_scrape(db)
    return _ok("Đã kích hoạt scrape tin Threads")


class ThreadsAccountBody(BaseModel):
    account_id: int


@router.post("/threads/link")
def admin_threads_link(body: ThreadsAccountBody, db: Session = Depends(get_db)):
    from app.features.threads.dashboard import ThreadsService

    ThreadsService.link_account(db, body.account_id)
    return _ok(f"Đã nối account #{body.account_id}")


@router.post("/threads/unlink")
def admin_threads_unlink(body: ThreadsAccountBody, db: Session = Depends(get_db)):
    from app.features.threads.dashboard import ThreadsService

    ThreadsService.unlink_account(db, body.account_id)
    return _ok(f"Đã gỡ account #{body.account_id}")


@router.post("/syspanel/retry-failed")
def admin_syspanel_retry_failed(db: Session = Depends(get_db)):
    failed = db.query(Job).filter(Job.status == JobStatus.FAILED).all()
    count = len(failed)
    for job in failed:
        job.status = JobStatus.PENDING
        job.tries = 0
        job.locked_at = None
    db.commit()
    return _ok(f"Retried {count} FAILED → PENDING", count=count)


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
