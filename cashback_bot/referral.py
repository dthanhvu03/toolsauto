"""Mời bạn (PLAN-155). Chủ bot chốt 2026-11-05.

• Người mời nhận 10% hoa hồng mỗi đơn của người được mời, trong 6 tháng kể từ lúc gắn mã. Tiền trích từ phần
  của bot; người được mời nhận đủ phần của họ. Một tầng: không thưởng người mời của người mời.
• Thưởng nằm trong sổ ví: dòng `<conversion>:ref` của người mời, hoa hồng ghi 0 (không đếm hai lần ở thống kê).
  Trạng thái đi theo đơn gốc: chờ / đang chờ Shopee trả / vào ví khi đơn gốc vào ví / huỷ khi đơn gốc huỷ.
  Trigger DB (db.py) xét dòng `:ref` theo đơn gốc: chỉ vào ví khi đơn gốc SETTLED, không vượt hoa hồng đơn gốc.
  Đã vào ví thì số tiền chốt; đơn gốc bị Shopee giảm hoa hồng sau đó thì thêm dòng `<conversion>:ref:clawback:<n>`
  (số âm) cho phần thưởng tương ứng, như dòng thu hồi của tiền hoàn.
• Dòng thưởng chỉ ghi «🤝 Thưởng mời bạn», không ghi món bạn bè mua.
• Người mời và người được mời từng khai cùng tài khoản ngân hàng (bank_account_history.account_sha): coi là tự mời
  mình, khoá lượt mời (`blocked_reason = same_bank`), huỷ mọi thưởng của lượt đó; service báo admin.
• Không tính đơn của người được mời vào hạng của người mời (membership.py bỏ dòng `:ref`).
• Gắn mã: Telegram `t.me/<bot>?start=ref_<MÃ>`, Zalo gõ `ref <MÃ>`. Chỉ người chưa tạo link nào và vào bot chưa
  quá 7 ngày; không tự mời mình; không mời chéo (A mời B thì B không mời được A); đã gắn thì không đổi.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

REF_TAG = ":ref"
SHARE_BPS = 1_000
TERM = timedelta(days=183)  # 6 tháng
JOIN_WINDOW = timedelta(days=7)
POLICY_LABEL = "ref-10"
ITEM_NAME = "🤝 Thưởng mời bạn"
CLAWBACK_TAG = ":clawback:"
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # bỏ O/0, I/1 cho dễ gõ
_CODE_RE = r"[A-Za-z0-9]{6}"
_PARSE = re.compile(rf"^(?:/start\s+ref_|/?ref\s+)({_CODE_RE})$", re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS referral_codes (
    user_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS referrals (
    invitee_id INTEGER PRIMARY KEY,
    referrer_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    blocked_reason TEXT,
    blocked_at TEXT,
    CHECK (invitee_id != referrer_id)
);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals (referrer_id);
"""


@dataclass(frozen=True)
class Notice:
    """kind: order (bạn được mời có đơn mới), paid (thưởng vào ví), cancelled (mất thưởng),
    clawback (Shopee giảm hoa hồng đơn gốc đã vào ví; reward_vnd là số bị trừ). previous: trạng thái trước."""

    user_id: int
    kind: str
    reward_vnd: int
    conversion_id: str
    previous: str | None = None


@dataclass(frozen=True)
class Stats:
    code: str
    invited: int
    waiting_vnd: int
    in_wallet_vnd: int


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    have = {row[1] for row in conn.execute("PRAGMA table_info(referrals)")}
    for column in ("blocked_reason", "blocked_at"):
        if column not in have:
            conn.execute(f"ALTER TABLE referrals ADD COLUMN {column} TEXT")


def reward_for(commission_vnd: int) -> int:
    return max(0, int(commission_vnd)) * SHARE_BPS // 10_000


def parse(text: str) -> str | None:
    """Mã mời trong `/start ref_ABC234` hoặc `ref ABC234` (không phân biệt hoa thường)."""
    found = _PARSE.fullmatch((text or "").strip())
    return found.group(1).upper() if found else None


