"""Lưu trữ dữ liệu Threads Growth & Quản lý Thử nghiệm A/B trong SQLite.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from app.features.threads.growth.config import ABVariant, DB_PATH, TargetBot


_EXTRA_COLUMNS = {
    "reply_url": "TEXT",
    "auto_approved": "INTEGER NOT NULL DEFAULT 0",
    "post_created_at": "TEXT",
    "notified_at": "TEXT",
}

STATUSES = ("pending", "approved", "rejected", "posted", "failed")


class GrowthStorage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        # Giữ khóa file của SQLite (không nolock): CLI và worker có thể ghi cùng lúc.
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS growth_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT UNIQUE NOT NULL,
                    post_url TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    target_bot TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    relevance_score INTEGER DEFAULT 0,
                    ai_analysis TEXT,
                    suggested_reply TEXT NOT NULL,
                    actual_reply TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected, posted, failed
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    posted_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_growth_posts_status ON growth_posts(status);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_growth_posts_bot_variant ON growth_posts(target_bot, variant);
                """
            )
            # Cột thêm sau (PLAN-158) — SQLite riêng của gói, thêm tại chỗ nếu DB cũ chưa có.
            have = {r["name"] for r in conn.execute("PRAGMA table_info(growth_posts)")}
            for col, ddl in _EXTRA_COLUMNS.items():
                if col not in have:
                    conn.execute(f"ALTER TABLE growth_posts ADD COLUMN {col} {ddl}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_growth_posts_author ON growth_posts(author, status)")

    def is_thread_scanned(self, thread_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM growth_posts WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return row is not None

    def save_post(
        self,
        thread_id: str,
        post_url: str,
        author: str,
        content: str,
        target_bot: TargetBot,
        variant: ABVariant,
        suggested_reply: str,
        relevance_score: int = 100,
        ai_analysis: str = "",
        status: str = "pending",
        auto_approved: bool = False,
        post_created_at: Optional[str] = None,
    ) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO growth_posts (
                    thread_id, post_url, author, content, target_bot, variant,
                    relevance_score, ai_analysis, suggested_reply, status, created_at,
                    actual_reply, auto_approved, post_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    post_url,
                    author,
                    content,
                    target_bot.value,
                    variant.value,
                    relevance_score,
                    ai_analysis,
                    suggested_reply,
                    status,
                    now_str,
                    suggested_reply if status == "approved" else None,
                    1 if auto_approved else 0,
                    post_created_at,
                ),
            )
            # INSERT OR IGNORE trùng thread_id → rowcount 0 (lastrowid không đáng tin khi bị bỏ qua).
            return cursor.lastrowid if cursor.rowcount else 0

    def get_pending_posts(
        self, bot: Optional[TargetBot] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            if bot:
                rows = conn.execute(
                    """
                    SELECT * FROM growth_posts
                    WHERE status = 'pending' AND target_bot = ?
                    ORDER BY relevance_score DESC, id DESC LIMIT ?
                    """,
                    (bot.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM growth_posts
                    WHERE status = 'pending'
                    ORDER BY relevance_score DESC, id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def list_posts(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Danh sách cho web: mới nhất trước (đã đăng → theo giờ đăng)."""
        order = "posted_at DESC" if status == "posted" else "id DESC"
        with self._connection() as conn:
            if status:
                rows = conn.execute(
                    f"SELECT * FROM growth_posts WHERE status = ? ORDER BY {order} LIMIT ?", (status, limit)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM growth_posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def approved_queue(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Bài đã duyệt chờ đăng — cũ trước."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM growth_posts WHERE status = 'approved' ORDER BY id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def replied_author_since(self, author: str, since: datetime) -> bool:
        """Đã reply (hoặc đang chờ đăng cho) người này kể từ ``since``?"""
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM growth_posts
                WHERE lower(author) = lower(?) AND (
                    (status = 'posted' AND posted_at >= ?) OR status = 'approved'
                ) LIMIT 1
                """,
                (author, since.astimezone(timezone.utc).isoformat()),
            ).fetchone()
        return row is not None

    def unnotified_pending(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM growth_posts WHERE status = 'pending' AND notified_at IS NULL ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_notified(self, post_id: int) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE growth_posts SET notified_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), post_id),
            )

    def get_post_by_id(self, post_id: int) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM growth_posts WHERE id = ?", (post_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_status(
        self,
        post_id: int,
        status: str,
        actual_reply: Optional[str] = None,
        error_message: Optional[str] = None,
        reply_url: Optional[str] = None,
    ) -> bool:
        now_str = datetime.now(timezone.utc).isoformat()
        posted_at = now_str if status == "posted" else None
        with self._connection() as conn:
            cur = conn.execute(
                """
                UPDATE growth_posts
                SET status = ?,
                    actual_reply = COALESCE(?, actual_reply),
                    error_message = COALESCE(?, error_message),
                    posted_at = COALESCE(?, posted_at),
                    reply_url = COALESCE(?, reply_url)
                WHERE id = ?
                """,
                (status, actual_reply, error_message, posted_at, reply_url, post_id),
            )
            return cur.rowcount > 0

    def switch_variant(
        self, post_id: int, new_variant: ABVariant, new_reply: str, ai_analysis: Optional[str] = None
    ) -> bool:
        with self._connection() as conn:
            cur = conn.execute(
                """
                UPDATE growth_posts
                SET variant = ?, suggested_reply = ?, ai_analysis = COALESCE(?, ai_analysis)
                WHERE id = ?
                """,
                (new_variant.value, new_reply, ai_analysis, post_id),
            )
            return cur.rowcount > 0

    def variant_counts(self, bot: TargetBot) -> Dict[str, int]:
        """Số bài đã gán cho từng biến thể của một bot (mọi trạng thái) — để chia A/B bền qua các lần chạy."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT variant, COUNT(*) AS n FROM growth_posts WHERE target_bot = ? GROUP BY variant",
                (bot.value,),
            ).fetchall()
        counts = {v.value: 0 for v in ABVariant}
        for r in rows:
            if r["variant"] in counts:
                counts[r["variant"]] = r["n"]
        return counts

    def count_posted_since(self, since: datetime) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM growth_posts WHERE status = 'posted' AND posted_at >= ?",
                (since.astimezone(timezone.utc).isoformat(),),
            ).fetchone()
        return int(row[0])

    def last_posted_at(self) -> Optional[datetime]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT MAX(posted_at) FROM growth_posts WHERE status = 'posted'"
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def get_ab_stats(self) -> Dict[str, Any]:
        """Thống kê tổng số bài đã quét, đã duyệt, đã đăng theo từng biến thể A/B."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT target_bot, variant, status, COUNT(*) as count
                FROM growth_posts
                GROUP BY target_bot, variant, status
                """
            ).fetchall()

            stats: Dict[str, Dict[str, Dict[str, int]]] = {
                b.value: {v.value: {} for v in ABVariant} for b in TargetBot
            }

            for row in rows:
                b = row["target_bot"]
                v = row["variant"]
                st = row["status"]
                cnt = row["count"]
                if b in stats and v in stats[b]:
                    stats[b][v][st] = cnt

            return stats
