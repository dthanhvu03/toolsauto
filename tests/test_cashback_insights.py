"""PLAN-089: số dòng tiền / khách hàng (insights.py), màn /admin Telegram và trang web /cashback. PLAN-090: mục tiêu. PLAN-091: tìm mã. PLAN-092: bản tin tối."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.cashback_insights.router import router as cashback_router
from cashback_bot import insights, ops_watch
from cashback_bot.admin_insights import parse_cost, parse_goal
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_ui import MENU_KEYBOARD
from cashback_bot.db import TrackingRepository
from tests.test_cashback_payout_lifecycle import T as PAY_T
from tests.test_cashback_payout_lifecycle import _available, _b3, _ready
from tests.test_cashback_reserve import LINK as RESERVE_LINK
from tests.test_cashback_reserve import NOW as RESERVE_NOW
from tests.test_cashback_reserve import _bot as _reserve_bot
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link, _order

NOW = datetime.now(timezone.utc)


def _entries(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM cashback_entries").fetchall()


def _view(bot, period="all"):
    with insights.open_readonly(bot.repo.path) as conn:
        return insights.overview(conn, period, NOW)


def test_dong_tien_tam_tinh_bien_va_huy(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, commission=10_000, cid="a")
    _order(bot, sub, commission=4_000, cid="b")
    _order(bot, sub, status="CANCELLED", commission=2_000, cid="c")
    bot.refresh_wallet(NOW)
    rows = {r["conversion_id"]: r for r in _entries(bot)}
    m = _view(bot).money
    live = [rows["a"], rows["b"]]
    assert (m.orders, m.net, m.cashback) == (2, 14_000, sum(r["cashback_vnd"] for r in live))
    assert m.reserve == sum(r["fee_vnd"] + r["tax_vnd"] for r in live)
    assert m.margin == m.net - m.cashback - m.reserve and m.margin_before_reserve == m.net - m.cashback
    assert (m.cancelled_orders, m.cancelled_net) == (1, 2_000)
    assert m.settled_net == 0 and m.profit is None, "chưa nhập chi phí vận hành thì không bịa lãi"
    assert _view(bot).liabilities.pending == m.cashback


def test_chi_phi_van_hanh_chia_theo_so_ngay(tmp_path):
    bot = _bot(tmp_path)
    _order(bot, _link(bot), commission=100_000, cid="a")
    bot.refresh_wallet(NOW)
    bot.repo.set_state(insights.OPS_COST_KEY, "3000000")
    m = _view(bot, "30d").money
    assert m.ops_cost == 3_000_000 and m.profit == m.margin - 3_000_000
    assert _view(bot, "7d").money.ops_cost == 700_000


def test_thuc_va_thu_hoi_tinh_vao_bien(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    bot.refresh_wallet(NOW)
    full = _view(bot).money
    assert full.settled_net == 20_000 and full.settled_margin == full.margin
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(NOW)
    after = _view(bot).money
    assert after.net == 10_000 and after.cashback == full.cashback // 2, "dòng thu hồi trừ cả hoa hồng lẫn phần khách"
    assert after.orders == 1


def test_nhom_khach_va_canh_bao(tmp_path):
    bot = _bot(tmp_path, allowed_telegram_ids=frozenset({USER, 222}))
    _order(bot, _link(bot), commission=50_000, cid="a")
    bot.handle_text(222, "khac", "/start", update_id=3, now=NOW)
    bot.refresh_wallet(NOW)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE telegram_users SET notify_blocked_at = 'x' WHERE telegram_user_id = 222")
    with insights.open_readonly(bot.repo.path) as conn:
        people = {c.user_id: c for c in insights.customers(conn, NOW)}
    assert people[USER].segment == "top" and people[USER].orders == 1 and people[USER].margin > 0
    assert people[222].segment == "attention" and "chặn bot" in people[222].flags
    assert insights.sort_customers(list(people.values()))[0].user_id == USER


def test_van_hanh_bao_bot_im_va_khac_code(tmp_path):
    bot = _bot(tmp_path)
    bot.repo.set_state("telegram_heartbeat", str(time.time()))
    bot.repo.set_state("zalo_heartbeat", str(time.time() - 3_600))
    bot.repo.set_state("code_version:telegram", "aaaaaaa@1")
    bot.repo.set_state("code_version:zalo", "aaaaaaa@1")
    with insights.open_readonly(bot.repo.path) as conn:
        checks = {c.code: c for c in insights.operations(conn, NOW)}
    assert not checks["bots"].ok and checks["zalo"].ok and checks["ledger"].ok


def test_dong_thoi_gian_khach_khong_lo_so_tai_khoan(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(NOW)
    with bot.repo.connect() as conn:
        conn.execute("INSERT INTO bank_accounts (telegram_user_id, bank_code, account_no, account_name, updated_at) "
                     "VALUES (?, 'MB', '0123456789', 'NGUYEN VAN A', 'x')", (USER,))
    with insights.open_readonly(bot.repo.path) as conn:
        events = insights.timeline(conn, USER)
        prof = insights.profile(conn, USER)
    assert {e.kind for e in events} >= {"link", "order"}
    assert prof.bank == "MB ••••6789 · NGUYEN VAN A" and "0123456789" not in str(events)


# --- Telegram /admin ---------------------------------------------------------------------------------


def test_menu_admin_co_4_man_moi():
    data = [d for row in MENU_KEYBOARD for _label, d in row]
    assert {"c:in:m:30d", "c:in:g:30d", "c:in:o", "c:in:u:margin:1"} <= set(data)


def test_man_telegram_dong_tien_tang_truong_khach(tmp_path):
    bot = _bot(tmp_path)
    _order(bot, _link(bot), commission=10_000, cid="a")
    bot.refresh_wallet(NOW)
    money = _callback(bot, ADMIN, "c:in:m:all")
    assert "Biên" in money.text and "chưa nhập" in money.text
    assert "Phễu" in _callback(bot, ADMIN, "c:in:g:7d").text
    assert "Hai bot sống" in _callback(bot, ADMIN, "c:in:o").text
    users = _callback(bot, ADMIN, "c:in:u:margin:1")
    assert f"c:in:d:{USER}" in str(users.inline_keyboard)
    detail = _callback(bot, ADMIN, f"c:in:d:{USER}")
    assert "Gần đây" in detail.text and f"c:wl:u:{USER}" in str(detail.inline_keyboard)


def test_admin_nhap_chi_phi_van_hanh(tmp_path):
    bot = _bot(tmp_path)
    assert "Gõ tổng chi phí" in _callback(bot, ADMIN, "c:in:cost").text
    assert "Chưa đọc được" in bot.admin_panel.consume_text(ADMIN, "nhiều lắm", NOW).text
    saved = bot.admin_panel.consume_text(ADMIN, "1,5tr", NOW)
    assert "1.500.000đ/tháng" in saved.text and bot.repo.get_state(insights.OPS_COST_KEY) == "1500000"
    assert bot.admin_panel.consume_text(ADMIN, "2000000", NOW) is None, "lưu xong thì thôi chờ"
    assert "Chi phí vận hành / hạ tầng: chưa nhập → 1.500.000đ mỗi tháng" in _callback(bot, ADMIN, "c:menu:hist").text


def test_doc_so_chi_phi():
    assert [parse_cost(t) for t in ("1500000", "1.500.000", "1,5tr", "800k", "0", "abc", "-5")] == [
        1_500_000, 1_500_000, 1_500_000, 800_000, 0, None, None]


# --- Web /cashback ----------------------------------------------------------------------------------


def _web(tmp_path, monkeypatch):
    bot = _bot(tmp_path)
    _order(bot, _link(bot), commission=10_000, cid="a")
    bot.refresh_wallet(NOW)
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    app = FastAPI()
    app.include_router(cashback_router)
    return TestClient(app), Path(bot.repo.path)


def test_web_trang_tong_quan_khach_va_chi_tiet(tmp_path, monkeypatch):
    client, _path = _web(tmp_path, monkeypatch)
    for url, marker in (("/cashback?period=7d", "Biên"), ("/cashback/users?segment=top", "HH ròng"),
                        (f"/cashback/users/{USER}", "Dòng thời gian")):
        page = client.get(url)
        assert page.status_code == 200 and marker in page.text, url
    assert client.get("/cashback/users/424242").status_code == 404


def test_web_chi_doc_db(tmp_path, monkeypatch):
    client, path = _web(tmp_path, monkeypatch)
    before = path.stat().st_mtime_ns
    for url in ("/cashback", "/cashback/users", f"/cashback/users/{USER}"):
        client.get(url)
    assert path.stat().st_mtime_ns == before


def test_moc_ky(tmp_path):
    bot = _bot(tmp_path)
    with insights.open_readonly(bot.repo.path) as conn:
        assert insights.period_bounds(conn, "7d", NOW) == (NOW - timedelta(days=7), 7)
        start, days = insights.period_bounds(conn, "month", NOW)
        assert start.day == 1 and days >= 1


# --- Hoà vốn ----------------------------------------------------------------------------------------


def test_hoa_von_theo_muc_hoan(tmp_path):
    bot = _bot(tmp_path)
    _order(bot, _link(bot), commission=10_000, cid="a")
    bot.refresh_wallet(NOW)
    with insights.open_readonly(bot.repo.path) as conn:
        assert insights.breakeven(conn, NOW).rows[0].need_net_month is None, "chưa có chi phí thì không tính"
    bot.repo.set_state(insights.OPS_COST_KEY, "1000000")
    with insights.open_readonly(bot.repo.path) as conn:
        b = insights.breakeven(conn, NOW)
    assert b.formula == "v1.1" and round(b.current_share, 2) == 0.70 and b.current.share_percent == 70
    row = b.current
    assert abs(row.margin_rate - (1 - 0.70 - b.reserve_rate)) < 1e-9
    assert row.need_net_month * row.margin_rate >= 1_000_000 - 1
    assert row.need_orders_month == -(-row.need_net_month // b.net_per_order)
    assert [r.need_net_month for r in b.rows] == sorted(r.need_net_month for r in b.rows), "hoàn càng nhiều càng cần nhiều"
    assert abs(insights.margin_rate(0.7, 0.1, "v1.2") - 0.27) < 1e-9


def test_hoa_von_theo_chinh_sach_link_moi_nhat(tmp_path):
    """Sổ chỉ có đơn link cũ (V1.1); link mới đã sang V1.2 thì hoà vốn tính theo V1.2 (production 26/10)."""
    old = _reserve_bot(tmp_path, v12=False)
    old.handle_text(USER, "buyer", RESERVE_LINK, update_id=1, now=RESERVE_NOW)
    with old.repo.connect() as conn:
        sub = conn.execute("SELECT sub_id FROM link_requests").fetchone()[0]
    _order(old, sub, commission=10_000, cid="a")
    old.refresh_wallet(RESERVE_NOW)
    old.repo.set_state(insights.OPS_COST_KEY, "1000000")
    with insights.open_readonly(old.repo.path) as conn:
        assert insights.breakeven(conn, RESERVE_NOW).formula == "v1.1"
    newer = _reserve_bot(tmp_path)
    newer.handle_text(USER, "buyer", RESERVE_LINK, update_id=2, now=RESERVE_NOW)
    with newer.repo.connect() as conn:
        snap = conn.execute("SELECT pricing_version, share_bps, fee_bps, tax_reserve_bps FROM link_policy_snapshots "
                            "ORDER BY link_id DESC LIMIT 1").fetchone()
    with insights.open_readonly(newer.repo.path) as conn:
        b = insights.breakeven(conn, RESERVE_NOW)
    assert snap[0].startswith("v1.2") and b.formula == "v1.2" and b.current_share == snap[1] / 10_000
    assert abs(b.reserve_rate - (snap[2] + snap[3]) / 10_000) < 1e-9
    assert abs(b.current.margin_rate - (1 - b.current_share) * (1 - b.reserve_rate)) < 1e-9


def test_man_hoa_von_telegram_va_web(tmp_path, monkeypatch):
    bot = _bot(tmp_path)
    assert "Chưa có chi phí vận hành" in _callback(bot, ADMIN, "c:in:b").text
    _order(bot, _link(bot), commission=10_000, cid="a")
    bot.refresh_wallet(NOW)
    bot.repo.set_state(insights.OPS_COST_KEY, "1000000")
    text = _callback(bot, ADMIN, "c:in:b").text
    assert "👉 70%" in text and "không đổi % hoàn" in text
    assert "c:in:b" in str(_callback(bot, ADMIN, "c:in:m:30d").inline_keyboard)
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    app = FastAPI()
    app.include_router(cashback_router)
    page = TestClient(app).get("/cashback")
    assert page.status_code == 200 and "Hoà vốn theo mức % hoàn" in page.text and "👉 70%" in page.text


# --- Mục tiêu (PLAN-090) ----------------------------------------------------------------------------


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _goals(bot, now=NOW):
    with insights.open_readonly(bot.repo.path) as conn:
        return insights.goals(conn, now)


def test_muc_tieu_so_that_trang_thai_va_moc(tmp_path):
    bot = _bot(tmp_path)
    _order(bot, _link(bot), status="COMPLETED", complete=_stamp(NOW), cid="a")
    bot.refresh_wallet(NOW)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE telegram_users SET created_at = ?", (_stamp(NOW - timedelta(days=10)),))
        conn.execute("UPDATE shopee_conversions SET purchase_time = ?", (_stamp(NOW - timedelta(days=9)),))
    g = _goals(bot)
    assert all(r.status == "unset" for r in g.rows), "chưa nhập thì bot không tự đặt mục tiêu"
    fresh = _goals(bot, NOW - timedelta(days=9))
    assert fresh.row("activation").actual is None and fresh.activation_waiting == 1, "khách chưa đủ 7 ngày: chưa có mẫu"
    assert g.row("completed").actual == 1 and g.row("active").actual == 1
    assert (g.row("activation").actual, g.activation_size, g.activation_waiting) == (100.0, 1, 0)
    assert [ok for _label, ok in g.milestones] == [True, True, False, False] and g.stage.startswith("G1")
    assert {c.code for c in g.guards} >= {"losing", "owing", "notices", "tickets", "ledger"}
    bot.repo.set_state(insights.GOALS_KEY, json.dumps({"completed": 1, "active": 5, "cancel": 10, "bad": 3, "new": "x"}))
    g = _goals(bot)
    assert (g.row("completed").status, g.row("active").status, g.row("cancel").status) == ("done", "behind", "done")
    assert g.row("new").target is None, "mục hỏng hoặc lạ thì bỏ qua"
    bot.repo.set_state(insights.GOALS_KEY, json.dumps({"completed": 10_000}))
    far = _goals(bot).row("completed")
    assert far.status == "behind" and far.per_day and far.forecast is not None and far.forecast < 10_000


def test_man_muc_tieu_telegram_nhap_bo_va_lich_su(tmp_path):
    bot = _bot(tmp_path)
    assert "c:in:t" in [d for row in MENU_KEYBOARD for _label, d in row]
    screen = _callback(bot, ADMIN, "c:in:t")
    assert "Giai đoạn" in screen.text and "chưa đặt" in screen.text and "c:in:t:completed" in str(screen.inline_keyboard)
    ask = _callback(bot, ADMIN, "c:in:t:completed")
    assert "Gợi ý G2: 100" in ask.text
    assert "Chưa đọc được" in bot.admin_panel.consume_text(ADMIN, "nhiều", NOW).text
    saved = bot.admin_panel.consume_text(ADMIN, "100", NOW)
    assert "Đã đặt mục tiêu" in saved.text and json.loads(bot.repo.get_state(insights.GOALS_KEY)) == {"completed": 100}
    assert bot.admin_panel.consume_text(ADMIN, "200", NOW) is None, "lưu xong thì thôi chờ"
    _callback(bot, ADMIN, "c:in:t:net")
    assert "5.000.000đ" in bot.admin_panel.consume_text(ADMIN, "5tr", NOW).text
    _callback(bot, ADMIN, "c:in:t:completed")
    assert "Đã bỏ" in bot.admin_panel.consume_text(ADMIN, "bỏ", NOW).text
    assert json.loads(bot.repo.get_state(insights.GOALS_KEY)) == {"net": 5_000_000}
    _callback(bot, ADMIN, "c:in:t:cancel")
    _callback(bot, ADMIN, "c:in:o")
    assert bot.admin_panel.consume_text(ADMIN, "10", NOW) is None, "bấm màn khác thì thôi chờ"
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "Mục tiêu: Đơn hoàn thành trong tháng chưa đặt → 100" in history
    assert "Mục tiêu: Đơn hoàn thành trong tháng 100 → bỏ" in history
    assert "Mục tiêu: Hoa hồng ròng trong tháng chưa đặt → 5.000.000đ" in history


def test_doc_so_muc_tieu():
    assert [parse_goal("count", t) for t in ("100", "1.000", "0", "abc", "-3")] == [100, 1_000, None, None, None]
    assert [parse_goal("percent", t) for t in ("30", "30%", "12,5", "0", "101")] == [30, 30, 12, 0, None]
    assert [parse_goal("vnd", t) for t in ("5tr", "800k", "0")] == [5_000_000, 800_000, None]


def test_web_the_muc_tieu(tmp_path, monkeypatch):
    client, path = _web(tmp_path, monkeypatch)
    TrackingRepository(str(path)).set_state(insights.GOALS_KEY, json.dumps({"completed": 100, "cancel": 10}))
    page = client.get("/cashback")
    assert page.status_code == 200 and "Mục tiêu tháng" in page.text and "Giới hạn an toàn" in page.text
    assert "tối đa 10%" in page.text


def test_van_hanh_bao_link_ket_cu_ngoai_24_gio(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE link_requests SET delivery_status = 'pending', created_at = ?",
                     (_stamp(NOW - timedelta(days=2)),))
    with insights.open_readonly(bot.repo.path) as conn:
        check = next(c for c in insights.operations(conn, NOW) if c.code == "links")
    assert not check.ok and "kẹt quá 1 giờ (từ đầu): 1" in check.value
    assert "links" in {c.code for c in _goals(bot).guards}


# --- Tìm mã (PLAN-091) ------------------------------------------------------------------------------


def _search(bot, query):
    with insights.open_readonly(bot.repo.path) as conn:
        return insights.search(conn, query)


def test_tim_ma_link_don_khach_san_pham(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, cid="conv-1")
    bot.refresh_wallet(NOW)
    with bot.repo.connect() as conn:
        link_id = conn.execute("SELECT id FROM link_requests WHERE sub_id = ?", (sub,)).fetchone()[0]
    for query in (sub, sub.lower(), f"https://s.shopee.vn/an_redir?origin_link=x&sub_id={sub}"):
        hits = _search(bot, query)
        assert hits and hits[0].kind == "link" and hits[0].ref == link_id, query
    order = _search(bot, "sn-conv-1")
    assert [(h.kind, h.ref) for h in order] == [("order", link_id)], "mã đơn không phân biệt hoa thường"
    assert [h.kind for h in _search(bot, str(USER))] == ["user"]
    assert [h.kind for h in _search(bot, "@buy")] == ["user"]
    assert [h.kind for h in _search(bot, "polo")] == ["link"], "tên có dấu, khác hoa thường vẫn tìm ra"
    assert _search(bot, "x") == [] and _search(bot, "") == [] and _search(bot, "#999") == []
    with insights.open_readonly(bot.repo.path) as conn:
        detail = insights.link_detail(conn, link_id)
        assert insights.link_detail(conn, 424242) is None
    assert detail.sub_id == sub and detail.user_id == USER and detail.delivery_status == "pending"
    assert [o.order_sn for o in detail.orders] == ["SN-conv-1"] and len(detail.entries) == 1


def test_tim_ticket_va_yeu_cau_rut(tmp_path):
    bot = _b3(tmp_path)
    payout, _code = bot.wallet.request_payout(USER, PAY_T, amount=20_000)
    pid = payout["id"]
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO support_tickets (telegram_user_id, category, message, status, created_at, updated_at) "
            "VALUES (?, 'missing', 'không thấy đơn', 'OPEN', ?, ?)", (USER, _stamp(NOW), _stamp(NOW)))
        ticket = conn.execute("SELECT MAX(id) FROM support_tickets").fetchone()[0]
    assert [(h.kind, h.ref) for h in _search(bot, f"#{ticket}")] == [("ticket", ticket)]
    assert [(h.kind, h.ref) for h in _search(bot, f"Hoan tien {pid:06d}")] == [("payout", pid)]


def test_man_tim_telegram_lenh_va_nut(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    assert "c:in:f" in [d for row in MENU_KEYBOARD for _label, d in row]
    reply = bot.handle_text(ADMIN, "admin", f"/tim {sub}", update_id=77, now=NOW)
    assert "1 kết quả" in reply.text and "c:in:l:" in str(reply.inline_keyboard)
    target = next(d for row in reply.inline_keyboard for _l, d in row if d.startswith("c:in:l:"))
    detail = _callback(bot, ADMIN, target)
    assert f"Link {sub}" in detail.text and "chưa giao" in detail.text and "về trễ" in detail.text
    assert f"c:in:d:{USER}" in str(detail.inline_keyboard)
    ask = _callback(bot, ADMIN, "c:in:f")
    assert "mã link 8 ký tự" in ask.text
    found = bot.admin_panel.consume_text(ADMIN, sub, NOW)
    assert found is not None and "1 kết quả" in found.text
    assert bot.admin_panel.consume_text(ADMIN, sub, NOW) is None, "tìm xong thì thôi chờ"
    assert "Không thấy kết quả" in bot.handle_text(ADMIN, "admin", "/tim khongcoma", update_id=78, now=NOW).text
    assert "kết quả" not in bot.handle_text(USER, "buyer", f"/tim {sub}", update_id=80, now=NOW).text, "khách không tìm được"


def test_web_tim_va_chi_tiet_link(tmp_path, monkeypatch):
    client, path = _web(tmp_path, monkeypatch)
    with insights.open_readonly(str(path)) as conn:
        sub, link_id = conn.execute("SELECT sub_id, id FROM link_requests").fetchone()
    page = client.get(f"/cashback/search?q={sub}")
    assert page.status_code == 200 and f"/cashback/links/{link_id}" in page.text
    detail = client.get(f"/cashback/links/{link_id}")
    assert detail.status_code == 200 and f"Link {sub}" in detail.text and "Sổ ví" in detail.text
    assert client.get("/cashback/links/424242").status_code == 404
    assert "Không thấy kết quả" in client.get("/cashback/search?q=khongcoma").text
    assert 'action="/cashback/search"' in client.get("/cashback").text


# --- Bản tin tối (PLAN-092) -------------------------------------------------------------------------


def _briefs(bot):
    with bot.repo.connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT message_html FROM admin_notifications WHERE event_type = 'NIGHTLY_BRIEF' ORDER BY id")]


def _recent(bot):
    """Đơn mẫu đặt lúc PURCHASE cố định; dời về NOW để số «hôm nay», «7 ngày» không hỏng theo ngày chạy test."""
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET purchase_time = ?", (_stamp(NOW),))
        conn.execute("UPDATE cashback_entries SET purchase_time = ?", (_stamp(NOW),))


def test_ban_tin_toi_moi_ngay_mot_lan_va_moc_moi(tmp_path):
    bot = _bot(tmp_path)
    admin = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
    sub = _link(bot)
    _order(bot, sub, cid="a")
    bot.refresh_wallet(NOW)
    _recent(bot)
    bot.repo.set_state(insights.GOALS_KEY, json.dumps({"completed": 100}))
    evening = NOW.astimezone(ops_watch.ICT).replace(hour=20, minute=50)
    ops_watch.check_nightly_brief(bot.repo, admin, now=evening)
    assert _briefs(bot) == [], "chưa tới 21 giờ"
    ops_watch.check_nightly_brief(bot.repo, admin, now=evening.replace(hour=21, minute=1))
    ops_watch.check_nightly_brief(bot.repo, admin, now=evening.replace(hour=23))
    briefs = _briefs(bot)
    assert len(briefs) == 1, "mỗi ngày một lần"
    text = briefs[0]
    assert "Bản tin tối" in text and "Hôm nay" in text and "/ 100" in text and "Top khách 7 ngày" in text
    assert "Mốc mới" not in text, "bản tin đầu tiên không báo mốc đã đạt từ trước"
    _order(bot, sub, status="COMPLETED", complete=_stamp(NOW), cid="b")
    bot.refresh_wallet(NOW)
    ops_watch.check_nightly_brief(bot.repo, admin, now=evening.replace(hour=21) + timedelta(days=1))
    assert "Mốc mới: <b>Đơn đầu tiên hoàn thành</b>" in _briefs(bot)[-1]


def test_so_lieu_hom_nay_va_top_tuan(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    _order(bot, sub, commission=10_000, cid="a")
    bot.refresh_wallet(NOW)
    _recent(bot)
    with insights.open_readonly(bot.repo.path) as conn:
        today = insights.day_stats(conn, NOW)
        top = insights.top_since(conn, NOW - timedelta(days=7))
    assert (today.new, today.links, today.orders, today.net) == (1, 1, 1, 10_000)
    assert top == [("@buyer", 1, 10_000)]
