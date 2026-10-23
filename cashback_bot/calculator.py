"""Tính cashback V1.2. Tiền là số nguyên VND. Không tạo khoản được chi.

payable_vnd luôn là None. Module này không nối với ví hay lệnh chi.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_ID = "v1.2-reserve-2026-10-23"
_BPS = 10_000


class CalculationError(ValueError):
    """Đầu vào tiền không dùng được."""


class ReconciliationRequired(Exception):
    """Kỳ thanh toán thiếu dữ liệu. Không phân bổ cho đủ."""


def _vnd(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalculationError(name)
    if value < 0:
        raise CalculationError(name)
    return value


def _bps(value: object, name: str) -> int:
    number = _vnd(value, name)
    if number > _BPS:
        raise CalculationError(name)
    return number


def bps_ceil(gross_vnd: int, rate_bps: int) -> int:
    """ceil(gross × rate). rate_bps = 10000 nghĩa là 100%."""
    gross_vnd = _vnd(gross_vnd, "gross")
    rate_bps = _bps(rate_bps, "rate")
    if gross_vnd == 0 or rate_bps == 0:
        return 0
    return (gross_vnd * rate_bps + (_BPS - 1)) // _BPS


def bps_floor(amount_vnd: int, rate_bps: int) -> int:
    amount_vnd = _vnd(amount_vnd, "amount")
    rate_bps = _bps(rate_bps, "rate")
    return (amount_vnd * rate_bps) // _BPS


def round_down(amount_vnd: int, unit: int) -> int:
    amount_vnd = _vnd(amount_vnd, "amount")
    if isinstance(unit, bool) or not isinstance(unit, int) or unit < 1:
        raise CalculationError("rounding_unit")
    return (amount_vnd // unit) * unit


def resolve_gross(
    total: int | None = None,
    shopee: int | None = None,
    xtra: int | None = None,
) -> int:
    """Một tổng. Không cộng thêm tổng vào Shopee + Xtra."""
    if total is not None:
        total = _vnd(total, "total")
    parts = []
    if shopee is not None:
        parts.append(_vnd(shopee, "shopee"))
    if xtra is not None:
        parts.append(_vnd(xtra, "xtra"))
    if total is None and len(parts) != 2:
        raise CalculationError("gross")
    if total is not None and len(parts) == 2 and total != parts[0] + parts[1]:
        raise CalculationError("gross_conflict")
    if total is not None and len(parts) == 1:
        raise CalculationError("gross_conflict")
    if total is not None:
        return total
    return parts[0] + parts[1]


@dataclass(frozen=True)
class EstimatePolicy:
    cashback_share_bps: int = 7_000
    service_fee_bps: int = 98
    tax_risk_reserve_bps: int = 1_000
    other_cost_reserve_vnd: int = 0
    rounding_unit: int = 1

    def __post_init__(self) -> None:
        _bps(self.cashback_share_bps, "share")
        _bps(self.service_fee_bps, "fee")
        _bps(self.tax_risk_reserve_bps, "tax")
        _vnd(self.other_cost_reserve_vnd, "other")
        if isinstance(self.rounding_unit, bool) or not isinstance(self.rounding_unit, int) or self.rounding_unit < 1:
            raise CalculationError("rounding_unit")


@dataclass(frozen=True)
class EstimateResult:
    policy_id: str
    gross_vnd: int
    fee_reserve_vnd: int
    tax_risk_reserve_vnd: int
    other_reserve_vnd: int
    distributable_vnd: int
    estimated_cashback_vnd: int
    reliable: bool


def estimate_cashback(gross_vnd: int | None, policy: EstimatePolicy, *, reliable: bool = True) -> EstimateResult:
    if not reliable or gross_vnd is None:
        return EstimateResult(POLICY_ID, 0, 0, 0, 0, 0, 0, False)
    gross = _vnd(gross_vnd, "gross")
    fee = bps_ceil(gross, policy.service_fee_bps)
    tax = bps_ceil(gross, policy.tax_risk_reserve_bps)
    other = policy.other_cost_reserve_vnd
    distributable = gross - fee - tax - other
    if distributable < 0:
        distributable = 0
    cashback = round_down(bps_floor(distributable, policy.cashback_share_bps), policy.rounding_unit)
    return EstimateResult(POLICY_ID, gross, fee, tax, other, distributable, cashback, True)


@dataclass(frozen=True)
class FinalInput:
    """Các cờ unaccounted chỉ trừ khoản chưa nằm trong verified_commission."""

    verified_commission: int | None
    fee_already_in_commission: bool
    tax_already_in_commission: bool
    actual_service_fee: int | None
    actual_tax_withheld: int | None
    adjustments_vnd: int = 0
    payment_cost_vnd: int = 0
    approved_unsettled_tax_reserve_vnd: int = 0
    payment_evidence: bool = False
    sub_id_matched: bool = False
    conversion_verified: bool = False
    commission_approved: bool = False
    dispute_open: bool = False
    fraud_or_cancelled: bool = False
    payout_policy_approved: bool = False


@dataclass(frozen=True)
class FinalResult:
    illustrative_cashback_vnd: int | None
    distributable_vnd: int | None
    payable_vnd: None
    status: str
    reasons: tuple[str, ...]


def final_cashback(data: FinalInput, share_bps: int = 7_000) -> FinalResult:
    share_bps = _bps(share_bps, "share")
    if data.fraud_or_cancelled:
        return FinalResult(None, None, None, "reversed", ("fraud_or_cancelled", "payout_not_authorized"))
    missing: list[str] = []
    if data.verified_commission is None:
        missing.append("missing_commission")
    if data.actual_service_fee is None and not data.fee_already_in_commission:
        missing.append("missing_fee")
    if data.actual_tax_withheld is None and not data.tax_already_in_commission:
        missing.append("missing_tax")
    if missing:
        return FinalResult(None, None, None, "reconciliation_required", tuple(missing))

    commission = _vnd(data.verified_commission, "commission")
    fee = 0 if data.fee_already_in_commission else _vnd(data.actual_service_fee, "fee")
    tax = 0 if data.tax_already_in_commission else _vnd(data.actual_tax_withheld, "tax")
    adjustments = _vnd(data.adjustments_vnd, "adjustments")
    payment_cost = _vnd(data.payment_cost_vnd, "payment_cost")
    reserve = _vnd(data.approved_unsettled_tax_reserve_vnd, "reserve")
    distributable = commission - fee - tax - adjustments - reserve
    if distributable < 0:
        distributable = 0
    illustrative = bps_floor(distributable, share_bps)
    reasons = _blocked(data)
    if payment_cost > distributable - illustrative:
        reasons.append("payment_cost_exceeds_cashback")
        illustrative = 0
    status = "blocked" if reasons else "formula_only"
    return FinalResult(illustrative, distributable, None, status, tuple(reasons))


def _blocked(data: FinalInput) -> list[str]:
    reasons = []
    if not data.conversion_verified:
        reasons.append("conversion_not_verified")
    if not data.sub_id_matched:
        reasons.append("sub_id_unmatched")
    if not data.commission_approved:
        reasons.append("commission_not_approved")
    if not data.payment_evidence:
        reasons.append("no_payment_evidence")
    if data.dispute_open:
        reasons.append("dispute_open")
    if not data.payout_policy_approved:
        reasons.append("payout_policy_not_approved")
    reasons.append("payout_not_authorized")
    return reasons


def sub_id_matches(conversion_sub_id: str, known_sub_ids: set[str]) -> bool:
    if not isinstance(conversion_sub_id, str) or conversion_sub_id in {"", "----"}:
        return False
    return conversion_sub_id in known_sub_ids


def authorize_payable(_: FinalResult) -> None:
    """Cổng chi. Luôn None cho tới khi có quyết định phát hành riêng."""
    return None


def allocate_exact(weights: list[int], total: int) -> list[int]:
    """Phân bổ total theo hoa hồng. Tổng phần phân bổ bằng total."""
    if isinstance(total, bool) or not isinstance(total, int):
        raise CalculationError("total")
    if not weights:
        if total == 0:
            return []
        raise ReconciliationRequired("empty_period")
    clean = [_vnd(weight, "weight") for weight in weights]
    sign = -1 if total < 0 else 1
    amount = abs(total)
    base = sum(clean)
    if base == 0:
        if amount == 0:
            return [0 for _ in clean]
        raise ReconciliationRequired("zero_weight")
    floors = [(weight * amount) // base for weight in clean]
    remainder = amount - sum(floors)
    ranked = sorted(
        range(len(clean)),
        key=lambda index: (-((clean[index] * amount) % base), index),
    )
    for index in ranked[:remainder]:
        floors[index] += 1
    if sum(floors) != amount:
        raise ReconciliationRequired("allocation_mismatch")
    return [sign * item for item in floors]


@dataclass(frozen=True)
class PeriodLine:
    key: str
    commission_vnd: int


@dataclass(frozen=True)
class PeriodAllocation:
    status: str
    fee: tuple[int, ...]
    tax: tuple[int, ...]
    adjustments: tuple[int, ...]


def allocate_period(
    lines: list[PeriodLine],
    period_fee: int,
    period_tax: int,
    period_adjustments: int,
) -> PeriodAllocation:
    if any(line.commission_vnd is None for line in lines):
        raise ReconciliationRequired("missing_line")
    weights = [line.commission_vnd for line in lines]
    fee = allocate_exact(weights, _signed(period_fee, "fee"))
    tax = allocate_exact(weights, _signed(period_tax, "tax"))
    adjustments = allocate_exact(weights, _signed(period_adjustments, "adjustments"))
    return PeriodAllocation("allocated", tuple(fee), tuple(tax), tuple(adjustments))


def _signed(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalculationError(name)
    return value


def settle_commission(
    gross_vnd: int,
    actual_fee_vnd: int | None,
    tax_withheld_vnd: int | None,
    unpaid_tax_reserve_vnd: int | None,
    other_cost_vnd: int,
    *,
    fee_already_in_gross: bool,
    withheld_already_in_gross: bool,
    reserve_already_in_gross: bool,
    share_bps: int = 7_000,
) -> tuple[int | None, int | None, tuple[str, ...]]:
    """Một công thức cho mọi loại hình. Trả (distributable, cashback, lý do thiếu).

    Thuế đã khấu trừ và dự phòng là hai khoản. Khoản đã nằm trong gross thì không trừ lại.
    """
    share_bps = _bps(share_bps, "share")
    missing: list[str] = []
    if actual_fee_vnd is None and not fee_already_in_gross:
        missing.append("missing_fee")
    if tax_withheld_vnd is None and not withheld_already_in_gross:
        missing.append("missing_withheld_tax")
    if unpaid_tax_reserve_vnd is None and not reserve_already_in_gross:
        missing.append("missing_tax_reserve")
    if missing:
        return None, None, tuple(missing)
    gross = _vnd(gross_vnd, "gross")
    fee = 0 if fee_already_in_gross else _vnd(actual_fee_vnd, "fee")
    withheld = 0 if withheld_already_in_gross else _vnd(tax_withheld_vnd, "withheld")
    reserve = 0 if reserve_already_in_gross else _vnd(unpaid_tax_reserve_vnd, "reserve")
    other = _vnd(other_cost_vnd, "other")
    distributable = gross - fee - withheld - reserve - other
    if distributable < 0:
        distributable = 0
    return distributable, bps_floor(distributable, share_bps), ()


def unaccounted_withheld(original_vnd: int, adjustment_vnd: int, already_in_gross_vnd: int) -> int:
    """Điều chỉnh sau khấu trừ. Chỉ phần chưa nằm trong gross được trừ tiếp."""
    original = _vnd(original_vnd, "original")
    already = _vnd(already_in_gross_vnd, "already")
    if isinstance(adjustment_vnd, bool) or not isinstance(adjustment_vnd, int):
        raise CalculationError("adjustment")
    updated = original + adjustment_vnd
    if updated < 0 or already > updated:
        raise ReconciliationRequired("withheld_adjustment")
    return updated - already


class DryRunLedger:
    """Sổ thử. Không ghi production và không phát hành payable."""

    def __init__(self, fund_vnd: int):
        self.fund_vnd = _vnd(fund_vnd, "fund")
        self.reserved_vnd = 0
        self._items: dict[str, int] = {}

    def propose(self, key: str, amount_vnd: int) -> int | None:
        if key in self._items:
            return self._items[key]
        amount = _vnd(amount_vnd, "amount")
        if self.reserved_vnd + amount > self.fund_vnd:
            return None
        self._items[key] = amount
        self.reserved_vnd += amount
        return amount
