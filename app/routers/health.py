from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import logging
from app.database.core import get_db
from app.services.health import HealthService

from app.main_templates import templates

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

_last_worker_down_alert = 0  # Unix timestamp of last alert (cooldown tracker)

@router.get("/json")
def health_check_json(db: Session = Depends(get_db)):
    """Health score & system metrics returning pure JSON."""
    global _last_worker_down_alert  # pylint: disable=global-statement
    try:
        health = HealthService.get_system_health(db)
        
        # Phase 4: Alert if worker heartbeat stale > 5 min, max once per 30 min
        worker_hb_age = health.get("worker", {}).get("heartbeat_age_seconds", 0)
        now_ts = int(time.time())
        if worker_hb_age > 300 and (now_ts - _last_worker_down_alert) > 1800:
            from app.services.notifier import NotifierService
            NotifierService.notify_worker_down()
            _last_worker_down_alert = now_ts
            
        return health
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "error": str(e)}

@router.get("", response_class=HTMLResponse)
@router.get("/ui", response_class=HTMLResponse)
def health_ui(request: Request, db: Session = Depends(get_db)):
    """Visual dashboard representation of system health."""
    try:
        health_data = HealthService.get_system_health(db)
    except Exception as e:
        logger.error(f"Health UI failed: {e}")
        health_data = {"status": "error", "error": str(e), 
                       "worker": {"status": "UNKNOWN", "heartbeat_age_seconds": 0, "safe_mode": False, "uptime_seconds": 0, "uptime_hours": 0},
                       "jobs": {"running": 0, "orphans": 0, "failed_24h": 0},
                       "accounts": {"disabled_or_invalid": 0, "details": []},
                       "metrics": {"total_views": 0, "total_clicks": 0, "avg_views_per_post": 0, "posts_checked": 0},
                       "system": {"memory_mb": 0, "browser_processes": 0},
                       "reasons": [str(e)]}
        
    return templates.TemplateResponse(
        "pages/health.html", 
        {"request": request, "health": health_data}
    )
