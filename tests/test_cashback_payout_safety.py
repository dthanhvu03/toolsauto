"""PLAN-088: sổ chi trả trước khi mở ví (B1–B17 trong reports/CASHBACK_REVIEW_2026-10-25.md).

Mọi dữ liệu «đủ điều kiện» chỉ nằm trong DB test (fixture), không có công tắc bỏ qua trong code.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from cashback_bot import db, payout_readiness, payouts, support
from cashback_bot.admin_stats import _csv_cell
from cashback_bot.admin_ui import PAYOUT_TEXT_MAX, payout_text
from cashback_bot.poller import process_updates
from cashback_bot.zalo_bot import ZaloChannel
from tests.test_cashback_payout_lifecycle import ACCOUNT, T, _advance, _available, _ready, _rows, _status, _to
from tests.test_cashback_wallet import ADMIN, USER, _callback, _customer_events, _order, _pay, _verify_bank


def _requested(tmp_path, commission: int = 20_000):
    bot = _ready(tmp_path)
    sub = _available(bot, commission, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    payout, code = bot.wallet.request_payout(USER, T)
    assert code == "ok"
    _verify_bank(bot)
    return bot, sub, int(payout["id"])


def _cancel_source(bot, cid: str = "a") -> None:
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET order_status = 'CANCELLED' WHERE conversion_id = ?", (cid,))
    bot.refresh_wallet(T)


# --- B1, B2: không chi khi nguồn đã huỷ, không chuyển hai lần ------------------------------------


def test_b1_nguon_bi_huy_khong_duyet_chi_duoc(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _to(bot, pid, "under_review")
    _cancel_source(bot)
    assert _status(bot, pid) == "needs_review"
    assert _advance(bot, pid, "under_review", note="xem lại") == "ok"  # chưa từng chuyển: mở lại vòng kiểm tra
    assert _advance(bot, pid, "approved_for_payment") == "source_changed"
    assert _status(bot, pid) == "under_review"


def test_b2_da_bat_dau_chuyen_khong_quay_lai_vong_duyet(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _to(bot, pid, "under_review", "approved_for_payment", "processing", "sent_unconfirmed")
    assert _advance(bot, pid, "needs_review", note="khách báo chưa nhận") == "ok"
    assert _advance(bot, pid, "under_review", note="duyệt lại") == "money_may_have_left"
    assert _advance(bot, pid, "rejected", note="x") == "money_may_have_left"
    assert _advance(bot, pid, "sent_unconfirmed", note="đã chuyển, chờ ngân hàng") == "ok"


def test_b2_chua_chuyen_khong_nhay_thang_toi_da_gui(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    assert _advance(bot, pid, "needs_review", note="kiểm tra tên") == "ok"
    assert _advance(bot, pid, "sent_unconfirmed", note="x") == "transition"
    assert _advance(bot, pid, "under_review", note="tên đúng") == "ok"


def test_b8_trigger_giu_may_trang_thai_va_chan_vong_hai(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    with bot.repo.connect() as conn, pytest.raises(sqlite3.IntegrityError, match="transition not allowed"):
        conn.execute("UPDATE cashback_payouts SET status = 'processing' WHERE id = ?", (pid,))
    _to(bot, pid, "under_review", "approved_for_payment", "processing")
    _advance(bot, pid, "needs_review", note="x")
    with bot.repo.connect() as conn, pytest.raises(sqlite3.IntegrityError, match="money may have left"):
        conn.execute("UPDATE cashback_payouts SET status = 'under_review' WHERE id = ?", (pid,))


def test_b8_trigger_va_may_trang_thai_python_trung_nhau():
    allowed = set(re.findall(r"'([a-z_]+>[a-z_]+)'", db.SCHEMA.split("payout_status_machine", 1)[1].split("BEGIN", 1)[0]))
    assert allowed == {f"{a}>{b}" for a, rules in payouts.TRANSITIONS.items() for b in rules}


def test_b8_khoa_theo_du_lieu_khong_theo_bang_ton_tai(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE settlement_batches SET status = 'DISPUTED'")
        with pytest.raises(sqlite3.IntegrityError, match="no matched settlement"):
            conn.execute(
                "INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, account_name, "
                "created_at) VALUES (?, 1, 'requested', 'MB', '1', 'A', 'x')", (USER,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="entry not in a matched settlement"):
            conn.execute(
                "INSERT INTO cashback_entries (conversion_id, telegram_user_id, cashback_vnd, status, created_at, updated_at) "
                "VALUES ('raw', ?, 5000, 'available', 'x', 'x')", (USER,)
            )


# --- B3: quỹ không đếm dòng của chứng từ đã bị thay ---------------------------------------------


def test_b3_quy_bo_dong_cua_chung_tu_cu(tmp_path):
    bot = _ready(tmp_path, fund=10_000)
    with bot.repo.connect() as conn:
        batch = conn.execute("SELECT id FROM settlement_batches").fetchone()[0]
        old = conn.execute("SELECT statement_evidence_id FROM settlement_batches").fetchone()[0]
        new = conn.execute(
            "INSERT INTO settlement_evidence (batch_id, kind, source, document_ref, content_sha256, stored_name, "
            "size_bytes, parser, recorded_by, recorded_at) VALUES (?, 'shopee_payment_report', 'test', 'v2', ?, 'x', "
            "1, 'test', 'test', 'x')", (batch, hashlib.sha256(b"v2").hexdigest())
        ).lastrowid
        conn.execute(
            "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, is_bot, settled_vnd, match_status, created_at) "
            "VALUES (?, ?, 'TEST-FUND', 1, 10000, 'MATCHED', 'x')", (batch, new)
        )
        conn.execute("UPDATE settlement_batches SET statement_evidence_id = ?", (new,))
        assert old != new
        assert payouts.fund_position(conn).allocatable_vnd == 10_000, "không cộng cả bản cũ lẫn bản thay"


# --- B4: thu hồi -----------------------------------------------------------------------------------


def test_b4_shopee_giam_hoa_hong_tru_vao_vi_va_khoa_rut(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.balance(USER).withdrawable_vnd == 14_000
    payout, _code = bot.wallet.request_payout(USER, T)
    _verify_bank(bot)
    assert _pay(bot, int(payout["id"])) == "ok"
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(T)
    bot.refresh_wallet(T)  # chạy lại không trừ thêm
    assert bot.wallet.balance(USER).withdrawable_vnd == -7_000
    assert _rows(bot, "SELECT conversion_id, cashback_vnd, status FROM cashback_entries WHERE conversion_id LIKE 'a:%'") == [
        ("a:clawback:1", -7_000, "available")]
    assert bot.wallet.request_payout(USER, T)[1] == "below_min"
    page = _callback(bot, USER, "u:p:wallet")
    assert "Đang trừ lại: <b>7.000đ</b>" in page.text and "Shopee giảm hoa hồng, trừ lại" in page.text
    _available(bot, 20_000, "b", sub=sub)
    bot.refresh_wallet(T)
    assert bot.wallet.balance(USER).withdrawable_vnd == 7_000, "đơn sau bù khoản bị trừ trước"


def test_b4_huy_sau_khi_da_tru_mot_phan_khong_tru_hai_lan(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(T)
    assert bot.wallet.balance(USER).withdrawable_vnd == 7_000
    _cancel_source(bot)
    assert bot.wallet.balance(USER).withdrawable_vnd == 0


def test_b4_ky_bi_dao_khoan_ve_holding(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    assert bot.wallet.balance(USER).withdrawable_vnd == 14_000
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET settlement_status = 'NOT_VERIFIED' WHERE conversion_id = 'a'")
    bot.refresh_wallet(T)
    balance = bot.wallet.balance(USER)
    assert (balance.withdrawable_vnd, balance.held_vnd) == (0, 14_000)


def test_b4_so_du_am_dua_yeu_cau_dang_mo_sang_can_kiem_tra(tmp_path):
    bot, sub, pid = _requested(tmp_path)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a", approved=True)
    bot.refresh_wallet(T)
    assert _status(bot, pid) == "needs_review"


# --- B5: khách Zalo rút được nhiều lần --------------------------------------------------------------


def test_b5_ma_callback_zalo_theo_tung_tin():
    seen = []

    class Service:
        def handle_update(self, update):
            seen.append(update["callback_query"]["id"])

    channel = ZaloChannel(Service(), None, None)
    channel._press(-3, "u:w:out:ok", -10)
    channel._press(-3, "u:w:out:ok", -11)
    channel._press(-3, "u:w:out:ok", -11)
    assert seen[0] != seen[1] and seen[1] == seen[2]


# --- B7: ghi đã trả không bị chặn bởi backup cũ / hạn mức vừa hạ -------------------------------------


def test_b7_backup_cu_khong_chan_ghi_da_tra(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _to(bot, pid, "under_review", "approved_for_payment", "processing", "sent_unconfirmed")
    with bot.repo.connect() as conn:
        conn.execute("UPDATE bot_state SET value = '0' WHERE key = 'backup_last_ok'")
        payouts.set_limits(conn, payouts.active_limits(conn), admin_id=ADMIN, now=T, min_vnd=1, max_per_request_vnd=1,
                           daily_total_vnd=1, monthly_total_vnd=1)
    assert _advance(bot, pid, "paid_confirmed", evidence="FT26102499999") == "ok"


# --- B9: đổi tài khoản chờ 7 ngày, admin xác minh thì rút ngay -----------------------------------------


def test_b9_doi_tai_khoan_cho_7_ngay_admin_xac_minh_thi_rut_ngay(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T, amount=10_000)[1] == "ok", "khai lần đầu không phải chờ"
    bot.wallet.save_bank(USER, ACCOUNT.__class__("VCB", "9999999999", "NGUYEN VAN A"), T)
    _advance(bot, 1, "rejected", note="khách đổi tài khoản")
    assert bot.wallet.request_payout(USER, T + timedelta(days=6), amount=10_000) == (None, "bank_cooldown")
    member = _callback(bot, ADMIN, f"c:wl:u:{USER}")
    assert "Vừa đổi tài khoản" in member.text and f"c:wl:vm:{USER}" in str(member.inline_keyboard)
    _callback(bot, ADMIN, f"c:wl:vm:{USER}")
    bot.admin_panel.consume_text(ADMIN, "chuyển thử 1.000đ đúng tên", T)
    assert bot.wallet.request_payout(USER, T + timedelta(days=1), amount=10_000)[1] == "ok"


def test_b9_het_7_ngay_rut_duoc(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.save_bank(USER, ACCOUNT.__class__("VCB", "9999999999", "NGUYEN VAN A"), T)
    assert bot.wallet.request_payout(USER, T + timedelta(days=7), amount=10_000)[1] == "ok"


# --- B10, B15: tin khách -----------------------------------------------------------------------------


def test_b10_ly_do_tu_choi_duoc_escape_va_b15_tieu_de(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _callback(bot, ADMIN, f"c:wl:mv:{pid}:1:rj:ok")
    bot.admin_panel.consume_text(ADMIN, "Tên <sai> & thiếu", T)
    last = _customer_events(bot)[-1]
    assert "Tên &lt;sai&gt; &amp; thiếu" in last and "không được duyệt" in last and "/hotro" in last


def test_b15_tin_da_tra_kem_ma_giao_dich(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _to(bot, pid, "under_review", "approved_for_payment", "processing", "sent_unconfirmed")
    _callback(bot, ADMIN, f"c:wl:mv:{pid}:5:pd:ok")
    bot.admin_panel.consume_text(ADMIN, "FT26102455555", T)
    assert "Mã giao dịch: <code>FT26102455555</code>" in _customer_events(bot)[-1]


# --- B12: màn chi tiết không cắt mất Điều kiện / Lịch sử ---------------------------------------------


def test_b12_nhieu_nguon_van_giu_dieu_kien_va_lich_su(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT * FROM cashback_payouts WHERE id = ?", (pid,)).fetchone()
        parts = payouts.allocations(conn, pid) * 200
        history = payouts.events(conn, pid)
    text = payout_text(row, "buyer", "MB Bank", allocations=parts, conditions=[], events=history, bank_state="VERIFIED",
                       shared_users=1, fund=payouts.FundPosition(True, 1, 0, 0, 0, 0, 1, 0, 0))
    assert len(text) <= PAYOUT_TEXT_MAX and "🔐 <b>Điều kiện</b>" in text and "🕘 <b>Lịch sử</b>" in text
    assert "khoản khác" in text


# --- B13: công bố bản điều khoản mới không làm mất điều kiện --------------------------------------------


def test_b13_dong_y_ban_moi_hon_van_dat(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE customer_terms_versions SET status = 'SUPERSEDED' WHERE version = 'TEST-PAYOUT-TERMS'")
        v4 = conn.execute(
            "INSERT INTO customer_terms_versions (version, title, content, content_hash, status, effective_from, "
            "created_by, created_at, approved_by, published_at) VALUES ('V4', 't', '[]', 'h4', 'PUBLISHED', "
            "'2026-11-01T00:00:00Z', 'test', 'x', 'test', 'x')"
        ).lastrowid
        assert not payout_readiness.user_conditions(conn, USER)[0].ok, "bản cũ đã bị thay: phải đồng ý bản mới"
        conn.execute(
            "INSERT INTO customer_terms_acceptances (telegram_user_id, terms_version_id, terms_hash, acceptance_source, "
            "accepted_at, recorded_at) VALUES (?, ?, 'h4', 'test', 'x', 'x')", (USER, v4)
        )
        assert payout_readiness.user_conditions(conn, USER)[0].ok


# --- C: dữ liệu cá nhân ------------------------------------------------------------------------------


def test_c3_so_tai_khoan_khong_nam_lai_sau_khi_gui(tmp_path):
    bot, _sub, pid = _requested(tmp_path)
    _to(bot, pid, "under_review", "approved_for_payment", "processing")
    update = {"update_id": 777, "callback_query": {"id": "q777", "from": {"id": ADMIN}, "data": f"c:wl:rq:{pid}",
                                                   "message": {"chat": {"id": ADMIN, "type": "private"}, "message_id": 5}}}
    sent = []

    class Telegram:
        def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
            sent.append(html)

        def edit_message_text(self, chat_id, message_id, html, reply_markup=None):
            sent.append(html)
            return True

        def answer_callback(self, *args, **kwargs):
            pass

        def send_photo(self, *args, **kwargs):
            pass

    process_updates(bot, Telegram(), bot.repo, [update], MagicMock())
    assert ACCOUNT.account_no in sent[-1], "admin vẫn thấy số đầy đủ để chuyển"
    assert ACCOUNT.account_no not in _rows(bot, "SELECT body_html FROM outbound_messages WHERE telegram_update_id = 777")[0][0]


def test_c5_csv_khong_chay_cong_thuc():
    assert _csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _csv_cell("@x") == "'@x"
    assert _csv_cell(-5) == -5 and _csv_cell("Áo") == "Áo" and _csv_cell(None) == ""


def test_c6_gioi_han_ticket_moi_trong_ngay(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        for n in range(support.MAX_NEW_PER_DAY):
            support.open_ticket(conn, USER, "other", f"tin {n}", T, None)
        with pytest.raises(support.SupportError, match="limit"):
            support.open_ticket(conn, USER, "other", "tin nữa", T, None)
        assert support.open_ticket(conn, USER, "other", "hôm sau", T + timedelta(days=1, minutes=1), None)[1]
