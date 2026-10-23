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
"""


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
        if fields.get("estimate_policy") and "estimate_policy" in self.column_names("link_requests"):
            columns.append("estimate_policy")
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
    ) -> sqlite3.Row:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO outbound_messages (
                    telegram_update_id, telegram_user_id, body_html, button_url, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(telegram_update_id) DO NOTHING
                """,
                (update_id, telegram_user_id, body_html, button_url, _utc_now()),
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
