"""Hạng thành viên đang chạy (PLAN-154). ranks.py giữ tỷ lệ; module này lưu hạng từng khách và xét theo tháng.

Chủ bot chốt 2026-11-05:
• Khách mới mặc định Đồng. Không có dòng trong member_ranks nghĩa là Đồng.
• Lúc bật hạng, khách đã có lên Vàng (`khach_cu`), giữ Vàng tới hết 31/12/2026; từ 01/01/2027 xét như mọi người.
• Tính theo 2 tháng: đơn hoàn thành (Shopee báo COMPLETED, chưa huỷ) của tháng trước + tháng này.
  Đủ ngưỡng thì lên ngay. Đầu mỗi tháng xét lại theo 2 tháng vừa qua, không đủ thì xuống MỘT bậc.
  Ngày 24 nhắc khách sắp xuống hạng. Hạng giữa tháng không bao giờ giảm.
• Ngưỡng admin cấu hình (/admin → 🏅 Hạng thành viên), lưu bot_state; mặc định bộ «dễ». Phải đủ cả đơn và tiền.
• Hạng mới chỉ áp cho link tạo sau đó; link cũ giữ tỷ lệ trong snapshot.

Tỷ lệ từng hạng lấy theo màn admin «Hạng» (policy_versions membership_rates), không có thì ranks.V1_TIERS.
Tỷ lệ chia chung (share_policies) là trần: hạng không vượt mức chung đang áp dụng.
Tháng tính theo giờ Việt Nam. Hàm ghi sổ dùng BEGIN IMMEDIATE vì hai bot (Telegram, Zalo) cùng chạy.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.ranks import V1_TIERS

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_RANK = "BRONZE"
LABELS = {tier.code: tier.label for tier in V1_TIERS}
ORDER = tuple(tier.code for tier in V1_TIERS)
SEEDED_KEY = "membership:seeded_at"
REVIEWED_KEY = "membership:reviewed_month"
REMINDED_KEY = "membership:reminded_month"
THRESHOLDS_KEY = "membership_thresholds"
# Khách cũ giữ Vàng tới hết tháng 12/2026: lần xét đầu tiên áp cho họ là tháng 2027-01.
GRANDFATHER_FIRST_REVIEW = "2027-01"
GRANDFATHER_UNTIL_TEXT = "31/12/2026"
REMIND_DAY = 24
EVENT_TYPE = "RANK_UP"
# mã: (nhãn, đơn vị, mặc định, nhỏ nhất, lớn nhất). Mặc định = bộ «dễ» trong ranks.THRESHOLD_SETS.
FIELDS: dict[str, tuple[str, str, int, int, int]] = {
    "silver_orders": ("🥈 Bạc: số đơn", "đơn", 2, 1, 500),
    "silver_vnd": ("🥈 Bạc: tiền hoàn", "đ", 30_000, 0, 100_000_000),
    "gold_orders": ("🥇 Vàng: số đơn", "đơn", 6, 1, 1_000),
    "gold_vnd": ("🥇 Vàng: tiền hoàn", "đ", 90_000, 0, 500_000_000),
}
DEFAULTS = {key: spec[2] for key, spec in FIELDS.items()}
_COUNTED = "status IN ('holding', 'available') AND completed_at IS NOT NULL AND cashback_vnd > 0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS member_ranks (
    user_id INTEGER PRIMARY KEY,
    rank_code TEXT NOT NULL CHECK (rank_code IN ('BRONZE', 'SILVER', 'GOLD')),
    reason TEXT NOT NULL,
    since TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS member_rank_events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    from_code TEXT,
    to_code TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_member_rank_events_user ON member_rank_events (user_id, id);
"""


@dataclass(frozen=True)
class Progress:
    rank_code: str
    orders: int
    cashback_vnd: int
    window: str
    next_code: str | None
    need_orders: int
    need_vnd: int
    keep_orders: int
    keep_vnd: int
    protected_until: str | None


@dataclass(frozen=True)
class Change:
    """kind: up (lên hạng), down (xét tháng, xuống một bậc), keep (nhắc giữ hạng; to_code = hạng đang có)."""

    user_id: int
    kind: str
    from_code: str
    to_code: str
    need_orders: int = 0
    need_vnd: int = 0


# --- Ngưỡng -----------------------------------------------------------------------------------


def valid(key: str, value: int) -> bool:
    _label, _unit, _default, low, high = FIELDS[key]
    return low <= value <= high


def ordered(values: dict[str, int]) -> bool:
    """Vàng không thấp hơn Bạc ở cả số đơn và tiền."""
    return values["gold_orders"] >= values["silver_orders"] and values["gold_vnd"] >= values["silver_vnd"]


def custom(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (THRESHOLDS_KEY,)).fetchone()
    try:
        raw = json.loads(row[0]) if row and row[0] else {}
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in FIELDS and isinstance(v, int) and valid(k, v)}


