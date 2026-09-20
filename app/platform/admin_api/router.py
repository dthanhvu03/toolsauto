"""Thin JSON API for React admin SPA — wraps existing DashboardService / JobService."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.account import AccountService
from app.core.database.core import get_db
from app.core.queue.job import JobService
from app.platform.dashboard_service import DashboardService

router = APIRouter(prefix="/api/admin", tags=["admin-api"])


def _account_row(a) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "platform": a.platform,
        "is_active": bool(a.is_active),
        "login_status": a.login_status,
        "daily_limit": a.daily_limit,
        "cooldown_seconds": a.cooldown_seconds,
        "target_page": a.target_page,
        "consecutive_failures": getattr(a, "consecutive_failures", 0) or 0,
    }


def _job_row(j) -> dict[str, Any]:
    acc = getattr(j, "account", None)
    return {
        "id": j.id,
        "status": j.status,
        "platform": j.platform,
        "job_type": getattr(j, "job_type", None),
        "account_id": j.account_id,
        "account_name": acc.name if acc else None,
        "target_page": j.target_page,
        "caption": (j.caption or "")[:160],
        "post_url": j.post_url,
        "schedule_ts": j.schedule_ts,
        "finished_at": j.finished_at,
        "error_message": (getattr(j, "error_message", None) or "")[:200],
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


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db)):
    data = DashboardService.get_overview_data(db)
    state = data["state"]
    queue = DashboardService.get_queue_stats(db)
    chart = DashboardService.get_chart_data(db)
    accounts = [_account_row(a) for a in data["accounts"]]
    return {
        "accounts": accounts,
        "accounts_count": len(accounts),
        "accounts_active": sum(1 for a in accounts if a["is_active"]),
        "state": {
            "worker_status": state.worker_status,
            "heartbeat_at": state.heartbeat_at,
            "current_job_id": state.current_job_id,
            "safe_mode": bool(getattr(state, "safe_mode", False)),
            "engagement_status": getattr(state, "engagement_status", None),
        },
        "queue": queue,
        "chart": chart,
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
    return {
        "jobs": [_job_row(j) for j in raw["jobs"]],
        "total": raw["total"],
        "total_pages": raw["total_pages"],
        "page": raw["page"],
        "status": status,
        "platform": platform,
        "q": q,
    }


@router.get("/accounts")
def admin_accounts(
    db: Session = Depends(get_db),
    q: str = Query(""),
    platform: str = Query(""),
):
    accounts = AccountService.list_accounts(db, skip=0, limit=200)
    qn = (q or "").strip().lower()
    pf = (platform or "").strip().lower()
    rows = []
    for a in accounts:
        if pf and pf != "all" and (a.platform or "").lower() != pf:
            continue
        if qn and qn not in (a.name or "").lower() and qn not in (a.platform or "").lower():
            continue
        rows.append(_account_row(a))
    return {"accounts": rows, "total": len(rows)}


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


def _affiliate_row(link) -> dict[str, Any]:
    return {
        "id": link.id,
        "keyword": link.keyword,
        "url": link.url,
        "comment_template": (link.comment_template or "")[:200],
        "commission_rate": link.commission_rate,
        "ai_status": link.ai_status,
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


def _flatten_tiktok_groups(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    page_index = ctx.get("page_index") or {}
    rows: list[dict[str, Any]] = []
    for tp, by_acc in (ctx.get("competitor_groups") or {}).items():
        meta = page_index.get(tp) or {}
        name = meta.get("name") if tp != "_unassigned" else None
        for acc_name, urls in (by_acc or {}).items():
            for url in urls:
                rows.append(
                    {
                        "account_name": acc_name,
                        "target_page": None if tp == "_unassigned" else tp,
                        "target_name": name,
                        "url": url,
                    }
                )
    return rows


@router.get("/affiliates")
def admin_affiliates(
    db: Session = Depends(get_db),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    from app.features.affiliates.service import AffiliateService

    raw = AffiliateService.get_links_paged(db, q=q, page=page)
    return {
        "links": [_affiliate_row(x) for x in raw["links"]],
        "total": raw["total"],
        "page": raw["page"],
        "total_pages": raw["total_pages"],
        "q": q,
    }


@router.get("/viral-sources")
def admin_viral_sources(db: Session = Depends(get_db)):
    from app.features.viral_intake.sources import SourceService

    try:
        sources = SourceService.list_sources(db)
    except Exception:
        sources = []
    return {"items": [_viral_source_row(s) for s in sources], "total": len(sources)}


@router.get("/tiktok-links")
def admin_tiktok_links(
    db: Session = Depends(get_db),
    q: str = Query(""),
):
    ctx = AccountService.build_tiktok_links_context_data(db, {"q": q})
    items = _flatten_tiktok_groups(ctx)
    return {
        "items": items,
        "total": ctx.get("competitor_total") or len(items),
        "q": q,
    }


def _fb_pro_task_row(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": t.get("key"),
        "label": t.get("label"),
        "current": t.get("current") or 0,
        "target": t.get("target") or 0,
        "source": t.get("source") or "auto",
        "auto": t.get("auto"),
        "pct": t.get("pct") or 0,
        "remaining": t.get("remaining") or 0,
    }


def _fb_pro_hint_row(j: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": j.get("id"),
        "status": j.get("status"),
        "target_page": j.get("target_page") or "",
        "caption": j.get("caption") or "",
        "media_name": j.get("media_name") or "",
        "is_video": bool(j.get("is_video")),
    }


def _fb_pro_option_row(o: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": o.get("key") or "",
        "label": o.get("label") or o.get("key") or "",
        "account_id": o.get("account_id"),
        "target_page": o.get("target_page") or "",
    }


@router.get("/fb-pro-tasks")
def admin_fb_pro_tasks(
    db: Session = Depends(get_db),
    key: str = Query(""),
    account_id: str = Query(""),
    target_page: str = Query(""),
):
    from app.features.fb_pro_tasks import service as fb_pro_tasks

    acc: int | None = None
    if (account_id or "").strip():
        try:
            acc = int(account_id)
        except ValueError:
            acc = None
    dash = fb_pro_tasks.build_dashboard(
        db,
        account_id=acc,
        target_page=(target_page or "").strip() or None,
        key=(key or "").strip() or None,
    )
    cfg = dash.get("config") or {}
    return {
        "scope_key": dash.get("scope_key") or "",
        "scope_label": dash.get("scope_label") or "",
        "account_id": dash.get("account_id"),
        "account_name": dash.get("account_name") or "",
        "target_page": dash.get("target_page") or "",
        "page_slug": dash.get("page_slug") or "",
        "scope_options": [_fb_pro_option_row(o) for o in (dash.get("scope_options") or [])],
        "week_start": dash.get("week_start") or "",
        "week_end": dash.get("week_end") or "",
        "week_label": dash.get("week_label") or "",
        "days_left": dash.get("days_left") or 0,
        "overall_pct": dash.get("overall_pct") or 0,
        "tasks": [_fb_pro_task_row(t) for t in (dash.get("tasks") or [])],
        "auto": dash.get("auto") or {"posts": 0, "reels": 0},
        "meta_url": dash.get("meta_url") or "",
        "queue_hints": [_fb_pro_hint_row(j) for j in (dash.get("queue_hints") or [])],
        "notes": (cfg.get("notes") or "")[:500],
        "updated_at": dash.get("updated_at") or 0,
    }


def _threads_article_row(a) -> dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "source_name": a.source_name,
        "status": a.status,
        "published_at": a.published_at,
    }


@router.get("/threads")
def admin_threads(db: Session = Depends(get_db)):
    from app.features.threads.dashboard import ThreadsService

    raw = ThreadsService.get_dashboard_data(db)
    failed = raw.get("failed_verifications") or {}
    return {
        "stats": raw.get("stats") or {"pending": 0, "success": 0, "failed": 0},
        "articles": [_threads_article_row(a) for a in (raw.get("articles") or [])],
        "jobs": [_job_row(j) for j in (raw.get("jobs") or [])],
        "linked_accounts": [_account_row(a) for a in (raw.get("linked_accounts") or [])],
        "verifying_accounts": [_account_row(a) for a in (raw.get("verifying_accounts") or [])],
        "available_accounts": [_account_row(a) for a in (raw.get("available_accounts") or [])],
        "failed_verifications": {str(k): v for k, v in failed.items()},
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

router.include_router(mutations_router)
