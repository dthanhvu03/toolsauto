from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.core import SessionLocal
from app.database.models import RuntimeSetting, Job, NewsArticle, Account
from app.main_templates import templates # Use the shared templates instance
from app.constants import JobType, JobStatus
import time
import logging

router = APIRouter(prefix="/threads", tags=["Threads"])
logger = logging.getLogger(__name__)


def _platform_tokens(platform: str | None) -> set[str]:
    return {token.strip().lower() for token in (platform or "").split(",") if token.strip()}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _classify_accounts(db: Session, all_accounts):
    """
    Classify Facebook accounts into 3 buckets for Threads connection UI:
    - linked_accounts: already have "threads" in platform (verified)
    - verifying_accounts: have a PENDING/RUNNING VERIFY_THREADS job
    - failed_verifications: dict of account_id -> error message (latest FAILED job)
    - available_accounts: FB accounts not linked and not verifying
    """
    linked_accounts = []
    verifying_accounts = []
    failed_verifications = {}
    available_accounts = []

    for acc in all_accounts:
        platforms = _platform_tokens(acc.platform)
        if "facebook" not in platforms:
            continue

        if "threads" in platforms:
            linked_accounts.append(acc)
            continue

        # Check for active verification jobs
        active_verify = db.query(Job).filter(
            Job.account_id == acc.id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        ).first()

        if active_verify:
            verifying_accounts.append(acc)
            continue

        # Check for most recent failed verification
        failed_verify = db.query(Job).filter(
            Job.account_id == acc.id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status == JobStatus.FAILED
        ).order_by(Job.id.desc()).first()

        if failed_verify:
            failed_verifications[acc.id] = failed_verify.last_error or "Xac minh that bai"
            available_accounts.append(acc)
            continue

        available_accounts.append(acc)

    return linked_accounts, verifying_accounts, failed_verifications, available_accounts


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
    
    # Get all FB accounts and classify for Threads connection UI
    all_accounts = db.query(Account).filter(Account.is_active == True).order_by(Account.id.asc()).all()
    linked_accounts, verifying_accounts, failed_verifications, available_accounts = _classify_accounts(db, all_accounts)
    
    return templates.TemplateResponse("pages/app_threads.html", {
        "request": request,
        "stats": stats,
        "articles": latest_articles,
        "jobs": threads_jobs,
        "linked_accounts": linked_accounts,
        "verifying_accounts": verifying_accounts,
        "failed_verifications": failed_verifications,
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
    from app.database.models import RuntimeSetting
    setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_AUTO_MODE").first()
    if setting:
        current_val = setting.value.lower() == "true"
        new_val = not current_val
        setting.value = "true" if new_val else "false"
    else:
        setting = RuntimeSetting(key="THREADS_AUTO_MODE", value="true")
        db.add(setting)
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
    """
    Start Threads verification for an account.
    Instead of immediately adding "threads" to the platform field,
    creates a VERIFY_THREADS job that a background worker will process
    using Playwright to confirm the account is actually logged in.
    """
    account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    if not account:
        return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

    platforms = _platform_tokens(account.platform)
    if "facebook" not in platforms:
        return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

    # Check if there's already an active verification job
    existing = db.query(Job).filter(
        Job.account_id == account_id,
        Job.job_type == JobType.VERIFY_THREADS,
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    ).first()

    if not existing:
        # Cancel any previous failed verify jobs for this account
        old_failed = db.query(Job).filter(
            Job.account_id == account_id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status == JobStatus.FAILED
        ).all()
        for j in old_failed:
            j.status = JobStatus.CANCELLED
        
        # Create new verification job
        verify_job = Job(
            platform="threads",
            account_id=account_id,
            job_type=JobType.VERIFY_THREADS,
            status=JobStatus.PENDING,
            caption="[VERIFY] Threads login verification",
            schedule_ts=int(time.time()),
        )
        db.add(verify_job)
        db.commit()
        logger.info("Created VERIFY_THREADS job #%s for account %s (%s)", verify_job.id, account.name, account_id)
    
    # Return full page redirect via HTMX
    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Redirect": "/threads"}
    )

@router.post("/cancel-verify", response_class=HTMLResponse)
async def cancel_threads_verification(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    """Cancel any pending/running VERIFY_THREADS jobs for an account."""
    active_jobs = db.query(Job).filter(
        Job.account_id == account_id,
        Job.job_type == JobType.VERIFY_THREADS,
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
    ).all()

    for j in active_jobs:
        j.status = JobStatus.CANCELLED
        j.last_error = "Cancelled by user"
        j.finished_at = int(time.time())

    if active_jobs:
        db.commit()
        logger.info("Cancelled %d VERIFY_THREADS job(s) for account_id %s", len(active_jobs), account_id)

    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Redirect": "/threads"}
    )

@router.post("/retry-verify", response_class=HTMLResponse)
async def retry_threads_verification(request: Request, account_id: int = Form(...), db: Session = Depends(get_db)):
    """Retry a failed Threads verification by creating a new VERIFY_THREADS job."""
    account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    if not account:
        return HTMLResponse(content="", status_code=200, headers={"HX-Redirect": "/threads"})

    # Cancel old failed jobs
    old_jobs = db.query(Job).filter(
        Job.account_id == account_id,
        Job.job_type == JobType.VERIFY_THREADS,
        Job.status == JobStatus.FAILED
    ).all()
    for j in old_jobs:
        j.status = JobStatus.CANCELLED

    # Create fresh verification job
    verify_job = Job(
        platform="threads",
        account_id=account_id,
        job_type=JobType.VERIFY_THREADS,
        status=JobStatus.PENDING,
        caption="[VERIFY] Threads login verification (retry)",
        schedule_ts=int(time.time()),
    )
    db.add(verify_job)
    db.commit()
    logger.info("Created retry VERIFY_THREADS job #%s for account %s", verify_job.id, account.name)

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
        platforms = _platform_tokens(account.platform)
        platforms.discard("threads")
        account.platform = ",".join(sorted(platforms)) or "facebook"
        db.commit()
    
    return HTMLResponse(
        content="",
        status_code=200,
        headers={"HX-Redirect": "/threads"}
    )
