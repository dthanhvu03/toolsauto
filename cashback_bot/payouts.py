"""Vòng đời yêu cầu rút, phân bổ, quỹ chi trả, hạn mức, tài khoản nhận tiền (PLAN-078, ADR-055).

Trạng thái (`cashback_payouts.status`):
  requested → under_review → approved_for_payment → processing → sent_unconfirmed → paid_confirmed
  rẽ nhánh: rejected, cancelled (chưa từng chuyển), failed (có chứng từ không thực hiện), needs_review,
  returned (ngân hàng hoàn lại khoản đã trả, có chứng từ).
- Admin bấm đã xử lý ≠ ngân hàng chuyển thành công; có mã QR ≠ đã gửi; đã gửi ≠ khách đã nhận.
- Mỗi đồng của yêu cầu là một dòng `payout_allocations` trỏ về khoản sổ ví (conversion). Không sửa, không xoá.
- Trạng thái đưa tiền ra cần khoá tài chính mở (payout_gate + trigger) cộng điều kiện của PLAN-078.
- Đã từng tới processing / sent_unconfirmed thì không còn đường «từ chối / huỷ» để giải phóng tiền: chỉ
  failed (có chứng từ không thực hiện) hoặc đi tiếp tới paid. Không có đường tự chuyển lại.
- needs_review (PLAN-088): chưa từng tới processing thì chỉ quay lại kiểm tra hoặc từ chối; đã từng tới thì chỉ
  ghi «đã gửi» hoặc «thất bại», không quay lại vòng duyệt (tránh chuyển tiền hai lần).
- Trước khi duyệt chi / bắt đầu chuyển: mọi khoản nguồn của yêu cầu phải còn 'available' (Shopee không huỷ,
  kỳ không bị đảo).
- Đổi tài khoản nhận tiền: chờ BANK_COOLDOWN mới rút về tài khoản mới, trừ khi admin đã xác minh (ADR-059).
Module không gọi ngân hàng, không gửi tiền.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cashback_bot.support import clean_text

REQUESTED = "requested"
UNDER_REVIEW = "under_review"
APPROVED = "approved_for_payment"
PROCESSING = "processing"
SENT = "sent_unconfirmed"
PAID = "paid_confirmed"
REJECTED = "rejected"
FAILED = "failed"
CANCELLED = "cancelled"
NEEDS_REVIEW = "needs_review"
RETURNED = "returned"
LEGACY_PAID = "paid"

OPEN = (REQUESTED, UNDER_REVIEW, APPROVED, PROCESSING, SENT, NEEDS_REVIEW)  # còn giữ tiền
PAID_STATES = (PAID, LEGACY_PAID)
RELEASED = (REJECTED, FAILED, CANCELLED, RETURNED)  # tiền trở lại ví
MONEY_LEFT = (PROCESSING, SENT)  # đã từng tới đây thì có thể tiền đã rời tài khoản
POLICY_TOPICS = ("tax", "clawback", "payout_terms", "bank_verification", "payment_limits", "manual_payment")
EVIDENCE_MIN = 4
BANK_COOLDOWN = timedelta(days=7)
SOURCE_CHECKED = (APPROVED, PROCESSING)  # bước trước khi tiền rời tài khoản
# Lựa chọn hạn mức admin chỉnh trong /admin → 👛 Ví khách → ⚙️ Cài đặt (ADR-059). Tối thiểu theo «Rút tối thiểu».
# Ngày / tháng tính theo từng khách; khách tích 5–10tr phải rút được một lần.
LIMIT_CHOICES = {
    "req": (500_000, 2_000_000, 5_000_000, 10_000_000),
    "day": (2_000_000, 5_000_000, 10_000_000, 20_000_000),
    "month": (10_000_000, 20_000_000, 50_000_000, 100_000_000),
}


@dataclass(frozen=True)
class Rule:
    needs_reason: bool = False
    needs_evidence: bool = False
    money_out: bool = False


TRANSITIONS: dict[str, dict[str, Rule]] = {
    REQUESTED: {
        UNDER_REVIEW: Rule(),
        REJECTED: Rule(needs_reason=True),
        CANCELLED: Rule(needs_reason=True),
        NEEDS_REVIEW: Rule(needs_reason=True),
    },
    UNDER_REVIEW: {
        APPROVED: Rule(money_out=True),
        REJECTED: Rule(needs_reason=True),
        NEEDS_REVIEW: Rule(needs_reason=True),
    },
    APPROVED: {
        PROCESSING: Rule(money_out=True),
        CANCELLED: Rule(needs_reason=True),
        NEEDS_REVIEW: Rule(needs_reason=True),
    },
    PROCESSING: {
        SENT: Rule(money_out=True),
        FAILED: Rule(needs_reason=True, needs_evidence=True),
        NEEDS_REVIEW: Rule(needs_reason=True),
    },
    SENT: {
        PAID: Rule(needs_evidence=True, money_out=True),
        FAILED: Rule(needs_reason=True, needs_evidence=True),
        NEEDS_REVIEW: Rule(needs_reason=True),
    },
    NEEDS_REVIEW: {
        UNDER_REVIEW: Rule(needs_reason=True),
        SENT: Rule(needs_reason=True, money_out=True),
        REJECTED: Rule(needs_reason=True),
        FAILED: Rule(needs_reason=True, needs_evidence=True),
    },
    PAID: {RETURNED: Rule(needs_reason=True, needs_evidence=True)},
}


class PayoutError(ValueError):
    """Mã lỗi ở args[0]."""


@dataclass(frozen=True)
class FundPosition:
    """Quỹ chi trả từ các kỳ đối soát MATCHED (PLAN-075). verified False: chưa có kỳ nào, mọi số là «chưa xác minh».

    allocatable_vnd = Σ mỗi kỳ max(0, tiền đơn bot khớp − phí − VAT chưa gồm − thuế khấu trừ của cả kỳ):
    giả định toàn bộ phí và thuế kỳ rơi vào đơn bot, nên không bao giờ cấp quá. Tiền ngoài bot, không rõ đơn,
    chưa phân bổ không vào quỹ.
    """

    verified: bool
    batches: int
    bot_vnd: int
    costs_vnd: int
    non_bot_vnd: int
    unknown_vnd: int
    allocatable_vnd: int
    reserved_vnd: int
    paid_vnd: int

    @property
    def headroom_vnd(self) -> int:
        return self.allocatable_vnd - self.reserved_vnd - self.paid_vnd


@dataclass(frozen=True)
class LimitPolicy:
    id: int
    min_vnd: int
    max_per_request_vnd: int
    daily_total_vnd: int
    monthly_total_vnd: int


def stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def account_sha(bank_code: str, account_no: str) -> str:
    return hashlib.sha256(f"{bank_code}:{account_no}".encode()).hexdigest()


def transfer_note(payout_id: int) -> str:
    """Nội dung chuyển khoản duy nhất, không dấu (app ngân hàng hay bỏ dấu)."""
    return f"Hoan tien {payout_id:06d}"


# --- Quỹ ----------------------------------------------------------------------------------------


def fund_position(conn: sqlite3.Connection) -> FundPosition:
    batches = conn.execute("SELECT * FROM settlement_batches WHERE status = 'MATCHED'").fetchall()
    bot = costs = non_bot = unknown = allocatable = 0
    for batch in batches:
        # Chỉ dòng của chứng từ thanh toán hiện hành: chứng từ bị thay vẫn giữ dòng cũ (chỉ thêm), đếm cả hai là
        # quỹ gấp đôi.
        items = conn.execute(
            "SELECT match_status, is_bot, settled_vnd, adjustment_vnd FROM settlement_items "
            "WHERE batch_id = ? AND evidence_id = ?",
            (batch["id"], batch["statement_evidence_id"]),
        ).fetchall()

        def total(status: str, want_bot: bool | None = None) -> int:
            return sum(
                int(row["settled_vnd"] or 0) + int(row["adjustment_vnd"] or 0)
                for row in items
                if row["match_status"] == status and (want_bot is None or bool(row["is_bot"]) == want_bot)
            )

        batch_bot = total("MATCHED", True)
        vat = 0 if batch["fee_includes_vat"] else int(batch["fee_vat_vnd"] or 0)
        batch_costs = int(batch["fee_vnd"] or 0) + vat + int(batch["tax_withheld_vnd"] or 0)
        bot += batch_bot
        costs += batch_costs
        non_bot += total("NOT_BOT")
        unknown += total("UNKNOWN_ORDER")
        allocatable += max(0, batch_bot - batch_costs)
    reserved, paid = payout_totals(conn)
    return FundPosition(bool(batches), len(batches), bot, costs, non_bot, unknown, allocatable, reserved, paid)


def payout_totals(conn: sqlite3.Connection, user_id: int | None = None) -> tuple[int, int]:
    where, args = ("AND telegram_user_id = ?", (user_id,)) if user_id is not None else ("", ())
    marks_open = ", ".join("?" for _ in OPEN)
    marks_paid = ", ".join("?" for _ in PAID_STATES)
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN status IN ({marks_open}) THEN amount_vnd END), 0),
               COALESCE(SUM(CASE WHEN status IN ({marks_paid}) THEN amount_vnd END), 0)
        FROM cashback_payouts WHERE 1 = 1 {where}
        """,
        (*OPEN, *PAID_STATES, *args),
    ).fetchone()
    return int(row[0]), int(row[1])


