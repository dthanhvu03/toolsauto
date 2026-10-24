"""PLAN-074: trạng thái duyệt hoa hồng, phát hiện thay đổi, Sub ID, màn duyệt, khoá tài chính.

Shopee và Telegram đều giả; mọi DB là SQLite tạm. Cấu trúc response theo 3 response thật đã lưu (24/10/2026).
"""

from __future__ import annotations

import itertools
import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_validation import NO_APPROVAL_NOTE
from cashback_bot.commission_validation import (
    APPROVED,
    FRAUD,
    NEEDS_REVIEW,
    PENDING,
    REJECTED,
    UNKNOWN,
    assess,
)
from cashback_bot.shopee_client import ShopeeApiError
from cashback_bot.shopee_sync import PAGE_SIZE, ShopeeSyncEngine
from tests.test_cashback_shopee_sync import _status
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _financially_ready, _link, _order

NOW = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)
OTHER = 222


def _checkout(
    sub: str = "",
    oid: str = "o1",
    net: int | None = 20_000,
    order_status: str = "PENDING",
    is_fraud: int = 0,
    fraud_reason: str = "",
    fraud_status: int = 2,
    item_status: int = 1,
    conversion_status: int = 1,
    cancel_reason: str = "",
    validation_month: str = "",
    items: bool = True,
) -> dict:
    """Một checkout một đơn, đúng dạng /api/v3/report/list (tiền × 100.000)."""
    top = {
        "checkout_id": f"chk-{oid}",
        "purchase_time": 1792726165,
        "utm_content": f"{sub}----" if sub else "----",
        "conversion_status": conversion_status,
        "checkout_status": "Pending",
        "estimated_validation_month": validation_month,
    }
    if net is not None:
        top["estimated_total_commission"] = net * 100_000
        top["affiliate_net_commission"] = str(net * 100_000)
    order = {"order_id": oid, "order_sn": f"2610{oid}SN", "order_status": order_status, "cancel_reason": cancel_reason}
    if items:
        order["items"] = [{
            "item_name": "Kem nền DOPI",
            "actual_amount": 23_157_000_000,
            "qty": 1,
            "affiliate_item_status": item_status,
            "is_fraud": is_fraud,
            "fraud_status": fraud_status,
            "fraud_reason": fraud_reason,
        }]
    top["orders"] = [order]
    return top


def _sync(bot, *checkouts, notifier=None):
    client = MagicMock()
    client.check_status.return_value = _status(True)
    client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
    client.fetch_conversions.return_value = {"code": 0, "data": {"list": list(checkouts)}}
    return ShopeeSyncEngine(bot.repo, admin_notifier=notifier).sync(client=client)


def _row(bot, oid: str = "o1"):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM shopee_conversions WHERE conversion_id = ?", (oid,)).fetchone()


def _history(bot, oid: str = "o1"):
    return list(reversed(bot.repo.conversion_changes(oid, limit=50)))


@pytest.fixture
def bot(tmp_path):
    return _bot(tmp_path)


# --- G1: trạng thái duyệt ------------------------------------------------------------------------


class TestValidation:
    def test_no_combination_of_shopee_fields_yields_approved(self):
        # Không field nào đã được xác minh là "đã duyệt": mọi tổ hợp đều không ra APPROVED.
        for order_status, item_status, conv, month in itertools.product(
            ("UNPAID", "PAID", "COMPLETED"), (1, 3), (1, 3), ("", "2026-10")
        ):
            top = _checkout(order_status=order_status, item_status=item_status, conversion_status=conv, validation_month=month)
            found = assess(top, top["orders"][0], 20_000)
            assert found.status == PENDING, (order_status, item_status, conv, month)

    def test_without_approval_flag_is_pending(self, bot):
        _sync(bot, _checkout())
        row = _row(bot)
        assert (row["validation_status"], row["validation_reason"]) == (PENDING, "awaiting_shopee_validation")
        assert row["validation_confidence"] == "INFERRED" and row["evidence_ref"].startswith("sync_run:")

    def test_missing_data_is_unknown(self, bot):
        _sync(bot, _checkout(items=False))
        assert _row(bot)["validation_status"] == UNKNOWN
        top = _checkout(net=None)
        assert assess(top, top["orders"][0], None).status == UNKNOWN

    def test_contradictory_status_needs_review(self):
        top = _checkout(fraud_status=3)  # mã gian lận nhưng is_fraud=0, không lý do
        assert assess(top, top["orders"][0], 20_000).status == NEEDS_REVIEW
        top = _checkout(item_status=7)  # mã chưa từng thấy
        assert assess(top, top["orders"][0], 20_000).reason == "unmapped_status"

    def test_fraud_flag(self, bot):
        _sync(bot, _checkout(order_status="COMPLETED", is_fraud=1, fraud_status=3, item_status=3,
                             fraud_reason="Rejected due to fraudulent activity detected", net=0))
        row = _row(bot)
        assert (row["validation_status"], row["fraud_flag"]) == (FRAUD, 1)

    def test_completed_order_is_not_approved(self, bot):
        _sync(bot, _checkout(order_status="COMPLETED", item_status=3, conversion_status=3))
        row = _row(bot)
        assert (row["validation_status"], row["validation_reason"]) == (PENDING, "completed_awaiting_validation")

    def test_paid_order_is_not_settled(self, bot):
        _sync(bot, _checkout(order_status="PAID"))
        assert _row(bot)["settlement_status"] == "NOT_VERIFIED"

    def test_validation_month_does_not_prove_approval(self, bot):
        _sync(bot, _checkout(order_status="COMPLETED", validation_month="2026-10"))
        row = _row(bot)
        assert row["validation_status"] == PENDING and row["settlement_status"] == "NOT_VERIFIED"


