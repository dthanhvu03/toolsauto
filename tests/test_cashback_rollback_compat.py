"""Rollback PLAN-079: code trước PLAN-079 chạy trên DB đã có hàng đợi mới mà không phát lại trạng thái lạ.

DB sau PLAN-079 được dựng lại bằng đúng các lệnh migration của PLAN-079 (cột, bảng tuỳ chọn, cột khách chặn bot).
Không sửa dòng nào để rollback: không đổi status, attempt_count, last_error hay lựa chọn của khách.
"""

from __future__ import annotations

from cashback_bot.db import TrackingRepository

POST_079 = """
ALTER TABLE admin_notifications ADD COLUMN audience TEXT NOT NULL DEFAULT 'admin';
ALTER TABLE admin_notifications ADD COLUMN category TEXT;
ALTER TABLE admin_notifications ADD COLUMN next_retry_at TEXT;
ALTER TABLE admin_notifications ADD COLUMN telegram_message_id INTEGER;
ALTER TABLE admin_notifications ADD COLUMN reply_markup_json TEXT;
ALTER TABLE admin_notifications ADD COLUMN source_ref TEXT;
ALTER TABLE telegram_users ADD COLUMN notify_blocked_at TEXT;
CREATE TABLE IF NOT EXISTS customer_notification_prefs (
    telegram_user_id INTEGER PRIMARY KEY,
    orders INTEGER NOT NULL DEFAULT 1,
    updates INTEGER NOT NULL DEFAULT 1,
    support INTEGER NOT NULL DEFAULT 1,
    wallet INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
"""
T = "2026-10-24T08:00:00Z"
ROWS = (
    # event_key, status, audience, category, chat_id, attempt_count
    ("admin_sent", "sent", "admin", None, 7, 1),
    ("admin_pending", "pending", "admin", None, 7, 0),
    ("admin_retry", "retry", "admin", None, 7, 2),
    ("support_pending", "pending", "customer", "support", 111, 0),
    ("support_pref_off", "pending", "customer", "support", 222, 0),
    ("support_blocked", "pending", "customer", "support", 333, 0),
    ("order_pending", "pending", "customer", "order_new", 111, 0),
    ("order_update_retry", "retry", "customer", "order_update", 111, 1),
    ("unknown", "unknown", "customer", "support", 111, 1),
    ("failed", "failed", "customer", "support", 111, 1),
    ("sending", "sending", "admin", None, 7, 1),
    ("suppressed", "suppressed", "customer", "order_new", 111, 0),
)


def _post_079_repo(tmp_path) -> TrackingRepository:
    repo = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    repo.migrate()
    with repo.connect() as conn:
        conn.executescript(POST_079)
        for user in (111, 222, 333):
            conn.execute("INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) VALUES (?, 'u', ?, ?)",
                         (user, T, T))
        conn.execute("UPDATE telegram_users SET notify_blocked_at = ? WHERE telegram_user_id = 333", (T,))
        conn.execute("INSERT INTO customer_notification_prefs VALUES (222, 1, 1, 0, 1, ?)", (T,))
        for key, status, audience, category, chat, attempts in ROWS:
            conn.execute(
                "INSERT INTO admin_notifications (event_key, event_type, chat_id, message_html, status, attempt_count, "
                "created_at, audience, category, last_error) VALUES (?, 'X', ?, 'm', ?, ?, ?, ?, ?, ?)",
                (key, chat, status, attempts, T, audience, category, f"e:{key}"),
            )
    return repo


def _snapshot(repo):
    with repo.connect() as conn:
        return [tuple(r) for r in conn.execute("SELECT * FROM admin_notifications ORDER BY id")] + [
            tuple(r) for r in conn.execute("SELECT * FROM customer_notification_prefs")
        ] + [tuple(r) for r in conn.execute("SELECT telegram_user_id, notify_blocked_at FROM telegram_users")]


def test_code_cu_chi_lay_tin_no_hieu_va_khong_sua_dong_nao(tmp_path):
    repo = _post_079_repo(tmp_path)
    before = _snapshot(repo)
    repo.migrate()  # migrate() của code cũ trên DB mới
    picked = [row["event_key"] for row in repo.list_pending_admin_events(limit=50)]
    assert picked == ["admin_pending", "admin_retry", "support_pending"]
    assert _snapshot(repo) == before, "rollback không đổi trạng thái, lịch sử thử, tuỳ chọn hay đánh dấu chặn bot"


def test_tin_moi_cua_code_cu_duoc_gan_dung_doi_tuong(tmp_path):
    repo = _post_079_repo(tmp_path)
    repo.enqueue_admin_event("support_customer:9:1", "SUPPORT_CUSTOMER", 111, "x")
    repo.enqueue_admin_event("sync:1", "SHOPEE_SYNC", 7, "y")
    with repo.connect() as conn:
        rows = dict(((r[0]), (r[1], r[2])) for r in conn.execute(
            "SELECT event_key, audience, category FROM admin_notifications WHERE event_key IN ('support_customer:9:1', 'sync:1')"
        ))
    assert rows == {"support_customer:9:1": ("customer", "support"), "sync:1": ("admin", None)}


def test_db_chua_co_plan079_van_chay_nhu_cu(tmp_path):
    repo = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    repo.migrate()
    repo.enqueue_admin_event("a", "SHOPEE_SYNC", 7, "y")
    assert [row["event_key"] for row in repo.list_pending_admin_events()] == ["a"]