# --- Hạn mức và quyết định chính sách ------------------------------------------------------------


def active_limits(conn: sqlite3.Connection) -> LimitPolicy | None:
    """Dòng hạn mức mới nhất, chỉ khi ACTIVE và có người duyệt. Mặc định không có."""
    row = conn.execute("SELECT * FROM payout_limit_policies ORDER BY id DESC LIMIT 1").fetchone()
    if row is None or row["status"] != "ACTIVE" or not row["approved_by"]:
        return None
    return LimitPolicy(int(row["id"]), int(row["min_vnd"]), int(row["max_per_request_vnd"]),
                       int(row["daily_total_vnd"]), int(row["monthly_total_vnd"]))


def create_limit_draft(conn: sqlite3.Connection, *, min_vnd: int, max_per_request_vnd: int, daily_total_vnd: int,
                       monthly_total_vnd: int, actor: str, now: datetime) -> int:
    """Bản nháp hạn mức (DRAFT). Không có hiệu lực cho tới khi một dòng ACTIVE có người duyệt được thêm."""
    cursor = conn.execute(
        """
        INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd,
            status, created_by, created_at)
        VALUES (?, ?, ?, ?, 'DRAFT', ?, ?)
        """,
        (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd, actor, stamp(now)),
    )
    return int(cursor.lastrowid)


