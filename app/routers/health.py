from fastapi import APIRouter, Depends, Request, HTTPException, Header
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

import app.config as config
import sys

COOKIE_PATH = str(config.BASE_DIR / "gemini_cookies.json")
INVALID_FLAG = str(config.BASE_DIR / "gemini_cookies_invalid")

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
                class="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 h-9 bg-green-50 border border-green-200 rounded-lg shadow-sm text-xs sm:text-sm font-medium text-green-700 hover:bg-green-100 transition-all cursor-pointer whitespace-nowrap shrink-0">
                <span class="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)] animate-pulse"></span>
                Gemini: Active
            </button>
        ''')
    else:
        return HTMLResponse('''
            <div id="gemini-badge" class="flex items-center gap-1.5 bg-red-50 p-1 rounded-lg border border-red-200 shadow-sm h-9 whitespace-nowrap shrink-0">
                <span class="flex items-center gap-1.5 text-red-600 text-xs sm:text-sm font-medium px-1 sm:px-2 shrink-0">
                    <span class="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]"></span> Gemini: Expired
                </span>
                <button hx-post="/health/gemini/login" hx-target="#gemini-badge" hx-swap="outerHTML"
                    class="px-2 sm:px-3 h-full bg-red-600 text-white text-[10px] sm:text-xs font-semibold rounded hover:bg-red-700 transition shrink-0 uppercase tracking-wide">
                    Login
                </button>
            </div>
        ''')

@router.post("/gemini/login", response_class=HTMLResponse)
def start_gemini_login():
    """Starts the login script on the server display."""
    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        python_bin = str(config.BASE_DIR / "venv" / "bin" / "python")
        subprocess.Popen(
            [python_bin, "scripts/login_gemini_bypass.py"], 
            env=env, 
            cwd=str(config.BASE_DIR),
            start_new_session=True
        )
        return HTMLResponse('''
            <button id="gemini-badge" hx-get="/health/gemini/ping" hx-target="#gemini-badge" hx-trigger="every 5s" hx-swap="outerHTML"
                class="inline-flex items-center gap-1.5 px-2 sm:px-3 py-1.5 h-9 bg-amber-50 border border-amber-200 rounded-lg shadow-sm text-xs sm:text-sm font-medium text-amber-700 animate-pulse whitespace-nowrap shrink-0">
                <svg class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Chrome...
            </button>
        ''')
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        return HTMLResponse(f"<button id='gemini-badge' class='inline-flex items-center px-3 py-2 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200'>Lỗi mở Chrome</button>")

@router.post("/gemini/cookie-sync")
async def cookie_sync(request: Request, x_api_secret: str = Header(None)):
    """Receives Gemini cookies from the Chrome Extension to revive RPA instantly."""
    import app.config as config
    expected_secret = getattr(config, 'COOKIE_SYNC_SECRET', "vuxuandao2026") # Fallback secret
    
    if not x_api_secret or x_api_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid API Secret")
        
    try:
        cookies = await request.json()
        if not isinstance(cookies, list):
            raise HTTPException(status_code=400, detail="Cookies must be a JSON array")
            
        with open(COOKIE_PATH, "w") as f:
            json.dump(cookies, f)
            
        if os.path.exists(INVALID_FLAG):
            os.remove(INVALID_FLAG)
            
        logger.info("✅ Đã nhận và cập nhật Cookie Gemini mới từ Chrome Extension!")
        return {"status": "success", "message": "Cookies synced successfully"}
    except Exception as e:
        logger.error("Lỗi khi xử lý cookie sync từ Extension: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

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
