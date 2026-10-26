"""Số liệu khách hàng và dòng tiền cho chủ bot (PLAN-089). Một nơi tính, Telegram /admin và web cùng dùng.

- Chỉ đọc. `open_readonly` mở DB `mode=ro`; mọi hàm nhận connection, không ghi gì.
- Tiền lấy từ sổ `cashback_entries` (mỗi đơn khớp bot một dòng, dòng `:clawback:` là số âm khi Shopee giảm hoa
  hồng) và `shopee_conversions` (GMV, hoa hồng gộp, phí MCN). Đơn huỷ / gian lận: dòng sổ `cancelled`.
- Hai lớp: tạm tính (mọi đơn chưa huỷ) và thực (đơn đã SETTLED: Shopee đã trả, đối soát khớp).
- Biên của chủ bot = hoa hồng ròng − phần khách − dự phòng thuế / phí (theo snapshot từng link)
  − chi phí vận hành và hạ tầng (admin nhập mỗi tháng, chia theo số ngày của kỳ).
Module chỉ dùng thư viện chuẩn và sổ chi trả, để web (venv khác) cũng import được.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median

from cashback_bot import payouts

ICT = timezone(timedelta(hours=7))
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
OPS_COST_KEY = "ops_cost_monthly_vnd"
PERIODS = {"7d": "7 ngày", "30d": "30 ngày", "month": "Tháng này", "all": "Từ đầu"}
CLAWBACK = ":clawback:"
TICKET_FINAL = ("RESOLVED", "REJECTED", "CLOSED")
ZALO_LIMIT = 50
# Ngưỡng cảnh báo vận hành và nhóm khách (PLAN-089 mục 2.3, 2.4).
HEARTBEAT_STALE_SEC = 600
SYNC_STALE_CYCLES = 2
TICKET_STALE = timedelta(hours=24)
PAYOUT_STALE = timedelta(days=7)
SETTLE_STALE = timedelta(days=45)
ZALO_WARN = 40
BACKUP_STALE = timedelta(hours=26)
LINK_STUCK = timedelta(hours=1)
NEW_DAYS, ACTIVE_DAYS, CHURN_DAYS = 7, 14, 30
SEGMENTS = {
    "attention": "🔴 Cần xử lý",
    "top": "💎 Giá trị cao",
    "new": "🆕 Mới",
    "active": "🟢 Đang hoạt động",
    "churn": "🟠 Sắp rời",
    "dormant": "⚪ Ngủ",
}


@contextmanager
def open_readonly(path: str) -> Iterator[sqlite3.Connection]:
    """Kết nối chỉ đọc, đóng khi ra khỏi khối with."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def period_bounds(conn: sqlite3.Connection, period: str, now: datetime) -> tuple[datetime, int]:
    """(mốc bắt đầu, số ngày của kỳ). 'all' bắt đầu từ khách đầu tiên."""
    if period == "7d":
        return now - timedelta(days=7), 7
    if period == "month":
        start = now.astimezone(ICT).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, max(1, (now - start).days + 1)
    if period == "all":
        # Không chặn dưới (dữ liệu cũ, đơn ghi trước khách); số ngày tính từ khách đầu tiên để chia chi phí.
        first = parse_stamp(conn.execute("SELECT MIN(created_at) FROM telegram_users").fetchone()[0]) or now
        return EPOCH, max(1, (now - first).days + 1)
    return now - timedelta(days=30), 30


def ops_cost_monthly(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (OPS_COST_KEY,)).fetchone()
    try:
        return None if row is None or row[0] in (None, "") else max(0, int(row[0]))
    except ValueError:
        return None


# --- Dòng tiền ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Money:
    """Tiền một kỳ. *_settled: phần của đơn Shopee đã trả (thực)."""

    orders: int
    customers: int
    gmv: int
    gross: int
    mcn_fee: int
    net: int
    cashback: int
    reserve: int
    cancelled_orders: int
    cancelled_net: int
    approved_net: int
    settled_net: int
    settled_cashback: int
    settled_reserve: int
    ops_cost_monthly: int | None
    days: int

    @property
    def margin_before_reserve(self) -> int:
        return self.net - self.cashback

    @property
    def margin(self) -> int:
        """Sau dự phòng thuế / phí."""
        return self.net - self.cashback - self.reserve

    @property
    def ops_cost(self) -> int | None:
        return None if self.ops_cost_monthly is None else self.ops_cost_monthly * self.days // 30

    @property
    def profit(self) -> int | None:
        """Sau cả chi phí vận hành và hạ tầng; None khi admin chưa nhập chi phí."""
        return None if self.ops_cost is None else self.margin - self.ops_cost

    @property
    def settled_margin(self) -> int:
        return self.settled_net - self.settled_cashback - self.settled_reserve

    @property
    def cancel_rate(self) -> float:
        total = self.net + self.cancelled_net
        return self.cancelled_net / total if total > 0 else 0.0


