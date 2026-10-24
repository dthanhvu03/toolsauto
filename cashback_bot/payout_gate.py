"""Khoá tài chính (Production Safety Hardening V1).

Không phát sinh nghĩa vụ chi trả khi chưa có bằng chứng Shopee đã duyệt và đã trả tiền:

- `readiness`: điều kiện cả hệ thống. Cần bảng bằng chứng kỳ Shopee đã thanh toán và bảng chính sách
  thuế người nhận đã duyệt, mỗi bảng ít nhất một dòng. Hai bảng này chưa có trên production
  (DDL nháp ở `migrations/007_settlement_evidence.DRAFT.sql`), nên mặc định luôn KHOÁ.
- `entry_payable`: điều kiện từng khoản. Không gian lận, có tháng duyệt, tháng đó đã nằm trong
  một kỳ Shopee đã trả, và link có snapshot chính sách chứng minh được (PLAN-077: link `unresolved`
  hoặc chưa có snapshot không bao giờ payable).
- `payout_headroom`: tổng đã chi + đang yêu cầu không vượt tổng tiền Shopee đã trả.

Không có công tắc nào để admin bỏ qua. Trigger SQLite trong `db.SCHEMA` chặn thêm ở tầng DB.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from cashback_bot import payout_readiness, payouts
from cashback_bot.commission_validation import APPROVED
from cashback_bot.db import TrackingRepository

SETTLEMENT_TABLE = "shopee_settlements"
TAX_POLICY_TABLE = "payout_tax_policies"

REASON_SETTLEMENT = "Chưa có bằng chứng kỳ Shopee đã thanh toán hoa hồng (đối soát tiền về)."
REASON_TAX = "Chưa chốt chính sách thuế cho người nhận tiền hoàn."
PROVEN_SNAPSHOTS = ("captured", "backfilled")


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


def proven_policy(conn: sqlite3.Connection, link_id: int | None) -> bool:
    """Link có snapshot chính sách đã ghi và dựng được (captured / backfilled). Thiếu hoặc unresolved: False.

    Không chứng minh được chính sách gốc thì không xác nhận được số tiền, nên không cho vào ví.
    """
    if link_id is None or "link_policy_snapshots" not in _tables(conn):
        return False
    row = conn.execute("SELECT provenance FROM link_policy_snapshots WHERE link_id = ?", (link_id,)).fetchone()
    return row is not None and row[0] in PROVEN_SNAPSHOTS


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
        # PLAN-078: cộng thêm điều kiện hệ thống mới (quyết định chính sách, hạn mức, kỳ đối soát khớp, backup).
        reasons.extend(payout_readiness.system_reasons(conn))
        return Readiness(not reasons, tuple(reasons))

    def entry_payable(
        self,
        conn: sqlite3.Connection,
        validation_month: str | None,
        raw_json: str | None,
        validation_status: str | None = None,
        link_id: int | None = None,
        settlement_status: str | None = None,
        conversion_id: str | None = None,
    ) -> bool:
        """Khoản này đã được Shopee duyệt và trả chưa. Thiếu bất kỳ bằng chứng nào thì False.

        PLAN-074: phải có validation_status = APPROVED (hiện chưa nguồn nào gán được). APPROVED vẫn chưa đủ:
        còn cần kỳ Shopee đã trả (settlement, PLAN-075).
        """
        if validation_status != APPROVED:
            return False
        if not proven_policy(conn, link_id):
            return False
        # PLAN-078: đơn phải nằm trong một kỳ đối soát khớp (tiền phân bổ tới đúng đơn) và không có điều chỉnh
        # chưa xử lý. Thiếu thì khoản ở «holding», không vào ví.
        if settlement_status != "SETTLED":
            return False
        if conversion_id is not None and conn.execute(
            "SELECT 1 FROM settlement_adjustments WHERE conversion_id = ? AND status = 'OPEN'", (conversion_id,)
        ).fetchone():
            return False
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
        # PLAN-078: mọi trạng thái còn giữ tiền và đã trả, không chỉ 'requested' / 'paid' cũ.
        reserved, paid = payouts.payout_totals(conn)
        return settled - reserved - paid

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
