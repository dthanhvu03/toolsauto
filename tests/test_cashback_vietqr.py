"""PLAN-066: VietQR tự tạo, chọn ngân hàng bằng nút, các trường hợp ngoại lệ khi chi trả."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import cashback_bot.vietqr as vietqr
from cashback_bot.poller import process_updates
from cashback_bot.vietqr import VietQRError, build_payload, clean_note, crc16_ccitt, parse_tlv, qr_png
from cashback_bot.wallet import BANKS, BankAccount, parse_bank_text
from tests.test_cashback_bot import NOW
from tests.test_cashback_wallet import (
    ADMIN,
    USER,
    _bot,
    _buttons,
    _callback,
    _customer_events,
    _financially_ready,
    _link,
    _order,
    _verify_bank,
)

PNG = b"\x89PNG\r\n\x1a\n"


def _ready(tmp_path, commission=20_000, bank=True):
    bot = _bot(tmp_path, admin_notifications_enabled=True, admin_chat_id=ADMIN)
    bot.admin_notifier = MagicMock()
    _financially_ready(bot)
    bot.wallet.set_enabled(True)
    bot.wallet.set_hold_days(0)
    sub = _link(bot)
    _order(bot, sub, status="COMPLETED", commission=commission, complete="2026-10-21T10:00:00Z", approved=True)
    bot.refresh_wallet(datetime(2026, 10, 21, 11, tzinfo=timezone.utc))
    if bank:
        bot.wallet.save_bank(USER, BankAccount("MB", "0123456789", "NGUYEN VAN A"), NOW)
    return bot


def _requested(tmp_path, **kwargs):
    bot = _ready(tmp_path, **kwargs)
    assert "Đã gửi yêu cầu rút" in _callback(bot, USER, "u:w:out:ok").text
    return bot


_CODES = {"under_review": "rv", "approved_for_payment": "ap", "processing": "pr", "sent_unconfirmed": "se",
          "paid_confirmed": "pd", "rejected": "rj", "failed": "fl", "needs_review": "nr"}


def _step(bot, pid: int, target: str, text: str | None = None):
    """Admin bấm một bước (hỏi lại → xác nhận), gõ lý do / chứng từ nếu bước cần (PLAN-078)."""
    version = int(bot.wallet.payout(pid)["version"])
    _callback(bot, ADMIN, f"c:wl:mv:{pid}:{version}:{_CODES[target]}")
    reply = _callback(bot, ADMIN, f"c:wl:mv:{pid}:{version}:{_CODES[target]}:ok")
    if text is not None:
        reply = bot.handle_text(ADMIN, "admin", text, update_id=900 + version, now=NOW)
    return reply


def _processing(tmp_path, **kwargs):
    bot = _requested(tmp_path, **kwargs)
    _verify_bank(bot)
    for target in ("under_review", "approved_for_payment", "processing"):
        _step(bot, 1, target)
    assert bot.wallet.payout(1)["status"] == "processing"
    return bot


def _paid(bot, pid: int = 1):
    _step(bot, pid, "sent_unconfirmed")
    return _step(bot, pid, "paid_confirmed", "FT26102499999")


# --- Chuỗi VietQR ------------------------------------------------------------


class TestPayload:
    def test_crc_matches_standard_check_value(self):
        assert crc16_ccitt("123456789") == "29B1"

    def test_payload_fields_follow_napas(self):
        payload = build_payload("970422", "0123456789", 14_000, "Hoan tien 000001")
        top = parse_tlv(payload)
        assert (top["00"], top["01"], top["53"], top["54"], top["58"]) == ("01", "12", "704", "14000", "VN")
        merchant = parse_tlv(top["38"])
        assert merchant["00"] == "A000000727" and merchant["02"] == "QRIBFTTA"
        assert parse_tlv(merchant["01"]) == {"00": "970422", "01": "0123456789"}
        assert parse_tlv(top["62"]) == {"08": "Hoan tien 000001"}
        assert payload[-8:-4] == "6304"
        assert top["63"] == crc16_ccitt(payload[:-4])

    def test_any_changed_char_breaks_crc(self):
        payload = build_payload("970422", "0123456789", 14_000, "Hoan tien 000001")
        tampered = payload.replace("14000", "94000")
        assert crc16_ccitt(tampered[:-4]) != tampered[-4:]

    @pytest.mark.parametrize("amount", [0, -1, 10_000_000_000_000, 14_000.5, True, "14000", None])
    def test_bad_amount_rejected(self, amount):
        with pytest.raises(VietQRError):
            build_payload("970422", "0123456789", amount, "x")

    @pytest.mark.parametrize("bin_code", ["", "97042", "9704222", "97042A", None])
    def test_bad_bin_rejected(self, bin_code):
        with pytest.raises(VietQRError):
            build_payload(bin_code, "0123456789", 14_000, "x")

    @pytest.mark.parametrize("account", ["", "0123 456", "1" * 20, "0123-456", None])
    def test_bad_account_rejected(self, account):
        with pytest.raises(VietQRError):
            build_payload("970422", account, 14_000, "x")

    def test_largest_amount_still_fits(self):
        assert parse_tlv(build_payload("970422", "1", 9_999_999_999_999, ""))["54"] == "9999999999999"

    def test_note_is_ascii_short_and_optional(self):
        assert clean_note("Hoàn tiền #000001 — Đức!") == "Hoan tien 000001 Duc"
        assert len(clean_note("a" * 80)) == 25
        assert "62" not in parse_tlv(build_payload("970422", "0123456789", 1_000, "!!!"))

    def test_tag_longer_than_99_rejected(self):
        with pytest.raises(VietQRError):
            vietqr._tlv("62", "x" * 100)

    def test_png_and_fallbacks(self, monkeypatch):
        assert qr_png(build_payload("970422", "0123456789", 14_000, "a"))[:8] == PNG
        monkeypatch.setattr(vietqr, "qrcode", None)
        assert qr_png("abc") is None

    def test_png_draw_error_returns_none(self, monkeypatch):
        broken = MagicMock()
        broken.make.side_effect = RuntimeError("boom")
        monkeypatch.setattr(vietqr, "qrcode", broken)
        assert qr_png("abc") is None


# --- Khai ngân hàng ----------------------------------------------------------


class TestBankInput:
    @pytest.mark.parametrize(
        "text, chosen, expected",
        [
            ("0123456789 Nguyễn Văn Đức", "MB", BankAccount("MB", "0123456789", "NGUYEN VAN DUC")),
            ("0123 456 789 tran thi b", "VCB", BankAccount("VCB", "0123456789", "TRAN THI B")),
            ("0123.456-789 Le C", "TCB", BankAccount("TCB", "0123456789", "LE C")),
            ("ACB 0123456789 Le Van C", "MB", BankAccount("ACB", "0123456789", "LE VAN C")),  # gõ mã khác thì theo mã gõ
            ("cake 0123456789 Pham D", None, BankAccount("CAKE", "0123456789", "PHAM D")),
            ("Nguyen Van A", "MB", "account"),
            ("0123456789", "MB", "format"),
            ("12345 Nguyen Van A", "MB", "account"),  # 5 số
            ("1" * 20 + " Nguyen Van A", "MB", "account"),
            ("0123456789 Nguyen Van 2", "MB", "name"),
            ("0123456789 AB", "MB", "name"),  # quá ngắn
            ("0123456789 " + "A" * 51, "MB", "name"),
            ("0123456789 Nguyen 🙂", "MB", "name"),
            ("0123456789 Nguyen", None, "bank"),
            ("", "MB", "format"),
        ],
    )
    def test_parse_cases(self, text, chosen, expected):
        assert parse_bank_text(text, chosen) == expected

    def test_picker_lists_every_bank_and_rejects_unknown(self, tmp_path):
        bot = _ready(tmp_path, bank=False)
        picker = _callback(bot, USER, "u:w:bank")
        assert {f"u:w:bk:{code}" for code in BANKS} <= set(_buttons(picker))
        unknown = _callback(bot, USER, "u:w:bk:XYZ")
        assert "chưa hỗ trợ" in unknown.text
        assert bot._bank_waiting(USER) is None

    def test_wrong_input_keeps_waiting_then_retry_saves(self, tmp_path):
        bot = _ready(tmp_path, bank=False)
        _callback(bot, USER, "u:w:bk:VCB")
        first = bot.handle_text(USER, "buyer", "Nguyen Van A", update_id=2, now=NOW)
        assert "Số tài khoản chỉ gồm" in first.text and "Vietcombank" in first.text
        second = bot.handle_text(USER, "buyer", "0011002233 Nguyen Van A", update_id=3, now=NOW)
        assert "Đã lưu tài khoản Vietcombank ••••2233" in second.text
        assert bot._bank_waiting(USER) is None

    def test_other_button_or_command_cancels_waiting(self, tmp_path):
        bot = _ready(tmp_path, bank=False)
        _callback(bot, USER, "u:w:bk:MB")
        _callback(bot, USER, "u:p:home")
        assert bot._bank_waiting(USER) is None
        _callback(bot, USER, "u:w:bk:MB")
        _callback(bot, USER, "u:w:bank")  # 🔁 Chọn ngân hàng khác
        assert bot._bank_waiting(USER) is None

    def test_shopee_link_while_waiting_creates_buy_link(self, tmp_path):
        bot = _ready(tmp_path, bank=False)
        _callback(bot, USER, "u:w:bk:MB")
        reply = bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=40, now=NOW)
        assert reply.button_url and "an_redir" in reply.button_url
        assert bot._bank_waiting(USER) is None
        assert bot.wallet.bank(USER) is None

    def test_wallet_turned_off_while_waiting(self, tmp_path):
        bot = _ready(tmp_path, bank=False)
        _callback(bot, USER, "u:w:bk:MB")
        bot.wallet.set_enabled(False)
        reply = bot.handle_text(USER, "buyer", "0123456789 Nguyen Van A", update_id=41, now=NOW)
        assert "Đã lưu tài khoản" not in reply.text
        assert bot.wallet.bank(USER) is None
        assert "Ví hoàn tiền chưa mở" in _callback(bot, USER, "u:w:bk:MB").toast

    def test_bank_change_after_request_keeps_old_account_on_payout(self, tmp_path):
        bot = _requested(tmp_path)
        bot.wallet.save_bank(USER, BankAccount("VCB", "9999999999", "NGUYEN VAN A"), NOW)
        payout = bot.wallet.payout(1)
        assert (payout["bank_code"], payout["account_no"]) == ("MB", "0123456789")
        assert payout["status"] == "needs_review", "không âm thầm đổi đích chuyển"
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert "••••6789" in detail.text and "9999" not in detail.text and detail.photo is None


# --- Duyệt rút và ảnh QR -------------------------------------------------------


class TestPayoutQR:
    def test_requested_payout_sends_qr_photo(self, tmp_path):
        bot = _requested(tmp_path)
        early = _callback(bot, ADMIN, "c:wl:rq:1")
        assert early.photo is None and "0123456789" not in early.text, "chưa tới bước chuyển: không QR, số che"
        bot = _processing(tmp_path / "p")
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        name, image, caption = detail.photo
        assert name == "qr-Hoan-tien-000001.png" and image[:8] == PNG
        assert caption == "Hoan tien 000001 · 14.000đ · MB Bank ••••6789"
        assert "Kiểm tên người nhận" in detail.text and "Mã QR không chứng minh đã chuyển tiền" in detail.text
        assert "<code>0123456789</code>" in detail.text

    def test_paid_payout_shows_no_qr(self, tmp_path):
        bot = _processing(tmp_path)
        _paid(bot)
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert detail.photo is None
        assert "Ảnh mã QR" not in detail.text and "✅ Đã trả (có chứng từ)" in detail.text
        assert "FT26102499999" in detail.text

    def test_unsupported_bank_on_old_payout_falls_back_to_text(self, tmp_path):
        bot = _processing(tmp_path)
        with bot.repo.connect() as conn:
            conn.execute("UPDATE cashback_payouts SET bank_code = 'OLD' WHERE id = 1")
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert detail.photo is None
        assert "không còn trong danh sách hỗ trợ" in detail.text and "<code>0123456789</code>" in detail.text

    def test_corrupt_account_falls_back_to_text(self, tmp_path):
        bot = _processing(tmp_path)
        with bot.repo.connect() as conn:
            conn.execute("UPDATE cashback_payouts SET account_no = '01 23' WHERE id = 1")
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert detail.photo is None and "Không tạo được mã QR" in detail.text

    def test_qr_library_missing_falls_back_to_text(self, tmp_path, monkeypatch):
        bot = _processing(tmp_path)
        monkeypatch.setattr(vietqr, "qrcode", None)
        detail = _callback(bot, ADMIN, "c:wl:rq:1")
        assert detail.photo is None and "chưa vẽ được ảnh QR" in detail.text

    def test_photo_send_failure_does_not_block_text(self, tmp_path):
        bot = _processing(tmp_path)
        telegram = MagicMock()
        telegram.send_photo.side_effect = RuntimeError("telegram down")
        update = {"update_id": 77, "callback_query": {
            "id": "q", "from": {"id": ADMIN}, "data": "c:wl:rq:1",
            "message": {"message_id": 5, "chat": {"type": "private", "id": ADMIN}},
        }}
        process_updates(bot, telegram, bot.repo, [update], MagicMock(), now=NOW)
        assert telegram.send_photo.called
        assert bot.repo.get_outbound(77) is not None  # tin chữ vẫn được xếp gửi

    def test_reject_then_paid_is_refused(self, tmp_path):
        bot = _requested(tmp_path)
        _step(bot, 1, "rejected", "Sai tên chủ tài khoản")
        assert bot.wallet.payout(1)["status"] == "rejected"
        version = int(bot.wallet.payout(1)["version"])
        for code in ("pd", "ap", "pr"):
            assert "Không chuyển được" in _callback(bot, ADMIN, f"c:wl:mv:1:{version}:{code}:ok").text
        assert "Nút đã cũ" in _callback(bot, ADMIN, "c:wl:mv:1:1:rv:ok").text
        assert bot.wallet.payout(1)["status"] == "rejected"
        assert "Lý do: Sai tên chủ tài khoản" in _customer_events(bot)[-1]

    def test_unknown_or_malformed_payout_buttons(self, tmp_path):
        bot = _requested(tmp_path)
        assert "Không tìm thấy" in _callback(bot, ADMIN, "c:wl:rq:999").text
        assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:wl:rq:abc").text

    def test_customer_cannot_open_or_pay_request(self, tmp_path):
        bot = _requested(tmp_path)
        assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:wl:paid:1:ok").text
        assert bot.wallet.payout(1)["status"] == "requested"

    def test_balance_drops_between_confirm_and_ok(self, tmp_path):
        bot = _ready(tmp_path)
        assert "Xác nhận rút tiền" in _callback(bot, USER, "u:w:out").text
        with bot.repo.connect() as conn:
            conn.execute("UPDATE cashback_entries SET status = 'cancelled'")
        assert "Chưa đủ số tối thiểu" in _callback(bot, USER, "u:w:out:ok").text
        assert bot.wallet.payout(1) is None

    def test_wallet_disabled_between_confirm_and_ok(self, tmp_path):
        bot = _ready(tmp_path)
        _callback(bot, USER, "u:w:out")
        bot.wallet.set_enabled(False)
        assert "Ví hoàn tiền chưa mở" in _callback(bot, USER, "u:w:out:ok").toast
        assert bot.wallet.payout(1) is None

    def test_notes_are_unique_per_request(self, tmp_path):
        bot = _processing(tmp_path)
        _paid(bot)
        sub = _link(bot)
        _order(bot, sub, status="COMPLETED", commission=30_000, complete="2026-10-21T10:00:00Z", cid="o2", approved=True)
        bot.refresh_wallet(datetime(2026, 10, 21, 12, tzinfo=timezone.utc))
        _callback(bot, USER, "u:w:out:ok")
        assert bot.wallet.payout(2)["transfer_note"] == "Hoan tien 000002"
        for target in ("under_review", "approved_for_payment", "processing"):
            _step(bot, 2, target)
        assert "Hoan tien 000002" in _callback(bot, ADMIN, "c:wl:rq:2").photo[2]

    def test_customer_told_once_when_paid(self, tmp_path):
        bot = _processing(tmp_path)
        _paid(bot)
        _callback(bot, ADMIN, "c:wl:mv:1:5:pd:ok")  # bấm lại nút cũ
        _callback(bot, ADMIN, "c:wl:mv:1:6:pd:ok")
        assert bot.wallet.payout(1)["status"] == "paid_confirmed"
        assert sum("Đã chuyển tiền hoàn" in e for e in _customer_events(bot)) == 1
