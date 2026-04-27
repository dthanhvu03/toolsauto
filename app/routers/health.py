from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import logging
from app.database.core import get_db
from app.services.health import HealthService
import app.config as config
from app.main_templates import templates

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

_last_worker_down_alert = 0

@router.get("/json")
def health_check_json(db: Session = Depends(get_db)):
    global _last_worker_down_alert
    try:
        health = HealthService.get_system_health(db)
        worker_hb_age = health.get("worker", {}).get("heartbeat_age_seconds", 0)
        now_ts = int(time.time())
        if worker_hb_age > 300 and (now_ts - _last_worker_down_alert) > 1800:
            HealthService.notify_worker_down()
            _last_worker_down_alert = now_ts
        return health
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "error": str(e)}

@router.get("/gemini/ping", response_class=HTMLResponse)
def ping_gemini_ui():
    health = HealthService.get_gemini_health()
    if health["is_valid"]:
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
    try:
        HealthService.start_gemini_login()
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
    expected_secret = getattr(config, 'COOKIE_SYNC_SECRET', "vuxuandao2026")
    if not x_api_secret or x_api_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid API Secret")
    try:
        cookies = await request.json()
        HealthService.sync_cookies(cookies)
        logger.info("✅ Đã nhận và cập nhật Cookie Gemini mới từ Chrome Extension!")
        return {"status": "success", "message": "Cookies synced successfully"}
    except Exception as e:
        logger.error("Lỗi khi xử lý cookie sync từ Extension: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_class=HTMLResponse)
@router.get("/ui", response_class=HTMLResponse)
def health_ui(request: Request, db: Session = Depends(get_db)):
    try:
        health_data = HealthService.get_system_health(db)
    except Exception as e:
        logger.error(f"Health UI failed: {e}")
        health_data = {"status": "error", "error": str(e), "worker": {"status": "UNKNOWN"}, "reasons": [str(e)]}
    return templates.TemplateResponse("pages/health.html", {"request": request, "health": health_data})
