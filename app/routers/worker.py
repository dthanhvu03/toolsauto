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
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time())}
    )

@router.post("/pause", response_class=HTMLResponse)
def pause_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_status(db, "PAUSED")
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time())}
    )

@router.post("/resume", response_class=HTMLResponse)
def resume_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_status(db, "RUNNING")
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time())}
    )

@router.post("/restart", response_class=HTMLResponse)
def restart_worker(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.set_command(db, "RESTART_REQUESTED")
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time())}
    )

@router.post("/toggle-safe-mode", response_class=HTMLResponse)
def toggle_safe_mode(request: Request, db: Session = Depends(get_db)):
    state = WorkerService.toggle_safe_mode(db)
    return templates.TemplateResponse(
        "fragments/worker_status.html", 
        {"request": request, "state": state, "now": int(time.time())}
    )
