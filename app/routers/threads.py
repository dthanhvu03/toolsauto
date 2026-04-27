from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.main_templates import templates
from app.services.threads_service import ThreadsService
import logging

router = APIRouter(prefix="/threads", tags=["Threads"])
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def threads_master_dashboard(request: Request, db: Session = Depends(get_db)):
    data = ThreadsService.get_dashboard_data(db)
    return templates.TemplateResponse("pages/app_threads.html", {
        "request": request,
        **data
    })

@router.get("/news-panel", response_class=HTMLResponse)
async def get_threads_news_panel(request: Request, db: Session = Depends(get_db)):
    data = ThreadsService.get_news_panel_data(db)
    return templates.TemplateResponse("fragments/threads_news_panel.html", {
        "request": request,
        **data
    })

@router.post("/toggle-auto", response_class=HTMLResponse)
async def toggle_threads_auto(request: Request, db: Session = Depends(get_db)):
    ThreadsService.toggle_auto_mode(db)
    return await get_threads_news_panel(request, db)

@router.post("/trigger-scrape", response_class=HTMLResponse)
async def trigger_news_scrape(request: Request, db: Session = Depends(get_db)):
    ThreadsService.trigger_news_scrape(db)
    return await get_threads_news_panel(request, db)

@router.post("/link-account", response_class=HTMLResponse)
async def link_account_to_threads(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    ThreadsService.link_account(db, account_id)
    return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

@router.post("/cancel-verify", response_class=HTMLResponse)
async def cancel_threads_verification(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    ThreadsService.cancel_verification(db, account_id)
    return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

@router.post("/retry-verify", response_class=HTMLResponse)
async def retry_threads_verification(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    ThreadsService.retry_verification(db, account_id)
    return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

@router.post("/unlink-account", response_class=HTMLResponse)
async def unlink_account_from_threads(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    ThreadsService.unlink_account(db, account_id)
    return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})