def set_limits(conn: sqlite3.Connection, current: LimitPolicy, *, admin_id: int, now: datetime, **changes: int) -> LimitPolicy:
    """Admin chỉnh hạn mức: thêm một dòng ACTIVE mới (bảng chỉ thêm), admin bấm là người duyệt.

    changes: min_vnd / max_per_request_vnd / daily_total_vnd / monthly_total_vnd. Không giữ thứ tự
    tối thiểu ≤ mỗi lần ≤ ngày ≤ tháng thì ném ValueError("order"), không ghi gì.
    """
    values = {
        "min_vnd": current.min_vnd,
        "max_per_request_vnd": current.max_per_request_vnd,
        "daily_total_vnd": current.daily_total_vnd,
        "monthly_total_vnd": current.monthly_total_vnd,
        **changes,
    }
    if not (0 < values["min_vnd"] <= values["max_per_request_vnd"] <= values["daily_total_vnd"]
            <= values["monthly_total_vnd"]):
        raise ValueError("order")
    actor = f"admin:{admin_id}"
    cursor = conn.execute(
        """
        INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd,
            status, created_by, approved_by, approved_at, created_at)
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
        """,
        (values["min_vnd"], values["max_per_request_vnd"], values["daily_total_vnd"], values["monthly_total_vnd"],
         actor, actor, stamp(now), stamp(now)),
    )
    return LimitPolicy(int(cursor.lastrowid), **values)


def decision(conn: sqlite3.Connection, topic: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM payout_policy_decisions WHERE topic = ? ORDER BY id DESC LIMIT 1", (topic,)
    ).fetchone()


def _used_since(conn: sqlite3.Connection, user_id: int, since: datetime, exclude_id: int | None) -> int:
    marks = ", ".join("?" for _ in RELEASED)
    return int(conn.execute(
        f"SELECT COALESCE(SUM(amount_vnd), 0) FROM cashback_payouts WHERE telegram_user_id = ? AND created_at >= ? "
        f"AND status NOT IN ({marks}) AND id != ?",
        (user_id, stamp(since), *RELEASED, exclude_id or 0),
    ).fetchone()[0])


