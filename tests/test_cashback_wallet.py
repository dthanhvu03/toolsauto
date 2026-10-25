"""PLAN-066: đối soát đầy đủ, đồng bộ chạy nền, CSV, sổ hoàn tiền, ví khách, rút tiền."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import cashback_bot.poller as poller
from cashback_bot import payouts
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_stats import collect
from cashback_bot.admin_ui import stats_detail_text, stats_text
from cashback_bot.messages import entry_notice
from cashback_bot.money import format_vnd
from cashback_bot.config import AutoSyncConfig
from cashback_bot.poller import _check_wallet_refresh, drain_sync_results, process_updates
from cashback_bot.shopee_client import ShopeeStatusResult
from cashback_bot.shopee_sync import SYNC_REQUEST_KEY, BotOrder, ShopeeSyncEngine, SyncResult
from cashback_bot.sync_scheduler import SyncCoordinator
from cashback_bot.wallet import BankAccount, parse_bank_text
from tests.test_cashback_bot import NOW, FakeClient, payload, service

USER = 111
ADMIN = 7
PURCHASE = "2026-10-21T09:00:00Z"


def _bot(tmp_path, **overrides):
    return service(tmp_path, FakeClient(payload()), admin_user_ids=frozenset({ADMIN}), **overrides)


def _link(bot) -> str:
    bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    with bot.repo.connect() as conn:
        return conn.execute("SELECT sub_id FROM link_requests WHERE link_status = 'created'").fetchone()[0]


DRAFT_EVIDENCE = Path(__file__).resolve().parents[1] / "cashback_bot" / "migrations" / "007_settlement_evidence.DRAFT.sql"


def _financially_ready(bot, period: str = "2026-10", amount: int = 10_000_000, users=(USER,)) -> None:
    """CHỈ DB TEST: dựng bằng chứng kỳ Shopee đã trả + thuế người nhận đã duyệt để thử luồng rút tiền.

    PLAN-078: thêm quyết định chính sách đã duyệt, hạn mức ACTIVE, một kỳ đối soát MATCHED có quỹ `amount`,
    backup mới, điều khoản chi trả đã công bố và `users` đã đồng ý. Không có công tắc bỏ qua trong code.
    """
    with bot.repo.connect() as conn:
        conn.executescript(DRAFT_EVIDENCE.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO shopee_settlements (period, amount_vnd, evidence_ref, recorded_by, recorded_at) "
            "VALUES (?, ?, ?, 1, '2026-11-15T00:00:00Z')",
            (period, amount, f"TEST-{period}-{amount}"),
        )
        conn.execute(
            "INSERT INTO payout_tax_policies (policy_ref, approved_by, approved_at) "
            "VALUES ('TEST-ADR', 1, '2026-11-15T00:00:00Z')"
        )
        _payout_policies_ready(conn, period, amount, users)


def _payout_policies_ready(conn, period: str = "2026-10", fund: int = 10_000_000, users=(USER,)) -> None:
    """CHỈ DB TEST (PLAN-078): mọi điều kiện hệ thống mới của cổng chi trả."""
    for topic in payouts.POLICY_TOPICS:
        conn.execute(
            "INSERT INTO payout_policy_decisions (topic, status, summary, reference, decided_by, decided_at, created_at) "
            "VALUES (?, 'APPROVED', 'test', ?, 'test', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')",
            (topic, "TEST-PAYOUT-TERMS" if topic == "payout_terms" else f"TEST-{topic}"),
        )
    conn.execute(
        "INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd, status, "
        "created_by, approved_by, approved_at, created_at) "
        "VALUES (1, 100000000, 100000000, 1000000000, 'ACTIVE', 'test', 'test', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')"
    )
    batch = conn.execute(
        "INSERT INTO settlement_batches (period, status, fee_vnd, fee_vat_vnd, fee_includes_vat, tax_withheld_vnd, "
        "created_by, created_at, updated_at) VALUES (?, 'MATCHED', 0, 0, 1, 0, 'test', 'x', 'x')",
        (period,),
    ).lastrowid
    evidence = conn.execute(
        "INSERT INTO settlement_evidence (batch_id, kind, source, document_ref, content_sha256, stored_name, size_bytes, "
        "parser, recorded_by, recorded_at) VALUES (?, 'shopee_payment_report', 'test', ?, ?, 'x', 1, 'test', 'test', 'x')",
        (batch, f"TEST-{batch}", hashlib.sha256(f"test-{batch}".encode()).hexdigest()),
    ).lastrowid
    conn.execute(
        "INSERT INTO settlement_items (batch_id, evidence_id, order_ref, is_bot, settled_vnd, match_status, created_at) "
        "VALUES (?, ?, 'TEST-FUND', 1, ?, 'MATCHED', 'x')",
        (batch, evidence, fund),
    )
    conn.execute(
        "INSERT INTO bot_state (key, value) VALUES ('backup_last_ok', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(time.time()),),
    )
    terms_id = conn.execute(
        "INSERT INTO customer_terms_versions (version, title, content, content_hash, status, effective_from, created_by, "
        "created_at, approved_by, published_at) VALUES ('TEST-PAYOUT-TERMS', 't', '[]', 'h', 'PUBLISHED', "
        "'2026-01-01T00:00:00Z', 'test', 'x', 'test', 'x')"
    ).lastrowid
    for user in users:
        conn.execute(
            "INSERT INTO customer_terms_acceptances (telegram_user_id, terms_version_id, terms_hash, acceptance_source, "
            "accepted_at, recorded_at) VALUES (?, ?, 'h', 'test', 'x', 'x')",
            (user, terms_id),
        )


def _verify_bank(bot, user: int = USER) -> None:
    """CHỈ DB TEST: admin xác minh tài khoản hiện tại của khách bằng bằng chứng thủ công."""
    account = bot.wallet.bank(user)
    with bot.repo.connect() as conn:
        payouts.verify_bank(conn, user, payouts.account_sha(account.bank_code, account.account_no), ADMIN, "manual",
                            "chuyển thử 1.000đ khớp tên", NOW)


def _pay(bot, payout_id: int, evidence: str = "FT26102412345", admin: int = ADMIN):
    """CHỈ DB TEST: đi đủ các bước tới đã trả. Trả mã của bước cuối."""
    code = "ok"
    for target, note, proof in (
        (payouts.UNDER_REVIEW, None, None),
        (payouts.APPROVED, None, None),
        (payouts.PROCESSING, None, None),
        (payouts.SENT, None, None),
        (payouts.PAID, None, evidence),
    ):
        row = bot.wallet.payout(payout_id)
        _row, code = bot.wallet.advance(payout_id, target, admin, int(row["version"]), NOW, note=note, evidence=proof)
        if code != "ok":
            return code
    return code


def _order(
    bot,
    sub_id: str,
    status: str = "PENDING",
    commission: int = 10_000,
    complete: str | None = None,
    cid="o1",
    validation: str | None = "2026-10",
    fraud: bool = False,
    approved: bool = False,
):
    item = {"is_fraud": 1 if fraud else 0, "fraud_reason": "Rejected due to fraudulent activity" if fraud else ""}
    bot.repo.record_shopee_conversion(
        conversion_id=cid,
        sub_id=sub_id,
        order_sn=f"SN-{cid}",
        order_status=status,
        conversion_status="",
        purchase_time=PURCHASE,
        gross_commission_vnd=commission,
        net_commission_vnd=commission,
        raw_json=json.dumps({"top": {}, "order": {"items": [item]}}),
        details={
            "item_name": "Áo Polo Nam",
            "gmv_vnd": 250_000,
            "item_qty": 1,
            "complete_time": complete,
            "validation_month": validation,
        },
    )
    if approved:
        # CHỈ DB TEST: chưa có nguồn Shopee nào gán APPROVED (PLAN-074); dựng để thử cơ chế rút tiền.
        # PLAN-078: khoản vào ví còn cần đơn nằm trong kỳ đối soát khớp (SETTLED).
        with bot.repo.connect() as conn:
            conn.execute(
                "UPDATE shopee_conversions SET validation_status = 'APPROVED', settlement_status = 'SETTLED' "
                "WHERE conversion_id = ?",
                (cid,),
            )


def _customer_events(bot) -> list[str]:
    with bot.repo.connect() as conn:
        rows = conn.execute(
            # Dòng 'suppressed' (PLAN-079: cờ tắt, đơn lịch sử…) không bao giờ được gửi.
            "SELECT message_html FROM admin_notifications WHERE chat_id = ? AND status != 'suppressed' ORDER BY id",
            (USER,)
        ).fetchall()
    return [row[0] for row in rows]


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


_CALLBACK_IDS = iter(range(1, 1_000_000))


def _callback(bot, user_id: int, data: str, query_id: str | None = None) -> object:
    """Mỗi lần bấm một mã callback mới như Telegram thật; truyền query_id để thử Telegram gửi lại cùng lần bấm."""
    update = {
        "update_id": 99,
        "callback_query": {
            "id": query_id or f"q{next(_CALLBACK_IDS)}", "from": {"id": user_id}, "data": data,
            "message": {"message_id": 5, "chat": {"type": "private"}},
        },
    }
    return bot.handle_update(update)[1]


# --- Bước 1: số liệu, đồng bộ nền, CSV ----------------------------------------


class TestReconciliation:
    def test_sync_stores_gmv_qty_fee_and_stats_show_them(self, tmp_path):
        bot = _bot(tmp_path)
        client = MagicMock()
        client.check_status.return_value = ShopeeStatusResult(ok=True, status_code=200, username="ID 1")
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": [{"click_id": "c1", "click_time": 1792742400}]}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [{
            "checkout_id": "chk", "purchase_time": 1792742400, "utm_content": "----",
            "gross_commission": 2_000_000_000, "affiliate_net_commission": "1800000000",
            "mcn_management_fee_commission": "200000000", "estimated_validation_month": "2026-11",
            "orders": [{"order_id": "o1", "order_sn": "SN1", "order_status": "COMPLETED", "complete_time": 1792828800,
                        "items": [{"item_name": "Áo", "qty": 2, "actual_amount": 39_900_000_000}]}],
        }]}}
        ShopeeSyncEngine(bot.repo).sync(client=client)
        with bot.repo.connect() as conn:
            row = conn.execute("SELECT * FROM shopee_conversions").fetchone()
            assert (row["gmv_vnd"], row["item_qty"], row["mcn_fee_vnd"]) == (399_000, 2, 2_000)
            assert row["complete_time"] == "2026-10-24T08:00:00Z"
            assert row["validation_month"] == "2026-11"
            stats = collect(conn, "7d", datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
        text = stats_text(stats, period_label="7 ngày", since=None)
        assert "Doanh số 399.000" in text
        assert "7 ngày gần nhất" in text
        detail = stats_detail_text(stats, period_label="7 ngày", since=None)
        assert "Doanh số <b>399.000đ</b>" in detail
        assert "HH gốc 20.000đ − phí MCN 2.000đ" in detail

    def test_cancelled_orders_counted_separately(self, tmp_path):
        bot = _bot(tmp_path)
        _order(bot, "x", status="CANCELLED", commission=5_000)
        with bot.repo.connect() as conn:
            shopee = collect(conn, "all", NOW).shopee
        assert shopee.real_commission_vnd == 0
        assert shopee.lost_commission_vnd == 5_000
        assert shopee.cancelled_gmv_vnd == 250_000

    def test_sync_button_answers_at_once_and_poller_runs_it(self, tmp_path, monkeypatch):
        bot = _bot(tmp_path)
        bot.repo.update_shopee_cookie_status(status="connected")
        reply = _callback(bot, ADMIN, "c:shopee:sync")
        assert "Đã bắt đầu đồng bộ" in reply.text
        assert bot.repo.get_state(SYNC_REQUEST_KEY) == "1"
        # PLAN-080: luồng nền chạy lượt thủ công có khoá; luồng chính cập nhật sổ, báo kết quả, gửi ngay.
        notifier = MagicMock()
        engine = MagicMock()
        engine.return_value.sync.return_value = SyncResult(ok=True, message="Đồng bộ xong: 1 click")
        coordinator = SyncCoordinator(bot.repo, notifier, engine_factory=engine)
        assert coordinator.next_job() == "manual"
        coordinator.run("manual")
        engine.return_value.sync.side_effect = RuntimeError("boom")
        bot.repo.set_state(SYNC_REQUEST_KEY, "1")
        coordinator.run(coordinator.next_job())
        bot.refresh_wallet = MagicMock()
        drain_sync_results(coordinator, bot, notifier)
        assert engine.call_args.kwargs["admin_notifier"] is notifier
        assert engine.return_value.sync.call_args.kwargs["trigger"] == "manual"
        assert notifier.notify_shopee_sync_result.call_args_list[0].args == (True, "Đồng bộ xong: 1 click", ())
        assert notifier.flush_pending.called  # tin kết quả gửi ngay, không đợi long-poll
        assert notifier.notify_shopee_sync_result.call_args_list[1].args[0] is False
        assert bot.refresh_wallet.call_count == 1, "một lần cho cả hai lượt đã xong"
        assert bot.repo.get_state(SYNC_REQUEST_KEY) == "0"

    def test_csv_export_sent_as_document(self, tmp_path):
        bot = _bot(tmp_path)
        bot.repo.update_shopee_cookie_status(status="connected")
        _order(bot, "x")
        telegram = MagicMock()
        update = {"update_id": 50, "callback_query": {
            "id": "q", "from": {"id": ADMIN}, "data": "c:shopee:csv",
            "message": {"message_id": 5, "chat": {"type": "private", "id": ADMIN}},
        }}
        process_updates(bot, telegram, bot.repo, [update], MagicMock(), now=datetime(2026, 10, 22, tzinfo=timezone.utc))
        name, data = telegram.send_document.call_args.args[1:3]
        assert name.endswith(".csv")
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        assert rows[0][1] == "Mã đơn"
        assert rows[1][1] == "SN-o1" and rows[1][5] == "250000"


# --- Bước 2–3: sổ hoàn tiền và báo khách ---------------------------------------


class TestLedger:
    def test_order_moves_pending_holding_available(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        bot.wallet.set_enabled(True)
        sub = _link(bot)
        _order(bot, sub)
        bot.refresh_wallet(datetime(2026, 10, 21, 10, tzinfo=timezone.utc))
        assert bot.wallet.balance(USER).pending_vnd == 7_000  # V1.1: 10.000 × 70%

        _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z", approved=True)
        bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
        entry = bot.wallet.entries(USER)[0]
        assert entry["status"] == "holding"
        # Hardening V1: chưa có ngày vào ví cố định; vào ví khi đủ 30 ngày VÀ kỳ Shopee đã trả.
        assert entry["available_at"] is None

        bot.refresh_wallet(datetime(2026, 11, 21, 1, tzinfo=timezone.utc))
        balance = bot.wallet.balance(USER)
        assert (balance.pending_vnd, balance.withdrawable_vnd) == (0, 7_000)
        events = _customer_events(bot)
        assert [e.split("\n")[0] for e in events] == [
            "🛒 <b>Có đơn mới qua link của bạn</b>",
            "✅ <b>Đơn đã hoàn thành</b>",
            "💰 <b>Tiền hoàn đã vào ví</b>",
        ]

    def test_amount_frozen_once_available_and_clawback_alerts_admin(self, tmp_path):
        bot = _bot(tmp_path, admin_notifications_enabled=True, admin_chat_id=ADMIN)
        bot.admin_notifier = MagicMock()
        _financially_ready(bot)
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z", approved=True)
        bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
        _order(bot, sub, status="COMPLETED", commission=50_000, complete="2026-10-22T00:00:00Z", approved=True)
        bot.refresh_wallet(datetime(2026, 10, 23, tzinfo=timezone.utc))
        assert bot.wallet.balance(USER).withdrawable_vnd == 7_000  # không tính lại sau khi đã vào ví

        _order(bot, sub, status="CANCELLED", complete="2026-10-22T00:00:00Z")
        bot.refresh_wallet(datetime(2026, 10, 24, tzinfo=timezone.utc))
        assert bot.wallet.balance(USER).withdrawable_vnd == 0
        bot.admin_notifier.notify_wallet_clawback.assert_called_once()

    def test_wallet_off_records_but_does_not_message_customer(self, tmp_path):
        bot = _bot(tmp_path)
        sub = _link(bot)
        _order(bot, sub)
        bot.refresh_wallet(datetime(2026, 10, 21, 10, tzinfo=timezone.utc))
        assert bot.wallet.balance(USER).pending_vnd == 7_000
        assert _customer_events(bot) == []

    def test_old_order_first_seen_is_not_announced(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        bot.wallet.set_enabled(True)
        sub = _link(bot)
        _order(bot, sub)
        bot.refresh_wallet(datetime(2026, 11, 30, tzinfo=timezone.utc))
        assert _customer_events(bot) == []

    def test_v12_link_uses_policy_in_force_when_link_was_made(self, tmp_path):
        bot = _bot(tmp_path)
        row = {"estimate_policy": "v1.2", "link_created_at": "2026-10-21T08:08:00Z", "cashback_rate_percent": 70}
        split = bot._real_cashback(10_000, row)
        assert split.label == "v1.2"
        assert 0 < split.cashback_vnd < 7_000  # đã trừ dự phòng phí và thuế trước khi chia
        assert split.fee_vnd > 0 and split.tax_vnd > 0

    def test_v11_link_admin_bears_fee_and_tax(self, tmp_path):
        # Số thật đơn DOPI 2026-10-24: HH 17.368, hoàn 70% trên HH gốc; phí 0,98% và thuế 10% admin chịu.
        bot = _bot(tmp_path)
        row = {"estimate_policy": None, "link_created_at": "2026-10-23T03:18:39Z", "cashback_rate_percent": 70}
        split = bot._real_cashback(17_368, row)
        assert (split.cashback_vnd, split.label) == (12_157, "v1.1:70")
        assert (split.fee_vnd, split.tax_vnd) == (171, 1_737)

    def test_admin_keep_in_stats_and_sync_message(self, tmp_path):
        bot = _bot(tmp_path, admin_notifications_enabled=True, admin_chat_id=ADMIN)
        sub = _link(bot)
        _order(bot, sub, commission=17_368)
        _order(bot, sub, status="CANCELLED", commission=5_000, cid="c2")
        bot.refresh_wallet(datetime(2026, 10, 21, 11, tzinfo=timezone.utc))
        with bot.repo.connect() as conn:
            stats = collect(conn, "all", datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
        shopee = stats.shopee
        # Đơn huỷ không tính.
        assert (shopee.bot_commission_vnd, shopee.bot_cashback_vnd) == (17_368, 12_157)
        assert shopee.admin_keep_vnd == 17_368 - 12_157 - shopee.bot_fee_vnd - shopee.bot_tax_vnd
        keep = format_vnd(shopee.admin_keep_vnd).removesuffix("đ")
        overview = stats_text(stats, period_label="Tất cả", since=None)
        assert f"= Admin    {keep}" in overview or f"= Admin {keep}" in overview.replace("  ", " ")
        assert "Admin còn" in stats_detail_text(stats, period_label="Tất cả", since=None)
        with bot.repo.connect() as conn:
            conversion_id = conn.execute("SELECT conversion_id FROM cashback_entries WHERE status != 'cancelled'").fetchone()[0]
        order = BotOrder("SN", "DOPI", 231_570, 17_368, "UNPAID", False, conversion_id)
        AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN).notify_shopee_sync_result(True, "ok", [order])
        with bot.repo.connect() as conn:
            text = conn.execute("SELECT message_html FROM admin_notifications ORDER BY id DESC").fetchone()[0]
        keep = 17_368 - 12_157 - shopee.bot_fee_vnd - shopee.bot_tax_vnd
        costs = format_vnd(shopee.bot_fee_vnd + shopee.bot_tax_vnd).removesuffix("đ")
        row = f"1 231.570 17.368 12.157 {costs:>5} {format_vnd(keep).removesuffix('đ'):>5} ⏳"
        assert row in text


# --- Bước 4: ngân hàng, rút tiền, admin duyệt ---------------------------------


class TestPayout:
    def _ready(self, tmp_path, amount=20_000):
        bot = _bot(tmp_path, admin_notifications_enabled=True, admin_chat_id=ADMIN)
        bot.admin_notifier = MagicMock()
        _financially_ready(bot)
        bot.wallet.set_enabled(True)
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", commission=amount, complete="2026-10-21T10:00:00Z", approved=True)
        bot.refresh_wallet(datetime(2026, 10, 21, 11, tzinfo=timezone.utc))
        return bot

    def test_parse_bank_text(self):
        assert parse_bank_text("mb 0123456789 Nguyễn Văn Đức") == BankAccount("MB", "0123456789", "NGUYEN VAN DUC")
        assert parse_bank_text("Vietcombank | 0011.0022.33 | tran thi b") == BankAccount("VCB", "0011002233", "TRAN THI B")
        assert parse_bank_text("XYZ 0123456789 A B") == "bank"
        assert parse_bank_text("MB 12ab 3 Nguyen") == "account"
        assert parse_bank_text("MB 0123456") == "format"

    def test_full_withdraw_flow(self, tmp_path):
        bot = self._ready(tmp_path)
        page = _callback(bot, USER, "u:p:wallet")
        assert "Có thể rút: <b>14.000đ</b>" in page.text
        assert "u:w:out" not in _buttons(page)  # chưa khai ngân hàng

        assert "u:w:bk:MB" in _buttons(_callback(bot, USER, "u:w:bank"))
        _callback(bot, USER, "u:w:bk:MB")
        bad = bot.handle_text(USER, "buyer", "Nguyen Van A", update_id=2, now=NOW)
        assert "Số tài khoản chỉ gồm" in bad.text
        saved = bot.handle_text(USER, "buyer", "0123 456 789 Nguyễn Văn A", update_id=3, now=NOW)
        assert "Đã lưu tài khoản MB Bank ••••6789 · NGUYEN VAN A" in saved.text
        assert "u:w:out" in _buttons(saved)

        confirm = _callback(bot, USER, "u:w:out")
        assert "Xác nhận rút tiền" in confirm.text
        done = _callback(bot, USER, "u:w:out:ok", query_id="tap-1")
        assert "Hoan tien 000001" in done.text
        bot.admin_notifier.notify_payout_request.assert_called_once()
        retry = _callback(bot, USER, "u:w:out:ok", query_id="tap-1")  # Telegram gửi lại cùng lần bấm
        assert "Hoan tien 000001" in retry.text
        again = _callback(bot, USER, "u:w:out:ok")
        assert "đang có một yêu cầu rút" in again.text
        assert bot.wallet.balance(USER).withdrawable_vnd == 0
        assert bot.wallet.balance(USER).requested_vnd == 14_000

        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert "••••6789" in detail.text and "0123456789" not in detail.text and detail.photo is None
        assert "chưa xác minh" in detail.text
        assert _buttons(detail)[0] == "c:wl:mv:1:1:rv"
        ask = _callback(bot, ADMIN, "c:wl:mv:1:1:rv")
        assert "c:wl:mv:1:1:rv:ok" in _buttons(ask)
        assert bot.wallet.payout(1)["status"] == "requested"  # chưa bấm xác nhận thì chưa ghi
        _callback(bot, ADMIN, "c:wl:mv:1:1:rv:ok")
        blocked = _callback(bot, ADMIN, "c:wl:mv:1:2:ap:ok")
        assert "Tài khoản người nhận chưa xác minh" in blocked.text
        _callback(bot, ADMIN, "c:wl:vb:1")
        bot.handle_text(ADMIN, "admin", "chuyển thử 1.000đ, app hiện NGUYEN VAN A", update_id=10, now=NOW)
        _callback(bot, ADMIN, "c:wl:mv:1:2:ap:ok")
        moving = _callback(bot, ADMIN, "c:wl:mv:1:3:pr:ok")
        assert "<code>0123456789</code>" in moving.text and "vietqr.io" not in moving.text
        assert moving.photo is not None and moving.photo[1][:8] == b"\x89PNG\r\n\x1a\n"
        _callback(bot, ADMIN, "c:wl:mv:1:4:se:ok")
        assert _customer_events(bot) == [] or "Đã chuyển tiền hoàn" not in _customer_events(bot)[-1]
        _callback(bot, ADMIN, "c:wl:mv:1:5:pd:ok")
        bot.handle_text(ADMIN, "admin", "FT26102400001", update_id=11, now=NOW)
        assert bot.wallet.payout(1)["status"] == "paid_confirmed"
        assert bot.wallet.balance(USER).paid_vnd == 14_000
        assert "Đã chuyển tiền hoàn" in _customer_events(bot)[-1]
        twice = _callback(bot, ADMIN, "c:wl:mv:1:5:pd:ok")
        assert "Nút đã cũ" in twice.text

    def test_reject_returns_money_to_wallet(self, tmp_path):
        bot = self._ready(tmp_path)
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        _callback(bot, USER, "u:w:out:ok")
        _callback(bot, ADMIN, "c:wl:mv:1:1:rj:ok")
        assert bot.wallet.payout(1)["status"] == "requested", "từ chối phải có lý do"
        bot.handle_text(ADMIN, "admin", "Tên chủ tài khoản không khớp", update_id=12, now=NOW)
        assert bot.wallet.balance(USER).withdrawable_vnd == 14_000
        assert "chưa được duyệt" in _customer_events(bot)[-1] and "Tên chủ tài khoản không khớp" in _customer_events(bot)[-1]

    def test_below_minimum_cannot_withdraw(self, tmp_path):
        bot = self._ready(tmp_path, amount=10_000)  # 7.000đ < 10.000đ
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        assert "u:w:out" not in _buttons(_callback(bot, USER, "u:p:wallet"))
        assert "Chưa đủ số tối thiểu" in _callback(bot, USER, "u:w:out:ok").text

    def test_command_cancels_bank_waiting(self, tmp_path):
        bot = self._ready(tmp_path)
        _callback(bot, USER, "u:w:bk:MB")
        bot.handle_text(USER, "buyer", "/start", update_id=4, now=NOW)
        reply = bot.handle_text(USER, "buyer", "0123456789 Nguyen Van A", update_id=5, now=NOW)
        assert "Đã lưu tài khoản" not in reply.text


class TestSwitch:
    def test_wallet_off_customer_sees_nothing_new(self, tmp_path):
        bot = _bot(tmp_path)
        home = bot.handle_text(USER, "buyer", "/start", update_id=1, now=NOW)
        assert "u:p:wallet" not in _buttons(home)
        assert "Ví hoàn tiền chưa mở" in _callback(bot, USER, "u:w:out:ok").toast

    def test_enable_needs_confirm_then_home_and_calc_change(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        ask = _callback(bot, ADMIN, "c:wl:on")
        assert "Bật ví cho khách?" in ask.text
        assert bot.wallet.settings().enabled is False
        _callback(bot, ADMIN, "c:wl:on:ok")
        home = bot.handle_text(USER, "buyer", "/start", update_id=1, now=NOW)
        assert "u:p:wallet" in _buttons(home)
        assert "chưa chi trả" not in home.text
        calc = bot.handle_text(USER, "buyer", "/cachtinh", update_id=2, now=NOW)
        assert "30 ngày" in calc.text and "%" not in calc.text

    def test_settings_presets(self, tmp_path):
        bot = _bot(tmp_path)
        _callback(bot, ADMIN, "c:wl:hold:7")
        reply = _callback(bot, ADMIN, "c:wl:min:50000")
        assert "<b>7 ngày</b>" in reply.text and "50.000đ" in reply.text
        assert bot.wallet.settings().hold_days == 7
        _callback(bot, ADMIN, "c:wl:hold:3")  # không có trong lựa chọn → bỏ qua
        assert bot.wallet.settings().hold_days == 7

    def test_admin_chinh_han_muc_rut(self, tmp_path):
        """ADR-059: admin chỉnh hạn mức trong ⚙️ Cài đặt; mỗi lần đổi thêm một dòng ACTIVE, «Rút tối thiểu» kéo theo."""
        bot = _bot(tmp_path)
        assert "Hạn mức rút: <b>chưa duyệt</b>" in _callback(bot, ADMIN, "c:wl:cfg").text
        assert "Chưa có bảng hạn mức" in _callback(bot, ADMIN, "c:wl:lim:req:2000000").text
        with bot.repo.connect() as conn:
            conn.execute(
                "INSERT INTO payout_limit_policies (min_vnd, max_per_request_vnd, daily_total_vnd, monthly_total_vnd, "
                "status, created_by, approved_by, approved_at, created_at) "
                "VALUES (20000, 500000, 2000000, 10000000, 'ACTIVE', 'chu_bot', 'chu_bot', 'x', 'x')"
            )

        def limits():
            with bot.repo.connect() as conn:
                return payouts.active_limits(conn)

        screen = _callback(bot, ADMIN, "c:wl:cfg")
        assert "mỗi khách: tối đa <b>500.000đ</b>/lần · <b>2.000.000đ</b>/ngày · <b>10.000.000đ</b>/tháng" in screen.text
        assert ("• 500k/lần", "c:wl:lim:req:500000") in screen.inline_keyboard[2]
        assert ("• 2tr/ngày", "c:wl:lim:day:2000000") in screen.inline_keyboard[3]

        _callback(bot, ADMIN, "c:wl:min:10000")  # trùng mặc định ví, nhưng bảng hạn mức đang 20k → kéo về 10k
        assert limits().min_vnd == 10_000
        _callback(bot, ADMIN, "c:wl:lim:req:2000000")
        assert limits().max_per_request_vnd == 2_000_000
        refused = _callback(bot, ADMIN, "c:wl:lim:req:5000000")  # vượt tổng ngày 2tr
        assert "Không đổi" in refused.text and limits().max_per_request_vnd == 2_000_000
        _callback(bot, ADMIN, "c:wl:lim:day:5000000")
        _callback(bot, ADMIN, "c:wl:lim:req:5000000")
        assert (limits().max_per_request_vnd, limits().daily_total_vnd) == (5_000_000, 5_000_000)
        _callback(bot, ADMIN, "c:wl:lim:day:3000000")  # không có trong lựa chọn → bỏ qua
        _callback(bot, ADMIN, "c:wl:lim:day:5000000")  # bấm lại cùng mức: không thêm dòng
        _callback(bot, USER, "c:wl:lim:month:50000000")  # khách không chỉnh được
        assert limits().monthly_total_vnd == 10_000_000
        with bot.repo.connect() as conn:
            rows = conn.execute("SELECT approved_by FROM payout_limit_policies ORDER BY id").fetchall()
        assert [r[0] for r in rows] == ["chu_bot"] + [f"admin:{ADMIN}"] * 4

        history = _callback(bot, ADMIN, "c:menu:hist").text
        assert "Ví khách: hạn mức rút tối thiểu 20.000đ → 10.000đ" in history
        assert "Ví khách: hạn mức rút mỗi ngày 2.000.000đ → 5.000.000đ" in history

    def test_customer_cannot_use_admin_wallet_buttons(self, tmp_path):
        bot = _bot(tmp_path)
        reply = _callback(bot, USER, "c:wl:on:ok")
        assert "chỉ dành cho quản trị" in reply.text
        assert bot.wallet.settings().enabled is False


class TestHistory:
    def _history(self, bot) -> str:
        return _callback(bot, ADMIN, "c:menu:hist").text

    def test_wallet_settings_show_in_history(self, tmp_path):
        bot = _bot(tmp_path)
        _callback(bot, ADMIN, "c:wl:hold:15")
        _callback(bot, ADMIN, "c:wl:hold:15")  # bấm lại cùng mức: không ghi thêm dòng
        _callback(bot, ADMIN, "c:wl:min:20000")
        _financially_ready(bot)
        _callback(bot, ADMIN, "c:wl:on:ok")
        _callback(bot, ADMIN, "c:wl:off")
        text = self._history(bot)
        assert "Ví khách: giữ tiền 30 → 15 ngày sau khi đơn hoàn thành" in text
        assert text.count("giữ tiền") == 1
        assert "Ví khách: rút tối thiểu 10.000đ → 20.000đ" in text
        assert "Ví khách → bật" in text and "Ví khách → tắt" in text
        # Mới nhất lên đầu, giống các dòng cũ
        assert text.index("Ví khách → tắt") < text.index("Ví khách → bật")

    def test_shopee_cookie_connect_in_history_without_cookie(self, tmp_path, monkeypatch):
        bot = _bot(tmp_path)
        monkeypatch.setattr(
            "cashback_bot.shopee_client.ShopeeAffiliateClient.check_status",
            lambda self: ShopeeStatusResult(ok=True, status_code=200, username="ID 17315920094"),
        )
        _callback(bot, ADMIN, "c:shopee:auth")
        bot.handle_text(ADMIN, "owner", "SPC_EC=bi_mat_khong_duoc_lo", update_id=70, now=NOW)
        text = self._history(bot)
        assert "Shopee Affiliate: kết nối cookie (ID 17315920094)" in text
        with bot.repo.connect() as conn:
            dump = " ".join(str(v) for row in conn.execute("SELECT * FROM admin_change_audit") for v in row)
        assert "bi_mat_khong_duoc_lo" not in dump


class TestAutoSyncSwitch:
    def test_auto_sync_off_by_default_and_toggle_logged(self, tmp_path, monkeypatch):
        bot = _bot(tmp_path)
        bot.repo.update_shopee_cookie_status(status="connected")
        engine = MagicMock()
        engine.return_value.sync.return_value = SyncResult(ok=True, message="ok")
        coordinator = SyncCoordinator(bot.repo, MagicMock(), engine_factory=engine)
        coordinator.start()

        assert coordinator.next_job() is None
        engine.assert_not_called()  # mặc định: không tự gọi Shopee
        screen = _callback(bot, ADMIN, "c:menu:shopee")
        assert "Tự đồng bộ: ⏸️ <b>tắt</b>" in screen.text
        assert "c:sy:home" in _buttons(screen) and "c:shopee:auto:on" not in _buttons(screen)

        # PLAN-080: nút Telegram không bật được khi cờ .env tắt (không có đường vượt cờ).
        refused = _callback(bot, ADMIN, "c:shopee:auto:on")
        assert "SHOPEE_AUTO_SYNC_ENABLED" in refused.text
        assert coordinator.next_job() is None
        engine.assert_not_called()

        on = _bot(tmp_path, auto_sync=AutoSyncConfig(enabled=True))
        paused = _callback(on, ADMIN, "c:shopee:auto:off")
        assert "Đã tạm dừng" in paused.text and "c:shopee:auto:on" in _buttons(paused)
        _callback(on, ADMIN, "c:shopee:auto:on")
        history = _callback(on, ADMIN, "c:menu:hist").text
        assert "tự đồng bộ → tạm dừng" in history and "tự đồng bộ → tiếp tục" in history

    def test_wallet_moves_on_time_without_calling_shopee(self, tmp_path):
        bot = _bot(tmp_path)
        bot.refresh_wallet = MagicMock()
        _check_wallet_refresh(bot, bot.repo)
        _check_wallet_refresh(bot, bot.repo)  # chưa đủ 1 giờ
        assert bot.refresh_wallet.call_count == 1


class TestPaidBasisWording:
    """Khách được báo số trên link tính theo giá tham khảo, số thật theo tiền thực trả (2026-10-24)."""

    def test_link_card_explains_paid_basis(self, tmp_path):
        reply = _bot(tmp_path).handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=901, now=NOW)
        assert "💰 Hoàn dự kiến: khoảng <b>" in reply.text
        assert "Shopee tính trên số tiền bạn thực trả" in reply.text
        assert "voucher, xu" in reply.text
        assert "%" not in reply.text

    def test_cachtinh_explains_paid_basis(self, tmp_path):
        reply = _bot(tmp_path).handle_text(USER, "buyer", "/cachtinh", update_id=902, now=NOW)
        assert "Số trên link tính theo giá tham khảo" in reply.text
        assert "%" not in reply.text

    def test_order_notice_says_why_lower_than_link(self):
        text = entry_notice("pending", "DOPI Kem Nền", 12_157, None, 15, estimated_vnd=21_357)
        assert "Hoàn tạm tính: <b>12.157đ</b>" in text
        assert "Lúc tạo link bot báo khoảng 21.357đ theo giá tham khảo" in text
        same = entry_notice("pending", "DOPI Kem Nền", 21_357, None, 15, estimated_vnd=21_357)
        assert "Lúc tạo link" not in same
        assert "Lúc tạo link" not in entry_notice("pending", "Áo", 5_000, None, 15)

    def test_refresh_passes_link_estimate_to_customer(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        bot.wallet.set_enabled(True)
        sub = _link(bot)
        _order(bot, sub, commission=1_000)
        bot.refresh_wallet(datetime(2026, 10, 21, 11, tzinfo=timezone.utc))
        events = _customer_events(bot)
        assert len(events) == 1 and "Lúc tạo link bot báo khoảng" in events[0]