def money(conn: sqlite3.Connection, since: datetime, days: int, user_id: int | None = None) -> Money:
    where_user, args = ("AND e.telegram_user_id = ?", (user_id,)) if user_id is not None else ("", ())
    row = conn.execute(
        f"""
        SELECT
          COUNT(DISTINCT CASE WHEN e.status != 'cancelled' AND instr(e.conversion_id, '{CLAWBACK}') = 0
                              THEN e.conversion_id END) AS orders,
          COUNT(DISTINCT CASE WHEN e.status != 'cancelled' THEN e.telegram_user_id END) AS customers,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.commission_vnd END), 0) AS net,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.cashback_vnd END), 0) AS cashback,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.fee_vnd + e.tax_vnd END), 0) AS reserve,
          COUNT(DISTINCT CASE WHEN e.status = 'cancelled' AND instr(e.conversion_id, '{CLAWBACK}') = 0
                              THEN e.conversion_id END) AS cancelled_orders,
          COALESCE(SUM(CASE WHEN e.status = 'cancelled' THEN e.commission_vnd END), 0) AS cancelled_net,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' AND c.validation_status = 'APPROVED'
                            THEN e.commission_vnd END), 0) AS approved_net,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' AND c.settlement_status = 'SETTLED'
                            THEN e.commission_vnd END), 0) AS settled_net,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' AND c.settlement_status = 'SETTLED'
                            THEN e.cashback_vnd END), 0) AS settled_cashback,
          COALESCE(SUM(CASE WHEN e.status != 'cancelled' AND c.settlement_status = 'SETTLED'
                            THEN e.fee_vnd + e.tax_vnd END), 0) AS settled_reserve
        FROM cashback_entries e
        LEFT JOIN shopee_conversions c
          ON c.conversion_id = CASE WHEN instr(e.conversion_id, '{CLAWBACK}') > 0
                                    THEN substr(e.conversion_id, 1, instr(e.conversion_id, '{CLAWBACK}') - 1)
                                    ELSE e.conversion_id END
        WHERE COALESCE(e.purchase_time, e.created_at) >= ? {where_user}
        """,
        (_stamp(since), *args),
    ).fetchone()
    conv_user, conv_args = ("AND c.telegram_user_id = ?", (user_id,)) if user_id is not None else ("", ())
    conv = conn.execute(
        f"""
        SELECT COALESCE(SUM(c.gmv_vnd), 0), COALESCE(SUM(c.gross_commission_vnd), 0), COALESCE(SUM(c.mcn_fee_vnd), 0)
        FROM shopee_conversions c JOIN cashback_entries e ON e.conversion_id = c.conversion_id
        WHERE e.status != 'cancelled' AND COALESCE(c.purchase_time, c.created_at) >= ? {conv_user}
        """,
        (_stamp(since), *conv_args),
    ).fetchone()
    return Money(
        int(row["orders"]), int(row["customers"]), int(conv[0]), int(conv[1]), int(conv[2]), int(row["net"]),
        int(row["cashback"]), int(row["reserve"]), int(row["cancelled_orders"]), int(row["cancelled_net"]),
        int(row["approved_net"]), int(row["settled_net"]), int(row["settled_cashback"]), int(row["settled_reserve"]),
        ops_cost_monthly(conn), days,
    )


@dataclass(frozen=True)
class Liabilities:
    """Nghĩa vụ với khách tại một thời điểm, và tiền Shopee đã trả thật."""

    pending: int
    holding: int
    in_wallet: int
    requested: int
    paid: int
    negative: int
    shopee_paid: int
    fund_headroom: int | None
    upcoming: int


