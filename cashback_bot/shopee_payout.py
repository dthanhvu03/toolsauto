"""Kỳ thanh toán Shopee tự động (PLAN-101).

Cuối mỗi lượt đồng bộ Shopee: đọc hoá đơn đối soát theo ngày (`billing_list`), gom theo mã thanh toán (`payout_id`).
Kỳ chưa có thì đọc đơn của từng hoá đơn, lập kỳ và nhập báo cáo Shopee định dạng chuẩn (settlement.py). Shopee chặn
chỗ đọc thuế và số sau thuế (GraphQL trả 403), nên báo cáo để trống hai số đó tới khi chủ bot bấm «✅ Đã nhận đúng …»
(confirm_bank): lúc đó bot nhập chứng từ ngân hàng và thay báo cáo bằng bản có thuế = sau phí − số nhận.

Không mở ví, không tạo payout, không đổi validation_status hay sổ cashback (như settlement.py).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.money import format_vnd
from cashback_bot.settlement import FORMAT, REVERSED, EvidenceError, Reconciliation, SettlementEngine

logger = logging.getLogger(__name__)

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
# Một kỳ gom cả hoá đơn ngày đã lâu (kỳ 29/10/2026 có hoá đơn ngày 27/08), nên đọc 120 ngày hoàn thành. Chỉ lập kỳ
# Shopee khởi tạo trong 14 ngày qua: kỳ cũ đã nhận tiền từ trước không báo lại.
WINDOW = timedelta(days=120)
RECENT = timedelta(days=14)
MONEY_SCALE = 100_000  # như shopee_sync: API web Shopee nhân số tiền lên 100.000 lần
PAGE_SIZE = 100
MAX_PAGES = 10
PAUSE_SECONDS = 1.5
ACTOR = "shopee_sync"
# Thuế Shopee giữ: TNCN 5% + VAT 5% trên hoa hồng trước phí, mỗi khoản làm tròn (đối chiếu kỳ 29/10/2026).
TAX_PERCENT = 5
# payout_status trên hoá đơn: kỳ 29/10/2026 trang web ghi «Đang xử lý» thì API trả 2. Mã khác chưa gặp nên hiện số.
# Đã chuyển hay chưa thì xem payment_completed_time.
SHOPEE_STATUS = {2: "Đang xử lý"}
CONFIRM = "c:sm:bok"
OTHER = "c:sm:box"


@dataclass(frozen=True)
class Payout:
    payout_id: str
    created: int
    bills: tuple[dict, ...]
    gross_vnd: int  # Σ hoa hồng trước phí
    net_vnd: int  # Σ sau phí
    status: int  # payout_status của Shopee
    paid_at: int  # giờ Shopee ghi đã chuyển tiền, 0 = chưa

    @property
    def paid(self) -> bool:
        return self.paid_at > 0

    def status_text(self) -> str:
        if self.paid:
            return f"Đã chuyển tiền {datetime.fromtimestamp(self.paid_at, ICT).strftime('%H:%M %d/%m')}"
        return SHOPEE_STATUS.get(self.status, f"mã {self.status} (bot chưa biết nghĩa)")


def _vnd(value) -> int:
    try:
        return int(round(float(value or 0) / MONEY_SCALE))
    except (TypeError, ValueError):
        return 0


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def expected_tax(gross_vnd: int) -> int:
    return 2 * ((gross_vnd * TAX_PERCENT + 50) // 100)


def payouts(payload) -> list[Payout]:
    """Gom hoá đơn ngày theo mã thanh toán. Hoá đơn chưa vào kỳ nào (chưa có payout_id) thì bỏ qua."""
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("billing_list_shape")
    groups: dict[str, list[dict]] = {}
    for bill in rows:
        if not isinstance(bill, dict):
            continue
        payout_id = str(bill.get("payout_id") or "").strip()
        if payout_id.isdigit() and _int(bill.get("payout_created_time")):
            groups.setdefault(payout_id, []).append(bill)
    found = [
        Payout(
            payout_id=payout_id,
            created=max(_int(b.get("payout_created_time")) for b in bills),
            bills=tuple(bills),
            gross_vnd=sum(_vnd(b.get("eligible_total_amount")) for b in bills),
            net_vnd=sum(_vnd(b.get("bill_total_amount")) for b in bills),
            status=max(_int(b.get("payout_status")) for b in bills),
            paid_at=max(_int(b.get("payment_completed_time")) for b in bills),
        )
        for payout_id, bills in groups.items()
    ]
    return sorted(found, key=lambda p: p.created)


def order_amounts(rows: list[dict]) -> dict[str, int]:
    """Hoa hồng từng đơn, cùng cách shopee_sync tính: checkout một đơn lấy affiliate_net_commission, nhiều đơn thì cộng
    item_commission + capped_brand_commission của từng món."""
    amounts: dict[str, int] = {}
    for row in rows:
        orders = [o for o in row.get("orders") or [] if isinstance(o, dict)]
        for order in orders:
            order_sn = str(order.get("order_sn") or "").strip()
            if not order_sn:
                continue
            if len(orders) == 1:
                raw = row.get("affiliate_net_commission")
                if raw in (None, ""):
                    raw = row.get("estimated_total_commission")
                amount = _vnd(raw)
            else:
                items = [i for i in order.get("items") or [] if isinstance(i, dict)]
                amount = _vnd(sum(_int(i.get("item_commission")) + _int(i.get("capped_brand_commission")) for i in items))
            amounts[order_sn] = amounts.get(order_sn, 0) + amount
    return amounts


def _bill_rows(client, bill: dict, sleep: Callable[[float], None]) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        sleep(PAUSE_SECONDS)
        payload = client.fetch_bill_orders(bill, page_no=page, page_size=PAGE_SIZE)
        data = payload.get("data") if isinstance(payload, dict) else None
        chunk = data.get("list") if isinstance(data, dict) else None
        if not isinstance(chunk, list):
            raise ValueError("bill_orders_shape")
        rows += [row for row in chunk if isinstance(row, dict)]
        if len(chunk) < PAGE_SIZE:
            return rows
    raise ValueError("bill_orders_truncated")


def _statement(payout: Payout, amounts: dict[str, int], days: list[str]) -> dict:
    return {
        "format": FORMAT,
        "kind": "shopee_payment_report",
        "period": datetime.fromtimestamp(payout.created, ICT).strftime("%Y-%m"),
        "document_ref": payout.payout_id,
        "shopee_payment_ref": payout.payout_id,
        "source_note": "Bot đọc /api/v3/payment/billing_list và report/validation_detail/v2 (PLAN-101). Hoá đơn ngày: "
                       + ", ".join(days) + ". Thuế và số sau thuế chưa có: chờ chủ bot xác nhận tiền về.",
        "totals": {
            "reported_commission_vnd": payout.gross_vnd,
            "adjustments_vnd": 0,
            "fee_vnd": payout.gross_vnd - payout.net_vnd,
            "fee_vat_vnd": 0,
            "fee_includes_vat": True,
            "tax_withheld_vnd": None,
            "payout_vnd": None,
        },
        "items": [{"order_ref": sn, "approved_vnd": vnd, "settled_vnd": vnd} for sn, vnd in sorted(amounts.items())],
    }


def _batch_for(repo: TrackingRepository, payout_id: str):
    with repo.connect() as conn:
        return conn.execute(
            "SELECT * FROM settlement_batches WHERE shopee_payment_ref = ? AND status != ? ORDER BY id DESC LIMIT 1",
            (payout_id, REVERSED),
        ).fetchone()


def expected_payout(batch) -> int | None:
    """Số dự kiến về tài khoản: số Shopee báo chuyển nếu đã có, không thì sau phí − thuế tạm tính."""
    if batch["shopee_payout_vnd"] is not None:
        return int(batch["shopee_payout_vnd"])
    if batch["reported_commission_vnd"] is None or batch["fee_vnd"] is None:
        return None
    gross = int(batch["reported_commission_vnd"]) + int(batch["adjustments_vnd"] or 0)
    return gross - int(batch["fee_vnd"]) - expected_tax(gross)


def confirm_buttons(batch) -> tuple:
    amount = expected_payout(batch)
    if amount is None or amount <= 0 or batch["bank_evidence_id"] is not None or batch["status"] == REVERSED:
        return ()
    return ((f"✅ Đã nhận đúng {format_vnd(amount)}", f"{CONFIRM}:{batch['id']}:{amount}"),
            ("⚠️ Số khác", f"{OTHER}:{batch['id']}"))


def _notice(batch, payout: Payout, paid: bool) -> str:
    amount = expected_payout(batch)
    gross = int(batch["reported_commission_vnd"] or 0)
    net = gross - int(batch["fee_vnd"] or 0)
    created = datetime.fromtimestamp(payout.created, ICT).strftime("%d/%m")
    head = ("💸 <b>Shopee đã chuyển tiền kỳ thanh toán</b>" if paid
            else "💳 <b>Shopee khởi tạo kỳ thanh toán mới</b>")
    step = ("Anh xem sao kê tài khoản, đúng số thì bấm nút dưới." if paid
            else "Shopee chưa chuyển tiền. Khi Shopee ghi đã chuyển, bot báo lại kèm nút xác nhận.")
    tax = (f"Thuế Shopee giữ: {format_vnd(int(batch['tax_withheld_vnd']))}" if batch["tax_withheld_vnd"] is not None
           else f"Thuế tạm tính (TNCN 5% + VAT 5%): {format_vnd(expected_tax(gross))}")
    return "\n".join([
        head, "",
        f"Mã thanh toán <code>{payout.payout_id}</code> · khởi tạo {created} · {len(payout.bills)} ngày hoàn thành",
        f"Trạng thái Shopee: <b>{payout.status_text()}</b>",
        f"Hoa hồng sau phí: {format_vnd(net)}",
        tax,
        f"Dự kiến về tài khoản: <b>{format_vnd(amount)}</b>" if amount is not None else "Chưa tính được số dự kiến.",
        "",
        f"Bot đã nhập báo cáo Shopee vào 🧾 Đối soát thanh toán (kỳ #{batch['id']}).",
        f"{step} Ví khách vẫn khoá.",
    ])


def _notify(repo: TrackingRepository, chat_id: int | None, batch, payout: Payout, paid: bool) -> None:
    if chat_id is None or batch["bank_evidence_id"] is not None:
        return
    buttons = confirm_buttons(batch) if paid else ()
    keyboard = [[{"text": text, "callback_data": data} for text, data in buttons]] if buttons else []
    keyboard.append([{"text": "🧾 Xem kỳ", "callback_data": f"c:sm:b:{batch['id']}"}])
    with repo.connect() as conn:
        enqueue_event(
            conn, event_key=f"payout_{'paid' if paid else 'new'}:{payout.payout_id}", event_type="SHOPEE_PAYOUT",
            chat_id=int(chat_id), message_html=_notice(batch, payout, paid),
            reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False),
            source_ref=f"settlement_batch:{batch['id']}",
        )


def poll(repo: TrackingRepository, client, chat_id: int | None, now: datetime | None = None,
         sleep: Callable[[float], None] = time.sleep, heartbeat: Callable[[], bool] | None = None) -> dict:
    """Một lượt: lập kỳ mới, báo admin (một lần lúc thấy kỳ, thêm một lần khi Shopee ghi đã chuyển). Trả số liệu cho
    log."""
    moment = now or datetime.now(timezone.utc)
    payload = client.fetch_billing_list(int((moment - WINDOW).timestamp()), int(moment.timestamp()))
    engine = SettlementEngine(repo)
    created = 0
    found = payouts(payload)
    for payout in found:
        if payout.created < (moment - RECENT).timestamp():
            continue
        batch = _batch_for(repo, payout.payout_id)
        if batch is None:
            if heartbeat is not None and not heartbeat():
                break
            rows: list[dict] = []
            for bill in payout.bills:
                rows += _bill_rows(client, bill, sleep)
            days = [datetime.fromtimestamp(_int(b.get("order_completed_period_start_time")), ICT).strftime("%d/%m")
                    for b in sorted(payout.bills, key=lambda b: _int(b.get("order_completed_period_start_time")))]
            raw = json.dumps(_statement(payout, order_amounts(rows), days), ensure_ascii=False).encode()
            period = datetime.fromtimestamp(payout.created, ICT).strftime("%Y-%m")
            batch_id = engine.create_batch(period, ACTOR, payout.payout_id)
            engine.import_document(batch_id, raw, ACTOR)
            batch = engine.batch(batch_id)
            created += 1
        _notify(repo, chat_id, batch, payout, paid=payout.paid)
    return {"payouts": len(found), "created": created}


def confirm_bank(repo: TrackingRepository, batch_id: int, amount: int, admin_id: int) -> Reconciliation:
    """Chủ bot xác nhận tài khoản nhận đúng `amount`: nhập chứng từ ngân hàng; báo cáo Shopee chưa có thuế thì thay
    bằng bản có thuế = sau phí − amount. Số trên nút phải bằng số bot tính lại lúc này."""
    engine = SettlementEngine(repo)
    batch = engine.batch(batch_id)
    if batch is None or batch["status"] == REVERSED:
        raise EvidenceError("no_batch")
    if batch["bank_evidence_id"] is not None:
        raise EvidenceError("bank_already_confirmed")
    if expected_payout(batch) != amount or amount <= 0:
        raise EvidenceError("amount_changed")
    actor = f"admin:{admin_id}"
    ref = batch["shopee_payment_ref"] or str(batch_id)
    if batch["shopee_payout_vnd"] is None:
        with repo.connect() as conn:
            row = conn.execute("SELECT stored_name FROM settlement_evidence WHERE id = ?",
                               (batch["statement_evidence_id"],)).fetchone()
        statement = json.loads((engine.evidence_dir / row["stored_name"]).read_text(encoding="utf-8"))
        totals = statement["totals"]
        gross = int(totals["reported_commission_vnd"]) + int(totals["adjustments_vnd"] or 0)
        totals["tax_withheld_vnd"] = gross - int(totals["fee_vnd"]) - amount
        totals["payout_vnd"] = amount
        statement["document_ref"] = f"{ref}-tax"
        statement["source_note"] = (statement.get("source_note", "") + f" Thuế và số sau thuế theo chủ bot xác nhận "
                                    f"tài khoản nhận {amount} ({actor}).")
        engine.import_document(batch_id, json.dumps(statement, ensure_ascii=False).encode(), actor,
                               replaces=int(batch["statement_evidence_id"]))
    bank = {"format": FORMAT, "kind": "bank_statement", "period": batch["period"], "document_ref": f"bank-{ref}",
            "shopee_payment_ref": batch["shopee_payment_ref"], "bank": {"received_vnd": amount},
            "source_note": f"Chủ bot xác nhận trong bot: tài khoản nhận đúng {amount} ({actor})."}
    engine.import_document(batch_id, json.dumps(bank, ensure_ascii=False).encode(), actor)
    return engine.evaluate(batch_id)
