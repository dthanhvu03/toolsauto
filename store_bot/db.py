"""SQLite của bot bán hàng. Mọi thay đổi tiền và kho đi qua một giao dịch BEGIN IMMEDIATE.

Bot Telegram và API đại lý là hai tiến trình dùng chung file này, nên mỗi thao tác mở kết nối riêng
(WAL + busy_timeout) thay vì giữ một kết nối dài.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(lower(username));

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL CHECK (price > 0),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    order_id INTEGER REFERENCES orders(id),
    added_at TEXT NOT NULL,
    sold_at TEXT,
    UNIQUE (product_id, content)
);
CREATE INDEX IF NOT EXISTS idx_stock_available ON stock_items(product_id, status, id);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    total INTEGER NOT NULL,
    source TEXT NOT NULL,
    api_key_id INTEGER REFERENCES api_keys(id),
    client_ref TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_ref ON orders(user_id, client_ref) WHERE client_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS topups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    code TEXT UNIQUE NOT NULL,
    amount INTEGER NOT NULL,
    credited INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    bank_ref TEXT UNIQUE,
    resolved_by TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    kind TEXT NOT NULL,
    ref TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    key_hash TEXT UNIQUE NOT NULL,
    prefix TEXT NOT NULL,
    discount_bps INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS api_key_blocks (
    key_id INTEGER NOT NULL REFERENCES api_keys(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    PRIMARY KEY (key_id, product_id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Khoản chi ngoài bot do admin tự ghi (bù khách, bảo hành, phí…): trừ vào lãi ròng và dòng tiền.
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER NOT NULL CHECK (amount > 0),
    note TEXT NOT NULL,
    order_id INTEGER REFERENCES orders(id),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expenses_created ON expenses(created_at);

-- Tiền admin nạp vào ví FatCat (vốn; số âm = rút về): đối chiếu với vốn đã dùng mua hàng + số dư FatCat thực.
CREATE TABLE IF NOT EXISTS capital (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER NOT NULL CHECK (amount <> 0),
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Cột thêm sau khi bot đã chạy thật (PLAN-097 bước 2: lấy hàng từ FatCat). migrate() tự ALTER khi thiếu.
ADDED_COLUMNS = {
    "users": {
        "notify_off": "INTEGER NOT NULL DEFAULT 0",  # khách tự tắt tin "HÀNG MỚI VỀ"
        "blocked_at": "TEXT",  # khách đã chặn bot (gửi tin bị 403); /start lại thì xoá
    },
    "products": {
        "upstream_id": "INTEGER",  # id sản phẩm bên FatCat; NULL = hàng tự nhập kho
        "upstream_cost": "INTEGER",  # giá FatCat tính cho mình (giá vốn)
        "upstream_stock": "INTEGER",
        "upstream_max": "INTEGER",  # số tối đa mỗi lượt mua bên FatCat
        "upstream_available": "INTEGER NOT NULL DEFAULT 1",  # FatCat còn mở bán cho khóa của mình
        "synced_at": "TEXT",
    },
    "orders": {
        "status": "TEXT NOT NULL DEFAULT 'done'",  # done · pending (chờ FatCat) · partial · failed
        "refunded": "INTEGER NOT NULL DEFAULT 0",
        "upstream_request_id": "TEXT",
        "upstream_order_id": "TEXT",
        "note": "TEXT",
        "updated_at": "TEXT",
        "unit_cost": "INTEGER",  # giá vốn 1 món lúc bán (hàng FatCat); NULL = hàng tự nhập, không tính vốn
        # 1 = khách đã trả, ví FatCat của shop chưa đủ nhập: chưa gọi FatCat, chờ admin nạp ví rồi bot tự lấy hàng.
        "waiting_funds": "INTEGER NOT NULL DEFAULT 0",
    },
    "topups": {
        # Thanh toán QR cho một đơn (mua thẳng không cần nạp ví trước): tiền vào là bot tự mua món này.
        "intent_product_id": "INTEGER",
        "intent_quantity": "INTEGER",
        # Giá 1 món lúc tạo QR: tiền về (trong 24 giờ mã còn hiệu lực) thì bán đúng giá này dù giá đã tăng.
        "intent_unit_price": "INTEGER",
    },
}
POST_MIGRATE = """
UPDATE orders SET unit_cost = (SELECT p.upstream_cost FROM products p WHERE p.id = orders.product_id)
    WHERE unit_cost IS NULL AND upstream_request_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_upstream ON products(upstream_id) WHERE upstream_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, id);
CREATE INDEX IF NOT EXISTS idx_topups_user_status ON topups(user_id, status);
CREATE INDEX IF NOT EXISTS idx_topups_status_created ON topups(status, created_at);
INSERT INTO order_items(order_id, content)
    SELECT s.order_id, s.content FROM stock_items s
    WHERE s.order_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM order_items o WHERE o.order_id = s.order_id);
