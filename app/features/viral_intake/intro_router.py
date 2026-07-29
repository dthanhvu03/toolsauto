"""Brand intro upload UI API — PLAN-044 Phase 2."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.account import AccountService
from app.core.database.core import get_db
from app.core.page_utils import PageUtils
from app.features.viral_intake import intro_service
from app.main_templates import templates
from app.utils.htmx import htmx_toast_response

router = APIRouter(prefix="/viral/intros", tags=["viral-intros"])
logger = logging.getLogger(__name__)


def _panel_context(db: Session, account_id: int, request: Request) -> dict:
    account = AccountService.get_account(db, account_id)
    if not account:
        return {}
    pages = PageUtils.build_page_view_models(account, q="", filter_str="all")
    page_dicts = [
        {
            "url": p.get("url") if isinstance(p, dict) else getattr(p, "url", ""),
            "name": p.get("name") if isinstance(p, dict) else getattr(p, "name", ""),
            "niches": p.get("niches") if isinstance(p, dict) else getattr(p, "niches", ""),
        }
        for p in pages
    ]
    bundle = intro_service.status_bundle(account_id=account_id, pages=page_dicts)
    return {
        "request": request,
        "account": account,
        "intro": bundle,
        "pages": pages,
    }


@router.get("/panel/{account_id}", response_class=HTMLResponse)
def intro_panel(account_id: int, request: Request, db: Session = Depends(get_db)):
    ctx = _panel_context(db, account_id, request)
    if not ctx:
        return HTMLResponse("<p class='text-sm text-[var(--color-danger)]'>Không tìm thấy account.</p>", status_code=404)
    return templates.TemplateResponse("fragments/intro_upload_panel.html", ctx)


@router.post("/toggle", response_class=HTMLResponse)
def toggle_intro(
    request: Request,
    account_id: int = Form(...),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    on = enabled in ("on", "true", "1", "yes")
    intro_service.set_intro_enabled(on)
    ctx = _panel_context(db, account_id, request)
    if not ctx:
        return htmx_toast_response("Account không tồn tại", type="error")
    html = templates.get_template("fragments/intro_upload_panel.html").render(ctx)
    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = (
        '{"showMessage":{"msg":"Đã %s ghép intro brand","type":"success"}}'
        % ("bật" if on else "tắt")
    )
    return resp


@router.post("/upload", response_class=HTMLResponse)
async def upload_intro(
    request: Request,
    account_id: int = Form(...),
    scope: str = Form(...),
    page_url: str = Form(""),
    niche: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    try:
        intro_service.save_intro_upload(
            scope=scope,
            data=raw,
            filename=file.filename or "intro.mp4",
            account_id=account_id,
            page_url=page_url or None,
            niche=niche or None,
        )
    except ValueError as e:
        return htmx_toast_response(str(e), type="error")
    except Exception as e:
        logger.exception("intro upload failed")
        return htmx_toast_response(f"Upload lỗi: {e}", type="error")

    ctx = _panel_context(db, account_id, request)
    if not ctx:
        return htmx_toast_response("Đã lưu intro", type="success")
    html = templates.get_template("fragments/intro_upload_panel.html").render(ctx)
    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = (
        '{"showMessage":{"msg":"Đã upload intro (%s) — sẽ ghép ≤3s khi reup","type":"success"}}'
        % scope
    )
    return resp


@router.post("/delete", response_class=HTMLResponse)
def delete_intro(
    request: Request,
    account_id: int = Form(...),
    scope: str = Form(...),
    page_url: str = Form(""),
    niche: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        intro_service.delete_intro(
            scope=scope,
            account_id=account_id,
            page_url=page_url or None,
            niche=niche or None,
        )
    except ValueError as e:
        return htmx_toast_response(str(e), type="error")

    ctx = _panel_context(db, account_id, request)
    if not ctx:
        return htmx_toast_response("Đã xóa intro", type="success")
    html = templates.get_template("fragments/intro_upload_panel.html").render(ctx)
    resp = HTMLResponse(html)
    resp.headers["HX-Trigger"] = '{"showMessage":{"msg":"Đã xóa intro","type":"success"}}'
    return resp
