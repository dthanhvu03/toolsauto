"""JSON API cho SPA `/app` — bọc DashboardService / JobService. PLAN-108: chỉ còn module đang chạy."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core.queue.job import JobService
from app.platform.dashboard_service import DashboardService

router = APIRouter(prefix="/api/admin", tags=["admin-api"])
logger = logging.getLogger(__name__)


def _comment_ok_label(job, child=None) -> str:
    """ok | fail | pending | none — Owner thấy comment affiliate đã lên Reel chưa."""
    from app.constants import JobStatus, JobType

    jt = str(getattr(job, "job_type", "") or "POST").strip().upper()
    if jt == JobType.COMMENT:
        st = str(job.status or "").upper()
        if st == JobStatus.DONE:
            return "ok"
        if st == JobStatus.FAILED:
            return "fail"
        return "pending"

    has_cmt = bool((getattr(job, "auto_comment_text", None) or "").strip())
    if not has_cmt:
        return "none"
    if child is None:
        return "none" if str(job.status or "").upper() != JobStatus.DONE else "fail"
    st = str(child.status or "").upper()
    if st == JobStatus.DONE:
        return "ok"
    if st == JobStatus.FAILED:
        return "fail"
    return "pending"


def _comment_children_by_parent(db: Session, jobs: list) -> dict[int, Any]:
    from app.constants import JobType
    from app.core.database.models import Job

    ids = [j.id for j in jobs if getattr(j, "id", None) is not None]
    if not ids:
        return {}
    children = (
        db.query(Job)
        .filter(Job.parent_job_id.in_(ids), Job.job_type == JobType.COMMENT)
        .order_by(Job.id.desc())
        .all()
    )
    by_parent: dict[int, Any] = {}
    for child in children:
        pid = child.parent_job_id
        if pid is not None and pid not in by_parent:
            by_parent[pid] = child
    return by_parent


def _job_row(j, comment_child=None, names: dict[str, str] | None = None) -> dict[str, Any]:
    acc = getattr(j, "account", None)
    aff = (getattr(j, "affiliate_url", None) or "").strip()
    post_url = getattr(j, "post_url", None)
    status = str(getattr(j, "status", "") or "")
    posted = status.upper() == "DONE" and bool(post_url)
    return {
        "id": j.id,
        "status": j.status,
        "platform": j.platform,
        "job_type": getattr(j, "job_type", None),
        "account_id": j.account_id,
        "account_name": acc.name if acc else None,
        "target_page": j.target_page,
        "channel": (names or {}).get(j.target_page or "", j.target_page),
        "material_id": getattr(j, "viral_material_id", None),
        "caption": (j.caption or "")[:160],
        "post_url": post_url,
        "posted": posted,
        "affiliate_url": aff[:160] if aff else None,
        "has_auto_comment": bool((getattr(j, "auto_comment_text", None) or "").strip()),
        "comment_ok": _comment_ok_label(j, comment_child),
        "schedule_ts": j.schedule_ts,
        "finished_at": j.finished_at,
        "error_message": (getattr(j, "last_error", None) or getattr(j, "error_message", None) or "")[:200],
    }


def _viral_item_row(row: dict[str, Any]) -> dict[str, Any]:
    it = row["item"]
    job = row.get("job") or {}
    return {
        "id": it.id,
        "url": it.url,
        "platform": it.platform,
        "status": it.status,
        "views": it.views,
        "account_name": row.get("account_name"),
        "has_reup": row.get("has_reup"),
        "is_mega": row.get("is_mega"),
        "created_at": it.created_at,
        "job_id": job.get("job_id"),
        "job_status": job.get("job_status"),
    }


# Project rule: disk < 2GB → pause new jobs.
DISK_PAUSE_GB = 2.0


def _disk_ops() -> dict[str, Any]:
    from pathlib import Path

    import psutil

    import app.config as app_config

    disk_path = str(app_config.BASE_DIR)
    try:
        disk = psutil.disk_usage(disk_path)
    except OSError:
        disk = psutil.disk_usage("/")
        disk_path = "/"
    free_gb = round(disk.free / 1024**3, 2)
    return {
        "free_gb": free_gb,
        "used_gb": round(disk.used / 1024**3, 2),
        "total_gb": round(disk.total / 1024**3, 2),
        "pct": disk.percent,
        "label": Path(disk_path).drive or disk_path,
        "pause_below_gb": DISK_PAUSE_GB,
        "below_pause": free_gb < DISK_PAUSE_GB,
    }


def _failed_jobs_ops(db: Session, names: dict[str, str]) -> dict[str, Any]:
    from app.constants import JobStatus
    from app.core.database.models import Job

    q = db.query(Job).filter(Job.status == JobStatus.FAILED)
    latest = q.order_by(Job.finished_at.desc(), Job.id.desc()).limit(5).all()
    return {
        "count": q.count(),
        "latest": [
            {
                "id": j.id,
                "status": j.status,
                "channel": names.get(j.target_page or "", j.target_page),
                "error": (j.last_error or "")[:200],
                "finished_at": j.finished_at,
            }
            for j in latest
        ],
    }


def _buffer_channels_ops(db: Session, names: dict[str, str], now: int) -> list[dict[str, Any]]:
    """
    Mỗi kênh Buffer: video READY chưa đưa lên Buffer, bài đã hẹn chưa tới giờ, giờ lên gần nhất,
    bài đã tới giờ 7 ngày qua. Chỉ đọc DB — không gọi Buffer API (tốn suất).
    """
    from sqlalchemy import and_, func

    from app.constants import JobStatus, ViralStatus
    from app.core.database.models import Job, ViralMaterial

    sent = (
        db.query(Job.id)
        .filter(
            Job.platform == "buffer",
            Job.status == JobStatus.DONE,
            Job.viral_material_id == ViralMaterial.id,
            Job.target_page == ViralMaterial.target_page,
        )
        .exists()
    )
    waiting = dict(
        db.query(ViralMaterial.target_page, func.count(ViralMaterial.id))
        .filter(ViralMaterial.status == ViralStatus.READY, ViralMaterial.target_page.isnot(None), ~sent)
        .group_by(ViralMaterial.target_page)
        .all()
    )
    buffer_done = and_(Job.platform == "buffer", Job.status == JobStatus.DONE)
    upcoming = {
        page: (n, nxt)
        for page, n, nxt in db.query(Job.target_page, func.count(Job.id), func.min(Job.schedule_ts))
        .filter(buffer_done, Job.schedule_ts > now)
        .group_by(Job.target_page)
        .all()
    }
    posted_7d = dict(
        db.query(Job.target_page, func.count(Job.id))
        .filter(buffer_done, Job.schedule_ts > now - 7 * 86400, Job.schedule_ts <= now)
        .group_by(Job.target_page)
        .all()
    )
    ids = list(names) + sorted({*waiting, *upcoming} - set(names) - {"", None})
    return [
        {
            "id": cid,
            "name": names.get(cid, cid),
            "ready_waiting": int(waiting.get(cid, 0)),
            "scheduled": int(upcoming.get(cid, (0, None))[0]),
            "next_at": upcoming.get(cid, (0, None))[1],
            "posted_7d": int(posted_7d.get(cid, 0)),
        }
        for cid in ids
    ]


def _count_by_status(db: Session, model, *filters) -> dict[str, int]:
    from sqlalchemy import func

    rows = db.query(model.status, func.count(model.id)).filter(*filters).group_by(model.status).all()
    return {str(status): int(n) for status, n in rows}


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db)):
    """PLAN-108: tổng quan theo luồng thật — video → Buffer. Chỉ đọc DB."""
    import time

    from app.core.database.models import Job, ViralMaterial

    now = int(time.time())
    names = _channel_names()
    return {
        "generated_at": now,
        "channels": _buffer_channels_ops(db, names, now),
        "jobs_24h": _count_by_status(db, Job, Job.platform == "buffer", Job.created_at > now - 86400),
        "materials_7d": _count_by_status(db, ViralMaterial, ViralMaterial.created_at > now - 7 * 86400),
        "failed_jobs": _failed_jobs_ops(db, names),
        "disk": _disk_ops(),
    }


@router.get("/jobs")
def admin_jobs(
    db: Session = Depends(get_db),
    status: str = Query("active"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str = Query(""),
    platform: str = Query(""),
):
    raw = JobService.get_jobs_paged(
        db, status=status, page=page, per_page=per_page, q=q, platform=platform
    )
    children = _comment_children_by_parent(db, raw["jobs"])
    names = _channel_names()
    return {
        "jobs": [_job_row(j, comment_child=children.get(j.id), names=names) for j in raw["jobs"]],
        "total": raw["total"],
        "total_pages": raw["total_pages"],
        "page": raw["page"],
        "status": status,
        "platform": platform,
        "q": q,
    }


@router.get("/viral")
def admin_viral(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=20, le=100),
    q: str = Query(""),
    status: str = Query(""),
    platform: str = Query(""),
    min_views: int = Query(0, ge=0),
):
    raw = DashboardService.get_viral_materials(
        db,
        page=page,
        per_page=per_page,
        q=q,
        status=status,
        platform=platform,
        min_views=min_views,
    )
    return {
        "items": [_viral_item_row(r) for r in raw["items"]],
        "page": raw["page"],
        "per_page": raw["per_page"],
        "total": raw["total"],
        "total_pages": raw["total_pages"],
        "status_counts": raw.get("status_counts"),
        "new_count": raw.get("new_count"),
        "failed_count": raw.get("failed_count"),
        "ready_count": raw.get("ready_count"),
    }


def _viral_source_row(src) -> dict[str, Any]:
    pages = list(getattr(src, "target_pages_list", None) or [])
    return {
        "id": src.id,
        "platform": src.platform,
        "url": src.url,
        "handle": src.handle,
        "min_views": src.min_views,
        "max_videos": src.max_videos,
        "target_pages": pages,
        "enabled": bool(src.enabled),
        "last_scanned_at": src.last_scanned_at,
        "last_found": src.last_found,
        "last_error": (src.last_error or "")[:200] or None,
    }


def _buffer_page_choices() -> list[dict[str, str]]:
    from app.features.buffer.queue_job import _channels
    from app.features.buffer.slots import slots_label

    rows = []
    for item in _channels():
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "slots": slots_label(item["name"]),
            }
        )
    return rows


def _channel_names() -> dict[str, str]:
    """id kênh Buffer → tên. Đọc cài đặt hỏng thì trả rỗng: bảng vẫn hiện id, không sập cả trang."""
    try:
        return {c["id"]: c["name"] for c in _buffer_page_choices()}
    except Exception:
        logger.warning("[ADMIN] không đọc được BUFFER_CHANNELS", exc_info=True)
        return {}


@router.get("/viral-sources")
def admin_viral_sources(db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    try:
        sources = SourceService.list_sources(db)
    except Exception:
        sources = []
    return {
        "items": [_viral_source_row(s) for s in sources],
        "total": len(sources),
        "pages": _buffer_page_choices(),
    }


def _log_event_row(e) -> dict[str, Any]:
    if hasattr(e, "model_dump"):
        d = e.model_dump(mode="json")
    else:
        d = e.dict()
    msg = d.get("message") or ""
    return {
        "timestamp": str(d.get("timestamp") or ""),
        "ts_unix": d.get("ts_unix"),
        "source": d.get("source") or "",
        "level": d.get("level") or "",
        "job_id": d.get("job_id"),
        "event_type": d.get("event_type") or "",
        "message": msg[:240],
    }


@router.get("/logs")
def admin_logs(
    db: Session = Depends(get_db),
    source: str = Query(""),
    level: str = Query(""),
    job_id: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    from app.core.observability.log_query_facade import LogQueryFacade

    job_id_int = int(job_id) if (job_id or "").isdigit() else None
    events, total, total_pages = LogQueryFacade.query_domain_events(
        db=db,
        source=source or None,
        level=level or None,
        job_id=job_id_int,
        q=q or None,
        page=page,
        per_page=30,
        category="user",
    )
    return {
        "events": [_log_event_row(e) for e in events],
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "q": q,
        "level": level,
        "source": source,
    }


def _studio_item(item_id: str, info: dict[str, Any]) -> dict[str, Any]:
    value = info.get("value") or ""
    return {
        "id": item_id,
        "key": info.get("key") or "",
        "label": info.get("label") or item_id,
        "preview": value[:160],
        "chars": len(value),
        "value": value,
    }


@router.get("/ai-studio")
def admin_ai_studio(db: Session = Depends(get_db)):
    from app.features.system_panel.ai_studio_service import AIStudioService

    ctx = AIStudioService.get_studio_context(db)
    return {
        "personas": [_studio_item(k, v) for k, v in (ctx.get("personas") or {}).items()],
        "configs": [_studio_item(k, v) for k, v in (ctx.get("configs") or {}).items()],
        "platforms": [_studio_item(k, v) for k, v in (ctx.get("platforms") or {}).items()],
    }


@router.get("/syspanel")
def admin_syspanel(db: Session = Depends(get_db)):
    import psutil
    from pathlib import Path

    from sqlalchemy import text as sa_text

    import app.config as app_config

    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk_path = str(app_config.BASE_DIR)
    try:
        disk = psutil.disk_usage(disk_path)
    except OSError:
        disk = psutil.disk_usage("/")
        disk_path = "/"
    jobs: dict[str, int] = {}
    try:
        rows = db.execute(sa_text("SELECT status, COUNT(*) FROM jobs GROUP BY status")).fetchall()
        jobs = {str(r[0]): int(r[1] or 0) for r in rows}
    except Exception:
        db.rollback()
        jobs = {}
    return {
        "cpu": cpu,
        "mem_pct": mem.percent,
        "mem_used_gb": round(mem.used / 1024**3, 2),
        "mem_total_gb": round(mem.total / 1024**3, 2),
        "disk_pct": disk.percent,
        "disk_used_gb": round(disk.used / 1024**3, 2),
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_label": Path(disk_path).drive or disk_path,
        "jobs": jobs,
    }


@router.get("/database")
def admin_database():
    from app.core.db_admin.database_service import DatabaseService

    tables = DatabaseService.get_all_tables_with_counts()
    return {"tables": tables, "total": len(tables)}


from app.platform.admin_api.mutations import router as mutations_router
from app.platform.admin_api.processes import router as processes_router

router.include_router(mutations_router)
router.include_router(processes_router)
