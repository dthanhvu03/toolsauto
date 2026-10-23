"""PLAN-063: thống kê trong /admin. Chỉ đọc."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from cashback_bot.admin_policy import AdminPanel
from cashback_bot.admin_stats import collect, period_start
from tests.test_cashback_bot import FakeClient, payload, repo, service

ADMIN = 7
NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)  # 16:00 23/10 giờ VN


def _seed(tmp_path):
    store = repo(tmp_path)
    with store.connect() as conn:
        conn.executemany(
            "INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            [
                (1, "an", "2026-10-01T00:00:00Z", "2026-10-23T08:00:00Z"),
                (2, None, "2026-10-22T17:00:00Z", "2026-10-23T08:00:00Z"),
                (3, "<b>x</b>", "2026-10-22T16:59:59Z", "2026-10-22T16:59:59Z"),
            ],
        )
        links = [
            # user, item, tên, hoa hồng, hoàn, trạng thái, lý do, lúc (UTC)
            (1, 8, "Áo Polo Nam, cổ bẻ", 20_000, 14_000, "created", None, "2026-10-22T17:00:00Z"),  # 00:00 23/10 VN
            (1, 8, "Áo Polo Nam, cổ bẻ", 20_000, 12_462, "created", None, "2026-10-23T08:00:00Z"),
            (2, 9, "Mực in HP", 10_000, 7_000, "created", None, "2026-10-23T08:30:00Z"),
            (3, 9, "Mực in HP", 10_000, 7_000, "created", None, "2026-10-22T16:59:59Z"),  # 23:59 22/10 VN
            (1, None, None, None, None, "rejected", "invalid_link", "2026-10-23T07:00:00Z"),
            (2, None, None, None, None, "rejected", "timeout", "2026-10-23T07:10:00Z"),
            (2, None, None, None, None, "rejected", "http_error", "2026-10-23T07:20:00Z"),
            (1, 5, "Cũ", 50_000, 35_000, "created", None, "2026-09-01T00:00:00Z"),
        ]
        conn.executemany(
            """
            INSERT INTO link_requests (
                telegram_user_id, item_id, product_name, estimated_commission, estimated_cashback,
                link_status, reject_reason, created_at, original_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'u')
            """,
            links,
        )
        conn.execute(
            "INSERT INTO admin_notifications (event_key, event_type, chat_id, message_html, created_at) "
            "VALUES ('e1', 'REQUEST_FAILED', 1, 'x', '2026-10-23T07:00:00Z')"
        )
        conn.execute(
            "INSERT INTO outbound_messages (telegram_update_id, telegram_user_id, body_html, status, created_at) "
            "VALUES (1, 1, 'x', 'needs_review', '2026-10-23T07:00:00Z')"
        )
    return store


def test_moc_ky_theo_gio_viet_nam():
    assert period_start("today", NOW) == datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)
    assert period_start("7d", NOW) == datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc)
    assert period_start("all", NOW) is None


def test_so_lieu_hom_nay(tmp_path):
    store = _seed(tmp_path)
    with store.connect() as conn:
        stats = collect(conn, "today", NOW)
    assert (stats.users_total, stats.users_new, stats.users_active) == (3, 1, 2)
    assert (stats.links_total, stats.links_created) == (6, 3)
    assert stats.rejected == [("Dữ liệu sản phẩm chưa sẵn", 2), ("Link sai", 1)]
    assert (stats.commission_vnd, stats.cashback_vnd) == (50_000, 33_462)
    assert stats.top_users == [(1, "an", 2), (2, None, 1)]
    assert stats.top_products == [("Áo Polo Nam", 2), ("Mực in HP", 1)]
    assert stats.trend[-2:] == [("22/10", 1), ("23/10", 3)]
    assert len(stats.trend) == 7
    assert (stats.delivery_pending, stats.errors) == (1, 1)


def test_ky_tat_ca_gom_link_cu(tmp_path):
    store = _seed(tmp_path)
    with store.connect() as conn:
        everything = collect(conn, "all", NOW)
        week = collect(conn, "7d", NOW)
    assert everything.links_created == 5
    assert everything.commission_vnd == 110_000
    assert week.links_created == 4
    assert week.top_products == [("Mực in HP", 2), ("Áo Polo Nam", 2)], "hoà thì món mới hỏi gần nhất lên trước"


def test_man_thong_ke_trong_admin(tmp_path):
    _seed(tmp_path)
    bot = service(tmp_path, FakeClient(payload()), admin_user_ids=frozenset({ADMIN}))
    home = bot.admin_panel.menu(ADMIN, NOW)
    assert home.inline_keyboard[0] == (("📈 Thống kê", "c:st:7d"),)

    reply = bot.admin_panel.handle_callback(ADMIN, "c:st:today", "private", NOW)
    assert reply.text.startswith("⚙️ Quản trị › <b>Thống kê · Hôm nay</b>")
    assert "<i>Từ 00:00 23/10/2026</i>" in reply.text
    assert "Gửi: <b>6</b> · Tạo được: <b>3</b> (50%)" in reply.text
    assert "Lỗi: Dữ liệu sản phẩm chưa sẵn 2 · Link sai 1" in reply.text
    assert "Chênh lệch trước phí, thuế: <b>16.538đ</b>" in reply.text
    assert "1. @an · 2 link" in reply.text
    assert "2. <code>2</code> · 1 link" in reply.text
    assert "23/10 ██████████ 3" in reply.text
    assert "chưa phải doanh thu" in reply.text
    assert reply.inline_keyboard[0][0] == ("• Hôm nay", "c:st:today")
    assert reply.inline_keyboard[-1] == (("◀️ Tổng quan", "c:menu:home"),)
    assert len(reply.text) < 3500

    everything = bot.admin_panel.handle_callback(ADMIN, "c:st:all", "private", NOW)
    assert "<i>Toàn bộ dữ liệu</i>" in everything.text
    assert "&lt;b&gt;x&lt;/b&gt;" in everything.text, "username phải được escape"

    assert "chỉ dành cho quản trị" in bot.admin_panel.handle_callback(222, "c:st:7d", "private", NOW).text


def test_chua_co_du_lieu(tmp_path):
    repo(tmp_path)
    panel = AdminPanel(str(tmp_path / "cashback.sqlite"), frozenset({ADMIN}), 70)
    reply = panel.handle_callback(ADMIN, "c:st:7d", "private", NOW)
    assert "Tổng: <b>0</b>" in reply.text
    assert "Lỗi: không có" in reply.text
    assert "Gửi nhiều nhất" not in reply.text
    assert "16/10" not in reply.text and "17/10 ▏ 0" in reply.text


def test_database_thieu_bang_khong_vo(tmp_path):
    panel = AdminPanel(str(tmp_path / "admin-only.sqlite"), frozenset({ADMIN}), 70)
    reply = panel.handle_callback(ADMIN, "c:st:today", "private", NOW)
    assert "Chưa đọc được dữ liệu thống kê" in reply.text
    assert reply.inline_keyboard[-1] == (("◀️ Tổng quan", "c:menu:home"),)


def test_thong_ke_chay_duoc_tren_ket_noi_chi_doc(tmp_path):
    """collect chỉ SELECT: kết nối mode=ro sẽ báo lỗi nếu có lệnh ghi."""
    _seed(tmp_path)
    conn = sqlite3.connect(f"file:{tmp_path / 'cashback.sqlite'}?mode=ro", uri=True)
    for period in ("today", "7d", "30d", "all"):
        collect(conn, period, NOW)
