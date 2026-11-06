"""API trang «Threads — Kéo khách» (PLAN-158). Đăng nhập do middleware chung của app lo."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.features.threads.growth import actions
from app.features.threads.growth import session as growth_session
from app.features.threads.growth.storage import STATUSES

router = APIRouter(prefix="/threads-growth/api", tags=["threads-growth"])


class ApproveBody(BaseModel):
    reply: Optional[str] = Field(default=None, max_length=500)


class SwitchBody(BaseModel):
    variant: Optional[str] = Field(default=None, pattern="^[AB]$")


class ToggleBody(BaseModel):
    enabled: bool


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return actions.overview(db)


@router.get("/posts")
def posts(status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)) -> dict:
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail="status không hợp lệ")
    return {"items": actions.runner().storage.list_posts(status, limit=limit)}


@router.post("/posts/{post_id}/approve")
def approve(post_id: int, body: ApproveBody) -> dict:
    try:
        return {"post": actions.approve(post_id, body.reply)}
    except actions.ActionError as exc:
        raise _bad(exc)


@router.post("/posts/{post_id}/reject")
def reject(post_id: int) -> dict:
    try:
        return {"post": actions.reject(post_id)}
    except actions.ActionError as exc:
        raise _bad(exc)


@router.post("/posts/{post_id}/switch")
def switch(post_id: int, body: SwitchBody) -> dict:
    try:
        return {"post": actions.switch(post_id, body.variant)}
    except actions.ActionError as exc:
        raise _bad(exc)


@router.post("/toggle")
def toggle(body: ToggleBody, db: Session = Depends(get_db)) -> dict:
    try:
        return {"enabled": actions.set_enabled(db, body.enabled, by="web")}
    except actions.ActionError as exc:
        raise _bad(exc)


@router.post("/login")
def login(db: Session = Depends(get_db)) -> dict:
    try:
        st = growth_session.start_login(db)
    except growth_session.SessionBusy as exc:
        raise _bad(exc)
    return {"login": {**st.__dict__, "ready": st.ready}}
