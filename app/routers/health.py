from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import logging
from app.database.core import get_db
from app.services.health import HealthService
import json
import os
import subprocess

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

COOKIE_PATH = "/home/vu/toolsauto/gemini_cookies.json"
INVALID_FLAG = "/home/vu/toolsauto/gemini_cookies_invalid"

@router.get("/gemini/ping", response_class=HTMLResponse)
def ping_gemini_ui():
    """Checks the gemini cookies and returns an HTMX badge."""
    is_valid = False
    # 1. Check flag file (runtime detection — ưu tiên cao nhất)
    if os.path.exists(INVALID_FLAG):
        is_valid = False  # Đã bị Google revoke ở runtime
    elif os.path.exists(COOKIE_PATH):
        try:
            with open(COOKIE_PATH, "r") as f:
                cookies = json.load(f)
            # Find __Secure-1PSID
            for c in cookies:
                if c.get("name") == "__Secure-1PSID":
                    expiry = c.get("expiry", 0)
                    if expiry > time.time():
                        is_valid = True
                    break
        except Exception as e:
            logger.error("Error reading cookies: %s", e)
            
    if is_valid:
        return HTMLResponse('''
            <button id="gemini-badge" hx-get="/health/gemini/ping" hx-target="#gemini-badge" hx-swap="outerHTML" 
                class="inline-flex items-center gap-2 px-3 py-2 bg-green-50 border border-green-200 rounded-lg shadow-sm text-sm font-medium text-green-700 hover:bg-green-100 transition-all cursor-pointer">
                🟢 Gemini: Active
            </button>
        ''')
    else:
        return HTMLResponse('''
            <div id="gemini-badge" class="flex items-center gap-2 bg-red-50 p-1.5 rounded-lg border border-red-200 shadow-sm h-[42px]">
                <span class="text-red-600 text-sm font-medium px-2">🔴 Gemini: Expired</span>
                <button hx-post="/health/gemini/login" hx-target="#gemini-badge" hx-swap="outerHTML"
                    class="px-3 h-full bg-red-600 text-white text-xs font-semibold rounded hover:bg-red-700 transition">
                    Login Now
                </button>
            </div>
        ''')

@router.post("/gemini/login", response_class=HTMLResponse)
def start_gemini_login():
    """Starts the login script on the server display."""
    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        subprocess.Popen(
            ["/home/vu/toolsauto/venv/bin/python", "scripts/login_gemini_bypass.py"], 
            env=env, 
            cwd="/home/vu/toolsauto",
            start_new_session=True
        )
        return HTMLResponse('''
            <button id="gemini-badge" hx-get="/health/gemini/ping" hx-target="#gemini-badge" hx-trigger="every 5s" hx-swap="outerHTML"
                class="inline-flex items-center gap-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded-lg shadow-sm text-sm font-medium text-yellow-700 animate-pulse">
                ⌛ Mở Chrome... (đang chờ)
            </button>
        ''')
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        return HTMLResponse(f"<button id='gemini-badge' class='inline-flex items-center px-3 py-2 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200'>Lỗi mở Chrome</button>")

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
