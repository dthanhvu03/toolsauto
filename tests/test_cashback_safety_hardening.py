"""Production Safety Hardening V1: cô lập update lỗi, log không lộ bí mật, backup tự động, khoá tài chính.

Mọi test chạy trên SQLite tạm (tmp_path), Telegram và Shopee đều giả. Không chạm DB production.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import stat
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

import cashback_bot.poller as poller
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.backup import (
    REQUIRED_TABLES,
    backup_database,
    latest_backup,
    restore_database,
    run_scheduled_backup,
    verify_backup,
)
from cashback_bot.calculator import CalculationError
from cashback_bot.payout_gate import REASON_SETTLEMENT, REASON_TAX, PayoutBlocked, is_fraud
from cashback_bot.poller import _check_backup, classify_update_error, process_updates
from cashback_bot.redact import RedactingFormatter, error_brief, redact
from cashback_bot.telegram_api import TelegramApi, TelegramDeliveryError
from cashback_bot.wallet import BankAccount
from tests.test_cashback_bot import NOW as QUOTE_NOW
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_wallet import (
    ADMIN,
    USER,
    _bot,
    _buttons,
    _callback,
    _financially_ready,
    _link,
    _order,
)

TOKEN = "123456789:AAH" + "x" * 32
NOW = datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc)


def _msg(update_id: int, text: str = "/start", user_id: int = USER) -> dict:
    return {
        "update_id": update_id,
        "message": {"chat": {"type": "private", "id": user_id}, "from": {"id": user_id, "username": "buyer"}, "text": text},
    }


class _Telegram:
    def __init__(self, fail_answer: bool = False):
        self.sent: list[tuple[int, str]] = []
        self.fail_answer = fail_answer

    def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
        self.sent.append((chat_id, html))

    def answer_callback(self, *_args, **_kwargs):
        if self.fail_answer:
            raise requests.ConnectionError(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery")


def _setup(tmp_path):
    bot = service(
        tmp_path,
        FakeClient(payload(last_update=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))),
        customer_access_enabled=True,
        allowed_telegram_ids=frozenset(),
        admin_user_ids=frozenset({ADMIN}),
    )
    admin = MagicMock()
    return bot, _Telegram(), admin


def _flaky(bot, fail_ids: dict[int, list[Exception]]):
    """handle_update ném lần lượt các lỗi đã định cho từng update, hết lỗi thì chạy thật."""
    real = bot.handle_update

    def handle(update):
        queue = fail_ids.get(update["update_id"])
        if queue:
            raise queue.pop(0)
        return real(update)

    bot.handle_update = handle


# --- P0-4: một update lỗi không làm kẹt bot -------------------------------------------------


class TestUpdateIsolation:
    def test_permanent_error_is_quarantined_and_next_update_still_runs(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {10: [KeyError("message")]})
        process_updates(bot, tg, bot.repo, [_msg(10), _msg(11)], admin, now=NOW, sleep=lambda _s: None)
        assert bot.repo.get_offset() == 12
        row = bot.repo.update_failure(10)
        assert (row["status"], row["category"], row["attempt_count"]) == ("quarantined", "invalid_update", 1)
        assert row["update_type"] == "message" and row["telegram_user_id"] == USER
        assert [chat for chat, _ in tg.sent] == [USER]  # update 11 vẫn được trả lời
        admin.notify_request_failed.assert_called_once()
        assert admin.notify_request_failed.call_args.kwargs["status"] == "QUARANTINED"

    def test_quarantined_count_visible_in_admin_stats(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {12: [KeyError("x")]})
        process_updates(bot, tg, bot.repo, [_msg(12)], admin, now=NOW, sleep=lambda _s: None)
        reply = bot.admin_panel.handle_callback(ADMIN, "c:st:all", "private", NOW)
        assert "Update cách ly: <b>1</b>" in reply.text

    def test_business_error_is_permanent(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {5: [CalculationError("gross")]})
        process_updates(bot, tg, bot.repo, [_msg(5)], admin, now=NOW, sleep=lambda _s: None)
        assert bot.repo.update_failure(5)["category"] == "business"
        assert bot.repo.get_offset() == 6

    def test_transient_error_keeps_offset_then_retry_succeeds(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        bot.repo.set_offset(20)
        _flaky(bot, {20: [requests.ConnectionError("reset")]})
        sleeps = []
        process_updates(bot, tg, bot.repo, [_msg(20), _msg(21)], admin, now=NOW, sleep=sleeps.append)
        # Offset giữ nguyên, update sau chưa xử lý (thứ tự được giữ), có giãn cách.
        assert bot.repo.get_offset() == 20
        assert tg.sent == [] and sleeps == [1]
        assert bot.repo.update_failure(20)["status"] == "retrying"
        process_updates(bot, tg, bot.repo, [_msg(20), _msg(21)], admin, now=NOW, sleep=sleeps.append)
        assert bot.repo.get_offset() == 22
        assert bot.repo.update_failure(20)["status"] == "resolved"
        assert len(tg.sent) == 2
        admin.notify_request_failed.assert_not_called()

    def test_persistent_network_error_quarantined_after_limit_no_infinite_loop(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {30: [requests.Timeout("t") for _ in range(10)]})
        sleeps = []
        for _ in range(10):
            process_updates(bot, tg, bot.repo, [_msg(30), _msg(31)], admin, now=NOW, sleep=sleeps.append)
            if bot.repo.get_offset() == 32:
                break
        row = bot.repo.update_failure(30)
        assert (row["status"], row["attempt_count"]) == ("quarantined", poller.UPDATE_RETRY_LIMITS["network"])
        assert sleeps == [1, 2, 4, 8]
        assert bot.repo.get_offset() == 32 and len(tg.sent) == 1

    def test_failure_record_survives_restart(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {40: [sqlite3.OperationalError("database is locked")]})
        process_updates(bot, tg, bot.repo, [_msg(40)], admin, now=NOW, sleep=lambda _s: None)
        again, tg2, admin2 = _setup(tmp_path)  # process mới, cùng file DB
        assert again.repo.update_failure(40)["attempt_count"] == 1
        _flaky(again, {40: [sqlite3.OperationalError("database is locked")]})
        process_updates(again, tg2, again.repo, [_msg(40)], admin2, now=NOW, sleep=lambda _s: None)
        assert again.repo.update_failure(40)["attempt_count"] == 2

    def test_cannot_record_failure_does_not_advance_offset(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        bot.repo.set_offset(50)
        _flaky(bot, {50: [KeyError("x")]})
        with patch.object(bot.repo, "record_update_failure", side_effect=sqlite3.OperationalError("disk I/O")):
            with pytest.raises(sqlite3.OperationalError):
                process_updates(bot, tg, bot.repo, [_msg(50), _msg(51)], admin, now=NOW, sleep=lambda _s: None)
        assert bot.repo.get_offset() == 50  # không có bản ghi cách ly thì không bỏ qua update

    def test_retry_same_update_never_creates_second_link(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        link = _msg(60, "https://shopee.vn/product/9/8")
        real_enqueue = bot.repo.enqueue_outbound
        calls = {"n": 0}

        def enqueue_once_fails(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_enqueue(*args, **kwargs)

        with patch.object(bot.repo, "enqueue_outbound", side_effect=enqueue_once_fails):
            process_updates(bot, tg, bot.repo, [link], admin, now=NOW, sleep=lambda _s: None)
            process_updates(bot, tg, bot.repo, [link], admin, now=NOW, sleep=lambda _s: None)
        with bot.repo.connect() as conn:
            links = conn.execute("SELECT sub_id FROM link_requests WHERE telegram_update_id = 60").fetchall()
            outbound = conn.execute("SELECT COUNT(*) FROM outbound_messages WHERE telegram_update_id = 60").fetchone()[0]
        assert len(links) == 1 and outbound == 1
        assert len(tg.sent) == 1  # khách nhận đúng một tin, cùng một link
        assert bot.repo.get_offset() == 61

    def test_outbox_rows_untouched_by_quarantine(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        bot.repo.enqueue_outbound(70, USER, "đã xếp hàng", None)
        _flaky(bot, {71: [TypeError("bad")]})
        process_updates(bot, tg, bot.repo, [_msg(71)], admin, now=NOW, sleep=lambda _s: None)
        with bot.repo.connect() as conn:
            row = conn.execute("SELECT body_html, status FROM outbound_messages WHERE telegram_update_id = 70").fetchone()
        assert row["body_html"] == "đã xếp hàng" and row["status"] != "needs_review"

    def test_side_call_failure_does_not_fail_update(self, tmp_path):
        bot, _tg, admin = _setup(tmp_path)
        tg = _Telegram(fail_answer=True)
        update = {
            "update_id": 80,
            "callback_query": {
                "id": "q1",
                "from": {"id": USER, "username": "buyer"},
                "data": "u:p:guide",
                "message": {"message_id": 3, "chat": {"id": USER, "type": "private"}},
            },
        }
        process_updates(bot, tg, bot.repo, [update], admin, now=NOW, sleep=lambda _s: None)
        assert bot.repo.update_failure(80) is None
        assert bot.repo.get_offset() == 81

    def test_error_detail_is_redacted(self, tmp_path):
        bot, tg, admin = _setup(tmp_path)
        _flaky(bot, {90: [ValueError(f"boom https://api.telegram.org/bot{TOKEN}/x SPC_EC=secretcookie")]})
        process_updates(bot, tg, bot.repo, [_msg(90)], admin, now=NOW, sleep=lambda _s: None)
        detail = bot.repo.update_failure(90)["error_detail"]
        assert TOKEN not in detail and "secretcookie" not in detail
        assert detail.startswith("ValueError:")

    def test_classification(self):
        assert classify_update_error(requests.ConnectionError()) == "network"
        assert classify_update_error(TelegramDeliveryError("transient")) == "telegram_send"
        assert classify_update_error(TelegramDeliveryError("permanent")) == "telegram_rejected"
        assert classify_update_error(sqlite3.OperationalError()) == "database"
        assert classify_update_error(CalculationError("x")) == "business"
        assert classify_update_error(KeyError("x")) == "invalid_update"
        assert classify_update_error(RuntimeError("x")) == "unknown"

    def test_admin_alert_for_loop_errors_not_once_forever(self, tmp_path):
        bot, _tg, _admin = _setup(tmp_path)
        notifier = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN, fail_cooldown_sec=0)
        with patch("cashback_bot.admin_notify.datetime") as fake:
            for second in (1000, 2000):
                fake.now.return_value = datetime.fromtimestamp(second, timezone.utc)
                notifier.notify_request_failed(error_type="poll_loop_failed", status="POLL_ERROR")
        with bot.repo.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type='REQUEST_FAILED'").fetchone()[0] == 2


# --- P1-8: log không lộ token, cookie, API key ------------------------------------------------


class TestSecretSafeLogging:
    def test_edit_and_delete_network_errors_do_not_log_token(self, caplog):
        api = TelegramApi(TOKEN)
        err = requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.telegram.org'): Max retries exceeded with url: /bot{TOKEN}/editMessageText"
        )
        with patch("cashback_bot.telegram_api.requests.post", side_effect=err), caplog.at_level(logging.INFO):
            assert api.edit_message_text(1, 2, "x") is False
            assert api.delete_message(1, 2) is False
        text = caplog.text
        assert TOKEN not in text
        assert "editMessageText network error: ConnectionError" in text
        assert "deleteMessage network error: ConnectionError" in text

    def test_http_error_body_is_redacted(self, caplog):
        api = TelegramApi(TOKEN)
        response = MagicMock(status_code=500, text=f"oops {TOKEN}")
        with patch("cashback_bot.telegram_api.requests.post", return_value=response), caplog.at_level(logging.INFO):
            api.edit_message_text(1, 2, "x")
        assert TOKEN not in caplog.text and "http=500" in caplog.text

    def test_formatter_masks_traceback_and_never_raises(self):
        formatter = RedactingFormatter("%(levelname)s %(message)s")
        try:
            raise RuntimeError(f"url /bot{TOKEN}/getUpdates Cookie: SPC_EC=abc; api_key=KEY123")
        except RuntimeError:
            record = logging.LogRecord("cashback_bot", logging.ERROR, __file__, 1, "fail %s", ("x",), None)
            record.exc_info = sys.exc_info()
        line = formatter.format(record)
        assert TOKEN not in line and "SPC_EC=abc" not in line and "KEY123" not in line
        assert "RuntimeError" in line  # vẫn đủ để debug

        class Bad:
            def __str__(self):
                raise ValueError("no")

        bad = logging.LogRecord("cashback_bot", logging.INFO, __file__, 1, "%s", (Bad(),), None)
        assert formatter.format(bad)  # không ném lỗi thứ cấp

    @pytest.mark.parametrize(
        ("raw", "secret"),
        [
            (f"https://api.telegram.org/bot{TOKEN}/sendMessage", TOKEN),
            ("SPC_EC=eyJhbGciOi; SPC_ST=zzz", "eyJhbGciOi"),
            ("Authorization: Bearer abc.def", "abc.def"),
            ("?api_key=SECRET1&x=1", "SECRET1"),
            ("X token=TK999 y", "TK999"),
        ],
    )
    def test_redact_patterns(self, raw, secret):
        assert secret not in redact(raw)

    def test_redact_keeps_normal_debug_info(self):
        text = "update_id=809860786 user=5967314745 http=502 price=339000 sub_id=e3HDgW9L"
        assert redact(text) == text
        assert error_brief(requests.Timeout("read timed out")) == "Timeout: read timed out"

    def test_process_logging_uses_redacting_formatter(self):
        root = logging.getLogger()
        saved = root.handlers[:]
        try:
            root.handlers = [logging.StreamHandler()]
            poller.configure_logging()
            assert all(isinstance(h.formatter, RedactingFormatter) for h in root.handlers)
        finally:
            root.handlers = saved


# --- P1-9: backup tự động, khôi phục được -------------------------------------------------------


def _live_like_db(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    return bot


class TestBackup:
    def test_scheduled_backup_restore_roundtrip(self, tmp_path):
        bot = _live_like_db(tmp_path)
        folder = tmp_path / "backups"
        check = run_scheduled_backup(bot.repo.path, folder, keep=14, now=NOW)
        assert check.link_requests == 1 and check.tables >= len(REQUIRED_TABLES)
        assert stat.S_IMODE(os.stat(check.path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
        restored = tmp_path / "restore.sqlite"
        restore_database(check.path, restored, protected=bot.repo.path)
        conn = sqlite3.connect(restored)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 1
        conn.close()
        with pytest.raises(RuntimeError):
            restore_database(check.path, bot.repo.path, protected=bot.repo.path)

    def test_corrupt_backup_detected(self, tmp_path):
        folder = tmp_path / "backups"
        folder.mkdir()
        bad = folder / "cashback-20261024T000000Z.sqlite"
        bad.write_bytes(b"not a database" * 100)
        with pytest.raises(RuntimeError):
            verify_backup(bad)
        with pytest.raises(RuntimeError):
            restore_database(bad, tmp_path / "out.sqlite")

    def test_backup_missing_tables_fails_and_leaves_no_file(self, tmp_path):
        source = tmp_path / "empty.sqlite"
        sqlite3.connect(source).execute("CREATE TABLE t (id INTEGER)").connection.commit()
        folder = tmp_path / "backups"
        with pytest.raises(RuntimeError):
            run_scheduled_backup(source, folder, keep=14, now=NOW)
        assert latest_backup(folder) is None
        assert not list(folder.glob("*.partial"))

    def test_check_backup_runs_daily_and_alerts_on_failure(self, tmp_path):
        bot = _live_like_db(tmp_path)
        folder = tmp_path / "backups"
        bot.settings = type(bot.settings)(**{**bot.settings.__dict__, "backup_dir": str(folder)})
        admin = MagicMock()
        start = NOW.timestamp()
        _check_backup(bot, bot.repo, admin, now=start)
        assert latest_backup(folder) is not None
        first = latest_backup(folder)
        _check_backup(bot, bot.repo, admin, now=start + 3600)  # chưa đủ 24h: không chạy
        assert latest_backup(folder) == first
        with patch("cashback_bot.poller.run_scheduled_backup", side_effect=OSError("disk full")):
            _check_backup(bot, bot.repo, admin, now=start + 86_400 + 1)
            admin.notify_request_failed.assert_called_once_with(error_type="backup_failed", status="BACKUP_FAILED")
            _check_backup(bot, bot.repo, admin, now=start + 86_400 + 60)  # thử lại sau 1 giờ, không spam
            assert admin.notify_request_failed.call_count == 1

    def test_backup_never_touches_live_database_file(self, tmp_path):
        bot = _live_like_db(tmp_path)
        before = os.stat(bot.repo.path).st_mtime_ns
        backup_database(bot.repo.path, tmp_path / "b", now=NOW)
        assert os.stat(bot.repo.path).st_mtime_ns == before


# --- Khoá tài chính -----------------------------------------------------------------------------


def _completed_order(bot, days_ago: int = 20, **kwargs):
    sub = _link(bot)
    complete = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _order(bot, sub, status="COMPLETED", commission=20_000, complete=complete, **kwargs)
    return sub


class TestFinancialLock:
    def test_default_is_locked_with_reasons(self, tmp_path):
        bot = _bot(tmp_path)
        settings = bot.wallet.settings()
        assert settings.enabled is False
        assert settings.locked_reasons == (REASON_SETTLEMENT, REASON_TAX)

    def test_admin_cannot_enable_wallet_even_with_old_callback(self, tmp_path):
        bot = _bot(tmp_path)
        for data in ("c:wl:on", "c:wl:on:ok"):
            reply = _callback(bot, ADMIN, data)
            assert "khoá tài chính" in reply.text
        assert bot.repo.get_state("wallet_enabled") in (None, "0")
        screen = _callback(bot, ADMIN, "c:menu:wallet")
        assert REASON_SETTLEMENT in screen.text and "🔒 Bật ví (đang khoá)" in str(screen.inline_keyboard)

    def test_direct_enable_raises(self, tmp_path):
        bot = _bot(tmp_path)
        with pytest.raises(PayoutBlocked):
            bot.wallet.set_enabled(True)
        bot.wallet.set_enabled(False)  # tắt luôn được

    def test_stored_switch_alone_does_not_open_wallet(self, tmp_path):
        bot = _bot(tmp_path)
        bot.repo.set_state("wallet_enabled", "1")  # ví như DB cũ đã bật trước hardening
        assert bot.wallet.settings().enabled is False
        home = bot.handle_text(USER, "buyer", "/start", update_id=1, now=NOW)
        assert "u:p:wallet" not in _buttons(home)

    def test_completed_plus_hold_without_evidence_stays_holding(self, tmp_path):
        bot = _bot(tmp_path)
        bot.wallet.set_hold_days(15)
        _completed_order(bot, days_ago=40)
        bot.refresh_wallet(NOW)
        entry = bot.wallet.entries(USER)[0]
        assert (entry["status"], entry["available_at"]) == ("holding", None)
        assert bot.wallet.balance(USER).withdrawable_vnd == 0

    def test_fraud_order_never_available_even_when_ready(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        bot.wallet.set_hold_days(0)
        _completed_order(bot, fraud=True)
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER)[0]["status"] == "holding"
        assert is_fraud(None) is True and is_fraud("{bad json") is True

    def test_missing_validation_month_or_unsettled_period_not_available(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot, period="2026-09")
        bot.wallet.set_hold_days(0)
        _completed_order(bot, validation="2026-10")  # kỳ 10 chưa được Shopee trả
        bot.refresh_wallet(NOW)
        assert bot.wallet.entries(USER)[0]["status"] == "holding"

    def test_settlement_only_or_tax_only_is_still_locked(self, tmp_path):
        bot = _bot(tmp_path)
        _financially_ready(bot)
        with bot.repo.connect() as conn:
            conn.execute("DELETE FROM payout_tax_policies")
        assert bot.wallet.settings().locked_reasons == (REASON_TAX,)
        with bot.repo.connect() as conn:
            conn.execute("INSERT INTO payout_tax_policies (policy_ref, approved_by, approved_at) VALUES ('x', 1, 'y')")
            conn.execute("DELETE FROM shopee_settlements")
        assert bot.wallet.settings().locked_reasons == (REASON_SETTLEMENT,)

    def test_direct_request_payout_refused_when_locked(self, tmp_path):
        bot = _bot(tmp_path)
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        assert bot.wallet.request_payout(USER, NOW) == (None, "locked")
        withdraw = _callback(bot, USER, "u:w:out:ok")
        assert "chưa mở" in (withdraw.text + (withdraw.toast or "")).lower()

    def _ready_with_request(self, tmp_path, settled: int = 10_000_000):
        bot = _bot(tmp_path)
        _financially_ready(bot, amount=settled)
        bot.wallet.set_enabled(True)
        bot.wallet.set_hold_days(0)
        _completed_order(bot)
        bot.refresh_wallet(NOW)
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
        return bot

    def test_insufficient_fund_blocks_request(self, tmp_path):
        bot = self._ready_with_request(tmp_path, settled=5_000)  # Shopee mới trả 5.000đ, khách có 14.000đ
        assert bot.wallet.balance(USER).withdrawable_vnd == 14_000
        assert bot.wallet.request_payout(USER, NOW) == (None, "fund")

    def test_paid_blocked_when_evidence_removed_but_reject_allowed(self, tmp_path):
        bot = self._ready_with_request(tmp_path)
        payout, code = bot.wallet.request_payout(USER, NOW)
        assert code == "ok"
        with bot.repo.connect() as conn:
            conn.execute("DELETE FROM payout_tax_policies")  # mất điều kiện thuế sau khi khách đã yêu cầu
        with pytest.raises(PayoutBlocked):
            bot.wallet.decide_payout(int(payout["id"]), True, ADMIN, NOW)
        reply = _callback(bot, ADMIN, f"c:wl:paid:{payout['id']}:ok")
        assert "Chưa xác nhận được" in reply.text and reply.photo is None
        assert bot.wallet.payout(int(payout["id"]))["status"] == "requested"
        rejected = bot.wallet.decide_payout(int(payout["id"]), False, ADMIN, NOW)
        assert rejected["status"] == "rejected"

    def test_paid_blocked_when_total_exceeds_settlement(self, tmp_path):
        bot = self._ready_with_request(tmp_path, settled=14_000)
        payout, code = bot.wallet.request_payout(USER, NOW)
        assert code == "ok"
        with bot.repo.connect() as conn:
            conn.execute("UPDATE shopee_settlements SET amount_vnd = 1000")  # số Shopee trả được sửa lại thấp hơn
        with pytest.raises(PayoutBlocked):
            bot.wallet.decide_payout(int(payout["id"]), True, ADMIN, NOW)

    def test_raw_sql_bypass_blocked_by_triggers(self, tmp_path):
        bot = _bot(tmp_path)
        _completed_order(bot)
        bot.refresh_wallet(NOW)
        with bot.repo.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
                conn.execute("UPDATE cashback_entries SET status = 'available'")
            with pytest.raises(sqlite3.IntegrityError, match="financial_lock"):
                conn.execute(
                    "INSERT INTO cashback_payouts (telegram_user_id, amount_vnd, status, bank_code, account_no, "
                    "account_name, created_at) VALUES (1, 1000, 'requested', 'MB', '1', 'A', 'now')"
                )

    def test_existing_history_preserved_and_tracking_still_works(self, tmp_path):
        bot = _bot(tmp_path)
        sub = _link(bot)
        _order(bot, sub)  # đơn mới, đang chờ
        bot.refresh_wallet(NOW)
        _order(bot, sub, status="COMPLETED", complete="2026-10-01T00:00:00Z")
        bot.refresh_wallet(NOW)
        with bot.repo.connect() as conn:
            rows = conn.execute("SELECT status, cashback_vnd FROM cashback_entries").fetchall()
            links = conn.execute("SELECT COUNT(*) FROM link_requests WHERE link_status = 'created'").fetchone()[0]
        assert [(r["status"], r["cashback_vnd"]) for r in rows] == [("holding", 7_000)]
        assert links == 1
        stats = _callback(bot, ADMIN, "c:menu:wallet")
        assert "Chờ duyệt: <b>7.000đ</b>" in stats.text  # admin vẫn thấy tiền chờ để đối soát

    def test_quotes_unchanged_v11_70_percent(self, tmp_path):
        bot = _bot(tmp_path)
        reply = bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=QUOTE_NOW)
        assert "<b>14.000đ</b>" in reply.text  # 20.000đ × 70%, như trước hardening
