"""Nền hạng V1 trong worktree. Không mở SQLite production và không gọi mạng."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from cashback_bot.pricing import (
    CalculationError,
    net_of_charges,
    quote_displayed_vnd,
    share_cashback,
)
from cashback_bot.ranks import (
    MEMBERSHIP_CUTOVER,
    THRESHOLD_SETS,
    IssuedLinkSnapshot,
    MembershipPolicy,
    ProgressBook,
    ProgressEvent,
    RankInputError,
    apply_snapshot_columns,
    benefit_term_status,
    cashback_owner,
    consider_promotion,
    freeze_stored_link,
    replay_share_bps,
    share_for_new_link,
    tier_share_bps,
    v1_policy,
)
from cashback_bot.service import CashbackService
from tests.test_cashback_bot import NOW, FakeClient, payload, repo, service

ROOT = Path(__file__).resolve().parents[1]


def test_quote_v11_giu_3157_va_khong_phai_60():
    assert quote_displayed_vnd(4_510, 70) == 3_157
    assert quote_displayed_vnd(4_510, 70) != quote_displayed_vnd(4_510, 60)
    assert share_for_new_link(v1_policy(), "BRONZE") is None
    assert MEMBERSHIP_CUTOVER is False


def test_ty_le_hang_va_tran_70():
    assert tier_share_bps("BRONZE") == 6_000
    assert tier_share_bps("SILVER") == 6_500
    assert tier_share_bps("GOLD") == 7_000
    assert max(tier_share_bps(code) for code in ("BRONZE", "SILVER", "GOLD")) == 7_000
    with pytest.raises(RankInputError):
        MembershipPolicy("rank-v1", 1, None, "draft", gold_bps=7_500)
    with pytest.raises(RankInputError):
        MembershipPolicy("rank-v1", 1, None, "active")
    text = (ROOT / "cashback_bot" / "ranks.py").read_text(encoding="utf-8")
    assert "// 10_000" not in text
    assert "share_cashback" not in text


def test_pricing_nhan_snapshot_khong_nhan_hang_hien_tai():
    stored = freeze_stored_link(
        link_id=1,
        sub_id="AbC12345",
        owner_id=111,
        rate_percent=70,
        estimated_commission_vnd=4_510,
        displayed_cashback_vnd=3_157,
        created_at="2026-10-22T14:20:27Z",
    )
    assert stored.displayed_cashback_vnd == 3_157
    assert stored.share_bps == 7_000
    assert replay_share_bps(stored, tier_share_bps("BRONZE")) == 7_000
    net, reasons = net_of_charges(4_510, 44, 0, 0, fee_includes_vat=True, vat_on_fee_vnd=3)
    assert reasons == ()
    assert net == 4_466
    cashback, remain = share_cashback(net, replay_share_bps(stored, 6_000))
    assert cashback == 3_126
    assert remain == 1_340
    with pytest.raises(CalculationError):
        share_cashback(net, 7_500)


def test_thieu_snapshot_khong_suy_dien():
    incomplete = freeze_stored_link(
        link_id=2,
        sub_id=None,
        owner_id=111,
        rate_percent=70,
        estimated_commission_vnd=4_510,
        displayed_cashback_vnd=None,
        created_at=None,
    )
    assert incomplete.review_status == "needs_owner_review"
    assert incomplete.share_bps is None
    assert replay_share_bps(incomplete, 6_000) is None
    assert benefit_term_status(incomplete, date(2027, 1, 1)) == "term_not_approved"


def test_nhieu_conversion_lam_tron_tung_don_va_khong_doi_khi_len_hang():
    stored = freeze_stored_link(
        link_id=3,
        sub_id="AbC12345",
        owner_id=111,
        rate_percent=60,
        estimated_commission_vnd=2_000,
        displayed_cashback_vnd=1_200,
        created_at="2026-11-02T00:00:00Z",
    )
    seen: set[str] = set()
    total = 0
    for key, net in (("a", 1_999), ("b", 1), ("a", 1_999)):
        if key in seen:
            continue
        seen.add(key)
        part, _ = share_cashback(net, replay_share_bps(stored, tier_share_bps("GOLD")))
        total += part
    assert total == 1_199
    assert total < share_cashback(2_000, 6_000)[0]


def test_policy_retired_van_giu_snapshot():
    retired = MembershipPolicy(
        "rank-v1",
        1,
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        "retired",
    )
    assert retired.status == "retired"
    stored = freeze_stored_link(
        link_id=4,
        sub_id="AbC12345",
        owner_id=111,
        rate_percent=65,
        estimated_commission_vnd=4_510,
        displayed_cashback_vnd=2_931,
        created_at="2026-11-02T00:00:00Z",
    )
    assert replay_share_bps(stored, None) == 6_500
    assert share_for_new_link(retired, "GOLD") is None


def test_khong_len_hang_bang_click_spam_hay_trung():
    book = ProgressBook()
    owner = 111
    assert book.apply(ProgressEvent("c1", "click", "AbC12345", owner)) == "ignored"
    assert book.apply(ProgressEvent("l1", "link", "AbC12345", owner)) == "ignored"
    assert book.apply(ProgressEvent("x1", "cancelled", "AbC12345", owner)) == "ignored"
    paid = ProgressEvent("o1", "confirmed", "AbC12345", owner, 4_466, True)
    assert book.apply(paid) == "counted"
    assert book.apply(paid) == "duplicate"
    assert book.confirmed_orders == 1
    assert book.ignored_clicks == 1
    for thresholds in THRESHOLD_SETS:
        assert consider_promotion(book, v1_policy(), thresholds) is None
        assert thresholds["approved"] is False


def test_thu_hoi_khong_am_va_chu_sub_id():
    book = ProgressBook()
    book.apply(ProgressEvent("o1", "confirmed", "AbC12345", 111, 4_466, True))
    assert book.apply(ProgressEvent("r1", "reversed", "AbC12345", 111, 9_000, origin_key="o1")) == "needs_review"
    assert book.paid_commission_vnd == 4_466
    assert book.apply(ProgressEvent("r2", "reversed", "AbC12345", 111, 1_000, origin_key="o1")) == "reversed"
    assert book.paid_commission_vnd == 3_466
    assert cashback_owner(111, "AbC12345", "AbC12345", 222) == 111
    assert cashback_owner(111, "AbC12345", "abc12345", 222) is None


def test_phi_vat_va_thue_khong_tru_hai_lan_thieu_du_lieu_khong_payable():
    once, _ = net_of_charges(4_510, 44, 200, 200, fee_includes_vat=True, vat_on_fee_vnd=3, reserve_same_as_withheld=True)
    assert once == 4_266
    missing, reasons = net_of_charges(4_510, None, None, None)
    assert missing is None
    assert "missing_fee" in reasons
    from cashback_bot.pricing import explain_final
    from cashback_bot.calculator import FinalInput

    explained = explain_final(
        FinalInput(
            verified_commission=4_466,
            fee_already_in_commission=True,
            tax_already_in_commission=True,
            actual_service_fee=44,
            actual_tax_withheld=0,
            payment_evidence=False,
        ),
        7_000,
    )
    assert explained.payable_vnd is None
    assert "no_payment_evidence" in explained.missing


def test_khong_chi_vuot_quy():
    cashback, remain = share_cashback(4_466, 7_000)
    assert cashback == 3_126
    assert remain == 1_340
    assert cashback <= 4_466
    zero, remain_zero = share_cashback(0, 6_000)
    assert zero == 0 and remain_zero == 0
    tiny, remain_tiny = share_cashback(1, 6_000)
    assert tiny == 0 and remain_tiny == 1


def test_migration_chay_lai_khong_sua_so_cu(tmp_path):
    path = tmp_path / "trial.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE link_requests (
            id INTEGER PRIMARY KEY,
            estimated_cashback INTEGER,
            cashback_rate_percent INTEGER
        )
        """
    )
    conn.execute("INSERT INTO link_requests (estimated_cashback, cashback_rate_percent) VALUES (3157, 70)")
    first = apply_snapshot_columns(conn)
    second = apply_snapshot_columns(conn)
    row = conn.execute("SELECT estimated_cashback, cashback_rate_percent, share_bps FROM link_requests").fetchone()
    conn.close()
    assert first == ["membership_policy_id", "membership_rank", "share_bps", "benefit_review"]
    assert second == []
    assert row == (3_157, 70, None)
    assert "UPDATE" not in (ROOT / "cashback_bot" / "ranks.py").read_text(encoding="utf-8").split("def apply_snapshot_columns")[1]
    assert "apply_snapshot_columns" not in (ROOT / "cashback_bot" / "db.py").read_text(encoding="utf-8")


