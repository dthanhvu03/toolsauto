from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
import logging
import secrets
from app.core.database.core import get_db
from app.core.observability.health import HealthService
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
            <button id="gemini-badge" hx-get="/health/gemini/ping" hx-target="closest [data-gemini-slot]" hx-swap="innerHTML"
                class="cave-badge cave-badge-moss inline-flex items-center gap-1.5 h-9 px-3 cursor-pointer hover:brightness-110 transition">
                <span class="cave-dot cave-dot-moss"></span>
                Gemini: Hoạt động
            </button>
        ''')
    else:
        return HTMLResponse('''
            <div id="gemini-badge" class="inline-flex items-center gap-1 h-8 sm:h-9 p-0.5 sm:p-1 max-w-full rounded-[var(--radius-lg)] border border-[var(--color-danger-border)] bg-[var(--color-danger-dim)] whitespace-nowrap shrink min-w-0">
                <span class="hidden md:inline-flex items-center gap-1.5 text-[var(--color-danger)] text-cave-xs font-semibold px-2 shrink-0">
                    <span class="cave-dot" style="background:var(--color-danger-deep)"></span>
                    Gemini: Hết hạn
                </span>
                <span class="md:hidden inline-flex items-center pl-1.5 shrink-0" title="Gemini: Hết hạn">
                    <span class="cave-dot" style="background:var(--color-danger-deep)"></span>
                </span>
                <button hx-post="/health/gemini/login" hx-target="closest [data-gemini-slot]" hx-swap="innerHTML"
                    type="button"
                    title="Mở Chrome đăng nhập Google AI Studio — không phải đăng nhập app"
                    aria-label="Làm mới cookie Gemini Web qua Chrome"
                    class="cave-btn cave-btn-primary h-full px-2 sm:px-2.5 text-[10px] tracking-wide shrink-0">
                    Cookie
                </button>
                <a href="/syspanel" title="Quản lý cookie thủ công"
                    class="hidden lg:inline-flex px-2 h-full items-center text-[10px] font-semibold text-[var(--color-mist)] hover:text-[var(--color-torch)] shrink-0">
                    Panel hệ thống
                </a>
            </div>
        ''')

@router.post("/gemini/login", response_class=HTMLResponse)
def start_gemini_login():
    try:
        HealthService.start_gemini_login()
        return HTMLResponse('''
            <button id="gemini-badge" hx-get="/health/gemini/ping" hx-target="closest [data-gemini-slot]" hx-trigger="every 5s" hx-swap="innerHTML"
                class="cave-badge cave-badge-torch inline-flex items-center gap-1.5 h-9 px-3 animate-pulse">
                <svg class="w-3.5 h-3.5 animate-spin text-[var(--color-torch)]" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Chrome...
            </button>
        ''')
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        detail = str(e).replace('"', "'")[:120]
        return HTMLResponse(
            "<button id='gemini-badge' "
            f"title=\"{detail}\" "
            "class='cave-badge cave-badge-danger inline-flex items-center h-9 px-3'>"
            "Lỗi mở Chrome</button>"
        )

@router.post("/gemini/cookie-sync")
async def cookie_sync(request: Request, x_api_secret: str = Header(None)):
    expected_secret = getattr(config, "COOKIE_SYNC_SECRET", "") or ""
    if not expected_secret:
        raise HTTPException(
            status_code=503,
            detail="COOKIE_SYNC_SECRET is not configured",
        )
    if not x_api_secret or not secrets.compare_digest(x_api_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid API Secret")
    try:
        cookies = await request.json()
        HealthService.sync_cookies(cookies)
        logger.info("✅ Đã nhận và cập nhật Cookie Gemini mới từ Chrome Extension!")
        return {"status": "success", "message": "Cookies synced successfully"}
    except HTTPException:
        raise
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
