"""Cửa tiền dùng chung. Không mở SQLite production và không gọi mạng."""

from __future__ import annotations

from cashback_bot.calculator import EstimatePolicy, FinalInput, estimate_cashback as raw_estimate
from cashback_bot.money import estimated_cashback
from cashback_bot.pricing import (
    calculate_final_cashback,
    explain_displayed,
    explain_estimate,
    explain_final,
    quote_displayed_vnd,
    snapshot_from_stored,
    exact_sub_id,
)


def test_cong_thuc_dang_hien_van_la_70_phan_tram_gross():
    assert quote_displayed_vnd(20_000, 70) == estimated_cashback(20_000, 70) == 14_000
    assert quote_displayed_vnd(4_510, 70) == 3_157
    shown = explain_displayed(4_510, 70)
    assert shown.kind == "displayed_gross"
    assert shown.fee_vnd is None
    assert shown.tax_withheld_vnd is None
    assert shown.tax_reserve_vnd is None
    assert shown.distributable_vnd is None
    assert shown.cashback_vnd == 3_157
    assert shown.policy_id == "v1.1-gross-70"
    assert shown.payable_vnd is None
    assert explain_displayed(4_510, 70) == shown


def test_khong_co_duong_mac_dinh_60():
    assert quote_displayed_vnd(10_000, 70) == 7_000
    assert quote_displayed_vnd(10_000, 60) == 6_000


def test_uoc_tinh_v12_khong_bien_du_phong_thanh_thue_da_nop():
    result = raw_estimate(4_510, EstimatePolicy())
    explained = explain_estimate(result)
    assert explained.kind == "estimate_reserve"
    assert explained.tax_withheld_vnd is None
    assert explained.tax_reserve_vnd == result.tax_risk_reserve_vnd
    assert explained.cashback_vnd == result.estimated_cashback_vnd
    assert explained.payable_vnd is None
    assert explain_estimate(result) == explained


def test_final_thieu_chung_tu_khong_dien_0():
    data = FinalInput(
        verified_commission=None,
        fee_already_in_commission=False,
        tax_already_in_commission=False,
        actual_service_fee=None,
        actual_tax_withheld=None,
        payment_evidence=False,
    )
    explained = explain_final(data)
    assert explained.cashback_vnd is None
    assert explained.payable_vnd is None
    assert explained.distributable_vnd is None
    assert 0 not in (explained.cashback_vnd, explained.payable_vnd)
    assert explained.missing
    assert "missing_commission" in explained.missing
    again = calculate_final_cashback(data)
    assert again.payable_vnd is None
    assert again.illustrative_cashback_vnd is None


def test_snapshot_cu_khong_bi_tinh_lai():
    stored = snapshot_from_stored(70, 3_157, None)
    assert stored.policy_id == "v1.1-gross-70"
    assert stored.estimated_cashback_vnd == 3_157
    assert stored.basis == "gross_estimate"
    incomplete = snapshot_from_stored(70, None, None)
    assert incomplete.basis is None
    assert incomplete.estimated_cashback_vnd is None
    assert incomplete.policy_id is None


def test_sub_id_khop_dung_chu_hoa_thuong():
    assert exact_sub_id("AbC12345", {"AbC12345"}) is True
    assert exact_sub_id("abc12345", {"AbC12345"}) is False
    assert exact_sub_id("----", {"----"}) is False
    assert exact_sub_id("", {""}) is False
