"""SQLite riêng cho tracking. Ví, payout và số dư nằm ở wallet.py (PLAN-066)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot.commission_validation import (
    CONFIDENCE_INFERRED,
    FRAUD,
    NEEDS_REVIEW,
    REJECTED,
    SETTLEMENT_NOT_VERIFIED,
    SOURCE_REPORT,
    UNKNOWN,
    Assessment,
    assess_raw,
    is_regression,
    is_significant_drop,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_user_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS link_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_update_id INTEGER UNIQUE,
    telegram_user_id INTEGER NOT NULL,
    sub_id TEXT UNIQUE,
    original_url TEXT NOT NULL,
    affiliate_url TEXT,
    item_id INTEGER,
    shop_id INTEGER,
    product_name TEXT,
    price_vnd INTEGER,
    estimated_commission INTEGER,
    estimated_cashback INTEGER,
    cashback_rate_percent INTEGER,
    api_status TEXT,
    data_source TEXT,
    product_last_update TEXT,
    link_status TEXT NOT NULL,
    reject_reason TEXT,
    delivery_status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (telegram_user_id) REFERENCES telegram_users(telegram_user_id)
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_update_id INTEGER UNIQUE,
    telegram_user_id INTEGER NOT NULL,
    body_html TEXT NOT NULL,
    button_url TEXT,
    edit_message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_html TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    last_attempt_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS shopee_cookies (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL DEFAULT 'disconnected',
    account_name TEXT,
    last_sync_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_clicks (
    click_id TEXT PRIMARY KEY,
    sub_id TEXT,
    click_time TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_conversions (
    conversion_id TEXT PRIMARY KEY,
    sub_id TEXT,
    order_sn TEXT,
    order_status TEXT,
    conversion_status TEXT,
    purchase_time TEXT,
    gross_commission_vnd INTEGER,
    net_commission_vnd INTEGER,
    matched_link_id INTEGER,
    telegram_user_id INTEGER,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL,
    clicks_synced INTEGER NOT NULL DEFAULT 0,
    conversions_synced INTEGER NOT NULL DEFAULT 0,
    new_orders_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

-- PLAN-066: sổ hoàn tiền. Mỗi đơn khớp link bot một dòng; số tiền đã chốt không tính lại.
CREATE TABLE IF NOT EXISTS cashback_entries (
    conversion_id TEXT PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    link_id INTEGER,
    order_sn TEXT,
    item_name TEXT,
    commission_vnd INTEGER NOT NULL DEFAULT 0,
    cashback_vnd INTEGER NOT NULL DEFAULT 0,
    fee_vnd INTEGER NOT NULL DEFAULT 0,
    tax_vnd INTEGER NOT NULL DEFAULT 0,
    policy_label TEXT,
    status TEXT NOT NULL,
    purchase_time TEXT,
    completed_at TEXT,
    available_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cashback_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL,
    amount_vnd INTEGER NOT NULL,
    status TEXT NOT NULL,
    bank_code TEXT NOT NULL,
    account_no TEXT NOT NULL,
    account_name TEXT NOT NULL,
    transfer_note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by INTEGER
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    telegram_user_id INTEGER PRIMARY KEY,
    bank_code TEXT NOT NULL,
    account_no TEXT NOT NULL,
    account_name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Lịch sử thay đổi của từng đơn Shopee (PLAN-074). Chỉ thêm dòng, không sửa, không xoá.
CREATE TABLE IF NOT EXISTS shopee_conversion_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    significant INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    sync_run_id INTEGER,
    detected_at TEXT NOT NULL,
    UNIQUE (conversion_id, field, sync_run_id)
);
CREATE INDEX IF NOT EXISTS idx_conversion_changes_conv ON shopee_conversion_changes(conversion_id);

-- Đối soát thanh toán Shopee (PLAN-075, ADR-052). Tên bảng cố ý KHÁC `shopee_settlements` /
-- `payout_tax_policies` (điều kiện mở khoá của payout_gate, PLAN-078): nhập chứng từ hay đối soát
-- MATCHED không thể mở ví. Tiền là VND nguyên; NULL nghĩa là "chưa xác minh", không phải 0.
CREATE TABLE IF NOT EXISTS settlement_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL CHECK (length(period) = 7),
    shopee_payment_ref TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN
        ('DRAFT', 'EVIDENCE_PENDING', 'PARTIALLY_MATCHED', 'MATCHED', 'DISPUTED', 'REVERSED')),
    reported_commission_vnd INTEGER,
    adjustments_vnd INTEGER,
    fee_vnd INTEGER,
    fee_vat_vnd INTEGER,
    fee_includes_vat INTEGER,
    tax_withheld_vnd INTEGER,
    shopee_payout_vnd INTEGER,
    bank_received_vnd INTEGER,
    statement_evidence_id INTEGER,
    bank_evidence_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_settlement_batch_ref
    ON settlement_batches(period, shopee_payment_ref) WHERE shopee_payment_ref IS NOT NULL;

-- Chứng cứ: chỉ thêm. Thay chứng từ = dòng mới + superseded_by, không sửa đè.
CREATE TABLE IF NOT EXISTS settlement_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES settlement_batches(id),
    kind TEXT NOT NULL CHECK (kind IN ('shopee_validation_report', 'shopee_payment_report', 'bank_statement')),
    source TEXT NOT NULL,
    document_ref TEXT NOT NULL CHECK (length(document_ref) > 0),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    stored_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    parser TEXT NOT NULL,
    verification TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (verification IN ('RECEIVED', 'VERIFIED', 'REJECTED', 'SUPERSEDED')),
    viewed_by INTEGER,
    viewed_at TEXT,
    superseded_by INTEGER,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (content_sha256),
    UNIQUE (kind, document_ref)
);

-- Khoản theo từng đơn trong một kỳ. conversion_id NULL: Shopee có trả nhưng bot không xác định được đơn.
CREATE TABLE IF NOT EXISTS settlement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES settlement_batches(id),
    evidence_id INTEGER NOT NULL REFERENCES settlement_evidence(id),
    order_ref TEXT NOT NULL,
    conversion_id TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    telegram_user_id INTEGER,
    approved_vnd INTEGER,
    settled_vnd INTEGER,
    adjustment_vnd INTEGER,
    match_status TEXT NOT NULL CHECK (match_status IN
        ('MATCHED', 'NOT_BOT', 'UNKNOWN_ORDER', 'AMOUNT_MISMATCH', 'DUPLICATE', 'NEEDS_REVIEW')),
    created_at TEXT NOT NULL,
    UNIQUE (batch_id, evidence_id, order_ref)
);
CREATE INDEX IF NOT EXISTS idx_settlement_items_conv ON settlement_items(conversion_id);

-- Điều chỉnh hoa hồng sau khi đã vào một kỳ (giảm, thu hồi, gian lận về sau). Một sự kiện một dòng.
CREATE TABLE IF NOT EXISTS settlement_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id TEXT NOT NULL,
    original_batch_id INTEGER,
    old_vnd INTEGER NOT NULL,
    new_vnd INTEGER NOT NULL,
    delta_vnd INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('conversion_change', 'settlement_item')),
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'DISPUTED')),
    detected_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    UNIQUE (source, source_ref)
);

-- Nhật ký đối soát: chỉ thêm. Trigger chặn sửa và xoá.
CREATE TABLE IF NOT EXISTS settlement_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS settlement_audit_no_update BEFORE UPDATE ON settlement_audit
BEGIN SELECT RAISE(ABORT, 'settlement_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS settlement_audit_no_delete BEFORE DELETE ON settlement_audit
BEGIN SELECT RAISE(ABORT, 'settlement_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS settlement_evidence_no_delete BEFORE DELETE ON settlement_evidence
BEGIN SELECT RAISE(ABORT, 'settlement_evidence is append-only'); END;

-- Chính sách chốt cho từng link lúc báo giá (PLAN-076, ADR-053). Một link một dòng, chỉ thêm.
-- captured: ghi cùng lúc tạo link. backfilled: dựng lại từ link cũ và đã tính ra đúng số đã báo.
-- unresolved: link cũ không dựng lại được; cột chính sách để trống, không gán chính sách mới.
CREATE TABLE IF NOT EXISTS link_policy_snapshots (
    link_id INTEGER PRIMARY KEY REFERENCES link_requests(id),
    schema_version INTEGER NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('captured', 'backfilled', 'unresolved')),
    policy_label TEXT NOT NULL,
    pricing_version TEXT CHECK (pricing_version IN ('v1.1', 'v1.2')),
    formula TEXT,
    rounding TEXT,
    share_bps INTEGER,
    share_policy_id INTEGER,
    reserve_policy_id INTEGER,
    fee_bps INTEGER,
    tax_reserve_bps INTEGER,
    other_reserve_vnd INTEGER,
    rounding_unit INTEGER,
    resolved_at TEXT,
    quote_commission_vnd INTEGER,
    quote_cashback_vnd INTEGER,
    quote_source TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    CHECK (provenance = 'unresolved' OR (
        pricing_version IS NOT NULL AND formula IS NOT NULL AND rounding IS NOT NULL
        AND share_bps IS NOT NULL AND fee_bps IS NOT NULL AND tax_reserve_bps IS NOT NULL
        AND other_reserve_vnd IS NOT NULL AND rounding_unit IS NOT NULL AND resolved_at IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS link_policy_snapshots_no_update BEFORE UPDATE ON link_policy_snapshots
BEGIN SELECT RAISE(ABORT, 'link_policy_snapshots is append-only'); END;
CREATE TRIGGER IF NOT EXISTS link_policy_snapshots_no_delete BEFORE DELETE ON link_policy_snapshots
BEGIN SELECT RAISE(ABORT, 'link_policy_snapshots is append-only'); END;

-- Update Telegram xử lý lỗi (hardening P0-4). Khoá chính là update_id: không ghi trùng.
-- retrying: còn thử lại, chưa tiến offset. quarantined: đã cách ly, offset đi tiếp, admin xem.
CREATE TABLE IF NOT EXISTS failed_updates (
    telegram_update_id INTEGER PRIMARY KEY,
    update_type TEXT NOT NULL,
    telegram_user_id INTEGER,
    category TEXT NOT NULL,
    error_code TEXT NOT NULL,
    error_detail TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('retrying', 'quarantined', 'resolved')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

-- Khoá tài chính ở tầng DB (Production Safety Hardening V1): chưa có bảng bằng chứng Shopee đã trả
-- và chính sách thuế người nhận thì không ghi được khoản 'available', yêu cầu rút mới hay trạng thái 'paid',
-- kể cả khi gọi SQL trực tiếp. Điều kiện chi tiết (có dòng, đủ quỹ, không gian lận) ở payout_gate.py.
CREATE TRIGGER IF NOT EXISTS financial_lock_entry_insert BEFORE INSERT ON cashback_entries
WHEN NEW.status = 'available' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_entry_update BEFORE UPDATE OF status ON cashback_entries
WHEN NEW.status = 'available' AND OLD.status != 'available' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_payout_insert BEFORE INSERT ON cashback_payouts
WHEN NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies')
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_payout_paid BEFORE UPDATE OF status ON cashback_payouts
WHEN NEW.status = 'paid' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE INDEX IF NOT EXISTS idx_cashback_entries_user ON cashback_entries(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_cashback_payouts_user ON cashback_payouts(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_shopee_conversions_sub_id ON shopee_conversions(sub_id);
CREATE INDEX IF NOT EXISTS idx_shopee_conversions_user_id ON shopee_conversions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_shopee_clicks_sub_id ON shopee_clicks(sub_id);
"""


