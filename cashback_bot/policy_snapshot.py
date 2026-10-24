"""Snapshot chính sách của từng link (PLAN-076, ADR-053).

Link mới: chính sách được chọn một lần lúc báo giá, ghi cùng transaction với link.
Link cũ chưa có snapshot: dựng lại từ nhãn và số đã lưu. Chỉ ghi `backfilled` khi tính lại
ra đúng số tiền đã báo cho khách; không thì ghi `unresolved` và để trống chính sách.
Bảng chỉ thêm. Module này không đổi link_requests, sổ ví hay trạng thái hoa hồng.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from cashback_bot.calculator import POLICY_ID, CalculationError
from cashback_bot.db import insert_snapshot
from cashback_bot.pricing import ROUNDING_RULE, V11, V12, CashbackQuote, PolicyResolution, cashback_for

SCHEMA_VERSION = 1
CAPTURED = "captured"
BACKFILLED = "backfilled"
UNRESOLVED = "unresolved"
QUOTE_SOURCE = "product_data"
_V12_LABEL = re.compile(rf"^{re.escape(POLICY_ID)}(?:\+r(\d+))?(?:\+s(\d+))?$")


@dataclass(frozen=True)
class PolicyDefaults:
    """Mặc định cấu hình (.env) khi chưa có dòng reserve_policies / share_policies."""

    share_bps: int
    fee_bps: int
    tax_reserve_bps: int
    other_reserve_vnd: int = 0
    rounding_unit: int = 1


@dataclass(frozen=True)
class LinkPolicy:
    """Snapshot đọc từ DB. policy None: unresolved."""

    provenance: str
    label: str
    policy: PolicyResolution | None
    quote_cashback_vnd: int | None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(
    policy: PolicyResolution,
    quote: CashbackQuote | None,
    *,
    provenance: str = CAPTURED,
    note: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Dòng link_policy_snapshots, chưa có link_id."""
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": provenance,
        "policy_label": policy.label,
        "pricing_version": policy.pricing_version,
        "formula": policy.formula,
        "rounding": ROUNDING_RULE,
        "share_bps": policy.share_bps,
        "share_policy_id": policy.share_policy_id,
        "reserve_policy_id": policy.reserve_policy_id,
        "fee_bps": policy.fee_bps,
        "tax_reserve_bps": policy.tax_reserve_bps,
        "other_reserve_vnd": policy.other_reserve_vnd,
        "rounding_unit": policy.rounding_unit,
        "resolved_at": policy.resolved_at,
        "quote_commission_vnd": None if quote is None else quote.commission_vnd,
        "quote_cashback_vnd": None if quote is None else quote.cashback_vnd,
        "quote_source": QUOTE_SOURCE,
        "note": note,
        "created_at": created_at or _now(),
    }


def _unresolved(label: str, row: sqlite3.Row, note: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": UNRESOLVED,
        "policy_label": label,
        "quote_commission_vnd": row["estimated_commission"],
        "quote_cashback_vnd": row["estimated_cashback"],
        "quote_source": QUOTE_SOURCE,
        "note": note,
        "created_at": _now(),
    }


def load(conn: sqlite3.Connection, link_id: int) -> LinkPolicy | None:
    row = conn.execute("SELECT * FROM link_policy_snapshots WHERE link_id = ?", (link_id,)).fetchone()
    return None if row is None else _from_record(dict(row))


def _policy_row(conn: sqlite3.Connection, table: str, policy_id: int) -> sqlite3.Row | None:
    try:
        return conn.execute(f"SELECT * FROM {table} WHERE id = ?", (policy_id,)).fetchone()
    except sqlite3.OperationalError:
        return None


