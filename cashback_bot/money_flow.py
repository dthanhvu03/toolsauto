"""Một ảnh chụp tiền cho mọi màn /admin (2026-11-03: chủ bot yêu cầu phần tiền một mối, đúng nghiệp vụ).

Dòng tiền:

    Đơn qua link bot ─▶ Shopee duyệt, gom vào KỲ THANH TOÁN ─▶ Shopee chuyển (hoa hồng − phí − thuế Shopee giữ)
    ─▶ TIỀN VỀ TÀI KHOẢN (anh xác nhận) = kỳ KHỚP ─▶ chia: TIỀN HOÀN của khách + PHẦN CỦA ANH

- Tiền hoàn của khách có 4 trạng thái: Chờ Shopee trả → Trong ví → Đang chờ chuyển → Đã chuyển.
  «Chờ Shopee trả» gồm cả đơn đã nằm trong kỳ khớp nhưng chưa đủ ngày giữ (tách riêng để anh thấy).
- Phần của anh: THỰC NHẬN (kỳ đã khớp, theo chứng từ: tiền về − tiền hoàn của đơn trong kỳ) và SẮP VỀ (kỳ chưa
  khớp, theo số Shopee báo). Phí và thuế cả kỳ trừ vào phần của anh; khách nhận đúng số đã báo.
- Quỹ chi trả: phần đơn bot của các kỳ khớp sau phí, thuế − đang chờ chuyển − đã chuyển (payouts.fund_position).
  Đây là trần chi cho khách, không phải tiền của anh.

Chỉ đọc. Mọi màn tiền đọc từ `snapshot()`, không tự tính lại.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from cashback_bot import payouts

CLAWBACK_TAG = ":clawback:"
# Dòng thưởng mời bạn «<id>:ref» (PLAN-155): phần chi cho khách của chính đơn đó.
REF_TAG = ":ref"
MATCHED = "MATCHED"

# Tên gọi tiền dùng chung cho admin, khách (Telegram, Zalo) và web. Đổi chữ ở đây, không viết lại ở từng màn.
WAIT_SHOPEE = "Chờ Shopee trả"
WAIT_HOLD = "Chờ đủ ngày giữ"
IN_WALLET = "Trong ví"
OWED_BACK = "Đang trừ lại"
RESERVED = "Đang chờ chuyển"
PAID_OUT = "Đã chuyển"
FUND_LEFT = "Quỹ chi trả còn"
OWNER_REAL = "Thực nhận"
OWNER_SOON = "Sắp về"


@dataclass(frozen=True)
class Period:
    """Một kỳ thanh toán Shopee. Số None: chứng từ chưa có số đó."""

    batch_id: int
    period: str
    status: str
    payment_ref: str | None
    commission_vnd: int | None  # hoa hồng Shopee báo (gồm điều chỉnh), trước phí / thuế
    fee_vnd: int | None  # phí dịch vụ + VAT chưa gồm
    tax_vnd: int | None  # thuế Shopee giữ (TNCN + VAT)
    payout_vnd: int | None  # Shopee báo chuyển
    received_vnd: int | None  # tiền về tài khoản (anh xác nhận)
    bot_commission_vnd: int  # hoa hồng đơn qua bot, trước phí / thuế
    own_commission_vnd: int  # đơn ngoài bot (đơn riêng của anh) + không rõ đơn
    customer_vnd: int  # tiền hoàn đã ghi sổ của đơn bot trong kỳ (gồm dòng trừ lại, bỏ khoản huỷ)

    @property
    def matched(self) -> bool:
        return self.status == MATCHED

    @property
    def amount_vnd(self) -> int | None:
        """Tiền của kỳ: đã về thì số về tài khoản, chưa về thì số Shopee báo chuyển."""
        return self.received_vnd if self.received_vnd is not None else self.payout_vnd

    @property
    def owner_vnd(self) -> int | None:
        """Phần của anh trong kỳ = tiền của kỳ − tiền hoàn của khách."""
        return None if self.amount_vnd is None else self.amount_vnd - self.customer_vnd


@dataclass(frozen=True)
class Customers:
    """Tiền hoàn của mọi khách tại lúc này."""

    waiting_shopee_vnd: int  # đơn chưa nằm trong kỳ khớp
    waiting_hold_vnd: int  # đơn đã trong kỳ khớp, chưa đủ ngày giữ
    in_wallet_vnd: int  # rút được (tổng số dư dương)
    owed_back_vnd: int  # khách đang âm vì Shopee trừ lại (số dương)
    reserved_vnd: int  # đang chờ chuyển (yêu cầu rút còn mở)
    paid_vnd: int  # đã chuyển
    open_requests: int

    @property
    def waiting_vnd(self) -> int:
        return self.waiting_shopee_vnd + self.waiting_hold_vnd


@dataclass(frozen=True)
class Snapshot:
    periods: tuple[Period, ...]  # mọi kỳ chưa đảo, cũ → mới
    customers: Customers
    fund: payouts.FundPosition
    open_adjustments: int

    @property
    def settled(self) -> tuple[Period, ...]:
        return tuple(p for p in self.periods if p.matched)

    @property
    def upcoming(self) -> tuple[Period, ...]:
        return tuple(p for p in self.periods if not p.matched)

    def _sum(self, field: str) -> int:
        return sum(getattr(p, field) or 0 for p in self.settled)

    @property
    def commission_vnd(self) -> int:
        return self._sum("commission_vnd")

    @property
    def fee_vnd(self) -> int:
        return self._sum("fee_vnd")

    @property
    def tax_vnd(self) -> int:
        return self._sum("tax_vnd")

    @property
    def received_vnd(self) -> int:
        return self._sum("received_vnd")

    @property
    def bot_commission_vnd(self) -> int:
        return self._sum("bot_commission_vnd")

    @property
    def own_commission_vnd(self) -> int:
        return self._sum("own_commission_vnd")

    @property
    def customer_vnd(self) -> int:
        """Tiền hoàn của khách cho đơn trong các kỳ đã khớp."""
        return self._sum("customer_vnd")

    @property
    def owner_vnd(self) -> int:
        """Thực nhận của anh = tiền về tài khoản − tiền hoàn của khách (các kỳ đã khớp)."""
        return self.received_vnd - self.customer_vnd

    @property
    def upcoming_owner_vnd(self) -> int:
        return sum(p.owner_vnd or 0 for p in self.upcoming)


def _items(conn: sqlite3.Connection, batch: sqlite3.Row) -> list[sqlite3.Row]:
    """Dòng của báo cáo Shopee hiện hành (chứng từ bị thay vẫn giữ dòng cũ, không đếm)."""
    return conn.execute(
        "SELECT match_status, is_bot, conversion_id, settled_vnd, adjustment_vnd FROM settlement_items "
        "WHERE batch_id = ? AND evidence_id = ?",
        (batch["id"], batch["statement_evidence_id"]),
    ).fetchall()


def _entry_totals(conn: sqlite3.Connection) -> dict[str, int]:
    """Tiền hoàn chưa huỷ theo đơn gốc (dòng trừ lại «<id>:clawback:<n>» và thưởng mời bạn «<id>:ref» cộng vào đơn gốc)."""
    totals: dict[str, int] = {}
    for row in conn.execute("SELECT conversion_id, cashback_vnd FROM cashback_entries WHERE status != 'cancelled'"):
        key = str(row["conversion_id"]).split(CLAWBACK_TAG)[0].split(REF_TAG)[0]
        totals[key] = totals.get(key, 0) + int(row["cashback_vnd"])
    return totals


def _period(conn: sqlite3.Connection, batch: sqlite3.Row, cashback: dict[str, int]) -> Period:
    commission = None
    if batch["reported_commission_vnd"] is not None:
        commission = int(batch["reported_commission_vnd"]) + int(batch["adjustments_vnd"] or 0)
    fee = None
    if batch["fee_vnd"] is not None:
        fee = int(batch["fee_vnd"]) + (0 if batch["fee_includes_vat"] else int(batch["fee_vat_vnd"] or 0))
    bot = own = customer = 0
    for item in _items(conn, batch):
        amount = int(item["settled_vnd"] or 0) + int(item["adjustment_vnd"] or 0)
        if item["is_bot"] and item["conversion_id"]:
            customer += cashback.get(str(item["conversion_id"]), 0)
            if item["match_status"] == "MATCHED":
                bot += amount
        elif item["match_status"] in ("NOT_BOT", "UNKNOWN_ORDER"):
            own += amount

    def number(column: str) -> int | None:
        return None if batch[column] is None else int(batch[column])

    return Period(
        int(batch["id"]), str(batch["period"]), str(batch["status"]), batch["shopee_payment_ref"], commission, fee,
        number("tax_withheld_vnd"), number("shopee_payout_vnd"), number("bank_received_vnd"), bot, own, customer,
    )


def _customers(conn: sqlite3.Connection) -> Customers:
    waiting = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN COALESCE(c.settlement_status, '') != 'SETTLED' THEN e.cashback_vnd END), 0),
               COALESCE(SUM(CASE WHEN c.settlement_status = 'SETTLED' THEN e.cashback_vnd END), 0)
        FROM cashback_entries e LEFT JOIN shopee_conversions c ON c.conversion_id = e.conversion_id
        WHERE e.status IN ('pending', 'holding')
        """
    ).fetchone()
    in_wallet = owed = 0
    for (user,) in conn.execute("SELECT DISTINCT telegram_user_id FROM cashback_entries WHERE status = 'available'"):
        left = payouts.withdrawable(conn, int(user))
        in_wallet += max(0, left)
        owed -= min(0, left)
    reserved, paid = payouts.payout_totals(conn)
    marks = ", ".join("?" for _ in payouts.OPEN)
    requests = conn.execute(f"SELECT COUNT(*) FROM cashback_payouts WHERE status IN ({marks})", payouts.OPEN).fetchone()
    return Customers(int(waiting[0]), int(waiting[1]), in_wallet, owed, reserved, paid, int(requests[0]))


def snapshot(conn: sqlite3.Connection) -> Snapshot:
    """conn cần row_factory = sqlite3.Row."""
    cashback = _entry_totals(conn)
    batches = conn.execute(
        "SELECT * FROM settlement_batches WHERE status != 'REVERSED' ORDER BY period, id"
    ).fetchall()
    adjustments = conn.execute("SELECT COUNT(*) FROM settlement_adjustments WHERE status = 'OPEN'").fetchone()[0]
    return Snapshot(
        tuple(_period(conn, batch, cashback) for batch in batches), _customers(conn), payouts.fund_position(conn),
        int(adjustments),
    )
