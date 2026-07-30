"""UI + form endpoints for FB Professional weekly tasks tracker."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.features.fb_pro_tasks import service as fb_pro_tasks
from app.main_templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app/fb-pro-tasks", tags=["fb-pro-tasks"])


def _redirect_scope(scope_key: str = "", account_id: str = "", target_page: str = "") -> RedirectResponse:
    params: list[str] = []
    if scope_key:
        params.append(f"key={quote(scope_key, safe='')}")
    elif account_id:
        params.append(f"account_id={quote(str(account_id), safe='')}")
        if target_page:
            params.append(f"target_page={quote(target_page, safe='')}")
    qs = ("?" + "&".join(params)) if params else ""
    return RedirectResponse(url=f"/app/fb-pro-tasks/{qs}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def view_fb_pro_tasks(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Query(""),
    account_id: str = Query(""),
    target_page: str = Query(""),
):
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
    return templates.TemplateResponse(
        "pages/app_fb_pro_tasks.html",
        {
            "request": request,
            "dash": dash,
            "active_tab": "fb_pro_tasks",
        },
    )


@router.post("/save")
def save_fb_pro_tasks(
    db: Session = Depends(get_db),
    scope_key: str = Form(""),
    account_id: str = Form(""),
    target_page: str = Form(""),
    interactions: str = Form(""),
    posts_override: str = Form(""),
    reels_override: str = Form(""),
    target_posts: str = Form(""),
    target_reels: str = Form(""),
    target_interactions: str = Form(""),
    notes: str = Form(""),
    week_start: str = Form(""),
    week_end: str = Form(""),
    clear_overrides: str = Form(""),
):
    def _opt_int(raw: str) -> int | None:
        raw = (raw or "").strip()
        if raw == "":
            return None
        return int(raw)

    payload: dict = {
        "scope_key": (scope_key or "").strip() or None,
        "account_id": (account_id or "").strip() or None,
        "target_page": (target_page or "").strip() or None,
        "posts_override": posts_override,
        "reels_override": reels_override,
        "notes": notes,
        "week_start": (week_start or "").strip() or None,
        "week_end": (week_end or "").strip() or None,
        "clear_overrides": str(clear_overrides).lower() in {"1", "true", "on", "yes"},
    }
    if (interactions or "").strip() != "":
        payload["interactions"] = _opt_int(interactions)
    tp = _opt_int(target_posts)
    tr = _opt_int(target_reels)
    ti = _opt_int(target_interactions)
    if tp is not None:
        payload["target_posts"] = tp
    if tr is not None:
        payload["target_reels"] = tr
    if ti is not None:
        payload["target_interactions"] = ti

    fb_pro_tasks.update_from_form(payload, db)
    return _redirect_scope(scope_key, account_id, target_page)


@router.post("/reset-week")
def reset_week(
    db: Session = Depends(get_db),
    scope_key: str = Form(""),
    account_id: str = Form(""),
    target_page: str = Form(""),
):
    fb_pro_tasks.reset_week_now(db, key=(scope_key or "").strip() or None)
    return _redirect_scope(scope_key, account_id, target_page)


@router.post("/refresh")
def refresh_counts(
    scope_key: str = Form(""),
    account_id: str = Form(""),
    target_page: str = Form(""),
):
    return _redirect_scope(scope_key, account_id, target_page)
