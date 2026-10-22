"""SQLite database prototype — hoàn toàn tách biệt khỏi production.

Database file: experiments/shopee_conversion_v2/data/conversion_poc.sqlite

KHÔNG ĐƯỢC dùng production cashback.sqlite để ghi. Module đối chiếu chỉ
mở cashback.sqlite bằng URI mode=ro.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    report_type TEXT NOT NULL,
    date_range_start TEXT,
    date_range_end TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    total_raw INTEGER DEFAULT 0,
    total_valid INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,
    total_new INTEGER DEFAULT 0,
    total_updated INTEGER DEFAULT 0,
    total_unchanged INTEGER DEFAULT 0,
    error_details TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'shopee_affiliate',
    conversion_id TEXT NOT NULL,
    checkout_id TEXT,
    order_id TEXT,
    order_sn TEXT,
    affiliate_transaction_id TEXT,
    sub_id TEXT,
    click_id TEXT,
    conversion_status_raw TEXT,
    checkout_status_raw TEXT,
    order_status_raw TEXT,
    internal_status TEXT NOT NULL DEFAULT 'unknown',
    gross_commission REAL,
    capped_commission REAL,
    estimated_total_commission REAL,
    affiliate_net_commission REAL,
    item_commission REAL,
    item_id TEXT,
    shop_id TEXT,
    item_name TEXT,
    item_price REAL,
    purchase_time TEXT,
    click_time TEXT,
    source_updated_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_sync_run_id INTEGER,
    extra_fields_json TEXT,
    UNIQUE(source, conversion_id)
);

CREATE TABLE IF NOT EXISTS conversion_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_db_id INTEGER NOT NULL,
    item_id TEXT,
    item_name TEXT,
    item_price REAL,
    item_commission REAL,
    quantity INTEGER DEFAULT 1,
    FOREIGN KEY (conversion_db_id) REFERENCES conversions(id)
);

CREATE TABLE IF NOT EXISTS conversion_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_db_id INTEGER NOT NULL,
    source_conversion_id TEXT NOT NULL,
    old_conversion_status TEXT,
    new_conversion_status TEXT,
    old_order_status TEXT,
    new_order_status TEXT,
    old_internal_status TEXT,
    new_internal_status TEXT,
    old_gross_commission REAL,
    new_gross_commission REAL,
    old_affiliate_net_commission REAL,
    new_affiliate_net_commission REAL,
    old_capped_commission REAL,
    new_capped_commission REAL,
    change_type TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    sync_run_id INTEGER,
    FOREIGN KEY (conversion_db_id) REFERENCES conversions(id)
);

CREATE TABLE IF NOT EXISTS attribution_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_db_id INTEGER NOT NULL,
    source_conversion_id TEXT NOT NULL,
    sub_id TEXT,
    telegram_user_id INTEGER,
    match_status TEXT NOT NULL,
    match_method TEXT NOT NULL,
    match_notes TEXT,
    matched_at TEXT NOT NULL,
    sync_run_id INTEGER,
    FOREIGN KEY (conversion_db_id) REFERENCES conversions(id)
);

CREATE INDEX IF NOT EXISTS idx_conversions_sub_id ON conversions(sub_id);
CREATE INDEX IF NOT EXISTS idx_conversions_conversion_id ON conversions(conversion_id);
CREATE INDEX IF NOT EXISTS idx_conversions_order_id ON conversions(order_id);
CREATE INDEX IF NOT EXISTS idx_attribution_sub_id ON attribution_matches(sub_id);
CREATE INDEX IF NOT EXISTS idx_attribution_status ON attribution_matches(match_status);
CREATE INDEX IF NOT EXISTS idx_history_conversion ON conversion_status_history(conversion_db_id);

CREATE TABLE IF NOT EXISTS click_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    evidence TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    sub_id TEXT,
    click_time TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(source, observation_key)
);

CREATE TABLE IF NOT EXISTS conversion_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    quarantine_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    checkout_id TEXT,
    order_id TEXT,
    affiliate_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(source, quarantine_key)
);
"""

