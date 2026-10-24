"""Yêu cầu hỗ trợ / khiếu nại V1 (PLAN-077).

Khách mở ticket theo danh mục, có hoặc không có đơn. Admin đổi trạng thái theo bảng cho phép, trả lời qua bot,
kết luận phải có lý do. Mọi thay đổi ghi vào support_ticket_events (chỉ thêm).
Ticket không có đường nào đổi hoa hồng, trạng thái duyệt/đối soát, sổ ví hay payout. Không có hẹn giờ tự đóng
hay tự từ chối: WAITING_SHOPEE giữ nguyên tới khi admin cập nhật.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from cashback_bot.redact import redact

MAX_MESSAGE = 1_000
CATEGORIES = {
    "missing": "📦 Không thấy đơn",
    "amount": "💰 Số hoàn không đúng",
    "wrong_link": "🔗 Ghi nhận sai link / sai người",
    "slow": "🕘 Đơn chờ xác minh quá lâu",
    "privacy": "🛡 Dữ liệu cá nhân",
    "other": "❓ Vấn đề khác",
}
STATUS_LABELS = {
    "OPEN": "🆕 Mới",
    "IN_REVIEW": "🔎 Đang xử lý",
    "WAITING_CUSTOMER": "💬 Chờ bạn bổ sung",
    "WAITING_SHOPEE": "⏳ Chờ Shopee",
    "RESOLVED": "✅ Đã giải quyết",
    "REJECTED": "✖️ Không chấp nhận",
    "CLOSED": "🔒 Đã đóng",
}
FINAL = {"RESOLVED", "REJECTED", "CLOSED"}
# Kết luận phải có lý do. Chuyển sang chờ hoặc đang xử lý thì lý do không bắt buộc.
NEEDS_REASON = {"RESOLVED", "REJECTED", "CLOSED", "WAITING_SHOPEE"}
TRANSITIONS = {
    "OPEN": {"IN_REVIEW", "WAITING_CUSTOMER", "WAITING_SHOPEE", "RESOLVED", "REJECTED", "CLOSED"},
    "IN_REVIEW": {"WAITING_CUSTOMER", "WAITING_SHOPEE", "RESOLVED", "REJECTED", "CLOSED"},
    "WAITING_CUSTOMER": {"IN_REVIEW", "WAITING_SHOPEE", "RESOLVED", "REJECTED", "CLOSED"},
    "WAITING_SHOPEE": {"IN_REVIEW", "WAITING_CUSTOMER", "RESOLVED", "REJECTED", "CLOSED"},
    "RESOLVED": {"CLOSED"},
    "REJECTED": {"CLOSED"},
    "CLOSED": set(),
}
# Mã theo dõi bot tạo (affiliate.new_sub_id) và mã đơn Shopee hay gặp. Chỉ gắn khi thuộc đúng khách.
_SUB_ID = re.compile(r"\b[0-9A-Za-z]{8}\b")
_ORDER_SN = re.compile(r"\b\d{6}[0-9A-Z]{8}\b")
# Dãy 13–19 chữ số (có thể cách bằng dấu cách/gạch) trông như số thẻ: chỉ giữ 4 số cuối.
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


class SupportError(ValueError):
    """Thao tác ticket không hợp lệ. Mã lỗi ở args[0]."""


@dataclass(frozen=True)
class Ticket:
    id: int
    telegram_user_id: int
    category: str
    link_id: int | None
    conversion_id: str | None
    message: str
    status: str
    resolution: str | None
    created_at: str
    updated_at: str


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(text: str, limit: int = MAX_MESSAGE) -> str:
    """Bỏ ký tự điều khiển, che token/cookie, cắt độ dài. Không lưu nguyên văn bí mật khách lỡ dán."""
    value = "".join(ch for ch in (text or "") if ch == "\n" or ch >= " ").strip()
    value = redact(value)
    value = _CARD.sub(lambda m: "••••" + re.sub(r"\D", "", m.group(0))[-4:], value)
    return value[:limit]


def _ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        int(row["id"]), int(row["telegram_user_id"]), str(row["category"]), row["link_id"], row["conversion_id"],
        str(row["message"]), str(row["status"]), row["resolution"], str(row["created_at"]), str(row["updated_at"]),
    )


def _event(conn, ticket_id: int, actor: str, action: str, before: str | None, after: str | None,
           note: str | None, now: datetime, source_update_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO support_ticket_events
            (ticket_id, actor, action, from_status, to_status, note, source_update_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticket_id, actor, action, before, after, note, source_update_id, _stamp(now)),
    )


def _own_references(conn: sqlite3.Connection, user_id: int, text: str) -> tuple[int | None, str | None]:
    """Link / đơn của chính khách được nhắc trong nội dung. Không gắn dữ liệu của người khác."""
    link_id = conversion_id = None
    for code in _SUB_ID.findall(text):
        row = conn.execute(
            "SELECT id FROM link_requests WHERE sub_id = ? AND telegram_user_id = ?", (code, user_id)
        ).fetchone()
        if row is not None:
            link_id = int(row[0])
            break
    for order in _ORDER_SN.findall(text):
        row = conn.execute(
            "SELECT conversion_id, matched_link_id FROM shopee_conversions WHERE order_sn = ? AND telegram_user_id = ?",
            (order, user_id),
        ).fetchone()
        if row is not None:
            conversion_id = str(row[0])
            link_id = link_id or row[1]
            break
    return link_id, conversion_id


def open_ticket(
    conn: sqlite3.Connection, user_id: int, category: str, text: str, now: datetime, source_update_id: int | None
) -> tuple[Ticket, bool]:
    """Tạo ticket. Trả (ticket, mới tạo?). Cùng update Telegram gửi lại thì trả ticket cũ."""
    if category not in CATEGORIES:
        raise SupportError("category")
    message = clean_text(text)
    if not message:
        raise SupportError("empty")
    if source_update_id is not None:
        old = conn.execute("SELECT * FROM support_tickets WHERE source_update_id = ?", (source_update_id,)).fetchone()
        if old is not None:
            return _ticket(old), False
    link_id, conversion_id = _own_references(conn, user_id, message)
    stamp = _stamp(now)
    cursor = conn.execute(
        """
        INSERT INTO support_tickets (telegram_user_id, category, link_id, conversion_id, message, status,
            source_update_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
        """,
        (user_id, category, link_id, conversion_id, message, source_update_id, stamp, stamp),
    )
    ticket_id = int(cursor.lastrowid)
    _event(conn, ticket_id, f"user:{user_id}", "open", None, "OPEN", None, now)
    return get(conn, ticket_id), True  # type: ignore[return-value]


def get(conn: sqlite3.Connection, ticket_id: int) -> Ticket | None:
    row = conn.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)).fetchone()
    return None if row is None else _ticket(row)


def get_for_user(conn: sqlite3.Connection, ticket_id: int, user_id: int) -> Ticket | None:
    """Ticket chỉ trả cho đúng chủ ticket. Khách khác nhận None như không tồn tại."""
    found = get(conn, ticket_id)
    return found if found is not None and found.telegram_user_id == user_id else None


def user_tickets(conn: sqlite3.Connection, user_id: int, limit: int = 5) -> list[Ticket]:
    rows = conn.execute(
        "SELECT * FROM support_tickets WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    ).fetchall()
    return [_ticket(row) for row in rows]


def by_status(conn: sqlite3.Connection, statuses: tuple[str, ...], limit: int = 10) -> list[Ticket]:
    marks = ", ".join("?" for _ in statuses)
    rows = conn.execute(
        f"SELECT * FROM support_tickets WHERE status IN ({marks}) ORDER BY id DESC LIMIT ?", (*statuses, limit)
    ).fetchall()
    return [_ticket(row) for row in rows]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    result = {status: 0 for status in STATUS_LABELS}
    for status, count in conn.execute("SELECT status, COUNT(*) FROM support_tickets GROUP BY status"):
        result[str(status)] = int(count)
    return result


def events(conn: sqlite3.Connection, ticket_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM support_ticket_events WHERE ticket_id = ? ORDER BY id", (ticket_id,)
    ).fetchall()


def transition(conn: sqlite3.Connection, ticket_id: int, admin_id: int, target: str, note: str | None,
               now: datetime) -> Ticket:
    """Admin đổi trạng thái. Kết luận và chờ Shopee phải có lý do. Không đụng dữ liệu tiền."""
    found = get(conn, ticket_id)
    if found is None:
        raise SupportError("not_found")
    if target not in TRANSITIONS[found.status]:
        raise SupportError("transition")
    reason = clean_text(note or "", 500) or None
    if target in NEEDS_REASON and not reason:
        raise SupportError("reason")
    resolution = reason if target in FINAL and target != "CLOSED" else found.resolution
    conn.execute(
        """
        UPDATE support_tickets SET status = ?, assigned_to = ?, resolution = ?, updated_at = ?
        WHERE id = ? AND status = ?
        """,
        (target, admin_id, resolution, _stamp(now), ticket_id, found.status),
    )
    _event(conn, ticket_id, f"admin:{admin_id}", "status", found.status, target, reason, now)
    return get(conn, ticket_id)  # type: ignore[return-value]


def admin_reply(conn: sqlite3.Connection, ticket_id: int, admin_id: int, text: str, now: datetime) -> tuple[Ticket, str]:
    """Ghi câu trả lời admin gửi khách. Trả (ticket, nội dung đã làm sạch). Không đổi trạng thái."""
    found = get(conn, ticket_id)
    if found is None:
        raise SupportError("not_found")
    if found.status == "CLOSED":
        raise SupportError("closed")
    reply = clean_text(text)
    if not reply:
        raise SupportError("empty")
    _event(conn, ticket_id, f"admin:{admin_id}", "reply", found.status, found.status, reply, now)
    return found, reply


def customer_reply(conn: sqlite3.Connection, ticket_id: int, user_id: int, text: str, now: datetime,
                   source_update_id: int | None) -> Ticket:
    """Khách bổ sung thông tin. Ticket đang chờ khách thì quay lại Đang xử lý."""
    found = get_for_user(conn, ticket_id, user_id)
    if found is None:
        raise SupportError("not_found")
    if found.status in FINAL:
        raise SupportError("closed")
    if source_update_id is not None and conn.execute(
        "SELECT 1 FROM support_ticket_events WHERE source_update_id = ?", (source_update_id,)
    ).fetchone():
        return found
    message = clean_text(text)
    if not message:
        raise SupportError("empty")
    target = "IN_REVIEW" if found.status == "WAITING_CUSTOMER" else found.status
    conn.execute("UPDATE support_tickets SET status = ?, updated_at = ? WHERE id = ?", (target, _stamp(now), ticket_id))
    _event(conn, ticket_id, f"user:{user_id}", "customer_reply", found.status, target, message, now, source_update_id)
    return get(conn, ticket_id)  # type: ignore[return-value]
