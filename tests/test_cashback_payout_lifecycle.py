"""PLAN-078: sổ ví, tài khoản nhận tiền, vòng đời yêu cầu rút, quỹ có chứng từ, hạn mức, khoá tài chính.

Mọi dữ liệu «đủ điều kiện» ở đây chỉ nằm trong DB test (fixture), không có công tắc bỏ qua trong code.
"""

from __future__ import annotations

import inspect
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from cashback_bot import admin_wallet, payout_readiness, payouts
from cashback_bot.payout_gate import REASON_SETTLEMENT, REASON_TAX
from cashback_bot.vietqr import build_payload, parse_tlv
from cashback_bot.wallet import BankAccount, parse_bank_text
from tests.test_cashback_bot import NOW as QUOTE_NOW
from tests.test_cashback_wallet import (
    ADMIN,
    USER,
    _bot,
    _callback,
    _customer_events,
    _financially_ready,
    _link,
    _order,
    _pay,
    _verify_bank,
)

OTHER = 222
T = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)
ACCOUNT = BankAccount("MB", "0123456789", "NGUYEN VAN A")


def _rows(bot, sql, args=()):
    with bot.repo.connect() as conn:
        return [tuple(row) for row in conn.execute(sql, args).fetchall()]


def _ready(tmp_path, fund: int = 10_000_000, users=(USER,), **overrides):
    overrides.setdefault("allowed_telegram_ids", frozenset({USER, OTHER}))
    bot = _bot(tmp_path, **overrides)
    _financially_ready(bot, amount=fund, users=users)
    bot.wallet.set_enabled(True)
    bot.wallet.set_hold_days(0)
    return bot


def _available(bot, commission: int, cid: str, user: int = USER, sub: str | None = None) -> str:
    """Khoản đủ điều kiện trong DB test: hoàn thành, APPROVED, SETTLED (fixture), snapshot có sẵn."""
    sub = sub or (_link(bot) if user == USER else _link_for(bot, user))
    _order(bot, sub, status="COMPLETED", commission=commission, complete="2026-10-21T10:00:00Z", cid=cid, approved=True)
    return sub


def _link_for(bot, user: int) -> str:
    bot.handle_text(user, "u", "https://shopee.vn/product/9/8", update_id=5000 + user, now=QUOTE_NOW)
    return _rows(bot, "SELECT sub_id FROM link_requests WHERE telegram_user_id = ? ORDER BY id DESC", (user,))[0][0]


def _b3(tmp_path):
    """Ví dụ B3 của PLAN: 50.000đ đang chờ, 30.000đ đủ điều kiện, 10.000đ đang giữ."""
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="PENDING", commission=71_429, cid="pend")
    _available(bot, 42_858, "avail", sub=sub)
    _order(bot, sub, status="COMPLETED", commission=14_286, complete="2026-10-21T10:00:00Z", cid="held")
    with bot.repo.connect() as conn:  # duyệt nhưng chưa nằm trong kỳ đối soát khớp → đang giữ
        conn.execute("UPDATE shopee_conversions SET validation_status = 'APPROVED' WHERE conversion_id = 'held'")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    return bot


def _status(bot, pid=1):
    return bot.wallet.payout(pid)["status"]


def _advance(bot, pid, target, **kw):
    row = bot.wallet.payout(pid)
    return bot.wallet.advance(pid, target, ADMIN, int(row["version"]), T, **kw)[1]


def _to(bot, pid, *targets):
    for target in targets:
        assert _advance(bot, pid, target) == "ok", target


# --- Sổ ví (1–8) ----------------------------------------------------------------------------------


