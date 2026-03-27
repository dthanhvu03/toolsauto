from typing import List
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.services.account import AccountService

from app.main_templates import templates

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.get("/table", response_class=HTMLResponse)
def get_accounts_table(request: Request, q: str = "", db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    q = (q or "").strip().lower()
    if q:
        filtered = []
        for a in accounts:
            hay = " ".join([
                str(getattr(a, "name", "") or ""),
                str(getattr(a, "platform", "") or ""),
                str(getattr(a, "target_page", "") or ""),
                str(getattr(a, "target_pages", "") or ""),
                str(getattr(a, "niche_topics", "") or ""),
                str(getattr(a, "page_niches", "") or ""),
                str(getattr(a, "competitor_urls", "") or ""),
            ]).lower()
            if q in hay:
                filtered.append(a)
        accounts = filtered
    now = int(time.time())
    html_content = ""
    for account in accounts:
        html_content += templates.get_template("fragments/account_row.html").render(
            {"request": request, "account": account, "now": now}
        )
    return HTMLResponse(content=html_content)

@router.post("/create", response_class=HTMLResponse)
def create_account(
    request: Request,
    name: str = Form(...),
    platform: str = Form("facebook"),
    daily_limit: int = Form(3),
    cooldown_seconds: int = Form(1800),
    db: Session = Depends(get_db)
):
    try:
        AccountService.create_account(db, platform=platform, name=name, daily_limit=daily_limit, cooldown_seconds=cooldown_seconds)
    except Exception as e:
        pass 
    accounts = AccountService.list_accounts(db)
    
    return templates.TemplateResponse(
        "fragments/accounts_table.html", 
        {"request": request, "accounts": accounts, "now": int(time.time())}
    )

@router.post("/{account_id}/start-login", response_class=HTMLResponse)
def start_account_login(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.start_login(db, account_id)
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/confirm-login", response_class=HTMLResponse)
def confirm_account_login(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.confirm_login(db, account_id)
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/validate-session", response_class=HTMLResponse)
def validate_account_session(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.validate_session(db, account_id)
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/toggle", response_class=HTMLResponse)
def toggle_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        account = AccountService.toggle_account(db, account_id)
    except ValueError:
        account = AccountService.get_account(db, account_id)
        
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/update-limits", response_class=HTMLResponse)
def update_account_limits(
    account_id: int, 
    request: Request, 
    daily_limit: int = Form(...),
    cooldown_seconds: int = Form(...),
    niche_topics: str = Form(""),
    sleep_start_time: str = Form(""),
    sleep_end_time: str = Form(""),
    competitor_urls: str = Form(""),
    target_pages: List[str] = Form(None),
    page_niches: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        account = AccountService.update_limits(
            db, account_id, daily_limit, cooldown_seconds, 
            niche_topics=niche_topics,
            sleep_start_time=sleep_start_time,
            sleep_end_time=sleep_end_time,
            competitor_urls=competitor_urls,
            target_pages=target_pages or [],
            page_niches=page_niches or "",
        )
    except ValueError:
        account = AccountService.get_account(db, account_id)
        
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/reset-failures", response_class=HTMLResponse)
def reset_account_failures(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        account = AccountService.reset_failures(db, account_id)
    except ValueError:
        account = AccountService.get_account(db, account_id)
        
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.post("/{account_id}/delete", response_class=HTMLResponse)
def delete_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        AccountService.delete_account(db, account_id)
        return HTMLResponse("")
    except ValueError:
        account = AccountService.get_account(db, account_id)
        return templates.TemplateResponse(
            "fragments/account_row.html", 
            {"request": request, "account": account, "now": int(time.time())}
        )

@router.get("/{account_id}/pages", response_class=HTMLResponse)
def get_account_pages(account_id: int, request: Request, db: Session = Depends(get_db)):
    """HTMX endpoint to return <option> elements for a specific account's managed pages."""
    account = AccountService.get_account(db, account_id)
    html_content = '<option value="" selected>Cá nhân / Mặc định</option>'
    
    if account and account.managed_pages_list:
        html_content += '<optgroup label="Managed Pages">'
        for page in account.managed_pages_list:
            name = page.get("name", "Unknown Page")
            url = page.get("url", "")
            html_content += f'<option value="{url}">{name}</option>'
        html_content += '</optgroup>'
        
    return HTMLResponse(content=html_content)

@router.post("/{account_id}/sync-pages", response_class=HTMLResponse)
def sync_account_pages(account_id: int, request: Request, db: Session = Depends(get_db)):
    """Triggers the background scraper for this account and returns updated row."""
    import subprocess
    import os
    import threading
    
    account = AccountService.get_account(db, account_id)
    if not account:
        return HTMLResponse(status_code=404)
        
    def _run_scraper(acc_id):
        import sys
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "scrape_pages.py"))
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        # Use sys.executable so it always uses the correct venv Python, never bare 'python'
        python_bin = str(__import__("app.config", fromlist=["BASE_DIR"]).BASE_DIR / "venv" / "bin" / "python")
        subprocess.run([python_bin, script_path, "--account", str(acc_id)], env=env, cwd=str(__import__("app.config", fromlist=["BASE_DIR"]).BASE_DIR))
        
    # Run in background to avoid blocking the UI
    thread = threading.Thread(target=_run_scraper, args=(account_id,))
    thread.daemon = True
    thread.start()
    
    # Return immediately, the user will have to refresh or ping session to see results
    # Or we can just pretend it's updating
    return templates.TemplateResponse(
        "fragments/account_row.html", 
        {"request": request, "account": account, "now": int(time.time()), "sync_started": True}
    )