def _reserve_at(conn: sqlite3.Connection, created_at: str, defaults: PolicyDefaults) -> tuple[int, int, int | None]:
    """Mức dự phòng có hiệu lực lúc link tạo. Chỉ dùng cho phần admin chịu của link V1.1."""
    try:
        row = conn.execute(
            "SELECT * FROM reserve_policies WHERE effective_at <= ? ORDER BY effective_at DESC, id DESC LIMIT 1",
            (created_at,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row is None:
        return defaults.fee_bps, defaults.tax_reserve_bps, None
    return int(row["fee_bps"]), int(row["tax_reserve_bps"]), int(row["id"])


def reconstruct(conn: sqlite3.Connection, link: sqlite3.Row, defaults: PolicyDefaults) -> tuple[dict, str]:
    """Dựng snapshot cho link cũ. Trả (dòng snapshot, lý do). Không khớp số đã báo thì unresolved."""
    label_raw = link["estimate_policy"]
    rate = link["cashback_rate_percent"]
    commission = link["estimated_commission"]
    quoted = link["estimated_cashback"]
    created_at = str(link["created_at"])
    label = str(label_raw) if label_raw else (f"v1.1:{rate}" if rate is not None else "v1.1:?")
    if commission is None or quoted is None:
        return _unresolved(label, link, "thiếu hoa hồng hoặc số đã báo"), "missing_quote"
    try:
        if not label_raw:
            if rate is None:
                return _unresolved(label, link, "link V1.1 không lưu tỷ lệ"), "missing_rate"
            fee, tax, reserve_id = _reserve_at(conn, created_at, defaults)
            policy = PolicyResolution(
                pricing_version=V11,
                share_bps=int(rate) * 100,
                fee_bps=fee,
                tax_reserve_bps=tax,
                reserve_policy_id=reserve_id,
                resolved_at=created_at,
            )
        else:
            matched = _V12_LABEL.fullmatch(str(label_raw))
            if matched is None:
                return _unresolved(label, link, "nhãn chính sách không nhận ra"), "unknown_label"
            reserve_id, share_id = matched.groups()
            if reserve_id is not None:
                reserve = _policy_row(conn, "reserve_policies", int(reserve_id))
                if reserve is None or str(reserve["effective_at"]) > created_at:
                    return _unresolved(label, link, f"không thấy mức dự phòng r{reserve_id} hợp lệ"), "reserve_missing"
                fee, tax = int(reserve["fee_bps"]), int(reserve["tax_reserve_bps"])
            else:
                fee, tax = defaults.fee_bps, defaults.tax_reserve_bps
            if share_id is not None:
                share = _policy_row(conn, "share_policies", int(share_id))
                if share is None or str(share["effective_at"]) > created_at:
                    return _unresolved(label, link, f"không thấy tỷ lệ chia s{share_id} hợp lệ"), "share_missing"
                share_bps = int(share["share_bps"])
                if rate is not None and share_bps != int(rate) * 100:
                    return _unresolved(label, link, "tỷ lệ trên link khác tỷ lệ chia đã áp dụng"), "share_conflict"
            elif rate is not None:
                share_bps = int(rate) * 100
            else:
                return _unresolved(label, link, "link V1.2 không lưu tỷ lệ chia"), "missing_rate"
            policy = PolicyResolution(
                pricing_version=V12,
                share_bps=share_bps,
                fee_bps=fee,
                tax_reserve_bps=tax,
                other_reserve_vnd=defaults.other_reserve_vnd,
                rounding_unit=defaults.rounding_unit,
                share_policy_id=None if share_id is None else int(share_id),
                reserve_policy_id=None if reserve_id is None else int(reserve_id),
                resolved_at=created_at,
            )
        quote = cashback_for(int(commission), policy)
    except (CalculationError, ValueError):
        return _unresolved(label, link, "giá trị chính sách không hợp lệ"), "invalid_policy"
    if quote.cashback_vnd != int(quoted) or policy.label != label:
        return _unresolved(label, link, "tính lại không ra số đã báo"), "quote_mismatch"
    return record(policy, quote, provenance=BACKFILLED, note="dựng lại từ link cũ, khớp số đã báo"), "ok"


def for_link(conn: sqlite3.Connection, link_id: int, defaults: PolicyDefaults) -> LinkPolicy | None:
    """Snapshot của link để tính tiền. Chỉ đọc: link cũ chưa có dòng thì dựng tạm trong bộ nhớ.

    Không ghi ở đây vì hàm chạy giữa transaction ghi sổ ví; dòng snapshot được ghi lúc khởi động (backfill).
    None: không có link đã tạo với id này.
    """
    found = load(conn, link_id)
    if found is not None:
        return found
    link = conn.execute(
        "SELECT * FROM link_requests WHERE id = ? AND link_status = 'created'", (link_id,)
    ).fetchone()
    if link is None:
        return None
    snapshot, _reason = reconstruct(conn, _with_policy_column(conn, link), defaults)
    return _from_record(snapshot)


def _from_record(snapshot: dict) -> LinkPolicy:
    policy = None
    if snapshot["provenance"] != UNRESOLVED:
        policy = PolicyResolution(
            pricing_version=snapshot["pricing_version"],
            share_bps=snapshot["share_bps"],
            fee_bps=snapshot["fee_bps"],
            tax_reserve_bps=snapshot["tax_reserve_bps"],
            other_reserve_vnd=snapshot["other_reserve_vnd"],
            rounding_unit=snapshot["rounding_unit"],
            share_policy_id=snapshot["share_policy_id"],
            reserve_policy_id=snapshot["reserve_policy_id"],
            resolved_at=snapshot["resolved_at"],
        )
    return LinkPolicy(snapshot["provenance"], snapshot["policy_label"], policy, snapshot.get("quote_cashback_vnd"))


def backfill(conn: sqlite3.Connection, defaults: PolicyDefaults) -> dict[str, int]:
    """Ghi snapshot cho mọi link đã tạo chưa có snapshot. Chạy lại không ghi thêm."""
    counts = {BACKFILLED: 0, UNRESOLVED: 0}
    rows = conn.execute(
        """
        SELECT l.* FROM link_requests l
        LEFT JOIN link_policy_snapshots s ON s.link_id = l.id
        WHERE l.link_status = 'created' AND s.link_id IS NULL
        ORDER BY l.id
        """
    ).fetchall()
    for link in rows:
        snapshot, _reason = reconstruct(conn, _with_policy_column(conn, link), defaults)
        insert_snapshot(conn, int(link["id"]), snapshot)
        counts[snapshot["provenance"]] += 1
    return counts


def coverage(conn: sqlite3.Connection) -> dict[str, int]:
    """Số link đã tạo theo loại snapshot; `missing`: chưa có dòng nào."""
    result = {CAPTURED: 0, BACKFILLED: 0, UNRESOLVED: 0, "missing": 0}
    for provenance, count in conn.execute(
        """
        SELECT COALESCE(s.provenance, 'missing'), COUNT(*)
        FROM link_requests l LEFT JOIN link_policy_snapshots s ON s.link_id = l.id
        WHERE l.link_status = 'created'
        GROUP BY 1
        """
    ):
        result[str(provenance)] = int(count)
    return result


def _with_policy_column(conn: sqlite3.Connection, link: sqlite3.Row) -> dict:
    """DB chưa chạy migration 001 thì không có cột estimate_policy: mọi link là V1.1."""
    data = dict(link)
    data.setdefault("estimate_policy", None)
    return data