# --- G2: thay đổi hoa hồng ----------------------------------------------------------------------


class TestCommissionChanges:
    def test_increase_logged_not_alarming(self, bot):
        _sync(bot, _checkout(net=20_000))
        _sync(bot, _checkout(net=25_000))
        (change,) = _history(bot)
        assert (change["field"], change["old_value"], change["new_value"], change["significant"]) == (
            "net_commission_vnd", "20000", "25000", 0)
        assert _row(bot)["review_status"] == "none"

    def test_decrease_logged_flagged_and_admin_told_once(self, bot):
        notifier = MagicMock()
        _sync(bot, _checkout(net=20_000), notifier=notifier)
        _sync(bot, _checkout(net=12_000), notifier=notifier)
        (change,) = _history(bot)
        assert (change["old_value"], change["new_value"], change["significant"]) == ("20000", "12000", 1)
        row = _row(bot)
        assert (row["first_commission_vnd"], row["net_commission_vnd"], row["review_status"]) == (20_000, 12_000, "needs_review")
        notifier.notify_commission_changes.assert_called_once()

    def test_drop_to_zero(self, bot):
        _sync(bot, _checkout(net=20_000))
        _sync(bot, _checkout(net=0))
        row = _row(bot)
        assert row["net_commission_vnd"] == 0
        # 0 mà không cờ gian lận: không kết luận gian lận, chỉ cần kiểm tra.
        assert (row["validation_status"], row["validation_reason"]) == (NEEDS_REVIEW, "commission_zero_unexplained")

    def test_becomes_fraud(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, net=20_000))
        bot.refresh_wallet(NOW)
        _sync(bot, _checkout(sub=sub, net=0, order_status="COMPLETED", is_fraud=1, fraud_status=3,
                             fraud_reason="Rejected due to fraudulent activity detected"))
        bot.refresh_wallet(NOW)
        fields = {c["field"]: (c["old_value"], c["new_value"]) for c in _history(bot)}
        assert fields["validation_status"] == (PENDING, FRAUD)
        assert fields["fraud_flag"] == ("0", "1")
        assert bot.wallet.entries(USER)[0]["status"] == "cancelled"

    def test_order_cancelled(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub))
        _sync(bot, _checkout(sub=sub, order_status="CANCELLED", cancel_reason="buyer"))
        assert _row(bot)["validation_status"] == REJECTED
        assert any(c["field"] == "order_status" and c["significant"] for c in _history(bot))
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER)[0]["status"] == "cancelled"

    def test_repeated_identical_sync_creates_no_history(self, bot):
        for _ in range(3):
            _sync(bot, _checkout(net=20_000))
        assert _history(bot) == []
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM shopee_conversions").fetchone()[0] == 1

    def test_error_midway_keeps_what_was_read_and_does_not_drop_old(self, bot):
        _sync(bot, _checkout(oid="old", net=9_000))
        page = [_checkout(oid=f"p{i}", net=1_000) for i in range(PAGE_SIZE)]
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.side_effect = [{"code": 0, "data": {"list": page}}, ShopeeApiError("Shopee HTTP 500", status_code=500)]
        result = ShopeeSyncEngine(bot.repo).sync(client=client)
        assert result.ok is False and "đơn hàng" in result.message
        assert bot.repo.get_last_sync_run()["status"] == "partial"
        assert _row(bot, "p0") is not None and _row(bot, "old")["net_commission_vnd"] == 9_000

    def test_missing_fields_never_overwrite_good_data(self, bot):
        _sync(bot, _checkout(net=20_000))
        _sync(bot, _checkout(net=None))  # Shopee trả thiếu hoa hồng
        _sync(bot, _checkout(net=20_000, items=False))  # thiếu items
        row = _row(bot)
        assert (row["net_commission_vnd"], row["validation_status"]) == (20_000, PENDING)
        assert _history(bot) == []

    def test_stale_data_after_newer_is_flagged(self, bot):
        _sync(bot, _checkout(net=0, is_fraud=1, fraud_reason="Rejected due to fraudulent activity detected"))
        _sync(bot, _checkout(net=20_000))  # snapshot cũ "chờ" đến sau kết luận gian lận
        row = _row(bot)
        assert (row["validation_status"], row["validation_reason"]) == (NEEDS_REVIEW, "status_regression")
        assert row["review_status"] == "needs_review"

    def test_many_changes_keep_full_history(self, bot):
        for net in (20_000, 15_000, 10_000, 0):
            _sync(bot, _checkout(net=net))
        commission = [(c["old_value"], c["new_value"]) for c in _history(bot) if c["field"] == "net_commission_vnd"]
        assert commission == [("20000", "15000"), ("15000", "10000"), ("10000", "0")]
        assert _row(bot)["first_commission_vnd"] == 20_000


