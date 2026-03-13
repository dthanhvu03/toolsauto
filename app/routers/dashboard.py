from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.database.models import Job, Account
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