def test_01_08_vi_du_b3_giu_tien_dung_va_khong_dem_trung(tmp_path):
    bot = _b3(tmp_path)
    balance = bot.wallet.balance(USER)
    assert (balance.pending_vnd - balance.held_vnd, balance.held_vnd, balance.withdrawable_vnd) == (50_000, 10_000, 30_000)
    payout, code = bot.wallet.request_payout(USER, T, amount=20_000)
    assert code == "ok"
    after = bot.wallet.balance(USER)
    assert (after.pending_vnd - after.held_vnd, after.held_vnd, after.requested_vnd, after.withdrawable_vnd) == (
        50_000, 10_000, 20_000, 10_000)
    assert _rows(bot, "SELECT conversion_id, amount_vnd FROM payout_allocations") == [("avail", 20_000)]
    assert bot.wallet.request_payout(USER, T, amount=10_000) == (None, "pending_exists")
    _advance(bot, 1, "rejected", note="Khách xin huỷ")
    assert bot.wallet.balance(USER).withdrawable_vnd == 30_000, "từ chối trước khi chuyển: giải phóng có audit"
    assert [r[0] for r in _rows(bot, "SELECT to_status FROM payout_events ORDER BY id")] == ["requested", "rejected"]
    with bot.repo.connect() as conn:
        assert payouts.invariants(conn) == []


def test_02_khoan_chi_vao_vi_khi_du_bang_chung(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=10_000, complete="2026-10-21T10:00:00Z", cid="a")
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET validation_status = 'APPROVED' WHERE conversion_id = 'a'")
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries") == [("holding",)], "APPROVED chưa SETTLED: chưa vào ví"
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET settlement_status = 'SETTLED' WHERE conversion_id = 'a'")
        conn.execute(
            "INSERT INTO settlement_adjustments (conversion_id, old_vnd, new_vnd, delta_vnd, source, source_ref, detected_at) "
            "VALUES ('a', 10000, 8000, -2000, 'conversion_change', 'run1', 'x')"
        )
    bot.refresh_wallet(T)
    assert _rows(bot, "SELECT status FROM cashback_entries") == [("holding",)], "điều chỉnh chưa xử lý: giữ lại"


