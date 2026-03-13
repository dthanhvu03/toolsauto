from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import logging

# Ensure models are loaded to initialize the database
from app.database import models
from app.database.core import engine, ensure_runtime_schema

# Create tables if they don't exist (useful for dev, Alembic handles prod)
models.Base.metadata.create_all(bind=engine)
ensure_runtime_schema()

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import routers
from app.routers import dashboard, jobs, accounts, worker, health, telegram, viral
from app.services.notifier import NotifierService, TelegramNotifier
import app.config as config

app = FastAPI(title="Auto Publisher Dashboard")

# Register Telegram Notifier for the Web Server process (used by Health checks)
NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))

# Include routers
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(accounts.router)
app.include_router(worker.router)
app.include_router(health.router)
app.include_router(telegram.router)
app.include_router(viral.router)

# Note: In an original larger setup we would serve static files, e.g.
# app.mount("/static", StaticFiles(directory="app/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
