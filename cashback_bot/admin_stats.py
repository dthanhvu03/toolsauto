"""Thống kê cho /admin (PLAN-063). Chỉ đọc.

Tiền ở đây là số dự kiến đã báo khách, chưa phải doanh thu: bot chưa theo dõi đơn.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
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
class Insight:
    """Dữ liệu AddLiveTag lưu lúc tạo link (PLAN-064). Chỉ link từ bản đó trở đi có."""

    detailed: int
    seller_commission_vnd: int
    shopee_commission_vnd: int
    avg_rate_bps: int | None
    xtra: int
    capped: int
    top_categories: list[tuple[str, int]]
    top_shops: list[tuple[str, int]]


# Trạng thái đơn Shopee (order_status), dùng chung cho thống kê và sổ hoàn tiền.
_CANCELLED = "(order_status LIKE '%CANCEL%')"
_COMPLETED = "(order_status LIKE '%COMPLETED%' OR order_status LIKE '%SUCCESS%')"
# Như wallet.order_state: chưa huỷ, chưa hoàn thành là chờ duyệt (UNPAID, PAID, PENDING, …).
_PENDING = f"(NOT {_CANCELLED} AND NOT {_COMPLETED})"


@dataclass(frozen=True)
class ShopeeDay:
    label: str
    orders: int
    cancelled: int
    gmv_vnd: int
    net_commission_vnd: int
    clicks: int


@dataclass(frozen=True)
class ShopeeStats:
    """Số liệu đối soát thật từ Shopee Affiliate (PLAN-065, PLAN-066).

    Tiền (doanh số, hoa hồng) không tính đơn huỷ; đơn huỷ có ô riêng.
    """

    total_clicks: int
    clicks_with_bot_sub_id: int
    orders_total: int
    orders_pending: int
    orders_completed: int
    orders_cancelled: int
    orders_matched_bot: int
    real_commission_vnd: int
    conversion_rate_percent: float | None = None
    gmv_vnd: int = 0
    item_qty: int = 0
    gross_commission_vnd: int = 0
    mcn_fee_vnd: int = 0
    cancelled_gmv_vnd: int = 0
    lost_commission_vnd: int = 0
    daily: list[ShopeeDay] = field(default_factory=list)
    # Đơn qua bot (sổ cashback_entries, không tính huỷ): HH − khách − phí − dự phòng thuế = admin còn.
    bot_commission_vnd: int = 0
    bot_cashback_vnd: int = 0
    bot_fee_vnd: int = 0
    bot_tax_vnd: int = 0

    @property
    def admin_keep_vnd(self) -> int:
        return self.bot_commission_vnd - self.bot_cashback_vnd - self.bot_fee_vnd - self.bot_tax_vnd


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
    quarantined_updates: int = 0
    insight: Insight | None = None
    shopee: ShopeeStats | None = None


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
        insight=_insight(conn, lo),
        shopee=_shopee_stats(conn, lo, period_start("7d", now)),
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
        # Update Telegram bị cách ly (hardening P0-4). DB cũ chưa có bảng thì _count trả 0.
        quarantined_updates=_count(conn, "SELECT COUNT(*) FROM failed_updates WHERE status = 'quarantined'"),
    )


def _insight(conn: sqlite3.Connection, lo: str) -> Insight | None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}
    if "cat_name" not in columns:
        return None
    where = "link_status = 'created' AND created_at >= ? AND (cat_name IS NOT NULL OR commission_rate_bps IS NOT NULL)"
    row = conn.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM(seller_commission_vnd), 0), COALESCE(SUM(shopee_commission_vnd), 0),
               AVG(commission_rate_bps), COALESCE(SUM(is_xtra = 1), 0), COALESCE(SUM(is_capped = 1), 0)
        FROM link_requests WHERE {where}
        """,
        (lo,),
    ).fetchone()

    def top(column: str) -> list[tuple[str, int]]:
        return [
            (str(name), int(count))
            for name, count in conn.execute(
                f"""
                SELECT {column}, COUNT(*) AS n FROM link_requests
                WHERE link_status = 'created' AND created_at >= ? AND {column} IS NOT NULL
                GROUP BY 1 ORDER BY n DESC, 1 LIMIT 3
                """,
                (lo,),
            ).fetchall()
        ]

    return Insight(
        detailed=int(row[0]),
        seller_commission_vnd=int(row[1]),
        shopee_commission_vnd=int(row[2]),
        avg_rate_bps=None if row[3] is None else round(row[3]),
        xtra=int(row[4]),
        capped=int(row[5]),
        top_categories=top("cat_name"),
        top_shops=top("shop_name"),
    )


