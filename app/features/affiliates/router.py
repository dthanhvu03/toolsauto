from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import logging
from app.core.database.core import get_db
from app.main_templates import templates
from app.features.affiliates.service import AffiliateService
from app.features.affiliates import lookup_queue as aff_lookup
from app.schemas.affiliates import (
    BatchImportRequest,
    AIGenerateRequest,
    ComplianceTextRequest,
)

router = APIRouter(prefix="/affiliates", tags=["affiliates"])
logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
def get_affiliates_page(request: Request):
    return templates.TemplateResponse("pages/app_affiliates.html", {
        "request": request,
        "active_tab": "affiliates",
        "csv_import_enabled": True,
        "ai_generate_enabled": True
    })

@router.get("/table", response_class=HTMLResponse)
def get_affiliates_table(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db)):
    res = AffiliateService.get_links_paged(db, q=q, page=page)
    return templates.TemplateResponse("fragments/affiliates_table.html", {
        "request": request,
        "links": res["links"],
        "total": res["total"],
        "page": res["page"],
        "total_pages": res["total_pages"],
        "q": q,
    })


@router.get("/lookup-panel", response_class=HTMLResponse)
def get_lookup_panel(request: Request, db: Session = Depends(get_db)):
    # Best-effort auto-resolve trước khi render (kho vừa thêm link mới).
    try:
        aff_lookup.process_pending_against_warehouse(db, limit=20)
    except Exception:
        pass
    items = aff_lookup.list_pending(limit=30)
    return templates.TemplateResponse("fragments/affiliate_lookup_panel.html", {
        "request": request,
        "items": items,
    })


@router.post("/lookup-resolve")
def lookup_resolve(
    fingerprint: str = Form(...),
    keyword: str = Form(...),
    url: str = Form(...),
    commission_rate: str = Form(""),
    comment_template: str = Form(""),
    db: Session = Depends(get_db),
):
    rate = None
    raw = (commission_rate or "").strip()
    if raw:
        try:
            rate = float(raw.replace(",", "."))
        except ValueError:
            return JSONResponse({"error": "Commission rate không hợp lệ."}, status_code=400)
    ok, err = aff_lookup.resolve_manual(
        db,
        fingerprint=fingerprint,
        keyword=keyword,
        url=url,
        comment_template=comment_template,
        commission_rate=rate,
    )
    if not ok:
        return JSONResponse(err, status_code=400)
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response


@router.post("/lookup-dismiss")
def lookup_dismiss(fingerprint: str = Form(...)):
    if not aff_lookup.dismiss(fingerprint):
        return JSONResponse({"error": "Không tìm thấy item."}, status_code=404)
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response

@router.post("/save")
def save_affiliate(
    request: Request,
    link_id: int = Form(0),
    keyword: str = Form(...),
    url: str = Form(...),
    comment_template: str = Form(...),
    commission_rate: str = Form(""),
    db: Session = Depends(get_db)
):
    rate = None
    raw = (commission_rate or "").strip()
    if raw:
        try:
            rate = float(raw.replace(",", "."))
        except ValueError:
            return JSONResponse({"error": "Commission rate không hợp lệ."}, status_code=400)
    success, error_data = AffiliateService.save_link(
        db, link_id, keyword, url, comment_template, commission_rate=rate
    )
    if not success:
        return JSONResponse(error_data, status_code=error_data.get("status_code", 400))
            
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response

@router.delete("/{link_id}")
def delete_affiliate(link_id: int, db: Session = Depends(get_db)):
    success = AffiliateService.delete_link(db, link_id)
    if not success:
        return JSONResponse({"error": "Không tìm thấy Link"}, status_code=404)
        
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "affiliatesChanged"
    return response

@router.post("/import-batch")
def import_batch(req: BatchImportRequest, db: Session = Depends(get_db)):
    return AffiliateService.import_batch(db, req.items)

@router.post("/ai-generate")
def ai_generate(req: AIGenerateRequest):
    res = AffiliateService.ai_generate(req.product_name, req.category, req.price, req.commission_rate)
    if "error" in res:
        return JSONResponse(res, status_code=res.get("status_code", 500))
    return res

@router.post("/compliance-check")
def compliance_check_preview(req: ComplianceTextRequest):
    return AffiliateService.compliance_check(req.text)
