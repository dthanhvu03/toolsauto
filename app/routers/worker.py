from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.services.worker import WorkerService
from app.main_templates import templates
from app.constants import JobStatus

router = APIRouter(prefix="/worker", tags=["worker"])

@router.get("/status", response_class=HTMLResponse)
def get_worker_status(request: Request, db: Session = Depends(get_db)):
    state, trace_data = WorkerService.get_state_with_trace(db)
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time()), "trace": trace_data}
    )

@router.post("/pause", response_class=HTMLResponse)
def pause_worker(request: Request, db: Session = Depends(get_db)):
    WorkerService.set_status(db, "PAUSED")
    return get_worker_status(request, db)

@router.post("/resume", response_class=HTMLResponse)
def resume_worker(request: Request, db: Session = Depends(get_db)):
    WorkerService.set_status(db, JobStatus.RUNNING)
    return get_worker_status(request, db)

@router.post("/restart", response_class=HTMLResponse)
def restart_worker(request: Request, db: Session = Depends(get_db)):
    WorkerService.set_command(db, "RESTART_REQUESTED")
    return get_worker_status(request, db)

@router.post("/toggle-safe-mode", response_class=HTMLResponse)
def toggle_safe_mode(request: Request, db: Session = Depends(get_db)):
    WorkerService.toggle_safe_mode(db)
    return get_worker_status(request, db)