def test_05_40_da_tra_khong_rut_lai_va_khong_tra_hai_lan(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _verify_bank(bot)
    assert _pay(bot, 1) == "ok"
    assert bot.wallet.balance(USER).paid_vnd == 14_000 and bot.wallet.balance(USER).withdrawable_vnd == 0
    assert bot.wallet.request_payout(USER, T) == (None, "below_min")
    assert _advance(bot, 1, "paid_confirmed", evidence="FT2") == "transition"
    assert _rows(bot, "SELECT COUNT(*) FROM payout_events WHERE to_status = 'paid_confirmed'") == [(1,)]


def test_06_07_khoan_bi_huy_khi_dang_giu_thanh_can_kiem_tra_khong_tru_tien(tmp_path):
    bot = _ready(tmp_path)
    sub = _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _order(bot, sub, status="CANCELLED", commission=20_000, complete="2026-10-21T10:00:00Z", cid="a")
    bot.refresh_wallet(T + timedelta(hours=1))
    assert _status(bot) == "needs_review"
    assert _rows(bot, "SELECT status FROM cashback_entries") == [("cancelled",)]
    with bot.repo.connect() as conn:
        assert any("reserved_but_cancelled" in p for p in payouts.invariants(conn))
        assert payouts.structural_problems(conn) == []
    assert _advance(bot, 1, "rejected", note="Shopee huỷ đơn nguồn") == "ok"


# --- Tài khoản nhận tiền (9–17) ---------------------------------------------------------------


def test_09_11_kiem_tra_dinh_dang_tai_khoan():
    assert parse_bank_text("mb 0123456789 Nguyễn Văn A") == ACCOUNT
    assert parse_bank_text("XYZ 0123456789 A B") == "bank"
    assert parse_bank_text("MB 01234 Nguyen Van A") == "account"
    assert parse_bank_text("MB 0123456789 Nguyen 3 A") == "name"


def test_12_16_doi_tai_khoan_co_lich_su_khong_luu_so_day_du_va_ve_chua_xac_minh(tmp_path):
    bot = _ready(tmp_path)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    _verify_bank(bot)
    assert bot.wallet.bank_status(USER) == "VERIFIED"
    bot.wallet.save_bank(USER, BankAccount("VCB", "9876543210", "NGUYEN VAN A"), T)
    assert bot.wallet.bank_status(USER) == "UNVERIFIED"
    history = _rows(bot, "SELECT bank_code, account_last4, action FROM bank_account_history ORDER BY id")
    assert history == [("MB", "6789", "add"), ("VCB", "3210", "change")]
    dump = repr(_rows(bot, "SELECT * FROM bank_account_history")) + repr(_rows(bot, "SELECT * FROM bank_account_verifications"))
    assert "0123456789" not in dump and "9876543210" not in dump
    bot.wallet.save_bank(USER, BankAccount("VCB", "9876543210", "NGUYEN VAN A"), T)
    assert len(_rows(bot, "SELECT * FROM bank_account_history")) == 2, "lưu lại cùng tài khoản không ghi thêm"
    with bot.repo.connect() as conn:
        with pytest.raises(payouts.PayoutError):
            payouts.verify_bank(conn, USER, "sha", ADMIN, "manual", "ok", T)


def test_tai_khoan_dung_chung_bi_canh_bao(tmp_path):
    bot = _ready(tmp_path, users=(USER, OTHER))
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.save_bank(OTHER, ACCOUNT, T)
    with bot.repo.connect() as conn:
        assert payouts.shared_account_users(conn, payouts.account_sha("MB", "0123456789")) == 2


def test_13_37_doi_tai_khoan_sau_khi_gui_yeu_cau(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    moved = bot.wallet.save_bank(USER, BankAccount("VCB", "9876543210", "NGUYEN VAN A"), T)
    payout = bot.wallet.payout(1)
    assert moved == [1] and payout["status"] == "needs_review"
    assert (payout["bank_code"], payout["account_no"]) == ("MB", "0123456789"), "giữ đích đã chụp"
    assert _advance(bot, 1, "under_review", note="Khách xác nhận lại tài khoản cũ") == "ok"


def test_14_15_qr_dung_noi_dung_va_khong_phai_xac_minh(tmp_path):
    payload = build_payload("970422", "0123456789", 14_000, "Hoan tien 000001")
    top = parse_tlv(payload)
    merchant = parse_tlv(top["38"])
    assert top["54"] == "14000" and "Hoan tien 000001" in parse_tlv(top["62"])["08"]
    assert "970422" in merchant["01"] and "0123456789" in merchant["01"]
    bot = _ready(tmp_path)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.bank_status(USER) == "UNVERIFIED"
    assert _rows(bot, "SELECT COUNT(*) FROM bank_account_verifications") == [(0,)]


def test_17_khong_log_so_tai_khoan(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _verify_bank(bot)
    _pay(bot, 1)
    assert "0123456789" not in caplog.text


# --- Yêu cầu rút (18–30) ------------------------------------------------------------------------


def test_18_19_25_yeu_cau_hop_le_thieu_tien_va_vuot_han_muc(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T, amount=15_000) == (None, "insufficient")
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd, status, "
            "created_by, approved_by, approved_at, created_at) VALUES (1000, 10000, 50000, 100000, 'ACTIVE', 't', 't', 'x', 'x')"
        )
    assert bot.wallet.request_payout(USER, T, amount=12_000) == (None, "over_request_limit")
    # B6: nút Rút (không chọn số) lấy đúng số tối đa được rút, phần còn lại rút lần sau.
    payout, code = bot.wallet.request_payout(USER, T)
    assert code == "ok" and payout["amount_vnd"] == 10_000 and payout["transfer_note"] == "Hoan tien 000001"


def test_han_muc_ban_nhap_khong_co_hieu_luc(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        payouts.create_limit_draft(conn, min_vnd=5, max_per_request_vnd=10, daily_total_vnd=10, monthly_total_vnd=10,
                                   actor="admin:7", now=T)
        assert payouts.active_limits(conn) is None
    assert bot.wallet.settings().locked_reasons, "hạn mức nháp làm mất hạn mức đang hiệu lực → khoá"


def test_47_48_han_muc_ngay_va_thang_theo_tung_khach(tmp_path):
    """ADR-059: tổng ngày / tháng tính riêng từng khách; khách này rút không làm khách khác chạm hạn mức."""
    bot = _ready(tmp_path, users=(USER, OTHER))
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd, status, "
            "created_by, approved_by, approved_at, created_at) VALUES (1000, 14000, 20000, 30000, 'ACTIVE', 't', 't', 'x', 'x')"
        )
    _available(bot, 20_000, "a")
    _available(bot, 20_000, "b", user=OTHER)
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.save_bank(OTHER, BankAccount("VCB", "1111111111", "TRAN B"), T)
    assert bot.wallet.request_payout(USER, T)[1] == "ok"
    assert bot.wallet.request_payout(OTHER, T)[1] == "ok", "khách khác không bị tính chung"
    with bot.repo.connect() as conn:
        assert payouts.check_limits(conn, USER, 7_000, T) == "over_daily_limit"
        assert payouts.check_limits(conn, USER, 6_000, T) is None
        assert payouts.check_limits(conn, USER, 14_000, T + timedelta(days=1)) is None
        conn.execute("UPDATE cashback_payouts SET created_at = ? WHERE telegram_user_id = ?",
                     ("2026-10-01T00:00:00Z", USER))
        assert payouts.check_limits(conn, USER, 14_000, T + timedelta(days=1)) is None
        conn.execute("UPDATE cashback_payouts SET amount_vnd = 20000 WHERE telegram_user_id = ?", (USER,))
        assert payouts.check_limits(conn, USER, 14_000, T + timedelta(days=1)) == "over_monthly_limit"
        assert payouts.check_limits(conn, OTHER, 1_000, T + timedelta(days=1)) is None


def test_20_22_thieu_ky_doi_soat_hoac_quyet_dinh_thue_thi_khoa(tmp_path):
    bot = _ready(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO payout_policy_decisions (topic, status, summary, created_at) VALUES ('tax', 'PENDING_REVIEW', 'chờ kế toán', 'x')"
        )
    assert any("Chính sách thuế" in r for r in bot.wallet.settings().locked_reasons)
    bot2 = _ready(tmp_path / "b")
    with bot2.repo.connect() as conn:
        conn.execute("UPDATE settlement_batches SET status = 'DISPUTED'")
    reasons = bot2.wallet.settings().locked_reasons
    assert any("kỳ Shopee đối soát khớp" in r for r in reasons)
    bot2.wallet.save_bank(USER, ACCOUNT, T)
    assert bot2.wallet.request_payout(USER, T) == (None, "locked")


def test_21_54_55_thieu_approved_gian_lan_tu_choi_khong_vao_vi(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=20_000, complete="2026-10-21T10:00:00Z", cid="a")
    _order(bot, sub, status="COMPLETED", commission=20_000, complete="2026-10-21T10:00:00Z", cid="f", fraud=True, approved=True)
    _order(bot, sub, status="COMPLETED", commission=20_000, complete="2026-10-21T10:00:00Z", cid="r", approved=True)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE shopee_conversions SET validation_status = 'REJECTED' WHERE conversion_id = 'r'")
    bot.refresh_wallet(T)
    assert dict(_rows(bot, "SELECT conversion_id, status FROM cashback_entries")) == {
        "a": "holding", "f": "cancelled", "r": "cancelled"}
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T) == (None, "below_min")


def test_23_57_thieu_xac_minh_tai_khoan_hoac_dieu_khoan_chi_tra(tmp_path):
    bot = _ready(tmp_path, users=())
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T) == (None, "terms")
    with bot.repo.connect() as conn:
        version_id = conn.execute("SELECT id FROM customer_terms_versions WHERE version = 'TEST-PAYOUT-TERMS'").fetchone()[0]
        conn.execute(
            "INSERT INTO customer_terms_acceptances (telegram_user_id, terms_version_id, terms_hash, acceptance_source, "
            "accepted_at, recorded_at) VALUES (?, ?, 'h', 'telegram_button', 'x', 'x')", (USER, version_id)
        )
    assert bot.wallet.request_payout(USER, T)[1] == "ok"
    _to(bot, 1, "under_review")
    assert _advance(bot, 1, "approved_for_payment") == "bank_verified"
    _verify_bank(bot)
    assert _advance(bot, 1, "approved_for_payment") == "ok"


