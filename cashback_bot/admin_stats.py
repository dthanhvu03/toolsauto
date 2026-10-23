"""Thống kê cho /admin (PLAN-063). Chỉ đọc.

Tiền ở đây là số dự kiến đã báo khách, chưa phải doanh thu: bot chưa theo dõi đơn.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cashback_bot.messages import buyer_name

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
# key: (nhãn, số ngày lùi thêm trước hôm nay; None là toàn bộ)
PERIODS = {
    "today": ("Hôm nay", 0),
    "7d": ("7 ngày", 6),
    "30d": ("30 ngày", 29),
    "all": ("Tất cả", None),
}
REJECT_LABELS = {
    "invalid_link": "Link sai",
    "not_found": "Không thấy sản phẩm",
    "link_build_failed": "Lỗi tạo link",
    "reserve_read_failed": "Lỗi đọc cấu hình",
}
DATA_NOT_READY = "Dữ liệu sản phẩm chưa sẵn"
TREND_DAYS = 7
TOP = 5


@dataclass(frozen=True)
class Stats:
    period: str
    since: datetime | None
    users_total: int
    users_new: int
    users_active: int
    links_total: int
    links_created: int
    rejected: list[tuple[str, int]]
    commission_vnd: int
    cashback_vnd: int
    trend: list[tuple[str, int]]
    top_users: list[tuple[int, str | None, int]]
    top_products: list[tuple[str, int]]
    delivery_pending: int
    errors: int


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def period_start(period: str, now: datetime) -> datetime | None:
    back = PERIODS[period][1]
    if back is None:
        return None
    local = now.astimezone(ICT)
    midnight = datetime(local.year, local.month, local.day, tzinfo=ICT)
    return (midnight - timedelta(days=back)).astimezone(timezone.utc)


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, args).fetchone()[0] or 0)
    except sqlite3.OperationalError:
        return 0


def collect(conn: sqlite3.Connection, period: str, now: datetime) -> Stats:
    since = period_start(period, now)
    lo = _stamp(since) if since else ""
    in_period = "created_at >= ?"

    rejected: dict[str, int] = {}
    for reason, count in conn.execute(
        f"SELECT reject_reason, COUNT(*) FROM link_requests WHERE link_status = 'rejected' AND {in_period} GROUP BY 1",
        (lo,),
    ).fetchall():
        label = REJECT_LABELS.get(reason or "", DATA_NOT_READY)
        rejected[label] = rejected.get(label, 0) + int(count)

    money = conn.execute(
        f"""
        SELECT COALESCE(SUM(estimated_commission), 0), COALESCE(SUM(estimated_cashback), 0)
        FROM link_requests WHERE link_status = 'created' AND {in_period}
        """,
        (lo,),
    ).fetchone()

    trend_start = period_start("7d", now)
    by_day = dict(
        conn.execute(
            """
            SELECT date(created_at, '+7 hours'), COUNT(*) FROM link_requests
            WHERE link_status = 'created' AND created_at >= ?
            GROUP BY 1
            """,
            (_stamp(trend_start),),
        ).fetchall()
    )
    trend = []
    for offset in range(TREND_DAYS):
        day = (trend_start + timedelta(days=offset)).astimezone(ICT)
        trend.append((day.strftime("%d/%m"), int(by_day.get(day.strftime("%Y-%m-%d"), 0))))

    top_users = [
        (int(user_id), username, int(count))
        for user_id, username, count in conn.execute(
            f"""
            SELECT l.telegram_user_id, u.username, COUNT(*) AS n
            FROM link_requests l LEFT JOIN telegram_users u ON u.telegram_user_id = l.telegram_user_id
            WHERE l.link_status = 'created' AND l.{in_period}
            GROUP BY 1, 2 ORDER BY n DESC, 1 LIMIT ?
            """,
            (lo, TOP),
        ).fetchall()
    ]
    top_products = [
        (buyer_name(name or "-"), int(count))
        for name, count in conn.execute(
            f"""
            SELECT MAX(product_name), COUNT(*) AS n FROM link_requests
            WHERE link_status = 'created' AND {in_period}
            GROUP BY item_id ORDER BY n DESC, MAX(id) DESC LIMIT ?
            """,
            (lo, TOP),
        ).fetchall()
    ]

    return Stats(
        period=period,
        since=since,
        users_total=_count(conn, "SELECT COUNT(*) FROM telegram_users"),
        users_new=_count(conn, f"SELECT COUNT(*) FROM telegram_users WHERE {in_period}", (lo,)),
        users_active=_count(
            conn, f"SELECT COUNT(DISTINCT telegram_user_id) FROM link_requests WHERE {in_period}", (lo,)
        ),
        links_total=_count(conn, f"SELECT COUNT(*) FROM link_requests WHERE {in_period}", (lo,)),
        links_created=_count(
            conn, f"SELECT COUNT(*) FROM link_requests WHERE link_status = 'created' AND {in_period}", (lo,)
        ),
        rejected=sorted(rejected.items(), key=lambda item: -item[1]),
        commission_vnd=int(money[0]),
        cashback_vnd=int(money[1]),
        trend=trend,
        top_users=top_users,
        top_products=top_products,
        delivery_pending=_count(
            conn, "SELECT COUNT(*) FROM outbound_messages WHERE status IN ('pending', 'retry', 'ambiguous', 'needs_review')"
        ),
        errors=_count(
            conn,
            f"SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'REQUEST_FAILED' AND {in_period}",
            (lo,),
        ),
    )
