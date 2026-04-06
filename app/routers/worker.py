import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.services.worker import WorkerService

from app.main_templates import templates

router = APIRouter(prefix="/worker", tags=["worker"])

@router.get("/status", response_class=HTMLResponse)
def get_worker_status(request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: Returns the worker status panel."""
    state = WorkerService.get_or_create_state(db)
    
    trace_data = None
    if state.engagement_status == 'JOB_EXECUTION' and state.engagement_detail:
        try:
            trace_data = json.loads(state.engagement_detail)
            # Tự động clear UI sau khi job kết thúc 30s
            if trace_data.get("status") in ("completed", "failed") and trace_data.get("updated_at"):
                from datetime import datetime
                try:
                    updated_ts = datetime.fromisoformat(trace_data["updated_at"]).timestamp()
                    if time.time() - updated_ts > 45:
                        trace_data = None
                        state.engagement_status = None
                        state.engagement_detail = None
                        db.commit()
                except Exception:
                    pass
        except Exception:
            pass

    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time()), "trace": trace_data}
    )

@router.post("/pause", response_class=HTMLResponse)
def pause_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_status(db, "PAUSED")
    return get_worker_status(request, db)

@router.post("/resume", response_class=HTMLResponse)
def resume_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_status(db, "RUNNING")
    return get_worker_status(request, db)

@router.post("/restart", response_class=HTMLResponse)
def restart_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_command(db, "RESTART_REQUESTED")
    return get_worker_status(request, db)

@router.post("/toggle-safe-mode", response_class=HTMLResponse)
def toggle_safe_mode(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.toggle_safe_mode(db)
    return get_worker_status(request, db)
