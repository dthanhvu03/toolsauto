"""Màn /admin → 🔗 Shopee Affiliate → 🧾 Đối soát thanh toán (PLAN-075).

Xem kỳ thanh toán, chứng từ, đối chiếu tiền nhận, chênh lệch, đơn thuộc kỳ, lịch sử. Thao tác ghi duy nhất:
"👁 Đã xem chứng từ" (không phải xác minh) và "🔄 Đối soát lại" (tính lại từ chứng từ đã có). Không có nút
nhập số tiền, gán duyệt, gán đã trả hay mở ví. Thiếu chứng từ thì hiện "Chưa xác minh", không hiện 0đ.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.admin_notify import short_order
from cashback_bot.commission_validation import PENDING, UNKNOWN
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd
from cashback_bot.settlement import MATCHED, REVERSED, SettlementEngine

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:sm:home"
BACK_SHOPEE = (("◀️ Shopee Affiliate", "c:menu:shopee"),)
BACK_HOME = (("◀️ Đối soát thanh toán", HOME),)
NOT_VERIFIED = "Chưa xác minh"
LOCK_NOTE = (
    "ⓘ «Chứng từ khớp» chỉ nói chứng từ Shopee, số học và tiền ngân hàng khớp nhau. "
    "Ví khách vẫn khoá; thuế người nhận: <b>chưa duyệt</b>."
)
IMPORT_NOTE = (
    "📥 Nhập chứng từ bằng công cụ trên máy chủ: <code>python -m cashback_bot.settlement_import</code> "
    "(định dạng <code>cashback_settlement_v1</code>). Bot chưa nhận file qua Telegram.\n"
    "Cần: báo cáo Thanh toán Shopee Affiliate của kỳ, sao kê/chứng từ ngân hàng của khoản Shopee chuyển, "
    "và nếu có, báo cáo Xác thực hoa hồng."
)
STATUS_LABELS = {
    "DRAFT": "📝 Bản nháp",
    "EVIDENCE_PENDING": "⏳ Chờ chứng từ",
    "PARTIALLY_MATCHED": "🟡 Khớp một phần",
    "MATCHED": "✅ Chứng từ khớp",
    "DISPUTED": "🔴 Có chênh lệch",
    "REVERSED": "↩️ Đã đảo",
}
DISCREPANCY_LABELS = {
    "NO_STATEMENT": "chưa có báo cáo thanh toán Shopee",
    "NO_BANK": "chưa có chứng từ tiền về ngân hàng",
    "TOTALS_INCOMPLETE": "báo cáo Shopee thiếu số (phí, thuế, VAT hoặc điều chỉnh)",
    "STATEMENT_ARITHMETIC": "số học báo cáo Shopee không khớp",
    "BANK_SHORT": "ngân hàng nhận thiếu",
    "BANK_OVER": "ngân hàng nhận thừa",
    "OVER_ALLOCATED": "tổng theo đơn vượt tổng kỳ",
    "UNALLOCATED": "phần tiền chưa gắn được với đơn",
    "ITEM_UNKNOWN_ORDER": "khoản không rõ đơn",
    "ITEM_AMOUNT_MISMATCH": "khoản lệch số với hoa hồng bot ghi",
    "ITEM_NEEDS_REVIEW": "Shopee trả cho đơn bot đã gắn gian lận/từ chối",
    "ITEM_DUPLICATE": "đơn đã được trả ở kỳ khác",
}
ITEM_LABELS = {
    "MATCHED": "✅", "NOT_BOT": "➖ ngoài bot", "UNKNOWN_ORDER": "❔ không rõ đơn",
    "AMOUNT_MISMATCH": "⚠️ lệch số", "DUPLICATE": "⚠️ trùng kỳ", "NEEDS_REVIEW": "🔎 cần kiểm tra",
}
KIND_LABELS = {
    "shopee_validation_report": "Báo cáo xác thực Shopee",
    "shopee_payment_report": "Báo cáo thanh toán Shopee",
    "bank_statement": "Chứng từ ngân hàng",
}
VERIFY_LABELS = {"RECEIVED": "đã nhận, chưa đối chiếu", "VERIFIED": "đã đối chiếu hai nguồn", "SUPERSEDED": "đã thay", "REJECTED": "bị loại"}

_BATCH = re.compile(r"^c:sm:(b|items|ev|rc):(\d{1,9})$")
_EVIDENCE = re.compile(r"^c:sm:(e|seen):(\d{1,9})$")


def _money(value) -> str:
    return NOT_VERIFIED if value is None else format_vnd(int(value))


def _vn(stamp: str | None) -> str:
    if not stamp:
        return "-"
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return html.escape(stamp)
    return moment.astimezone(ICT).strftime("%H:%M %d/%m")


def _title(*path: str) -> str:
    return "⚙️ Quản trị › " + " › ".join(path[:-1] + (f"<b>{path[-1]}</b>",))


def _table(rows: list[tuple[str, str]]) -> str:
    width = max(len(label) for label, _ in rows)
    value_width = max(len(value) for _, value in rows)
    return "<pre>" + html.escape("\n".join(f"{label.ljust(width)} {value.rjust(value_width)}" for label, value in rows)) + "</pre>"


class SettlementAdmin:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo
        self.engine = SettlementEngine(repo)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self.home()
        if data == "c:sm:bl":
            return self.batches()
        if data == "c:sm:ev":
            return self.evidence_list(None)
        if data == "c:sm:bank":
            return self.bank()
        if data == "c:sm:diff":
            return self.differences()
        if data == "c:sm:h":
            return self.history()
        batch = _BATCH.fullmatch(data)
        if batch:
            action, batch_id = batch.group(1), int(batch.group(2))
            if self.engine.batch(batch_id) is None:
                return BotReply("Không tìm thấy kỳ thanh toán này.", inline_keyboard=(BACK_HOME,))
            if action == "b":
                return self.batch_detail(batch_id)
            if action == "items":
                return self.items(batch_id)
            if action == "ev":
                return self.evidence_list(batch_id)
            self.engine.reconcile(batch_id, f"admin:{admin_id}")
            return self.batch_detail(batch_id, "🔄 Đã đối soát lại từ chứng từ đang có.")
        evidence = _EVIDENCE.fullmatch(data)
        if evidence:
            evidence_id = int(evidence.group(2))
            if evidence.group(1) == "seen":
                ok = self.engine.mark_viewed(evidence_id, admin_id)
                return self.evidence_detail(evidence_id, "👁 Đã ghi nhận bạn đã xem (chưa phải xác minh)." if ok else "")
            return self.evidence_detail(evidence_id)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME,))

    # --- Tổng quan -------------------------------------------------------------------------------

    def home(self) -> BotReply:
        with self.repo.connect() as conn:
            pending = conn.execute(
                "SELECT COALESCE(SUM(net_commission_vnd), 0), COUNT(*) FROM shopee_conversions "
                f"WHERE matched_link_id IS NOT NULL AND validation_status IN ('{PENDING}', '{UNKNOWN}')"
            ).fetchone()
            latest = conn.execute(
                "SELECT * FROM settlement_batches WHERE status != 'REVERSED' ORDER BY period DESC, id DESC LIMIT 1"
            ).fetchone()
            review = int(conn.execute(
                "SELECT (SELECT COUNT(*) FROM settlement_adjustments WHERE status = 'OPEN') + "
                "(SELECT COUNT(*) FROM settlement_batches WHERE status IN ('DISPUTED', 'PARTIALLY_MATCHED'))"
            ).fetchone()[0])
            approved = None
            if latest is not None:
                row = conn.execute(
                    "SELECT SUM(approved_vnd), COUNT(approved_vnd) FROM settlement_items i "
                    "JOIN settlement_evidence e ON e.id = i.evidence_id "
                    "WHERE i.batch_id = ? AND e.kind = 'shopee_validation_report' AND e.verification != 'SUPERSEDED'",
                    (latest["id"],),
                ).fetchone()
                approved = row[0] if row[1] else None
        result = None if latest is None else self.engine.evaluate(int(latest["id"]))
        if latest is None:
            head = "Chưa có kỳ thanh toán nào được nhập."
        else:
            head = f"Kỳ gần nhất: <b>{latest['period']}</b> · {STATUS_LABELS.get(latest['status'], latest['status'])}"
        gap = None
        if latest is not None and latest["shopee_payout_vnd"] is not None and latest["bank_received_vnd"] is not None:
            gap = int(latest["bank_received_vnd"]) - int(latest["shopee_payout_vnd"])
        rows = [
            ("HH chờ xác minh (bot)", f"{format_vnd(int(pending[0]))} · {pending[1]} đơn"),
            ("Shopee báo đã duyệt", _money(approved) + (" (chưa đối chiếu)" if approved is not None else "")),
            ("Shopee báo thanh toán", _money(None if latest is None else latest["shopee_payout_vnd"])),
            ("Tiền thực nhận", _money(None if latest is None else latest["bank_received_vnd"])),
            ("Thuộc đơn Cashback Bot", _money(None if result is None or result.status != MATCHED else result.bot_vnd)),
            ("Chênh lệch nhận/Shopee", "—" if gap is None else format_vnd(gap)),
            ("Khoản cần kiểm tra", str(review)),
        ]
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán"), "", head, _table(rows), LOCK_NOTE]
        if latest is None:
            lines += ["", IMPORT_NOTE]
        keyboard = (
            (("📅 Kỳ thanh toán", "c:sm:bl"), ("📄 Chứng từ", "c:sm:ev")),
            (("🏦 Đối chiếu tiền nhận", "c:sm:bank"), ("🔍 Khoản chênh lệch", "c:sm:diff")),
            (("🕘 Lịch sử đối soát", "c:sm:h"),),
            BACK_SHOPEE,
        )
        return BotReply("\n".join(lines), inline_keyboard=keyboard)

    def batches(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute("SELECT * FROM settlement_batches ORDER BY period DESC, id DESC LIMIT 10").fetchall()
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Kỳ thanh toán"), ""]
        if not rows:
            lines += ["Chưa có kỳ nào.", "", IMPORT_NOTE]
        buttons = tuple(
            ((f"{STATUS_LABELS.get(r['status'], r['status']).split(' ', 1)[0]} {r['period']} · {_money(r['shopee_payout_vnd'])}",
              f"c:sm:b:{r['id']}"),)
            for r in rows
        )
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, BACK_HOME))

    def batch_detail(self, batch_id: int, notice: str = "") -> BotReply:
        batch = self.engine.batch(batch_id)
        result = self.engine.evaluate(batch_id)
        includes = {None: "chưa rõ", 1: "đã gồm VAT", 0: "chưa gồm VAT"}.get(batch["fee_includes_vat"], "chưa rõ")
        rows = [
            ("Hoa hồng Shopee báo", _money(batch["reported_commission_vnd"])),
            ("Điều chỉnh", _money(batch["adjustments_vnd"])),
            ("Phí dịch vụ", _money(batch["fee_vnd"])),
            ("VAT trên phí", _money(batch["fee_vat_vnd"])),
            ("Thuế khấu trừ", _money(batch["tax_withheld_vnd"])),
            ("Shopee báo chuyển", _money(batch["shopee_payout_vnd"])),
            ("Số học kỳ phải là", _money(result.expected_payout_vnd)),
            ("Ngân hàng nhận", _money(batch["bank_received_vnd"])),
        ]
        split = [
            ("Đơn qua bot (khớp)", format_vnd(result.bot_vnd)),
            ("Đơn ngoài bot", format_vnd(result.non_bot_vnd)),
            ("Không rõ đơn", format_vnd(result.unknown_vnd)),
            ("Cần kiểm tra", format_vnd(result.review_vnd)),
            ("Chưa phân bổ", _money(result.unallocated_vnd)),
        ]
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", f"Kỳ {batch['period']}"), ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Trạng thái: <b>{STATUS_LABELS.get(batch['status'], batch['status'])}</b>"
            + (f" · mã thanh toán <code>{html.escape(batch['shopee_payment_ref'])}</code>" if batch["shopee_payment_ref"] else ""),
            _table(rows),
            f"ⓘ Phí {includes}. Phí và thuế chưa phân bổ theo từng đơn.",
            "",
            "💼 <b>Phân bổ</b>",
            _table(split),
        ]
        if result.eligible_fund_vnd is not None:
            lines.append(f"Quỹ có chứng từ của đơn bot: <b>{format_vnd(result.eligible_fund_vnd)}</b> (chưa phải tiền khách được rút)")
        if result.discrepancies:
            lines += ["", "🔍 <b>Chênh lệch</b>"]
            for item in result.discrepancies[:12]:
                amount = "" if item.amount_vnd is None else f" · {format_vnd(item.amount_vnd)}"
                ref = f" · <code>{html.escape(short_order(item.detail))}</code>" if item.detail else ""
                lines.append(f"• {DISCREPANCY_LABELS.get(item.code, item.code)}{amount}{ref}")
        lines += ["", LOCK_NOTE]
        keyboard = (
            (("📦 Đơn thuộc kỳ", f"c:sm:items:{batch_id}"), ("📄 Chứng từ kỳ", f"c:sm:ev:{batch_id}")),
            ((("🔄 Đối soát lại", f"c:sm:rc:{batch_id}"),) if batch["status"] != REVERSED else ()),
            (("◀️ Kỳ thanh toán", "c:sm:bl"),),
        )
        return BotReply("\n".join(lines), inline_keyboard=tuple(row for row in keyboard if row))

    def items(self, batch_id: int) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute(
                "SELECT i.*, e.kind FROM settlement_items i JOIN settlement_evidence e ON e.id = i.evidence_id "
                "WHERE i.batch_id = ? AND e.verification != 'SUPERSEDED' ORDER BY i.is_bot DESC, i.id LIMIT 20",
                (batch_id,),
            ).fetchall()
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Đơn thuộc kỳ"), ""]
        if not rows:
            lines.append("Kỳ này chưa có khoản theo đơn.")
        for row in rows:
            source = "duyệt" if row["kind"] == "shopee_validation_report" else "trả"
            amount = row["approved_vnd"] if row["kind"] == "shopee_validation_report" else row["settled_vnd"]
            adjust = "" if row["adjustment_vnd"] is None else f" · điều chỉnh {format_vnd(int(row['adjustment_vnd']))}"
            who = "bot" if row["is_bot"] else "—"
            lines.append(
                f"• <code>{html.escape(short_order(row['order_ref']))}</code> · {who} · {source} {_money(amount)}{adjust} · "
                f"{ITEM_LABELS.get(row['match_status'], row['match_status'])}"
            )
        return BotReply("\n".join(lines), inline_keyboard=((("◀️ Kỳ", f"c:sm:b:{batch_id}"),),))

    # --- Chứng từ --------------------------------------------------------------------------------

    def evidence_list(self, batch_id: int | None) -> BotReply:
        where, args = ("WHERE batch_id = ?", (batch_id,)) if batch_id else ("", ())
        with self.repo.connect() as conn:
            rows = conn.execute(f"SELECT * FROM settlement_evidence {where} ORDER BY id DESC LIMIT 10", args).fetchall()
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Chứng từ"), ""]
        if not rows:
            lines += ["Chưa có chứng từ nào.", "", IMPORT_NOTE]
        buttons = tuple(
            ((f"{KIND_LABELS.get(r['kind'], r['kind'])} · {r['document_ref'][:20]}", f"c:sm:e:{r['id']}"),) for r in rows
        )
        back = (("◀️ Kỳ", f"c:sm:b:{batch_id}"),) if batch_id else BACK_HOME
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, back))

    def evidence_detail(self, evidence_id: int, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT e.*, b.period FROM settlement_evidence e JOIN settlement_batches b ON b.id = e.batch_id WHERE e.id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            return BotReply("Không tìm thấy chứng từ này.", inline_keyboard=(BACK_HOME,))
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Chứng từ"), ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"• Loại: <b>{KIND_LABELS.get(row['kind'], row['kind'])}</b> · kỳ {row['period']}",
            f"• Mã chứng từ: <code>{html.escape(row['document_ref'])}</code>",
            f"• Dấu vân tay: <code>{row['content_sha256'][:12]}…</code> · {row['size_bytes']} byte · {html.escape(row['parser'])}",
            f"• Xác minh: <b>{VERIFY_LABELS.get(row['verification'], row['verification'])}</b>",
            f"• Nhập bởi {html.escape(row['recorded_by'])} lúc {_vn(row['recorded_at'])}",
            "• Admin đã xem: " + ("chưa" if row["viewed_by"] is None else f"<code>{row['viewed_by']}</code> lúc {_vn(row['viewed_at'])}"),
            "",
            "ⓘ «Đã xem» chỉ ghi nhận bạn đã đọc chứng từ, không xác nhận Shopee đã duyệt hay đã trả.",
        ]
        keyboard = []
        if row["viewed_by"] is None:
            keyboard.append((("👁 Đã xem chứng từ", f"c:sm:seen:{evidence_id}"),))
        keyboard.append((("◀️ Chứng từ kỳ", f"c:sm:ev:{row['batch_id']}"),))
        return BotReply("\n".join(lines), inline_keyboard=tuple(keyboard))

    # --- Đối chiếu, chênh lệch, lịch sử -------------------------------------------------------------

    def bank(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM settlement_batches WHERE status != 'REVERSED' ORDER BY period DESC, id DESC LIMIT 10"
            ).fetchall()
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Đối chiếu tiền nhận"), ""]
        if not rows:
            lines += ["Chưa có kỳ nào để đối chiếu.", "", IMPORT_NOTE]
        for row in rows:
            gap = "—"
            if row["shopee_payout_vnd"] is not None and row["bank_received_vnd"] is not None:
                gap = format_vnd(int(row["bank_received_vnd"]) - int(row["shopee_payout_vnd"]))
            lines.append(
                f"• {row['period']}: Shopee báo {_money(row['shopee_payout_vnd'])} · nhận {_money(row['bank_received_vnd'])} · lệch {gap}"
            )
        return BotReply("\n".join(lines), inline_keyboard=(BACK_HOME,))

    def differences(self) -> BotReply:
        with self.repo.connect() as conn:
            batches = conn.execute(
                "SELECT id, period, status FROM settlement_batches WHERE status IN ('DISPUTED', 'PARTIALLY_MATCHED', 'EVIDENCE_PENDING') "
                "ORDER BY period DESC LIMIT 10"
            ).fetchall()
            adjustments = conn.execute(
                "SELECT a.*, c.order_sn FROM settlement_adjustments a LEFT JOIN shopee_conversions c ON c.conversion_id = a.conversion_id "
                "WHERE a.status = 'OPEN' ORDER BY a.id DESC LIMIT 10"
            ).fetchall()
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Khoản chênh lệch"), ""]
        if not batches and not adjustments:
            lines.append("Không có khoản nào cần kiểm tra.")
        if batches:
            lines.append("📅 <b>Kỳ chưa khớp</b>")
            lines += [f"• Kỳ {r['period']}: {STATUS_LABELS.get(r['status'], r['status'])}" for r in batches]
            lines.append("")
        if adjustments:
            lines.append("🔁 <b>Điều chỉnh sau khi đã vào kỳ</b> (chưa xử lý)")
            for row in adjustments:
                lines.append(
                    f"• <code>{html.escape(short_order(row['order_sn'] or row['conversion_id']))}</code> "
                    f"{format_vnd(int(row['old_vnd']))} → <b>{format_vnd(int(row['new_vnd']))}</b> ({format_vnd(int(row['delta_vnd']))})"
                )
        buttons = tuple(
            ((f"{STATUS_LABELS.get(r['status'], r['status'])} · kỳ {r['period']}", f"c:sm:b:{r['id']}"),) for r in batches
        )
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, BACK_HOME))

    def history(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute("SELECT * FROM settlement_audit ORDER BY id DESC LIMIT 15").fetchall()
        labels = {
            "batch_create": "tạo kỳ", "evidence_import": "nhập chứng từ", "evidence_viewed": "admin đã xem chứng từ",
            "reconcile": "đối soát", "batch_reverse": "đảo kỳ", "adjustment_open": "ghi điều chỉnh",
        }
        lines = [_title("Shopee Affiliate", "Đối soát thanh toán", "Lịch sử"), ""]
        if not rows:
            lines.append("Chưa có thao tác đối soát nào.")
        for row in rows:
            detail = json.loads(row["detail_json"] or "{}")
            extra = f" → {STATUS_LABELS.get(detail['status'], detail['status'])}" if row["action"] == "reconcile" else ""
            batch = f" · kỳ #{row['batch_id']}" if row["batch_id"] else ""
            lines.append(f"• {_vn(row['created_at'])} · {labels.get(row['action'], row['action'])}{extra}{batch} · {html.escape(row['actor'])}")
        return BotReply("\n".join(lines), inline_keyboard=(BACK_HOME,))

