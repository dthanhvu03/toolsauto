"""Cashback V1.2 offline. Không mở data/cashback.sqlite và không có định danh khách."""

from __future__ import annotations

from pathlib import Path

import pytest

from cashback_bot.calculator import (
    POLICY_ID,
    CalculationError,
    DryRunLedger,
    EstimatePolicy,
    FinalInput,
    PeriodLine,
    ReconciliationRequired,
    allocate_period,
    authorize_payable,
    estimate_cashback,
    final_cashback,
    resolve_gross,
    sub_id_matches,
)
from cashback_bot.messages import tip_reply
from cashback_bot.money import estimated_cashback
from cashback_bot.service import CashbackService
from tests.test_cashback_bot import NOW, FakeClient, payload, repo, service, settings

POLICY = EstimatePolicy()
PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "cashback.sqlite"


def _final(**overrides) -> FinalInput:
    base = dict(
        verified_commission=4_510,
        fee_already_in_commission=False,
        tax_already_in_commission=False,
        actual_service_fee=44,
        actual_tax_withheld=0,
    )
    base.update(overrides)
    return FinalInput(**base)


def test_khong_mo_sqlite_that():
    assert not any(path == PRODUCTION_DB for path in Path("/tmp").glob("cashback.sqlite"))


def test_case_01_chung_tu_thang_8():
    gross = resolve_gross(total=4_510, shopee=2_050, xtra=2_460)
    result = final_cashback(_final(verified_commission=gross))
    assert result.distributable_vnd == 4_466
    assert result.illustrative_cashback_vnd == 3_126
    assert result.payable_vnd is None
    assert authorize_payable(result) is None
    assert "payment_cost" not in result.reasons
    estimated = estimate_cashback(gross, POLICY)
    assert estimated.fee_reserve_vnd == 45
    assert result.distributable_vnd != gross - estimated.fee_reserve_vnd - 3


def test_case_02_thue_thuc_te_bang_0_khong_tru_du_phong():
    result = final_cashback(_final(actual_tax_withheld=0))
    assert result.distributable_vnd == 4_466
    estimated = estimate_cashback(4_510, POLICY)
    assert estimated.tax_risk_reserve_vnd == 451
    assert result.distributable_vnd == 4_510 - 44


def test_case_03_thue_chua_nam_trong_net_moi_duoc_tru():
    once = final_cashback(_final(actual_tax_withheld=200))
    assert once.distributable_vnd == 4_266
    already = final_cashback(_final(tax_already_in_commission=True, actual_tax_withheld=200))
    assert already.distributable_vnd == 4_466


def test_case_04_phan_bo_ky_khop_tong():
    lines = [PeriodLine("a", 2_050), PeriodLine("b", 2_460)]
    period = allocate_period(lines, period_fee=44, period_tax=0, period_adjustments=0)
    assert sum(period.fee) == 44
    assert sum(period.tax) == 0
    assert sum(period.adjustments) == 0
    assert period.fee[0] + period.fee[1] == 44


def test_case_05_hoa_hong_giam_dung_snapshot_moi():
    previous = 4_510
    current = 3_000
    assert current != previous
    result = final_cashback(_final(verified_commission=current, actual_service_fee=0))
    assert result.distributable_vnd == 3_000


def test_case_06_huy_hoac_fraud_khong_co_cashback():
    result = final_cashback(_final(fraud_or_cancelled=True))
    assert result.illustrative_cashback_vnd is None
    assert result.payable_vnd is None
    assert result.status == "reversed"


def test_case_07_hoa_hong_0_khong_am():
    estimated = estimate_cashback(0, POLICY)
    assert estimated.estimated_cashback_vnd == 0
    result = final_cashback(_final(verified_commission=0, actual_service_fee=0))
    assert result.illustrative_cashback_vnd == 0
    assert result.payable_vnd is None
    with pytest.raises(CalculationError):
        estimate_cashback(-1, POLICY)


def test_case_08_chua_co_chung_tu_thanh_toan():
    result = final_cashback(
        _final(
            payment_evidence=False,
            sub_id_matched=True,
            conversion_verified=True,
            commission_approved=True,
            payout_policy_approved=True,
        )
    )
    assert result.illustrative_cashback_vnd == 3_126
    assert result.payable_vnd is None
    assert "no_payment_evidence" in result.reasons


def test_case_09_sub_id_khong_khop():
    known = {"bAtxNOK7"}
    assert sub_id_matches("bAtxNOK7", known) is True
    assert sub_id_matches("KJBLJBN", known) is False
    assert sub_id_matches("----", known) is False
    result = final_cashback(_final(sub_id_matched=False, payment_evidence=True))
    assert result.payable_vnd is None
    assert "sub_id_unmatched" in result.reasons


