"""PLAN-101: kỳ thanh toán Shopee tự động (lập kỳ từ hoá đơn đối soát, báo admin, nút xác nhận tiền về).

Payload theo cấu trúc response thật đọc thử 29/10/2026 (số tiền nhân 100.000). SQLite tạm, không gọi Shopee hay
Telegram.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cashback_bot import shopee_payout
from cashback_bot.settlement import EVIDENCE_PENDING, MATCHED, SettlementEngine
from cashback_bot.shopee_client import ShopeeApiError, ShopeeStatusResult
from cashback_bot.shopee_sync import ShopeeSyncEngine
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link, _order

PAYOUT = "17315920094261029"
CREATED = 1793214007  # 02:00 29/10/2026 giờ VN
NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
DAY_A, DAY_B = 1793034000, 1787763600  # hoàn thành 27/10 và 27/08
E = 100_000


def _bill(start: int, gross: int, net: int, payout: str = PAYOUT, created: int = CREATED, paid: int = 0) -> dict:
    return {
        "validation_id": f"v{start}", "payout_id": payout, "payout_created_time": created,
        "order_completed_period_start_time": start, "order_completed_period_end_time": start + 86_399,
        "validation_period_start_time": start + 86_400, "validation_period_end_time": start + 172_799,
        "eligible_total_amount": gross * E, "bill_total_amount": net * E, "payment_completed_time": paid,
        "payment_status": 8, "settlement_cycle": 4,
    }


def _bills(paid: int = 0) -> list[dict]:
    return [
        _bill(DAY_A, 18_000, 17_820, paid=paid),
        _bill(DAY_B, 2_000, 1_980, paid=paid),
        {**_bill(DAY_A + 86_400, 900, 891), "payout_id": "", "payout_created_time": 0},  # chưa vào kỳ nào
        _bill(1784000000, 5_000, 4_950, payout="17315920094260720", created=1784500000, paid=1784800000),  # kỳ tháng 7
    ]


ORDERS = {
    # Checkout một đơn: lấy affiliate_net_commission. Checkout hai đơn: cộng hoa hồng từng món (Shopee + shop).
    DAY_A: [
        {"affiliate_net_commission": str(10_000 * E), "orders": [{"order_sn": "SN-o1", "items": []}]},
        {"affiliate_net_commission": str(8_000 * E), "orders": [
            {"order_sn": "SN-nb", "items": [{"item_commission": 3_000 * E, "capped_brand_commission": 2_000 * E}]},
            {"order_sn": "SN-o3", "items": [{"item_commission": 3_000 * E, "capped_brand_commission": 0}]},
        ]},
    ],
    DAY_B: [{"affiliate_net_commission": str(2_000 * E), "orders": [{"order_sn": "SN-nb2", "items": []}]}],
}


class FakeShopee:
    def __init__(self, bills=None):
        self.bills = bills if bills is not None else _bills()
        self.order_calls = 0

    def fetch_billing_list(self, start_time: int, end_time: int) -> dict:
        self.window = (start_time, end_time)
        return {"code": 0, "data": {"list": self.bills}}

    def fetch_bill_orders(self, bill: dict, page_no: int = 1, page_size: int = 100) -> dict:
        self.order_calls += 1
        return {"code": 0, "data": {"list": ORDERS[bill["order_completed_period_start_time"]]}}


@pytest.fixture
def bot(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, cid="o1")
    _order(bot, sub, status="COMPLETED", commission=3_000, cid="o3")
    _order(bot, None, status="COMPLETED", commission=5_000, cid="nb")
    _order(bot, None, status="COMPLETED", commission=2_000, cid="nb2")
    return bot


def _poll(bot, client) -> dict:
    return shopee_payout.poll(bot.repo, client, ADMIN, now=NOW, sleep=lambda _s: None)


def _rows(bot, sql: str, *args):
    with bot.repo.connect() as conn:
        return conn.execute(sql, args).fetchall()


def _events(bot) -> list:
    return _rows(bot, "SELECT * FROM admin_notifications WHERE event_type = 'SHOPEE_PAYOUT' ORDER BY id")


def _buttons(event) -> list[str]:
    return [b["callback_data"] for row in json.loads(event["reply_markup_json"])["inline_keyboard"] for b in row]


def test_lap_ky_moi_tu_hoa_don_doi_soat_va_bao_admin_mot_lan(bot):
    client = FakeShopee()
    assert _poll(bot, client) == {"payouts": 2, "created": 1}
    assert client.window[1] - client.window[0] == 120 * 86_400
    batches = _rows(bot, "SELECT * FROM settlement_batches")
    assert len(batches) == 1, "kỳ tháng 7 đã nhận tiền từ lâu và hoá đơn chưa vào kỳ thì không lập"
    batch = batches[0]
    assert (batch["period"], batch["shopee_payment_ref"], batch["status"]) == ("2026-10", PAYOUT, EVIDENCE_PENDING)
    assert (batch["reported_commission_vnd"], batch["fee_vnd"], batch["tax_withheld_vnd"]) == (20_000, 200, None)
    items = {r["order_ref"]: (r["settled_vnd"], r["match_status"]) for r in _rows(bot, "SELECT * FROM settlement_items")}
    assert items == {"SN-o1": (10_000, "MATCHED"), "SN-o3": (3_000, "MATCHED"), "SN-nb": (5_000, "NOT_BOT"),
                     "SN-nb2": (2_000, "NOT_BOT")}
    result = SettlementEngine(bot.repo).evaluate(batch["id"])
    assert {d.code for d in result.discrepancies} == {"NO_BANK", "TOTALS_INCOMPLETE"}
    [event] = _events(bot)
    assert event["chat_id"] == ADMIN and event["audience"] == "admin"
    assert "Hoa hồng sau phí: 19.800đ" in event["message_html"] and "<b>17.800đ</b>" in event["message_html"]
    assert "Thuế tạm tính (TNCN 5% + VAT 5%): 2.000đ" in event["message_html"]
    assert _buttons(event) == [f"c:sm:bok:{batch['id']}:17800", f"c:sm:box:{batch['id']}", f"c:sm:b:{batch['id']}"]
    calls = client.order_calls
    assert _poll(bot, client)["created"] == 0
    assert client.order_calls == calls and len(_events(bot)) == 1, "lượt sau không đọc đơn lại, không báo lại"


def test_shopee_ghi_da_chuyen_thi_nhac_them_mot_lan(bot):
    _poll(bot, FakeShopee())
    paid = FakeShopee(_bills(paid=CREATED + 3_600))
    _poll(bot, paid)
    _poll(bot, paid)
    events = _events(bot)
    assert [e["event_key"] for e in events] == [f"payout_new:{PAYOUT}", f"payout_paid:{PAYOUT}"]
    assert "Shopee đã chuyển tiền" in events[1]["message_html"]


def test_ky_nhap_tay_cung_ma_khong_lap_lai_chi_bao_nut(bot):
    engine = SettlementEngine(bot.repo)
    batch = engine.create_batch("2026-10", "cli:test", PAYOUT)
    manual = {"format": "cashback_settlement_v1", "kind": "shopee_payment_report", "period": "2026-10",
              "document_ref": PAYOUT, "shopee_payment_ref": PAYOUT,
              "totals": {"reported_commission_vnd": 20_000, "adjustments_vnd": 0, "fee_vnd": 200, "fee_vat_vnd": 0,
                         "fee_includes_vat": True, "tax_withheld_vnd": 1_900, "payout_vnd": 17_900}, "items": []}
    engine.import_document(batch, json.dumps(manual).encode(), "cli:test")
    client = FakeShopee()
    assert _poll(bot, client)["created"] == 0 and client.order_calls == 0
    [event] = _events(bot)
    assert "Thuế Shopee giữ: 1.900đ" in event["message_html"] and f"c:sm:bok:{batch}:17900" in _buttons(event)


def test_bam_da_nhan_dung_thi_nhap_ngan_hang_va_thay_bao_cao(bot):
    _poll(bot, FakeShopee())
    batch = _rows(bot, "SELECT id FROM settlement_batches")[0]["id"]
    wallet = [tuple(r) for r in _rows(bot, "SELECT * FROM cashback_entries ORDER BY conversion_id")]
    detail = _callback(bot, ADMIN, f"c:sm:b:{batch}")
    assert f"c:sm:bok:{batch}:17800" in [d for row in detail.inline_keyboard for _l, d in row]
    assert "chỉ dành cho quản trị" in _callback(bot, USER, f"c:sm:bok:{batch}:17800").text
    other = _callback(bot, ADMIN, f"c:sm:box:{batch}")
    assert "Bot chưa ghi gì" in other.text
    assert len(_rows(bot, "SELECT * FROM settlement_evidence")) == 1
    assert "Số dự kiến đã đổi" in _callback(bot, ADMIN, f"c:sm:bok:{batch}:17000").text
    done = _callback(bot, ADMIN, f"c:sm:bok:{batch}:17800")
    assert "Đã ghi tài khoản nhận 17.800đ" in done.text and "Chứng từ khớp" in done.text
    assert not [d for row in done.inline_keyboard for _l, d in row if d.startswith("c:sm:bok")]
    row = _rows(bot, "SELECT * FROM settlement_batches WHERE id = ?", batch)[0]
    assert (row["status"], row["tax_withheld_vnd"], row["shopee_payout_vnd"], row["bank_received_vnd"]) == (
        MATCHED, 2_000, 17_800, 17_800)
    evidence = [(r["kind"], r["verification"]) for r in _rows(bot, "SELECT * FROM settlement_evidence ORDER BY id")]
    assert evidence == [("shopee_payment_report", "SUPERSEDED"), ("shopee_payment_report", "VERIFIED"),
                        ("bank_statement", "VERIFIED")]
    assert "đã xác nhận tiền về rồi" in _callback(bot, ADMIN, f"c:sm:bok:{batch}:17800").text
    assert [tuple(r) for r in _rows(bot, "SELECT * FROM cashback_entries ORDER BY conversion_id")] == wallet
    assert not _rows(bot, "SELECT * FROM cashback_payouts")
    assert {r["validation_status"] for r in _rows(bot, "SELECT validation_status FROM shopee_conversions")} != {"APPROVED"}


def test_loi_doc_ky_khong_lam_hong_luot_dong_bo(bot):
    client = MagicMock()
    client.check_status.return_value = ShopeeStatusResult(ok=True, status_code=200, username="shop")
    client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
    client.fetch_conversions.return_value = {"code": 0, "data": {"list": []}}
    client.fetch_billing_list.side_effect = ShopeeApiError("Shopee HTTP 403", status_code=403, category="ACCESS_DENIED")
    result = ShopeeSyncEngine(bot.repo).sync(client=client)
    assert result.ok is True and result.status == "success"
    client.fetch_billing_list.assert_called_once()
    assert not _rows(bot, "SELECT * FROM settlement_batches")


def test_thue_tam_tinh_lam_tron_tung_khoan():
    assert shopee_payout.expected_tax(25_371) == 2_538  # kỳ 29/10/2026: 1.269đ TNCN + 1.269đ VAT
    assert shopee_payout.expected_tax(20_000) == 2_000