def _windows(limits: LimitPolicy, now: datetime) -> tuple[tuple[datetime, int, str], ...]:
    local = now.astimezone(timezone(timedelta(hours=7)))
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return ((day_start, limits.daily_total_vnd, "over_daily_limit"),
            (day_start.replace(day=1), limits.monthly_total_vnd, "over_monthly_limit"))


def check_limits(conn: sqlite3.Connection, user_id: int, amount: int, now: datetime,
                 exclude_id: int | None = None) -> str | None:
    """None nếu trong hạn mức. Tổng ngày/tháng tính trên các yêu cầu chưa bị giải phóng của chính khách (ADR-059)."""
    limits = active_limits(conn)
    if limits is None:
        return "limits_missing"
    if amount < limits.min_vnd:
        return "below_min"
    if amount > limits.max_per_request_vnd:
        return "over_request_limit"
    for since, cap, code in _windows(limits, now):
        if _used_since(conn, user_id, since, exclude_id) + amount > cap:
            return code
    return None


def limit_room(conn: sqlite3.Connection, user_id: int, now: datetime) -> int | None:
    """Số lớn nhất khách được rút trong một yêu cầu lúc này: mỗi lần, phần còn lại của ngày và của tháng.
    None khi chưa có hạn mức đã duyệt."""
    limits = active_limits(conn)
    if limits is None:
        return None
    room = limits.max_per_request_vnd
    for since, cap, _code in _windows(limits, now):
        room = min(room, cap - _used_since(conn, user_id, since, None))
    return max(0, room)


def request_amount(conn: sqlite3.Connection, user_id: int, now: datetime) -> int:
    """Số mặc định của nút Rút: toàn bộ số rút được, cắt theo hạn mức còn lại (phần dư rút lần sau)."""
    can = withdrawable(conn, user_id)
    room = limit_room(conn, user_id, now)
    return can if room is None else min(can, room)


# --- Tài khoản nhận tiền -------------------------------------------------------------------------


def bank_status(conn: sqlite3.Connection, user_id: int, sha: str | None) -> str:
    """VERIFIED / REJECTED / UNVERIFIED cho đúng tài khoản (sha). Đổi tài khoản thì về UNVERIFIED."""
    if not sha:
        return "UNVERIFIED"
    row = conn.execute(
        "SELECT status FROM bank_account_verifications WHERE telegram_user_id = ? AND account_sha = ? "
        "ORDER BY id DESC LIMIT 1",
        (user_id, sha),
    ).fetchone()
    return "UNVERIFIED" if row is None else str(row[0])


def bank_cooldown_until(conn: sqlite3.Connection, user_id: int, sha: str | None) -> datetime | None:
    """Tài khoản vừa đổi (không phải khai lần đầu) và chưa được admin xác minh: rút được từ thời điểm trả về.
    None: không phải chờ."""
    if not sha or bank_status(conn, user_id, sha) == "VERIFIED":
        return None
    row = conn.execute(
        "SELECT action, created_at FROM bank_account_history WHERE telegram_user_id = ? AND account_sha = ? "
        "ORDER BY id DESC LIMIT 1",
        (user_id, sha),
    ).fetchone()
    if row is None or row["action"] != "change":
        return None
    try:
        changed = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return changed + BANK_COOLDOWN


def sources_available(conn: sqlite3.Connection, payout_id: int) -> bool:
    """Mọi khoản nguồn của yêu cầu còn 'available'. Yêu cầu cũ không có phân bổ thì không chặn."""
    return conn.execute(
        "SELECT 1 FROM payout_allocations a LEFT JOIN cashback_entries e ON e.conversion_id = a.conversion_id "
        "WHERE a.payout_id = ? AND COALESCE(e.status, '') != 'available' LIMIT 1",
        (payout_id,),
    ).fetchone() is None


def shared_account_users(conn: sqlite3.Connection, sha: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(DISTINCT telegram_user_id) FROM bank_account_history WHERE account_sha = ?", (sha,)
    ).fetchone()[0])


