"""Hồ sơ thuế nhiều loại hình. Không mở database production và không chi tiền."""

from __future__ import annotations

from datetime import date

import pytest

from cashback_bot.calculator import ReconciliationRequired, allocate_period, PeriodLine
from cashback_bot.tax_profile import (
    AccountKind,
    PolicyHistory,
    RuleStatus,
    TaxProfileVersion,
    TaxRule,
    WithholdingMethod,
    assess_conversion,
    fund_after_shopee,
    revalue_order,
    CashOrder,
)

DAY = date(2026, 8, 22)
RULE = TaxRule(
    "rule-open",
    date(2026, 1, 1),
    None,
    "chưa đối chiếu văn bản",
    RuleStatus.UNVERIFIED,
    "chưa xác minh",
)
VERIFIED = TaxRule(
    "rule-verified-zero",
    date(2026, 1, 1),
    None,
    "chứng từ kỳ này ghi thuế khấu trừ bằng 0",
    RuleStatus.VERIFIED,
    "khấu trừ thực tế của kỳ",
    allows_zero_retention=False,
)


def make(kind: AccountKind, version: str, day: date, **overrides) -> TaxProfileVersion:
    fields = dict(
        version_id=version,
        account_kind=kind,
        shopee_status="confirmed",
        effective_from=day,
        shopee_accepted_on=day,
        withholding_method=WithholdingMethod.SHOPEE_WITHHOLDS,
        method_confirmed="admin",
        tax_withheld_vnd=0,
        self_assessed_tax_due_vnd=None,
        tax_reserve_vnd=0,
        declared_annual_revenue_vnd=None,
        evidence_source="admin-note",
        evidence_confirmed_on=day,
        legal_rule_id=RULE.rule_id,
    )
    fields.update(overrides)
    return TaxProfileVersion(**fields)


def test_ba_loai_hinh_dung_chung_mot_cong_thuc():
    numbers = []
    for kind in AccountKind:
        profile = make(kind, kind.value, date(2026, 1, 1))
        result = assess_conversion(profile, RULE, DAY, 4_510, 44)
        numbers.append((result.distributable_vnd, result.cashback_vnd, result.payable_vnd))
    assert numbers[0] == numbers[1] == numbers[2] == (4_466, 3_126, None)


def test_01_ca_nhan_chuyen_cnkd_giua_nam():
    personal = make(AccountKind.PERSONAL, "personal-2026", date(2026, 1, 1))
    business = make(AccountKind.INDIVIDUAL_BUSINESS, "cnkd-2026-07", date(2026, 7, 1))
    first = PolicyHistory().append(personal)
    second = first.append(business)
    assert first.on(date(2026, 8, 1)).version_id == "personal-2026"
    assert second.on(date(2026, 3, 15)).version_id == "personal-2026"
    assert second.on(date(2026, 7, 1)).version_id == "cnkd-2026-07"
    order = CashOrder("old", date(2026, 3, 15), "personal-2026", 4_510, committed_cashback_vnd=2_809)
    kept = revalue_order(order, second, 9_999, 44, rule=RULE)
    assert kept.profile_version_id == "personal-2026"
    assert kept.committed_cashback_vnd == 2_809
    assert kept.paid_cashback_vnd is None


def test_02_cnkd_chuyen_hkd():
    business = make(AccountKind.INDIVIDUAL_BUSINESS, "cnkd", date(2026, 1, 1))
    household = make(AccountKind.HOUSEHOLD_BUSINESS, "hkd", date(2026, 9, 1))
    history = PolicyHistory().append(business).append(household)
    assert history.on(date(2026, 8, 1)).account_kind is AccountKind.INDIVIDUAL_BUSINESS
    assert history.on(date(2026, 9, 2)).account_kind is AccountKind.HOUSEHOLD_BUSINESS


def test_03_thue_shopee_da_khau_tru_khong_tru_them_du_phong_mac_dinh():
    profile = make(
        AccountKind.PERSONAL,
        "withheld",
        date(2026, 1, 1),
        tax_withheld_vnd=200,
        tax_reserve_vnd=0,
        self_assessed_tax_due_vnd=None,
    )
    result = assess_conversion(profile, RULE, DAY, 4_510, 44)
    assert result.distributable_vnd == 4_266
    assert result.cashback_vnd == 2_986
    assert result.payable_vnd is None


def test_04_tu_khai_chua_nop():
    profile = make(
        AccountKind.INDIVIDUAL_BUSINESS,
        "self",
        date(2026, 1, 1),
        withholding_method=WithholdingMethod.SELF_DECLARE,
        tax_withheld_vnd=0,
        self_assessed_tax_due_vnd=300,
        tax_reserve_vnd=None,
    )
    result = assess_conversion(profile, RULE, DAY, 4_510, 44)
    assert result.distributable_vnd == 4_166
    assert result.payable_vnd is None
    assert "payout_not_authorized" in result.reasons