def _shopee_stats(conn: sqlite3.Connection, lo: str, trend_start: datetime | None = None) -> ShopeeStats | None:
    # Lọc theo giờ click / giờ đặt hàng; lần đồng bộ đầu kéo 30 ngày nên created_at không dùng được.
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "shopee_clicks" not in tables or "shopee_conversions" not in tables:
        return None
    columns = {row[1] for row in conn.execute("PRAGMA table_info(shopee_conversions)")}

    def col(name: str) -> str:
        # DB chưa chạy migrate PLAN-066 thì coi như 0, không vỡ màn thống kê.
        return name if name in columns else "0"

    bot_sub = "sub_id IN (SELECT sub_id FROM link_requests WHERE sub_id IS NOT NULL)"
    clicks_row = conn.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM({bot_sub}), 0)
        FROM shopee_clicks
        WHERE COALESCE(click_time, created_at) >= ?
        """,
        (lo,),
    ).fetchone()
    total_clicks = int(clicks_row[0])
    bot_clicks = int(clicks_row[1])

    conv_row = conn.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM({_PENDING}), 0),
            COALESCE(SUM({_COMPLETED}), 0),
            COALESCE(SUM({_CANCELLED}), 0),
            COALESCE(SUM(matched_link_id IS NOT NULL), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE net_commission_vnd END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE {col("gmv_vnd")} END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE {col("item_qty")} END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE gross_commission_vnd END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE {col("mcn_fee_vnd")} END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN {col("gmv_vnd")} ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN {_CANCELLED} THEN COALESCE(net_commission_vnd, gross_commission_vnd) ELSE 0 END), 0)
        FROM shopee_conversions
        WHERE COALESCE(purchase_time, created_at) >= ?
        """,
        (lo,),
    ).fetchone()
    values = [int(value or 0) for value in conv_row]
    orders_total, pending, completed, cancelled, matched, net, gmv, qty, gross, fee, cancelled_gmv, lost = values

    # CR chỉ tính phần đi qua link bot: đơn khớp Sub ID / click mang Sub ID của bot.
    cr = round((matched / bot_clicks) * 100, 1) if bot_clicks > 0 else None
    split = _bot_split(conn, lo, tables)

    return ShopeeStats(
        total_clicks=total_clicks,
        clicks_with_bot_sub_id=bot_clicks,
        orders_total=orders_total,
        orders_pending=pending,
        orders_completed=completed,
        orders_cancelled=cancelled,
        orders_matched_bot=matched,
        real_commission_vnd=net,
        conversion_rate_percent=cr,
        gmv_vnd=gmv,
        item_qty=qty,
        gross_commission_vnd=gross,
        mcn_fee_vnd=fee,
        cancelled_gmv_vnd=cancelled_gmv,
        lost_commission_vnd=lost,
        daily=_shopee_daily(conn, trend_start, col) if trend_start else [],
        bot_commission_vnd=split[0],
        bot_cashback_vnd=split[1],
        bot_fee_vnd=split[2],
        bot_tax_vnd=split[3],
    )


