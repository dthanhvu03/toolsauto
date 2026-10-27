"""Dữ liệu /donhang và tuỳ chọn /thongbao (PLAN-079). Chỉ đọc đơn của đúng khách hỏi.

Đơn của khách = shopee_conversions có telegram_user_id của khách (người tạo link có Sub ID được ghi nhận).
Không trả raw Shopee, không trả dữ liệu người mua. Tiền hoàn lấy từ sổ ví nếu đã có, không thì tính theo snapshot.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot import policy_snapshot
from cashback_bot.order_notify import cashback_of, short_order

PAGE_SIZE = 5
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
PREF_KEYS = ("orders", "updates", "support", "wallet", "reminders")
INELIGIBLE = ("REJECTED", "FRAUD")


def _date(stamp: str | None) -> str:
    try:
        moment = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "-"
    return moment.astimezone(ICT).strftime("%d/%m/%Y")


def _cancelled(row) -> bool:
    return (row["order_status"] or "").upper() in ("CANCELLED", "CANCELED")


_SELECT = """
    SELECT c.conversion_id, c.order_sn, c.order_status, c.validation_status, c.settlement_status, c.created_at,
           c.purchase_time, c.net_commission_vnd, c.matched_link_id, l.sub_id, l.product_name,
           e.cashback_vnd AS entry_cashback, e.status AS entry_status
    FROM shopee_conversions c
    LEFT JOIN link_requests l ON l.id = c.matched_link_id
    LEFT JOIN cashback_entries e ON e.conversion_id = c.conversion_id
    WHERE c.telegram_user_id = ? AND c.matched_link_id IS NOT NULL
"""


def _view(conn: sqlite3.Connection, row) -> dict:
    cashback = row["entry_cashback"]
    if cashback is None:
        cashback = cashback_of(conn, row["matched_link_id"], row["net_commission_vnd"])
    if _cancelled(row) or row["validation_status"] in INELIGIBLE:
        cashback = None if row["entry_cashback"] is None else int(row["entry_cashback"])
    found = policy_snapshot.load(conn, int(row["matched_link_id"])) if row["matched_link_id"] else None
    policy = "chưa xác định" if found is None or found.policy is None else found.policy.pricing_version.upper()
    return {
        "conversion_id": str(row["conversion_id"]),
        "order": short_order(row["order_sn"], str(row["conversion_id"])),
        # Ngày mua theo Shopee; thiếu thì ngày bot ghi nhận.
        "date": _date(row["purchase_time"] or row["created_at"]),
        # Tên sản phẩm của link khách tự gửi (link_requests), không phải dữ liệu người mua.
        "product": row["product_name"],
        "order_status": row["order_status"],
        "validation_status": row["validation_status"],
        "settlement_status": row["settlement_status"],
        "cashback": None if cashback is None else int(cashback),
        "sub_id": row["sub_id"],
        "policy": policy,
        "entry_status": row["entry_status"],
    }


def summary(conn: sqlite3.Connection, user_id: int) -> dict:
    rows = conn.execute(_SELECT, (user_id,)).fetchall()
    stats = {"total": len(rows), "waiting": 0, "approved": 0, "ineligible": 0, "estimated": 0, "available": 0}
    for row in rows:
        if _cancelled(row) or row["validation_status"] in INELIGIBLE:
            stats["ineligible"] += 1
            continue
        if row["validation_status"] == "APPROVED":
            stats["approved"] += 1
        else:
            stats["waiting"] += 1
        if row["entry_status"] == "available":
            stats["available"] += 1
        elif row["entry_status"] in ("pending", "holding") and row["entry_cashback"] is not None:
            stats["estimated"] += int(row["entry_cashback"])
    return stats


def page(conn: sqlite3.Connection, user_id: int, number: int) -> tuple[list[dict], int, int]:
    """(đơn của trang, trang hiện tại, số trang). Mới nhất trước, PAGE_SIZE mỗi trang."""
    total = int(conn.execute(
        "SELECT COUNT(*) FROM shopee_conversions WHERE telegram_user_id = ? AND matched_link_id IS NOT NULL", (user_id,)
    ).fetchone()[0])
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    number = min(max(1, number), pages)
    rows = conn.execute(
        _SELECT + " ORDER BY COALESCE(c.purchase_time, c.created_at) DESC, c.conversion_id DESC LIMIT ? OFFSET ?",
        (user_id, PAGE_SIZE, (number - 1) * PAGE_SIZE),
    ).fetchall()
    return [_view(conn, row) for row in rows], number, pages


def detail(conn: sqlite3.Connection, user_id: int, conversion_id: str) -> dict | None:
    """Đơn chỉ trả cho đúng chủ. Đổi mã đơn trong nút cũng không xem được đơn người khác."""
    row = conn.execute(_SELECT + " AND c.conversion_id = ?", (user_id, conversion_id)).fetchone()
    return None if row is None else _view(conn, row)


def prefs(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM customer_notification_prefs WHERE telegram_user_id = ?", (user_id,)).fetchone()
    return {key: True if row is None else bool(row[key]) for key in PREF_KEYS}


def toggle(conn: sqlite3.Connection, user_id: int, key: str, now: str) -> dict:
    if key not in PREF_KEYS:
        raise ValueError(key)
    current = prefs(conn, user_id)
    current[key] = not current[key]
    conn.execute(
        """
        INSERT INTO customer_notification_prefs (telegram_user_id, orders, updates, support, wallet, reminders, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET orders = excluded.orders, updates = excluded.updates,
            support = excluded.support, wallet = excluded.wallet, reminders = excluded.reminders,
            updated_at = excluded.updated_at
        """,
        (user_id, *(int(current[k]) for k in PREF_KEYS), now),
    )
    return current
