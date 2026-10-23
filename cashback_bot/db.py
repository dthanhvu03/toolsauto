"""SQLite riêng cho tracking. Không có ví, payout hay số dư."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

CREATE INDEX IF NOT EXISTS idx_shopee_conversions_sub_id ON shopee_conversions(sub_id);
CREATE INDEX IF NOT EXISTS idx_shopee_conversions_user_id ON shopee_conversions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_shopee_clicks_sub_id ON shopee_clicks(sub_id);
"""


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    def insert_created(self, fields: dict) -> int:
        fields = dict(fields)
        fields["delivery_status"] = "pending"
        return self._insert(fields)

    def insert_rejected(self, fields: dict) -> int:
        fields = dict(fields)
        fields["link_status"] = "rejected"
        fields.setdefault("sub_id", None)
        fields.setdefault("affiliate_url", None)
        return self._insert(fields)

    def _insert(self, fields: dict) -> int:
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
            return int(cursor.lastrowid)

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
    ) -> tuple[bool, bool, int | None, int | None]:
        """Lưu đơn hàng và đối soát sub_id.

        Trả về (is_new, is_matched, matched_link_id, telegram_user_id).
        """
        now = _utc_now()
        with self.connect() as conn:
            # Tìm link khớp sub_id
            matched_link_id = None
            telegram_user_id = None
            if sub_id:
                link = conn.execute(
                    "SELECT id, telegram_user_id FROM link_requests WHERE sub_id = ? ORDER BY id DESC LIMIT 1",
                    (sub_id,),
                ).fetchone()
                if link is not None:
                    matched_link_id = int(link["id"])
                    telegram_user_id = int(link["telegram_user_id"])

            is_matched = matched_link_id is not None

            # Kiểm tra xem đã có đơn này chưa
            existing = conn.execute(
                "SELECT conversion_id FROM shopee_conversions WHERE conversion_id = ?",
                (conversion_id,),
            ).fetchone()
            is_new = existing is None

            conn.execute(
                """
                INSERT INTO shopee_conversions (
                    conversion_id, sub_id, order_sn, order_status, conversion_status,
                    purchase_time, gross_commission_vnd, net_commission_vnd,
                    matched_link_id, telegram_user_id, raw_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversion_id) DO UPDATE SET
                    sub_id = excluded.sub_id,
                    order_sn = excluded.order_sn,
                    order_status = excluded.order_status,
                    conversion_status = excluded.conversion_status,
                    purchase_time = excluded.purchase_time,
                    gross_commission_vnd = excluded.gross_commission_vnd,
                    net_commission_vnd = excluded.net_commission_vnd,
                    matched_link_id = COALESCE(excluded.matched_link_id, shopee_conversions.matched_link_id),
                    telegram_user_id = COALESCE(excluded.telegram_user_id, shopee_conversions.telegram_user_id),
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    conversion_id,
                    sub_id,
                    order_sn,
                    order_status,
                    conversion_status,
                    purchase_time,
                    gross_commission_vnd,
                    net_commission_vnd,
                    matched_link_id,
                    telegram_user_id,
                    raw_json,
                    now,
                    now,
                ),
            )
            return is_new, is_matched, matched_link_id, telegram_user_id

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
