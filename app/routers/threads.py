from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import RuntimeSetting, Job, NewsArticle, Account
from app.main_templates import templates # Use the shared templates instance
import time

router = APIRouter(prefix="/threads", tags=["Threads"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_class=HTMLResponse)
async def threads_master_dashboard(request: Request, db: Session = Depends(get_db)):
    # Summary stats
    stats = {
        "pending": db.query(Job).filter(Job.platform == "threads", Job.status == "PENDING").count(),
        "success": db.query(Job).filter(Job.platform == "threads", Job.status == "COMPLETED").count(),
        "failed": db.query(Job).filter(Job.platform == "threads", Job.status == "FAILED").count(),
    }
    
    latest_articles = db.query(NewsArticle).order_by(NewsArticle.id.desc()).limit(10).all()
    threads_jobs = db.query(Job).filter(Job.platform == "threads").order_by(Job.id.desc()).limit(10).all()
    
    # Get all FB accounts and mark which ones are linked to Threads
    all_accounts = db.query(Account).filter(Account.is_active == True).all()
    linked_accounts = []
    available_accounts = []
    for acc in all_accounts:
        if acc.platform and "threads" in acc.platform:
            linked_accounts.append(acc)
        else:
            available_accounts.append(acc)
    
    return templates.TemplateResponse("pages/app_threads.html", {
        "request": request,
        "stats": stats,
        "articles": latest_articles,
        "jobs": threads_jobs,
        "linked_accounts": linked_accounts,
        "available_accounts": available_accounts,
    })

@router.get("/news-panel", response_class=HTMLResponse)
async def get_threads_news_panel(request: Request, db: Session = Depends(get_db)):
    auto_mode_setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_AUTO_MODE").first()
    auto_mode = (auto_mode_setting.value.lower() == "true") if auto_mode_setting else False
    
    total_articles = db.query(NewsArticle).count()
    new_articles = db.query(NewsArticle).filter(NewsArticle.status == "NEW").count()
    
    latest_jobs = db.query(Job).filter(Job.platform == "threads").order_by(Job.id.desc()).limit(3).all()
    
    return templates.TemplateResponse("fragments/threads_news_panel.html", {
        "request": request,
        "auto_mode": auto_mode,
        "total_articles": total_articles,
        "new_articles": new_articles,
        "latest_jobs": latest_jobs
    })

@router.post("/toggle-auto", response_class=HTMLResponse)
async def toggle_threads_auto(request: Request, db: Session = Depends(get_db)):
    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_AUTO_MODE").first()
    if setting:
        current_val = setting.value.lower() == "true"
        new_val = not current_val
        setting.value = "true" if new_val else "false"
        db.commit()
    
    return await get_threads_news_panel(request, db)

@router.post("/trigger-scrape", response_class=HTMLResponse)
async def trigger_news_scrape(request: Request, db: Session = Depends(get_db)):
    from app.services.news_scraper import NewsScraper
    scraper = NewsScraper()
    scraper.scrape_all()
    
    # Also trigger processing to create jobs
    from app.services.threads_news import ThreadsNewsService
    service = ThreadsNewsService()
    service.process_news_to_threads()
    
    return await get_threads_news_panel(request, db)

@router.post("/link-account", response_class=HTMLResponse)
async def link_account_to_threads(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    """Link an existing Facebook account profile to Threads."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        # Append 'threads' to the platform field (e.g. "facebook" -> "facebook,threads")
        platforms = set((account.platform or "").split(","))
        platforms.discard("")
        platforms.add("threads")
        account.platform = ",".join(sorted(platforms))
        db.commit()
    
    # Return full page redirect via HTMX
    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Redirect": "/threads"}
    )

@router.post("/unlink-account", response_class=HTMLResponse)
async def unlink_account_from_threads(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    """Remove Threads capability from an account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if account:
        platforms = set((account.platform or "").split(","))
        platforms.discard("threads")
        platforms.discard("")
        account.platform = ",".join(sorted(platforms)) or "facebook"
        db.commit()
    
    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Redirect": "/threads"}
    )
