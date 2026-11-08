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
    "like_count": "INTEGER NOT NULL DEFAULT 0",
    "reply_count": "INTEGER NOT NULL DEFAULT 0",
    "author_followers": "INTEGER NOT NULL DEFAULT 0",
    "reach": "INTEGER NOT NULL DEFAULT 0",
    "followup_checked_at": "TEXT",
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
            # PLAN-159: bài riêng trên tài khoản + trả lời người hỏi lại dưới reply của mình.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS own_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot TEXT UNIQUE NOT NULL,   -- ngày + giờ khung (VN): mỗi khung tối đa 1 bài
                    kind TEXT NOT NULL,          -- deal · sale
                    ref TEXT NOT NULL DEFAULT '',-- deal:<item>,… / sale:<ngày>:<hôm nay> — tránh đăng lặp
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,        -- posted · failed · skipped
                    post_url TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,   -- mã bài của người hỏi lại
                    growth_post_id INTEGER NOT NULL,
                    author TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    post_url TEXT NOT NULL,
                    reply_text TEXT,
                    reply_url TEXT,
                    status TEXT NOT NULL,        -- answered · skipped · failed
                    error_message TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

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
        like_count: int = 0,
        reply_count: int = 0,
        author_followers: int = 0,
        reach: int = 0,
    ) -> int:
        now_str = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO growth_posts (
                    thread_id, post_url, author, content, target_bot, variant,
                    relevance_score, ai_analysis, suggested_reply, status, created_at,
                    actual_reply, auto_approved, post_created_at,
                    like_count, reply_count, author_followers, reach
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    like_count,
                    reply_count,
                    author_followers,
                    reach,
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
        """Bài đã duyệt chờ đăng — điểm thành khách cao trước (theo nấc 10, PLAN-163), cùng nấc thì độ phủ cao trước, rồi cũ trước."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM growth_posts WHERE status = 'approved' "
                "ORDER BY COALESCE(relevance_score, 0) / 10 DESC, reach DESC, id ASC LIMIT ?",
                (limit,),
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

    def posted_to_author_since(self, author: str, since: datetime) -> bool:
        """Đã ĐĂNG reply cho người này kể từ ``since`` (không tính bài đang chờ)?"""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM growth_posts WHERE lower(author) = lower(?) AND status = 'posted' AND posted_at >= ? LIMIT 1",
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

    # ── bài riêng (PLAN-159) ───────────────────────────────────
    def own_post_slot_done(self, slot: str) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM own_posts WHERE slot = ?", (slot,)).fetchone() is not None

    def own_post_refs(self, since: datetime) -> set[str]:
        """Món / dịp đã đăng (hoặc đã thử) gần đây — không lặp lại."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT ref FROM own_posts WHERE created_at >= ?", (since.astimezone(timezone.utc).isoformat(),)
            ).fetchall()
        return {part for (ref,) in rows for part in str(ref).split(",") if part}

    def save_own_post(self, slot: str, kind: str, ref: str, text: str, status: str,
                      post_url: Optional[str] = None, error: Optional[str] = None) -> int:
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO own_posts (slot, kind, ref, text, status, post_url, error_message, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (slot, kind, ref, text, status, post_url, error, datetime.now(timezone.utc).isoformat()),
            )
            return cur.lastrowid if cur.rowcount else 0

    def list_own_posts(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM own_posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── trả lời lại (PLAN-159) ─────────────────────────────────
    def followup_targets(self, since: datetime, checked_before: datetime, limit: int) -> List[Dict[str, Any]]:
        """Reply của mình đăng từ ``since``, lâu chưa kiểm (``followup_checked_at`` < ``checked_before``) — cũ trước."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM growth_posts
                WHERE status = 'posted' AND reply_url IS NOT NULL AND posted_at >= ?
                  AND (followup_checked_at IS NULL OR followup_checked_at < ?)
                ORDER BY COALESCE(followup_checked_at, '') ASC, posted_at DESC LIMIT ?
                """,
                (since.astimezone(timezone.utc).isoformat(), checked_before.astimezone(timezone.utc).isoformat(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_followup_checked(self, post_id: int, at: datetime) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE growth_posts SET followup_checked_at = ? WHERE id = ?",
                         (at.astimezone(timezone.utc).isoformat(), post_id))

    def followup_seen(self, code: str) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM followups WHERE code = ?", (code,)).fetchone() is not None

    def save_followup(self, code: str, growth_post_id: int, author: str, comment: str, post_url: str,
                      status: str, reply_text: Optional[str] = None, reply_url: Optional[str] = None,
                      error: Optional[str] = None) -> int:
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO followups (code, growth_post_id, author, comment, post_url, reply_text, "
                "reply_url, status, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (code, growth_post_id, author, comment, post_url, reply_text, reply_url, status, error,
                 datetime.now(timezone.utc).isoformat()),
            )
            return cur.lastrowid if cur.rowcount else 0

    def count_followups_since(self, since: datetime) -> int:
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM followups WHERE status = 'answered' AND created_at >= ?",
                               (since.astimezone(timezone.utc).isoformat(),)).fetchone()
        return int(row[0])

    def list_followups(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM followups ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def fallback_pending(self, limit: int) -> List[Dict[str, Any]]:
        """Bài chờ duyệt vì AI lỗi (đang dùng câu mẫu) — để thử cho AI viết lại khi AI chạy lại."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM growth_posts WHERE status = 'pending' AND ai_analysis LIKE 'Fallback%' "
                "ORDER BY reach DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

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