"""
# Số tồn: hàng tự nhập đếm trong kho; hàng FatCat lấy theo lần đồng bộ gần nhất.
STOCK_SQL = """CASE WHEN p.upstream_id IS NULL
        THEN (SELECT COUNT(*) FROM stock_items s WHERE s.product_id = p.id AND s.status = 'available')
        ELSE COALESCE(p.upstream_stock, 0) END AS stock"""

ICT = timezone(timedelta(hours=7))
FUNDS_BASE_KEY = "funds_base"  # mốc đối chiếu ví FatCat: {"balance": số dư lẽ ra còn, "at": giờ đọc}
FUNDS_MIN_DELTA = 1_000  # lệch dưới mức này cộng dồn, chưa ghi sổ
FUNDS_QUIET_SEC = 120
AUTO_CAPITAL_BY = "auto"
TOPUP_CODE_RE = re.compile(r"NAP[A-Z0-9]{6}")
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # bỏ 0/O, 1/I dễ gõ nhầm
KEY_PREFIX = "sk_"


UPSTREAM_FUNDS_KEY = "upstream_balance"
AUTO_REFUND_NOTE = "tự hoàn sau 6 giờ chờ nhập hàng"


class StoreError(Exception):
    """Lỗi nghiệp vụ. code ổn định để bot và API dịch ra câu cho người đọc."""

    def __init__(self, code: str, **info):
        self.code = code
        self.info = info
        super().__init__(code)


@dataclass(frozen=True)
class User:
    user_id: int
    username: str | None
    first_name: str | None
    balance: int
    notify_off: bool = False

    @property
    def label(self) -> str:
        return f"@{self.username}" if self.username else (self.first_name or str(self.user_id))


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    description: str
    price: int
    active: bool
    stock: int
    upstream_id: int | None = None
    cost: int | None = None
    max_quantity: int | None = None
    available: bool = True

    @property
    def on_sale(self) -> bool:
        """Khách mua được: admin không ẩn và (nếu là hàng FatCat) FatCat còn mở bán."""
        return self.active and self.available


@dataclass(frozen=True)
class Order:
    id: int
    user_id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: int
    total: int
    source: str
    created_at: str
    items: list[str] = field(default_factory=list)
    balance_after: int | None = None
    replayed: bool = False
    status: str = "done"
    refunded: int = 0
    note: str | None = None
    waiting_funds: bool = False
    upstream_order_id: str | None = None  # mã đơn FatCat trả về (vd DH5FG3NW) — khách đưa mã này khi khiếu nại


@dataclass(frozen=True)
class Topup:
    id: int
    user_id: int
    code: str
    amount: int
    credited: int | None
    status: str
    created_at: str
    intent_product_id: int | None = None
    intent_quantity: int | None = None
    intent_unit_price: int | None = None
    resolved_by: str | None = None  # sepay · admin:<id> · user · expired


@dataclass(frozen=True)
class ApiKey:
    id: int
    user_id: int
    prefix: str
    discount_bps: int
    active: bool
    created_at: str
    last_used_at: str | None
    user_label: str = ""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unit_price(price: int, discount_bps: int) -> int:
    """Giá sau giảm, làm tròn giảm giá xuống (phần lẻ đồng thuộc về shop)."""
    return price - price * discount_bps // 10_000


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_lines(lines: Iterable[str]) -> list[str]:
    """Mỗi dòng không rỗng là một món; bỏ trùng trong cùng lần nhập, giữ thứ tự."""
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        text = line.strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


class StoreRepository:
    def __init__(self, path: str):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def migrate(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._read() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            for table, columns in ADDED_COLUMNS.items():
                have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                for column, ddl in columns.items():
                    if column not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.executescript(POST_MIGRATE)

    # ---------- state ----------

    def get_state(self, key: str) -> str | None:
        with self._read() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_state(self, key: str) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM state WHERE key = ?", (key,))

    def states_with_prefix(self, prefix: str) -> dict[str, str]:
        """Mọi state có khoá bắt đầu bằng `prefix` — một truy vấn (dùng khoảng khoá, đi theo chỉ mục)."""
        with self._read() as conn:
            rows = conn.execute("SELECT key, value FROM state WHERE key >= ? AND key < ?",
                                (prefix, prefix + "\U0010ffff")).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def upstream_funds(self) -> int | None:
        """Số dư ví FatCat lần đọc gần nhất (trừ dần theo đơn vừa đặt). None = chưa biết."""
        raw = self.get_state(UPSTREAM_FUNDS_KEY)
        return int(raw) if raw and raw.lstrip("-").isdigit() else None

    # ---------- users ----------

    def touch_user(self, user_id: int, username: str | None, first_name: str | None) -> User:
        now = utcnow()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO users(user_id, username, first_name, created_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET username = excluded.username,
                       first_name = excluded.first_name, last_seen_at = excluded.last_seen_at, blocked_at = NULL""",
                (user_id, username, first_name, now, now),
            )
            return _user(conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())

    def record_source(self, user_id: int, code: str) -> bool:
        """Ghi nguồn khách (mã ?start=, PLAN-153). Gọi khi khách mới /start lần đầu; đã có thì không ghi đè."""
        with self._tx() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO state(key, value) VALUES (?, ?)", (f"src:{user_id}", code))
            return cur.rowcount == 1

    def source_counts(self, days: int = 7) -> list[tuple[str, int]]:
        """Khách mới theo nguồn trong `days` ngày gần nhất."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self._read() as conn:
            rows = conn.execute(
                """SELECT s.value, COUNT(*) AS n FROM state s
                   JOIN users u ON u.user_id = CAST(substr(s.key, 5) AS INTEGER)
                   WHERE s.key >= 'src:' AND s.key < 'src;' AND u.created_at >= ?
                   GROUP BY s.value ORDER BY n DESC, s.value LIMIT 6""",
                (since,),
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def get_user(self, user_id: int) -> User | None:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return _user(row) if row else None

    def find_user(self, ref: str) -> User | None:
        """@username (không phân biệt hoa thường) hoặc ID Telegram. Khách phải từng /start bot."""
        ref = (ref or "").strip()
        with self._read() as conn:
            if ref.lstrip("-").isdigit():
                row = conn.execute("SELECT * FROM users WHERE user_id = ?", (int(ref),)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM users WHERE lower(username) = lower(?)", (ref.lstrip("@"),)
                ).fetchone()
        return _user(row) if row else None

    def set_notify(self, user_id: int, on: bool) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE users SET notify_off = ? WHERE user_id = ?", (0 if on else 1, user_id))

    def mark_blocked(self, user_id: int) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE users SET blocked_at = ? WHERE user_id = ?", (utcnow(), user_id))

    def broadcast_targets(self) -> list[int]:
        """Khách nhận tin hàng mới: chưa tắt, chưa chặn bot."""
        with self._read() as conn:
            return [row["user_id"] for row in conn.execute(
                "SELECT user_id FROM users WHERE notify_off = 0 AND blocked_at IS NULL ORDER BY user_id"
            )]

    def adjust_balance(self, user_id: int, delta: int, note: str, by: str) -> int:
        with self._tx() as conn:
            return _move_money(conn, user_id, delta, "adjust", by, note)

    # ---------- products & stock ----------

    def add_product(self, name: str, price: int, description: str = "") -> int:
        if price <= 0:
            raise StoreError("bad_price")
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO products(name, description, price, created_at) VALUES (?, ?, ?, ?)",
                (name.strip(), description.strip(), price, utcnow()),
            )
            return int(cur.lastrowid)

    def update_product(self, product_id: int, *, price: int | None = None, active: bool | None = None,
                       name: str | None = None, description: str | None = None) -> Product:
        if price is not None and price <= 0:
            raise StoreError("bad_price")
        with self._tx() as conn:
            if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise StoreError("product_not_found")
            for column, value in (("price", price), ("active", None if active is None else int(active)),
                                  ("name", name), ("description", description)):
                if value is not None:
                    conn.execute(f"UPDATE products SET {column} = ? WHERE id = ?", (value, product_id))
            return _load_product(conn, product_id)

    def get_product(self, product_id: int) -> Product | None:
        with self._read() as conn:
            return _load_product(conn, product_id)

    def list_products(self, include_inactive: bool = False) -> list[Product]:
        where = "" if include_inactive else "WHERE p.active = 1 AND p.upstream_available = 1"
        with self._read() as conn:
            rows = conn.execute(f"SELECT p.*, {STOCK_SQL} FROM products p {where} ORDER BY p.id").fetchall()
        return [_product(row) for row in rows]

    def add_stock(self, product_id: int, lines: Iterable[str]) -> tuple[int, int, int]:
        """Trả (số món thêm được, số món trùng bỏ qua, tồn kho sau khi thêm)."""
        items = clean_lines(lines)
        now = utcnow()
        with self._tx() as conn:
            if not conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone():
                raise StoreError("product_not_found")
            added = 0
            for content in items:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO stock_items(product_id, content, added_at) VALUES (?, ?, ?)",
                    (product_id, content, now),
                )
                added += cur.rowcount
            stock = _stock(conn, product_id)
        return added, len(items) - added, stock

    # ---------- orders ----------

    def buy(self, user_id: int, product_id: int, quantity: int, client_ref: str | None = None, *,
            discount_bps: int = 0, source: str = "bot", api_key_id: int | None = None,
            locked_unit_price: int | None = None) -> Order:
        """Trừ tiền + lấy hàng trong cùng một giao dịch. client_ref trùng thì trả lại đơn cũ, không mua lần hai."""
        if quantity < 1:
            raise StoreError("bad_quantity")
        with self._tx() as conn:
            if client_ref:
                row = conn.execute(
                    "SELECT id FROM orders WHERE user_id = ? AND client_ref = ?", (user_id, client_ref)
                ).fetchone()
                if row:
                    return _load_order(conn, row["id"], replayed=True)
            product = _load_product(conn, product_id)
            if product is None:
                raise StoreError("product_not_found")
            if not product.on_sale:
                raise StoreError("product_inactive")
            if api_key_id is not None and conn.execute(
                "SELECT 1 FROM api_key_blocks WHERE key_id = ? AND product_id = ?", (api_key_id, product_id)
            ).fetchone():
                raise StoreError("product_blocked")
            if product.stock < quantity:
                raise StoreError("out_of_stock", available=product.stock)
            funds = _upstream_funds(conn) if product.upstream_id is not None and product.cost else None
            # Ví FatCat không đủ nhập: vẫn bán, nhưng giữ đơn chờ admin nạp ví — không gọi FatCat để khỏi bị 402
            # rồi hoàn tiền bắt khách mua lại (sự cố 04/11 đơn #2 #3).
            waiting = funds is not None and funds < product.cost * quantity
            if product.max_quantity and quantity > product.max_quantity:
                raise StoreError("bad_quantity", max=product.max_quantity)
            unit = unit_price(product.price, discount_bps)
            if locked_unit_price:
                unit = min(unit, locked_unit_price)  # giá đã báo trên QR; giá giảm thì khách được giá mới
            if product.cost:
                unit = max(unit, product.cost)  # giảm cho đại lý cấp dưới không bao giờ bán dưới giá vốn
            total = unit * quantity
            balance = _balance(conn, user_id)
            if balance < total:
                raise StoreError("insufficient_balance", need=total, balance=balance)
            now = utcnow()
            upstream = product.upstream_id is not None
            # request_id ngẫu nhiên: DB có bị làm lại thì id đơn lặp lại cũng không đụng đơn cũ bên FatCat.
            request_id = f"aps-{secrets.token_hex(8)}" if upstream else None
            order_id = int(conn.execute(
                """INSERT INTO orders(user_id, product_id, product_name, quantity, unit_price, total, source,
                                      api_key_id, client_ref, created_at, status, upstream_request_id, updated_at,
                                      unit_cost, waiting_funds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, product_id, product.name, quantity, unit, total, source, api_key_id, client_ref, now,
                 "pending" if upstream else "done", request_id, now, product.cost, int(waiting)),
            ).lastrowid)
            if not upstream:
                item_ids = [row["id"] for row in conn.execute(
                    "SELECT id FROM stock_items WHERE product_id = ? AND status = 'available' ORDER BY id LIMIT ?",
                    (product_id, quantity),
                )]
                conn.executemany(
                    "UPDATE stock_items SET status = 'sold', order_id = ?, sold_at = ? WHERE id = ? AND status = 'available'",
                    [(order_id, now, item_id) for item_id in item_ids],
                )
                conn.execute(
                    "INSERT INTO order_items(order_id, content) SELECT ?, content FROM stock_items WHERE order_id = ? ORDER BY id",
                    (order_id, order_id),
                )
            _move_money(conn, user_id, -total, "order", f"order:{order_id}", product.name)
            if funds is not None and not waiting:
                # Giữ chỗ trong ví FatCat để hai đơn cùng lúc không vượt số dư; lần đồng bộ sau ghi lại số thật.
                conn.execute("UPDATE state SET value = ? WHERE key = ?",
                             (str(funds - product.cost * quantity), UPSTREAM_FUNDS_KEY))
            return _load_order(conn, order_id)

    # ---------- đơn lấy từ FatCat ----------

    def upstream_job(self, order_id: int) -> tuple[int, int, str] | None:
        """(id sản phẩm FatCat, số lượng, request_id) của đơn đang chờ; None nếu đơn đã xong / đang chờ ví."""
        with self._read() as conn:
            row = conn.execute(
                """SELECT p.upstream_id, o.quantity, o.upstream_request_id FROM orders o
                   JOIN products p ON p.id = o.product_id
                   WHERE o.id = ? AND o.status = 'pending' AND o.waiting_funds = 0""",
                (order_id,),
            ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def pending_upstream_orders(self, older_than_sec: int) -> list[int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)).isoformat(timespec="seconds")
        with self._read() as conn:
            return [row["id"] for row in conn.execute(
                "SELECT id FROM orders WHERE status = 'pending' AND waiting_funds = 0 AND created_at <= ? ORDER BY id",
                (cutoff,),
            )]

    def cleanup_state(self, now: float, keep_sec: int = 24 * 3600) -> int:
        """Dọn khoá state hết tác dụng (vòng nền gọi mỗi giờ). Trả số dòng đã xoá. Không đụng src:/menu_sent:/icon:/markup.
        - stuck_alerted:<đơn> khi đơn hết chờ · topup_msg:<mã> khi mã nạp đã xong
        - announced:<món> / callme:<khách> (giá trị = thời điểm) cũ hơn keep_sec
        - await:<khách> (đang chờ gõ chữ) của khách không hoạt động quá keep_sec"""
        cutoff_iso = datetime.fromtimestamp(now - keep_sec, timezone.utc).isoformat(timespec="seconds")
        with self._tx() as conn:
            deleted = 0
            for sql, args in (
                ("""DELETE FROM state WHERE key >= 'stuck_alerted:' AND key < 'stuck_alerted;'
                    AND CAST(substr(key, 15) AS INTEGER) NOT IN (SELECT id FROM orders WHERE status = 'pending')""", ()),
                ("""DELETE FROM state WHERE key >= 'topup_msg:' AND key < 'topup_msg;'
                    AND CAST(substr(key, 11) AS INTEGER) NOT IN (SELECT id FROM topups WHERE status = 'pending')""", ()),
                ("""DELETE FROM state WHERE ((key >= 'announced:' AND key < 'announced;')
                                            OR (key >= 'callme:' AND key < 'callme;'))
                    AND CAST(value AS REAL) < ?""", (now - keep_sec,)),
                ("""DELETE FROM state WHERE key >= 'await:' AND key < 'await;'
                    AND CAST(substr(key, 7) AS INTEGER) IN (SELECT user_id FROM users WHERE last_seen_at < ?)""",
                 (cutoff_iso,)),
            ):
                deleted += conn.execute(sql, args).rowcount
            return deleted

    def has_order_ref(self, user_id: int, client_ref: str) -> bool:
        with self._read() as conn:
            return conn.execute("SELECT 1 FROM orders WHERE user_id = ? AND client_ref = ?",
                                (user_id, client_ref)).fetchone() is not None

    def waiting_summary(self) -> tuple[int, int]:
        """(số đơn chờ ví, tổng vốn cần nạp) — một truy vấn, không tải cả đơn (vòng nền gọi mỗi 10 giây)."""
        with self._read() as conn:
            row = conn.execute(
                """SELECT COUNT(*), SUM(COALESCE(unit_cost, 0) * quantity) FROM orders
                   WHERE status = 'pending' AND waiting_funds = 1"""
            ).fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    def waiting_orders(self) -> list[Order]:
        """Đơn khách đã trả, đang chờ admin nạp ví FatCat (cũ trước)."""
        with self._read() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM orders WHERE status = 'pending' AND waiting_funds = 1 ORDER BY id")]
            return [_load_order(conn, order_id) for order_id in ids]

    def release_waiting(self) -> list[int]:
        """Ví FatCat đủ lại: mở các đơn chờ (cũ trước) vừa đủ số dư, giữ chỗ ví cho từng đơn. Trả id đơn được mở."""
        released = []
        if not self.waiting_summary()[0]:
            return released  # không giữ khoá ghi mỗi 10 giây khi chẳng có đơn chờ
        with self._tx() as conn:
            funds = _upstream_funds(conn)
            if funds is None:
                return []
            for row in conn.execute(
                """SELECT id, quantity, COALESCE(unit_cost, 0) AS cost FROM orders
                   WHERE status = 'pending' AND waiting_funds = 1 ORDER BY id"""
            ).fetchall():
                need = row["cost"] * row["quantity"]
                if need > funds:
                    break  # giữ thứ tự: đơn trước chưa đủ thì đơn sau cũng chờ
                funds -= need
                conn.execute("UPDATE orders SET waiting_funds = 0, updated_at = ? WHERE id = ?", (utcnow(), row["id"]))
                released.append(row["id"])
            if released:
                conn.execute("UPDATE state SET value = ? WHERE key = ?", (str(funds), UPSTREAM_FUNDS_KEY))
        return released

    def wait_for_funds(self, order_id: int) -> tuple[Order, bool]:
        """FatCat báo 402 (ví shop thiếu, FatCat KHÔNG trừ tiền): giữ đơn chờ ví thay vì hoàn tiền.
        Đổi request_id mới vì id cũ đã bị từ chối. Trả (đơn, vừa chuyển sang chờ không)."""
        with self._tx() as conn:
            cur = conn.execute(
                """UPDATE orders SET waiting_funds = 1, upstream_request_id = ?, updated_at = ?
                   WHERE id = ? AND status = 'pending' AND waiting_funds = 0""",
                (f"aps-{secrets.token_hex(8)}", utcnow(), order_id),
            )
            return _load_order(conn, order_id), cur.rowcount == 1

    def expire_waiting(self, older_than_sec: int) -> list[Order]:
        """Đơn chờ ví quá lâu (admin chưa nạp): tự hoàn đủ vào số dư khách. Trả các đơn vừa hoàn."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)).isoformat(timespec="seconds")
        with self._read() as conn:
            rows = conn.execute(
                "SELECT id, user_id FROM orders WHERE status = 'pending' AND waiting_funds = 1 AND created_at < ?",
                (cutoff,),
            ).fetchall()
        done = []
        for row in rows:
            order = self.cancel_waiting(row["id"], row["user_id"], note=AUTO_REFUND_NOTE)
            if order is not None:
                done.append(order)
        return done

    def cancel_waiting(self, order_id: int, user_id: int, note: str = "khách huỷ khi chờ nhập hàng") -> Order | None:
        """Huỷ đơn đang chờ ví (khách bấm huỷ / quá hạn), hoàn đủ vào số dư. Đơn đã được mở lấy hàng thì không huỷ."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ? AND user_id = ? AND status = 'pending' AND waiting_funds = 1",
                (order_id, user_id),
            ).fetchone()
            if row is None:
                return None
            _move_money(conn, user_id, row["total"], "refund", f"order:{order_id}", note)
            conn.execute(
                """UPDATE orders SET status = 'failed', refunded = ?, waiting_funds = 0, note = ?, updated_at = ?
                   WHERE id = ?""",
                (row["total"], note, utcnow(), order_id),
            )
            return _load_order(conn, order_id)

    def complete_upstream(self, order_id: int, items: list[str], upstream_order_id: str | None) -> tuple[Order, bool]:
        """Ghi hàng FatCat giao. Thiếu món nào hoàn tiền món đó cho khách. Chỉ chạy một lần mỗi đơn."""
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row["status"] != "pending":
                return _load_order(conn, order_id), False
            items = items[: row["quantity"]]
            conn.executemany("INSERT INTO order_items(order_id, content) VALUES (?, ?)",
                             [(order_id, item) for item in items])
            missing = row["quantity"] - len(items)
            refund = missing * row["unit_price"]
            status = "done" if not missing else ("partial" if items else "failed")
            if refund:
                _move_money(conn, row["user_id"], refund, "refund", f"order:{order_id}", f"thiếu {missing} món")
            conn.execute(
                "UPDATE orders SET status = ?, refunded = ?, upstream_order_id = ?, updated_at = ? WHERE id = ?",
                (status, refund, upstream_order_id, utcnow(), order_id),
            )
            conn.execute(
                "UPDATE products SET upstream_stock = MAX(COALESCE(upstream_stock, 0) - ?, 0) WHERE id = ?",
                (len(items), row["product_id"]),
            )
            return _load_order(conn, order_id), True

    def fail_upstream(self, order_id: int, note: str) -> tuple[Order, bool]:
        """FatCat từ chối chắc chắn (không trừ tiền bên đó): hoàn đủ cho khách. Chỉ chạy một lần mỗi đơn."""
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row["status"] != "pending":
                return _load_order(conn, order_id), False
            _move_money(conn, row["user_id"], row["total"], "refund", f"order:{order_id}", note[:200])
            conn.execute(
                "UPDATE orders SET status = 'failed', refunded = ?, note = ?, updated_at = ? WHERE id = ?",
                (row["total"], note[:200], utcnow(), order_id),
            )
            return _load_order(conn, order_id), True

    def sync_upstream(self, rows: list[dict], price_fn) -> list[tuple[Product, int]]:
        """Cập nhật sản phẩm theo danh sách FatCat; giá bán = price_fn(giá vốn, upstream_id).
        Trả [(sản phẩm, số tăng)] cho món vừa có thêm hàng.
        Món FatCat không trả về nữa thì ẩn (upstream_available = 0), không xoá để giữ lịch sử đơn."""
        now = utcnow()
        restocked: list[tuple[Product, int]] = []
        with self._tx() as conn:
            seen: set[int] = set()
            for item in rows:
                upstream_id = int(item["id"])
                seen.add(upstream_id)
                cost = int(item.get("regular_price_vnd") or item["price_vnd"])
                stock = max(int(item.get("stock") or 0), 0)
                values = (str(item.get("name") or f"#{upstream_id}").strip(), str(item.get("description") or "").strip(),
                          price_fn(cost, upstream_id), cost, stock, item.get("max_quantity"), now)
                old = conn.execute(
                    "SELECT id, upstream_stock, upstream_available FROM products WHERE upstream_id = ?", (upstream_id,)
                ).fetchone()
                if old is None:
                    conn.execute(
                        """INSERT INTO products(name, description, price, upstream_cost, upstream_stock, upstream_max,
                                                synced_at, upstream_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (*values, upstream_id, now),
                    )
                    continue
                product_id = old["id"]
                conn.execute(
                    """UPDATE products SET name = ?, description = ?, price = ?, upstream_cost = ?, upstream_stock = ?,
                              upstream_max = ?, synced_at = ?, upstream_available = 1 WHERE id = ?""",
                    (*values, product_id),
                )
                before = old["upstream_stock"] if old["upstream_available"] else 0
                if before is not None and stock > before:
                    restocked.append((_load_product(conn, product_id), stock - before))
            for row in conn.execute("SELECT id, upstream_id FROM products WHERE upstream_id IS NOT NULL").fetchall():
                if row["upstream_id"] not in seen:
                    conn.execute("UPDATE products SET upstream_available = 0, upstream_stock = 0 WHERE id = ?", (row["id"],))
        return restocked

    def reprice_upstream(self, price_fn) -> int:
        """Tính lại giá bán mọi món FatCat từ giá vốn đã lưu (admin vừa đổi mức tăng giá). Trả số món đổi giá."""
        changed = 0
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT id, price, upstream_id, upstream_cost FROM products WHERE upstream_id IS NOT NULL "
                "AND upstream_cost IS NOT NULL").fetchall()
            for row in rows:
                price = price_fn(row["upstream_cost"], row["upstream_id"])
                if price != row["price"]:
                    conn.execute("UPDATE products SET price = ? WHERE id = ?", (price, row["id"]))
                    changed += 1
        return changed

    def sales_by_product(self, days: int = 30, since: str | None = None,
                         exclude: Iterable[int] = ()) -> dict[int, tuple[int, int, int]]:
        """{product_id: (số món đã giao, tiền khách trả, tiền vốn)} trong `days` ngày gần nhất (hoặc từ mốc `since`)."""
        if since is None:
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        not_admin, args = _not_in(exclude)
        with self._read() as conn:
            rows = conn.execute(
                f"""SELECT product_id, SUM(items), SUM(total - refunded), SUM(COALESCE(unit_cost, 0) * items)
                   FROM (SELECT o.product_id, o.total, o.refunded, o.unit_cost,
                                (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS items
                         FROM orders o WHERE o.status IN ('done', 'partial') AND o.created_at >= ?
                         AND o.user_id {not_admin})
                   WHERE items > 0 GROUP BY product_id""",
                (since, *args),
            ).fetchall()
        return {row[0]: (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)) for row in rows}

    def get_order(self, order_id: int, user_id: int | None = None) -> Order | None:
        with self._read() as conn:
            row = conn.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None or (user_id is not None and row["user_id"] != user_id):
                return None
            return _load_order(conn, order_id)

    def list_orders(self, user_id: int, limit: int = 10) -> list[Order]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
        return [_order(row) for row in rows]

    # ---------- topups ----------

    def create_topup(self, user_id: int, amount: int, product_id: int | None = None,
                     quantity: int | None = None, unit_price: int | None = None) -> Topup:
        with self._tx() as conn:
            for _ in range(10):
                code = "NAP" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
                try:
                    cur = conn.execute(
                        """INSERT INTO topups(user_id, code, amount, created_at, intent_product_id, intent_quantity,
                                              intent_unit_price)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (user_id, code, amount, utcnow(), product_id, quantity, unit_price),
                    )
                except sqlite3.IntegrityError:
                    continue
                return _topup(conn.execute("SELECT * FROM topups WHERE id = ?", (cur.lastrowid,)).fetchone())
        raise StoreError("topup_code_exhausted")

    def find_pending_topup(self, user_id: int, amount: int, product_id: int | None, quantity: int | None,
                           max_age_sec: int) -> Topup | None:
        """Mã nạp còn chờ y hệt (cùng số tiền, cùng món) để khách bấm QR lại thì dùng lại, không đẻ mã mới."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_sec)).isoformat(timespec="seconds")
        with self._read() as conn:
            row = conn.execute(
                """SELECT * FROM topups WHERE user_id = ? AND status = 'pending' AND amount = ? AND created_at >= ?
                   AND intent_product_id IS ? AND intent_quantity IS ? ORDER BY id DESC LIMIT 1""",
                (user_id, amount, cutoff, product_id, quantity),
            ).fetchone()
        return _topup(row) if row else None

    def latest_pending_topup(self, user_id: int) -> Topup | None:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM topups WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (user_id,)
            ).fetchone()
        return _topup(row) if row else None

    def expire_topups(self, older_than_sec: int) -> list[int]:
        """Huỷ mã nạp chờ quá lâu, trả id các mã vừa huỷ. Tiền lỡ về mã quá hạn vẫn được cộng (confirm_topup)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)).isoformat(timespec="seconds")
        with self._read() as conn:
            if not conn.execute("SELECT 1 FROM topups WHERE status = 'pending' AND created_at < ? LIMIT 1",
                                (cutoff,)).fetchone():
                return []  # thường gặp: không mở giao dịch ghi
        with self._tx() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM topups WHERE status = 'pending' AND created_at < ?", (cutoff,))]
            conn.executemany(
                "UPDATE topups SET status = 'cancelled', resolved_by = 'expired', resolved_at = ? WHERE id = ? "
                "AND status = 'pending'",
                [(utcnow(), i) for i in ids],
            )
            return ids

    def get_topup(self, topup_id: int) -> Topup | None:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM topups WHERE id = ?", (topup_id,)).fetchone()
        return _topup(row) if row else None

    def find_topup_in_text(self, text: str) -> Topup | None:
        """Tìm mã NAPxxxxxx trong nội dung chuyển khoản (ngân hàng hay chèn dấu, viết thường)."""
        squashed = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
        with self._read() as conn:
            for code in TOPUP_CODE_RE.findall(squashed):
                row = conn.execute("SELECT * FROM topups WHERE code = ?", (code,)).fetchone()
                if row:
                    return _topup(row)
        return None

    def bank_ref_seen(self, bank_ref: str) -> bool:
        with self._read() as conn:
            return conn.execute("SELECT 1 FROM topups WHERE bank_ref = ?", (bank_ref,)).fetchone() is not None

    def pending_topups(self, limit: int = 20) -> list[Topup]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM topups WHERE status = 'pending' ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_topup(row) for row in rows]

    def confirm_topup(self, topup_id: int, by: str, credited: int | None = None,
                      bank_ref: str | None = None) -> tuple[Topup, int, bool]:
        """Cộng tiền một lần. Trả (topup, số dư, có cộng mới không). Bấm lại / webhook gửi lại thì không cộng nữa."""
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM topups WHERE id = ?", (topup_id,)).fetchone()
            if row is None:
                raise StoreError("topup_not_found")
            already_used = bank_ref and conn.execute(
                "SELECT 1 FROM topups WHERE bank_ref = ?", (bank_ref,)
            ).fetchone()
            # Khách tự huỷ / mã quá 24 giờ mà tiền vẫn về: vẫn cộng vào ví, nhưng bỏ ý định mua (khách có thể đã
            # chọn món khác). Mã admin huỷ thì không tự cộng.
            revived = row["status"] == "cancelled" and row["resolved_by"] in ("user", "expired")
            if (row["status"] != "pending" and not revived) or already_used:
                return _topup(row), _balance(conn, row["user_id"]), False
            amount = row["amount"] if credited is None else credited
            if amount <= 0:
                raise StoreError("bad_amount")
            conn.execute(
                """UPDATE topups SET status = 'paid', credited = ?, bank_ref = ?, resolved_by = ?, resolved_at = ?,
                          intent_product_id = CASE WHEN ? THEN NULL ELSE intent_product_id END
                   WHERE id = ?""",
                (amount, bank_ref, by, utcnow(), revived, topup_id),
            )
            balance = _move_money(conn, row["user_id"], amount, "topup", f"topup:{row['code']}", by)
            return _topup(conn.execute("SELECT * FROM topups WHERE id = ?", (topup_id,)).fetchone()), balance, True

    def cancel_topup(self, topup_id: int, by: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE topups SET status = 'cancelled', resolved_by = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
                (by, utcnow(), topup_id),
            )
            return cur.rowcount == 1

    # ---------- API keys ----------

    def issue_key(self, user_id: int, discount_bps: int) -> tuple[str, ApiKey]:
        """Cấp khóa mới, thu hồi khóa cũ của cùng người. Chỉ lưu hash: khóa thô trả về đúng một lần.
        Danh sách sản phẩm bị chặn được chép sang khóa mới để cấp lại không mở chặn."""
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        now = utcnow()
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                raise StoreError("user_not_found")
            old_ids = [row["id"] for row in conn.execute(
                "SELECT id FROM api_keys WHERE user_id = ? AND active = 1", (user_id,)
            )]
            conn.execute("UPDATE api_keys SET active = 0, revoked_at = ? WHERE user_id = ? AND active = 1", (now, user_id))
            key_id = int(conn.execute(
                "INSERT INTO api_keys(user_id, key_hash, prefix, discount_bps, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, hash_key(raw), raw[:10], discount_bps, now),
            ).lastrowid)
            for old_id in old_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO api_key_blocks(key_id, product_id) SELECT ?, product_id FROM api_key_blocks WHERE key_id = ?",
                    (key_id, old_id),
                )
            return raw, _load_key(conn, key_id)

    def key_for_raw(self, raw: str) -> ApiKey | None:
        if not raw or not raw.startswith(KEY_PREFIX):
            return None
        with self._tx() as conn:
            row = conn.execute(
                "SELECT id FROM api_keys WHERE key_hash = ? AND active = 1", (hash_key(raw),)
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (utcnow(), row["id"]))
            return _load_key(conn, row["id"])

    def get_key(self, key_id: int) -> ApiKey | None:
        with self._read() as conn:
            return _load_key(conn, key_id)

    def list_keys(self) -> list[ApiKey]:
        with self._read() as conn:
            ids = [row["id"] for row in conn.execute("SELECT id FROM api_keys WHERE active = 1 ORDER BY id")]
            return [_load_key(conn, key_id) for key_id in ids]

    def revoke_key(self, key_id: int) -> bool:
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET active = 0, revoked_at = ? WHERE id = ? AND active = 1", (utcnow(), key_id)
            )
            return cur.rowcount == 1

    def set_discount(self, key_id: int, discount_bps: int) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE api_keys SET discount_bps = ? WHERE id = ?", (discount_bps, key_id))

    def blocked_products(self, key_id: int) -> set[int]:
        with self._read() as conn:
            return {row["product_id"] for row in conn.execute(
                "SELECT product_id FROM api_key_blocks WHERE key_id = ?", (key_id,)
            )}

    def toggle_block(self, key_id: int, product_id: int) -> bool:
        """Đảo trạng thái chặn. Trả True nếu sau khi đảo là đang chặn."""
        with self._tx() as conn:
            cur = conn.execute(
                "DELETE FROM api_key_blocks WHERE key_id = ? AND product_id = ?", (key_id, product_id)
            )
            if cur.rowcount:
                return False
            conn.execute("INSERT INTO api_key_blocks(key_id, product_id) VALUES (?, ?)", (key_id, product_id))
            return True

    # ---------- stats ----------

    def stats(self, admins: Iterable[int] = ()) -> dict[str, int]:
        """Số liệu admin. Doanh thu chỉ tính đơn đã giao (trừ phần hoàn); vốn = giá vốn × số món thực giao.
        `admins`: tài khoản admin — tiền tự nạp / tự mua của admin không tính là của khách."""
        not_admin, args = _not_in(admins)
        today = datetime.now(ICT).replace(hour=0, minute=0, second=0, microsecond=0)
        periods = {
            "today": today.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "7d": (today - timedelta(days=6)).astimezone(timezone.utc).isoformat(timespec="seconds"),
            "all": "",
        }
        with self._read() as conn:
            def one(sql: str, *args) -> int:
                return int(conn.execute(sql, args).fetchone()[0] or 0)

            result = {
                "users": one("SELECT COUNT(*) FROM users"),
                "buyers": one("SELECT COUNT(DISTINCT user_id) FROM orders WHERE status IN ('done', 'partial')"),
                "balances": one(f"SELECT SUM(balance) FROM users WHERE user_id {not_admin}", *args),
                "pending_topups": one("SELECT COUNT(*) FROM topups WHERE status = 'pending'"),
                "pending_orders": one("SELECT COUNT(*) FROM orders WHERE status = 'pending'"),
                "stock": one("SELECT COUNT(*) FROM stock_items WHERE status = 'available'"),
            }
            for name, since in periods.items():
                row = conn.execute(
                    f"""SELECT COUNT(*), SUM(o.total - o.refunded), SUM(COALESCE(o.unit_cost, 0) * {_SOLD_SQL})
                        FROM orders o WHERE o.status IN ('done', 'partial') AND o.created_at >= ?
                        AND o.user_id {not_admin}""",
                    (since, *args),
                ).fetchone()
                result[f"orders_{name}"] = int(row[0] or 0)
                result[f"revenue_{name}"] = int(row[1] or 0)
                result[f"cost_{name}"] = int(row[2] or 0)
                result[f"expense_{name}"] = one("SELECT SUM(amount) FROM expenses WHERE created_at >= ?", since)
                result[f"profit_{name}"] = result[f"revenue_{name}"] - result[f"cost_{name}"] - result[f"expense_{name}"]
                result[f"topup_{name}"] = one(
                    f"SELECT SUM(credited) FROM topups WHERE status = 'paid' AND resolved_at >= ? AND user_id {not_admin}",
                    since, *args)
                result[f"refunded_{name}"] = one(
                    "SELECT SUM(refunded) FROM orders WHERE refunded > 0 AND created_at >= ?", since)
            return result

    def cashflow(self, days: int | None = 7, top: int = 5, admins: Iterable[int] = ()) -> dict:
        """Báo cáo «Dòng tiền & biên lãi» cho một kỳ: `days` ngày tính theo lịch VN (1 = hôm nay), None = từ đầu.
        Trả tổng kỳ, kỳ liền trước (để so sánh), diễn biến (ngày ≤ 7 ngày · tuần với 30 ngày · tháng với từ đầu),
        món lãi nhất trong kỳ, tiền đang giữ hộ khách. Cách tính như stats(): doanh thu = đơn đã giao trừ phần hoàn,
        vốn = giá vốn × số món thực giao (hàng tự nhập không có giá vốn).
        `admins`: tiền admin tự nạp / tự mua tách riêng thành «admin», không tính vào khách."""
        admins = tuple(admins)
        not_admin, args = _not_in(admins)
        today = datetime.now(ICT).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._read() as conn:
            if days is None:
                first = conn.execute(
                    "SELECT MIN(t) FROM (SELECT MIN(created_at) AS t FROM orders "
                    "UNION ALL SELECT MIN(resolved_at) FROM topups WHERE status = 'paid' "
                    "UNION ALL SELECT MIN(created_at) FROM expenses)").fetchone()[0]
                first_day = (datetime.fromisoformat(first).astimezone(ICT).replace(hour=0, minute=0, second=0,
                                                                                  microsecond=0)
                             if first else today)
            else:
                first_day = today - timedelta(days=days - 1)
            start = _utc_iso(first_day)
            daily = _daily_totals(conn, start, None, admins)
            previous = (_sum_totals(_daily_totals(conn, _utc_iso(first_day - timedelta(days=days)), start, admins)
                                    .values()) if days else None)
            admin_total = (_sum_totals(_daily_totals(conn, start, None, admins, admin_side=True).values())
                           if admins else None)
            balances = int(conn.execute(f"SELECT SUM(balance) FROM users WHERE user_id {not_admin}",
                                        args).fetchone()[0] or 0)
            admin_balance = (int(conn.execute(f"SELECT SUM(balance) FROM users WHERE NOT (user_id {not_admin})",
                                              args).fetchone()[0] or 0) if admins else 0)
            capital = int(conn.execute("SELECT SUM(amount) FROM capital").fetchone()[0] or 0)
            capital_count = int(conn.execute("SELECT COUNT(*) FROM capital").fetchone()[0] or 0)
            used_all = int(conn.execute(
                f"""SELECT SUM(COALESCE(o.unit_cost, 0) * {_SOLD_SQL}) FROM orders o
                    WHERE o.status IN ('done', 'partial')""").fetchone()[0] or 0)
            names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM products")}

        span = (today - first_day).days + 1
        day_keys = [(today - timedelta(days=back)).date().isoformat() for back in range(span)]  # mới nhất trước
        if days is None:
            unit, groups = "month", {}
            for key in day_keys:
                groups.setdefault(key[:7], []).append(key)
        elif days > 7:
            unit, groups = "week", {}
            for i in range(0, len(day_keys), 7):
                chunk = day_keys[i:i + 7]
                groups[f"{chunk[-1]}|{chunk[0]}"] = chunk
        else:
            unit, groups = "day", {key: [key] for key in day_keys} if days > 1 else {}
        buckets = [{"key": key, **_sum_totals(daily.get(k, {}) for k in keys)} for key, keys in groups.items()]

        products = [
            {"name": names.get(pid, f"#{pid}"), "sold": n, "revenue": revenue, "profit": revenue - cost}
            for pid, (n, revenue, cost) in self.sales_by_product(since=start, exclude=admins).items()
        ]
        waiting_orders, waiting_cost = self.waiting_summary()
        return {
            "days": days,
            "from": first_day.date().isoformat(),
            "to": today.date().isoformat(),
            "total": _sum_totals(daily.values()),
            "previous": previous,
            "unit": unit,
            "buckets": buckets,
            "top": sorted(products, key=lambda p: p["profit"], reverse=True)[:top],
            "balances": balances,
            "admin": admin_total,  # None = không tách admin
            "admin_balance": admin_balance,
            "capital": capital,  # tổng admin đã ghi nạp ví FatCat (từ đầu)
            "capital_count": capital_count,
            "capital_used": used_all,  # vốn FatCat đã dùng cho mọi đơn đã giao (cả đơn admin tự mua), từ đầu
            "waiting_orders": waiting_orders,
            "waiting_cost": waiting_cost,
        }

    # ---------- khoản chi ngoài bot ----------

    def add_expense(self, amount: int, note: str, by: str, order_id: int | None = None) -> int:
        if amount <= 0 or not note.strip():
            raise StoreError("bad_amount")
        with self._tx() as conn:
            if order_id is not None and conn.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,)).fetchone() is None:
                order_id = None
            cur = conn.execute(
                "INSERT INTO expenses(amount, note, order_id, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (amount, note.strip()[:200], order_id, by, utcnow()),
            )
            return int(cur.lastrowid)

    def recent_expenses(self, limit: int = 10) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def delete_expense(self, expense_id: int) -> bool:
        """Xoá khoản admin ghi nhầm (chỉ bảng expenses, không đụng ví khách / đơn)."""
        with self._tx() as conn:
            return conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,)).rowcount > 0

    # ---------- vốn nạp ví FatCat ----------

    def add_capital(self, amount: int, note: str, by: str) -> int:
        if amount == 0:
            raise StoreError("bad_amount")
        with self._tx() as conn:
            cur = conn.execute("INSERT INTO capital(amount, note, created_by, created_at) VALUES (?, ?, ?, ?)",
                               (amount, note.strip()[:200], by, utcnow()))
            return int(cur.lastrowid)

    def reconcile_funds(self, balance: int, read_at: datetime) -> int | None:
        """Tự đối chiếu ví FatCat sau mỗi lần đọc số dư. Lẽ ra còn = mốc trước − giá vốn đơn bot giao từ mốc đó;
        số dư thực lệch ≥ FUNDS_MIN_DELTA → tự ghi một dòng sổ vốn (dương: anh nạp / FatCat hoàn; âm: FatCat trừ
        ngoài bot, vd anh mua thẳng). Chỉ đối chiếu lúc yên: không có đơn đang gọi FatCat và không đơn nào vừa đổi
        trạng thái trong FUNDS_QUIET_SEC giây (tránh tính đơn FatCat đã trừ mà bot chưa ghi). Lệch nhỏ cộng dồn.
        Lần đầu chỉ đặt mốc. Trả id dòng sổ vốn vừa ghi, hoặc None."""
        read_iso = read_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._tx() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = ?", (FUNDS_BASE_KEY,)).fetchone()
            base = json.loads(row["value"]) if row else None

            def save(expected: int) -> None:
                conn.execute(
                    "INSERT INTO state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (FUNDS_BASE_KEY, json.dumps({"balance": expected, "at": read_iso})))

            if base is None:
                save(balance)
                return None
            if read_iso < base["at"]:
                return None  # số đọc cũ hơn mốc (tiến trình kia vừa đối chiếu)
            quiet_from = (read_at - timedelta(seconds=FUNDS_QUIET_SEC)).astimezone(timezone.utc).isoformat(
                timespec="seconds")
            busy = conn.execute(
                """SELECT 1 FROM orders WHERE (status = 'pending' AND waiting_funds = 0)
                   OR (unit_cost IS NOT NULL AND updated_at >= ?) LIMIT 1""", (quiet_from,)).fetchone()
            if busy:
                return None
            bot_cost = int(conn.execute(
                f"""SELECT SUM(COALESCE(o.unit_cost, 0) * {_SOLD_SQL}) FROM orders o
                    WHERE o.status IN ('done', 'partial') AND o.updated_at >= ? AND o.updated_at <= ?""",
                (base["at"], read_iso)).fetchone()[0] or 0)
            expected = int(base["balance"]) - bot_cost
            delta = balance - expected
            capital_id = None
            if abs(delta) >= FUNDS_MIN_DELTA:
                note = ("tự ghi: ví FatCat tăng ngoài đơn bot (anh nạp?)" if delta > 0
                        else "tự ghi: FatCat trừ ngoài đơn bot (anh mua thẳng trên FatCat?)")
                capital_id = int(conn.execute(
                    "INSERT INTO capital(amount, note, created_by, created_at) VALUES (?, ?, ?, ?)",
                    (delta, note, AUTO_CAPITAL_BY, read_iso)).lastrowid)
                expected = balance
            save(expected)
            return capital_id

    def auto_capital_after(self, last_id: int) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM capital WHERE created_by = ? AND id > ? ORDER BY id",
                                (AUTO_CAPITAL_BY, last_id)).fetchall()
        return [dict(row) for row in rows]

    def get_capital(self, capital_id: int) -> dict | None:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM capital WHERE id = ?", (capital_id,)).fetchone()
        return dict(row) if row else None

    def order_cost(self, order_id: int) -> int | None:
        """Vốn FatCat của một đơn = giá vốn × số món thực giao; hàng tự nhập (không giá vốn) → None."""
        with self._read() as conn:
            row = conn.execute(f"SELECT o.unit_cost, {_SOLD_SQL} FROM orders o WHERE o.id = ?", (order_id,)).fetchone()
        return None if row is None or row[0] is None else int(row[0]) * int(row[1] or 0)

    def last_synced(self) -> str | None:
        """Lần đồng bộ FatCat gần nhất (synced_at mới nhất của sản phẩm FatCat)."""
        with self._read() as conn:
            return conn.execute("SELECT MAX(synced_at) FROM products WHERE upstream_id IS NOT NULL").fetchone()[0]

    def capital_total(self) -> int:
        with self._read() as conn:
            return int(conn.execute("SELECT SUM(amount) FROM capital").fetchone()[0] or 0)

    def recent_capital(self, limit: int = 10) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM capital ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def delete_capital(self, capital_id: int) -> bool:
        """Xoá lần ghi nạp nhầm (chỉ dòng ghi chép, không đụng ví FatCat)."""
        with self._tx() as conn:
            return conn.execute("DELETE FROM capital WHERE id = ?", (capital_id,)).rowcount > 0

    def recent_ledger(self, limit: int = 15) -> list[dict]:
        """Các lần tiền vào / ra ví khách, mới nhất trước (nạp, mua, hoàn, admin cộng/trừ)."""
        with self._read() as conn:
            rows = conn.execute(
                """SELECT l.delta, l.balance_after, l.kind, l.ref, l.note, l.created_at, u.username, u.first_name,
                          l.user_id FROM ledger l JOIN users u ON u.user_id = l.user_id
                   ORDER BY l.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


_SOLD_SQL = "(SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id)"
_ZERO_TOTALS = {"orders": 0, "revenue": 0, "cost": 0, "cash_in": 0, "adjust": 0, "expense": 0}


def _utc_iso(local: datetime) -> str:
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def _not_in(ids: Iterable[int]) -> tuple[str, tuple[int, ...]]:
    """Mảnh SQL «NOT IN (?, ?)» cho cột user_id; danh sách rỗng → luôn đúng."""
    ids = tuple(int(i) for i in ids)
    return (f"NOT IN ({', '.join('?' * len(ids))})", ids) if ids else ("IS NOT NULL", ())


def _daily_totals(conn: sqlite3.Connection, start: str, end: str | None, admins: tuple[int, ...] = (),
                  admin_side: bool = False) -> dict[str, dict[str, int]]:
    """{ngày VN "YYYY-MM-DD": đơn, doanh thu, vốn, tiền chuyển vào, admin cộng/trừ tay, khoản chi} trong [start, end).
    Mặc định chỉ tiền của khách (bỏ tài khoản `admins`) + khoản chi; admin_side=True: chỉ tiền tài khoản admin."""
    end = end or "9999"
    not_admin, ids = _not_in(admins)
    def who(column: str = "user_id") -> str:
        return f"NOT ({column} {not_admin})" if admin_side else f"{column} {not_admin}"
    out: dict[str, dict[str, int]] = {}

    def add(day: str, **values: int) -> None:
        row = out.setdefault(day, dict(_ZERO_TOTALS))
        for name, value in values.items():
            row[name] += int(value or 0)

    for day, orders, revenue, cost in conn.execute(
        f"""SELECT date(o.created_at, '+7 hours'), COUNT(*), SUM(o.total - o.refunded),
                   SUM(COALESCE(o.unit_cost, 0) * {_SOLD_SQL})
            FROM orders o WHERE o.status IN ('done', 'partial') AND o.created_at >= ? AND o.created_at < ?
            AND {who('o.user_id')} GROUP BY 1""", (start, end, *ids)):
        add(day, orders=orders, revenue=revenue, cost=cost)
    for day, amount in conn.execute(
        f"""SELECT date(resolved_at, '+7 hours'), SUM(credited) FROM topups
            WHERE status = 'paid' AND resolved_at >= ? AND resolved_at < ? AND {who()} GROUP BY 1""", (start, end, *ids)):
        add(day, cash_in=amount)
    for day, amount in conn.execute(
        f"""SELECT date(created_at, '+7 hours'), SUM(delta) FROM ledger
            WHERE kind = 'adjust' AND created_at >= ? AND created_at < ? AND {who()} GROUP BY 1""", (start, end, *ids)):
        add(day, adjust=amount)
    if admin_side:
        return out
    for day, amount in conn.execute(
        """SELECT date(created_at, '+7 hours'), SUM(amount) FROM expenses
           WHERE created_at >= ? AND created_at < ? GROUP BY 1""", (start, end)):
        add(day, expense=amount)
    return out


def _sum_totals(rows: Iterable[dict[str, int]]) -> dict[str, int]:
    total = dict(_ZERO_TOTALS)
    for row in rows:
        for name in total:
            total[name] += row.get(name, 0)
    total["profit"] = total["revenue"] - total["cost"]  # lãi gộp
    total["net"] = total["profit"] - total["expense"]  # lãi ròng sau khoản chi ngoài bot
    return total


def _upstream_funds(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM state WHERE key = ?", (UPSTREAM_FUNDS_KEY,)).fetchone()
    return int(row["value"]) if row and str(row["value"]).lstrip("-").isdigit() else None


def _balance(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise StoreError("user_not_found")
    return int(row["balance"])


def _move_money(conn: sqlite3.Connection, user_id: int, delta: int, kind: str, ref: str, note: str) -> int:
    balance = _balance(conn, user_id) + delta
    if balance < 0:
        raise StoreError("insufficient_balance", need=-delta, balance=balance - delta)
    conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (balance, user_id))
    conn.execute(
        "INSERT INTO ledger(user_id, delta, balance_after, kind, ref, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, delta, balance, kind, ref, note, utcnow()),
    )
    return balance


def _stock(conn: sqlite3.Connection, product_id: int) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM stock_items WHERE product_id = ? AND status = 'available'", (product_id,)
    ).fetchone()[0])


def _user(row: sqlite3.Row) -> User:
    return User(row["user_id"], row["username"], row["first_name"], row["balance"], bool(row["notify_off"]))


def _product(row: sqlite3.Row) -> Product:
    return Product(row["id"], row["name"], row["description"], row["price"], bool(row["active"]), row["stock"],
                   row["upstream_id"], row["upstream_cost"], row["upstream_max"], bool(row["upstream_available"]))


def _load_product(conn: sqlite3.Connection, product_id: int) -> Product | None:
    row = conn.execute(f"SELECT p.*, {STOCK_SQL} FROM products p WHERE p.id = ?", (product_id,)).fetchone()
    return _product(row) if row else None


def _order(row: sqlite3.Row, **extra) -> Order:
    return Order(row["id"], row["user_id"], row["product_id"], row["product_name"], row["quantity"],
                 row["unit_price"], row["total"], row["source"], row["created_at"], status=row["status"],
                 refunded=row["refunded"], note=row["note"],
                 waiting_funds=bool(row["waiting_funds"]) if "waiting_funds" in row.keys() else False,
                 upstream_order_id=row["upstream_order_id"] if "upstream_order_id" in row.keys() else None, **extra)


def _load_order(conn: sqlite3.Connection, order_id: int, replayed: bool = False) -> Order:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    items = [r["content"] for r in conn.execute("SELECT content FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))]
    return _order(row, items=items, balance_after=_balance(conn, row["user_id"]), replayed=replayed)


def _topup(row: sqlite3.Row) -> Topup:
    return Topup(row["id"], row["user_id"], row["code"], row["amount"], row["credited"], row["status"], row["created_at"],
                 row["intent_product_id"], row["intent_quantity"],
                 row["intent_unit_price"] if "intent_unit_price" in row.keys() else None,
                 row["resolved_by"] if "resolved_by" in row.keys() else None)


def _load_key(conn: sqlite3.Connection, key_id: int) -> ApiKey | None:
    row = conn.execute(
        """SELECT k.*, u.username, u.first_name FROM api_keys k JOIN users u ON u.user_id = k.user_id
           WHERE k.id = ?""",
        (key_id,),
    ).fetchone()
    if row is None:
        return None
    label = f"@{row['username']}" if row["username"] else (row["first_name"] or str(row["user_id"]))
    return ApiKey(row["id"], row["user_id"], row["prefix"], row["discount_bps"], bool(row["active"]),
                  row["created_at"], row["last_used_at"], label)
