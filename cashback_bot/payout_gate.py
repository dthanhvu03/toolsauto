"""Khoá tài chính (Production Safety Hardening V1).

Không phát sinh nghĩa vụ chi trả khi chưa có bằng chứng Shopee đã duyệt và đã trả tiền:

- `readiness`: điều kiện cả hệ thống. Cần bảng bằng chứng kỳ Shopee đã thanh toán và bảng chính sách
  thuế người nhận đã duyệt, mỗi bảng ít nhất một dòng. Hai bảng này chưa có trên production
  (DDL nháp ở `migrations/007_settlement_evidence.DRAFT.sql`), nên mặc định luôn KHOÁ.
- `entry_payable`: điều kiện từng khoản. Không gian lận, có tháng duyệt, tháng đó đã nằm trong
  một kỳ Shopee đã trả.
- `payout_headroom`: tổng đã chi + đang yêu cầu không vượt tổng tiền Shopee đã trả.

Không có công tắc nào để admin bỏ qua. Trigger SQLite trong `db.SCHEMA` chặn thêm ở tầng DB.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from cashback_bot.db import TrackingRepository

SETTLEMENT_TABLE = "shopee_settlements"
TAX_POLICY_TABLE = "payout_tax_policies"

REASON_SETTLEMENT = "Chưa có bằng chứng kỳ Shopee đã thanh toán hoa hồng (đối soát tiền về)."
REASON_TAX = "Chưa chốt chính sách thuế cho người nhận tiền hoàn."


class PayoutBlocked(RuntimeError):
    """Thao tác chi trả bị khoá tài chính chặn. `reason` là chữ cho admin."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Readiness:
    ok: bool
    reasons: tuple[str, ...]


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _has_rows(conn: sqlite3.Connection, table: str, tables: set[str]) -> bool:
    if table not in tables:
        return False
    return conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None


def is_fraud(raw_json: str | None) -> bool:
    """Shopee gắn cờ gian lận trên từng món: `is_fraud=1` hoặc có `fraud_reason` (đơn 23/09 là ví dụ thật).

    Không đọc được raw thì coi như chưa chứng minh sạch: trả True (không cho chi).
    """
    if not raw_json:
        return True
    try:
        data = json.loads(raw_json)
    except ValueError:
        return True
    order = data.get("order") if isinstance(data, dict) else None
    items = order.get("items") if isinstance(order, dict) else None
    if not isinstance(items, list):
        return True
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("is_fraud") or "0") not in ("0", "") or item.get("fraud_reason"):
            return True
    return False


class FinancialGate:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo

    def readiness(self, conn: sqlite3.Connection | None = None) -> Readiness:
        if conn is None:
            with self.repo.connect() as own:
                return self.readiness(own)
        tables = _tables(conn)
        reasons = []
        if not _has_rows(conn, SETTLEMENT_TABLE, tables):
            reasons.append(REASON_SETTLEMENT)
        if not _has_rows(conn, TAX_POLICY_TABLE, tables):
            reasons.append(REASON_TAX)
        return Readiness(not reasons, tuple(reasons))

    def entry_payable(self, conn: sqlite3.Connection, validation_month: str | None, raw_json: str | None) -> bool:
        """Khoản này đã được Shopee duyệt và trả chưa. Thiếu bất kỳ bằng chứng nào thì False."""
        if not self.readiness(conn).ok or not validation_month or is_fraud(raw_json):
            return False
        row = conn.execute(
            f"SELECT 1 FROM {SETTLEMENT_TABLE} WHERE period >= ? LIMIT 1", (str(validation_month)[:7],)
        ).fetchone()
        return row is not None

    def payout_headroom(self, conn: sqlite3.Connection) -> int:
        """Tiền Shopee đã trả − đã chi − đang yêu cầu. Chưa có bảng bằng chứng thì 0."""
        if SETTLEMENT_TABLE not in _tables(conn):
            return 0
        settled = int(conn.execute(f"SELECT COALESCE(SUM(amount_vnd), 0) FROM {SETTLEMENT_TABLE}").fetchone()[0])
        spent = int(
            conn.execute(
                "SELECT COALESCE(SUM(amount_vnd), 0) FROM cashback_payouts WHERE status IN ('paid', 'requested')"
            ).fetchone()[0]
        )
        return settled - spent

    def check_withdrawal(self, conn: sqlite3.Connection, amount_vnd: int) -> str | None:
        """None nếu được tạo yêu cầu rút. Ngược lại là mã lỗi: locked / fund."""
        if not self.readiness(conn).ok:
            return "locked"
        if self.payout_headroom(conn) < amount_vnd:
            return "fund"
        return None

    def check_payout(self, conn: sqlite3.Connection, amount_vnd: int) -> None:
        """Ném PayoutBlocked nếu không được xác nhận đã chuyển khoản yêu cầu này (đã nằm trong 'requested')."""
        readiness = self.readiness(conn)
        if not readiness.ok:
            raise PayoutBlocked(" ".join(readiness.reasons))
        settled_left = self.payout_headroom(conn)
        # Yêu cầu đang xét đã tính trong 'requested'; chỉ cần phần còn lại không âm.
        if settled_left < 0:
            raise PayoutBlocked(f"Tổng chi vượt tiền Shopee đã trả {abs(settled_left):,}đ.".replace(",", "."))
        if amount_vnd <= 0:
            raise PayoutBlocked("Số tiền yêu cầu không hợp lệ.")
