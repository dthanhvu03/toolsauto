"""Khoá tài chính (Production Safety Hardening V1).

Không phát sinh nghĩa vụ chi trả khi chưa có bằng chứng Shopee đã duyệt và đã trả tiền:

- `readiness`: điều kiện cả hệ thống, đọc dữ liệu thật: ít nhất một kỳ đối soát MATCHED (báo cáo Shopee
  khớp tiền về ngân hàng, settlement.py) và quyết định thuế người nhận mới nhất APPROVED, cộng các điều kiện
  PLAN-078 (payout_readiness). Trước 2026-11-03 hai điều kiện đầu đọc bảng nháp `shopee_settlements` /
  `payout_tax_policies` (migration 007 không bao giờ chạy) nên khoá vĩnh viễn; chủ bot cho nối vào đối soát.
- `entry_payable`: điều kiện từng khoản. Đơn nằm trong kỳ MATCHED (SETTLED: Shopee đã duyệt và đã trả đúng
  đơn đó), không gian lận / bị từ chối, không có điều chỉnh mở, link có snapshot chính sách chứng minh được
  (PLAN-077: link `unresolved` hoặc chưa có snapshot không bao giờ payable).
- `payout_headroom`: quỹ chia được (phần đơn bot của các kỳ MATCHED trừ phí, thuế) − đang giữ − đã chi.

Không có công tắc nào để admin bỏ qua. Trigger SQLite trong `db.SCHEMA` chặn thêm ở tầng DB.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from cashback_bot import payout_readiness, payouts
from cashback_bot.commission_validation import FRAUD, REJECTED
from cashback_bot.db import TrackingRepository

REASON_SETTLEMENT = "Chưa có bằng chứng kỳ Shopee đã thanh toán hoa hồng (đối soát tiền về)."
REASON_TAX = "Chưa chốt chính sách thuế cho người nhận tiền hoàn."
_HEADLINE = {"settlement_matched": REASON_SETTLEMENT, "decision_tax": REASON_TAX}
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
        failed = [item for item in payout_readiness.system_conditions(conn) if not item.ok]
        codes = {item.code for item in failed}
        # Hai lý do gốc đứng đầu (màn admin, khách), rồi danh sách chi tiết PLAN-078.
        reasons = [_HEADLINE[code] for code in ("settlement_matched", "decision_tax") if code in codes]
        if "schema" in codes:  # chưa có bảng PLAN-078: chưa đọc được kỳ đối soát hay quyết định thuế
            reasons = [REASON_SETTLEMENT, REASON_TAX]
        reasons += [f"Chưa đạt: {item.label}." for item in failed]
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

        Báo cáo đơn Shopee không có trường nào chứng minh «đã duyệt» (commission_validation.py). Bằng chứng duyệt
        là đơn nằm trong một kỳ thanh toán MATCHED: Shopee chỉ đưa vào hoá đơn đối soát đơn đã duyệt, và tiền kỳ
        đó đã về ngân hàng. Vì vậy SETTLED thay cho APPROVED; đơn bị gắn gian lận / từ chối thì không bao giờ.
        `validation_month` giữ trong chữ ký cho bên gọi cũ, không còn dùng.
        """
        if validation_status in (FRAUD, REJECTED):
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
        return self.readiness(conn).ok and not is_fraud(raw_json)

    def payout_headroom(self, conn: sqlite3.Connection) -> int:
        """Quỹ chia được của các kỳ MATCHED (payouts.fund_position) − đang giữ cho yêu cầu rút − đã chi."""
        return payouts.fund_position(conn).headroom_vnd

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