def test_v12_bat_nhung_thieu_cot_van_70(tmp_path):
    turned = service(tmp_path, FakeClient(payload(commission=4_510)), estimate_policy="v1.2")
    reply = turned.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    assert "3.157đ" in reply.text
    store = repo(tmp_path)
    apply_snapshot_columns(sqlite3.connect(store.path))
    reply = CashbackService(turned.settings, store, FakeClient(payload(commission=4_510))).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=2, now=NOW
    )
    assert "3.157đ" in reply.text


def test_lenh_thong_tin_khong_tao_sub_id(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    for update_id, text in ((10, "/start"), (11, "/cachtinh"), (12, "/help"), (13, "/huongdan")):
        reply = bot.handle_text(111, "buyer", text, update_id=update_id, now=NOW)
        assert reply.button_url is None
    assert client.calls == 0
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 0


def test_chia_se_link_tinh_cho_chu_va_khong_tu_len_hang():
    book = ProgressBook()
    for index in range(10):
        book.apply(ProgressEvent(f"o{index}", "confirmed", "AbC12345", 111, 4_466, True))
    assert book.confirmed_orders == 10
    assert book.paid_commission_vnd == 44_660
    assert cashback_owner(111, "AbC12345", "AbC12345", 999) == 111
    assert consider_promotion(book, v1_policy(), THRESHOLD_SETS[0]) is None
    user_total = 0
    for _ in range(10):
        part, _ = share_cashback(4_466, tier_share_bps("BRONZE"))
        user_total += part
    assert user_total == 26_790


def test_san_loi_nhuan_chua_duyet_khong_doi_ty_le():
    _, remain_60 = share_cashback(4_466, 6_000)
    _, remain_65 = share_cashback(4_466, 6_500)
    _, remain_70 = share_cashback(4_466, 7_000)
    assert (remain_60, remain_65, remain_70) == (1_787, 1_564, 1_340)
    assert share_for_new_link(v1_policy(), "GOLD") is None
    assert isinstance(IssuedLinkSnapshot(None, None, None, None, None, None, None, None, None, None, None, None, None).benefit_valid_until, type(None))