def liabilities(conn: sqlite3.Connection) -> Liabilities:
    entry = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN status = 'pending' THEN cashback_vnd END), 0),
               COALESCE(SUM(CASE WHEN status = 'holding' THEN cashback_vnd END), 0)
        FROM cashback_entries
        """
    ).fetchone()
    requested, paid = payouts.payout_totals(conn)
    in_wallet = negative = 0
    for (user,) in conn.execute("SELECT DISTINCT telegram_user_id FROM cashback_entries WHERE status = 'available'"):
        left = payouts.withdrawable(conn, int(user))
        in_wallet += max(0, left)
        negative += min(0, left)
    shopee = conn.execute(
        "SELECT COALESCE(SUM(bank_received_vnd), 0) FROM settlement_batches WHERE status = 'MATCHED'"
    ).fetchone()[0]
    fund = payouts.fund_position(conn)
    upcoming = conn.execute(
        "SELECT COALESCE(SUM(e.commission_vnd), 0) FROM cashback_entries e JOIN shopee_conversions c "
        "ON c.conversion_id = e.conversion_id WHERE e.status != 'cancelled' AND c.validation_status = 'APPROVED' "
        "AND COALESCE(c.settlement_status, '') != 'SETTLED'"
    ).fetchone()[0]
    return Liabilities(int(entry[0]), int(entry[1]), in_wallet, requested, paid, -negative, int(shopee),
                       fund.headroom_vnd if fund.verified else None, int(upcoming))


@dataclass(frozen=True)
class CashTiming:
    """Trung vị số ngày; None khi chưa có mẫu."""

    purchase_to_complete: float | None
    complete_to_settled: float | None
    request_to_paid: float | None
    samples: tuple[int, int, int]


def _days(pairs) -> tuple[float | None, int]:
    values = []
    for start, end in pairs:
        a, b = parse_stamp(start), parse_stamp(end)
        if a and b and b >= a:
            values.append((b - a).total_seconds() / 86_400)
    return (round(median(values), 1) if values else None), len(values)


def cash_timing(conn: sqlite3.Connection) -> CashTiming:
    t1 = _days(conn.execute(
        "SELECT purchase_time, complete_time FROM shopee_conversions WHERE telegram_user_id IS NOT NULL "
        "AND complete_time IS NOT NULL"
    ))
    t2 = _days(conn.execute(
        """
        SELECT c.complete_time, MIN(i.created_at) FROM shopee_conversions c
        JOIN settlement_items i ON i.conversion_id = c.conversion_id AND i.match_status = 'MATCHED'
        WHERE c.settlement_status = 'SETTLED' GROUP BY c.conversion_id
        """
    ))
    t3 = _days(conn.execute(
        "SELECT p.created_at, MIN(ev.created_at) FROM cashback_payouts p JOIN payout_events ev "
        "ON ev.payout_id = p.id AND ev.to_status = 'paid_confirmed' GROUP BY p.id"
    ))
    return CashTiming(t1[0], t2[0], t3[0], (t1[1], t2[1], t3[1]))


@dataclass(frozen=True)
class DayPoint:
    day: str
    net: int
    margin: int
    orders: int


def daily(conn: sqlite3.Connection, since: datetime, now: datetime) -> list[DayPoint]:
    """Theo ngày giờ VN, từ `since` tới hôm nay (ngày không có đơn = 0)."""
    rows = conn.execute(
        """
        SELECT purchase_time, created_at, commission_vnd, cashback_vnd, fee_vnd + tax_vnd, conversion_id
        FROM cashback_entries WHERE status != 'cancelled' AND COALESCE(purchase_time, created_at) >= ?
        """,
        (_stamp(since),),
    ).fetchall()
    days: dict[str, list[int]] = {}
    cursor = since.astimezone(ICT).date()
    end = now.astimezone(ICT).date()
    while cursor <= end:
        days[cursor.isoformat()] = [0, 0, 0]
        cursor += timedelta(days=1)
    for purchase, created, net, cashback, reserve, conversion_id in rows:
        moment = parse_stamp(purchase) or parse_stamp(created)
        if moment is None:
            continue
        bucket = days.setdefault(moment.astimezone(ICT).date().isoformat(), [0, 0, 0])
        bucket[0] += int(net)
        bucket[1] += int(net) - int(cashback) - int(reserve)
        bucket[2] += 0 if CLAWBACK in conversion_id else 1
    return [DayPoint(day, *values) for day, values in sorted(days.items())]


# --- Tăng trưởng ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Funnel:
    linked: int
    clicked: int
    ordered: int
    completed: int
    settled: int
    links: int
    clicks: int
    orders: int


def funnel(conn: sqlite3.Connection, since: datetime) -> Funnel:
    """Khách tạo link trong kỳ → bao nhiêu người có click, có đơn, đơn hoàn thành, Shopee đã trả."""
    lo = _stamp(since)
    linked = conn.execute(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM link_requests WHERE created_at >= ? AND sub_id IS NOT NULL", (lo,)
    ).fetchone()[0]
    clicked = conn.execute(
        """
        SELECT COUNT(DISTINCT l.telegram_user_id) FROM link_requests l JOIN shopee_clicks k ON k.sub_id = l.sub_id
        WHERE l.created_at >= ?
        """,
        (lo,),
    ).fetchone()[0]
    per_stage = conn.execute(
        """
        SELECT COUNT(DISTINCT c.telegram_user_id),
               COUNT(DISTINCT CASE WHEN c.complete_time IS NOT NULL THEN c.telegram_user_id END),
               COUNT(DISTINCT CASE WHEN c.settlement_status = 'SETTLED' THEN c.telegram_user_id END)
        FROM shopee_conversions c JOIN link_requests l ON l.id = c.matched_link_id
        WHERE l.created_at >= ? AND c.telegram_user_id IS NOT NULL
        """,
        (lo,),
    ).fetchone()
    links = conn.execute("SELECT COUNT(*) FROM link_requests WHERE created_at >= ? AND sub_id IS NOT NULL", (lo,)).fetchone()[0]
    clicks = conn.execute(
        "SELECT COUNT(*) FROM shopee_clicks k JOIN link_requests l ON l.sub_id = k.sub_id WHERE k.click_time >= ?",
        (lo,),
    ).fetchone()[0]
    orders = conn.execute(
        "SELECT COUNT(*) FROM shopee_conversions WHERE telegram_user_id IS NOT NULL AND COALESCE(purchase_time, created_at) >= ?",
        (lo,),
    ).fetchone()[0]
    return Funnel(int(linked), int(clicked), int(per_stage[0]), int(per_stage[1]), int(per_stage[2]),
                  int(links), int(clicks), int(orders))


@dataclass(frozen=True)
class Growth:
    total: int
    telegram: int
    zalo: int
    new: int
    new_telegram: int
    new_zalo: int
    active_7d: int
    active_30d: int


def growth(conn: sqlite3.Connection, since: datetime, now: datetime) -> Growth:
    lo = _stamp(since)
    total, zalo, new, new_zalo = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(telegram_user_id < 0), 0), COALESCE(SUM(created_at >= ?), 0), "
        "COALESCE(SUM(created_at >= ? AND telegram_user_id < 0), 0) FROM telegram_users",
        (lo, lo),
    ).fetchone()

    def active(days: int) -> int:
        start = _stamp(now - timedelta(days=days))
        return int(conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT telegram_user_id FROM link_requests WHERE created_at >= ?
              UNION SELECT telegram_user_id FROM shopee_conversions
                    WHERE telegram_user_id IS NOT NULL AND COALESCE(purchase_time, created_at) >= ?)
            """,
            (start, start),
        ).fetchone()[0])

    return Growth(int(total), int(total) - int(zalo), int(zalo), int(new), int(new) - int(new_zalo), int(new_zalo),
                  active(7), active(30))


@dataclass(frozen=True)
class Cohort:
    week: str
    size: int
    next_week: int
    week_4: int


def cohorts(conn: sqlite3.Connection, now: datetime, weeks: int = 6) -> list[Cohort]:
    """Khách vào tuần N (thứ Hai giờ VN): bao nhiêu người tạo link ở tuần N+1, và trong tuần N+4."""
    local = now.astimezone(ICT)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    for back in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=back)
        users = [int(r[0]) for r in conn.execute(
            "SELECT telegram_user_id FROM telegram_users WHERE created_at >= ? AND created_at < ?",
            (_stamp(start), _stamp(start + timedelta(weeks=1))),
        )]

        def came_back(offset: int) -> int:
            if not users:
                return 0
            lo, hi = start + timedelta(weeks=offset), start + timedelta(weeks=offset + 1)
            marks = ", ".join("?" for _ in users)
            return int(conn.execute(
                f"SELECT COUNT(DISTINCT telegram_user_id) FROM link_requests WHERE telegram_user_id IN ({marks}) "
                "AND created_at >= ? AND created_at < ?",
                (*users, _stamp(lo), _stamp(hi)),
            ).fetchone()[0])

        result.append(Cohort(start.strftime("%d/%m"), len(users), came_back(1), came_back(4)))
    return result


@dataclass(frozen=True)
class Ranked:
    label: str
    orders: int
    net: int
    gmv: int


