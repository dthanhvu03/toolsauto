"""Mức admin áp dụng cho báo giá V1.2: phí, thuế dự phòng (ADR-047) và tỷ lệ chia (ADR-048).

reserve_policies và share_policies chỉ thêm dòng. Mỗi bảng lấy dòng mới nhất đã tới effective_at.
Chưa có dòng nào thì dùng mặc định cấu hình (.env). Loại hình chỉ là nhãn, không chọn thuế suất.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cashback_bot.pricing import V11, V12, PolicyResolution

SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "005_reserve_policies.sql"
SHARE_SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "006_share_policies.sql"
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_RESERVE_BPS = 5_000
MAX_AHEAD = timedelta(days=365)
ACCOUNT_KINDS = {
    "PERSONAL": "Cá nhân",
    "INDIVIDUAL_BUSINESS": "Cá nhân kinh doanh",
    "HOUSEHOLD_BUSINESS": "Hộ kinh doanh",
}
KIND_CODES = {"P": "PERSONAL", "I": "INDIVIDUAL_BUSINESS", "H": "HOUSEHOLD_BUSINESS"}
OPEN_STEPS = ("kind", "fee", "tax", "when", "preview")
SHARE_OPEN_STEPS = ("share", "when", "preview")
_WHEN = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?:\s+(\d{1,2})[:h](\d{2}))?$")


@dataclass(frozen=True)
class AppliedReserve:
    fee_bps: int
    tax_reserve_bps: int
    policy_id: int | None = None
    account_kind: str | None = None
    effective_at: str | None = None


def stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vn_time(stamp_text: str) -> str:
    moment = datetime.strptime(stamp_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return moment.astimezone(ICT).strftime("%H:%M %d/%m/%Y")


def _from_row(row: sqlite3.Row) -> AppliedReserve:
    return AppliedReserve(
        fee_bps=int(row["fee_bps"]),
        tax_reserve_bps=int(row["tax_reserve_bps"]),
        policy_id=int(row["id"]),
        account_kind=str(row["account_kind"]),
        effective_at=str(row["effective_at"]),
    )


def active_reserve(conn: sqlite3.Connection, now: datetime, fee_default: int, tax_default: int) -> AppliedReserve:
    row = conn.execute(
        """
        SELECT * FROM reserve_policies
        WHERE effective_at <= ?
        ORDER BY effective_at DESC, id DESC
        LIMIT 1
        """,
        (stamp(now),),
    ).fetchone()
    if row is None:
        return AppliedReserve(fee_default, tax_default)
    return _from_row(row)


def upcoming_reserves(conn: sqlite3.Connection, now: datetime) -> list[AppliedReserve]:
    rows = conn.execute(
        "SELECT * FROM reserve_policies WHERE effective_at > ? ORDER BY effective_at, id",
        (stamp(now),),
    ).fetchall()
    return [_from_row(row) for row in rows]


@dataclass(frozen=True)
class AppliedShare:
    """Tỷ lệ chia khách đang nhận (ADR-048). policy_id None: mặc định cấu hình."""

    share_bps: int
    policy_id: int | None = None
    effective_at: str | None = None


def active_share(conn: sqlite3.Connection, now: datetime, default_bps: int) -> AppliedShare:
    row = conn.execute(
        """
        SELECT * FROM share_policies
        WHERE effective_at <= ?
        ORDER BY effective_at DESC, id DESC
        LIMIT 1
        """,
        (stamp(now),),
    ).fetchone()
    if row is None:
        return AppliedShare(default_bps)
    return AppliedShare(int(row["share_bps"]), int(row["id"]), str(row["effective_at"]))


def upcoming_shares(conn: sqlite3.Connection, now: datetime) -> list[AppliedShare]:
    rows = conn.execute(
        "SELECT * FROM share_policies WHERE effective_at > ? ORDER BY effective_at, id",
        (stamp(now),),
    ).fetchall()
    return [AppliedShare(int(row["share_bps"]), int(row["id"]), str(row["effective_at"])) for row in rows]


def resolve_policy(
    conn: sqlite3.Connection,
    now: datetime,
    *,
    v12: bool,
    default_share_bps: int,
    fee_default: int,
    tax_default: int,
    other_reserve_vnd: int = 0,
    rounding_unit: int = 1,
) -> PolicyResolution:
    """Chọn chính sách cho link báo giá lúc `now` (PLAN-076). Đọc hai bảng trong một transaction đọc.

    V1.1 chia theo CASHBACK_RATE_PERCENT, không đọc share_policies; phí, thuế chỉ để tính phần admin chịu.
    """
    started = not conn.in_transaction
    if started:
        conn.execute("BEGIN")
    try:
        reserve = active_reserve(conn, now, fee_default, tax_default)
        share = active_share(conn, now, default_share_bps) if v12 else AppliedShare(default_share_bps)
    finally:
        if started:
            conn.commit()
    return PolicyResolution(
        pricing_version=V12 if v12 else V11,
        share_bps=share.share_bps,
        fee_bps=reserve.fee_bps,
        tax_reserve_bps=reserve.tax_reserve_bps,
        other_reserve_vnd=other_reserve_vnd if v12 else 0,
        rounding_unit=rounding_unit if v12 else 1,
        share_policy_id=share.policy_id,
        reserve_policy_id=reserve.policy_id,
        resolved_at=stamp(now),
    )


def effective_from(requested: str | None, now: datetime) -> str:
    """Mốc ghi vào bảng chính sách. Không bao giờ sớm hơn lúc bấm Áp dụng: không hồi tố (PLAN-076)."""
    current = stamp(now)
    if requested is None or requested < current:
        return current
    return requested


def parse_when(text: str, now: datetime) -> tuple[datetime | None, str | None]:
    """`dd/mm`, `dd/mm/yyyy`, kèm `HH:MM` tùy chọn, giờ Việt Nam. Trả (mốc UTC, lỗi)."""
    matched = _WHEN.fullmatch((text or "").strip())
    if matched is None:
        return None, None
    day, month, year, hour, minute = matched.groups()
    local_now = now.astimezone(ICT)
    try:
        moment = datetime(
            int(year or local_now.year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            tzinfo=ICT,
        ).astimezone(timezone.utc)
    except ValueError:
        return None, "Ngày giờ không hợp lệ."
    if moment < now - timedelta(minutes=1):
        return None, "Mốc này đã qua. Chọn Ngay bây giờ hoặc một mốc sắp tới."
    if moment > now + MAX_AHEAD:
        return None, "Mốc quá xa. Tối đa 365 ngày tới."
    return moment, None


def next_midnight(now: datetime) -> datetime:
    local = now.astimezone(ICT)
    midnight = datetime(local.year, local.month, local.day, tzinfo=ICT) + timedelta(days=1)
    return midnight.astimezone(timezone.utc)


def recent_commissions(conn: sqlite3.Connection, limit: int = 200) -> list[int]:
    """Hoa hồng ước tính của link gần nhất, để mô phỏng tác động. Bảng chưa có thì rỗng."""
    try:
        rows = conn.execute(
            """
            SELECT estimated_commission FROM link_requests
            WHERE link_status = 'created' AND estimated_commission IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [int(row[0]) for row in rows]
