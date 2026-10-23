"""Một cửa cho công thức tiền.

Khách đang thấy V1.1: quote_displayed_vnd gọi money.estimated_cashback.
V1.2 chỉ chạy khi caller đưa EstimatePolicy. Module này không gọi mạng và không ghi SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass

from cashback_bot.calculator import (
    CalculationError,
    EstimatePolicy,
    EstimateResult,
    FinalInput,
    FinalResult,
    bps_floor,
    estimate_cashback,
    final_cashback,
    sub_id_matches,
)
from cashback_bot.money import estimated_cashback

DISPLAYED_POLICY_ID = "v1.1-gross"
MAX_SHARE_BPS = 7_000


@dataclass(frozen=True)
class CalculationBreakdown:
    """Một hình dạng kết quả. Trường None nghĩa là chưa có, không phải số 0."""

    kind: str
    basis: str
    commission_vnd: int | None
    fee_vnd: int | None
    tax_withheld_vnd: int | None
    tax_reserve_vnd: int | None
    other_vnd: int | None
    distributable_vnd: int | None
    share_bps: int | None
    cashback_vnd: int | None
    policy_id: str | None
    payable_vnd: None
    missing: tuple[str, ...]


@dataclass(frozen=True)
class LinkBenefitSnapshot:
    """Số đã lưu trên link. Không tính lại."""

    policy_id: str | None
    share_rate_percent: int | None
    estimated_cashback_vnd: int | None
    basis: str | None


def quote_displayed_vnd(commission_vnd: int, rate_percent: int) -> int:
    """Công thức production: hoa hồng ước tính nhân tỷ lệ, làm tròn xuống đồng."""
    return estimated_cashback(commission_vnd, rate_percent)


def share_cashback(net_vnd: int, share_bps: int) -> tuple[int, int]:
    """Làm tròn xuống phần chia. Trần hạng V1 là 70%. Trả (khách, phần còn lại)."""
    if isinstance(share_bps, bool) or not isinstance(share_bps, int) or not 0 <= share_bps <= MAX_SHARE_BPS:
        raise CalculationError("above_v1_cap")
    if isinstance(net_vnd, bool) or not isinstance(net_vnd, int) or net_vnd < 0:
        raise CalculationError("net")
    cashback = bps_floor(net_vnd, share_bps)
    return cashback, net_vnd - cashback


def net_of_charges(
    gross_vnd: int,
    fee_vnd: int | None,
    withheld_vnd: int | None,
    reserve_vnd: int | None,
    *,
    fee_includes_vat: bool = False,
    vat_on_fee_vnd: int | None = None,
    fee_already_in_gross: bool = False,
    withheld_already_in_gross: bool = False,
    reserve_same_as_withheld: bool = False,
) -> tuple[int | None, tuple[str, ...]]:
    """None khi thiếu số. Phí đã gồm VAT thì không cộng VAT lần nữa."""
    missing: list[str] = []
    if isinstance(gross_vnd, bool) or not isinstance(gross_vnd, int) or gross_vnd < 0:
        raise CalculationError("gross")
    if fee_vnd is None and not fee_already_in_gross:
        missing.append("missing_fee")
    if withheld_vnd is None and not withheld_already_in_gross:
        missing.append("missing_withheld")
    if reserve_vnd is None and not reserve_same_as_withheld:
        missing.append("missing_reserve")
    if missing:
        return None, tuple(missing)
    fee = 0 if fee_already_in_gross else int(fee_vnd or 0)
    if vat_on_fee_vnd is not None:
        if isinstance(vat_on_fee_vnd, bool) or not isinstance(vat_on_fee_vnd, int) or vat_on_fee_vnd < 0:
            raise CalculationError("vat")
        if fee_includes_vat and vat_on_fee_vnd > fee:
            raise CalculationError("vat")
        if not fee_includes_vat and not fee_already_in_gross:
            fee += vat_on_fee_vnd
    withheld = 0 if withheld_already_in_gross else int(withheld_vnd or 0)
    reserve = 0 if reserve_same_as_withheld else int(reserve_vnd or 0)
    total = fee + withheld + reserve
    if total > gross_vnd:
        return None, ("costs_exceed_gross",)
    return gross_vnd - total, ()


def calculate_final_cashback(data: FinalInput, share_bps: int = 7_000) -> FinalResult:
    return final_cashback(data, share_bps)


def explain_displayed(commission_vnd: int, rate_percent: int) -> CalculationBreakdown:
    cashback = quote_displayed_vnd(commission_vnd, rate_percent)
    return CalculationBreakdown(
        "displayed_gross",
        "gross_estimate",
        commission_vnd,
        None,
        None,
        None,
        None,
        None,
        rate_percent * 100,
        cashback,
        f"{DISPLAYED_POLICY_ID}-{rate_percent}",
        None,
        (),
    )


def explain_estimate(result: EstimateResult) -> CalculationBreakdown:
    """Phí và thuế ở đây là dự phòng cấu hình, không phải chứng từ."""
    missing = () if result.reliable else ("unreliable_gross",)
    return CalculationBreakdown(
        "estimate_reserve",
        "distributable_estimate",
        result.gross_vnd if result.reliable else None,
        result.fee_reserve_vnd if result.reliable else None,
        None,
        result.tax_risk_reserve_vnd if result.reliable else None,
        result.other_reserve_vnd if result.reliable else None,
        result.distributable_vnd if result.reliable else None,
        None,
        result.estimated_cashback_vnd if result.reliable else None,
        result.policy_id,
        None,
        missing,
    )


def explain_final(data: FinalInput, share_bps: int = 7_000) -> CalculationBreakdown:
    result = calculate_final_cashback(data, share_bps)
    computed = result.illustrative_cashback_vnd is not None and result.distributable_vnd is not None
    return CalculationBreakdown(
        "final",
        "distributable_net",
        data.verified_commission if computed else None,
        None if data.fee_already_in_commission else data.actual_service_fee,
        None if data.tax_already_in_commission else data.actual_tax_withheld,
        data.approved_unsettled_tax_reserve_vnd if computed else None,
        data.adjustments_vnd if computed else None,
        result.distributable_vnd,
        share_bps if computed else None,
        result.illustrative_cashback_vnd,
        None,
        None,
        result.reasons,
    )


def snapshot_from_stored(
    rate_percent: int | None,
    estimated_cashback_vnd: int | None,
    estimate_policy: str | None,
) -> LinkBenefitSnapshot:
    """Thiếu policy hoặc thiếu số đã lưu thì để trống. Không suy ra 60% hay 70%."""
    if estimate_policy:
        return LinkBenefitSnapshot(estimate_policy, rate_percent, estimated_cashback_vnd, "distributable_estimate")
    if rate_percent is None or estimated_cashback_vnd is None:
        return LinkBenefitSnapshot(None, rate_percent, estimated_cashback_vnd, None)
    return LinkBenefitSnapshot(f"{DISPLAYED_POLICY_ID}-{rate_percent}", rate_percent, estimated_cashback_vnd, "gross_estimate")


def exact_sub_id(conversion_sub_id: str, known_sub_ids: set[str]) -> bool:
    return sub_id_matches(conversion_sub_id, known_sub_ids)


__all__ = [
    "DISPLAYED_POLICY_ID",
    "CalculationBreakdown",
    "EstimatePolicy",
    "LinkBenefitSnapshot",
    "calculate_final_cashback",
    "estimate_cashback",
    "exact_sub_id",
    "explain_displayed",
    "explain_estimate",
    "explain_final",
    "MAX_SHARE_BPS",
    "net_of_charges",
    "quote_displayed_vnd",
    "share_cashback",
    "snapshot_from_stored",
]