def thresholds(conn: sqlite3.Connection) -> dict[str, int]:
    values = {**DEFAULTS, **custom(conn)}
    return values if ordered(values) else dict(DEFAULTS)


def need_for(rank_code: str, values: dict[str, int]) -> tuple[int, int]:
    if rank_code == DEFAULT_RANK:
        return 0, 0
    key = rank_code.lower()
    return values[f"{key}_orders"], values[f"{key}_vnd"]


# --- Tháng ------------------------------------------------------------------------------------


def _month(now: datetime, shift: int = 0) -> tuple[int, int]:
    local = now.astimezone(ICT)
    index = local.year * 12 + local.month - 1 + shift
    return index // 12, index % 12 + 1


def _month_key(now: datetime, shift: int = 0) -> str:
    year, month = _month(now, shift)
    return f"{year:04d}-{month:02d}"


def _month_start_utc(now: datetime, shift: int = 0) -> str:
    year, month = _month(now, shift)
    return datetime(year, month, 1, tzinfo=ICT).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def window_label(now: datetime) -> str:
    return f"tháng {_month(now, -1)[1]} và tháng {_month(now)[1]}"


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Sổ hạng ----------------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _row(conn: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    row = conn.execute("SELECT rank_code, reason FROM member_ranks WHERE user_id = ?", (user_id,)).fetchone()
    return (row[0], row[1]) if row else (DEFAULT_RANK, "mac_dinh")


def rank_of(conn: sqlite3.Connection, user_id: int) -> str:
    return _row(conn, user_id)[0]


def _set(conn: sqlite3.Connection, user_id: int, old: str | None, new: str, reason: str, at: str) -> None:
    conn.execute("INSERT INTO member_ranks (user_id, rank_code, reason, since) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET rank_code = excluded.rank_code, reason = excluded.reason, "
                 "since = excluded.since", (user_id, new, reason, at))
    conn.execute("INSERT INTO member_rank_events (user_id, from_code, to_code, reason, at) VALUES (?, ?, ?, ?, ?)",
                 (user_id, old, new, reason, at))


def _state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _put_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO bot_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def _protected(reason: str, review_month: str) -> bool:
    return reason == "khach_cu" and review_month < GRANDFATHER_FIRST_REVIEW


def seed_existing(conn: sqlite3.Connection, now: datetime) -> int:
    """Lần đầu bật hạng: mọi khách đã biết (Telegram, Zalo, đã tạo link) lên Vàng. Chạy lại không làm gì."""
    ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if _state(conn, SEEDED_KEY):
            conn.execute("COMMIT")
            return 0
        at = _stamp(now)
        users = [row[0] for row in conn.execute(
            "SELECT telegram_user_id FROM telegram_users UNION SELECT internal_user_id FROM channel_identities "
            "UNION SELECT telegram_user_id FROM link_requests")]
        count = 0
        for user_id in users:
            if conn.execute("SELECT 1 FROM member_ranks WHERE user_id = ?", (user_id,)).fetchone():
                continue
            _set(conn, int(user_id), None, "GOLD", "khach_cu", at)
            count += 1
        _put_state(conn, SEEDED_KEY, at)
        # Tháng bật hạng coi như đã xét: lần xét đầu là đầu tháng sau.
        _put_state(conn, REVIEWED_KEY, _month_key(now))
        conn.execute("COMMIT")
        return count
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def share_bps(rank_code: str, rates: dict[str, int], cap_bps: int) -> int:
    """Tỷ lệ của hạng, không vượt tỷ lệ chia chung đang áp dụng."""
    return min(int(rates[rank_code]), cap_bps)


def _totals(conn: sqlite3.Connection, user_id: int, start: str, end: str | None = None) -> tuple[int, int]:
    sql = (f"SELECT COUNT(DISTINCT COALESCE(order_sn, conversion_id)), COALESCE(SUM(cashback_vnd), 0) "
           f"FROM cashback_entries WHERE telegram_user_id = ? AND {_COUNTED} AND completed_at >= ?")
    args: list = [user_id, start]
    if end is not None:
        sql += " AND completed_at < ?"
        args.append(end)
    row = conn.execute(sql, args).fetchone()
    return int(row[0]), int(row[1])


def earned(orders: int, cashback_vnd: int, values: dict[str, int]) -> str:
    for code in reversed(ORDER[1:]):
        need_orders, need_vnd = need_for(code, values)
        if orders >= need_orders and cashback_vnd >= need_vnd:
            return code
    return DEFAULT_RANK


def progress(conn: sqlite3.Connection, user_id: int, now: datetime) -> Progress:
    """Hạng và số của cửa sổ đang chạy (tháng trước + tháng này): cũng là số sẽ xét đầu tháng sau."""
    values = thresholds(conn)
    code, reason = _row(conn, user_id)
    orders, cashback = _totals(conn, user_id, _month_start_utc(now, -1))
    protected = GRANDFATHER_UNTIL_TEXT if _protected(reason, _month_key(now, 1)) else None
    keep_orders, keep_vnd = need_for(code, values)
    keep = (max(0, keep_orders - orders), max(0, keep_vnd - cashback))
    if code == ORDER[-1]:
        return Progress(code, orders, cashback, window_label(now), None, 0, 0, *keep, protected)
    target = ORDER[ORDER.index(code) + 1]
    need_orders, need_vnd = need_for(target, values)
    return Progress(code, orders, cashback, window_label(now), target, max(0, need_orders - orders),
                    max(0, need_vnd - cashback), *keep, protected)


# --- Xét hạng ---------------------------------------------------------------------------------


def _review(conn: sqlite3.Connection, now: datetime, values: dict[str, int], at: str) -> list[Change]:
    """Đầu tháng: xét theo 2 tháng vừa qua. Không đủ hạng đang có thì xuống một bậc. Mỗi tháng một lần."""
    month = _month_key(now)
    if _state(conn, REVIEWED_KEY) == month:
        return []
    start, end = _month_start_utc(now, -2), _month_start_utc(now)
    done: list[Change] = []
    for user_id, code, reason in conn.execute(
            "SELECT user_id, rank_code, reason FROM member_ranks WHERE rank_code != ?", (DEFAULT_RANK,)).fetchall():
        if _protected(reason, month):
            continue
        got = earned(*_totals(conn, user_id, start, end), values)
        if ORDER.index(got) >= ORDER.index(code):
            continue
        lower = ORDER[max(ORDER.index(got), ORDER.index(code) - 1)]
        _set(conn, int(user_id), code, lower, "xet_thang", at)
        done.append(Change(int(user_id), "down", code, lower))
    _put_state(conn, REVIEWED_KEY, month)
    return done


def _promote(conn: sqlite3.Connection, now: datetime, values: dict[str, int], at: str) -> list[Change]:
    """Đủ ngưỡng trong tháng trước + tháng này thì lên ngay. Chỉ lên, không hạ."""
    start = _month_start_utc(now, -1)
    done: list[Change] = []
    users = [row[0] for row in conn.execute(
        f"SELECT DISTINCT telegram_user_id FROM cashback_entries WHERE {_COUNTED} AND completed_at >= ?", (start,))]
    for user_id in users:
        current = rank_of(conn, user_id)
        got = earned(*_totals(conn, user_id, start), values)
        if ORDER.index(got) <= ORDER.index(current):
            continue
        _set(conn, int(user_id), current, got, "du_nguong", at)
        done.append(Change(int(user_id), "up", current, got))
    return done


def _remind(conn: sqlite3.Connection, now: datetime, values: dict[str, int]) -> list[Change]:
    """Từ ngày 24: nhắc một lần mỗi tháng khách mà lần xét tới sẽ xuống hạng nếu không mua thêm."""
    month = _month_key(now)
    if now.astimezone(ICT).day < REMIND_DAY or _state(conn, REMINDED_KEY) == month:
        return []
    start = _month_start_utc(now, -1)
    done: list[Change] = []
    for user_id, code, reason in conn.execute(
            "SELECT user_id, rank_code, reason FROM member_ranks WHERE rank_code != ?", (DEFAULT_RANK,)).fetchall():
        if _protected(reason, _month_key(now, 1)):
            continue
        orders, cashback = _totals(conn, user_id, start)
        if ORDER.index(earned(orders, cashback, values)) >= ORDER.index(code):
            continue
        keep_orders, keep_vnd = need_for(code, values)
        done.append(Change(int(user_id), "keep", code, code, max(0, keep_orders - orders), max(0, keep_vnd - cashback)))
    _put_state(conn, REMINDED_KEY, month)
    return done


def tick(conn: sqlite3.Connection, now: datetime) -> list[Change]:
    """Một lượt: xét tháng (nếu sang tháng mới), lên hạng, nhắc giữ hạng. Gọi lúc khởi động và sau mỗi lần cập nhật ví."""
    # Đang trong transaction của người gọi thì ghi chung transaction đó, người gọi commit.
    own = not conn.in_transaction
    if own:
        conn.execute("BEGIN IMMEDIATE")
    try:
        values, at = thresholds(conn), _stamp(now)
        changes = _review(conn, now, values, at) + _promote(conn, now, values, at) + _remind(conn, now, values)
        if own:
            conn.execute("COMMIT")
        return changes
    except BaseException:
        if own:
            conn.execute("ROLLBACK")
        raise


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Số khách đang ở Bạc / Vàng (Đồng là mọi khách còn lại)."""
    return {code: n for code, n in conn.execute("SELECT rank_code, COUNT(*) FROM member_ranks GROUP BY rank_code")}