# Số liệu đối soát thêm (PLAN-066), theo các ô của Addlivetag. NULL: dòng kéo trước PLAN-066.
SHOPEE_CONVERSION_COLUMNS = (
    ("gmv_vnd", "INTEGER"),
    ("item_qty", "INTEGER"),
    ("item_name", "TEXT"),
    ("mcn_fee_vnd", "INTEGER"),
    ("complete_time", "TEXT"),
    ("validation_month", "TEXT"),
)

# Dữ liệu sản phẩm thêm cho thống kê (PLAN-064). Cho phép NULL: link cũ không có.
PRODUCT_INSIGHT_COLUMNS = (
    ("cat_name", "TEXT"),
    ("shop_name", "TEXT"),
    ("seller_commission_vnd", "INTEGER"),
    ("shopee_commission_vnd", "INTEGER"),
    ("commission_rate_bps", "INTEGER"),
    ("is_xtra", "INTEGER"),
    ("is_capped", "INTEGER"),
)


# Trạng thái duyệt hoa hồng (PLAN-074). Ba trạng thái tách cột: order_status / validation_status / settlement_status.
VALIDATION_COLUMNS = (
    ("first_commission_vnd", "INTEGER"),
    ("validation_status", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
    ("validation_reason", "TEXT"),
    ("fraud_flag", "INTEGER"),
    ("affiliate_item_status", "TEXT"),
    ("checkout_status", "TEXT"),
    ("settlement_status", f"TEXT NOT NULL DEFAULT '{SETTLEMENT_NOT_VERIFIED}'"),
    ("validation_source", "TEXT"),
    ("validation_confidence", "TEXT"),
    ("evidence_ref", "TEXT"),
    ("review_status", "TEXT NOT NULL DEFAULT 'none'"),
    ("reviewed_by", "INTEGER"),
    ("reviewed_at", "TEXT"),
)


@dataclass(frozen=True)
class ConversionChange:
    field: str
    old: str | None
    new: str | None
    significant: bool


@dataclass(frozen=True)
class ConversionResult:
    is_new: bool
    is_matched: bool
    matched_link_id: int | None
    telegram_user_id: int | None
    changes: tuple[ConversionChange, ...]
    validation_status: str


def _text(value) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _backfill_validation(conn: sqlite3.Connection) -> None:
    """Dòng có từ trước PLAN-074: chép hoa hồng hiện tại làm mốc đầu, đánh giá lại từ raw_json đã lưu.

    Không ghi lịch sử (đây là mốc, không phải thay đổi), không bao giờ ra APPROVED hay SETTLED.
    Chạy lại nhiều lần không đổi gì: chỉ đụng dòng còn UNKNOWN chưa có nguồn.
    """
    rows = conn.execute(
        "SELECT conversion_id, raw_json, net_commission_vnd, gross_commission_vnd FROM shopee_conversions "
        "WHERE validation_source IS NULL"
    ).fetchall()
    for row in rows:
        commission = row["net_commission_vnd"] if row["net_commission_vnd"] is not None else row["gross_commission_vnd"]
        found = assess_raw(row["raw_json"], commission)
        conn.execute(
            """
            UPDATE shopee_conversions SET
                first_commission_vnd = COALESCE(first_commission_vnd, net_commission_vnd),
                validation_status = ?, validation_reason = ?, fraud_flag = ?, affiliate_item_status = ?,
                checkout_status = ?, validation_source = ?, validation_confidence = ?,
                review_status = CASE WHEN ? = 'NEEDS_REVIEW' THEN 'needs_review' ELSE review_status END
            WHERE conversion_id = ?
            """,
            (
                found.status, found.reason, found.fraud_flag, found.item_statuses, found.checkout_status,
                SOURCE_REPORT, CONFIDENCE_INFERRED, found.status, row["conversion_id"],
            ),
        )


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


@dataclass(frozen=True)
class LinkRow:
    id: int
    telegram_update_id: int | None
    telegram_user_id: int
    sub_id: str | None
    affiliate_url: str | None
    item_id: int | None
    product_name: str | None
    price_vnd: int | None
    estimated_commission: int | None
    estimated_cashback: int | None
    cashback_rate_percent: int | None
    link_status: str
    reject_reason: str | None
    estimate_policy: str | None = None


def insert_snapshot(conn: sqlite3.Connection, link_id: int, snapshot: dict) -> None:
    row = {"link_id": link_id, **snapshot}
    names = ", ".join(row)
    conn.execute(
        f"INSERT INTO link_policy_snapshots ({names}) VALUES ({', '.join('?' for _ in row)})",
        list(row.values()),
    )


# Bảng huỷ lịch chính sách (PLAN-076). Admin cũng chạy file này khi mở kết nối, như 004–006.
CANCEL_SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "008_policy_cancellations.sql"


class TrackingRepository:
    def __init__(self, path: str):
        self.path = path

    def column_names(self, table: str) -> set[str]:
        with self.connect() as conn:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def connect(self) -> sqlite3.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executescript(CANCEL_SCHEMA_PATH.read_text(encoding="utf-8"))
            columns = {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}
            if "delivery_status" not in columns:
                conn.execute("ALTER TABLE link_requests ADD COLUMN delivery_status TEXT")
            _add_column(conn, "link_requests", "delivery_attempts", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "link_requests", "next_retry_at", "TEXT")
            _add_column(conn, "link_requests", "last_delivery_error", "TEXT")
            _add_column(conn, "telegram_users", "rate_window_start", "TEXT")
            _add_column(conn, "telegram_users", "rate_count", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "telegram_users", "cooldown_until", "TEXT")
            _add_column(conn, "outbound_messages", "edit_message_id", "INTEGER")
            _add_column(conn, "outbound_messages", "reply_markup_json", "TEXT")
            for column, ddl in PRODUCT_INSIGHT_COLUMNS:
                _add_column(conn, "link_requests", column, ddl)
            for column, ddl in SHOPEE_CONVERSION_COLUMNS:
                _add_column(conn, "shopee_conversions", column, ddl)
            for column, ddl in VALIDATION_COLUMNS:
                _add_column(conn, "shopee_conversions", column, ddl)
            _backfill_validation(conn)
            # Phần admin chịu trên từng đơn: phí và dự phòng thuế (admin còn = HH − hoàn − phí − thuế).
            _add_column(conn, "cashback_entries", "fee_vnd", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "cashback_entries", "tax_vnd", "INTEGER NOT NULL DEFAULT 0")

    def upsert_user(self, telegram_user_id: int, username: str | None) -> bool:
        now = _utc_now()
        with self.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM telegram_users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone() is not None
            conn.execute(
                """
                INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username = excluded.username,
                    last_seen_at = excluded.last_seen_at
                """,
                (telegram_user_id, username, now, now),
            )
        return not existed

    def get_user(self, telegram_user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT telegram_user_id, username, created_at, last_seen_at FROM telegram_users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()

    def count_users(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM telegram_users").fetchone()[0])

    def get_by_update_id(self, update_id: int) -> LinkRow | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM link_requests WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()
        return _row(row) if row else None

    def sub_id_exists(self, sub_id: str) -> bool:
        with self.connect() as conn:
            found = conn.execute(
                "SELECT 1 FROM link_requests WHERE sub_id = ?",
                (sub_id,),
            ).fetchone()
        return found is not None

    def insert_created(self, fields: dict, snapshot: dict | None = None) -> int:
        """snapshot: dòng link_policy_snapshots (không có link_id). Ghi cùng transaction với link."""
        fields = dict(fields)
        fields["delivery_status"] = "pending"
        return self._insert(fields, snapshot)

    def insert_rejected(self, fields: dict) -> int:
        fields = dict(fields)
        fields["link_status"] = "rejected"
        fields.setdefault("sub_id", None)
        fields.setdefault("affiliate_url", None)
        return self._insert(fields)

    def _insert(self, fields: dict, snapshot: dict | None = None) -> int:
        columns = [
            "telegram_update_id",
            "telegram_user_id",
            "sub_id",
            "original_url",
            "affiliate_url",
            "item_id",
            "shop_id",
            "product_name",
            "price_vnd",
            "estimated_commission",
            "estimated_cashback",
            "cashback_rate_percent",
            "api_status",
            "data_source",
            "product_last_update",
            "link_status",
            "reject_reason",
            "delivery_status",
            "created_at",
        ]
        existing = self.column_names("link_requests")
        if fields.get("estimate_policy") and "estimate_policy" in existing:
            columns.append("estimate_policy")
        columns += [name for name, _ddl in PRODUCT_INSIGHT_COLUMNS if name in existing and name in fields]
        payload = {key: fields.get(key) for key in columns}
        payload["created_at"] = payload["created_at"] or _utc_now()
        placeholders = ", ".join("?" for _ in columns)
        with self.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO link_requests ({', '.join(columns)}) VALUES ({placeholders})",
                [payload[key] for key in columns],
            )
            link_id = int(cursor.lastrowid)
            if snapshot is not None:
                insert_snapshot(conn, link_id, snapshot)
            return link_id

    def get_offset(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = 'update_offset'"
            ).fetchone()
        return int(row["value"]) if row else 0

    def mark_delivered(self, update_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE link_requests
                SET delivery_status = 'sent',
                    next_retry_at = NULL,
                    last_delivery_error = NULL
                WHERE telegram_update_id = ? AND link_status = 'created'
                """,
                (update_id,),
            )

    def mark_link_delivery(
        self,
        update_id: int,
        status: str,
        attempts: int,
        next_retry_at: str | None,
        error_kind: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE link_requests
                SET delivery_status = ?,
                    delivery_attempts = ?,
                    next_retry_at = ?,
                    last_delivery_error = ?
                WHERE telegram_update_id = ?
                """,
                (status, attempts, next_retry_at, error_kind, update_id),
            )

    def consume_link_attempt(
        self,
        telegram_user_id: int,
        now: datetime,
        limit: int,
        window_sec: int,
        cooldown_sec: int,
    ) -> bool:
        """True nếu còn lượt. False thì không tạo link. limit <= 0 là tắt giới hạn."""
        if limit <= 0:
            return True
        moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        moment = moment.astimezone(timezone.utc)
        now_text = _stamp(moment)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT rate_window_start, rate_count, cooldown_until
                FROM telegram_users WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
            if row is None:
                return True
            cooldown_until = row["cooldown_until"]
            if cooldown_until and cooldown_until > now_text:
                return False
            window_start = row["rate_window_start"]
            count = int(row["rate_count"] or 0)
            expired = True
            if window_start:
                started = datetime.strptime(window_start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                expired = (moment - started).total_seconds() >= window_sec
            if expired or (cooldown_until and cooldown_until <= now_text):
                conn.execute(
                    """
                    UPDATE telegram_users
                    SET rate_window_start = ?, rate_count = 1, cooldown_until = NULL
                    WHERE telegram_user_id = ?
                    """,
                    (now_text, telegram_user_id),
                )
                return True
            if count >= limit:
                until = _stamp(moment + timedelta(seconds=cooldown_sec))
                conn.execute(
                    """
                    UPDATE telegram_users
                    SET cooldown_until = ?
                    WHERE telegram_user_id = ?
                    """,
                    (until, telegram_user_id),
                )
                return False
            conn.execute(
                """
                UPDATE telegram_users
                SET rate_count = ?
                WHERE telegram_user_id = ?
                """,
                (count + 1, telegram_user_id),
            )
            return True

    def enqueue_outbound(
        self,
        update_id: int,
        telegram_user_id: int,
        body_html: str,
        button_url: str | None,
        edit_message_id: int | None = None,
        reply_markup_json: str | None = None,
    ) -> sqlite3.Row:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO outbound_messages (
                    telegram_update_id, telegram_user_id, body_html, button_url, edit_message_id,
                    reply_markup_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(telegram_update_id) DO NOTHING
                """,
                (update_id, telegram_user_id, body_html, button_url, edit_message_id, reply_markup_json, _utc_now()),
            )
            return conn.execute(
                "SELECT * FROM outbound_messages WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()

    def get_outbound(self, update_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM outbound_messages WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()

    def list_due_outbound(self, now: datetime, limit: int) -> list[sqlite3.Row]:
        now_text = _stamp(now)
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM outbound_messages
                WHERE status IN ('pending', 'retry', 'ambiguous', 'sending')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (now_text, limit),
            ).fetchall()

    def mark_outbound_sending(self, outbound_id: int) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = 'sending',
                    attempt_count = attempt_count + 1,
                    next_retry_at = NULL
                WHERE id = ?
                """,
                (outbound_id,),
            )
            row = conn.execute(
                "SELECT attempt_count FROM outbound_messages WHERE id = ?",
                (outbound_id,),
            ).fetchone()
        return int(row["attempt_count"])

    def mark_outbound_sent(self, outbound_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = 'sent', sent_at = ?, last_error = NULL, next_retry_at = NULL
                WHERE id = ?
                """,
                (_utc_now(), outbound_id),
            )

    def schedule_outbound(
        self,
        outbound_id: int,
        status: str,
        next_retry_at: str | None,
        error_kind: str,
        attempts: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = ?, next_retry_at = ?, last_error = ?, attempt_count = ?
                WHERE id = ?
                """,
                (status, next_retry_at, error_kind[:40], attempts, outbound_id),
            )

    def enqueue_admin_event(self, event_key: str, event_type: str, chat_id: int, message_html: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM admin_notifications WHERE event_key = ?",
                (event_key,),
            ).fetchone()
            if row is not None:
                return False
            conn.execute(
                """
                INSERT INTO admin_notifications
                (event_key, event_type, chat_id, message_html, status, attempt_count, created_at)
                VALUES (?, ?, ?, ?, 'pending', 0, ?)
                """,
                (event_key, event_type, chat_id, message_html, _utc_now()),
            )
            return True

    def list_pending_admin_events(self, limit: int = 10, max_attempts: int = 5) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM admin_notifications
                WHERE status != 'sent' AND attempt_count < ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (max_attempts, limit),
            ).fetchall()

    def mark_admin_event_sent(self, event_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE admin_notifications
                SET status = 'sent',
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    sent_at = ?,
                    last_error = NULL
                WHERE id = ?
                """,
                (_utc_now(), _utc_now(), event_id),
            )

    def mark_admin_event_failed(self, event_id: int, error_code: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE admin_notifications
                SET status = 'pending',
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (_utc_now(), error_code[:80], event_id),
            )

    def record_update_failure(
        self,
        update_id: int,
        update_type: str,
        telegram_user_id: int | None,
        category: str,
        error_code: str,
        error_detail: str,
    ) -> int:
        """Ghi một lần xử lý lỗi, trả số lần đã lỗi. Lỗi ghi DB thì ném ra: caller không được tiến offset."""
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO failed_updates (
                    telegram_update_id, update_type, telegram_user_id, category, error_code, error_detail,
                    attempt_count, status, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 'retrying', ?, ?)
                ON CONFLICT(telegram_update_id) DO UPDATE SET
                    category = excluded.category,
                    error_code = excluded.error_code,
                    error_detail = excluded.error_detail,
                    attempt_count = failed_updates.attempt_count + 1,
                    status = CASE WHEN failed_updates.status = 'quarantined' THEN 'quarantined' ELSE 'retrying' END,
                    last_seen_at = excluded.last_seen_at
                """,
                (update_id, update_type, telegram_user_id, category, error_code, error_detail, now, now),
            )
            row = conn.execute(
                "SELECT attempt_count FROM failed_updates WHERE telegram_update_id = ?", (update_id,)
            ).fetchone()
        return int(row["attempt_count"])

    def quarantine_update(self, update_id: int) -> None:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE failed_updates SET status = 'quarantined', last_seen_at = ? WHERE telegram_update_id = ?",
                (_utc_now(), update_id),
            )
            if cursor.rowcount != 1:
                raise sqlite3.OperationalError("failed_updates row missing")

    def resolve_update_failure(self, update_id: int) -> None:
        """Update từng lỗi tạm rồi xử lý được: đánh dấu resolved, giữ lịch sử."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE failed_updates SET status = 'resolved', last_seen_at = ? "
                "WHERE telegram_update_id = ? AND status = 'retrying'",
                (_utc_now(), update_id),
            )

    def update_failure(self, update_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM failed_updates WHERE telegram_update_id = ?", (update_id,)).fetchone()

    def count_quarantined_updates(self) -> int:
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM failed_updates WHERE status = 'quarantined'").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0])

    def get_state(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def set_offset(self, offset: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES ('update_offset', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(offset),),
            )

    def get_shopee_cookie_status(self) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM shopee_cookies WHERE id = 1").fetchone()
            if row is None:
                return {
                    "status": "disconnected",
                    "account_name": None,
                    "last_sync_at": None,
                    "last_error": None,
                    "updated_at": None,
                }
            return dict(row)

    def update_shopee_cookie_status(
        self,
        status: str,
        account_name: str | None = None,
        last_error: str | None = None,
        last_sync_at: str | None = None,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO shopee_cookies (id, status, account_name, last_sync_at, last_error, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    account_name = COALESCE(excluded.account_name, shopee_cookies.account_name),
                    last_sync_at = COALESCE(excluded.last_sync_at, shopee_cookies.last_sync_at),
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (status, account_name, last_sync_at, last_error, now),
            )

    def record_shopee_click(
        self,
        click_id: str,
        sub_id: str | None,
        click_time: str | None,
        raw_json: str | None = None,
    ) -> bool:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO shopee_clicks (click_id, sub_id, click_time, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(click_id) DO NOTHING
                """,
                (click_id, sub_id, click_time, raw_json, now),
            )
            return cursor.rowcount > 0

    def record_shopee_conversion(
        self,
        conversion_id: str,
        sub_id: str | None,
        order_sn: str | None,
        order_status: str | None,
        conversion_status: str | None,
        purchase_time: str | None,
        gross_commission_vnd: int | None,
        net_commission_vnd: int | None,
        raw_json: str | None = None,
        details: dict | None = None,
    ) -> tuple[bool, bool, int | None, int | None]:
        """Lưu đơn hàng và đối soát sub_id. Trả về (is_new, is_matched, matched_link_id, telegram_user_id).

        Bản rút gọn của record_conversion_snapshot (giữ cho code và test cũ). Có raw_json thì đánh giá
        trạng thái hoa hồng từ đó.
        """
        assessment = assess_raw(raw_json, net_commission_vnd if net_commission_vnd is not None else gross_commission_vnd) if raw_json else None
        result = self.record_conversion_snapshot(
            conversion_id=conversion_id,
            sub_id=sub_id,
            order_sn=order_sn,
            order_status=order_status,
            conversion_status=conversion_status,
            purchase_time=purchase_time,
            gross_commission_vnd=gross_commission_vnd,
            net_commission_vnd=net_commission_vnd,
            raw_json=raw_json,
            details=details,
            assessment=assessment,
        )
        return result.is_new, result.is_matched, result.matched_link_id, result.telegram_user_id

    def record_conversion_snapshot(
        self,
        conversion_id: str,
        sub_id: str | None,
        order_sn: str | None,
        order_status: str | None,
        conversion_status: str | None,
        purchase_time: str | None,
        gross_commission_vnd: int | None,
        net_commission_vnd: int | None,
        raw_json: str | None = None,
        details: dict | None = None,
        assessment: Assessment | None = None,
        sync_run_id: int | None = None,
    ) -> ConversionResult:
        """Ghi một lần Shopee báo về đơn (PLAN-074), trong một transaction.

        - Người thụ hưởng giữ theo lần gắn đầu tiên; Sub ID lần sau trỏ link khác → ghi lịch sử, cần kiểm tra.
        - Giá trị thiếu (None) không ghi đè giá trị đã có; hoa hồng không bị đưa về 0 vì response thiếu field.
        - Chỉ ghi lịch sử khi giá trị thật sự đổi; đồng bộ lại y hệt không tạo dòng.
        - Không bao giờ gán APPROVED hay SETTLED ở đây.
        """
        extra = {name: (details or {}).get(name) for name, _ddl in SHOPEE_CONVERSION_COLUMNS}
        now = _utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prev = conn.execute("SELECT * FROM shopee_conversions WHERE conversion_id = ?", (conversion_id,)).fetchone()
            found_link, found_user = None, None
            if sub_id:
                link = conn.execute(
                    "SELECT id, telegram_user_id FROM link_requests WHERE sub_id = ? ORDER BY id DESC LIMIT 1",
                    (sub_id,),
                ).fetchone()
                if link is not None:
                    found_link, found_user = int(link["id"]), int(link["telegram_user_id"])

            def keep(column: str, new):
                return new if new is not None else (None if prev is None else prev[column])

            changes: list[ConversionChange] = []
            review = "none" if prev is None else (prev["review_status"] or "none")
            matched_link_id, telegram_user_id = found_link, found_user
            if prev is not None and prev["matched_link_id"] is not None:
                matched_link_id, telegram_user_id = prev["matched_link_id"], prev["telegram_user_id"]
                if found_link is not None and found_link != prev["matched_link_id"]:
                    changes.append(ConversionChange("attribution", str(prev["matched_link_id"]), str(found_link), True))

            net = keep("net_commission_vnd", net_commission_vnd)
            gross = keep("gross_commission_vnd", gross_commission_vnd)
            status = keep("order_status", order_status or None)
            if assessment is not None and assessment.complete:
                validation, reason = assessment.status, assessment.reason
                fraud_flag, item_statuses = assessment.fraud_flag, assessment.item_statuses
                checkout = assessment.checkout_status
                if prev is not None and is_regression(prev["validation_status"], validation):
                    validation, reason = NEEDS_REVIEW, "status_regression"
            elif prev is not None:
                validation, reason = prev["validation_status"], prev["validation_reason"]
                fraud_flag, item_statuses, checkout = prev["fraud_flag"], prev["affiliate_item_status"], prev["checkout_status"]
            else:
                validation = UNKNOWN if assessment is None else assessment.status
                reason = None if assessment is None else assessment.reason
                fraud_flag = None if assessment is None else assessment.fraud_flag
                item_statuses = None if assessment is None else assessment.item_statuses
                checkout = None if assessment is None else assessment.checkout_status

            if prev is not None:
                old_net = prev["net_commission_vnd"]
                if net_commission_vnd is not None and net_commission_vnd != old_net:
                    changes.append(
                        ConversionChange("net_commission_vnd", _text(old_net), _text(net), is_significant_drop(old_net, net))
                    )
                if order_status and order_status != prev["order_status"]:
                    changes.append(
                        ConversionChange("order_status", prev["order_status"], order_status, "CANCEL" in order_status.upper())
                    )
                if validation != prev["validation_status"]:
                    significant = validation in (FRAUD, REJECTED, NEEDS_REVIEW)
                    changes.append(ConversionChange("validation_status", prev["validation_status"], validation, significant))
                if fraud_flag is not None and fraud_flag != prev["fraud_flag"] and prev["fraud_flag"] is not None:
                    changes.append(ConversionChange("fraud_flag", _text(prev["fraud_flag"]), _text(fraud_flag), fraud_flag == 1))
            if any(change.significant for change in changes) or (validation == NEEDS_REVIEW and (prev is None or prev["validation_status"] != NEEDS_REVIEW)):
                review = "needs_review"

            values = {
                "sub_id": keep("sub_id", sub_id),
                "order_sn": keep("order_sn", order_sn),
                "order_status": status,
                "conversion_status": keep("conversion_status", conversion_status),
                "purchase_time": keep("purchase_time", purchase_time),
                "gross_commission_vnd": gross,
                "net_commission_vnd": net,
                "matched_link_id": matched_link_id,
                "telegram_user_id": telegram_user_id,
                "raw_json": keep("raw_json", raw_json),
                "updated_at": now,
                **{name: keep(name, value) for name, value in extra.items()},
                "first_commission_vnd": net if prev is None or prev["first_commission_vnd"] is None else prev["first_commission_vnd"],
                "validation_status": validation,
                "validation_reason": reason,
                "fraud_flag": fraud_flag,
                "affiliate_item_status": item_statuses,
                "checkout_status": checkout,
                "validation_source": SOURCE_REPORT,
                "validation_confidence": CONFIDENCE_INFERRED,
                "evidence_ref": f"sync_run:{sync_run_id}" if sync_run_id else (None if prev is None else prev["evidence_ref"]),
                "review_status": review,
            }
            if prev is None:
                columns = ["conversion_id", "created_at", *values]
                conn.execute(
                    f"INSERT INTO shopee_conversions ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                    (conversion_id, now, *values.values()),
                )
            else:
                conn.execute(
                    f"UPDATE shopee_conversions SET {', '.join(f'{name} = ?' for name in values)} WHERE conversion_id = ?",
                    (*values.values(), conversion_id),
                )
            for change in changes:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO shopee_conversion_changes
                    (conversion_id, field, old_value, new_value, significant, source, sync_run_id, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (conversion_id, change.field, change.old, change.new, int(change.significant), SOURCE_REPORT, sync_run_id, now),
                )
        return ConversionResult(
            is_new=prev is None,
            is_matched=matched_link_id is not None,
            matched_link_id=matched_link_id,
            telegram_user_id=telegram_user_id,
            changes=tuple(changes),
            validation_status=validation,
        )

    def conversion_changes(self, conversion_id: str | None = None, limit: int = 10) -> list[sqlite3.Row]:
        where, args = ("WHERE conversion_id = ?", (conversion_id,)) if conversion_id else ("", ())
        with self.connect() as conn:
            return conn.execute(
                f"SELECT * FROM shopee_conversion_changes {where} ORDER BY id DESC LIMIT ?", (*args, limit)
            ).fetchall()

    def mark_conversion_reviewed(self, conversion_id: str, admin_id: int, now: str | None = None) -> bool:
        """Admin đã xem cảnh báo. Không đổi hoa hồng, trạng thái duyệt hay quyền rút."""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE shopee_conversions SET review_status = 'reviewed', reviewed_by = ?, reviewed_at = ?
                WHERE conversion_id = ? AND review_status = 'needs_review'
                """,
                (admin_id, now or _utc_now(), conversion_id),
            )
            return cursor.rowcount == 1

    def record_shopee_sync_run(self, trigger_type: str = "manual") -> int:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO shopee_sync_runs (trigger_type, status, started_at)
                VALUES (?, 'running', ?)
                """,
                (trigger_type, now),
            )
            return int(cursor.lastrowid)

    def complete_shopee_sync_run(
        self,
        run_id: int,
        status: str,
        clicks: int,
        conversions: int,
        new_orders: int,
        error: str | None = None,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE shopee_sync_runs
                SET status = ?, clicks_synced = ?, conversions_synced = ?,
                    new_orders_count = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, clicks, conversions, new_orders, error, now, run_id),
            )

    def get_last_sync_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM shopee_sync_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return None if row is None else dict(row)


def _row(row: sqlite3.Row) -> LinkRow:
    return LinkRow(
        id=row["id"],
        telegram_update_id=row["telegram_update_id"],
        telegram_user_id=row["telegram_user_id"],
        sub_id=row["sub_id"],
        affiliate_url=row["affiliate_url"],
        item_id=row["item_id"],
        product_name=row["product_name"],
        price_vnd=row["price_vnd"],
        estimated_commission=row["estimated_commission"],
        estimated_cashback=row["estimated_cashback"],
        cashback_rate_percent=row["cashback_rate_percent"],
        link_status=row["link_status"],
        reject_reason=row["reject_reason"],
        estimate_policy=row["estimate_policy"] if "estimate_policy" in row.keys() else None,
    )
