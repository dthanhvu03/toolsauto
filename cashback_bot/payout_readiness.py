"""Điều kiện chi trả của PLAN-078, cộng thêm vào khoá tài chính cũ (không thay nó).

Ba cấp:
- hệ thống (mở ví): quyết định chính sách đã duyệt cho từng chủ đề, hạn mức ACTIVE có người duyệt, ít nhất một
  kỳ đối soát MATCHED (quỹ có chứng từ), backup gần đây.
- khách (tạo yêu cầu): đã đồng ý bản điều khoản chứa điều kiện chi trả (khi chủ đề payout_terms đã duyệt).
- từng yêu cầu (đưa tiền ra): tài khoản nhận tiền đã xác minh, quỹ còn đủ, trong hạn mức.
Chỉ đọc dữ liệu thật trong DB. Không có công tắc bỏ qua; test dựng dữ liệu trong DB test.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime

from cashback_bot import payouts

BACKUP_MAX_AGE_SEC = 48 * 3600
TOPIC_LABELS = {
    "tax": "Chính sách thuế khi chi cho người nhận",
    "clawback": "Chính sách khi Shopee thu hồi hoa hồng đã chi",
    "payout_terms": "Điều khoản chi trả đã công bố",
    "bank_verification": "Cách xác minh tài khoản nhận tiền",
    "payment_limits": "Hạn mức rút",
    "manual_payment": "Quy trình chuyển khoản thủ công và chứng từ",
}


@dataclass(frozen=True)
class Condition:
    code: str
    label: str
    ok: bool
    scope: str  # system | user | payout


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def system_conditions(conn: sqlite3.Connection, now: float | None = None) -> list[Condition]:
    if not _table(conn, "payout_policy_decisions"):
        return [Condition("schema", "Chưa có bảng chính sách chi trả (chưa chạy migration PLAN-078)", False, "system")]
    result = []
    for topic, label in TOPIC_LABELS.items():
        row = payouts.decision(conn, topic)
        result.append(Condition(f"decision_{topic}", label, row is not None and row["status"] == "APPROVED", "system"))
    result.append(Condition("limits_active", "Hạn mức rút đang hiệu lực (có người duyệt)",
                            payouts.active_limits(conn) is not None, "system"))
    result.append(Condition("settlement_matched", "Ít nhất một kỳ Shopee đối soát khớp (quỹ có chứng từ)",
                            payouts.fund_position(conn).verified, "system"))
    row = conn.execute("SELECT value FROM bot_state WHERE key = 'backup_last_ok'").fetchone()
    try:
        age = (now or time.time()) - float(row[0]) if row else None
    except ValueError:
        age = None
    result.append(Condition("backup_recent", "Backup DB trong 48 giờ gần nhất", age is not None and age <= BACKUP_MAX_AGE_SEC, "system"))
    return result


def system_reasons(conn: sqlite3.Connection) -> list[str]:
    return [f"Chưa đạt: {item.label}." for item in system_conditions(conn) if not item.ok]


def payout_terms_version(conn: sqlite3.Connection) -> str | None:
    """Phiên bản điều khoản chứa điều kiện chi trả, theo quyết định payout_terms đã duyệt (cột reference)."""
    row = payouts.decision(conn, "payout_terms")
    return str(row["reference"]) if row is not None and row["status"] == "APPROVED" else None


def user_conditions(conn: sqlite3.Connection, user_id: int) -> list[Condition]:
    version = payout_terms_version(conn)
    accepted = False
    if version is not None:
        accepted = conn.execute(
            """
            SELECT 1 FROM customer_terms_acceptances a JOIN customer_terms_versions v ON v.id = a.terms_version_id
            WHERE a.telegram_user_id = ? AND v.version = ? AND v.status = 'PUBLISHED'
            """,
            (user_id, version),
        ).fetchone() is not None
    return [Condition("payout_terms_accepted", "Khách đã đồng ý điều khoản chi trả", accepted, "user")]


def payout_conditions(conn: sqlite3.Connection, row: sqlite3.Row, now: datetime) -> list[Condition]:
    status = payouts.bank_status(conn, int(row["telegram_user_id"]), row["account_sha"])
    fund = payouts.fund_position(conn)
    limit = payouts.check_limits(conn, int(row["amount_vnd"]), now, exclude_id=int(row["id"]))
    return [
        Condition("bank_verified", "Tài khoản nhận tiền đã xác minh (không phải chỉ tạo được QR)", status == "VERIFIED", "payout"),
        Condition("fund", "Quỹ có chứng từ còn đủ cho yêu cầu này", fund.verified and fund.headroom_vnd >= 0, "payout"),
        Condition("limits", "Trong hạn mức rút", limit is None, "payout"),
    ]
