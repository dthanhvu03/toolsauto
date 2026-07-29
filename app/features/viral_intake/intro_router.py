"""Brand intro/outro/hook upload UI API — PLAN-044/045."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.account import AccountService
from app.core.database.core import get_db
from app.core.page_utils import PageUtils
from app.features.viral_intake import intro_service
from app.main_templates import templates

router = APIRouter(prefix="/viral/intros", tags=["viral-intros"])
logger = logging.getLogger(__name__)


def _panel_context(
    db: Session,
    account_id: int,
    request: Request,
    flash: str | None = None,
    flash_type: str = "success",
) -> dict:
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
        "flash": flash,
        "flash_type": flash_type,
    }


def _render_panel(ctx: dict, toast_msg: str | None = None, toast_type: str = "success") -> HTMLResponse:
    html = templates.get_template("fragments/intro_upload_panel.html").render(ctx)
    resp = HTMLResponse(html)
    if toast_msg:
        resp.headers["HX-Trigger"] = json.dumps(
            {"showMessage": {"msg": toast_msg, "type": toast_type}}
        )
    return resp


def _panel_or_toast(
    db: Session,
    account_id: int,
    request: Request,
    *,
    flash: str,
    flash_type: str = "success",
) -> HTMLResponse:
    ctx = _panel_context(db, account_id, request, flash=flash, flash_type=flash_type)
    if not ctx:
        # Still return a tiny HTML so hx-swap doesn't wipe the panel silently
        body = (
            f"<div id='intro-upload-panel' class='p-4 text-sm "
            f"{'text-[var(--color-lichen)]' if flash_type=='success' else 'text-[var(--color-danger)]'}'>"
            f"{flash}</div>"
        )
        resp = HTMLResponse(body)
        resp.headers["HX-Trigger"] = json.dumps(
            {"showMessage": {"msg": flash, "type": flash_type}}
        )
        return resp
    return _render_panel(ctx, toast_msg=flash, toast_type=flash_type)


@router.get("/panel/{account_id}", response_class=HTMLResponse)
def intro_panel(account_id: int, request: Request, db: Session = Depends(get_db)):
    ctx = _panel_context(db, account_id, request)
    if not ctx:
        return HTMLResponse(
            "<p class='text-sm text-[var(--color-danger)]'>Không tìm thấy account.</p>",
            status_code=404,
        )
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
    msg = f"Đã {'BẬT' if on else 'TẮT'} ghép intro brand"
    return _panel_or_toast(db, account_id, request, flash=msg)


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
    name = file.filename or "intro.mp4"
    try:
        intro_service.save_intro_upload(
            scope=scope,
            data=raw,
            filename=name,
            account_id=account_id,
            page_url=page_url or None,
            niche=niche or None,
        )
    except ValueError as e:
        return _panel_or_toast(db, account_id, request, flash=str(e), flash_type="error")
    except Exception as e:
        logger.exception("intro upload failed")
        return _panel_or_toast(
            db, account_id, request, flash=f"Upload lỗi: {e}", flash_type="error"
        )

    size_mb = round(len(raw) / (1024 * 1024), 2)
    from app.features.viral_intake.reup_config import load_reup_config

    pool_max = int(load_reup_config().get("intro_pool_max") or 8)
    msg = f"✓ Thêm intro vào pool — {name} ({size_mb}MB, {scope}). Tối đa {pool_max} clip/scope; reup sẽ random."
    return _panel_or_toast(db, account_id, request, flash=msg)


@router.post("/delete-file", response_class=HTMLResponse)
def delete_intro_file_route(
    request: Request,
    account_id: int = Form(...),
    file_path: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        intro_service.delete_intro_file(rel_or_abs=file_path)
    except ValueError as e:
        return _panel_or_toast(db, account_id, request, flash=str(e), flash_type="error")
    return _panel_or_toast(db, account_id, request, flash="Đã xóa 1 clip khỏi pool")


@router.post("/toggle-outro", response_class=HTMLResponse)
def toggle_outro(
    request: Request,
    account_id: int = Form(...),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    on = enabled in ("on", "true", "1", "yes")
    intro_service.set_outro_enabled(on)
    return _panel_or_toast(
        db, account_id, request, flash=f"Đã {'BẬT' if on else 'TẮT'} ghép outro brand"
    )


@router.post("/toggle-hook", response_class=HTMLResponse)
def toggle_hook(
    request: Request,
    account_id: int = Form(...),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    on = enabled in ("on", "true", "1", "yes")
    intro_service.set_hook_enabled(on)
    return _panel_or_toast(
        db, account_id, request, flash=f"Đã {'BẬT' if on else 'TẮT'} hook text"
    )


@router.post("/toggle-reels-1080", response_class=HTMLResponse)
def toggle_reels_1080(
    request: Request,
    account_id: int = Form(...),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    on = enabled in ("on", "true", "1", "yes")
    intro_service.set_reels_1080_enabled(on)
    return _panel_or_toast(
        db,
        account_id,
        request,
        flash=f"Đã {'BẬT' if on else 'TẮT'} chuẩn hóa Reels 1080×1920",
    )


@router.post("/upload-outro", response_class=HTMLResponse)
async def upload_outro(
    request: Request,
    account_id: int = Form(...),
    scope: str = Form(...),
    page_url: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    name = file.filename or "outro.mp4"
    try:
        intro_service.save_outro_upload(
            scope=scope,
            data=raw,
            filename=name,
            account_id=account_id,
            page_url=page_url or None,
        )
    except ValueError as e:
        return _panel_or_toast(db, account_id, request, flash=str(e), flash_type="error")
    except Exception as e:
        logger.exception("outro upload failed")
        return _panel_or_toast(
            db, account_id, request, flash=f"Upload outro lỗi: {e}", flash_type="error"
        )

    size_mb = round(len(raw) / (1024 * 1024), 2)
    msg = f"✓ Upload outro thành công — {name} ({size_mb}MB, scope={scope})"
    return _panel_or_toast(db, account_id, request, flash=msg)


@router.post("/delete-outro", response_class=HTMLResponse)
def delete_outro_route(
    request: Request,
    account_id: int = Form(...),
    scope: str = Form(...),
    page_url: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        intro_service.delete_outro(
            scope=scope,
            account_id=account_id,
            page_url=page_url or None,
        )
    except ValueError as e:
        return _panel_or_toast(db, account_id, request, flash=str(e), flash_type="error")
    return _panel_or_toast(db, account_id, request, flash="Đã xóa outro")


@router.post("/save-hook", response_class=HTMLResponse)
def save_hook(
    request: Request,
    account_id: int = Form(...),
    scope: str = Form(...),
    text: str = Form(""),
    page_url: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        intro_service.save_hook_text(
            scope=scope,
            text=text,
            account_id=account_id,
            page_url=page_url or None,
        )
    except ValueError as e:
        return _panel_or_toast(db, account_id, request, flash=str(e), flash_type="error")
    preview = (text or "").strip()
    msg = f"✓ Đã lưu hook text" + (f": “{preview[:40]}”" if preview else " (đã xóa)")
    return _panel_or_toast(db, account_id, request, flash=msg)
