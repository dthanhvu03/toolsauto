"""Hồ sơ thuế có phiên bản. Không suy ra thuế từ nhãn tài khoản.

payable_vnd luôn None. Module không ghi database và không chi tiền.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from cashback_bot.calculator import (
    CalculationError,
    DryRunLedger,
    authorize_payable,
    settle_commission,
)

PAYABLE_BLOCK = "payout_not_authorized"


class AccountKind(Enum):
    PERSONAL = "PERSONAL"
    INDIVIDUAL_BUSINESS = "INDIVIDUAL_BUSINESS"
    HOUSEHOLD_BUSINESS = "HOUSEHOLD_BUSINESS"


class WithholdingMethod(Enum):
    SHOPEE_WITHHOLDS = "shopee_withholds"
    SELF_DECLARE = "self_declare"
    COMBINED = "combined"
    UNVERIFIED = "unverified"


class RuleStatus(Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class TaxRule:
    """Quy tắc pháp lý. Thuế suất chỉ có khi đã xác minh và admin ghi số."""

    rule_id: str
    effective_from: date
    effective_to: date | None
    source: str
    status: RuleStatus
    method_note: str
    allows_zero_retention: bool = False

    def covers(self, day: date) -> bool:
        if day < self.effective_from:
            return False
        if self.effective_to is not None and day > self.effective_to:
            return False
        return True


@dataclass(frozen=True)
class TaxProfileVersion:
    version_id: str
    account_kind: AccountKind
    shopee_status: str
    effective_from: date
    shopee_accepted_on: date | None
    withholding_method: WithholdingMethod
    method_confirmed: str
    tax_withheld_vnd: int | None
    self_assessed_tax_due_vnd: int | None
    tax_reserve_vnd: int | None
    declared_annual_revenue_vnd: int | None
    evidence_source: str
    evidence_confirmed_on: date | None
    legal_rule_id: str | None

    def __post_init__(self) -> None:
        if self.shopee_status not in {"confirmed", "pending", "unverified"}:
            raise CalculationError("shopee_status")


@dataclass(frozen=True)
class PolicyHistory:
    versions: tuple[TaxProfileVersion, ...] = ()

    def append(self, version: TaxProfileVersion) -> PolicyHistory:
        if any(item.version_id == version.version_id for item in self.versions):
            raise CalculationError("duplicate_version")
        if self.versions:
            previous = self.versions[-1]
            if version.effective_from <= previous.effective_from:
                raise CalculationError("effective_from")
            if version.account_kind != previous.account_kind:
                if version.shopee_accepted_on != version.effective_from:
                    raise CalculationError("shopee_accepted_on")
                if version.shopee_status != "confirmed":
                    raise CalculationError("shopee_status")
        return PolicyHistory(self.versions + (version,))

    def on(self, day: date) -> TaxProfileVersion | None:
        found = [item for item in self.versions if item.effective_from <= day]
        if not found:
            return None
        return found[-1]


@dataclass(frozen=True)
class CashOrder:
    order_key: str
    order_date: date
    profile_version_id: str
    gross_vnd: int
    committed_cashback_vnd: int | None = None
    paid_cashback_vnd: int | None = None


@dataclass(frozen=True)
class Assessment:
    profile_version_id: str
    distributable_vnd: int | None
    cashback_vnd: int | None
    payable_vnd: None
    available_fund_vnd: None
    reasons: tuple[str, ...]
    committed_cashback_vnd: int | None = None
    paid_cashback_vnd: int | None = None


def _unpaid(self_assessed: int | None, reserve: int | None) -> int | None:
    """Thuế tự nộp và dự phòng cộng lại. Thiếu cả hai thì chưa có số."""
    if self_assessed is None and reserve is None:
        return None
    return (self_assessed or 0) + (reserve or 0)


def _gates(profile: TaxProfileVersion, rule: TaxRule | None, day: date, claim_exemption: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if profile.withholding_method is WithholdingMethod.UNVERIFIED:
        reasons.append("withholding_unverified")
    if profile.shopee_status != "confirmed":
        reasons.append("account_kind_unconfirmed")
    if rule is None or profile.legal_rule_id != rule.rule_id or not rule.covers(day):
        reasons.append("rule_unverified")
    elif rule.status is not RuleStatus.VERIFIED:
        reasons.append("rule_unverified")
    if claim_exemption:
        reasons.append("exemption_rejected")
    if profile.evidence_source.strip() == "" or profile.evidence_confirmed_on is None:
        reasons.append("missing_evidence")
    reasons.append(PAYABLE_BLOCK)
    return tuple(reasons)


def assess_conversion(
    profile: TaxProfileVersion,
    rule: TaxRule | None,
    day: date,
    gross_vnd: int,
    actual_fee_vnd: int | None,
    *,
    fee_already_in_gross: bool = False,
    withheld_already_in_gross: bool = False,
    reserve_already_in_gross: bool = False,
    other_cost_vnd: int = 0,
    shopee_paid_vnd: int | None = None,
    claim_exemption: bool = False,
    share_bps: int = 7_000,
    committed_cashback_vnd: int | None = None,
    paid_cashback_vnd: int | None = None,
    withheld_vnd: int | None = None,
    reserve_vnd: int | None = None,
    self_assessed_vnd: int | None = None,
) -> Assessment:
    """Ba loại hình đi qua cùng một hàm. Nhãn tài khoản không tạo mức thuế."""
    reasons = list(_gates(profile, rule, day, claim_exemption))
    if claim_exemption:
        reasons.append("revenue_does_not_grant_exemption")
    withheld = profile.tax_withheld_vnd if withheld_vnd is None else withheld_vnd
    self_assessed = profile.self_assessed_tax_due_vnd if self_assessed_vnd is None else self_assessed_vnd
    reserve = profile.tax_reserve_vnd if reserve_vnd is None else reserve_vnd
    unpaid = _unpaid(self_assessed, reserve)
    distributable, cashback, missing = settle_commission(
        gross_vnd,
        actual_fee_vnd,
        withheld,
        unpaid,
        other_cost_vnd,
        fee_already_in_gross=fee_already_in_gross,
        withheld_already_in_gross=withheld_already_in_gross,
        reserve_already_in_gross=reserve_already_in_gross,
        share_bps=share_bps,
    )
    reasons.extend(missing)
    if shopee_paid_vnd is None:
        reasons.append("shopee_not_paid")
    elif distributable is not None and shopee_paid_vnd < distributable:
        reasons.append("paid_amount_below_distributable")
    return Assessment(
        profile.version_id,
        distributable,
        cashback,
        authorize_payable(None),
        None,
        tuple(dict.fromkeys(reasons)),
        committed_cashback_vnd,
        paid_cashback_vnd,
    )


def revalue_order(
    order: CashOrder,
    history: PolicyHistory,
    gross_vnd: int,
    actual_fee_vnd: int | None,
    **kwargs,
) -> Assessment:
    """Điều chỉnh đơn cũ theo đúng phiên bản đã gắn, không theo hồ sơ hiện tại."""
    version = next((item for item in history.versions if item.version_id == order.profile_version_id), None)
    if version is None:
        raise CalculationError("unknown_version")
    if order.paid_cashback_vnd is not None or order.committed_cashback_vnd is not None:
        kept = assess_conversion(
            version,
            kwargs.get("rule"),
            order.order_date,
            order.gross_vnd,
            actual_fee_vnd,
            committed_cashback_vnd=order.committed_cashback_vnd,
            paid_cashback_vnd=order.paid_cashback_vnd,
            **{key: value for key, value in kwargs.items() if key != "rule"},
        )
        return replace(
            kept,
            committed_cashback_vnd=order.committed_cashback_vnd,
            paid_cashback_vnd=order.paid_cashback_vnd,
        )
    return assess_conversion(
        version,
        kwargs.get("rule"),
        order.order_date,
        gross_vnd,
        actual_fee_vnd,
        **{key: value for key, value in kwargs.items() if key != "rule"},
    )


def fund_after_shopee(shopee_paid_vnd: int | None, cashback_vnd: int | None) -> int | None:
    """Tiền Shopee chưa về thì không có quỹ."""
    if shopee_paid_vnd is None or cashback_vnd is None:
        return None
    ledger = DryRunLedger(shopee_paid_vnd)
    return ledger.propose("cashback", cashback_vnd)