def verify_bank(conn: sqlite3.Connection, user_id: int, sha: str, admin_id: int, method: str, evidence: str,
                now: datetime, verified: bool = True) -> None:
    proof = clean_text(evidence, 300)
    if len(proof) < EVIDENCE_MIN:
        raise PayoutError("evidence")
    conn.execute(
        """
        INSERT INTO bank_account_verifications (telegram_user_id, account_sha, status, method, evidence_ref,
            decided_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, sha, "VERIFIED" if verified else "REJECTED", method, proof, admin_id, stamp(now)),
    )


def record_bank_change(conn: sqlite3.Connection, user_id: int, bank_code: str, account_no: str, account_name: str,
                       previous_sha: str | None, now: datetime) -> list[int]:
    """Ghi lịch sử (không lưu số đầy đủ). Yêu cầu rút còn mở mang tài khoản khác thì chuyển cần kiểm tra.

    Yêu cầu giữ nguyên tài khoản đã chụp lúc tạo; bot không âm thầm đổi đích chuyển. Trả id các yêu cầu bị chuyển.
    """
    sha = account_sha(bank_code, account_no)
    if sha == previous_sha:
        return []
    conn.execute(
        """
        INSERT INTO bank_account_history (telegram_user_id, bank_code, account_last4, account_sha, account_name,
            action, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, bank_code, account_no[-4:], sha, account_name, "add" if previous_sha is None else "change", stamp(now)),
    )
    moved = []
    marks = ", ".join("?" for _ in OPEN if _ != NEEDS_REVIEW)
    rows = conn.execute(
        f"SELECT * FROM cashback_payouts WHERE telegram_user_id = ? AND status IN ({marks})",
        (user_id, *[s for s in OPEN if s != NEEDS_REVIEW]),
    ).fetchall()
    for row in rows:
        if row["account_sha"] and row["account_sha"] == sha:
            continue
        _move(conn, row, NEEDS_REVIEW, f"user:{user_id}", "Khách đổi tài khoản nhận tiền sau khi gửi yêu cầu", None, now)
        moved.append(int(row["id"]))
    return moved


# --- Sổ: số còn rút được theo từng khoản ---------------------------------------------------------


def _remaining_by_entry(conn: sqlite3.Connection, user_id: int) -> list[tuple[str, int]]:
    """(conversion, còn lại) của các khoản available, cũ trước. Đã giữ hoặc đã trả cho yêu cầu khác thì trừ."""
    marks = ", ".join("?" for _ in (*OPEN, *PAID_STATES))
    rows = conn.execute(
        f"""
        SELECT e.conversion_id, e.cashback_vnd,
               COALESCE((SELECT SUM(a.amount_vnd) FROM payout_allocations a JOIN cashback_payouts p ON p.id = a.payout_id
                         WHERE a.conversion_id = e.conversion_id AND p.status IN ({marks})), 0) AS used
        FROM cashback_entries e
        WHERE e.telegram_user_id = ? AND e.status = 'available'
        ORDER BY COALESCE(e.completed_at, e.created_at), e.conversion_id
        """,
        (*OPEN, *PAID_STATES, user_id),
    ).fetchall()
    return [(str(row[0]), int(row[1]) - int(row[2])) for row in rows if int(row[1]) - int(row[2]) > 0]


def withdrawable(conn: sqlite3.Connection, user_id: int) -> int:
    """Rút được = available − đang giữ − đã trả (cả yêu cầu cũ không có phân bổ)."""
    available = int(conn.execute(
        "SELECT COALESCE(SUM(cashback_vnd), 0) FROM cashback_entries WHERE telegram_user_id = ? AND status = 'available'",
        (user_id,),
    ).fetchone()[0])
    reserved, paid = payout_totals(conn, user_id)
    return available - reserved - paid


# --- Tạo yêu cầu ---------------------------------------------------------------------------------