# --- G3: Sub ID --------------------------------------------------------------------------------


class TestAttribution:
    def test_exact_sub_id_matches_link_owner(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub))
        assert _row(bot)["telegram_user_id"] == USER

    def test_wrong_or_missing_sub_id_unmatched(self, bot):
        _link(bot)
        _sync(bot, _checkout(sub="ZZZZZZZZ", oid="a"), _checkout(oid="b"))
        assert _row(bot, "a")["matched_link_id"] is None and _row(bot, "b")["matched_link_id"] is None
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER) == []

    def test_shared_link_credits_link_creator(self, bot):
        # Người mua là ai không quan trọng: tiền về người tạo link (chủ Sub ID).
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, oid="bought-by-friend"))
        assert _row(bot, "bought-by-friend")["telegram_user_id"] == USER

    def test_never_reassigned_to_another_user(self, tmp_path):
        bot = _bot(tmp_path, customer_access_enabled=True)
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub))
        bot.handle_text(OTHER, "khac", "https://shopee.vn/product/9/8", update_id=50, now=datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc))
        with bot.repo.connect() as conn:
            other_sub = conn.execute("SELECT sub_id FROM link_requests WHERE telegram_user_id = ?", (OTHER,)).fetchone()[0]
        _sync(bot, _checkout(sub=other_sub))
        row = _row(bot)
        assert row["telegram_user_id"] == USER and row["review_status"] == "needs_review"
        assert [c["field"] for c in _history(bot)] == ["attribution"]

    def test_one_conversion_one_cashback_entry(self, bot):
        sub = _link(bot)
        for net in (20_000, 18_000, 18_000):
            _sync(bot, _checkout(sub=sub, net=net))
            bot.refresh_wallet(NOW)
        with bot.repo.connect() as conn:
            rows = conn.execute("SELECT commission_vnd FROM cashback_entries").fetchall()
        assert [r[0] for r in rows] == [18_000]


# --- G4: quyền và khoá tài chính -----------------------------------------------------------------


class TestSecurityAndLock:
    def test_non_admin_refused(self, bot):
        assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:cv:home").text
        assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:cv:ack:o1").text

    def test_forged_callbacks_do_not_escalate(self, bot):
        _sync(bot, _checkout(oid="nonbot"))
        assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:cv:o:x'; DROP TABLE x;--").text
        assert "Không tìm thấy đơn qua bot" in _callback(bot, ADMIN, "c:cv:o:nonbot").text
        assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:cv:l:approved_all").text

    def test_approved_but_unsettled_cannot_withdraw(self, bot):
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", complete="2026-10-01T00:00:00Z", approved=True)
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER)[0]["status"] == "holding"
        assert bot.wallet.request_payout(USER, NOW) == (None, "locked")

    def test_fraud_never_available_even_if_marked_approved(self, bot):
        _financially_ready(bot)
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", complete="2026-10-01T00:00:00Z", fraud=True, approved=True)
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER)[0]["status"] == "cancelled"

    def test_migration_keeps_financial_lock(self, bot):
        bot.repo.migrate()
        bot.repo.migrate()
        with bot.repo.connect() as conn:
            triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
            evidence = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('shopee_settlements', 'payout_tax_policies')"
            ).fetchone()[0]
        # 4 trigger gốc còn nguyên; PLAN-078 thêm financial_lock_payout_progress (chỉ chặt hơn).
        assert {t for t in triggers if t.startswith("financial_lock_")} == {
            "financial_lock_entry_insert", "financial_lock_entry_update", "financial_lock_payout_insert",
            "financial_lock_payout_paid", "financial_lock_payout_progress"}
        assert evidence == 0 and bot.wallet.settings().locked_reasons

    def test_no_payout_created_and_triggers_still_block(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, order_status="COMPLETED"))
        bot.refresh_wallet(NOW)
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0] == 0
            with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
                conn.execute("UPDATE cashback_entries SET status = 'available'")


