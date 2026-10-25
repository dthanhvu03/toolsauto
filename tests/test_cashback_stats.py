"""PLAN-063: thống kê trong /admin. Chỉ đọc."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from cashback_bot.admin_policy import AdminPanel
from cashback_bot.admin_stats import TopUser, collect, period_start
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
    assert stats.top_users == [TopUser(1, "an", 2, 0), TopUser(2, None, 1, 0)]
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
    # Tổng quan: tiền thật, phễu, bảng 7 ngày (bỏ ngày trống); không có top, số dự kiến.
    assert "Link       3  gửi 6 · lỗi 3" in reply.text
    assert "23/10    3     0   0     0" in reply.text
    assert "Gửi nhiều nhất" not in reply.text and "chưa phải doanh thu" not in reply.text
    assert reply.inline_keyboard[0][0] == ("• Hôm nay", "c:st:today")
    assert reply.inline_keyboard[1] == (("🔎 Chi tiết", "c:st:today:more"),)
    assert reply.inline_keyboard[-1] == (("◀️ Tổng quan", "c:menu:home"),)
    assert reply.text.count("\n") < 30

    detail = bot.admin_panel.handle_callback(ADMIN, "c:st:today:more", "private", NOW)
    assert "Thống kê · Hôm nay › Chi tiết" in detail.text
    assert "Gửi: <b>6</b> · Tạo được: <b>3</b> (50%)" in detail.text
    assert "Lỗi: Dữ liệu sản phẩm chưa sẵn 2 · Link sai 1" in detail.text
    assert "Chênh lệch trước phí, thuế: <b>16.538đ</b>" in detail.text
    assert "1. @an · 2 link · 0 click" in detail.text
    assert "2. <code>2</code> · 1 link · 0 click" in detail.text
    assert "chưa phải doanh thu" in detail.text
    # Đổi kỳ ở màn chi tiết thì vẫn ở chi tiết.
    assert detail.inline_keyboard[0][1] == ("7 ngày", "c:st:7d:more")
    assert detail.inline_keyboard[1] == (("◀️ Về thống kê", "c:st:today"),)
    assert len(detail.text) < 3500

    everything = bot.admin_panel.handle_callback(ADMIN, "c:st:all:more", "private", NOW)
    assert "<i>Toàn bộ dữ liệu</i>" in everything.text
    assert "&lt;b&gt;x&lt;/b&gt;" in everything.text, "username phải được escape"

    assert "chỉ dành cho quản trị" in bot.admin_panel.handle_callback(222, "c:st:7d", "private", NOW).text


def test_chua_co_du_lieu(tmp_path):
    repo(tmp_path)
    panel = AdminPanel(str(tmp_path / "cashback.sqlite"), frozenset({ADMIN}), 70)
    reply = panel.handle_callback(ADMIN, "c:st:7d", "private", NOW)
    assert "Người dùng 0  mới 0 · gửi link 0" in reply.text
    assert "Chưa có hoạt động." in reply.text
    assert "Chưa có dữ liệu đối soát" in reply.text
    detail = panel.handle_callback(ADMIN, "c:st:7d:more", "private", NOW)
    assert "Lỗi: không có" in detail.text
    assert "Gửi nhiều nhất" not in detail.text


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


def test_khach_zalo_hien_ten_va_so_click(tmp_path):
    """Khách Zalo (ID âm, PLAN-082) hiện tên Zalo thay cho -1; click khớp sub_id từ báo cáo Shopee."""
    store = _seed(tmp_path)
    with store.connect() as conn:
        conn.executemany(
            "INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) VALUES (?, NULL, ?, ?)",
            [(-1, "2026-10-23T08:00:00Z", "2026-10-23T08:00:00Z"), (-2, "2026-10-23T08:00:00Z", "2026-10-23T08:00:00Z")],
        )
        conn.executemany(
            "INSERT INTO channel_identities (internal_user_id, channel, external_id, display_name, created_at) "
            "VALUES (?, 'zalo', ?, ?, '2026-10-23T08:00:00Z')",
            [(-1, "z1", "Chị <Lan>"), (-2, "z2", None)],
        )
        conn.executemany(
            "INSERT INTO link_requests (telegram_user_id, sub_id, item_id, product_name, link_status, created_at, original_url) "
            "VALUES (?, ?, 7, 'Mực', 'created', ?, 'u')",
            [(-1, "zaloAAA1", "2026-10-23T08:40:00Z"), (-1, "zaloAAA2", "2026-10-23T08:41:00Z"),
             (-2, "zaloBBB1", "2026-10-23T08:42:00Z")],
        )
        conn.executemany(
            "INSERT INTO shopee_clicks (click_id, sub_id, click_time, raw_json, created_at) VALUES (?, ?, ?, '{}', ?)",
            [("c1", "zaloAAA1", "2026-10-23T08:45:00Z", NOW.isoformat()),
             ("c2", "zaloAAA1", "2026-10-23T08:46:00Z", NOW.isoformat()),
             ("c3", "zaloAAA2", "2026-10-23T08:47:00Z", NOW.isoformat()),
             ("c4", None, "2026-10-23T08:48:00Z", NOW.isoformat())],
        )
        stats = collect(conn, "today", NOW)
    assert stats.top_users[0] == TopUser(-1, "Chị <Lan>", 2, 3)
    assert TopUser(-2, None, 1, 0) in stats.top_users
    assert [(link.sub_id, link.when, link.clicks) for link in stats.recent_links[:2]] == [
        ("zaloBBB1", "15:42 23/10", 0),
        ("zaloAAA2", "15:41 23/10", 1),
    ]

    bot = service(tmp_path, FakeClient(payload()), admin_user_ids=frozenset({ADMIN}))
    detail = bot.admin_panel.handle_callback(ADMIN, "c:st:today:more", "private", NOW)
    assert "1. Zalo · Chị &lt;Lan&gt; · 2 link · 3 click" in detail.text
    assert "Zalo #2 · 1 link · 0 click" in detail.text
    assert "• <code>zaloAAA2</code> 15:41 23/10 · Zalo · Chị &lt;Lan&gt; · 1 click" in detail.text
    assert "-1" not in detail.text
    assert len(detail.text) < 3500