def test_26_45_hai_yeu_cau_dong_thoi_chi_mot_duoc_giu(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 42_858, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    barrier = threading.Barrier(2)
    results = []

    def press(key):
        barrier.wait()
        results.append(bot.wallet.request_payout(USER, T, amount=20_000, idempotency_key=key)[1])

    threads = [threading.Thread(target=press, args=(f"k{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["ok", "pending_exists"]
    assert _rows(bot, "SELECT COUNT(*), SUM(amount_vnd) FROM cashback_payouts") == [(1, 20_000)]
    assert bot.wallet.balance(USER).withdrawable_vnd == 10_000


def test_nhieu_khach_dong_thoi_khong_vuot_quy(tmp_path):
    bot = _ready(tmp_path, fund=20_000, users=(USER, OTHER))
    _available(bot, 20_000, "a")
    _available(bot, 20_000, "b", user=OTHER)
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.save_bank(OTHER, BankAccount("VCB", "1111111111", "TRAN B"), T)
    barrier = threading.Barrier(2)
    results = []

    def press(user):
        barrier.wait()
        results.append(bot.wallet.request_payout(user, T)[1])

    threads = [threading.Thread(target=press, args=(user,)) for user in (USER, OTHER)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["fund", "ok"]
    with bot.repo.connect() as conn:
        assert payouts.fund_position(conn).headroom_vnd == 6_000


def test_27_30_telegram_gui_lai_va_db_chan_hai_yeu_cau_mo(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    first = bot.wallet.request_payout(USER, T, idempotency_key="cb:111:abc")
    again = bot.wallet.request_payout(USER, T, idempotency_key="cb:111:abc")
    assert first[1] == "ok" and again[1] == "duplicate" and again[0]["id"] == first[0]["id"]
    with bot.repo.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, account_name, created_at) "
            "VALUES (?, 1000, 'under_review', 'MB', '1', 'A', 'x')", (USER,)
        )


def test_28_callback_gia_sai_quyen_sai_phien_ban(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:wl:mv:1:1:rv:ok").text
    for data in ("c:wl:mv:1:1:xx:ok", "c:wl:mv:a:1:rv", "c:wl:paid:1:ok", "c:wl:rej:1:ok", "c:wl:mv:1:1:pd:ok:x"):
        assert "không còn hiệu lực" in _callback(bot, ADMIN, data).text
    assert "Nút đã cũ" in _callback(bot, ADMIN, "c:wl:mv:1:9:rv:ok").text
    assert "Không chuyển được" in _callback(bot, ADMIN, "c:wl:mv:1:1:pd:ok").text, "không có requested → paid"
    assert _status(bot) == "requested"


def test_29_restart_giua_quy_trinh_khong_tu_lam_gi(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _verify_bank(bot)
    _to(bot, 1, "under_review", "approved_for_payment", "processing", "sent_unconfirmed")
    before = _rows(bot, "SELECT * FROM payout_events")
    bot = _bot(tmp_path, allowed_telegram_ids=frozenset({USER, OTHER}))
    bot.refresh_wallet(T + timedelta(hours=2))
    assert _status(bot) == "sent_unconfirmed"
    assert _rows(bot, "SELECT * FROM payout_events") == before
    assert _rows(bot, "SELECT COUNT(*) FROM cashback_payouts") == [(1,)]
    assert bot.wallet.request_payout(USER, T) == (None, "pending_exists"), "không tạo yêu cầu thứ hai để chuyển lại"
    assert "Đã gửi, chờ xác nhận ngân hàng" in _callback(bot, ADMIN, "c:menu:wallet").text


# --- Xử lý chuyển khoản (31–40) ---------------------------------------------------------------


def _sent(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _verify_bank(bot)
    _to(bot, 1, "under_review", "approved_for_payment", "processing", "sent_unconfirmed")
    return bot


def test_31_32_59_da_tra_can_chung_tu(tmp_path):
    bot = _sent(tmp_path)
    assert _advance(bot, 1, "paid_confirmed") == "evidence"
    assert _advance(bot, 1, "paid_confirmed", evidence="ok") == "evidence"
    with bot.repo.connect() as conn, pytest.raises(sqlite3.IntegrityError, match="paid needs bank evidence"):
        conn.execute("UPDATE cashback_payouts SET status = 'paid_confirmed' WHERE id = 1")
    version = int(bot.wallet.payout(1)["version"])
    _callback(bot, ADMIN, f"c:wl:mv:1:{version}:pd:ok")
    bot.handle_text(ADMIN, "admin", "FT26102488888", update_id=77, now=T)
    assert _status(bot) == "paid_confirmed"
    assert "Đã chuyển tiền hoàn" in _customer_events(bot)[-1]


def test_33_ngan_hang_tu_choi_can_chung_tu_moi_giai_phong(tmp_path):
    bot = _sent(tmp_path)
    assert _advance(bot, 1, "failed", note="NH từ chối") == "evidence"
    assert _advance(bot, 1, "failed", note="NH từ chối", evidence="GD lỗi mã E05, không trừ tiền") == "ok"
    assert bot.wallet.balance(USER).withdrawable_vnd == 14_000


def test_34_35_ket_qua_chua_ro_khong_tu_chuyen_lai(tmp_path):
    bot = _sent(tmp_path)
    assert _advance(bot, 1, "rejected", note="x") in ("transition", "money_may_have_left")
    assert _advance(bot, 1, "needs_review", note="App ngân hàng treo, chưa có biên nhận") == "ok"
    assert _advance(bot, 1, "rejected", note="huỷ") == "money_may_have_left"
    assert _advance(bot, 1, "processing") == "transition", "không quay lại bước chuyển"
    assert bot.wallet.balance(USER).withdrawable_vnd == 0, "tiền vẫn giữ"
    assert _advance(bot, 1, "sent_unconfirmed", note="Sao kê có lệnh đi") == "ok"
    assert _advance(bot, 1, "paid_confirmed", evidence="FT26102477777") == "ok"


def test_36_sai_tai_khoan_truoc_khi_chuyen(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    _to(bot, 1, "under_review")
    assert _advance(bot, 1, "needs_review", note="Tên app hiện khác tên khách khai") == "ok"
    assert _advance(bot, 1, "rejected", note="Sai tài khoản, mời khách khai lại") == "ok"
    assert bot.wallet.balance(USER).withdrawable_vnd == 14_000


def test_38_39_ngan_hang_hoan_lai_giu_lich_su_da_tra(tmp_path):
    bot = _sent(tmp_path)
    _advance(bot, 1, "paid_confirmed", evidence="FT26102466666")
    assert _advance(bot, 1, "returned", note="NH hoàn") == "evidence"
    assert _advance(bot, 1, "returned", note="NH hoàn do sai tên", evidence="Sao kê ghi có hoàn FT26102466666") == "ok"
    statuses = [r[0] for r in _rows(bot, "SELECT to_status FROM payout_events ORDER BY id")]
    assert statuses[-2:] == ["paid_confirmed", "returned"]
    assert bot.wallet.balance(USER).paid_vnd == 0 and bot.wallet.balance(USER).withdrawable_vnd == 14_000
    with bot.repo.connect() as conn, pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM payout_events")


# --- Quỹ (41–50) --------------------------------------------------------------------------------


def test_41_42_49_quy_du_khong_du_va_pending_khong_la_quy(tmp_path):
    bot = _ready(tmp_path, fund=10_000)
    sub = _available(bot, 20_000, "a")
    _order(bot, sub, status="PENDING", commission=500_000, cid="p")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T) == (None, "fund")
    assert bot.wallet.request_payout(USER, T, amount=10_000)[1] == "ok"


def test_43_44_50_tien_ngoai_bot_chua_phan_bo_va_phi_thue_khong_vao_quy(tmp_path):
    bot = _ready(tmp_path, fund=1)  # kỳ fixture góp 1đ
    with bot.repo.connect() as conn:
        batch = conn.execute(
            "INSERT INTO settlement_batches (period, status, fee_vnd, fee_vat_vnd, fee_includes_vat, tax_withheld_vnd, "
            "reported_commission_vnd, created_by, created_at, updated_at) VALUES ('2026-11', 'MATCHED', 1000, 100, 0, 2000, "
            "1000000, 't', 'x', 'x')"
        ).lastrowid
        evidence = conn.execute("SELECT id FROM settlement_evidence LIMIT 1").fetchone()[0]
        conn.execute("UPDATE settlement_batches SET statement_evidence_id = ? WHERE id = ?", (evidence, batch))
        for ref, is_bot, amount, status in (("bot", 1, 20_000, "MATCHED"), ("ngoai", 0, 800_000, "NOT_BOT"),
                                            ("la", 0, 50_000, "UNKNOWN_ORDER")):
            conn.execute(
                "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, is_bot, settled_vnd, match_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'x')", (batch, evidence, ref, is_bot, amount, status)
            )
        fund = payouts.fund_position(conn)
    assert (fund.bot_vnd, fund.non_bot_vnd, fund.unknown_vnd, fund.costs_vnd) == (20_001, 800_000, 50_000, 3_100)
    assert fund.allocatable_vnd == 1 + 16_900, "chỉ tiền đơn bot, trừ toàn bộ phí/VAT/thuế kỳ"
    with bot.repo.connect() as conn:
        conn.execute("UPDATE settlement_batches SET status = 'DISPUTED'")
        assert payouts.fund_position(conn).verified is False


def test_46_mot_khach_chi_mot_yeu_cau_mo(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 42_858, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    assert bot.wallet.request_payout(USER, T, amount=10_000)[1] == "ok"
    assert bot.wallet.request_payout(USER, T, amount=10_000) == (None, "pending_exists")


# --- An toàn (51–60) ----------------------------------------------------------------------------


def test_51_52_production_van_khoa_va_quyet_dinh_khong_mo_khoa_cu(tmp_path):
    bot = _bot(tmp_path)
    with bot.repo.connect() as conn:
        for topic in payouts.POLICY_TOPICS:
            conn.execute(
                "INSERT INTO payout_policy_decisions (topic, status, summary, reference, decided_by, decided_at, created_at) "
                "VALUES (?, 'APPROVED', 's', 'r', 'd', 'x', 'x')", (topic,)
            )
    reasons = bot.wallet.settings().locked_reasons
    assert reasons[:2] == (REASON_SETTLEMENT, REASON_TAX), "duyệt quyết định không làm mất khoá cũ"
    assert bot.wallet.settings().enabled is False
    names = {r[0] for r in _rows(bot, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "shopee_settlements" not in names and "payout_tax_policies" not in names
    with bot.repo.connect() as conn:
        conditions = {c.code: c.ok for c in payout_readiness.system_conditions(conn)}
    assert all(conditions[f"decision_{t}"] for t in payouts.POLICY_TOPICS) and not conditions["settlement_matched"]


def test_trigger_chan_buoc_chi_tien_khi_con_khoa(tmp_path):
    bot = _ready(tmp_path)
    _available(bot, 20_000, "a")
    bot.refresh_wallet(T)
    bot.wallet.save_bank(USER, ACCOUNT, T)
    bot.wallet.request_payout(USER, T)
    with bot.repo.connect() as conn:
        conn.execute("DROP TABLE payout_tax_policies")
        for status in ("approved_for_payment", "processing", "sent_unconfirmed"):
            with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
                conn.execute("UPDATE cashback_payouts SET status = ? WHERE id = 1", (status,))


def test_60_khong_co_api_chuyen_tien(tmp_path):
    source = inspect.getsource(payouts) + inspect.getsource(admin_wallet)
    for word in ("requests.", "urllib", "httpx", "http://", "https://"):
        assert word not in source


def test_tai_khoan_khai_truoc_plan078_duoc_ghi_lich_su_mot_lan(tmp_path):
    bot = _bot(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute(
            "INSERT INTO bank_accounts (telegram_user_id, bank_code, account_no, account_name, updated_at) "
            "VALUES (?, 'VCB', '0011223344', 'NGUYEN VAN A', '2026-10-23T12:31:43Z')", (USER,)
        )
    bot.repo.migrate()
    bot.repo.migrate()
    rows = _rows(bot, "SELECT bank_code, account_last4, action, created_at FROM bank_account_history")
    assert rows == [("VCB", "3344", "add", "2026-10-23T12:31:43Z")]
    assert "0011223344" not in repr(_rows(bot, "SELECT * FROM bank_account_history"))


def test_hai_dieu_kien_han_muc_co_nhan_khac_nhau(tmp_path):
    bot = _bot(tmp_path)
    with bot.repo.connect() as conn:
        labels = {c.code: c.label for c in payout_readiness.system_conditions(conn)}
    assert labels["decision_payment_limits"] == "Quyết định chính sách hạn mức rút"
    assert labels["limits_active"] == "Bảng số hạn mức đã duyệt, đang dùng"
    assert len(set(labels.values())) == len(labels), "không có hai điều kiện trùng chữ"
