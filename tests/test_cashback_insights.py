"""PLAN-089: số dòng tiền / khách hàng (insights.py), màn /admin Telegram và trang web /cashback."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.cashback_insights.router import router as cashback_router
from cashback_bot import insights
from cashback_bot.admin_insights import parse_cost
from cashback_bot.admin_ui import MENU_KEYBOARD
from tests.test_cashback_payout_lifecycle import _available, _ready
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
    assert "Biên sau dự phòng" in money.text and "chưa nhập" in money.text
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
    for url, marker in (("/cashback?period=7d", "Biên sau dự phòng"), ("/cashback/users?segment=top", "HH ròng"),
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
