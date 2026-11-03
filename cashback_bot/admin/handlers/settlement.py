"""Màn /admin → 💰 Tiền & ví → 💳 Kỳ thanh toán Shopee (PLAN-075; số tiền đọc từ money_flow).

Xem kỳ thanh toán, chứng từ, đối chiếu tiền nhận, chênh lệch, đơn thuộc kỳ, lịch sử. Thao tác ghi:
"👁 Đã xem chứng từ" (không phải xác minh), "🔄 Đối soát lại" (tính lại từ chứng từ đã có) và, từ PLAN-101 (chủ bot
duyệt 29/10/2026), "✅ Đã nhận đúng …": xác nhận tài khoản nhận đúng số bot tính (shopee_payout.confirm_bank). Không có
nút gõ số tiền, gán duyệt, gán đã trả hay mở ví. Thiếu chứng từ thì hiện "Chưa xác minh", không hiện 0đ.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot import money_flow, shopee_payout
from cashback_bot.admin.notify.admin_notify import short_order
from cashback_bot.admin.ui.glossary import MONEY_HOME
from cashback_bot.admin.ui.views import money_todo
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd
from cashback_bot.settlement import REVERSED, EvidenceError, SettlementEngine

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:sm:home"
MONEY = html.escape(MONEY_HOME)
SECTION = "Kỳ thanh toán Shopee"
BACK_MONEY = (("◀️ Tiền & ví", "c:menu:money"),)
BACK_HOME = ((f"◀️ {SECTION}", HOME),)
NOT_VERIFIED = "Chưa xác minh"
MATCH_NOTE = (
    "ⓘ «Khớp» = báo cáo Shopee, phép tính và tiền về tài khoản khớp nhau. Chỉ kỳ khớp mới tính vào "
    "💼 Thực nhận và Quỹ chi trả; đơn trong kỳ khớp mới vào ví khách."
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
    "MATCHED": "✅ Khớp",
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
_CONFIRM = re.compile(r"^c:sm:bok:(\d{1,9}):(\d{1,12})$")
_OTHER = re.compile(r"^c:sm:box:(\d{1,9})$")
_ADJUST = re.compile(r"^c:sm:adj:(\d{1,9})(:ok)?$")
OTHER_NOTE = (
    "⚠️ Bot chưa ghi gì. Anh gửi em ảnh trang «Đối soát vào ngày …» trên Shopee (Thanh toán → Lịch sử thanh toán → "
    "Xem chi tiết) và số tiền tài khoản thực nhận, em nhập tay."
)


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


def _period_line(p: money_flow.Period) -> str:
    label = STATUS_LABELS.get(p.status, p.status)
    if p.received_vnd is not None:
        money = f"Shopee báo {_money(p.payout_vnd)} · về tài khoản {format_vnd(p.received_vnd)}"
    else:
        money = f"Shopee báo {_money(p.payout_vnd)} · chưa về"
    return f"• Kỳ <b>{html.escape(p.period)}</b> {label} · {money}"


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
        confirm = _CONFIRM.fullmatch(data)
        if confirm:
            batch_id, amount = int(confirm.group(1)), int(confirm.group(2))
            try:
                result = shopee_payout.confirm_bank(self.repo, batch_id, amount, admin_id)
            except EvidenceError as exc:
                text = {
                    "bank_already_confirmed": "Kỳ này đã xác nhận tiền về rồi.",
                    "amount_changed": "Số dự kiến đã đổi. Xem lại kỳ rồi bấm nút mới.",
                }.get(exc.code, "Không tìm thấy kỳ thanh toán này.")
                if self.engine.batch(batch_id) is None:
                    return BotReply(text, inline_keyboard=(BACK_HOME,))
                return self.batch_detail(batch_id, f"⚠️ {text}")
            label = STATUS_LABELS.get(result.status, result.status)
            return self.batch_detail(batch_id, f"✅ Đã ghi tài khoản nhận {format_vnd(amount)}. Kỳ: {label}.")
        adjust = _ADJUST.fullmatch(data)
        if adjust:
            return self._adjustment(admin_id, int(adjust.group(1)), bool(adjust.group(2)))
        other = _OTHER.fullmatch(data)
        if other:
            return BotReply(OTHER_NOTE, inline_keyboard=((("🧾 Xem kỳ", f"c:sm:b:{int(other.group(1))}"),), BACK_HOME))
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
            snap = money_flow.snapshot(conn)
        lines = [_title(MONEY, SECTION), ""]
        if not snap.periods:
            lines += ["Chưa có kỳ thanh toán nào.", "", IMPORT_NOTE]
        lines += [_period_line(p) for p in reversed(snap.periods)]
        todo = [t for t in money_todo(snap) if "Kỳ" in t or "điều chỉnh" in t]
        if todo:
            lines += ["", "📌 <b>Cần làm</b>", *(f"• {t}" for t in todo)]
        lines += ["", MATCH_NOTE]
        buttons = tuple(
            ((f"{STATUS_LABELS.get(p.status, p.status).split(' ', 1)[0]} Kỳ {p.period} · {_money(p.amount_vnd)}",
              f"c:sm:b:{p.batch_id}"),)
            for p in reversed(snap.periods)
        )
        diff = f"🔍 Khoản chênh lệch ({snap.open_adjustments})" if snap.open_adjustments else "🔍 Khoản chênh lệch"
        keyboard = (
            *buttons,
            ((diff, "c:sm:diff"), ("📄 Chứng từ", "c:sm:ev")),
            (("🕘 Lịch sử", "c:sm:h"),),
            BACK_MONEY,
        )
        return BotReply("\n".join(lines), inline_keyboard=keyboard)

    def batches(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute("SELECT * FROM settlement_batches ORDER BY period DESC, id DESC LIMIT 10").fetchall()
        lines = [_title(MONEY, SECTION, "Kỳ thanh toán"), ""]
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
            ("Thuế Shopee giữ", _money(batch["tax_withheld_vnd"])),
            ("Shopee báo chuyển", _money(batch["shopee_payout_vnd"])),
            ("Tính lại HH−phí−thuế", _money(result.expected_payout_vnd)),
            ("Về tài khoản", _money(batch["bank_received_vnd"])),
        ]
        split = [
            ("Đơn qua bot (khớp)", format_vnd(result.bot_vnd)),
            ("Đơn ngoài bot", format_vnd(result.non_bot_vnd)),
            ("Không rõ đơn", format_vnd(result.unknown_vnd)),
            ("Cần kiểm tra", format_vnd(result.review_vnd)),
            ("Chưa phân bổ", _money(result.unallocated_vnd)),
        ]
        lines = [_title(MONEY, SECTION, f"Kỳ {batch['period']}"), ""]
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
        with self.repo.connect() as conn:
            period = next((p for p in money_flow.snapshot(conn).periods if p.batch_id == batch_id), None)
            approved = conn.execute(
                "SELECT SUM(approved_vnd), COUNT(approved_vnd) FROM settlement_items i "
                "JOIN settlement_evidence e ON e.id = i.evidence_id "
                "WHERE i.batch_id = ? AND e.kind = 'shopee_validation_report' AND e.verification != 'SUPERSEDED'",
                (batch_id,),
            ).fetchone()
        if approved[1]:
            lines.append(f"Shopee báo đã duyệt (báo cáo xác thực): {format_vnd(int(approved[0]))} (chưa đối chiếu)")
        if period is not None and period.owner_vnd is not None:
            lines.append(
                f"Tiền hoàn khách của kỳ: <b>{format_vnd(period.customer_vnd)}</b> · phần anh"
                + ("" if period.matched else " (dự kiến)") + f": <b>{format_vnd(period.owner_vnd)}</b>"
            )
        if result.discrepancies:
            lines += ["", "🔍 <b>Chênh lệch</b>"]
            for item in result.discrepancies[:12]:
                amount = "" if item.amount_vnd is None else f" · {format_vnd(item.amount_vnd)}"
                ref = f" · <code>{html.escape(short_order(item.detail))}</code>" if item.detail else ""
                lines.append(f"• {DISCREPANCY_LABELS.get(item.code, item.code)}{amount}{ref}")
        lines += ["", MATCH_NOTE]
        keyboard = (
            shopee_payout.confirm_buttons(batch),
            (("📦 Đơn thuộc kỳ", f"c:sm:items:{batch_id}"), ("📄 Chứng từ kỳ", f"c:sm:ev:{batch_id}")),
            ((("🔄 Đối soát lại", f"c:sm:rc:{batch_id}"),) if batch["status"] != REVERSED else ()),
            BACK_HOME,
        )
        return BotReply("\n".join(lines), inline_keyboard=tuple(row for row in keyboard if row))

    def items(self, batch_id: int) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute(
                "SELECT i.*, e.kind FROM settlement_items i JOIN settlement_evidence e ON e.id = i.evidence_id "
                "WHERE i.batch_id = ? AND e.verification != 'SUPERSEDED' ORDER BY i.is_bot DESC, i.id LIMIT 20",
                (batch_id,),
            ).fetchall()
        lines = [_title(MONEY, SECTION, "Đơn thuộc kỳ"), ""]
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
        lines = [_title(MONEY, SECTION, "Chứng từ"), ""]
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
        lines = [_title(MONEY, SECTION, "Chứng từ"), ""]
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
        lines = [_title(MONEY, SECTION, "Đối chiếu tiền nhận"), ""]
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

    def _adjustment(self, admin_id: int, adjustment_id: int, confirmed: bool) -> BotReply:
        if confirmed:
            done = self.engine.resolve_adjustment(adjustment_id, f"admin:{admin_id}")
            return self.differences("✅ Đã đóng điều chỉnh. Đơn vào ví lại ở lần cập nhật ví kế tiếp." if done
                                    else "Điều chỉnh này đã được xử lý trước đó.")
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT a.*, c.order_sn FROM settlement_adjustments a LEFT JOIN shopee_conversions c "
                "ON c.conversion_id = a.conversion_id WHERE a.id = ? AND a.status = 'OPEN'", (adjustment_id,)
            ).fetchone()
        if row is None:
            return self.differences("Điều chỉnh này đã được xử lý trước đó.")
        order = html.escape(short_order(row["order_sn"] or row["conversion_id"]))
        text = (
            f"{_title(MONEY, SECTION, 'Đóng điều chỉnh')}"
            f"Đơn <code>{order}</code>: {format_vnd(int(row['old_vnd']))} → <b>{format_vnd(int(row['new_vnd']))}</b> "
            f"({format_vnd(int(row['delta_vnd']))})\n\n"
            "Đóng nghĩa là anh đã xem và chấp nhận số mới. Bot không đổi tiền khách ở bước này: Shopee giảm hoa hồng "
            "thì ví khách đã tự trừ lại. Sau khi đóng, đơn không còn bị giữ vì điều chỉnh này."
        )
        return BotReply(text, inline_keyboard=(
            (("✅ Đóng điều chỉnh", f"c:sm:adj:{adjustment_id}:ok"),), (("◀️ Khoản chênh lệch", "c:sm:diff"),),
        ))

    def differences(self, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            batches = conn.execute(
                "SELECT id, period, status FROM settlement_batches WHERE status IN ('DISPUTED', 'PARTIALLY_MATCHED', 'EVIDENCE_PENDING') "
                "ORDER BY period DESC LIMIT 10"
            ).fetchall()
            adjustments = conn.execute(
                "SELECT a.*, c.order_sn FROM settlement_adjustments a LEFT JOIN shopee_conversions c ON c.conversion_id = a.conversion_id "
                "WHERE a.status = 'OPEN' ORDER BY a.id DESC LIMIT 10"
            ).fetchall()
        lines = [_title(MONEY, SECTION, "Khoản chênh lệch"), ""]
        if notice:
            lines += [notice, ""]
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
        buttons += tuple(
            ((f"✅ Đóng · {short_order(r['order_sn'] or r['conversion_id'])} ({format_vnd(int(r['delta_vnd']))})",
              f"c:sm:adj:{r['id']}"),) for r in adjustments
        )
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, BACK_HOME))

    def history(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute("SELECT * FROM settlement_audit ORDER BY id DESC LIMIT 15").fetchall()
        labels = {
            "batch_create": "tạo kỳ", "evidence_import": "nhập chứng từ", "evidence_viewed": "admin đã xem chứng từ",
            "reconcile": "đối soát", "batch_reverse": "đảo kỳ", "adjustment_open": "ghi điều chỉnh",
            "adjustment_resolve": "đóng điều chỉnh",
        }
        lines = [_title(MONEY, SECTION, "Lịch sử"), ""]
        if not rows:
            lines.append("Chưa có thao tác đối soát nào.")
        for row in rows:
            detail = json.loads(row["detail_json"] or "{}")
            extra = f" → {STATUS_LABELS.get(detail['status'], detail['status'])}" if row["action"] == "reconcile" else ""
            batch = f" · kỳ #{row['batch_id']}" if row["batch_id"] else ""
            lines.append(f"• {_vn(row['created_at'])} · {labels.get(row['action'], row['action'])}{extra}{batch} · {html.escape(row['actor'])}")
        return BotReply("\n".join(lines), inline_keyboard=(BACK_HOME,))

