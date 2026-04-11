from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import json
import logging
from app.database.core import get_db
from app.database.models import Account
from app.services.account import AccountService
from app.main_templates import templates
from app.services.fb_compliance import compliance_checker, Severity

router = APIRouter(prefix="/pages", tags=["pages"])
logger = logging.getLogger(__name__)

@router.get("/table", response_class=HTMLResponse)
def get_pages_table(request: Request, q: str = "", filter: str = "all", db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    q = (q or "").strip().lower()
    filter = (filter or "all").lower()
    
    pages_list = []
    
    for acc in accounts:
        managed = acc.managed_pages_list or []
        target_urls = set(acc.target_pages_list or [])
        page_niches = acc.page_niches_map or {}
        competitors = acc.competitor_urls_grouped or {}
        
        for p in managed:
            url = p.get('url', '')
            name = p.get('name', 'Unknown')
            if not url:
                continue
            
            is_active = url in target_urls
            
            # --- Filter Logic ---
            if filter == "active" and not is_active:
                continue
            if filter == "paused" and is_active:
                continue
            
            niches = ", ".join(page_niches.get(url, []))
            comps = competitors.get(url, "")
            
            # Allow searching by page name, url, or niche
            haystack = f"{name} {url} {niches} {acc.name}".lower()
            if q and q not in haystack:
                continue
                
            pages_list.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "platform": acc.platform,
                "url": url,
                "name": name,
                "is_active": is_active,
                "niches": niches,
                "competitors": comps
            })
            
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
    is_active: str = Form("off"), # Checkbox returns 'on' if checked, else omitted
    niches: str = Form(""),
    competitors: str = Form(""),
    db: Session = Depends(get_db)
):
    """
    Updates a specific page's configuration within the parent Account's JSON fields.
    Will only be called from HTMX. Returns the updated row.
    """
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        return HTMLResponse("<tr class='text-red-500'><td>Account not found</td></tr>")
    
    # [Compliance Gate] Check niches (comma-separated list of keywords)
    # User Note: Check each keyword individually. Report field type.
    raw_niches = (niches or "").strip()
    if raw_niches:
        logger.info(f"[Compliance Check] Target field: niches (type: CommaSeparatedKeywords)")
        n_list_to_check = [n.strip() for n in raw_niches.split(",") if n.strip()]
        for kw in n_list_to_check:
            comp = compliance_checker.check(kw)
            if comp.status == Severity.VIOLATION:
                msg = f"❌ Vi phạm chính sách tại từ khóa: '{kw}'"
                # Return an HX-Trigger to show original data or a toast error
                response = HTMLResponse(content="")
                response.headers["HX-Trigger"] = json.dumps({"showMessage": {"text": msg, "type": "error"}})
                return response

    # 1. Update target_pages_list
    target_urls = set(acc.target_pages_list or [])
    active = is_active == "on"
    if active:
        target_urls.add(url)
    elif url in target_urls:
        target_urls.remove(url)
    acc.target_pages_list = list(target_urls)
    
    # 2. Update page_niches_map
    current_niches = acc.page_niches_map or {}
    n_list = [n.strip() for n in raw_niches.split(",") if n.strip()]
    if n_list:
        current_niches[url] = n_list
    elif url in current_niches:
        del current_niches[url]
    acc.page_niches_map = current_niches
    
    # 3. Update competitor_urls_grouped
    comp_urls = [c.strip() for c in competitors.replace("\r\n", "\n").split("\n") if c.strip()]
    # Load raw JSON manually to update
    try:
        raw_comps = json.loads(acc.competitor_urls or "[]") if acc.competitor_urls else []
        if not isinstance(raw_comps, list):
            raw_comps = []
    except Exception:
        raw_comps = []
        
    # Filter out existing comps for this exact page
    new_comps = [c for c in raw_comps if not (isinstance(c, dict) and c.get('target_page') == url)]
    # Add the new ones
    for c_url in comp_urls:
        new_comps.append({"target_page": url, "url": c_url})
        
    acc.competitor_urls = json.dumps(new_comps, ensure_ascii=False) if new_comps else None
    
    db.commit()
    
    # We don't render single row replacement. We just trigger a full table reload using HX-Trigger.
    # So we return empty success but with an HX-Trigger header.
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
    """
    Removes a target page from an account's target_pages_list.
    Also cleans up associated niches.
    """
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        return HTMLResponse("<tr class='text-red-500'><td>Account not found</td></tr>")

    # 1. Remove from target_pages_list
    target_urls = set(acc.target_pages_list or [])
    if url in target_urls:
        target_urls.remove(url)
    acc.target_pages_list = list(target_urls)

    # 2. Cleanup niches for this page
    page_niches = acc.page_niches_map or {}
    if url in page_niches:
        del page_niches[url]
    acc.page_niches_map = page_niches

    db.commit()

    response = HTMLResponse(content="")
    response.headers["HX-Trigger"] = "pagesChanged"
    return response