def test_case_10_vuot_quy_khong_tao_nghia_vu_moi():
    ledger = DryRunLedger(1_000)
    assert ledger.propose("order-a", 800) == 800
    assert ledger.propose("order-b", 300) is None
    assert ledger.reserved_vnd == 800


def test_case_11_lam_tron_xuong_va_phan_du():
    policy = EstimatePolicy(rounding_unit=10)
    gross = 1_000
    result = estimate_cashback(gross, policy)
    assert result.estimated_cashback_vnd % 10 == 0
    assert result.estimated_cashback_vnd <= estimate_cashback(gross, POLICY).estimated_cashback_vnd
    tiny = estimate_cashback(1, POLICY)
    assert tiny.estimated_cashback_vnd == 0
    split = allocate_period(
        [PeriodLine("u1", 1), PeriodLine("u2", 1), PeriodLine("u3", 1)],
        period_fee=2,
        period_tax=0,
        period_adjustments=0,
    )
    assert sum(split.fee) == 2


def test_case_12_tinh_lai_khong_ghi_trung():
    ledger = DryRunLedger(5_000)
    assert ledger.propose("same", 3_126) == 3_126
    assert ledger.propose("same", 3_126) == 3_126
    assert ledger.reserved_vnd == 3_126
    assert len(ledger._items) == 1


def test_case_13_phi_chuyen_tien_lon_hon_phan_giu_lai():
    result = final_cashback(_final(payment_cost_vnd=2_000))
    assert result.illustrative_cashback_vnd == 0
    assert result.payable_vnd is None
    assert "payment_cost_exceeds_cashback" in result.reasons


def test_case_14_dong_cu_khong_bi_tinh_lai(tmp_path):
    client = FakeClient(payload())
    service(tmp_path, client).handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    store = repo(tmp_path)
    with store.connect() as conn:
        before = conn.execute("SELECT estimated_cashback, sub_id FROM link_requests").fetchone()
    estimate_cashback(20_000, POLICY)
    with store.connect() as conn:
        after = conn.execute("SELECT estimated_cashback, sub_id FROM link_requests").fetchone()
    assert after["estimated_cashback"] == before["estimated_cashback"] == 14_000
    assert after["sub_id"] == before["sub_id"]
    assert str(tmp_path) not in str(PRODUCTION_DB)


def test_v11_van_la_70_phan_tram_gop():
    assert estimated_cashback(20_000, 70) == 14_000
    assert estimated_cashback(4_510, 70) == 3_157


def test_uoc_tinh_mau(tmp_path):
    samples = {
        1_000: 623,
        4_510: 2_809,
        10_000: 6_231,
        100_000: 62_314,
        1_000_000: 623_140,
    }
    for gross, expected in samples.items():
        result = estimate_cashback(gross, POLICY)
        assert result.reliable is True
        assert result.estimated_cashback_vnd == expected
        assert result.estimated_cashback_vnd < estimated_cashback(gross, 70)
    assert estimate_cashback(4_510, POLICY, reliable=False).reliable is False
    with pytest.raises(CalculationError):
        resolve_gross(total=4_510, shopee=2_050)


def test_thieu_du_lieu_ky_khong_ep_can():
    with pytest.raises(ReconciliationRequired):
        allocate_period([PeriodLine("only", 0)], period_fee=44, period_tax=0, period_adjustments=0)


def test_policy_v12_chi_bat_khi_co_cot(tmp_path):
    turned_on = settings(tmp_path, estimate_policy="v1.2")
    reply = CashbackService(turned_on, repo(tmp_path), FakeClient(payload())).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW
    )
    assert "14.000đ" in reply.text
    assert "Hoàn dự kiến:" in reply.text
    assert "dự phòng" not in reply.text

    store = repo(tmp_path)
    with store.connect() as conn:
        conn.execute("ALTER TABLE link_requests ADD COLUMN estimate_policy TEXT")
    reply = CashbackService(turned_on, store, FakeClient(payload())).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=2, now=NOW
    )
    assert "sau dự phòng phí và thuế" in tip_reply(reply.inline_keyboard[-1][0][1]).text
    assert "<b>12.462đ</b>" in reply.text
    assert "chắc chắn" not in reply.text.lower()
    assert "số dư" not in reply.text.lower()
    assert "đã nhận hoa hồng" not in reply.text.lower()
    with store.connect() as conn:
        saved = conn.execute(
            "SELECT estimated_cashback, estimate_policy FROM link_requests WHERE telegram_update_id = 2"
        ).fetchone()
    assert saved["estimated_cashback"] == 12_462
    assert saved["estimate_policy"] == POLICY_ID
    old = conn_old(store)
    assert old["estimated_cashback"] == 14_000
    assert old["estimate_policy"] is None


def conn_old(store):
    with store.connect() as conn:
        return conn.execute(
            "SELECT estimated_cashback, estimate_policy FROM link_requests WHERE telegram_update_id = 1"
        ).fetchone()
