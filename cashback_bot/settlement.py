"""Đối soát thanh toán Shopee và quỹ cashback (PLAN-075, ADR-052).

Ba bước, độc lập với giao diện Telegram:
1. Duyệt hoa hồng: chỉ lưu số Shopee báo duyệt kèm chứng từ. KHÔNG đổi validation_status
   (APPROVED vẫn BLOCKED theo ADR-051 cho tới khi nghiệm thu riêng).
2. Đối soát kỳ: báo cáo thanh toán Shopee ↔ số học tổng kỳ ↔ tiền ngân hàng thực nhận.
3. Phân bổ quỹ: tách tiền đơn qua bot / ngoài bot / không rõ đơn. Không chia theo tỷ lệ ước lượng;
   phí, thuế không có chi tiết theo đơn thì để "chưa phân bổ".

Chứng từ vào bằng định dạng chuẩn nội bộ `cashback_settlement_v1` (không phải định dạng Shopee).
Chưa có mẫu báo cáo Shopee thật nên chưa có parser cho file Shopee; parser sau này phải chuyển về
định dạng này. Không đường nào trong module này mở ví, tạo payout hay đổi cashback_entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cashback_bot.commission_validation import FRAUD, REJECTED
from cashback_bot.db import TrackingRepository

FORMAT = "cashback_settlement_v1"
KINDS = ("shopee_validation_report", "shopee_payment_report", "bank_statement")
MAX_BYTES = 2_000_000
MAX_ITEMS = 20_000
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_REF = re.compile(r"^[0-9A-Za-z._:/-]{1,64}$")

DRAFT, EVIDENCE_PENDING, PARTIALLY_MATCHED, MATCHED, DISPUTED, REVERSED = (
    "DRAFT", "EVIDENCE_PENDING", "PARTIALLY_MATCHED", "MATCHED", "DISPUTED", "REVERSED")

# Mã chênh lệch → trạng thái kỳ mà nó kéo theo.
_DISPUTE = {"STATEMENT_ARITHMETIC", "BANK_SHORT", "BANK_OVER", "OVER_ALLOCATED"}
_PENDING = {"NO_STATEMENT", "NO_BANK", "TOTALS_INCOMPLETE"}


class EvidenceError(ValueError):
    """Chứng từ bị từ chối. `code` để test và admin đọc, không chứa nội dung file."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Discrepancy:
    code: str
    amount_vnd: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class Reconciliation:
    batch_id: int
    status: str
    discrepancies: tuple[Discrepancy, ...]
    expected_payout_vnd: int | None
    bot_vnd: int
    non_bot_vnd: int
    unknown_vnd: int
    review_vnd: int
    unallocated_vnd: int | None
    eligible_fund_vnd: int | None  # chỉ có khi kỳ MATCHED; vẫn KHÔNG phải tiền được rút


@dataclass(frozen=True)
class Statement:
    kind: str
    period: str
    document_ref: str
    payment_ref: str | None
    totals: dict = field(default_factory=dict)
    items: tuple[dict, ...] = ()
    bank: dict = field(default_factory=dict)


def _stamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _vnd(value, name: str, allow_negative: bool = False, allow_none: bool = True) -> int | None:
    """Tiền VND nguyên. Từ chối float, chuỗi, bool: nguồn tiền không được qua dấu phẩy động."""
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"bad_amount:{name}")
    if value < 0 and not allow_negative:
        raise EvidenceError(f"negative_amount:{name}")
    if abs(value) > 10**13:
        raise EvidenceError(f"amount_too_large:{name}")
    return value


