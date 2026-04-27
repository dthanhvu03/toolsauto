from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import json
import logging
from app.database.core import get_db
from app.services.account import AccountService
from app.services.page_utils import PageUtils
from app.main_templates import templates
from app.services.affiliate_service import AffiliateService

router = APIRouter(prefix="/pages", tags=["pages"])
logger = logging.getLogger(__name__)

@router.get("/table", response_class=HTMLResponse)
def get_pages_table(request: Request, q: str = "", filter: str = "all", db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    pages_list = []
    
    for acc in accounts:
        acc_pages = PageUtils.build_page_view_models(acc, q=q, filter_str=filter)
        pages_list.extend(acc_pages)
            
    return templates.TemplateResponse("fragments/pages_table.html", {
        "request": request, 
        "pages": pages_list,
        "now": int(time.time())
    })


@router.post("/update", response_class=HTMLResponse)
def update_page(
    request: Request,
    account_id: int = Form(...),
    url: str = Form(...),
    is_active: str = Form("off"),
    niches: str = Form(""),
    competitors: str = Form(""),
    db: Session = Depends(get_db)
):
    raw_niches = (niches or "").strip()
    if raw_niches:
        n_list_to_check = [n.strip() for n in raw_niches.split(",") if n.strip()]
        for kw in n_list_to_check:
            comp_data = AffiliateService.compliance_check(kw)
            if comp_data.get("status") == "VIOLATION":
                msg = f"❌ Vi phạm chính sách tại từ khóa: '{kw}'"
                response = HTMLResponse(content="")
                response.headers["HX-Trigger"] = json.dumps({"showMessage": {"text": msg, "type": "error"}})
                return response

    active = is_active == "on"
    success = AccountService.update_page_config(db, account_id, url, active, niches, competitors)
    if not success:
        return HTMLResponse("<tr class='text-red-500'><td>Account not found</td></tr>")
    
    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "pagesChanged"
    return response


@router.post("/delete", response_class=HTMLResponse)
def delete_page(
    request: Request,
    account_id: int = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db)
):
    success = AccountService.delete_page_config(db, account_id, url)
    if not success:
        return HTMLResponse("<tr class='text-red-500'><td>Account not found</td></tr>")

    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "pagesChanged"
    return response
