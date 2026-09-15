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