SCHEMA_VERSION = 1

_STATUS_FIELDS = {
    "conversion_status_raw",
    "checkout_status_raw",
    "order_status_raw",
}
_COMMISSION_FIELDS = {
    "gross_commission",
    "capped_commission",
    "estimated_total_commission",
    "affiliate_net_commission",
    "item_commission",
}
_COMPARISONS = (
    ("conversion_status_raw", "conversion_status"),
    ("checkout_status_raw", "checkout_status"),
    ("order_status_raw", "order_status"),
    ("gross_commission", "gross_commission"),
    ("capped_commission", "capped_commission"),
    ("estimated_total_commission", "estimated_total_commission"),
    ("affiliate_net_commission", "affiliate_net_commission"),
    ("item_commission", "item_commission"),
    ("sub_id", "sub_id"),
    ("click_id", "click_id"),
    ("purchase_time", "purchase_time"),
    ("click_time", "click_time"),
    ("order_id", "order_id"),
    ("item_id", "item_id"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _detect_changes(existing: sqlite3.Row, new_record: dict[str, Any]) -> list[str]:
    """So sánh record cũ và mới, trả về danh sách cột thay đổi."""
    changes: list[str] = []
    for db_col, rec_key in _COMPARISONS:
        old_val = existing[db_col]
        new_val = new_record.get(rec_key)
        if old_val == new_val:
            continue
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            if abs(old_val - new_val) < 0.001:
                continue
        changes.append(db_col)
    return changes


def _classify_change(changes: list[str]) -> str:
    """Phân loại thay đổi: status_change, commission_change, hoặc both."""
    has_status = bool(set(changes) & _STATUS_FIELDS)
    has_commission = bool(set(changes) & _COMMISSION_FIELDS)
    if has_status and has_commission:
        return "both"
    if has_status:
        return "status_change"
    if has_commission:
        return "commission_change"
    return "data_change"


class ConversionDatabase:
    """Prototype database cho Conversion Sync V2."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def migrate(self) -> None:
        """Tạo hoặc cập nhật schema."""
        conn = self.connect()
        try:
            conn.executescript(SCHEMA_SQL)
            existing = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            if existing != SCHEMA_VERSION:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _utc_now()),
                )
            conn.commit()
        finally:
            conn.close()

    def start_sync_run(
        self,
        source: str,
        report_type: str,
        date_range_start: str | None = None,
        date_range_end: str | None = None,
    ) -> int:
        """Bắt đầu một lần sync, trả về run_id."""
        conn = self.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs
                    (source, report_type, date_range_start, date_range_end, status, started_at)
                VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (source, report_type, date_range_start, date_range_end, _utc_now()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def complete_sync_run(self, run_id: int, stats: dict[str, Any], errors: list[str] | None = None) -> None:
        """Đánh dấu sync run hoàn thành."""
        now = _utc_now()
        conn = self.connect()
        try:
            row = conn.execute("SELECT started_at FROM sync_runs WHERE run_id = ?", (run_id,)).fetchone()
            duration = None
            if row and row["started_at"]:
                started = datetime.strptime(row["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                completed = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                duration = (completed - started).total_seconds()
            conn.execute(
                """
                UPDATE sync_runs SET
                    status = 'completed',
                    total_raw = ?, total_valid = ?, total_errors = ?,
                    total_new = ?, total_updated = ?, total_unchanged = ?,
                    error_details = ?,
                    completed_at = ?, duration_seconds = ?
                WHERE run_id = ?
                """,
                (
                    stats.get("total_raw", 0),
                    stats.get("total_valid", 0),
                    stats.get("total_errors", 0),
                    stats.get("total_new", 0),
                    stats.get("total_updated", 0),
                    stats.get("total_unchanged", 0),
                    json.dumps(errors or [], ensure_ascii=False),
                    now,
                    duration,
                    run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_sync_run(self, run_id: int, error: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE sync_runs SET status = 'failed', error_details = ?, completed_at = ? WHERE run_id = ?",
                (error, _utc_now(), run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_conversion(self, record: dict[str, Any], sync_run_id: int | None = None) -> tuple[str, int]:
        """Upsert một conversion record.

        Returns:
            ("new" | "updated" | "unchanged", conversion_db_id)
        """
        source = record.get("source") or "shopee_affiliate"
        conv_id = record.get("conversion_id")
        if not conv_id:
            raise ValueError("conversion_id is required")
        extra = record.get("_extra_fields")
        extra_json = json.dumps(extra, ensure_ascii=False, sort_keys=True) if extra else None
        items = record.get("_items") or []
        now = _utc_now()
        values = {
            "source": source,
            "conversion_id": conv_id,
            "checkout_id": record.get("checkout_id"),
            "order_id": record.get("order_id"),
            "order_sn": record.get("order_sn"),
            "affiliate_transaction_id": record.get("affiliate_transaction_id"),
            "sub_id": record.get("sub_id"),
            "click_id": record.get("click_id"),
            "conversion_status_raw": record.get("conversion_status"),
            "checkout_status_raw": record.get("checkout_status"),
            "order_status_raw": record.get("order_status"),
            "internal_status": "unknown",
            "gross_commission": record.get("gross_commission"),
            "capped_commission": record.get("capped_commission"),
            "estimated_total_commission": record.get("estimated_total_commission"),
            "affiliate_net_commission": record.get("affiliate_net_commission"),
            "item_commission": record.get("item_commission"),
            "item_id": record.get("item_id"),
            "shop_id": record.get("shop_id"),
            "item_name": record.get("item_name"),
            "item_price": record.get("item_price"),
            "purchase_time": record.get("purchase_time"),
            "click_time": record.get("click_time"),
            "source_updated_at": record.get("source_updated_at"),
            "extra_fields_json": extra_json,
        }
        conn = self.connect()
        try:
            existing = conn.execute(
                "SELECT * FROM conversions WHERE source = ? AND conversion_id = ?",
                (source, conv_id),
            ).fetchone()
            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO conversions (
                        source, conversion_id, checkout_id, order_id, order_sn,
                        affiliate_transaction_id, sub_id, click_id,
                        conversion_status_raw, checkout_status_raw, order_status_raw,
                        internal_status,
                        gross_commission, capped_commission, estimated_total_commission,
                        affiliate_net_commission, item_commission,
                        item_id, shop_id, item_name, item_price,
                        purchase_time, click_time, source_updated_at,
                        first_seen_at, last_seen_at, last_sync_run_id, extra_fields_json
                    ) VALUES (
                        :source, :conversion_id, :checkout_id, :order_id, :order_sn,
                        :affiliate_transaction_id, :sub_id, :click_id,
                        :conversion_status_raw, :checkout_status_raw, :order_status_raw,
                        :internal_status,
                        :gross_commission, :capped_commission, :estimated_total_commission,
                        :affiliate_net_commission, :item_commission,
                        :item_id, :shop_id, :item_name, :item_price,
                        :purchase_time, :click_time, :source_updated_at,
                        :now, :now, :sync_run_id, :extra_fields_json
                    )
                    """,
                    {**values, "now": now, "sync_run_id": sync_run_id},
                )
                db_id = int(cursor.lastrowid)
                self._insert_history(
                    conn,
                    db_id,
                    conv_id,
                    None,
                    values,
                    "initial",
                    sync_run_id,
                    now,
                )
                self._replace_items(conn, db_id, items)
                conn.commit()
                return "new", db_id

            changes = _detect_changes(existing, record)
            db_id = int(existing["id"])
            if not changes and existing["extra_fields_json"] == extra_json:
                conn.execute(
                    "UPDATE conversions SET last_seen_at = ?, last_sync_run_id = ? WHERE id = ?",
                    (now, sync_run_id, db_id),
                )
                self._replace_items(conn, db_id, items)
                conn.commit()
                return "unchanged", db_id

            change_type = _classify_change(changes) if changes else "data_change"
            conn.execute(
                """
                UPDATE conversions SET
                    checkout_id = :checkout_id,
                    order_id = :order_id,
                    order_sn = :order_sn,
                    affiliate_transaction_id = :affiliate_transaction_id,
                    sub_id = :sub_id,
                    click_id = :click_id,
                    conversion_status_raw = :conversion_status_raw,
                    checkout_status_raw = :checkout_status_raw,
                    order_status_raw = :order_status_raw,
                    internal_status = :internal_status,
                    gross_commission = :gross_commission,
                    capped_commission = :capped_commission,
                    estimated_total_commission = :estimated_total_commission,
                    affiliate_net_commission = :affiliate_net_commission,
                    item_commission = :item_commission,
                    item_id = :item_id,
                    shop_id = :shop_id,
                    item_name = :item_name,
                    item_price = :item_price,
                    purchase_time = :purchase_time,
                    click_time = :click_time,
                    source_updated_at = :source_updated_at,
                    last_seen_at = :now,
                    last_sync_run_id = :sync_run_id,
                    extra_fields_json = :extra_fields_json
                WHERE id = :id
                """,
                {**values, "now": now, "sync_run_id": sync_run_id, "id": db_id},
            )
            self._insert_history(conn, db_id, conv_id, existing, values, change_type, sync_run_id, now)
            self._replace_items(conn, db_id, items)
            conn.commit()
            return "updated", db_id
        finally:
            conn.close()

    def _insert_history(
        self,
        conn: sqlite3.Connection,
        db_id: int,
        conv_id: str,
        existing: sqlite3.Row | None,
        values: dict[str, Any],
        change_type: str,
        sync_run_id: int | None,
        now: str,
    ) -> None:
        def old(column: str) -> Any:
            return None if existing is None else existing[column]

        conn.execute(
            """
            INSERT INTO conversion_status_history (
                conversion_db_id, source_conversion_id,
                old_conversion_status, new_conversion_status,
                old_order_status, new_order_status,
                old_internal_status, new_internal_status,
                old_gross_commission, new_gross_commission,
                old_affiliate_net_commission, new_affiliate_net_commission,
                old_capped_commission, new_capped_commission,
                change_type, observed_at, sync_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                conv_id,
                old("conversion_status_raw"),
                values["conversion_status_raw"],
                old("order_status_raw"),
                values["order_status_raw"],
                old("internal_status"),
                values["internal_status"],
                old("gross_commission"),
                values["gross_commission"],
                old("affiliate_net_commission"),
                values["affiliate_net_commission"],
                old("capped_commission"),
                values["capped_commission"],
                change_type,
                now,
                sync_run_id,
            ),
        )

    def _replace_items(self, conn: sqlite3.Connection, db_id: int, items: list[dict[str, Any]]) -> None:
        conn.execute("DELETE FROM conversion_items WHERE conversion_db_id = ?", (db_id,))
        for item in items:
            conn.execute(
                """
                INSERT INTO conversion_items (
                    conversion_db_id, item_id, item_name, item_price, item_commission, quantity
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    db_id,
                    item.get("item_id"),
                    item.get("item_name"),
                    item.get("item_price"),
                    item.get("item_commission"),
                    item.get("quantity") or 1,
                ),
            )

    def get_items(self, db_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM conversion_items WHERE conversion_db_id = ? ORDER BY id",
                (db_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_conversion(self, source: str, conversion_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM conversions WHERE source = ? AND conversion_id = ?",
                (source, conversion_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_conversions(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM conversions ORDER BY id").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_conversion_history(self, db_id: int) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM conversion_status_history WHERE conversion_db_id = ? ORDER BY id",
                (db_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def quarantine_conversion(self, record: dict[str, Any], sync_run_id: int | None = None) -> str:
        """Giữ bản ghi thiếu hoặc trùng identity. Không ghi đè bảng conversions.

        sync_run_id được nhận để cùng chữ ký với upsert, nhưng quarantine không
        gắn vào lịch sử hoa hồng.
        """
        del sync_run_id
        source = record.get("source") or "shopee_affiliate"
        key = record.get("quarantine_key")
        if not key:
            raise ValueError("quarantine_key is required")
        now = _utc_now()
        conn = self.connect()
        try:
            existing = conn.execute(
                "SELECT id FROM conversion_quarantine WHERE source = ? AND quarantine_key = ?",
                (source, key),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE conversion_quarantine SET last_seen_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                conn.commit()
                return "unchanged"
            conn.execute(
                """
                INSERT INTO conversion_quarantine (
                    source, quarantine_key, reason, checkout_id, order_id, affiliate_id,
                    first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    key,
                    record.get("reason") or "unspecified",
                    record.get("checkout_id"),
                    record.get("order_id"),
                    record.get("affiliate_id"),
                    now,
                    now,
                ),
            )
            conn.commit()
            return "new"
        finally:
            conn.close()

    def upsert_click_observation(
        self,
        observation_key: str,
        sub_id: str | None,
        click_time: str | None,
        source: str,
        evidence: str,
    ) -> str:
        """Ghi một click đã quan sát. Không tạo conversion."""
        if not observation_key:
            raise ValueError("observation_key is required")
        now = _utc_now()
        conn = self.connect()
        try:
            existing = conn.execute(
                "SELECT id FROM click_observations WHERE source = ? AND observation_key = ?",
                (source, observation_key),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE click_observations SET last_seen_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                conn.commit()
                return "unchanged"
            conn.execute(
                """
                INSERT INTO click_observations (
                    source, evidence, observation_key, sub_id, click_time, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, evidence, observation_key, sub_id, click_time, now, now),
            )
            conn.commit()
            return "new"
        finally:
            conn.close()

    def get_click_observations(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM click_observations ORDER BY id").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_quarantine_rows(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM conversion_quarantine ORDER BY id").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_quarantine(self) -> int:
        conn = self.connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM conversion_quarantine").fetchone()[0])
        finally:
            conn.close()

    def count_conversions(self) -> int:
        conn = self.connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM conversions").fetchone()[0])
        finally:
            conn.close()

    def save_attribution(
        self,
        conversion_db_id: int,
        source_conversion_id: str,
        sub_id: str | None,
        telegram_user_id: int | None,
        match_status: str,
        match_method: str,
        match_notes: str | None,
        sync_run_id: int | None,
    ) -> None:
        """Ghi lại kết quả đối chiếu, thay bản cũ của cùng conversion."""
        conn = self.connect()
        try:
            conn.execute("DELETE FROM attribution_matches WHERE conversion_db_id = ?", (conversion_db_id,))
            conn.execute(
                """
                INSERT INTO attribution_matches (
                    conversion_db_id, source_conversion_id, sub_id, telegram_user_id,
                    match_status, match_method, match_notes, matched_at, sync_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversion_db_id,
                    source_conversion_id,
                    sub_id,
                    telegram_user_id,
                    match_status,
                    match_method,
                    match_notes,
                    _utc_now(),
                    sync_run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_attribution_summary(self) -> dict[str, int]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT match_status, COUNT(*) AS cnt FROM attribution_matches GROUP BY match_status"
            ).fetchall()
            summary = {"matched": 0, "unmatched": 0, "ambiguous": 0, "missing_sub_id": 0, "total": 0}
            for row in rows:
                summary[row["match_status"]] = int(row["cnt"])
                summary["total"] += int(row["cnt"])
            return summary
        finally:
            conn.close()

    def get_all_attributions(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(
                """
                SELECT a.*, c.order_id, c.order_status_raw, c.affiliate_net_commission
                FROM attribution_matches a
                JOIN conversions c ON c.id = a.conversion_db_id
                ORDER BY a.id
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_sync_runs(self) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM sync_runs ORDER BY run_id").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
