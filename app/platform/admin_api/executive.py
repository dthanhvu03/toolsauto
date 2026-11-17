"""Read-only executive aggregates; never start workers, sync vendors or mutate bot state."""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core.database.models import StudioProject, StudioTask
from app.features.threads.growth.config import DB_PATH as THREADS_DB_PATH
from cashback_bot import all_users, insights
from store_bot.db import StoreRepository

router = APIRouter()
logger = logging.getLogger(__name__)


class ReadOnlyStore(StoreRepository):
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn


def cashback_summary(now: datetime) -> dict:
    with insights.open_readonly(str(all_users.cashback_db())) as conn:
        money = insights.money(conn, now - timedelta(days=7), 7)
    return {
        "orders": money.orders,
        "net_commission": money.net,
        "customer_share": money.cashback,
        "reserve": money.reserve,
        "margin": money.margin,
        "period": "7 ngày gần nhất · theo thời điểm mua / ghi nhận",
    }


def store_summary() -> dict:
    raw = os.getenv("STORE_ADMIN_IDS", "").strip()
    if not raw:
        raise ValueError("STORE_ADMIN_IDS missing; cannot exclude admin purchases")
    admins = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not admins:
        raise ValueError("STORE_ADMIN_IDS empty")
    stats = ReadOnlyStore(str(all_users.store_db())).stats(admins=admins)
    return {
        "orders": stats["orders_7d"],
        "revenue": stats["revenue_7d"],
        "cost": stats["cost_7d"],
        "profit": stats["profit_7d"],
        "pending_orders": stats["pending_orders"],
        "pending_topups": stats["pending_topups"],
        "period": "7 ngày lịch Việt Nam · đơn đã giao, trừ hoàn · loại giao dịch admin",
    }


def threads_summary() -> dict:
    with insights.open_readonly(str(THREADS_DB_PATH)) as conn:
        counts = {row[0]: row[1] for row in conn.execute(
            "SELECT status, COUNT(*) FROM growth_posts GROUP BY status"
        )}
    return {"counts": counts, "period": "Từ đầu · số reply theo trạng thái"}


def studio_summary(db: Session) -> dict:
    projects = dict(db.query(StudioProject.status, func.count(StudioProject.id)).group_by(StudioProject.status).all())
    tasks = dict(db.query(StudioTask.status, func.count(StudioTask.id)).group_by(StudioTask.status).all())
    return {"projects": projects, "tasks": tasks}


@router.get("/executive")
def executive(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    result: dict = {"generated_at": now.isoformat(), "errors": {}}
    for key, reader in (
        ("cashback", lambda: cashback_summary(now)),
        ("store", store_summary),
        ("threads", threads_summary),
        ("studio", lambda: studio_summary(db)),
    ):
        try:
            result[key] = reader()
        except Exception:
            logger.exception("executive: cannot read %s", key)
            if key == "studio":
                db.rollback()
            result[key] = None
            result["errors"][key] = "Chưa đọc được nguồn dữ liệu"
    return result
