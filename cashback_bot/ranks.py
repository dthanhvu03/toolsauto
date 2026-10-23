"""Hạng Đồng 60%, Bạc 65%, Vàng 70%. Chưa kích hoạt.

Module này chỉ trả tỷ lệ và snapshot. Số tiền do pricing.py tính.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

POLICY_ID = "rank-v1"
POLICY_VERSION = 1
LEGACY_POLICY_ID = "v1.1-gross-70"
MEMBERSHIP_CUTOVER = False

# Bộ thử. Chưa được duyệt. Không phải quyết định lên hạng.
# ⚠ Chưa có phân bố đơn của bot. Mốc tiền chỉ để chặn đơn rất nhỏ.
THRESHOLD_SETS = (
    {
        "name": "de",
        "silver_orders": 2,
        "gold_orders": 6,
        "silver_paid_vnd": 30_000,
        "gold_paid_vnd": 90_000,
        "approved": False,
        "hold_rule": "chua_duyet",
        "cancel_rule": "don_huy_khong_tinh",
        "clawback_rule": "thu_hoi_khong_duoc_am_quy",
    },
    {
        "name": "can_bang",
        "silver_orders": 4,
        "gold_orders": 8,
        "silver_paid_vnd": 80_000,
        "gold_paid_vnd": 250_000,
        "approved": False,
        "hold_rule": "chua_duyet",
        "cancel_rule": "don_huy_khong_tinh",
        "clawback_rule": "thu_hoi_khong_duoc_am_quy",
    },
    {
        "name": "than_trong",
        "silver_orders": 8,
        "gold_orders": 16,
        "silver_paid_vnd": 200_000,
        "gold_paid_vnd": 700_000,
        "approved": False,
        "hold_rule": "chua_duyet",
        "cancel_rule": "don_huy_khong_tinh",
        "clawback_rule": "thu_hoi_khong_duoc_am_quy",
    },
)


class RankInputError(ValueError):
    """Policy hoặc sự kiện không dùng được."""


def _bps(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7_000:
        raise RankInputError(name)
    return value


@dataclass(frozen=True)
class RankTier:
    code: str
    label: str
    share_bps: int

    def __post_init__(self) -> None:
        _bps(self.share_bps, self.code)


V1_TIERS = (
    RankTier("BRONZE", "Đồng", 6_000),
    RankTier("SILVER", "Bạc", 6_500),
    RankTier("GOLD", "Vàng", 7_000),
)
TIER_BPS = {tier.code: tier.share_bps for tier in V1_TIERS}


@dataclass(frozen=True)
class MembershipPolicy:
    policy_id: str
    version: int
    effective_at: datetime | None
    status: str
    bronze_bps: int = 6_000
    silver_bps: int = 6_500
    gold_bps: int = 7_000
    promotion_rule_version: str | None = None
    reason: str = "dinh_huong_da_chot_chua_ngay_hieu_luc"
    source: str = "quyet_dinh_chu_bot_2026-10-23"

    def __post_init__(self) -> None:
        shares = (_bps(self.bronze_bps, "bronze"), _bps(self.silver_bps, "silver"), _bps(self.gold_bps, "gold"))
        if not shares[0] <= shares[1] <= shares[2]:
            raise RankInputError("tier_order")
        if self.status not in {"draft", "active", "retired"}:
            raise RankInputError("status")
        if self.version < 1:
            raise RankInputError("version")
        if self.status == "active" and self.effective_at is None:
            raise RankInputError("effective_at")
        if self.status == "active" and not self.promotion_rule_version:
            raise RankInputError("promotion_rule")
        if not self.reason.strip() or not self.source.strip():
            raise RankInputError("audit")


def v1_policy() -> MembershipPolicy:
    return MembershipPolicy(POLICY_ID, POLICY_VERSION, None, "draft")


def tier_share_bps(code: str) -> int:
    if code not in TIER_BPS:
        raise RankInputError("rank")
    return TIER_BPS[code]


def share_for_new_link(policy: MembershipPolicy, rank_code: str) -> int | None:
    """Cửa production. Draft hoặc chưa cutover thì không trả tỷ lệ mới."""
    tier_share_bps(rank_code)
    if not MEMBERSHIP_CUTOVER or policy.status != "active":
        return None
    if policy.policy_id != POLICY_ID or policy.version != POLICY_VERSION:
        return None
    return TIER_BPS[rank_code]


@dataclass(frozen=True)
class RankChange:
    user_key: str
    at: str
    from_code: str | None
    to_code: str
    reason: str
    policy_id: str
    policy_version: int
    share_bps: int


@dataclass(frozen=True)
class RankHistory:
    changes: tuple[RankChange, ...] = ()

    def append(self, change: RankChange) -> "RankHistory":
        _bps(change.share_bps, "share")
        if not change.reason.strip():
            raise RankInputError("reason")
        return RankHistory(self.changes + (change,))


@dataclass(frozen=True)
class IssuedLinkSnapshot:
    """Quyền lợi đã gắn vào link. benefit_valid_until trống vì chưa có số ngày được duyệt."""

    link_id: int | None
    sub_id: str | None
    owner_id: int | None
    rank_code: str | None
    share_bps: int | None
    cashback_policy_id: str | None
    membership_policy_id: str | None
    membership_policy_version: int | None
    estimated_commission_vnd: int | None
    displayed_cashback_vnd: int | None
    estimate_source: str | None
    created_at: str | None
    policy_effective_at: str | None
    benefit_valid_until: None = None
    tracking_url_expiry: None = None
    review_status: str = "needs_owner_review"


def freeze_stored_link(
    *,
    link_id: int | None,
    sub_id: str | None,
    owner_id: int | None,
    rate_percent: int | None,
    estimated_commission_vnd: int | None,
    displayed_cashback_vnd: int | None,
    created_at: str | None,
    estimate_policy: str | None = None,
) -> IssuedLinkSnapshot:
    """Không điền số còn thiếu và không tính lại số đã lưu."""
    base = dict(
        link_id=link_id,
        sub_id=sub_id,
        owner_id=owner_id,
        estimated_commission_vnd=estimated_commission_vnd,
        displayed_cashback_vnd=displayed_cashback_vnd,
        created_at=created_at,
        benefit_valid_until=None,
        tracking_url_expiry=None,
    )
    complete = (
        bool(sub_id)
        and sub_id != "----"
        and owner_id is not None
        and rate_percent is not None
        and displayed_cashback_vnd is not None
        and created_at is not None
    )
    if not complete:
        return IssuedLinkSnapshot(
            **base,
            rank_code=None,
            share_bps=None,
            cashback_policy_id=estimate_policy,
            membership_policy_id=None,
            membership_policy_version=None,
            estimate_source=None,
            policy_effective_at=None,
            review_status="needs_owner_review",
        )
    if estimate_policy:
        return IssuedLinkSnapshot(
            **base,
            rank_code=None,
            share_bps=rate_percent * 100,
            cashback_policy_id=estimate_policy,
            membership_policy_id=None,
            membership_policy_version=None,
            estimate_source="stored_estimate_policy",
            policy_effective_at=None,
            review_status="stored",
        )
    return IssuedLinkSnapshot(
        **base,
        rank_code=None,
        share_bps=rate_percent * 100,
        cashback_policy_id=f"v1.1-gross-{rate_percent}",
        membership_policy_id=None,
        membership_policy_version=None,
        estimate_source="stored_gross_rate",
        policy_effective_at=None,
        review_status="stored",
    )


def replay_share_bps(snapshot: IssuedLinkSnapshot, current_rank_bps: int | None) -> int | None:
    """Đơn và lần bấm sau dùng tỷ lệ đã gắn. Hạng mới không ghi đè."""
    if current_rank_bps is not None:
        _bps(current_rank_bps, "current")
    if snapshot.share_bps is None or snapshot.review_status == "needs_owner_review":
        return None
    return snapshot.share_bps


def benefit_term_status(snapshot: IssuedLinkSnapshot, on_day: date) -> str:
    """Chưa có số ngày được duyệt. Không suy ra còn hiệu lực mãi và cũng không cắt quyền lợi."""
    del on_day
    if snapshot.benefit_valid_until is None:
        return "term_not_approved"
    return "term_set"


@dataclass(frozen=True)
class ProgressEvent:
    event_key: str
    kind: str
    sub_id: str
    owner_user_id: int
    paid_commission_vnd: int = 0
    shopee_paid: bool = False
    origin_key: str | None = None


@dataclass
class ProgressBook:
    confirmed_orders: int = 0
    paid_commission_vnd: int = 0
    cancelled_orders: int = 0
    ignored_clicks: int = 0
    ignored_links: int = 0
    _seen: set[str] = field(default_factory=set)
    _counted: dict[str, int] = field(default_factory=dict)

    def apply(self, event: ProgressEvent) -> str:
        if not event.event_key.strip():
            raise RankInputError("event_key")
        if event.kind == "confirmed" and not event.shopee_paid:
            return "ignored"
        if event.event_key in self._seen:
            return "duplicate"
        if event.kind == "reversed":
            origin = event.origin_key or ""
            already = self._counted.get(origin)
            if already is None:
                return "ignored"
            if event.paid_commission_vnd > already:
                return "needs_review"
            self._seen.add(event.event_key)
            self._counted[origin] = already - event.paid_commission_vnd
            self.paid_commission_vnd -= event.paid_commission_vnd
            return "reversed"
        self._seen.add(event.event_key)
        if event.kind == "click":
            self.ignored_clicks += 1
            return "ignored"
        if event.kind == "link":
            self.ignored_links += 1
            return "ignored"
        if event.kind == "cancelled":
            self.cancelled_orders += 1
            return "ignored"
        if event.kind != "confirmed":
            return "ignored"
        self.confirmed_orders += 1
        self.paid_commission_vnd += event.paid_commission_vnd
        self._counted[event.event_key] = event.paid_commission_vnd
        return "counted"


def consider_promotion(book: ProgressBook, policy: MembershipPolicy, thresholds: dict) -> RankChange | None:
    """Không bộ ngưỡng nào được duyệt. Không thăng hạng."""
    del book
    if policy.status != "active" or not policy.promotion_rule_version or not thresholds.get("approved"):
        return None
    return None


def cashback_owner(link_owner_id: int, link_sub_id: str, conversion_sub_id: str, forwarded_to_id: int | None) -> int | None:
    if not link_sub_id or link_sub_id != conversion_sub_id or link_sub_id == "----":
        return None
    del forwarded_to_id
    return link_owner_id


SNAPSHOT_COLUMNS = (
    ("membership_policy_id", "TEXT"),
    ("membership_rank", "TEXT"),
    ("share_bps", "INTEGER"),
    ("benefit_review", "TEXT"),
)


def apply_snapshot_columns(conn: sqlite3.Connection) -> list[str]:
    """Chỉ thêm cột trên database thử. Không cập nhật số cashback đã lưu."""
    added: list[str] = []
    have = {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}
    for name, ddl in SNAPSHOT_COLUMNS:
        if name in have:
            continue
        conn.execute(f"ALTER TABLE link_requests ADD COLUMN {name} {ddl}")
        added.append(name)
    conn.commit()
    return added
