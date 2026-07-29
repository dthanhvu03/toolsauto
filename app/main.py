from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


import logging

# Ensure models are loaded (relationships, mappers)
from app.core.database import models  # noqa: F401

# Schema: apply migrations with `python manage.py db upgrade` (Alembic), not at startup.

# Setup Logging
from app.utils.logger import setup_shared_logger
logger = setup_shared_logger(__name__ if __name__ != "__main__" else "fastapi")

# Import routers
# Core & Platform Routers
from app.platform.auth import router as auth
from app.platform.dashboard_shell import router as dashboard
from app.platform.health import router as health
from app.core.db_admin import router as database
from app.core.compliance import router as compliance
from app.core.ai import router as ai

# Feature Routers
from app.features.jobs import router as jobs
from app.features.accounts import router as accounts
from app.features.threads import router as threads
from app.features.affiliates import router as affiliates
from app.features.system_panel import router as system_panel
from app.features.system_panel import worker_router as worker
from app.features.system_panel import config_router as platform_config
from app.features.system_panel import ai_studio_router as ai_studio
from app.features.facebook import pages_router as pages
from app.features.facebook import manual_job_router as manual_job
from app.features.insights import router as insights
from app.features.telegram_bot import router as telegram
from app.features.viral_intake import router as viral
from app.features.viral_intake import intro_router as viral_intros
from app.core.notifier.service import NotifierService, TelegramNotifier
import app.config as config
from app.bootstrap_hooks import register_feature_hooks

register_feature_hooks()

app = FastAPI(
    title="Auto Publisher Dashboard",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Register Telegram Notifier when configured (no default secrets in config)
if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))


@app.on_event("startup")
def _load_runtime_settings_on_startup():
    """Apply DB overrides (Telegram / Gemini / …) so web process matches Settings UI."""
    try:
        from app.core.database.core import SessionLocal
        from app.core.settings import load_runtime_settings_into_process

        with SessionLocal() as db:
            load_runtime_settings_into_process(db)
    except Exception:
        logger.exception("startup: load_runtime_settings_into_process failed")

# Include routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(accounts.router)
app.include_router(worker.router)
app.include_router(health.router)
app.include_router(telegram.router)
app.include_router(viral_intros.router)
app.include_router(viral.router)
app.include_router(insights.router)
app.include_router(system_panel.router)
app.include_router(pages.router)
app.include_router(manual_job.router)
app.include_router(affiliates.router)
app.include_router(compliance.router)
app.include_router(database.router)
app.include_router(platform_config.router)
app.include_router(ai.router)
app.include_router(ai_studio.router)
app.include_router(threads.router)

# Static assets (SaaS UI CSS, etc.)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "app" / "static")), name="static")
config.THUMB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(config.THUMB_DIR)), name="thumbnails")

import secrets
import base64
from fastapi.responses import Response, JSONResponse, RedirectResponse
from fastapi import Request
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

@app.middleware("http")
async def cookie_auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Public paths (no session). Gemini login/ping require auth; cookie-sync uses X-Api-Secret.
    public_exact = {
        "/health",
        "/health/json",
        "/health/ui",
        "/health/gemini/cookie-sync",
    }
    public_prefixes = ("/static", "/login", "/favicon.ico")
    if path in public_exact or any(path.startswith(p) for p in public_prefixes):
        return await call_next(request)
        
    token = request.cookies.get("session_token")
    is_authenticated = False
    
    if token:
        try:
            # Re-read secret key from config directly inside middleware 
            signer = URLSafeTimedSerializer(config.SECRET_KEY)
            # max_age=604800 (7 days)
            payload = signer.loads(token, max_age=604800)
            if payload.get("user") == "admin":
                is_authenticated = True
                request.state.user = payload
        except Exception:
            # Invalid or expired token
            pass
            
    if is_authenticated:
        return await call_next(request)
        
    # Unauthenticated handling
    accept = request.headers.get("accept", "")
    if "text/html" in accept and request.method == "GET":
        return RedirectResponse(url="/login")
        
    return JSONResponse(
        content={"ok": False, "message": "Unauthorized or Session Expired"},
        status_code=401
    )
@app.middleware("http")
async def _inject_now_ts(request, call_next):
    import time as _time
    request.state.now_ts = int(_time.time())
    return await call_next(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