def test_05_xac_minh_khong_phat_sinh_thue_can_giu():
    profile = make(
        AccountKind.PERSONAL,
        "zero",
        date(2026, 1, 1),
        tax_withheld_vnd=0,
        self_assessed_tax_due_vnd=0,
        tax_reserve_vnd=0,
        legal_rule_id=VERIFIED.rule_id,
        declared_annual_revenue_vnd=500_000,
    )
    result = assess_conversion(profile, VERIFIED, DAY, 4_510, 44, shopee_paid_vnd=4_466)
    assert result.distributable_vnd == 4_466
    assert result.cashback_vnd == 3_126
    assert result.payable_vnd is None
    assert "rule_unverified" not in result.reasons
    blocked = assess_conversion(
        profile,
        VERIFIED,
        DAY,
        4_510,
        44,
        claim_exemption=True,
        shopee_paid_vnd=4_466,
    )
    assert "exemption_rejected" in blocked.reasons
    assert blocked.payable_vnd is None


def test_06_nhieu_ky_nhieu_chinh_sach():
    early = make(AccountKind.PERSONAL, "early", date(2026, 1, 1), tax_reserve_vnd=100)
    late = make(AccountKind.HOUSEHOLD_BUSINESS, "late", date(2026, 7, 1), tax_reserve_vnd=0)
    history = PolicyHistory().append(early).append(late)
    first = assess_conversion(history.on(date(2026, 2, 1)), RULE, date(2026, 2, 1), 4_510, 44)
    second = assess_conversion(history.on(date(2026, 8, 1)), RULE, date(2026, 8, 1), 4_510, 44)
    assert first.profile_version_id == "early"
    assert second.profile_version_id == "late"
    assert first.distributable_vnd == 4_366
    assert second.distributable_vnd == 4_466


def test_07_mot_ky_nhieu_conversion():
    profile = make(AccountKind.PERSONAL, "period", date(2026, 1, 1))
    split = allocate_period(
        [PeriodLine("a", 2_050), PeriodLine("b", 2_460)],
        period_fee=44,
        period_tax=0,
        period_adjustments=0,
    )
    assert sum(split.fee) == 44
    results = [
        assess_conversion(profile, RULE, DAY, gross, fee, withheld_vnd=0, reserve_vnd=0)
        for gross, fee in ((2_050, split.fee[0]), (2_460, split.fee[1]))
    ]
    assert sum(item.distributable_vnd for item in results) == 4_466
    assert sum(item.cashback_vnd for item in results) == 3_126


def test_08_khau_tru_roi_dieu_chinh():
    from cashback_bot.calculator import unaccounted_withheld

    assert unaccounted_withheld(100, 30, 0) == 130
    assert unaccounted_withheld(100, 30, 100) == 30
    with pytest.raises(ReconciliationRequired):
        unaccounted_withheld(100, 30, 200)
    profile = make(AccountKind.PERSONAL, "adjust", date(2026, 1, 1))
    result = assess_conversion(
        profile,
        RULE,
        DAY,
        4_510,
        44,
        withheld_vnd=130,
        reserve_vnd=0,
        withheld_already_in_gross=False,
    )
    assert result.distributable_vnd == 4_336


def test_09_thieu_du_lieu_thi_chan():
    profile = make(
        AccountKind.PERSONAL,
        "gap",
        date(2026, 1, 1),
        withholding_method=WithholdingMethod.UNVERIFIED,
        tax_withheld_vnd=None,
        tax_reserve_vnd=None,
        evidence_source="",
        evidence_confirmed_on=None,
        legal_rule_id=None,
    )
    result = assess_conversion(profile, None, DAY, 4_510, None)
    assert result.distributable_vnd is None
    assert result.payable_vnd is None
    assert "missing_fee" in result.reasons
    assert "withholding_unverified" in result.reasons
    assert "rule_unverified" in result.reasons


def test_10_khong_chi_vuot_tien_shopee_da_tra():
    assert fund_after_shopee(None, 3_126) is None
    assert fund_after_shopee(1_000, 3_126) is None
    reserved = fund_after_shopee(4_466, 3_126)
    assert reserved == 3_126
    profile = make(AccountKind.PERSONAL, "paid", date(2026, 1, 1), legal_rule_id=VERIFIED.rule_id)
    result = assess_conversion(profile, VERIFIED, DAY, 4_510, 44, shopee_paid_vnd=1_000)
    assert result.payable_vnd is None
    assert result.available_fund_vnd is None
    assert "paid_amount_below_distributable" in result.reasons


def test_chuyen_loai_hinh_thieu_ngay_shopee_bi_tu_choi():
    personal = make(AccountKind.PERSONAL, "p", date(2026, 1, 1))
    bad = make(
        AccountKind.HOUSEHOLD_BUSINESS,
        "h",
        date(2026, 5, 1),
        shopee_accepted_on=None,
        shopee_status="pending",
    )
    with pytest.raises(Exception):
        PolicyHistory().append(personal).append(bad)
