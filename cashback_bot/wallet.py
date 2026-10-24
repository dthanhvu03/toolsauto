"""Sổ hoàn tiền và ví khách (PLAN-066, ADR-049).

Mỗi đơn Shopee khớp link bot là một dòng `cashback_entries`:

- pending: đơn chưa hoàn thành.
- holding: đã hoàn thành, chờ đủ số ngày giữ (Shopee còn đối soát, trả hàng có thể trừ lại).
- available: đã vào ví. Số tiền chốt, không tính lại khi chính sách đổi.
- cancelled: huỷ, trả hàng. Không tính vào số dư.

Rút được = tổng available − yêu cầu đang chờ − đã trả. Đơn đã available mà Shopee huỷ sau đó thì
chuyển cancelled, số dư có thể âm; admin được báo để xử lý.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cashback_bot.db import TrackingRepository

KEY_ENABLED = "wallet_enabled"
KEY_HOLD_DAYS = "wallet_hold_days"
KEY_MIN_WITHDRAW = "wallet_min_withdraw_vnd"
DEFAULT_HOLD_DAYS = 30
DEFAULT_MIN_WITHDRAW = 10_000
HOLD_DAY_CHOICES = (0, 7, 15, 30, 45)
MIN_WITHDRAW_CHOICES = (10_000, 20_000, 50_000, 100_000)
OPEN_STATUSES = ("pending", "holding")

# Mã gõ tắt → (BIN NAPAS dùng cho VietQR, tên hiển thị).
BANKS: dict[str, tuple[str, str]] = {
    "VCB": ("970436", "Vietcombank"),
    "TCB": ("970407", "Techcombank"),
    "MB": ("970422", "MB Bank"),
    "ACB": ("970416", "ACB"),
    "VPB": ("970432", "VPBank"),
    "BIDV": ("970418", "BIDV"),
    "CTG": ("970415", "VietinBank"),
    "TPB": ("970423", "TPBank"),
    "STB": ("970403", "Sacombank"),
    "VIB": ("970441", "VIB"),
    "HDB": ("970437", "HDBank"),
    "MSB": ("970426", "MSB"),
    "OCB": ("970448", "OCB"),
    "SHB": ("970443", "SHB"),
    "AGR": ("970405", "Agribank"),
    "SEAB": ("970440", "SeABank"),
    "EIB": ("970431", "Eximbank"),
    "LPB": ("970449", "LPBank"),
    "NAB": ("970428", "Nam A Bank"),
    "BAB": ("970409", "Bac A Bank"),
    "KLB": ("970452", "KienlongBank"),
    "PVCB": ("970412", "PVcomBank"),
    "ABB": ("970425", "ABBANK"),
    "VAB": ("970427", "VietABank"),
    "NCB": ("970419", "NCB"),
    "BVB": ("970454", "BVBank"),
    "SHBVN": ("970424", "Shinhan Bank"),
    "CAKE": ("546034", "Cake by VPBank"),
    "UBANK": ("546035", "Ubank by VPBank"),
    "TIMO": ("963388", "Timo"),
}
BANK_ALIASES = {
    "VIETCOMBANK": "VCB",
    "TECHCOMBANK": "TCB",
    "MBBANK": "MB",
    "VPBANK": "VPB",
    "VIETINBANK": "CTG",
    "TPBANK": "TPB",
    "SACOMBANK": "STB",
    "HDBANK": "HDB",
    "AGRIBANK": "AGR",
    "SEABANK": "SEAB",
    "EXIMBANK": "EIB",
    "LPBANK": "LPB",
    "NAMABANK": "NAB",
    "BACABANK": "BAB",
    "KIENLONGBANK": "KLB",
    "PVCOMBANK": "PVCB",
    "ABBANK": "ABB",
    "VIETABANK": "VAB",
    "BVBANK": "BVB",
    "SHINHAN": "SHBVN",
    "MBV": "MB",
}
_ACCOUNT_NO = re.compile(r"^\d{6,19}$")
_ACCOUNT_NAME = re.compile(r"^[A-Z ]{3,50}$")

@dataclass(frozen=True)
class Split:
    """Chia hoa hồng một đơn: khách nhận, phí và dự phòng thuế admin chịu. Phần còn lại là của admin."""

    cashback_vnd: int
    label: str
    fee_vnd: int = 0
    tax_vnd: int = 0


# (hoa hồng thật, dòng link) → Split. Do service cung cấp.
CashbackFor = Callable[[int, sqlite3.Row], Split]


@dataclass(frozen=True)
class WalletSettings:
    enabled: bool
    hold_days: int
    min_withdraw_vnd: int


@dataclass(frozen=True)
class Balance:
    pending_vnd: int
    earned_vnd: int
    requested_vnd: int
    paid_vnd: int

    @property
    def withdrawable_vnd(self) -> int:
        return self.earned_vnd - self.requested_vnd - self.paid_vnd


@dataclass(frozen=True)
class Transition:
    conversion_id: str
    telegram_user_id: int
    previous: str | None
    status: str
    item_name: str
    cashback_vnd: int
    available_at: str | None
    purchase_time: str | None


@dataclass(frozen=True)
class BankAccount:
    bank_code: str
    account_no: str
    account_name: str

    @property
    def bank_name(self) -> str:
        return BANKS[self.bank_code][1]

    @property
    def masked(self) -> str:
        return f"{self.bank_name} ••••{self.account_no[-4:]}"


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def order_state(order_status: str | None) -> str:
    status = (order_status or "").upper()
    if "CANCEL" in status:
        return "cancelled"
    if "COMPLETED" in status:
        return "completed"
    return "pending"


def _plain_upper(text: str) -> str:
    """Tên chủ tài khoản kiểu ngân hàng: bỏ dấu, viết hoa."""
    text = text.replace("đ", "d").replace("Đ", "D")
    stripped = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.upper().split())


def bank_code_of(token: str) -> str | None:
    code = (token or "").strip().upper()
    code = BANK_ALIASES.get(code, code)
    return code if code in BANKS else None


def parse_bank_text(text: str, bank_code: str | None = None) -> BankAccount | str:
    """'MB 0123456789 Nguyễn Văn A' → BankAccount. Sai thì trả mã lỗi.

    bank_code: khách đã bấm chọn ngân hàng, chỉ cần gõ 'số tài khoản + tên'. Gõ cả mã ở đầu vẫn nhận.
    Số tài khoản gõ tách nhóm ('0123 456 789', '0123.456.789') được ghép lại.
    """
    parts = re.sub(r"[|,;\n]+", " ", text or "").split()
    if parts and bank_code_of(parts[0]) and not parts[0].isdigit():
        bank_code, parts = bank_code_of(parts[0]), parts[1:]
    elif bank_code is None:
        return "bank" if parts else "format"
    if bank_code not in BANKS:
        return "bank"
    digits: list[str] = []
    while parts and re.fullmatch(r"[\d.\-]+", parts[0]):
        digits.append(parts.pop(0))
    if not digits:
        return "account" if parts else "format"
    account_no = "".join(digits).replace(".", "").replace("-", "")
    if not _ACCOUNT_NO.fullmatch(account_no):
        return "account"
    if not parts:
        return "format"
    name = _plain_upper(" ".join(parts))
    if not _ACCOUNT_NAME.fullmatch(name):
        return "name"
    return BankAccount(bank_code, account_no, name)


def transfer_note(payout_id: int) -> str:
    return f"Hoan tien {payout_id:06d}"


class Wallet:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo

    # --- Cài đặt (bot_state) -------------------------------------------------

    def settings(self) -> WalletSettings:
        def number(key: str, default: int) -> int:
            try:
                return int(self.repo.get_state(key) or default)
            except ValueError:
                return default

        return WalletSettings(
            enabled=self.repo.get_state(KEY_ENABLED) == "1",
            hold_days=number(KEY_HOLD_DAYS, DEFAULT_HOLD_DAYS),
            min_withdraw_vnd=number(KEY_MIN_WITHDRAW, DEFAULT_MIN_WITHDRAW),
        )

    def set_enabled(self, enabled: bool) -> None:
        self.repo.set_state(KEY_ENABLED, "1" if enabled else "0")

    def set_hold_days(self, days: int) -> None:
        if days not in HOLD_DAY_CHOICES:
            raise ValueError("hold_days")
        self.repo.set_state(KEY_HOLD_DAYS, str(days))

    def set_min_withdraw(self, amount_vnd: int) -> None:
        if amount_vnd not in MIN_WITHDRAW_CHOICES:
            raise ValueError("min_withdraw")
        self.repo.set_state(KEY_MIN_WITHDRAW, str(amount_vnd))

    # --- Sổ ------------------------------------------------------------------

    def refresh(self, now: datetime, cashback_for: CashbackFor) -> list[Transition]:
        """Dựng lại trạng thái từng đơn khớp bot từ shopee_conversions. Trả các dòng đổi trạng thái."""
        hold = timedelta(days=self.settings().hold_days)
        now_text = _stamp(now)
        transitions: list[Transition] = []
        with self.repo.connect() as conn:
            existing = {row["conversion_id"]: row for row in conn.execute("SELECT * FROM cashback_entries")}
            link_columns = {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}
            # Cột V1.2 chỉ có sau migration 001; DB chưa chạy thì mọi link là V1.1.
            policy = "l.estimate_policy" if "estimate_policy" in link_columns else "NULL"
            rows = conn.execute(
                f"""
                SELECT c.conversion_id, c.telegram_user_id, c.matched_link_id, c.order_sn, c.order_status,
                       c.net_commission_vnd, c.gross_commission_vnd, c.purchase_time, c.complete_time, c.item_name,
                       l.product_name, {policy} AS estimate_policy, l.cashback_rate_percent,
                       l.created_at AS link_created_at
                FROM shopee_conversions c JOIN link_requests l ON l.id = c.matched_link_id
                WHERE c.telegram_user_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                prev = existing.get(row["conversion_id"])
                state = order_state(row["order_status"])
                if prev is not None and prev["status"] == "available" and state != "cancelled":
                    continue
                commission = row["net_commission_vnd"]
                if commission is None:
                    commission = row["gross_commission_vnd"] or 0
                if prev is not None and prev["status"] == "available":
                    # Shopee huỷ sau khi đã vào ví: giữ số đã chốt để admin thấy khoản bị trừ.
                    split = Split(
                        int(prev["cashback_vnd"]), prev["policy_label"], int(prev["fee_vnd"]), int(prev["tax_vnd"])
                    )
                else:
                    split = cashback_for(max(0, int(commission)), row)
                cashback, label = split.cashback_vnd, split.label
                completed_at = row["complete_time"] or (prev["completed_at"] if prev is not None else None)
                available_at = None
                if state == "cancelled":
                    status = "cancelled"
                elif state == "completed":
                    completed_at = completed_at or now_text
                    done = _parse(completed_at) or now
                    available_at = _stamp(done + hold)
                    status = "available" if available_at <= now_text else "holding"
                else:
                    status = "pending"
                item_name = row["item_name"] or row["product_name"] or row["order_sn"] or "-"
                conn.execute(
                    """
                    INSERT INTO cashback_entries (
                        conversion_id, telegram_user_id, link_id, order_sn, item_name, commission_vnd,
                        cashback_vnd, fee_vnd, tax_vnd, policy_label, status, purchase_time, completed_at,
                        available_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(conversion_id) DO UPDATE SET
                        item_name = excluded.item_name,
                        commission_vnd = excluded.commission_vnd,
                        cashback_vnd = excluded.cashback_vnd,
                        fee_vnd = excluded.fee_vnd,
                        tax_vnd = excluded.tax_vnd,
                        policy_label = excluded.policy_label,
                        status = excluded.status,
                        purchase_time = excluded.purchase_time,
                        completed_at = excluded.completed_at,
                        available_at = excluded.available_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row["conversion_id"], int(row["telegram_user_id"]), row["matched_link_id"], row["order_sn"],
                        item_name, int(commission), int(cashback), int(split.fee_vnd), int(split.tax_vnd), label,
                        status, row["purchase_time"],
                        completed_at, available_at, now_text, now_text,
                    ),
                )
                previous = None if prev is None else str(prev["status"])
                if previous != status:
                    transitions.append(
                        Transition(
                            conversion_id=str(row["conversion_id"]),
                            telegram_user_id=int(row["telegram_user_id"]),
                            previous=previous,
                            status=status,
                            item_name=item_name,
                            cashback_vnd=int(cashback),
                            available_at=available_at,
                            purchase_time=row["purchase_time"],
                        )
                    )
        return transitions

    def balance(self, user_id: int) -> Balance:
        with self.repo.connect() as conn:
            return _balance(conn, user_id)

    def entries(self, user_id: int, limit: int = 5) -> list[sqlite3.Row]:
        with self.repo.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM cashback_entries WHERE telegram_user_id = ?
                ORDER BY COALESCE(purchase_time, created_at) DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    # --- Tài khoản nhận tiền -------------------------------------------------

    def bank(self, user_id: int) -> BankAccount | None:
        with self.repo.connect() as conn:
            row = conn.execute("SELECT * FROM bank_accounts WHERE telegram_user_id = ?", (user_id,)).fetchone()
        if row is None or row["bank_code"] not in BANKS:
            return None
        return BankAccount(row["bank_code"], row["account_no"], row["account_name"])

    def save_bank(self, user_id: int, account: BankAccount, now: datetime) -> None:
        with self.repo.connect() as conn:
            conn.execute(
                """
                INSERT INTO bank_accounts (telegram_user_id, bank_code, account_no, account_name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    bank_code = excluded.bank_code,
                    account_no = excluded.account_no,
                    account_name = excluded.account_name,
                    updated_at = excluded.updated_at
                """,
                (user_id, account.bank_code, account.account_no, account.account_name, _stamp(now)),
            )

    # --- Rút tiền ------------------------------------------------------------

    def open_request(self, user_id: int) -> sqlite3.Row | None:
        with self.repo.connect() as conn:
            return conn.execute(
                "SELECT * FROM cashback_payouts WHERE telegram_user_id = ? AND status = 'requested'",
                (user_id,),
            ).fetchone()

    def request_payout(self, user_id: int, now: datetime) -> tuple[sqlite3.Row | None, str]:
        """Rút toàn bộ số đang rút được. Trả (yêu cầu, 'ok') hoặc (None, mã lỗi)."""
        settings = self.settings()
        if not settings.enabled:
            return None, "disabled"
        account = self.bank(user_id)
        if account is None:
            return None, "no_bank"
        with self.repo.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM cashback_payouts WHERE telegram_user_id = ? AND status = 'requested'", (user_id,)
            ).fetchone():
                return None, "pending_exists"
            amount = _balance(conn, user_id).withdrawable_vnd
            if amount < settings.min_withdraw_vnd or amount <= 0:
                return None, "below_min"
            cursor = conn.execute(
                """
                INSERT INTO cashback_payouts (
                    telegram_user_id, amount_vnd, status, bank_code, account_no, account_name, created_at
                ) VALUES (?, ?, 'requested', ?, ?, ?, ?)
                """,
                (user_id, amount, account.bank_code, account.account_no, account.account_name, _stamp(now)),
            )
            payout_id = int(cursor.lastrowid)
            conn.execute(
                "UPDATE cashback_payouts SET transfer_note = ? WHERE id = ?", (transfer_note(payout_id), payout_id)
            )
            row = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()
        return row, "ok"

    def payout(self, payout_id: int) -> sqlite3.Row | None:
        with self.repo.connect() as conn:
            return conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()

    def decide_payout(self, payout_id: int, paid: bool, admin_id: int, now: datetime) -> sqlite3.Row | None:
        """Chỉ đổi yêu cầu còn 'requested'. Bấm hai lần thì lần sau trả None."""
        with self.repo.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE cashback_payouts SET status = ?, decided_at = ?, decided_by = ?
                WHERE id = ? AND status = 'requested'
                """,
                ("paid" if paid else "rejected", _stamp(now), admin_id, payout_id),
            )
            if cursor.rowcount == 0:
                return None
            return conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()

    # --- Màn admin -----------------------------------------------------------

    def open_requests(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.repo.connect() as conn:
            return conn.execute(
                """
                SELECT p.*, u.username FROM cashback_payouts p
                LEFT JOIN telegram_users u ON u.telegram_user_id = p.telegram_user_id
                WHERE p.status = 'requested' ORDER BY p.id LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def members(self, limit: int = 10) -> list[dict]:
        """Khách có đơn khớp bot, xếp theo số rút được rồi số chờ duyệt."""
        with self.repo.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.telegram_user_id, u.username, COUNT(*) AS orders,
                       COALESCE(SUM(CASE WHEN e.status IN ('pending', 'holding') THEN e.cashback_vnd END), 0) AS pending,
                       MAX(COALESCE(e.purchase_time, e.created_at)) AS last_purchase
                FROM cashback_entries e LEFT JOIN telegram_users u ON u.telegram_user_id = e.telegram_user_id
                GROUP BY e.telegram_user_id
                """
            ).fetchall()
            result = []
            for row in rows:
                balance = _balance(conn, int(row["telegram_user_id"]))
                result.append(
                    {
                        "telegram_user_id": int(row["telegram_user_id"]),
                        "username": row["username"],
                        "orders": int(row["orders"]),
                        "balance": balance,
                        "last_purchase": row["last_purchase"],
                    }
                )
        result.sort(key=lambda m: (m["balance"].withdrawable_vnd, m["balance"].pending_vnd), reverse=True)
        return result[:limit]

    def totals(self) -> Balance:
        with self.repo.connect() as conn:
            return _balance(conn, None)


def _balance(conn: sqlite3.Connection, user_id: int | None) -> Balance:
    where, args = ("WHERE telegram_user_id = ?", (user_id,)) if user_id is not None else ("", ())
    entry = conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN status IN ('pending', 'holding') THEN cashback_vnd END), 0),
               COALESCE(SUM(CASE WHEN status = 'available' THEN cashback_vnd END), 0)
        FROM cashback_entries {where}
        """,
        args,
    ).fetchone()
    payout = conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN status = 'requested' THEN amount_vnd END), 0),
               COALESCE(SUM(CASE WHEN status = 'paid' THEN amount_vnd END), 0)
        FROM cashback_payouts {where}
        """,
        args,
    ).fetchone()
    return Balance(int(entry[0]), int(entry[1]), int(payout[0]), int(payout[1]))