def top_categories(conn: sqlite3.Connection, since: datetime, column: str = "cat_name", limit: int = 5) -> list[Ranked]:
    if column not in ("cat_name", "shop_name"):
        raise ValueError(column)
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(l.{column}, ''), '(không rõ)'), COUNT(*), COALESCE(SUM(e.commission_vnd), 0),
               COALESCE(SUM(c.gmv_vnd), 0)
        FROM cashback_entries e JOIN shopee_conversions c ON c.conversion_id = e.conversion_id
        LEFT JOIN link_requests l ON l.id = e.link_id
        WHERE e.status != 'cancelled' AND COALESCE(e.purchase_time, e.created_at) >= ?
        GROUP BY 1 ORDER BY 3 DESC, 2 DESC LIMIT ?
        """,
        (_stamp(since), limit),
    ).fetchall()
    return [Ranked(str(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]


# --- Từng khách -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Customer:
    user_id: int
    name: str | None
    channel: str
    joined: str | None
    last_active: str | None
    links: int
    clicks: int
    orders: int
    completed: int
    cancelled: int
    gmv: int
    net: int
    cashback: int
    reserve: int
    wallet: int
    requested: int
    paid: int
    open_tickets: int
    blocked: bool
    bank_cooldown: bool
    segment: str = "dormant"
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def margin(self) -> int:
        return self.net - self.cashback - self.reserve

    @property
    def label(self) -> str:
        if self.channel == "zalo":
            return f"Zalo · {self.name}" if self.name else f"Zalo #{-self.user_id}"
        return f"@{self.name}" if self.name else f"ID {self.user_id}"


def customers(conn: sqlite3.Connection, now: datetime) -> list[Customer]:
    rows = conn.execute(
        """
        SELECT u.telegram_user_id AS uid, u.created_at, u.last_seen_at, u.notify_blocked_at,
               COALESCE(u.username, ci.display_name) AS name,
               (SELECT COUNT(*) FROM link_requests l WHERE l.telegram_user_id = u.telegram_user_id
                  AND l.sub_id IS NOT NULL) AS links,
               (SELECT MAX(created_at) FROM link_requests l WHERE l.telegram_user_id = u.telegram_user_id) AS last_link,
               (SELECT COUNT(*) FROM shopee_clicks k JOIN link_requests l ON l.sub_id = k.sub_id
                  WHERE l.telegram_user_id = u.telegram_user_id) AS clicks,
               (SELECT MAX(COALESCE(purchase_time, created_at)) FROM shopee_conversions c
                  WHERE c.telegram_user_id = u.telegram_user_id) AS last_order,
               (SELECT COUNT(*) FROM support_tickets t WHERE t.telegram_user_id = u.telegram_user_id
                  AND t.status NOT IN ('RESOLVED', 'REJECTED', 'CLOSED')) AS open_tickets
        FROM telegram_users u
        LEFT JOIN channel_identities ci ON ci.internal_user_id = u.telegram_user_id AND u.telegram_user_id < 0
        """
    ).fetchall()
    ledger = {
        int(r["uid"]): r for r in conn.execute(
            f"""
            SELECT e.telegram_user_id AS uid,
                   COUNT(DISTINCT CASE WHEN e.status != 'cancelled' AND instr(e.conversion_id, '{CLAWBACK}') = 0
                                       THEN e.conversion_id END) AS orders,
                   COUNT(DISTINCT CASE WHEN e.status IN ('holding', 'available')
                                        AND instr(e.conversion_id, '{CLAWBACK}') = 0 THEN e.conversion_id END) AS completed,
                   COUNT(DISTINCT CASE WHEN e.status = 'cancelled' AND instr(e.conversion_id, '{CLAWBACK}') = 0
                                       THEN e.conversion_id END) AS cancelled,
                   COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.commission_vnd END), 0) AS net,
                   COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.cashback_vnd END), 0) AS cashback,
                   COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN e.fee_vnd + e.tax_vnd END), 0) AS reserve,
                   COALESCE(SUM(CASE WHEN e.status != 'cancelled' THEN c.gmv_vnd END), 0) AS gmv
            FROM cashback_entries e LEFT JOIN shopee_conversions c ON c.conversion_id = e.conversion_id
            GROUP BY e.telegram_user_id
            """
        )
    }
    banks = {int(r[0]): payouts.account_sha(r[1], r[2])
             for r in conn.execute("SELECT telegram_user_id, bank_code, account_no FROM bank_accounts")}
    result = []
    for row in rows:
        uid = int(row["uid"])
        money_row = ledger.get(uid)
        requested, paid = payouts.payout_totals(conn, uid)
        until = payouts.bank_cooldown_until(conn, uid, banks.get(uid)) if uid in banks else None
        last = max((s for s in (row["last_seen_at"], row["last_link"], row["last_order"]) if s), default=None)
        result.append(Customer(
            user_id=uid, name=row["name"], channel="zalo" if uid < 0 else "telegram", joined=row["created_at"],
            last_active=last, links=int(row["links"]), clicks=int(row["clicks"]),
            orders=int(money_row["orders"]) if money_row else 0,
            completed=int(money_row["completed"]) if money_row else 0,
            cancelled=int(money_row["cancelled"]) if money_row else 0,
            gmv=int(money_row["gmv"]) if money_row else 0, net=int(money_row["net"]) if money_row else 0,
            cashback=int(money_row["cashback"]) if money_row else 0,
            reserve=int(money_row["reserve"]) if money_row else 0,
            wallet=payouts.withdrawable(conn, uid), requested=requested, paid=paid,
            open_tickets=int(row["open_tickets"]), blocked=bool(row["notify_blocked_at"]),
            bank_cooldown=until is not None and until > now,
        ))
    return _segment(result, now)


def _segment(items: list[Customer], now: datetime) -> list[Customer]:
    earners = sorted((c for c in items if c.margin > 0), key=lambda c: c.margin, reverse=True)
    top = {c.user_id for c in earners[:max(1, len(earners) // 10)]} if earners else set()
    out = []
    for c in items:
        flags = []
        if c.blocked:
            flags.append("chặn bot")
        if c.wallet < 0:
            flags.append("số dư âm")
        if c.open_tickets:
            flags.append(f"{c.open_tickets} ticket mở")
        if c.bank_cooldown:
            flags.append("vừa đổi tài khoản")
        joined = parse_stamp(c.joined)
        last = parse_stamp(c.last_active)
        idle = (now - last).days if last else 10_000
        if flags:
            segment = "attention"
        elif c.user_id in top:
            segment = "top"
        elif joined and now - joined <= timedelta(days=NEW_DAYS):
            segment = "new"
        elif idle <= ACTIVE_DAYS:
            segment = "active"
        elif idle <= CHURN_DAYS and c.orders:
            segment = "churn"
        else:
            segment = "dormant"
        out.append(Customer(**{**c.__dict__, "segment": segment, "flags": tuple(flags)}))
    return out


SORTS = {
    "margin": lambda c: (c.margin, c.orders),
    "orders": lambda c: (c.orders, c.margin),
    "new": lambda c: c.joined or "",
    "recent": lambda c: c.last_active or "",
    "wallet": lambda c: (c.wallet + c.requested, c.margin),
}


def sort_customers(items: list[Customer], key: str = "margin") -> list[Customer]:
    return sorted(items, key=SORTS.get(key, SORTS["margin"]), reverse=True)


@dataclass(frozen=True)
class Concentration:
    top1_share: float
    top10_share: float
    earners: int


def concentration(items: list[Customer]) -> Concentration:
    values = sorted((c.margin for c in items if c.margin > 0), reverse=True)
    total = sum(values)
    if not total:
        return Concentration(0.0, 0.0, 0)
    return Concentration(values[0] / total, sum(values[:max(1, len(values) // 10)]) / total, len(values))


@dataclass(frozen=True)
class Event:
    at: str
    kind: str
    text: str


def timeline(conn: sqlite3.Connection, user_id: int, limit: int = 40) -> list[Event]:
    """Mới trước. Không có số tài khoản đầy đủ, không có nội dung tin bot gửi."""
    events: list[Event] = []
    for r in conn.execute(
        "SELECT created_at, product_name, sub_id, link_status FROM link_requests WHERE telegram_user_id = ?", (user_id,)
    ):
        events.append(Event(r[0], "link", f"Tạo link {r[2] or '-'} · {(r[1] or '-')[:50]}"
                            + ("" if r[3] in (None, "created") else f" · {r[3]}")))
    for r in conn.execute(
        "SELECT k.click_time, k.sub_id FROM shopee_clicks k JOIN link_requests l ON l.sub_id = k.sub_id "
        "WHERE l.telegram_user_id = ?", (user_id,)
    ):
        events.append(Event(r[0], "click", f"Click link {r[1]}"))
    for r in conn.execute(
        "SELECT COALESCE(purchase_time, created_at), order_sn, order_status, net_commission_vnd, item_name, complete_time "
        "FROM shopee_conversions WHERE telegram_user_id = ?", (user_id,)
    ):
        events.append(Event(r[0], "order", f"Đơn …{(r[1] or '')[-6:]} · {(r[4] or '-')[:40]} · {r[2]} · HH {r[3] or 0}"))
        if r[5]:
            events.append(Event(r[5], "order", f"Đơn …{(r[1] or '')[-6:]} hoàn thành"))
    for r in conn.execute(
        "SELECT updated_at, item_name, status, cashback_vnd, conversion_id FROM cashback_entries WHERE telegram_user_id = ?",
        (user_id,),
    ):
        if CLAWBACK in r[4]:
            events.append(Event(r[0], "wallet", f"Thu hồi {r[3]} · {(r[1] or '-')[:40]}"))
        elif r[2] in ("available", "cancelled"):
            events.append(Event(r[0], "wallet", f"Sổ ví: {(r[1] or '-')[:40]} → {r[2]} ({r[3]})"))
    for r in conn.execute(
        "SELECT ev.created_at, p.transfer_note, ev.to_status, p.amount_vnd FROM payout_events ev "
        "JOIN cashback_payouts p ON p.id = ev.payout_id WHERE p.telegram_user_id = ?", (user_id,)
    ):
        events.append(Event(r[0], "payout", f"Rút {r[1] or ''} {r[3]} → {r[2]}"))
    for r in conn.execute(
        "SELECT created_at, id, category, status FROM support_tickets WHERE telegram_user_id = ?", (user_id,)
    ):
        events.append(Event(r[0], "ticket", f"Ticket #{r[1]} · {r[2]} · {r[3]}"))
    for r in conn.execute(
        "SELECT created_at, event_type, status FROM admin_notifications WHERE audience = 'customer' AND chat_id = ?",
        (user_id,),
    ):
        events.append(Event(r[0], "notice", f"Bot nhắn {r[1]} → {r[2]}"))
    events.sort(key=lambda e: e.at or "", reverse=True)
    return events[:limit]


@dataclass(frozen=True)
class Profile:
    bank: str | None
    bank_state: str
    terms: str | None
    prefs: dict[str, bool] | None


def profile(conn: sqlite3.Connection, user_id: int) -> Profile:
    bank_row = conn.execute("SELECT bank_code, account_no, account_name FROM bank_accounts WHERE telegram_user_id = ?",
                            (user_id,)).fetchone()
    bank = state = None
    if bank_row is not None:
        bank = f"{bank_row[0]} ••••{str(bank_row[1])[-4:]} · {bank_row[2]}"
        state = payouts.bank_status(conn, user_id, payouts.account_sha(bank_row[0], bank_row[1]))
    terms = conn.execute(
        "SELECT v.version || ' (' || substr(a.accepted_at, 1, 10) || ')' FROM customer_terms_acceptances a "
        "JOIN customer_terms_versions v ON v.id = a.terms_version_id WHERE a.telegram_user_id = ? ORDER BY a.id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    pref = conn.execute("SELECT orders, updates, support, wallet FROM customer_notification_prefs WHERE telegram_user_id = ?",
                        (user_id,)).fetchone()
    return Profile(bank, state or "NONE", terms[0] if terms else None,
                   None if pref is None else {k: bool(pref[k]) for k in ("orders", "updates", "support", "wallet")})


# --- Vận hành -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    code: str
    label: str
    value: str
    ok: bool


def _state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return None if row is None else row[0]


def _age_text(seconds: float | None) -> str:
    if seconds is None:
        return "chưa có"
    if seconds < 120:
        return f"{int(seconds)} giây"
    if seconds < 7_200:
        return f"{int(seconds // 60)} phút"
    if seconds < 172_800:
        return f"{seconds / 3600:.1f} giờ"
    return f"{seconds / 86_400:.1f} ngày"


def operations(conn: sqlite3.Connection, now: datetime, sync_interval_minutes: int = 240) -> list[Check]:
    checks: list[Check] = []
    stamp_now = now.timestamp()

    def beat(key: str) -> float | None:
        try:
            raw = _state(conn, key)
            return None if not raw else stamp_now - float(raw)
        except ValueError:
            return None

    versions = {ch: (_state(conn, f"code_version:{ch}") or "").partition("@")[0] or "?" for ch in ("telegram", "zalo")}
    tg, zl = beat("telegram_heartbeat"), beat("zalo_heartbeat")
    alive = all(age is not None and age <= HEARTBEAT_STALE_SEC for age in (tg, zl))
    checks.append(Check("bots", "Hai bot sống, cùng code",
                        f"Telegram {versions['telegram']} ({_age_text(tg)}) · Zalo {versions['zalo']} ({_age_text(zl)})",
                        alive and versions["telegram"] == versions["zalo"]))
    sync = conn.execute("SELECT last_success_at, consecutive_failures, enabled, paused FROM shopee_sync_state WHERE id = 1"
                        ).fetchone()
    last_sync = parse_stamp(sync["last_success_at"]) if sync else None
    sync_age = (now - last_sync).total_seconds() if last_sync else None
    sync_ok = sync_age is not None and sync_age <= sync_interval_minutes * 60 * SYNC_STALE_CYCLES \
        and not (sync and sync["consecutive_failures"])
    checks.append(Check("sync", "Đồng bộ Shopee",
                        f"thành công gần nhất {_age_text(sync_age)} trước · lỗi liền {sync['consecutive_failures'] if sync else 0}",
                        sync_ok))
    day = _stamp(now - timedelta(hours=24))
    sent = dict(conn.execute(
        "SELECT status, COUNT(*) FROM admin_notifications WHERE audience = 'customer' AND created_at >= ? GROUP BY status",
        (day,),
    ).fetchall())
    bad = int(sent.get("unknown", 0)) + int(sent.get("failed", 0))
    checks.append(Check("notices", "Tin gửi khách 24 giờ",
                        f"đã gửi {sent.get('sent', 0)} · không rõ {sent.get('unknown', 0)} · lỗi {sent.get('failed', 0)} · "
                        f"bỏ qua {sent.get('suppressed', 0)}", bad == 0))
    links = conn.execute(
        "SELECT COALESCE(SUM(link_status != 'created'), 0), "
        "COALESCE(SUM(link_status = 'created' AND COALESCE(delivery_status, 'sent') NOT IN ('sent')), 0) "
        "FROM link_requests WHERE created_at >= ?",
        (day,),
    ).fetchone()
    # Link kẹt quá 1 giờ tính từ đầu, không chỉ 24 giờ: link cũ kẹt không được lặng lẽ rơi khỏi cửa sổ.
    stuck = conn.execute(
        "SELECT COUNT(*) FROM link_requests WHERE link_status = 'created' "
        "AND COALESCE(delivery_status, 'sent') != 'sent' AND created_at < ?",
        (_stamp(now - LINK_STUCK),),
    ).fetchone()[0]
    checks.append(Check("links", "Link giao tới khách",
                        f"24 giờ: tạo lỗi {links[0]} · chưa giao {links[1]} · kẹt quá 1 giờ (từ đầu): {stuck}",
                        int(links[1]) == 0 and int(stuck) == 0))
    tickets = conn.execute(
        "SELECT COUNT(*), MIN(created_at) FROM support_tickets WHERE status NOT IN ('RESOLVED', 'REJECTED', 'CLOSED')"
    ).fetchone()
    oldest = parse_stamp(tickets[1])
    checks.append(Check("tickets", "Ticket đang mở",
                        f"{tickets[0]} · lâu nhất {_age_text((now - oldest).total_seconds()) if oldest else '-'}",
                        oldest is None or now - oldest <= TICKET_STALE))
    marks = ", ".join("?" for _ in payouts.OPEN)
    open_pay = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(amount_vnd), 0), MIN(created_at) FROM cashback_payouts WHERE status IN ({marks})",
        payouts.OPEN,
    ).fetchone()
    oldest_pay = parse_stamp(open_pay[2])
    checks.append(Check("payouts", "Yêu cầu rút đang mở",
                        f"{open_pay[0]} · {open_pay[1]:,}đ · lâu nhất "
                        f"{_age_text((now - oldest_pay).total_seconds()) if oldest_pay else '-'}".replace(",", "."),
                        oldest_pay is None or now - oldest_pay <= PAYOUT_STALE))
    stale = conn.execute(
        "SELECT COUNT(*) FROM shopee_conversions WHERE telegram_user_id IS NOT NULL AND complete_time IS NOT NULL "
        "AND complete_time < ? AND COALESCE(settlement_status, '') != 'SETTLED' AND COALESCE(validation_status, '') "
        "NOT IN ('FRAUD', 'REJECTED')",
        (_stamp(now - SETTLE_STALE),),
    ).fetchone()[0]
    checks.append(Check("settle", "Đơn hoàn thành > 45 ngày chưa đối soát", str(stale), int(stale) == 0))
    zalo = conn.execute("SELECT COUNT(*) FROM channel_identities WHERE channel = 'zalo'").fetchone()[0]
    checks.append(Check("zalo", "Sức chứa Zalo BASIC", f"{zalo}/{ZALO_LIMIT}", int(zalo) < ZALO_WARN))
    backup = beat("backup_last_ok")
    checks.append(Check("backup", "Backup tự động gần nhất", _age_text(backup),
                        backup is not None and backup <= BACKUP_STALE.total_seconds()))
    problems = payouts.invariants(conn)
    checks.append(Check("ledger", "Cảnh báo sổ ví", "không có" if not problems else ", ".join(problems[:3]), not problems))
    checks.append(Check("wallet", "Ví khách", "đang bật" if _state(conn, "wallet_enabled") == "1" else "đang tắt / khoá",
                        True))
    return checks


# --- Hoà vốn --------------------------------------------------------------------------------------

SHARE_CHOICES = (50, 55, 60, 65, 70, 75)


@dataclass(frozen=True)
class BreakevenRow:
    share_percent: int
    margin_rate: float
    need_net_month: int | None
    need_orders_month: int | None


@dataclass(frozen=True)
class Breakeven:
    """Cần bao nhiêu hoa hồng ròng / đơn mỗi tháng để biên sau dự phòng bù đủ chi phí vận hành.

    Số thật: hoa hồng ròng trung bình mỗi đơn và tỉ lệ dự phòng lấy từ sổ (đơn chưa huỷ). Công thức theo cách tính
    đang chạy: V1.1 khách nhận share × hoa hồng; V1.2 khách nhận share × (hoa hồng − dự phòng).
    """

    ops_cost_monthly: int | None
    formula: str
    orders: int
    net_per_order: int | None
    reserve_rate: float
    current_share: float | None
    net_30d: int
    orders_30d: int
    rows: tuple[BreakevenRow, ...]

    @property
    def current(self) -> BreakevenRow | None:
        if self.current_share is None:
            return None
        return min(self.rows, key=lambda r: abs(r.share_percent / 100 - self.current_share))


def margin_rate(share: float, reserve_rate: float, formula: str) -> float:
    if formula == "v1.2":
        return (1 - share) * (1 - reserve_rate)
    return 1 - share - reserve_rate


def breakeven(conn: sqlite3.Connection, now: datetime) -> Breakeven:
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT CASE WHEN instr(conversion_id, '{CLAWBACK}') = 0 THEN conversion_id END),
               COALESCE(SUM(commission_vnd), 0), COALESCE(SUM(cashback_vnd), 0), COALESCE(SUM(fee_vnd + tax_vnd), 0),
               COALESCE(SUM(policy_label LIKE 'v1.2%'), 0), COUNT(*)
        FROM cashback_entries WHERE status != 'cancelled'
        """
    ).fetchone()
    orders, net, cashback, reserve, v12, total = (int(v) for v in row)
    formula = "v1.2" if total and v12 * 2 > total else "v1.1"
    reserve_rate = reserve / net if net > 0 else 0.0
    per_order = net // orders if orders else None
    recent = money(conn, now - timedelta(days=30), 30)
    cost = ops_cost_monthly(conn)
    rows = []
    for percent in SHARE_CHOICES:
        rate = margin_rate(percent / 100, reserve_rate, formula)
        need_net = need_orders = None
        if cost is not None and rate > 0:
            need_net = -(-cost * 10_000 // int(round(rate * 10_000)))
            need_orders = -(-need_net // per_order) if per_order else None
        rows.append(BreakevenRow(percent, rate, need_net, need_orders))
    current = None
    if net > 0:
        current = cashback / net if formula == "v1.1" else cashback / max(1, net - reserve)
    return Breakeven(cost, formula, orders, per_order, reserve_rate, current, recent.net, recent.orders, tuple(rows))


# --- Mục tiêu (PLAN-090) --------------------------------------------------------------------------

GOALS_KEY = "goals_monthly"
# mã: (nhãn, đơn vị, kiểu). month: cộng dồn trong tháng, có dự báo · level: mức hiện tại · cap: không được vượt.
GOALS = {
    "completed": ("Đơn hoàn thành trong tháng", "count", "month"),
    "net": ("Hoa hồng ròng trong tháng", "vnd", "month"),
    "new": ("Khách mới trong tháng", "count", "month"),
    "active": ("Khách hoạt động 30 ngày", "count", "level"),
    "activation": ("Khách mới có đơn trong 7 ngày", "percent", "level"),
    "cancel": ("Tỉ lệ huỷ 30 ngày tối đa", "percent", "cap"),
}
ACTIVATION_DAYS = 7
ACTIVATION_WINDOW = 30


def goal_targets(conn: sqlite3.Connection) -> dict[str, int]:
    """Mục tiêu admin đã nhập. Mục chưa nhập hoặc hỏng thì bỏ qua."""
    try:
        raw = json.loads(_state(conn, GOALS_KEY) or "{}")
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: int(v) for k, v in raw.items() if k in GOALS and isinstance(v, int) and v >= 0}


@dataclass(frozen=True)
class GoalRow:
    key: str
    label: str
    unit: str
    kind: str
    actual: float | None
    target: int | None
    forecast: int | None
    per_day: int | None

    @property
    def status(self) -> str:
        """unset · nodata (chưa có mẫu) · done (đã đạt / trong giới hạn) · on_track (kịp cuối tháng) · behind."""
        if self.target is None:
            return "unset"
        if self.actual is None:
            return "nodata"
        if self.kind == "cap":
            return "done" if self.actual <= self.target else "behind"
        if self.actual >= self.target:
            return "done"
        if self.forecast is not None and self.forecast >= self.target:
            return "on_track"
        return "behind"


@dataclass(frozen=True)
class Goals:
    month: str
    day: int
    days_in_month: int
    rows: tuple[GoalRow, ...]
    milestones: tuple[tuple[str, bool], ...]
    guards: tuple[Check, ...]
    placed: int
    activation_size: int
    activation_waiting: int
    breakeven_net: int | None

    @property
    def stage(self) -> str:
        done = sum(ok for _label, ok in self.milestones)
        if done < len(self.milestones):
            return f"G1 · Chạy trọn vòng tiền ({done}/{len(self.milestones)} mốc)"
        return "G2+ · Tăng theo mục tiêu tháng"

    def row(self, key: str) -> GoalRow:
        return next(r for r in self.rows if r.key == key)


def _exists(conn: sqlite3.Connection, sql: str) -> bool:
    return conn.execute(f"SELECT EXISTS ({sql})").fetchone()[0] == 1


def goals(conn: sqlite3.Connection, now: datetime, sync_interval_minutes: int = 240) -> Goals:
    start, day = period_bounds(conn, "month", now)
    local = start.astimezone(ICT)
    following = (local.replace(day=28) + timedelta(days=4)).replace(day=1)
    days_in_month = (following - local).days
    elapsed = max(1.0, (now - start).total_seconds() / 86_400)
    left = max(1.0, days_in_month - elapsed)
    lo = _stamp(start)
    completed = conn.execute(
        "SELECT COUNT(DISTINCT c.conversion_id) FROM shopee_conversions c JOIN cashback_entries e "
        "ON e.conversion_id = c.conversion_id WHERE e.status != 'cancelled' AND c.complete_time >= ?",
        (lo,),
    ).fetchone()[0]
    month_money = money(conn, start, day)
    new = conn.execute("SELECT COUNT(*) FROM telegram_users WHERE created_at >= ?", (lo,)).fetchone()[0]
    active = growth(conn, start, now).active_30d
    first_order = {
        int(uid): parse_stamp(first) for uid, first in conn.execute(
            "SELECT telegram_user_id, MIN(COALESCE(purchase_time, created_at)) FROM shopee_conversions "
            "WHERE telegram_user_id IS NOT NULL GROUP BY telegram_user_id"
        )
    }
    size = activated = waiting = 0
    window = timedelta(days=ACTIVATION_DAYS)
    for uid, joined_raw in conn.execute("SELECT telegram_user_id, created_at FROM telegram_users"):
        joined = parse_stamp(joined_raw)
        if joined is None:
            continue
        if now - joined < window:
            waiting += 1
        elif now - joined <= window + timedelta(days=ACTIVATION_WINDOW):
            size += 1
            first = first_order.get(int(uid))
            activated += first is not None and first - joined <= window
    cancel = money(conn, now - timedelta(days=30), 30).cancel_rate * 100
    actual = {
        "completed": float(completed), "net": float(month_money.net), "new": float(new), "active": float(active),
        "activation": activated * 100 / size if size else None, "cancel": cancel,
    }
    targets = goal_targets(conn)
    rows = []
    for key, (label, unit, kind) in GOALS.items():
        target, value = targets.get(key), actual[key]
        forecast = per_day = None
        if kind == "month" and value is not None:
            forecast = int(value * days_in_month / elapsed)
            if target is not None and target > value:
                per_day = int(-(-(target - value) // left))
        rows.append(GoalRow(key, label, unit, kind, value, target, forecast, per_day))
    milestones = (
        ("Đơn đầu tiên qua bot", _exists(conn, "SELECT 1 FROM shopee_conversions WHERE telegram_user_id IS NOT NULL")),
        ("Đơn đầu tiên hoàn thành", _exists(
            conn, "SELECT 1 FROM shopee_conversions WHERE telegram_user_id IS NOT NULL AND complete_time IS NOT NULL")),
        ("Shopee trả tiền đơn đầu tiên (đối soát khớp)", _exists(
            conn, "SELECT 1 FROM shopee_conversions WHERE telegram_user_id IS NOT NULL AND settlement_status = 'SETTLED'")),
        ("Khách đầu tiên nhận tiền", _exists(conn, "SELECT 1 FROM payout_events WHERE to_status = 'paid_confirmed'")),
    )
    people = customers(conn, now)
    losing = sum(1 for c in people if c.margin < 0)
    owing = sum(1 for c in people if c.wallet < 0)
    checks = {c.code: c for c in operations(conn, now, sync_interval_minutes)}
    guards = (
        Check("losing", "Khách có biên âm", str(losing), losing == 0),
        Check("owing", "Khách có số dư âm", str(owing), owing == 0),
        checks["notices"], checks["links"], checks["tickets"], checks["ledger"],
    )
    current = breakeven(conn, now).current
    return Goals(
        local.strftime("%m/%Y"), now.astimezone(ICT).day, days_in_month, tuple(rows), milestones, guards,
        month_money.orders, size, waiting, None if current is None else current.need_net_month,
    )


# --- Gói cho màn hình -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Overview:
    period: str
    since: datetime
    money: Money
    liabilities: Liabilities
    timing: CashTiming
    growth: Growth
    funnel: Funnel
    concentration: Concentration
    top_customers: list[Customer]
    categories: list[Ranked]
    shops: list[Ranked]
    channels: dict[str, tuple[int, int, int]]
    days: list[DayPoint]
    cohorts: list[Cohort]
    checks: list[Check]
    breakeven: Breakeven


def overview(conn: sqlite3.Connection, period: str, now: datetime, sync_interval_minutes: int = 240) -> Overview:
    period = period if period in PERIODS else "30d"
    since, days = period_bounds(conn, period, now)
    people = customers(conn, now)
    channels: dict[str, tuple[int, int, int]] = {}
    for name in ("telegram", "zalo"):
        group = [c for c in people if c.channel == name]
        channels[name] = (len(group), sum(c.orders for c in group), sum(c.margin for c in group))
    chart_since = since if period != "all" else now - timedelta(days=90)
    return Overview(
        period, since, money(conn, since, days), liabilities(conn), cash_timing(conn), growth(conn, since, now),
        funnel(conn, since), concentration(people), sort_customers(people)[:5],
        top_categories(conn, since), top_categories(conn, since, "shop_name"), channels,
        daily(conn, chart_since, now), cohorts(conn, now), operations(conn, now, sync_interval_minutes),
        breakeven(conn, now),
    )