def parse_statement(raw: bytes) -> Statement:
    """Đọc và kiểm tra chặt chứng từ định dạng chuẩn. Không thực thi gì từ nội dung file."""
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise EvidenceError("empty")
    if len(raw) > MAX_BYTES:
        raise EvidenceError("too_large")
    try:
        data = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise EvidenceError("not_canonical_json") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise EvidenceError("not_canonical_json")
    kind = data.get("kind")
    if kind not in KINDS:
        raise EvidenceError("bad_kind")
    period, ref = data.get("period"), data.get("document_ref")
    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        raise EvidenceError("bad_period")
    if not isinstance(ref, str) or not _REF.fullmatch(ref):
        raise EvidenceError("bad_document_ref")
    payment_ref = data.get("shopee_payment_ref")
    if payment_ref is not None and (not isinstance(payment_ref, str) or not _REF.fullmatch(payment_ref)):
        raise EvidenceError("bad_payment_ref")

    totals: dict = {}
    items: list[dict] = []
    bank: dict = {}
    if kind == "bank_statement":
        raw_bank = data.get("bank")
        if not isinstance(raw_bank, dict):
            raise EvidenceError("missing_bank")
        bank = {"received_vnd": _vnd(raw_bank.get("received_vnd"), "received_vnd", allow_none=False)}
        if bank["received_vnd"] <= 0:
            raise EvidenceError("bad_amount:received_vnd")
    else:
        if kind == "shopee_payment_report":
            raw_totals = data.get("totals")
            if not isinstance(raw_totals, dict):
                raise EvidenceError("missing_totals")
            totals = {
                "reported_commission_vnd": _vnd(raw_totals.get("reported_commission_vnd"), "reported_commission_vnd"),
                "adjustments_vnd": _vnd(raw_totals.get("adjustments_vnd"), "adjustments_vnd", allow_negative=True),
                "fee_vnd": _vnd(raw_totals.get("fee_vnd"), "fee_vnd"),
                "fee_vat_vnd": _vnd(raw_totals.get("fee_vat_vnd"), "fee_vat_vnd"),
                "tax_withheld_vnd": _vnd(raw_totals.get("tax_withheld_vnd"), "tax_withheld_vnd"),
                "payout_vnd": _vnd(raw_totals.get("payout_vnd"), "payout_vnd"),
            }
            inc = raw_totals.get("fee_includes_vat")
            if inc is not None and not isinstance(inc, bool):
                raise EvidenceError("bad_fee_includes_vat")
            totals["fee_includes_vat"] = inc
        raw_items = data.get("items") or []
        if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
            raise EvidenceError("bad_items")
        seen: set[str] = set()
        for entry in raw_items:
            if not isinstance(entry, dict):
                raise EvidenceError("bad_items")
            order_ref = entry.get("order_ref")
            if not isinstance(order_ref, str) or not _REF.fullmatch(order_ref):
                raise EvidenceError("bad_order_ref")
            if order_ref in seen:
                raise EvidenceError("duplicate_order_in_document")
            seen.add(order_ref)
            items.append({
                "order_ref": order_ref,
                "approved_vnd": _vnd(entry.get("approved_vnd"), "approved_vnd"),
                "settled_vnd": _vnd(entry.get("settled_vnd"), "settled_vnd"),
                "adjustment_vnd": _vnd(entry.get("adjustment_vnd"), "adjustment_vnd", allow_negative=True),
            })
    return Statement(kind, period, ref, payment_ref, totals, tuple(items), bank)


