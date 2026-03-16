from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Form
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.database.models import Job, Account, DiscoveredChannel
from app.services.worker import WorkerService

# Gắn FastAPI app state or custom dependencies later if needed.
# Note: we need access to templates in routers. We'll import them from a shared location.
from app.main_templates import templates

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Render the main dashboard."""
    # Default: show active jobs (PENDING+RUNNING) with pagination
    query = db.query(Job).filter(Job.status.in_(["PENDING", "RUNNING"]))
    total = query.count()
    per_page = 20
    total_pages = max(1, (total + per_page - 1) // per_page)
    jobs = query.order_by(Job.schedule_ts.desc()).limit(per_page).all()
    accounts = db.query(Account).all()
    state = WorkerService.get_or_create_state(db)
    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, "jobs": jobs, "accounts": accounts, "state": state, "now": int(time.time()),
            "current_status": "active", "current_page": 1, "total_pages": total_pages, "total_jobs": total, "per_page": per_page
        }
    )

@router.get("/r/{code}")
def redirect_tracking(code: str, db: Session = Depends(get_db)):
    """Redirect tracking link and increment click counter."""
    job = db.query(Job).filter(Job.tracking_code == code).first()
    if not job or not job.affiliate_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tracking link not found or no affiliate URL set.")
    job.click_count = (job.click_count or 0) + 1
    db.commit()
    return RedirectResponse(job.affiliate_url, status_code=302)

@router.get("/discovery/panel", response_class=HTMLResponse)
def get_discovery_panel(request: Request, db: Session = Depends(get_db)):
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/approve", response_class=HTMLResponse)
def approve_discovered_channel(channel_id: int, request: Request, target_page: str = Form(""), db: Session = Depends(get_db)):
    channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
    if channel and channel.status == "NEW":
        channel.status = "APPROVED"
        account = channel.account
        if account:
            import json as _json
            urls = []
            if account.competitor_urls:
                try:
                    data = _json.loads(account.competitor_urls)
                    if isinstance(data, list):
                        urls = data
                except Exception:
                    pass
            exists = any(u.get("url") == channel.channel_url for u in urls if isinstance(u, dict))
            if not exists:
                urls.append({"url": channel.channel_url, "target_page": target_page if target_page else None})
                account.competitor_urls = _json.dumps(urls, ensure_ascii=False)
        db.commit()
    
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/reject", response_class=HTMLResponse)
def reject_discovered_channel(channel_id: int, request: Request, db: Session = Depends(get_db)):
    channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
    if channel and channel.status == "NEW":
        channel.status = "REJECTED"
        db.commit()
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/force-scan", response_class=HTMLResponse)
def force_discovery_scan(request: Request, db: Session = Depends(get_db)):
    """Manually trigger competitor discovery scan for all active accounts (bypasses 2-5AM schedule)."""
    import random
    import logging
    logger = logging.getLogger(__name__)

    from app.services.discovery_scraper import DiscoveryScraper

    accounts = db.query(Account).filter(
        Account.is_active == True,
        Account.niche_topics != None,
    ).all()

    scraper = DiscoveryScraper()
    total_found = 0
    scan_log = []

    for acc in accounts:
        import json as _json
        keywords = []
        try:
            raw = acc.niche_topics
            if raw and raw.strip().startswith("["):
                keywords = _json.loads(raw)
            elif raw:
                keywords = [k.strip() for k in raw.split(",") if k.strip()]
        except Exception:
            continue

        if not keywords:
            continue

        selected = random.sample(keywords, min(2, len(keywords)))
        for kw in selected:
            try:
                found = scraper.discover_for_keyword(kw, acc.id, db)
                total_found += found
                scan_log.append(f"✅ '{acc.name}' / kw='{kw}': {found} kênh mới")
            except Exception as e:
                scan_log.append(f"❌ '{acc.name}' / kw='{kw}': lỗi {str(e)[:80]}")

    logger.info("[DISCOVERY] Force scan complete. %d new channels found.", total_found)

    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels, "scan_log": scan_log, "total_found": total_found}
    )

