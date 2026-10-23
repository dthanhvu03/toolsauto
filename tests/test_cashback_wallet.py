"""PLAN-066: đối soát đầy đủ, đồng bộ chạy nền, CSV, sổ hoàn tiền, ví khách, rút tiền."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from unittest.mock import MagicMock

import cashback_bot.poller as poller
from cashback_bot.admin_stats import collect
from cashback_bot.admin_ui import stats_text
from cashback_bot.poller import _check_shopee_auto_sync, _check_wallet_refresh, process_updates
from cashback_bot.shopee_client import ShopeeStatusResult
from cashback_bot.shopee_sync import SYNC_REQUEST_KEY, ShopeeSyncEngine, SyncResult
from cashback_bot.wallet import BankAccount, parse_bank_text, transfer_note, vietqr_url
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


def _order(bot, sub_id: str, status: str = "PENDING", commission: int = 10_000, complete: str | None = None, cid="o1"):
    bot.repo.record_shopee_conversion(
        conversion_id=cid,
        sub_id=sub_id,
        order_sn=f"SN-{cid}",
        order_status=status,
        conversion_status="",
        purchase_time=PURCHASE,
        gross_commission_vnd=commission,
        net_commission_vnd=commission,
        details={"item_name": "Áo Polo Nam", "gmv_vnd": 250_000, "item_qty": 1, "complete_time": complete},
    )


def _customer_events(bot) -> list[str]:
    with bot.repo.connect() as conn:
        rows = conn.execute(
            "SELECT message_html FROM admin_notifications WHERE chat_id = ? ORDER BY id", (USER,)
        ).fetchall()
    return [row[0] for row in rows]


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


def _callback(bot, user_id: int, data: str) -> object:
    update = {
        "update_id": 99,
        "callback_query": {"id": "q", "from": {"id": user_id}, "data": data, "message": {"message_id": 5, "chat": {"type": "private"}}},
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
        assert "Doanh số <b>399.000đ</b>" in text
        assert "HH gốc 20.000đ − phí MCN 2.000đ" in text
        assert "<pre>" in text and "7 ngày qua" in text

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
        # Vừa tự đồng bộ xong nhưng admin bấm: vẫn chạy ngay, báo kết quả, cập nhật sổ.
        bot.repo.set_state("shopee_last_auto_sync", str(datetime.now(timezone.utc).timestamp()))
        notifier, synced = MagicMock(), MagicMock()
        engine = MagicMock()
        engine.return_value.sync.return_value = SyncResult(ok=True, message="Đồng bộ xong: 1 click")
        monkeypatch.setattr(poller, "ShopeeSyncEngine", engine)
        _check_shopee_auto_sync(bot.repo, notifier, on_synced=synced)
        engine.return_value.sync.side_effect = RuntimeError("boom")
        bot.repo.set_state(SYNC_REQUEST_KEY, "1")
        _check_shopee_auto_sync(bot.repo, notifier, on_synced=synced)
        assert engine.call_args.kwargs["admin_notifier"] is notifier
        assert notifier.notify_shopee_sync_result.call_args_list[0].args == (True, "Đồng bộ xong: 1 click")
        assert notifier.notify_shopee_sync_result.call_args_list[1].args[0] is False
        assert synced.call_count == 1
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
        bot.wallet.set_enabled(True)
        sub = _link(bot)
        _order(bot, sub)
        bot.refresh_wallet(datetime(2026, 10, 21, 10, tzinfo=timezone.utc))
        assert bot.wallet.balance(USER).pending_vnd == 7_000  # V1.1: 10.000 × 70%

        _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z")
        bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
        entry = bot.wallet.entries(USER)[0]
        assert entry["status"] == "holding"
        assert entry["available_at"] == "2026-11-21T00:00:00Z"  # 30 ngày mặc định

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
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z")
        bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
        _order(bot, sub, status="COMPLETED", commission=50_000, complete="2026-10-22T00:00:00Z")
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
        bot.wallet.set_enabled(True)
        sub = _link(bot)
        _order(bot, sub)
        bot.refresh_wallet(datetime(2026, 11, 30, tzinfo=timezone.utc))
        assert _customer_events(bot) == []

    def test_v12_link_uses_policy_in_force_when_link_was_made(self, tmp_path):
        bot = _bot(tmp_path)
        row = {"estimate_policy": "v1.2", "link_created_at": "2026-10-21T08:08:00Z", "cashback_rate_percent": 70}
        amount, label = bot._real_cashback(10_000, row)
        assert label == "v1.2"
        assert 0 < amount < 7_000  # đã trừ dự phòng phí và thuế trước khi chia


# --- Bước 4: ngân hàng, rút tiền, admin duyệt ---------------------------------


class TestPayout:
    def _ready(self, tmp_path, amount=20_000):
        bot = _bot(tmp_path, admin_notifications_enabled=True, admin_chat_id=ADMIN)
        bot.admin_notifier = MagicMock()
        bot.wallet.set_enabled(True)
        bot.wallet.set_hold_days(0)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", commission=amount, complete="2026-10-21T10:00:00Z")
        bot.refresh_wallet(datetime(2026, 10, 21, 11, tzinfo=timezone.utc))
        return bot

    def test_parse_bank_text(self):
        assert parse_bank_text("mb 0123456789 Nguyễn Văn Đức") == BankAccount("MB", "0123456789", "NGUYEN VAN DUC")
        assert parse_bank_text("Vietcombank | 0011.0022.33 | tran thi b") == BankAccount("VCB", "0011002233", "TRAN THI B")
        assert parse_bank_text("XYZ 0123456789 A B") == "bank"
        assert parse_bank_text("MB 12ab 3 Nguyen") == "account"
        assert parse_bank_text("MB 0123456") == "format"

    def test_vietqr_url(self):
        url = vietqr_url("MB", "0123456789", "NGUYEN VAN A", 14_000, transfer_note(12))
        assert url == (
            "https://img.vietqr.io/image/970422-0123456789-compact2.png"
            "?amount=14000&addInfo=Hoan%20tien%20000012&accountName=NGUYEN%20VAN%20A"
        )

    def test_full_withdraw_flow(self, tmp_path):
        bot = self._ready(tmp_path)
        page = _callback(bot, USER, "u:p:wallet")
        assert "Có thể rút: <b>14.000đ</b>" in page.text
        assert "u:w:out" not in _buttons(page)  # chưa khai ngân hàng

        _callback(bot, USER, "u:w:bank")
        bad = bot.handle_text(USER, "buyer", "MB abc", update_id=2, now=NOW)
        assert "Thiếu thông tin" in bad.text or "Số tài khoản" in bad.text
        saved = bot.handle_text(USER, "buyer", "MB 0123456789 Nguyen Van A", update_id=3, now=NOW)
        assert "Đã lưu tài khoản MB Bank ••••6789" in saved.text
        assert "u:w:out" in _buttons(saved)

        confirm = _callback(bot, USER, "u:w:out")
        assert "Xác nhận rút tiền" in confirm.text
        done = _callback(bot, USER, "u:w:out:ok")
        assert "Hoan tien 000001" in done.text
        bot.admin_notifier.notify_payout_request.assert_called_once()
        again = _callback(bot, USER, "u:w:out:ok")
        assert "đang có một yêu cầu rút" in again.text
        assert bot.wallet.balance(USER).withdrawable_vnd == 0

        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert "<code>0123456789</code>" in detail.text and "img.vietqr.io" in detail.text
        ask = _callback(bot, ADMIN, "c:wl:paid:1")
        assert "c:wl:paid:1:ok" in _buttons(ask)
        assert bot.wallet.payout(1)["status"] == "requested"  # chưa bấm xác nhận thì chưa ghi
        _callback(bot, ADMIN, "c:wl:paid:1:ok")
        assert bot.wallet.payout(1)["status"] == "paid"
        assert bot.wallet.balance(USER).paid_vnd == 14_000
        assert "Đã chuyển tiền hoàn" in _customer_events(bot)[-1]
        twice = _callback(bot, ADMIN, "c:wl:paid:1:ok")
        assert "đã được xử lý" in twice.text

    def test_reject_returns_money_to_wallet(self, tmp_path):
        bot = self._ready(tmp_path)
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        _callback(bot, USER, "u:w:out:ok")
        _callback(bot, ADMIN, "c:wl:rej:1:ok")
        assert bot.wallet.balance(USER).withdrawable_vnd == 14_000
        assert "chưa được duyệt" in _customer_events(bot)[-1]

    def test_below_minimum_cannot_withdraw(self, tmp_path):
        bot = self._ready(tmp_path, amount=10_000)  # 7.000đ < 10.000đ
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        assert "u:w:out" not in _buttons(_callback(bot, USER, "u:p:wallet"))
        assert "Chưa đủ số tối thiểu" in _callback(bot, USER, "u:w:out:ok").text

    def test_command_cancels_bank_waiting(self, tmp_path):
        bot = self._ready(tmp_path)
        _callback(bot, USER, "u:w:bank")
        bot.handle_text(USER, "buyer", "/start", update_id=4, now=NOW)
        reply = bot.handle_text(USER, "buyer", "MB 0123456789 Nguyen Van A", update_id=5, now=NOW)
        assert "Đã lưu tài khoản" not in reply.text


class TestSwitch:
    def test_wallet_off_customer_sees_nothing_new(self, tmp_path):
        bot = _bot(tmp_path)
        home = bot.handle_text(USER, "buyer", "/start", update_id=1, now=NOW)
        assert "u:p:wallet" not in _buttons(home)
        assert "Ví hoàn tiền chưa mở" in _callback(bot, USER, "u:w:out:ok").toast

    def test_enable_needs_confirm_then_home_and_calc_change(self, tmp_path):
        bot = _bot(tmp_path)
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
        monkeypatch.setattr(poller, "ShopeeSyncEngine", engine)

        _check_shopee_auto_sync(bot.repo, MagicMock())
        engine.assert_not_called()  # mặc định: không tự gọi Shopee
        screen = _callback(bot, ADMIN, "c:menu:shopee")
        assert "Tự đồng bộ: ⏸️ <b>tắt</b>" in screen.text
        assert "c:shopee:auto:on" in _buttons(screen)

        on = _callback(bot, ADMIN, "c:shopee:auto:on")
        assert "c:shopee:auto:off" in _buttons(on)
        _check_shopee_auto_sync(bot.repo, MagicMock())
        assert engine.return_value.sync.call_args.kwargs["trigger"] == "auto"

        _callback(bot, ADMIN, "c:shopee:auto:off")
        history = _callback(bot, ADMIN, "c:menu:hist").text
        assert "tự đồng bộ 4 giờ → bật" in history and "tự đồng bộ 4 giờ → tắt" in history

    def test_wallet_moves_on_time_without_calling_shopee(self, tmp_path):
        bot = _bot(tmp_path)
        bot.refresh_wallet = MagicMock()
        _check_wallet_refresh(bot, bot.repo)
        _check_wallet_refresh(bot, bot.repo)  # chưa đủ 1 giờ
        assert bot.refresh_wallet.call_count == 1