class SettlementEngine:
    def __init__(self, repo: TrackingRepository, evidence_dir: Path | str | None = None):
        self.repo = repo
        self.evidence_dir = Path(evidence_dir) if evidence_dir else Path(repo.path).resolve().parent / "settlement_evidence"

    # --- Kỳ thanh toán -------------------------------------------------------------------------

    def create_batch(self, period: str, actor: str, payment_ref: str | None = None) -> int:
        if not _PERIOD.fullmatch(period or ""):
            raise EvidenceError("bad_period")
        if payment_ref is not None and not _REF.fullmatch(payment_ref):
            raise EvidenceError("bad_payment_ref")
        now = _stamp()
        with self.repo.connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO settlement_batches (period, shopee_payment_ref, status, created_by, created_at, updated_at) "
                    "VALUES (?, ?, 'DRAFT', ?, ?, ?)",
                    (period, payment_ref, actor, now, now),
                )
            except sqlite3.IntegrityError:
                raise EvidenceError("duplicate_batch") from None
            batch_id = int(cursor.lastrowid)
            self._audit(conn, batch_id, "batch_create", actor, {"period": period, "payment_ref": payment_ref})
        return batch_id

    def reverse(self, batch_id: int, actor: str, reason: str) -> Reconciliation:
        """Đảo một kỳ đã nhập (nhập nhầm, Shopee huỷ lệnh trả). Giữ nguyên chứng cứ và item."""
        with self.repo.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._batch(conn, batch_id)
            conn.execute("UPDATE settlement_batches SET status = 'REVERSED', updated_at = ? WHERE id = ?", (_stamp(), batch_id))
            self._audit(conn, batch_id, "batch_reverse", actor, {"from": row["status"], "reason": reason[:200]})
            self._sync_conversion_settlement(conn, batch_id)
        return self.reconcile(batch_id, actor)

    # --- Chứng cứ -----------------------------------------------------------------------------

    def import_document(self, batch_id: int, raw: bytes, actor: str, replaces: int | None = None) -> int:
        """Nhập một chứng từ định dạng chuẩn vào kỳ. Trả evidence_id.

        Chống trùng theo nội dung (sha256) và theo (loại, mã chứng từ). Thay chứng từ phải nói rõ
        `replaces`; chứng từ cũ giữ nguyên, chỉ đánh dấu SUPERSEDED.
        """
        statement = parse_statement(raw)
        digest = hashlib.sha256(bytes(raw)).hexdigest()
        now = _stamp()
        with self.repo.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            batch = self._batch(conn, batch_id)
            if batch["status"] == REVERSED:
                raise EvidenceError("batch_reversed")
            if statement.period != batch["period"]:
                raise EvidenceError("period_mismatch")
            if batch["shopee_payment_ref"] and statement.payment_ref and statement.payment_ref != batch["shopee_payment_ref"]:
                raise EvidenceError("payment_ref_mismatch")
            slot = {"shopee_payment_report": "statement_evidence_id", "bank_statement": "bank_evidence_id"}.get(statement.kind)
            if slot and batch[slot] is not None and replaces != batch[slot]:
                raise EvidenceError("slot_taken_use_replaces")
            if replaces is not None:
                old = conn.execute("SELECT * FROM settlement_evidence WHERE id = ? AND batch_id = ?", (replaces, batch_id)).fetchone()
                if old is None or old["kind"] != statement.kind or old["verification"] == "SUPERSEDED":
                    raise EvidenceError("bad_replaces")
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO settlement_evidence (batch_id, kind, source, document_ref, content_sha256, stored_name,
                        size_bytes, parser, verification, recorded_by, recorded_at)
                    VALUES (?, ?, 'import', ?, ?, ?, ?, ?, 'RECEIVED', ?, ?)
                    """,
                    (batch_id, statement.kind, statement.document_ref, digest, f"{digest}.json", len(raw), FORMAT, actor, now),
                )
            except sqlite3.IntegrityError:
                raise EvidenceError("duplicate_evidence") from None
            evidence_id = int(cursor.lastrowid)
            self._store(digest, bytes(raw))
            if replaces is not None:
                conn.execute(
                    "UPDATE settlement_evidence SET verification = 'SUPERSEDED', superseded_by = ? WHERE id = ?",
                    (evidence_id, replaces),
                )
                conn.execute("DELETE FROM settlement_items WHERE evidence_id = ?", (replaces,))
            if statement.kind == "shopee_payment_report":
                totals = statement.totals
                conn.execute(
                    """
                    UPDATE settlement_batches SET reported_commission_vnd = ?, adjustments_vnd = ?, fee_vnd = ?,
                        fee_vat_vnd = ?, fee_includes_vat = ?, tax_withheld_vnd = ?, shopee_payout_vnd = ?,
                        statement_evidence_id = ?, shopee_payment_ref = COALESCE(shopee_payment_ref, ?), updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        totals["reported_commission_vnd"], totals["adjustments_vnd"], totals["fee_vnd"], totals["fee_vat_vnd"],
                        None if totals["fee_includes_vat"] is None else int(totals["fee_includes_vat"]),
                        totals["tax_withheld_vnd"], totals["payout_vnd"], evidence_id, statement.payment_ref, now, batch_id,
                    ),
                )
            elif statement.kind == "bank_statement":
                conn.execute(
                    "UPDATE settlement_batches SET bank_received_vnd = ?, bank_evidence_id = ?, updated_at = ? WHERE id = ?",
                    (statement.bank["received_vnd"], evidence_id, now, batch_id),
                )
            for item in statement.items:
                self._insert_item(conn, batch_id, evidence_id, item, now)
            self._audit(conn, batch_id, "evidence_import", actor, {
                "evidence_id": evidence_id, "kind": statement.kind, "document_ref": statement.document_ref,
                "sha256": digest, "items": len(statement.items), "replaces": replaces, "totals": statement.totals,
                "bank": statement.bank,
            })
        self.reconcile(batch_id, actor)
        return evidence_id

    def mark_viewed(self, evidence_id: int, admin_id: int) -> bool:
        """Admin đã xem chứng từ. KHÔNG phải xác minh, không đổi trạng thái kỳ hay hoa hồng."""
        with self.repo.connect() as conn:
            row = conn.execute("SELECT batch_id, viewed_by FROM settlement_evidence WHERE id = ?", (evidence_id,)).fetchone()
            if row is None or row["viewed_by"] is not None:
                return False
            conn.execute("UPDATE settlement_evidence SET viewed_by = ?, viewed_at = ? WHERE id = ?", (admin_id, _stamp(), evidence_id))
            self._audit(conn, row["batch_id"], "evidence_viewed", f"admin:{admin_id}", {"evidence_id": evidence_id})
        return True

    def _store(self, digest: str, raw: bytes) -> None:
        """Lưu bản gốc theo tên sha256 (không dùng tên file người gửi: không có path traversal)."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.evidence_dir, 0o700)
        target = self.evidence_dir / f"{digest}.json"
        if target.exists():
            return
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)

    def _insert_item(self, conn: sqlite3.Connection, batch_id: int, evidence_id: int, item: dict, now: str) -> None:
        conv = conn.execute(
            "SELECT conversion_id, matched_link_id, telegram_user_id, net_commission_vnd, validation_status "
            # Báo cáo thanh toán Shopee chỉ khớp đơn Shopee (đơn TikTok có order_sn riêng của TikTok).
            "FROM shopee_conversions WHERE platform = 'shopee' AND (order_sn = ? OR conversion_id = ?) LIMIT 1",
            (item["order_ref"], item["order_ref"]),
        ).fetchone()
        settled = item["settled_vnd"]
        conversion_id = None if conv is None else conv["conversion_id"]
        is_bot = conv is not None and conv["matched_link_id"] is not None
        if conv is None:
            status = "UNKNOWN_ORDER"
        elif settled is None:
            status = "MATCHED" if is_bot else "NOT_BOT"  # báo cáo xác thực: chỉ có số duyệt
        elif not is_bot:
            status = "NOT_BOT"
        elif conv["validation_status"] in (FRAUD, REJECTED):
            status = "NEEDS_REVIEW"  # Shopee trả cho đơn bot đã đánh dấu gian lận/từ chối
        elif self._paid_elsewhere(conn, batch_id, conversion_id) and item["adjustment_vnd"] is None:
            status = "DUPLICATE"
        elif item["adjustment_vnd"] is None and conv["net_commission_vnd"] is not None and settled != conv["net_commission_vnd"]:
            status = "AMOUNT_MISMATCH"
        else:
            status = "MATCHED"
        conn.execute(
            """
            INSERT INTO settlement_items (batch_id, evidence_id, order_ref, conversion_id, is_bot, telegram_user_id,
                approved_vnd, settled_vnd, adjustment_vnd, match_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, evidence_id, item["order_ref"], conversion_id, int(is_bot),
                conv["telegram_user_id"] if is_bot else None,
                item["approved_vnd"], settled, item["adjustment_vnd"], status, now,
            ),
        )

    @staticmethod
    def _paid_elsewhere(conn: sqlite3.Connection, batch_id: int, conversion_id: str | None) -> bool:
        if conversion_id is None:
            return False
        row = conn.execute(
            """
            SELECT 1 FROM settlement_items i JOIN settlement_batches b ON b.id = i.batch_id
            WHERE i.conversion_id = ? AND i.batch_id != ? AND i.settled_vnd IS NOT NULL
              AND b.status != 'REVERSED' AND i.evidence_id = b.statement_evidence_id
            LIMIT 1
            """,
            (conversion_id, batch_id),
        ).fetchone()
        return row is not None

    # --- Đối soát ------------------------------------------------------------------------------

    def reconcile(self, batch_id: int, actor: str) -> Reconciliation:
        with self.repo.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            batch = self._batch(conn, batch_id)
            result = self._evaluate(conn, batch)
            if batch["status"] != REVERSED and result.status != batch["status"]:
                conn.execute("UPDATE settlement_batches SET status = ?, updated_at = ? WHERE id = ?", (result.status, _stamp(), batch_id))
            # Chứng từ chỉ VERIFIED khi hai nguồn độc lập khớp (báo cáo Shopee ↔ ngân hàng) và kỳ MATCHED.
            verified = result.status == MATCHED
            for slot in ("statement_evidence_id", "bank_evidence_id"):
                if batch[slot] is not None:
                    conn.execute(
                        "UPDATE settlement_evidence SET verification = ? WHERE id = ? AND verification IN ('RECEIVED', 'VERIFIED')",
                        ("VERIFIED" if verified else "RECEIVED", batch[slot]),
                    )
            self._sync_conversion_settlement(conn, batch_id)
            self._audit(conn, batch_id, "reconcile", actor, {
                "status": result.status, "discrepancies": [d.code for d in result.discrepancies],
                "bot_vnd": result.bot_vnd, "unallocated_vnd": result.unallocated_vnd,
            })
        return result

    def _evaluate(self, conn: sqlite3.Connection, batch: sqlite3.Row) -> Reconciliation:
        found: list[Discrepancy] = []
        statement_id = batch["statement_evidence_id"]
        items = [] if statement_id is None else conn.execute(
            "SELECT * FROM settlement_items WHERE evidence_id = ?", (statement_id,)
        ).fetchall()
        if statement_id is None:
            found.append(Discrepancy("NO_STATEMENT"))
        if batch["bank_evidence_id"] is None:
            found.append(Discrepancy("NO_BANK"))

        reported, adjustments = batch["reported_commission_vnd"], batch["adjustments_vnd"]
        fee, vat, tax, payout = batch["fee_vnd"], batch["fee_vat_vnd"], batch["tax_withheld_vnd"], batch["shopee_payout_vnd"]
        includes_vat = batch["fee_includes_vat"]
        expected = None
        if statement_id is not None:
            # Phí đã gồm VAT thì không trừ VAT lần nữa; chưa biết có gồm hay không thì chưa tính được.
            vat_part = 0 if includes_vat == 1 else vat
            needed = (reported, adjustments, fee, tax, payout, includes_vat, vat_part)
            if any(value is None for value in needed):
                found.append(Discrepancy("TOTALS_INCOMPLETE"))
            else:
                expected = reported + adjustments - fee - vat_part - tax
                if expected != payout:
                    found.append(Discrepancy("STATEMENT_ARITHMETIC", payout - expected))
        if payout is not None and batch["bank_received_vnd"] is not None:
            gap = batch["bank_received_vnd"] - payout
            if gap < 0:
                found.append(Discrepancy("BANK_SHORT", gap))
            elif gap > 0:
                found.append(Discrepancy("BANK_OVER", gap))

        def total(statuses: tuple[str, ...], bot: bool | None = None) -> int:
            return sum(
                (row["settled_vnd"] or 0) + (row["adjustment_vnd"] or 0)
                for row in items
                if row["match_status"] in statuses and (bot is None or bool(row["is_bot"]) == bot)
            )

        bot_vnd = total(("MATCHED",), bot=True)
        non_bot = total(("NOT_BOT",))
        unknown = total(("UNKNOWN_ORDER",))
        review = total(("AMOUNT_MISMATCH", "NEEDS_REVIEW", "DUPLICATE"))
        unallocated = None
        if statement_id is not None and reported is not None and adjustments is not None:
            allocated = bot_vnd + non_bot + unknown + review
            unallocated = reported + adjustments - allocated
            if unallocated < 0:
                found.append(Discrepancy("OVER_ALLOCATED", unallocated))
            elif unallocated > 0:
                found.append(Discrepancy("UNALLOCATED", unallocated))
        for row in items:
            if row["match_status"] in ("UNKNOWN_ORDER", "AMOUNT_MISMATCH", "NEEDS_REVIEW", "DUPLICATE"):
                found.append(Discrepancy(f"ITEM_{row['match_status']}", row["settled_vnd"], row["order_ref"]))

        codes = {d.code for d in found}
        if batch["status"] == REVERSED:
            status = REVERSED
        elif codes & _DISPUTE:
            status = DISPUTED
        elif codes & _PENDING:
            status = EVIDENCE_PENDING
        elif codes:
            status = PARTIALLY_MATCHED
        else:
            status = MATCHED
        return Reconciliation(
            batch_id=int(batch["id"]),
            status=status,
            discrepancies=tuple(found),
            expected_payout_vnd=expected,
            bot_vnd=bot_vnd,
            non_bot_vnd=non_bot,
            unknown_vnd=unknown,
            review_vnd=review,
            unallocated_vnd=unallocated,
            eligible_fund_vnd=bot_vnd if status == MATCHED else None,
        )

    def _sync_conversion_settlement(self, conn: sqlite3.Connection, batch_id: int) -> None:
        """settlement_status của đơn = SETTLED chỉ khi có item MATCHED trong một kỳ MATCHED (đã đối chiếu
        hai nguồn); kỳ bị đảo hoặc lệch thì trả về NOT_VERIFIED. Không đụng validation_status hay sổ ví."""
        ids = [row[0] for row in conn.execute(
            "SELECT DISTINCT conversion_id FROM settlement_items WHERE batch_id = ? AND conversion_id IS NOT NULL", (batch_id,)
        )]
        for conversion_id in ids:
            settled = conn.execute(
                """
                SELECT 1 FROM settlement_items i JOIN settlement_batches b ON b.id = i.batch_id
                WHERE i.conversion_id = ? AND i.match_status = 'MATCHED' AND i.settled_vnd IS NOT NULL
                  AND b.status = 'MATCHED' AND i.evidence_id = b.statement_evidence_id
                LIMIT 1
                """,
                (conversion_id,),
            ).fetchone()
            conn.execute(
                "UPDATE shopee_conversions SET settlement_status = ? WHERE conversion_id = ?",
                ("SETTLED" if settled else "NOT_VERIFIED", conversion_id),
            )

    # --- Điều chỉnh -----------------------------------------------------------------------------

    def scan_adjustments(self, actor: str = "system") -> int:
        """Đơn đã nằm trong kỳ MATCHED mà sau đó Shopee giảm hoa hồng hoặc gắn gian lận: ghi một dòng
        điều chỉnh OPEN cho mỗi sự kiện (khoá source + source_ref). Không thu hồi tiền, không đổi sổ ví."""
        created = 0
        now = _stamp()
        with self.repo.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT h.id, h.conversion_id, h.field, h.old_value, h.new_value, h.sync_run_id, h.detected_at,
                       i.batch_id, i.settled_vnd
                FROM shopee_conversion_changes h
                JOIN settlement_items i ON i.conversion_id = h.conversion_id AND i.match_status = 'MATCHED'
                    AND i.settled_vnd IS NOT NULL
                JOIN settlement_batches b ON b.id = i.batch_id AND b.status = 'MATCHED' AND i.evidence_id = b.statement_evidence_id
                WHERE h.detected_at >= i.created_at
                  AND (h.field = 'net_commission_vnd' OR (h.field = 'validation_status' AND h.new_value IN (?, ?)))
                ORDER BY h.id
                """,
                (FRAUD, REJECTED),
            ).fetchall()
            # Một lần Shopee báo (cùng đơn, cùng lần đồng bộ) là MỘT sự kiện: gian lận kéo hoa hồng về 0 sinh hai
            # dòng lịch sử nhưng chỉ được một điều chỉnh. Gian lận/từ chối ưu tiên hơn số hoa hồng mới.
            # Khoá sự kiện: lần đồng bộ (sync_run_id). Ghi ngoài đồng bộ (không có run) thì gom theo đơn + thời điểm
            # và lấy mã thay đổi lớn nhất của nhóm làm khoá, để hai lần báo trong cùng một giây không đè nhau.
            groups: dict[tuple, list] = {}
            for row in rows:
                groups.setdefault((row["conversion_id"], row["sync_run_id"] or row["detected_at"]), []).append(row)
            events: dict[str, dict] = {}
            for (conversion_id, scope), members in groups.items():
                run = members[0]["sync_run_id"]
                key = f"{conversion_id}:run{run}" if run else f"{conversion_id}:chg{max(m['id'] for m in members)}"
                events[key] = {"row": members[0], "new": None, "terminal": False, "members": members}
            for event in events.values():
                for row in event["members"]:
                    if row["field"] == "validation_status":
                        event["terminal"], event["new"] = True, 0
                    elif not event["terminal"]:
                        try:
                            event["new"] = int(row["new_value"])
                        except (TypeError, ValueError):
                            continue
            for key, event in events.items():
                row, settled, new = event["row"], int(event["row"]["settled_vnd"]), event["new"]
                if new is None or new >= settled:
                    continue
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO settlement_adjustments (conversion_id, original_batch_id, old_vnd, new_vnd,
                        delta_vnd, source, source_ref, status, detected_at)
                    VALUES (?, ?, ?, ?, ?, 'conversion_change', ?, 'OPEN', ?)
                    """,
                    (row["conversion_id"], row["batch_id"], settled, new, new - settled, key, now),
                )
                if cursor.rowcount:
                    created += 1
                    self._audit(conn, row["batch_id"], "adjustment_open", actor, {
                        "conversion_id": row["conversion_id"], "delta_vnd": new - settled, "event": key})
            for item in conn.execute(
                "SELECT i.* FROM settlement_items i JOIN settlement_batches b ON b.id = i.batch_id "
                "WHERE i.adjustment_vnd IS NOT NULL AND i.conversion_id IS NOT NULL AND b.status != 'REVERSED'"
            ).fetchall():
                prior = conn.execute(
                    "SELECT batch_id, settled_vnd FROM settlement_items WHERE conversion_id = ? AND batch_id != ? "
                    "AND settled_vnd IS NOT NULL ORDER BY id LIMIT 1",
                    (item["conversion_id"], item["batch_id"]),
                ).fetchone()
                old = 0 if prior is None else int(prior["settled_vnd"])
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO settlement_adjustments (conversion_id, original_batch_id, old_vnd, new_vnd,
                        delta_vnd, source, source_ref, status, detected_at)
                    VALUES (?, ?, ?, ?, ?, 'settlement_item', ?, 'OPEN', ?)
                    """,
                    (item["conversion_id"], None if prior is None else prior["batch_id"], old,
                     old + int(item["adjustment_vnd"]), int(item["adjustment_vnd"]), str(item["id"]), now),
                )
                if cursor.rowcount:
                    created += 1
                    self._audit(conn, item["batch_id"], "adjustment_open", actor, {
                        "conversion_id": item["conversion_id"], "delta_vnd": int(item["adjustment_vnd"]), "item_id": item["id"]})
        return created

    # --- Đọc cho màn admin ---------------------------------------------------------------------

    def batch(self, batch_id: int) -> sqlite3.Row | None:
        with self.repo.connect() as conn:
            return conn.execute("SELECT * FROM settlement_batches WHERE id = ?", (batch_id,)).fetchone()

    def evaluate(self, batch_id: int) -> Reconciliation:
        """Tính lại để hiển thị, không ghi gì."""
        with self.repo.connect() as conn:
            return self._evaluate(conn, self._batch(conn, batch_id))

    # --- Nội bộ ---------------------------------------------------------------------------------

    @staticmethod
    def _batch(conn: sqlite3.Connection, batch_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM settlement_batches WHERE id = ?", (batch_id,)).fetchone()
        if row is None:
            raise EvidenceError("no_batch")
        return row

    @staticmethod
    def _audit(conn: sqlite3.Connection, batch_id: int | None, action: str, actor: str, detail: dict) -> None:
        conn.execute(
            "INSERT INTO settlement_audit (batch_id, action, actor, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (batch_id, action, actor, json.dumps(detail, ensure_ascii=False, default=str), _stamp()),
        )