def create_request(
    conn: sqlite3.Connection,
    user_id: int,
    account,
    amount: int | None,
    min_vnd: int,
    now: datetime,
    idempotency_key: str | None = None,
    fund_check=None,
) -> tuple[sqlite3.Row | None, str]:
    """Trong một transaction BEGIN IMMEDIATE. Trả (yêu cầu, 'ok' | 'duplicate') hoặc (None, mã lỗi).

    fund_check(conn, amount) → mã lỗi hoặc None: khoá tài chính cũ (shopee_settlements) do payout_gate cấp.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            old = conn.execute("SELECT * FROM cashback_payouts WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if old is not None:
                conn.commit()
                return old, "duplicate"
        marks = ", ".join("?" for _ in OPEN)
        if conn.execute(
            f"SELECT 1 FROM cashback_payouts WHERE telegram_user_id = ? AND status IN ({marks})", (user_id, *OPEN)
        ).fetchone():
            conn.rollback()
            return None, "pending_exists"
        can = withdrawable(conn, user_id)
        want = request_amount(conn, user_id, now) if amount is None else int(amount)
        if want <= 0 or want > can:
            conn.rollback()
            return None, "below_min" if amount is None else "insufficient"
        if want < min_vnd:
            conn.rollback()
            return None, "below_min"
        limit = check_limits(conn, user_id, want, now)
        if limit is not None:
            conn.rollback()
            return None, limit
        sha = account_sha(account.bank_code, account.account_no)
        until = bank_cooldown_until(conn, user_id, sha)
        if until is not None and now < until:
            conn.rollback()
            return None, "bank_cooldown"
        fund = fund_position(conn)
        if not fund.verified or fund.headroom_vnd < want:
            conn.rollback()
            return None, "fund"
        if fund_check is not None:
            blocked = fund_check(conn, want)
            if blocked:
                conn.rollback()
                return None, blocked
        cursor = conn.execute(
            """
            INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, account_name,
                created_at, version, idempotency_key, account_sha)
            VALUES (?, ?, 'requested', ?, ?, ?, ?, 1, ?, ?)
            """,
            (user_id, want, account.bank_code, account.account_no, account.account_name, stamp(now), idempotency_key, sha),
        )
        payout_id = int(cursor.lastrowid)
        conn.execute("UPDATE cashback_payouts SET transfer_note = ? WHERE id = ?", (transfer_note(payout_id), payout_id))
        left = want
        for conversion_id, remaining in _remaining_by_entry(conn, user_id):
            take = min(left, remaining)
            conn.execute(
                "INSERT INTO payout_allocations (payout_id, conversion_id, amount_vnd, created_at) VALUES (?, ?, ?, ?)",
                (payout_id, conversion_id, take, stamp(now)),
            )
            left -= take
            if left == 0:
                break
        if left != 0:
            raise PayoutError("allocation")
        conn.execute(
            """
            INSERT INTO payout_events (payout_id, from_status, to_status, actor, version, idempotency_key, created_at)
            VALUES (?, NULL, 'requested', ?, 1, ?, ?)
            """,
            (payout_id, f"user:{user_id}", None if idempotency_key is None else f"create:{idempotency_key}", stamp(now)),
        )
        problems = structural_problems(conn, user_id)
        if problems:
            raise PayoutError("invariant:" + problems[0])
        row = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()
        conn.commit()
        return row, "ok"
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


# --- Đổi trạng thái ------------------------------------------------------------------------------


def ever_reached(conn: sqlite3.Connection, payout_id: int, statuses: tuple[str, ...]) -> bool:
    marks = ", ".join("?" for _ in statuses)
    return conn.execute(
        f"SELECT 1 FROM payout_events WHERE payout_id = ? AND to_status IN ({marks}) LIMIT 1", (payout_id, *statuses)
    ).fetchone() is not None


def _move(conn, row: sqlite3.Row, target: str, actor: str, note: str | None, evidence: str | None,
          now: datetime, idempotency_key: str | None = None) -> None:
    version = int(row["version"] or 1)
    conn.execute(
        """
        INSERT INTO payout_events (payout_id, from_status, to_status, actor, note, evidence_ref, version,
            idempotency_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (row["id"], row["status"], target, actor, note, evidence, version + 1, idempotency_key, stamp(now)),
    )
    updated = conn.execute(
        """
        UPDATE cashback_payouts SET status = ?, version = ?, decided_at = ?, decided_by = ?
        WHERE id = ? AND status = ? AND version = ?
        """,
        (target, version + 1, stamp(now), _admin_id(actor), row["id"], row["status"], version),
    )
    if updated.rowcount != 1:
        raise PayoutError("stale")


def _admin_id(actor: str) -> int | None:
    return int(actor.split(":", 1)[1]) if actor.startswith("admin:") else None


