"""PLAN-154: hạng Đồng/Bạc/Vàng xét theo 2 tháng. Khách mới Đồng, khách cũ Vàng tới hết 2026. Không gọi mạng."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from cashback_bot import membership
from cashback_bot.admin.handlers.membership import MembershipAdmin
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import hang_message, rank_down_notice, rank_keep_notice, rank_up_notice
from cashback_bot.terms_content import DRAFT_SECTIONS, DRAFT_VERSION
from tests.test_cashback_bot import NOW, FakeClient, payload, service

LINK = "https://shopee.vn/product/9/8"
OLD, NEW = 111, 222


def at(year, month, day, hour=5):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _bot(tmp_path, **overrides):
    overrides.setdefault("customer_access_enabled", True)
    return service(tmp_path, FakeClient(payload(commission=20_000)), **overrides)


def _rows(tmp_path, sql):
    with sqlite3.connect(tmp_path / "cashback.sqlite") as conn:
        return conn.execute(sql).fetchall()


# --- Tỷ lệ theo hạng lúc tạo link ---------------------------------------------------------------


def test_tat_hang_thi_moi_khach_van_70_va_khong_xep_hang(tmp_path):
    bot = _bot(tmp_path)
    assert "14.000đ" in bot.handle_text(NEW, "moi", LINK, update_id=1, now=NOW).text
    assert _rows(tmp_path, "SELECT COUNT(*) FROM member_ranks") == [(0,)]
    assert bot._resolve_for(None, NOW).share_bps == 7_000
    assert "chưa chính thức áp dụng" in bot.handle_text(NEW, "moi", "/hang", update_id=2, now=NOW).text


def test_bat_hang_khach_cu_vang_khach_moi_dong(tmp_path):
    _bot(tmp_path).handle_text(OLD, "cu", LINK, update_id=1, now=NOW)
    bot = _bot(tmp_path, membership_enabled=True)
    assert _rows(tmp_path, "SELECT user_id, rank_code, reason FROM member_ranks") == [(OLD, "GOLD", "khach_cu")]
    assert "14.000đ" in bot.handle_text(OLD, "cu", LINK, update_id=2, now=NOW).text
    assert "12.000đ" in bot.handle_text(NEW, "moi", LINK, update_id=3, now=NOW).text
    rates = _rows(tmp_path, "SELECT telegram_user_id, cashback_rate_percent FROM link_requests ORDER BY id")
    assert rates == [(OLD, 70), (OLD, 70), (NEW, 60)]


def test_xep_khach_cu_chi_mot_lan(tmp_path):
    _bot(tmp_path, membership_enabled=True)
    bot = _bot(tmp_path, membership_enabled=True)
    bot.handle_text(NEW, "moi", LINK, update_id=1, now=NOW)
    _bot(tmp_path, membership_enabled=True)
    assert _rows(tmp_path, "SELECT COUNT(*) FROM member_ranks") == [(0,)]
    assert bot._resolve_for(NEW, NOW).share_bps == 6_000


def test_v12_snapshot_luu_ty_le_hang(tmp_path):
    bot = _bot(tmp_path, membership_enabled=True, estimate_policy="v1.2")
    bot.handle_text(NEW, "moi", LINK, update_id=1, now=NOW)
    assert _rows(tmp_path, "SELECT share_bps FROM link_policy_snapshots") == [(6_000,)]


def test_deal_gui_chung_tinh_muc_dong(tmp_path):
    assert _bot(tmp_path, membership_enabled=True)._resolve_for(None, NOW).share_bps == 6_000


def test_ty_le_hang_khong_vuot_ty_le_chung():
    rates = {"BRONZE": 6_000, "SILVER": 6_500, "GOLD": 7_000}
    assert membership.share_bps("GOLD", rates, 7_000) == 7_000
    assert membership.share_bps("GOLD", rates, 5_000) == 5_000
    assert membership.share_bps("BRONZE", rates, 7_000) == 6_000


# --- Xét hạng theo tháng --------------------------------------------------------------------------


def _ledger() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cashback_entries (conversion_id TEXT PRIMARY KEY, telegram_user_id INTEGER, "
                 "order_sn TEXT, cashback_vnd INTEGER, status TEXT, completed_at TEXT)")
    conn.execute("CREATE TABLE bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    membership.ensure_schema(conn)
    return conn


def _orders(conn, user, count, each, when, status="holding"):
    start = conn.execute("SELECT COUNT(*) FROM cashback_entries").fetchone()[0]
    for index in range(start, start + count):
        conn.execute("INSERT INTO cashback_entries VALUES (?, ?, ?, ?, ?, ?)",
                     (f"c{index}", user, f"o{index}", each, status,
                      None if status == "pending" else when.strftime("%Y-%m-%dT%H:%M:%SZ")))


def _rank(conn, user, code, reason="du_nguong"):
    conn.execute("INSERT INTO member_ranks VALUES (?, ?, ?, '2026-11-01T00:00:00Z')", (user, code, reason))


def _mark_reviewed(conn, month):
    conn.execute("INSERT OR REPLACE INTO bot_state VALUES (?, ?)", (membership.REVIEWED_KEY, month))


def test_len_ngay_khi_du_trong_thang_truoc_va_thang_nay():
    conn = _ledger()
    _mark_reviewed(conn, "2026-11")
    _orders(conn, NEW, 1, 20_000, at(2026, 10, 10))
    assert membership.tick(conn, at(2026, 11, 20)) == []
    _orders(conn, NEW, 1, 20_000, at(2026, 11, 19))
    assert membership.tick(conn, at(2026, 11, 20)) == [membership.Change(NEW, "up", "BRONZE", "SILVER")]
    assert membership.tick(conn, at(2026, 11, 20)) == []
    assert membership.rank_of(conn, NEW) == "SILVER"


def test_don_cu_hon_2_thang_huy_chua_hoan_thanh_khong_tinh():
    conn = _ledger()
    _mark_reviewed(conn, "2026-11")
    _orders(conn, NEW, 5, 50_000, at(2026, 9, 25))
    _orders(conn, NEW, 5, 50_000, at(2026, 11, 2), status="cancelled")
    _orders(conn, NEW, 5, 50_000, at(2026, 11, 2), status="pending")
    _orders(conn, NEW, 1, 50_000, at(2026, 11, 2))
    assert membership.tick(conn, at(2026, 11, 20)) == []
    progress = membership.progress(conn, NEW, at(2026, 11, 20))
    assert (progress.orders, progress.need_orders, progress.need_vnd) == (1, 1, 0)
    assert progress.window == "tháng 10 và tháng 11"


def test_dau_thang_xuong_mot_bac_moi_lan():
    conn = _ledger()
    _rank(conn, NEW, "GOLD")
    _mark_reviewed(conn, "2026-11")
    assert membership.tick(conn, at(2027, 1, 1)) == [membership.Change(NEW, "down", "GOLD", "SILVER")]
    assert membership.tick(conn, at(2027, 1, 5)) == []
    assert membership.tick(conn, at(2027, 2, 1)) == [membership.Change(NEW, "down", "SILVER", "BRONZE")]
    reasons = conn.execute("SELECT to_code, reason FROM member_rank_events ORDER BY id").fetchall()
    assert reasons == [("SILVER", "xet_thang"), ("BRONZE", "xet_thang")]


def test_dau_thang_du_hai_thang_vua_qua_thi_giu_hang():
    conn = _ledger()
    _rank(conn, NEW, "GOLD")
    _orders(conn, NEW, 6, 15_000, at(2026, 11, 10))
    assert membership.tick(conn, at(2026, 12, 1)) == []
    assert membership.tick(conn, at(2027, 1, 1)) == []
    assert membership.tick(conn, at(2027, 2, 1)) == [membership.Change(NEW, "down", "GOLD", "SILVER")]


def test_khach_cu_giu_vang_toi_het_thang_12():
    conn = _ledger()
    _rank(conn, OLD, "GOLD", reason="khach_cu")
    assert membership.tick(conn, at(2026, 12, 1)) == []
    assert membership.progress(conn, OLD, at(2026, 11, 20)).protected_until == "31/12/2026"
    assert membership.progress(conn, OLD, at(2026, 12, 20)).protected_until is None
    assert membership.tick(conn, at(2027, 1, 1)) == [membership.Change(OLD, "down", "GOLD", "SILVER")]


def test_nhac_giu_hang_ngay_24_mot_lan_khong_nhac_khach_con_bao_ve():
    conn = _ledger()
    _rank(conn, NEW, "GOLD")
    _rank(conn, OLD, "GOLD", reason="khach_cu")
    _mark_reviewed(conn, "2026-11")
    _orders(conn, NEW, 4, 10_000, at(2026, 11, 3))
    assert membership.tick(conn, at(2026, 11, 23)) == []
    assert membership.tick(conn, at(2026, 11, 24)) == [membership.Change(NEW, "keep", "GOLD", "GOLD", 2, 50_000)]
    assert membership.tick(conn, at(2026, 11, 28)) == []
    _mark_reviewed(conn, "2026-12")
    reminded = membership.tick(conn, at(2026, 12, 24))
    assert sorted((c.user_id, c.kind) for c in reminded) == [(OLD, "keep"), (NEW, "keep")]


def test_nguong_admin_cau_hinh_va_nguong_sai_thu_tu_ve_mac_dinh():
    conn = _ledger()
    _mark_reviewed(conn, "2026-11")
    conn.execute("INSERT INTO bot_state VALUES (?, ?)", (membership.THRESHOLDS_KEY, json.dumps({"silver_orders": 3})))
    _orders(conn, NEW, 2, 20_000, at(2026, 11, 3))
    assert membership.tick(conn, at(2026, 11, 20)) == []
    conn.execute("UPDATE bot_state SET value = ? WHERE key = ?",
                 (json.dumps({"silver_orders": 9, "gold_orders": 3}), membership.THRESHOLDS_KEY))
    assert membership.thresholds(conn) == membership.DEFAULTS
    assert membership.tick(conn, at(2026, 11, 20)) == [membership.Change(NEW, "up", "BRONZE", "SILVER")]


def test_bot_gui_tin_len_hang_qua_hang_doi(tmp_path):
    bot = _bot(tmp_path, membership_enabled=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with sqlite3.connect(tmp_path / "cashback.sqlite") as conn:
        for index in range(2):
            conn.execute("INSERT INTO cashback_entries (conversion_id, telegram_user_id, order_sn, commission_vnd, "
                         "cashback_vnd, status, completed_at, created_at, updated_at) "
                         "VALUES (?, ?, ?, 30000, 20000, 'holding', ?, ?, ?)",
                         (f"c{index}", NEW, f"o{index}", stamp, stamp, stamp))
    bot._promote(now)
    sent = _rows(tmp_path, "SELECT chat_id, event_type, audience FROM admin_notifications WHERE event_type = 'RANK_UP'")
    assert sent == [(NEW, "RANK_UP", "customer")]
    page = bot.handle_text(NEW, "moi", "/hang", update_id=1, now=NOW).text
    assert "🥈 Bạc" in page and "%" not in page


# --- Lời cho khách, điều khoản, admin ---------------------------------------------------------------


def test_trang_hang_va_tin_khong_dua_ty_le(tmp_path):
    bot = _bot(tmp_path, membership_enabled=True)
    page = bot.handle_text(NEW, "moi", "/hang", update_id=1, now=NOW).text
    assert "🥉 Đồng" in page and "Còn <b>2</b> đơn và <b>30.000đ</b> tiền hoàn nữa là lên" in page
    for text in (page, rank_up_notice("SILVER"), rank_down_notice("SILVER"), rank_keep_notice("GOLD", 2, 0)):
        assert "%" not in text
    assert "đang được phát triển" in hang_message()


def test_dieu_khoan_v4_co_muc_hang():
    assert DRAFT_VERSION == "V4"
    body = {key: text for key, _label, text in DRAFT_SECTIONS}["hang"]
    assert "tháng trước và tháng này" in body and "một bậc" in body and "31/12/2026" in body
    assert "%" not in body and len(body) < 3_500


def test_admin_doi_nguong_va_chan_vang_thap_hon_bac(tmp_path):
    _bot(tmp_path)
    audit = []
    admin = MembershipAdmin(TrackingRepository(str(tmp_path / "cashback.sqlite")),
                            audit=lambda *args: audit.append(args[1:4]))
    assert "2 đơn" in admin.route(7, "c:mb:home", NOW).text
    admin.route(7, "c:mb:e:silver_vnd", NOW)
    saved = admin.consume_text(7, "50.000", NOW)
    assert "✅ Đã lưu" in saved.text and "50.000đ" in saved.text
    assert audit == [("membership_thresholds", {"key": "silver_vnd", "value": 30_000},
                      {"key": "silver_vnd", "value": 50_000})]
    admin.route(7, "c:mb:e:silver_orders", NOW)
    refused = admin.consume_text(7, "10", NOW)
    assert "Chưa lưu" in refused.text
    with sqlite3.connect(tmp_path / "cashback.sqlite") as conn:
        assert membership.thresholds(conn)["silver_orders"] == 2


def test_the_link_hien_tien_them_nho_hang(tmp_path):
    _bot(tmp_path).handle_text(OLD, "cu", LINK, update_id=1, now=NOW)
    bot = _bot(tmp_path, membership_enabled=True)
    gold = bot.handle_text(OLD, "cu", LINK, update_id=2, now=NOW).text
    assert "🏅 Hạng 🥇 Vàng: đã cộng thêm 2.000đ so với hạng Đồng" in gold
    bronze = bot.handle_text(NEW, "moi", LINK, update_id=3, now=NOW).text
    assert "🏅 Lên 🥇 Vàng, món này hoàn thêm 2.000đ · /hang" in bronze
    for text in (gold, bronze):
        assert "%" not in text


def test_tat_hang_the_link_khong_co_dong_hang(tmp_path):
    assert "🏅" not in _bot(tmp_path).handle_text(NEW, "moi", LINK, update_id=1, now=NOW).text