def _bot_split(conn: sqlite3.Connection, lo: str, tables: set[str]) -> tuple[int, int, int, int]:
    if "cashback_entries" not in tables:
        return 0, 0, 0, 0
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cashback_entries)")}
    fee, tax = ("fee_vnd", "tax_vnd") if "fee_vnd" in columns else ("0", "0")
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(commission_vnd), 0), COALESCE(SUM(cashback_vnd), 0),
               COALESCE(SUM({fee}), 0), COALESCE(SUM({tax}), 0)
        FROM cashback_entries
        WHERE status != 'cancelled' AND COALESCE(purchase_time, created_at) >= ?
        """,
        (lo,),
    ).fetchone()
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


def _shopee_daily(conn: sqlite3.Connection, trend_start: datetime, col) -> list[ShopeeDay]:
    """Bảng 7 ngày như trang Thống kê của Addlivetag, theo ngày giờ VN."""
    lo = _stamp(trend_start)
    orders = {
        row[0]: row[1:]
        for row in conn.execute(
            f"""
            SELECT date(COALESCE(purchase_time, created_at), '+7 hours'),
                   COUNT(*), COALESCE(SUM({_CANCELLED}), 0),
                   COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE {col("gmv_vnd")} END), 0),
                   COALESCE(SUM(CASE WHEN {_CANCELLED} THEN 0 ELSE net_commission_vnd END), 0)
            FROM shopee_conversions WHERE COALESCE(purchase_time, created_at) >= ?
            GROUP BY 1
            """,
            (lo,),
        ).fetchall()
    }
    clicks = dict(
        conn.execute(
            """
            SELECT date(COALESCE(click_time, created_at), '+7 hours'), COUNT(*)
            FROM shopee_clicks WHERE COALESCE(click_time, created_at) >= ?
            GROUP BY 1
            """,
            (lo,),
        ).fetchall()
    )
    days = []
    for offset in range(TREND_DAYS):
        day = (trend_start + timedelta(days=offset)).astimezone(ICT)
        key = day.strftime("%Y-%m-%d")
        n, n_cancel, gmv, net = (int(v or 0) for v in orders.get(key, (0, 0, 0, 0)))
        days.append(ShopeeDay(day.strftime("%d/%m"), n, n_cancel, gmv, net, int(clicks.get(key, 0))))
    return days


CSV_HEADER = (
    "Ngày đặt (giờ VN)", "Mã đơn", "Trạng thái", "Tên món", "Số lượng", "Doanh số",
    "HH gốc", "Phí MCN", "HH sau cùng", "Sub ID", "Telegram ID", "Username", "Hoàn thành lúc", "Tháng duyệt dự kiến",
)


def _vn(stamp: str | None) -> str:
    if not stamp:
        return ""
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return stamp
    return moment.astimezone(ICT).strftime("%Y-%m-%d %H:%M")


def conversions_csv(conn: sqlite3.Connection, since: datetime) -> tuple[bytes, int]:
    """CSV đơn Shopee từ `since` (theo giờ đặt). BOM UTF-8 để Excel đọc đúng tiếng Việt."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(shopee_conversions)")}

    def col(name: str) -> str:
        return f"c.{name}" if name in columns else "NULL"

    rows = conn.execute(
        f"""
        SELECT COALESCE(c.purchase_time, c.created_at), c.order_sn, c.order_status, {col("item_name")}, {col("item_qty")},
               {col("gmv_vnd")}, c.gross_commission_vnd, {col("mcn_fee_vnd")}, c.net_commission_vnd, c.sub_id,
               c.telegram_user_id, u.username, {col("complete_time")}, {col("validation_month")}
        FROM shopee_conversions c LEFT JOIN telegram_users u ON u.telegram_user_id = c.telegram_user_id
        WHERE COALESCE(c.purchase_time, c.created_at) >= ?
        ORDER BY 1 DESC
        """,
        (_stamp(since),),
    ).fetchall()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for row in rows:
        values = list(row)
        values[0] = _vn(values[0])
        values[12] = _vn(values[12])
        writer.writerow(["" if value is None else value for value in values])
    return buffer.getvalue().encode("utf-8-sig"), len(rows)
