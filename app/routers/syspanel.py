from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
import os
import json
import glob
import time
import psutil
import shutil
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.main_templates import templates
from app.database.core import SessionLocal, engine
from app.database.models import Job, Account
from app.constants import JobStatus
from app.config import (
    TIMEZONE,
    DATABASE_URL,
    BASE_DIR,
    DATA_DIR,
    CONTENT_DIR,
    DONE_DIR,
    FAILED_DIR,
    REUP_DIR,
    THUMB_DIR,
    LOGS_DIR,
    VNC_PORT,
    CONTENT_MEDIA_DIR,
    CONTENT_VIDEO_DIR,
    CONTENT_PROCESSED_DIR,
    iter_pm2_log_directories,
)
import app.config as config

from app.services import syspanel_service

APP_DIR = str(BASE_DIR)
PM2_SAFE_NAMES = {
    "FB_Publisher_1", "FB_Publisher_2",
    "AI_Generator_1", "AI_Generator_2",
    "Maintenance", "Web_Dashboard", "9Router_Gateway",
    # Legacy (single-instance)
    "FB_Publisher", "AI_Generator",
}
PERSONA_FILE = str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")
DEFAULT_PERSONA = (
    "Bạn là chuyên gia content sáng tạo, viết tiếng Việt tự nhiên, gần gũi với người dùng Facebook Việt Nam. "
    "Hãy viết caption hấp dẫn, giàu cảm xúc, phù hợp với chủ đề video, có thể dùng emoji vừa phải."
)
router = APIRouter(prefix="/syspanel", tags=["syspanel"])
logger = logging.getLogger(__name__)

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_syspanel(request: Request):
    return syspanel_service.get_syspanel(request)

@router.get("/fragments/metrics", response_class=HTMLResponse)
def frag_metrics(request: Request):
    return syspanel_service.frag_metrics(request)

@router.get("/fragments/pm2", response_class=HTMLResponse)
def frag_pm2(request: Request):
    return syspanel_service.frag_pm2(request)

@router.get("/fragments/job-stats", response_class=HTMLResponse)
def frag_job_stats(request: Request):
    return syspanel_service.frag_job_stats(request)

@router.get("/fragments/content-stats", response_class=HTMLResponse)
def frag_content_stats(request: Request):
    return syspanel_service.frag_content_stats(request)

@router.get("/fragments/gemini-cookies", response_class=HTMLResponse)
def frag_gemini_cookies(request: Request):
    return syspanel_service.frag_gemini_cookies(request)

@router.get("/fragments/screenshots", response_class=HTMLResponse)
def frag_screenshots(request: Request):
    return syspanel_service.frag_screenshots(request)

@router.get("/logs", response_class=HTMLResponse)
def get_logs(request: Request, worker: str = "Web_Dashboard", log_type: str = "error", lines: int = 100):
    # Bao gồm cả process names của root PM2 (production) và vu PM2 (dev)
    return syspanel_service.get_logs(request, worker, log_type, lines)

@router.get("/screenshot", response_class=HTMLResponse)
def serve_screenshot(path: str):
    return syspanel_service.serve_screenshot(path)

@router.post("/cmd/git-pull", response_class=HTMLResponse)
def cmd_git_pull():
    return syspanel_service.cmd_git_pull()

@router.post("/cmd/pm2-restart", response_class=HTMLResponse)
def cmd_pm2_restart():
    return syspanel_service.cmd_pm2_restart()

@router.post("/cmd/pm2-restart-one", response_class=HTMLResponse)
def cmd_pm2_restart_one(name: str = Form(...)):
    return syspanel_service.cmd_pm2_restart_one(name)

@router.post("/cmd/pm2-action", response_class=HTMLResponse)
def cmd_pm2_action(request: Request, action: str = Form(...), name: str = Form(...)):
    return syspanel_service.cmd_pm2_action(request, action, name)

@router.post("/cmd/pm2-start", response_class=HTMLResponse)
def cmd_pm2_start():
    return syspanel_service.cmd_pm2_start()

@router.post("/cmd/pm2-stop", response_class=HTMLResponse)
def cmd_pm2_stop():
    return syspanel_service.cmd_pm2_stop()

@router.post("/cmd/kill-chrome", response_class=HTMLResponse)
def cmd_kill_chrome():
    return syspanel_service.cmd_kill_chrome()

@router.post("/cmd/start-vnc", response_class=HTMLResponse)
def cmd_start_vnc(request: Request):
    return syspanel_service.cmd_start_vnc(request)

@router.post("/cmd/stop-vnc", response_class=HTMLResponse)
def cmd_stop_vnc():
    return syspanel_service.cmd_stop_vnc()

@router.post("/cmd/cleanup-db", response_class=HTMLResponse)
def cmd_cleanup_db():
    return syspanel_service.cmd_cleanup_db()

@router.post("/cmd/db-vacuum", response_class=HTMLResponse)
def cmd_db_vacuum():
    return syspanel_service.cmd_db_vacuum()

@router.post("/cmd/db-backup", response_class=HTMLResponse)
def cmd_db_backup():
    return syspanel_service.cmd_db_backup()

@router.post("/cmd/db-info", response_class=HTMLResponse)
def cmd_db_info():
    return syspanel_service.cmd_db_info()

@router.post("/cmd/cleanup-videos", response_class=HTMLResponse)
def cmd_cleanup_videos():
    return syspanel_service.cmd_cleanup_videos()

@router.post("/cmd/retry-failed", response_class=HTMLResponse)
def cmd_retry_failed():
    return syspanel_service.cmd_retry_failed()

@router.post("/cmd/cancel-stuck", response_class=HTMLResponse)
def cmd_cancel_stuck():
    return syspanel_service.cmd_cancel_stuck()

@router.post("/cmd/clear-gemini-cookies", response_class=HTMLResponse)
def cmd_clear_gemini_cookies():
    return syspanel_service.cmd_clear_gemini_cookies()

@router.get("/persona", response_class=HTMLResponse)
def get_persona(request: Request):
    return syspanel_service.get_persona(request)

@router.post("/persona", response_class=HTMLResponse)
def save_persona(system_prompt: str = Form("")):
    return syspanel_service.save_persona(system_prompt)

@router.get("/fragments/9router-tuner", response_class=HTMLResponse)
def frag_9router_tuner(request: Request):
    return syspanel_service.frag_9router_tuner(request)

@router.post("/cmd/9router/config", response_class=HTMLResponse)
def cmd_save_9router_config(
    enabled: str = Form("false"),
    base_url: str = Form(""),
    api_key: str = Form(""),
    default_model: str = Form("")
):
    return syspanel_service.cmd_save_9router_config(enabled, base_url, api_key, default_model)

@router.post("/cmd/9router/test", response_class=HTMLResponse)
def cmd_test_9router_connection(
    base_url: str = Form(""),
    api_key: str = Form(""),
    default_model: str = Form("")
):
    return syspanel_service.cmd_test_9router_connection(base_url, api_key, default_model)