def code_for(conn: sqlite3.Connection, user_id: int, now: datetime) -> str:
    row = conn.execute("SELECT code FROM referral_codes WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return str(row[0])
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(6))
        try:
            conn.execute("INSERT INTO referral_codes (user_id, code, created_at) VALUES (?, ?, ?)",
                         (user_id, code, _stamp(now)))
            return code
        except sqlite3.IntegrityError:
            row = conn.execute("SELECT code FROM referral_codes WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return str(row[0])


def attach(conn: sqlite3.Connection, invitee_id: int, code: str, now: datetime) -> str:
    """ok · unknown · self · already · old_user · mutual."""
    owner = conn.execute("SELECT user_id FROM referral_codes WHERE code = ?", (code.upper(),)).fetchone()
    if owner is None:
        return "unknown"
    referrer = int(owner[0])
    if referrer == invitee_id:
        return "self"
    if conn.execute("SELECT 1 FROM referrals WHERE invitee_id = ?", (invitee_id,)).fetchone():
        return "already"
    links = conn.execute("SELECT COUNT(*) FROM link_requests WHERE telegram_user_id = ? AND link_status = 'created'",
                         (invitee_id,)).fetchone()[0]
    seen = conn.execute("SELECT created_at FROM telegram_users WHERE telegram_user_id = ?", (invitee_id,)).fetchone()
    if links or (seen is not None and str(seen[0]) < _stamp(now - JOIN_WINDOW)):
        return "old_user"
    if conn.execute("SELECT 1 FROM referrals WHERE invitee_id = ? AND referrer_id = ?",
                    (referrer, invitee_id)).fetchone():
        return "mutual"
    conn.execute("INSERT INTO referrals (invitee_id, referrer_id, code, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                 (invitee_id, referrer, code.upper(), _stamp(now), _stamp(now + TERM)))
    return "ok"


def referrer_of(conn: sqlite3.Connection, invitee_id: int) -> int | None:
    row = conn.execute("SELECT referrer_id FROM referrals WHERE invitee_id = ?", (invitee_id,)).fetchone()
    return None if row is None else int(row[0])


def block_same_bank(conn: sqlite3.Connection, now: datetime) -> list[tuple[int, int]]:
    """Khoá lượt mời mà hai bên từng khai cùng một tài khoản ngân hàng. Trả (người được mời, người mời) mới khoá."""
    found = conn.execute(
        """
        SELECT DISTINCT r.invitee_id, r.referrer_id FROM referrals r
        JOIN bank_account_history a ON a.telegram_user_id = r.referrer_id
        JOIN bank_account_history b ON b.telegram_user_id = r.invitee_id AND b.account_sha = a.account_sha
        WHERE r.blocked_reason IS NULL
        """
    ).fetchall()
    for invitee, _referrer in found:
        conn.execute("UPDATE referrals SET blocked_reason = 'same_bank', blocked_at = ? WHERE invitee_id = ?",
                     (_stamp(now), invitee))
    return [(int(a), int(b)) for a, b in found]


def _sum(conn: sqlite3.Connection, column: str, prefix: str) -> int:
    row = conn.execute(f"SELECT COALESCE(SUM({column}), 0) FROM cashback_entries WHERE instr(conversion_id, ?) = 1",
                       (prefix,)).fetchone()
    return int(row[0])


def _claw(conn: sqlite3.Connection, ref_id: str, referrer: int, parent: sqlite3.Row, delta: int, at: str) -> None:
    count = conn.execute("SELECT COUNT(*) FROM cashback_entries WHERE instr(conversion_id, ?) = 1",
                         (ref_id + CLAWBACK_TAG,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO cashback_entries (
            conversion_id, telegram_user_id, link_id, order_sn, item_name, commission_vnd, cashback_vnd, fee_vnd,
            tax_vnd, policy_label, status, purchase_time, completed_at, available_at, created_at, updated_at
        ) VALUES (?, ?, NULL, ?, ?, 0, ?, 0, 0, ?, 'available', ?, ?, ?, ?, ?)
        """,
        (f"{ref_id}{CLAWBACK_TAG}{int(count) + 1}", referrer, parent["order_sn"], ITEM_NAME, -delta, POLICY_LABEL,
         parent["purchase_time"], parent["completed_at"], at, at, at),
    )


def sync(conn: sqlite3.Connection, now: datetime) -> list[Notice]:
    """Dựng dòng thưởng `:ref` theo đơn của người được mời. Gọi sau Wallet.refresh, trong cùng lượt."""
    at = _stamp(now)
    notices: list[Notice] = []
    rows = conn.execute(
        """
        SELECT e.*, r.referrer_id, r.blocked_reason FROM cashback_entries e
        JOIN referrals r ON r.invitee_id = e.telegram_user_id
        WHERE instr(e.conversion_id, ':clawback:') = 0 AND instr(e.conversion_id, ':ref') = 0
          AND COALESCE(e.purchase_time, e.created_at) >= r.created_at
          AND COALESCE(e.purchase_time, e.created_at) < r.expires_at
        """
    ).fetchall()
    for parent in rows:
        conversion = str(parent["conversion_id"])
        ref_id = conversion + REF_TAG
        referrer = int(parent["referrer_id"])
        status = "cancelled" if parent["blocked_reason"] else str(parent["status"])
        # Hoa hồng hiện hành của đơn gốc: dòng gốc + các dòng thu hồi (hoa hồng âm) sau khi vào ví.
        commission = int(parent["commission_vnd"] or 0) + _sum(conn, "commission_vnd", conversion + CLAWBACK_TAG)
        reward = reward_for(commission)
        old = conn.execute("SELECT status, cashback_vnd FROM cashback_entries WHERE conversion_id = ?",
                           (ref_id,)).fetchone()
        if old is None:
            if status == "cancelled" or reward <= 0:
                continue
            conn.execute(
                """
                INSERT INTO cashback_entries (
                    conversion_id, telegram_user_id, link_id, order_sn, item_name, commission_vnd, cashback_vnd,
                    fee_vnd, tax_vnd, policy_label, status, purchase_time, completed_at, available_at, created_at,
                    updated_at
                ) VALUES (?, ?, NULL, ?, ?, 0, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ref_id, referrer, parent["order_sn"], ITEM_NAME, reward, POLICY_LABEL, status,
                 parent["purchase_time"], parent["completed_at"], parent["available_at"], at, at),
            )
            notices.append(Notice(referrer, "paid" if status == "available" else "order", reward, ref_id))
            continue
        before = str(old["status"])
        if before == "available" and status == "available":
            given = int(old["cashback_vnd"]) + _sum(conn, "cashback_vnd", ref_id + CLAWBACK_TAG)
            if reward < given:
                _claw(conn, ref_id, referrer, parent, given - reward, at)
                notices.append(Notice(referrer, "clawback", given - reward, ref_id, before))
            continue
        amount = int(old["cashback_vnd"]) if before == "available" or status == "cancelled" else reward
        if before == status and amount == int(old["cashback_vnd"]):
            continue
        if before == "available":
            # Đã vào ví: số tiền chốt (trigger ledger_available_frozen), chỉ đổi trạng thái theo đơn gốc.
            conn.execute("UPDATE cashback_entries SET status = ?, available_at = ?, updated_at = ? WHERE conversion_id = ?",
                         (status, parent["available_at"], at, ref_id))
        else:
            conn.execute(
                "UPDATE cashback_entries SET cashback_vnd = ?, status = ?, completed_at = ?, available_at = ?, "
                "updated_at = ? WHERE conversion_id = ?",
                (amount, status, parent["completed_at"], parent["available_at"], at, ref_id),
            )
        if (before == "available") != (status == "available"):
            # Dòng trừ lại của thưởng đi theo khoản thưởng, như dòng «:clawback:» của tiền hoàn.
            conn.execute("UPDATE cashback_entries SET status = ?, updated_at = ? WHERE instr(conversion_id, ?) = 1",
                         (status, at, ref_id + CLAWBACK_TAG))
        if before != status and status == "available":
            notices.append(Notice(referrer, "paid", amount, ref_id, before))
        elif before != status and status == "cancelled":
            notices.append(Notice(referrer, "cancelled", amount, ref_id, before))
    return notices


def stats(conn: sqlite3.Connection, user_id: int, now: datetime) -> Stats:
    code = code_for(conn, user_id, now)
    invited = conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)).fetchone()[0]
    money = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN status IN ('pending', 'holding') THEN cashback_vnd END), 0), "
        "COALESCE(SUM(CASE WHEN status = 'available' THEN cashback_vnd END), 0) "
        "FROM cashback_entries WHERE telegram_user_id = ? AND instr(conversion_id, ?) > 0",
        (user_id, REF_TAG),
    ).fetchone()
    return Stats(code, int(invited), int(money[0]), int(money[1]))