# --- Màn duyệt hoa hồng, backfill, cảnh báo ------------------------------------------------------


class TestValidationScreen:
    def test_home_shows_real_counts_and_no_approval_note(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub))
        home = _callback(bot, ADMIN, "c:cv:home")
        assert "Đơn qua bot: <b>1</b>" in home.text and NO_APPROVAL_NOTE in home.text
        assert "Chờ xác minh       1" in home.text and "Shopee đã duyệt    0" in home.text
        assert NO_APPROVAL_NOTE in _callback(bot, ADMIN, "c:cv:l:approved").text
        bot.repo.update_shopee_cookie_status(status="connected")
        shopee = _callback(bot, ADMIN, "c:menu:shopee")
        assert ("🧾 Duyệt hoa hồng", "c:cv:home") in [b for row in shopee.inline_keyboard for b in row]

    def test_detail_history_and_acknowledge_with_audit(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, net=20_000))
        _sync(bot, _checkout(sub=sub, net=12_000))
        detail = _callback(bot, ADMIN, "c:cv:o:o1")
        assert "Hoa hồng ban đầu: 20.000đ · hiện tại: <b>12.000đ</b> · chênh: -8.000đ" in detail.text
        assert "hoa hồng: 20.000đ → <b>12.000đ</b>" in detail.text and "Tiền Shopee đã trả: <b>chưa xác minh</b>" in detail.text
        assert ("✔️ Đã kiểm tra cảnh báo", "c:cv:ack:o1") in [b for row in detail.inline_keyboard for b in row]
        acked = _callback(bot, ADMIN, "c:cv:ack:o1")
        assert "Đã ghi nhận" in acked.text and _row(bot)["review_status"] == "reviewed"
        assert _row(bot)["net_commission_vnd"] == 12_000  # đánh dấu không đổi tiền
        assert "đã kiểm tra cảnh báo" in _callback(bot, ADMIN, "c:menu:hist").text
        assert "Không có cảnh báo" in _callback(bot, ADMIN, "c:cv:ack:o1").text

    def test_lists_and_history_screen(self, bot):
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, net=20_000))
        _sync(bot, _checkout(sub=sub, net=0, is_fraud=1, fraud_reason="Rejected due to fraudulent activity detected"))
        alert = _callback(bot, ADMIN, "c:cv:l:alert")
        assert any("c:cv:o:o1" == data for row in alert.inline_keyboard for _l, data in row)
        assert "🚨 Gian lận" in _callback(bot, ADMIN, "c:cv:h").text

    def test_alert_message_one_per_sync(self, tmp_path):
        bot = _bot(tmp_path)
        notifier = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
        sub = _link(bot)
        _sync(bot, _checkout(sub=sub, net=20_000), notifier=notifier)
        _sync(bot, _checkout(sub=sub, net=12_000), notifier=notifier)
        _sync(bot, _checkout(sub=sub, net=12_000), notifier=notifier)  # không đổi: không báo thêm
        with bot.repo.connect() as conn:
            rows = conn.execute("SELECT message_html FROM admin_notifications WHERE event_type = 'COMMISSION_CHANGED'").fetchall()
        assert len(rows) == 1 and "hoa hồng: 20.000đ → <b>12.000đ</b>" in rows[0][0]

    def test_backfill_old_rows_never_approved(self, bot):
        sub = _link(bot)
        _order(bot, sub)
        _order(bot, sub, cid="f1", fraud=True, commission=0)
        with bot.repo.connect() as conn:  # giả lập dòng có từ trước PLAN-074
            conn.execute("UPDATE shopee_conversions SET validation_status = 'UNKNOWN', validation_source = NULL, first_commission_vnd = NULL")
        bot.repo.migrate()
        assert (_row(bot)["validation_status"], _row(bot)["first_commission_vnd"]) == (PENDING, 10_000)
        assert _row(bot, "f1")["validation_status"] == FRAUD
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM shopee_conversion_changes").fetchone()[0] == 0
            assert conn.execute(f"SELECT COUNT(*) FROM shopee_conversions WHERE validation_status = '{APPROVED}'").fetchone()[0] == 0
