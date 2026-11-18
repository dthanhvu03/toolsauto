"""Read-only executive aggregates; never start workers, sync vendors or mutate bot state."""

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core.database.models import StudioProject, StudioTask
from app.features.threads.growth.config import DB_PATH as THREADS_DB_PATH
from cashback_bot import all_users, insights, money_flow
from store_bot.db import ICT, StoreRepository

router = APIRouter()
logger = logging.getLogger(__name__)


class ReadOnlyStore(StoreRepository):
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn


def cashback_summary(now: datetime, days: int) -> dict:
    now_local = now.astimezone(ICT)
    chart_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    since = chart_start.astimezone(timezone.utc)
    with insights.open_readonly(str(all_users.cashback_db())) as conn:
        period = insights.money(conn, since, days)
        trend = insights.daily(conn, chart_start, now)
        position = money_flow.snapshot(conn)
    settled_periods = position.settled
    upcoming_periods = position.upcoming
    settled_known = all(item.received_vnd is not None for item in settled_periods)
    upcoming_known = all(item.amount_vnd is not None for item in upcoming_periods)
    return {
        "orders": period.orders,
        "net_commission": period.net,
        "customer_share": period.cashback,
        "reserve": period.reserve,
        "margin": period.margin,
        "period": f"{days} ngày lịch Việt Nam · theo thời điểm mua / ghi nhận",
        "period_start": chart_start.date().isoformat(),
        "period_end": now_local.date().isoformat(),
        "trend": [
            {"day": point.day, "net_commission": point.net, "margin": point.margin, "label": point.day}
            for point in trend
        ] if days <= 7 else _weekly_trend(
            [{"day": point.day, "net_commission": point.net, "margin": point.margin} for point in trend],
            ("net_commission", "margin"),
        ),
        "money_position": {
            "settled_owner_received": position.owner_vnd if settled_known else None,
            "settled_owner_received_known": settled_known,
            "upcoming_owner": position.upcoming_owner_vnd if upcoming_known else None,
            "upcoming_owner_known": upcoming_known,
            "customer_waiting": position.customers.waiting_vnd,
            "customer_wallet": position.customers.in_wallet_vnd,
            "payout_reserved": position.customers.reserved_vnd,
            "payout_paid": position.customers.paid_vnd,
            "fund_available": position.fund.headroom_vnd if position.fund.verified else None,
            "fund_verified": position.fund.verified,
            "open_adjustments": position.open_adjustments,
            "settled_periods": len(settled_periods),
            "upcoming_periods": len(upcoming_periods),
        },
    }


def _weekly_trend(points: list[dict], fields: tuple[str, ...]) -> list[dict]:
    weeks = []
    for offset in range(0, len(points), 7):
        week = points[offset:offset + 7]
        if not week:
            continue
        first, last = week[0]["day"], week[-1]["day"]
        start_label = datetime.fromisoformat(first).strftime("%d/%m")
        end_label = datetime.fromisoformat(last).strftime("%d/%m")
        weeks.append({"day": last, "label": f"{start_label} – {end_label}",
                      **{field: sum(int(point[field]) for point in week) for field in fields}})
    return weeks


def store_summary(days: int) -> dict:
    raw = os.getenv("STORE_ADMIN_IDS", "").strip()
    if not raw:
        raise ValueError("STORE_ADMIN_IDS missing; cannot exclude admin purchases")
    admins = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not admins:
        raise ValueError("STORE_ADMIN_IDS empty")
    repo = ReadOnlyStore(str(all_users.store_db()))
    today = datetime.now(ICT).replace(hour=0, minute=0, second=0, microsecond=0)
    first_day = today - timedelta(days=days - 1)
    start = first_day.astimezone(timezone.utc).isoformat(timespec="seconds")
    cashflow = repo.cashflow(days=days, top=0, admins=admins)
    sales = repo.sales_by_product(since=start, exclude=admins)
    with repo._read() as conn:
        names = {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM products")}
        marks = ", ".join("?" for _ in admins)
        pending_orders, pending_topups, waiting_cost = conn.execute(
            f"""SELECT
                (SELECT COUNT(*) FROM orders WHERE status = 'pending' AND user_id NOT IN ({marks})),
                (SELECT COUNT(*) FROM topups WHERE status = 'pending' AND user_id NOT IN ({marks})),
                (SELECT COALESCE(SUM(COALESCE(unit_cost, 0) * quantity), 0) FROM orders
                 WHERE status = 'pending' AND waiting_funds = 1 AND user_id NOT IN ({marks}))""",
            (*admins, *admins, *admins),
        ).fetchone()
    products = [
        {"name": names.get(product_id, f"#{product_id}"), "sold": sold, "revenue": revenue,
         "gross_profit": revenue - cost}
        for product_id, (sold, revenue, cost) in sales.items()
    ]
    trend = [
        {
            "day": point["key"].split("|")[-1] if "|" in point["key"] else point["key"],
            "label": point["key"].replace("|", " – ").replace("-", "/"),
            "revenue": point["revenue"],
            "net_profit": point["net"],
        }
        for point in sorted(cashflow["buckets"], key=lambda item: item["key"].split("|")[0])
    ]
    total = cashflow["total"]
    return {
        "orders": total["orders"],
        "revenue": total["revenue"],
        "cost": total["cost"],
        "profit": total["net"],
        "gross_profit": total["profit"],
        "external_expense": total["expense"],
        "pending_orders": int(pending_orders),
        "pending_topups": int(pending_topups),
        "period": f"{days} ngày lịch Việt Nam · đơn đã giao, trừ hoàn · loại giao dịch admin",
        "period_start": first_day.date().isoformat(),
        "period_end": today.date().isoformat(),
        "cost_note": "Giá vốn chưa ghi nhận được tính 0đ; lãi gộp theo món chưa phân bổ chi phí ngoài.",
        "trend": trend,
        "top_sellers": sorted(products, key=lambda product: (-product["sold"], product["name"]))[:5],
        "top_profit": sorted(products, key=lambda product: (-product["gross_profit"], product["name"]))[:5],
        "money_position": {
            "customer_wallet": cashflow["balances"],
            "capital_recorded": cashflow["capital"],
            "capital_used": cashflow["capital_used"],
            "waiting_order_cost": int(waiting_cost),
        },
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
def executive(db: Session = Depends(get_db), days: str = Query(default="7", pattern="^(7|30)$")) -> dict:
    days = int(days)
    now = datetime.now(timezone.utc)
    result: dict = {"generated_at": now.isoformat(), "errors": {}}
    for key, reader in (
        ("cashback", lambda: cashback_summary(now, days)),
        ("store", lambda: store_summary(days)),
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
