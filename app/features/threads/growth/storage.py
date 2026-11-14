"""Lưu trữ dữ liệu Threads Growth & Quản lý Thử nghiệm A/B trong SQLite.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from app.features.threads.growth.config import ACCOUNTS, DEFAULT_ACCOUNT, ABVariant, DB_PATH, TargetBot


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
    "account": "TEXT",  # PLAN-167: tài khoản Threads đã đăng reply (ghi lúc đăng)
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
            if "account" not in have:
                # Trước PLAN-167 chỉ @us28qt đăng — gán một lần cho reply đã đăng / đã thử đăng.
                conn.execute("UPDATE growth_posts SET account = ? WHERE status IN ('posted', 'failed')", (DEFAULT_ACCOUNT,))
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
            own_cols = {r["name"] for r in conn.execute("PRAGMA table_info(own_posts)")}
            if "account" not in own_cols:
                conn.execute("ALTER TABLE own_posts ADD COLUMN account TEXT")
                conn.execute("UPDATE own_posts SET account = ?", (DEFAULT_ACCOUNT,))
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
            # PLAN-171: tin nhắn riêng — một dòng / cuộc trò chuyện + nhật ký mọi tin vào / ra.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dm_threads (
                    thread_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    folder TEXT NOT NULL,        -- inbox · requests
                    preview TEXT,                -- chữ hàng lúc xem gần nhất: không đổi thì không mở lại
                    handled_sig TEXT,            -- dấu các tin khách đã xử lý (dm.signature)
                    status TEXT NOT NULL,        -- open · handoff · ignored
                    hold_until TEXT,             -- handoff: agent im tới lúc này
                    note TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, account)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dm_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    handle TEXT NOT NULL,
                    direction TEXT NOT NULL,     -- in · out · note
                    text TEXT NOT NULL,
                    action TEXT,                 -- reply · handoff · skip · failed
                    hot INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dm_messages_out ON dm_messages(account, direction, created_at)")

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

    def approved_queue(self, limit: int = 20, bots: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Bài đã duyệt chờ đăng — điểm thành khách cao trước (theo nấc 10, PLAN-163), cùng nấc thì độ phủ cao trước, rồi cũ trước.

        ``bots``: chỉ bài của các bot này (vai của tài khoản đang đăng, PLAN-167); None = mọi bot.
        """
        where, args = "status = 'approved'", []
        if bots is not None:
            if not bots:
                return []
            where += f" AND target_bot IN ({','.join('?' * len(bots))})"
            args.extend(bots)
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM growth_posts WHERE {where} "
                "ORDER BY COALESCE(relevance_score, 0) / 10 DESC, reach DESC, id ASC LIMIT ?",
                (*args, limit),
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
        account: Optional[str] = None,
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
                    reply_url = COALESCE(?, reply_url),
                    account = COALESCE(?, account)
                WHERE id = ?
                """,
                (status, actual_reply, error_message, posted_at, reply_url, account, post_id),
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
                      post_url: Optional[str] = None, error: Optional[str] = None,
                      account: str = DEFAULT_ACCOUNT) -> int:
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO own_posts (slot, kind, ref, text, status, post_url, error_message, created_at, "
                "account) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slot, kind, ref, text, status, post_url, error, datetime.now(timezone.utc).isoformat(), account),
            )
            return cur.lastrowid if cur.rowcount else 0

    def list_own_posts(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM own_posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── trả lời lại (PLAN-159) ─────────────────────────────────
    def followup_targets(self, since: datetime, checked_before: datetime, limit: int,
                         account: Optional[str] = None) -> List[Dict[str, Any]]:
        """Reply của mình đăng từ ``since``, lâu chưa kiểm (``followup_checked_at`` < ``checked_before``) — cũ trước.

        ``account``: chỉ reply tài khoản này đăng (mở bằng đúng profile đó mới thấy «trả lời cho mình»).
        """
        acc_sql, acc_args = ("AND COALESCE(account, ?) = ?", (DEFAULT_ACCOUNT, account)) if account else ("", ())
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM growth_posts
                WHERE status = 'posted' AND reply_url IS NOT NULL AND posted_at >= ?
                  AND (followup_checked_at IS NULL OR followup_checked_at < ?) {acc_sql}
                ORDER BY COALESCE(followup_checked_at, '') ASC, posted_at DESC LIMIT ?
                """,
                (since.astimezone(timezone.utc).isoformat(), checked_before.astimezone(timezone.utc).isoformat(),
                 *acc_args, limit),
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

    def count_followups_since(self, since: datetime, account: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM followups f WHERE f.status = 'answered' AND f.created_at >= ?"
        args: list = [since.astimezone(timezone.utc).isoformat()]
        if account:
            sql += " AND (SELECT COALESCE(g.account, ?) FROM growth_posts g WHERE g.id = f.growth_post_id) = ?"
            args.extend([DEFAULT_ACCOUNT, account])
        with self._connection() as conn:
            row = conn.execute(sql, args).fetchone()
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

    def count_posted_since(self, since: datetime, account: Optional[str] = None) -> int:
        """Reply đã đăng từ ``since`` — của một tài khoản (hạn mức riêng, PLAN-167) hoặc tất cả."""
        acc_sql, acc_args = (" AND COALESCE(account, ?) = ?", (DEFAULT_ACCOUNT, account)) if account else ("", ())
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM growth_posts WHERE status = 'posted' AND posted_at >= ?" + acc_sql,
                (since.astimezone(timezone.utc).isoformat(), *acc_args),
            ).fetchone()
        return int(row[0])

    def last_posted_at(self, account: Optional[str] = None) -> Optional[datetime]:
        acc_sql, acc_args = (" AND COALESCE(account, ?) = ?", (DEFAULT_ACCOUNT, account)) if account else ("", ())
        with self._connection() as conn:
            row = conn.execute(
                "SELECT MAX(posted_at) FROM growth_posts WHERE status = 'posted'" + acc_sql, acc_args
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

    def get_account_stats(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """PLAN-167: reply đã đăng / lỗi theo tài khoản × bot (chỉ dòng đã ghi tài khoản — tức đã thử đăng)."""
        stats: Dict[str, Dict[str, Dict[str, int]]] = {
            acc: {b.value: {} for b in TargetBot} for acc in ACCOUNTS
        }
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT account, target_bot, status, COUNT(*) AS n FROM growth_posts "
                "WHERE account IS NOT NULL GROUP BY account, target_bot, status"
            ).fetchall()
        for r in rows:
            if r["account"] in stats and r["target_bot"] in stats[r["account"]]:
                stats[r["account"]][r["target_bot"]][r["status"]] = r["n"]
        return stats

    # ── PLAN-171: tin nhắn riêng ───────────────────────────────
    def dm_thread(self, thread_id: str, account: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM dm_threads WHERE thread_id = ? AND account = ?",
                               (thread_id, account)).fetchone()
        return dict(row) if row else None

    def save_dm_thread(self, thread_id: str, account: str, handle: str, folder: str, *, preview: Optional[str],
                       handled_sig: Optional[str], status: str, hold_until: Optional[str] = None,
                       note: Optional[str] = None) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO dm_threads (thread_id, account, handle, folder, preview, handled_sig, status, hold_until,
                                        note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id, account) DO UPDATE SET
                    handle = excluded.handle, folder = excluded.folder, preview = excluded.preview,
                    handled_sig = excluded.handled_sig, status = excluded.status, hold_until = excluded.hold_until,
                    note = excluded.note, updated_at = excluded.updated_at
                """,
                (thread_id, account, handle, folder, preview, handled_sig, status, hold_until, note,
                 datetime.now(timezone.utc).isoformat()),
            )

    def log_dm(self, thread_id: str, account: str, handle: str, direction: str, text: str,
               action: Optional[str] = None, hot: Optional[int] = None) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO dm_messages (thread_id, account, handle, direction, text, action, hot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (thread_id, account, handle, direction, text, action, hot, datetime.now(timezone.utc).isoformat()),
            )

    def count_dm_sent_since(self, since: datetime, account: str, thread_id: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM dm_messages WHERE account = ? AND direction = 'out' AND created_at >= ?"
        args: list = [account, since.astimezone(timezone.utc).isoformat()]
        if thread_id:
            sql += " AND thread_id = ?"
            args.append(thread_id)
        with self._connection() as conn:
            return int(conn.execute(sql, args).fetchone()[0])