def transition(
    conn: sqlite3.Connection,
    payout_id: int,
    target: str,
    admin_id: int,
    expected_version: int,
    now: datetime,
    note: str | None = None,
    evidence: str | None = None,
    idempotency_key: str | None = None,
    money_out_check=None,
) -> tuple[sqlite3.Row | None, str]:
    """Một bước của máy trạng thái, trong BEGIN IMMEDIATE. Trả (yêu cầu sau bước, 'ok' | 'duplicate') hoặc lỗi.

    money_out_check(conn, row) → mã lỗi hoặc None: khoá tài chính, tài khoản đã xác minh, quỹ, hạn mức.
    Chạy lại ở đây mỗi lần bấm, không tin trạng thái nút.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key and conn.execute(
            "SELECT 1 FROM payout_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone():
            row = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()
            conn.commit()
            return row, "duplicate"
        row = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()
        if row is None:
            conn.rollback()
            return None, "not_found"
        if int(row["version"] or 1) != expected_version:
            conn.rollback()
            return row, "stale"
        rule = TRANSITIONS.get(row["status"], {}).get(target)
        if rule is None:
            conn.rollback()
            return row, "transition"
        reason = clean_text(note or "", 300) or None
        proof = clean_text(evidence or "", 300) or None
        if rule.needs_reason and not reason:
            conn.rollback()
            return row, "reason"
        if rule.needs_evidence and (proof is None or len(proof) < EVIDENCE_MIN):
            conn.rollback()
            return row, "evidence"
        money_left = ever_reached(conn, payout_id, MONEY_LEFT)
        if target in (REJECTED, CANCELLED, UNDER_REVIEW) and money_left:
            conn.rollback()
            return row, "money_may_have_left"
        if row["status"] == NEEDS_REVIEW and target == SENT and not money_left:
            # Chưa từng bắt đầu chuyển thì phải đi lại vòng duyệt, không nhảy thẳng tới «đã gửi».
            conn.rollback()
            return row, "transition"
        if target in SOURCE_CHECKED and not sources_available(conn, payout_id):
            conn.rollback()
            return row, "source_changed"
        if rule.money_out and money_out_check is not None:
            blocked = money_out_check(conn, row)
            if blocked:
                conn.rollback()
                return row, blocked
        _move(conn, row, target, f"admin:{admin_id}", reason, proof, now, idempotency_key)
        problems = structural_problems(conn, int(row["telegram_user_id"]))
        if problems:
            raise PayoutError("invariant:" + problems[0])
        fresh = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone()
        conn.commit()
        return fresh, "ok"
    except sqlite3.IntegrityError as exc:
        if conn.in_transaction:
            conn.rollback()
        if "financial_lock" in str(exc):
            return conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (payout_id,)).fetchone(), "locked"
        raise
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


# --- Truy vết và bất biến ------------------------------------------------------------------------


def allocations(conn: sqlite3.Connection, payout_id: int) -> list[sqlite3.Row]:
    """Mỗi đồng của yêu cầu: khoản sổ ví, link, snapshot chính sách, trạng thái duyệt / đối soát, kỳ đối soát."""
    return conn.execute(
        """
        SELECT a.conversion_id, a.amount_vnd, e.order_sn, e.cashback_vnd, e.status AS entry_status, e.link_id,
               l.sub_id, s.policy_label, s.provenance, c.validation_status, c.settlement_status,
               (SELECT GROUP_CONCAT(DISTINCT i.batch_id) FROM settlement_items i
                WHERE i.conversion_id = a.conversion_id AND i.match_status = 'MATCHED') AS batches
        FROM payout_allocations a
        LEFT JOIN cashback_entries e ON e.conversion_id = a.conversion_id
        LEFT JOIN link_requests l ON l.id = e.link_id
        LEFT JOIN link_policy_snapshots s ON s.link_id = e.link_id
        LEFT JOIN shopee_conversions c ON c.conversion_id = a.conversion_id
        WHERE a.payout_id = ? ORDER BY a.id
        """,
        (payout_id,),
    ).fetchall()


def events(conn: sqlite3.Connection, payout_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM payout_events WHERE payout_id = ? ORDER BY id", (payout_id,)).fetchall()


def invariants(conn: sqlite3.Connection, user_id: int | None = None) -> list[str]:
    """Danh sách vi phạm (rỗng = ổn). Kiểm sau mỗi lần ghi và hiện ở màn admin."""
    problems: list[str] = []
    where, args = ("WHERE p.telegram_user_id = ?", (user_id,)) if user_id is not None else ("", ())
    for row in conn.execute(
        f"""
        SELECT p.id, p.amount_vnd, p.status, COALESCE(SUM(a.amount_vnd), 0) AS allocated, COUNT(a.id) AS n
        FROM cashback_payouts p LEFT JOIN payout_allocations a ON a.payout_id = p.id {where}
        GROUP BY p.id
        """,
        args,
    ):
        if row["n"] and int(row["allocated"]) != int(row["amount_vnd"]):
            problems.append(f"payout_{row['id']}_allocation_mismatch")
    marks = ", ".join("?" for _ in (*OPEN, *PAID_STATES))
    user_filter = "AND e.telegram_user_id = ?" if user_id is not None else ""
    for row in conn.execute(
        f"""
        SELECT a.conversion_id, e.cashback_vnd, e.status, SUM(a.amount_vnd) AS used,
               SUM(CASE WHEN p.status IN ({', '.join('?' for _ in OPEN)}) THEN 1 ELSE 0 END) AS open_n
        FROM payout_allocations a JOIN cashback_payouts p ON p.id = a.payout_id
        LEFT JOIN cashback_entries e ON e.conversion_id = a.conversion_id
        WHERE p.status IN ({marks}) {user_filter}
        GROUP BY a.conversion_id
        """,
        (*OPEN, *OPEN, *PAID_STATES, *args),
    ):
        if row["cashback_vnd"] is None or int(row["used"]) > int(row["cashback_vnd"]):
            problems.append(f"entry_{row['conversion_id']}_over_allocated")
        if row["open_n"] and row["status"] != "available":
            problems.append(f"entry_{row['conversion_id']}_reserved_but_{row['status']}")
    users = [user_id] if user_id is not None else [
        int(r[0]) for r in conn.execute("SELECT DISTINCT telegram_user_id FROM cashback_payouts")
    ]
    for uid in users:
        if withdrawable(conn, uid) < 0:
            problems.append(f"user_{uid}_negative_balance")
    return problems


def structural_problems(conn: sqlite3.Connection, user_id: int | None = None) -> list[str]:
    """Vi phạm làm sai sổ (phân bổ lệch, giữ quá số): chặn mọi lần ghi. Khoản bị huỷ khi đang giữ hay số dư âm
    do thu hồi thì không chặn ghi, chỉ báo và đưa yêu cầu sang cần kiểm tra."""
    return [p for p in invariants(conn, user_id) if p.endswith("_allocation_mismatch") or p.endswith("_over_allocated")]


def flag_cancelled_reservations(conn: sqlite3.Connection, now: datetime) -> list[int]:
    """Khoản đang giữ cho yêu cầu rút mà Shopee huỷ / từ chối sau đó, hoặc số dư khách âm do thu hồi: yêu cầu
    chuyển cần kiểm tra. Không trừ tiền."""
    states = tuple(s for s in OPEN if s != NEEDS_REVIEW)
    marks = ", ".join("?" for _ in states)
    rows = conn.execute(
        f"""
        SELECT DISTINCT p.* FROM cashback_payouts p
        JOIN payout_allocations a ON a.payout_id = p.id
        JOIN cashback_entries e ON e.conversion_id = a.conversion_id
        WHERE p.status IN ({marks}) AND e.status != 'available'
        """,
        states,
    ).fetchall()
    flagged = {int(row["id"]) for row in rows}
    for row in rows:
        _move(conn, row, NEEDS_REVIEW, "system", "Khoản nguồn không còn đủ điều kiện (Shopee huỷ hoặc điều chỉnh)", None, now)
    for row in conn.execute(f"SELECT * FROM cashback_payouts WHERE status IN ({marks})", states).fetchall():
        if int(row["id"]) not in flagged and withdrawable(conn, int(row["telegram_user_id"])) < 0:
            _move(conn, row, NEEDS_REVIEW, "system", "Shopee giảm hoa hồng đơn đã vào ví: số dư khách âm", None, now)
            flagged.add(int(row["id"]))
    return sorted(flagged)
