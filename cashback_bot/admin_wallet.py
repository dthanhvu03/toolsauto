"""Màn /admin → 👛 Ví khách (PLAN-066): bật ví, cài đặt, thành viên, duyệt yêu cầu rút."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from cashback_bot.admin_ui import (
    WALLET_ADMIN_BACK,
    WALLET_ENABLE_CONFIRM,
    WALLET_ENABLE_KEYBOARD,
    payout_confirm_keyboard,
    payout_confirm_text,
    payout_keyboard,
    payout_text,
    wallet_admin_keyboard,
    wallet_admin_text,
    wallet_member_text,
    wallet_members_keyboard,
    wallet_members_text,
    wallet_settings_keyboard,
    wallet_settings_text,
)
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, payout_notice
from cashback_bot.money import format_vnd
from cashback_bot.payout_gate import PayoutBlocked
from cashback_bot.vietqr import VietQRError, build_payload, qr_png
from cashback_bot.wallet import BANKS, HOLD_DAY_CHOICES, KEY_ENABLED, MIN_WITHDRAW_CHOICES, Wallet

_PAYOUT = re.compile(r"^c:wl:(rq|paid|rej):(\d+)(:ok)?$")
_MEMBER = re.compile(r"^c:wl:u:(\d+)$")
_HOLD = re.compile(r"^c:wl:hold:(\d+)$")
_MIN = re.compile(r"^c:wl:min:(\d+)$")

# (admin, action, trước, sau, lúc): ghi vào admin_change_audit để màn 📊 Lịch sử thấy.
AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


class WalletAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.wallet = Wallet(repo)
        self.audit = audit

    def _log(self, admin_id: int, action: str, before: dict | None, after: dict | None, now: datetime) -> None:
        if self.audit is not None and before != after:
            self.audit(admin_id, action, before, after, now)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == "c:menu:wallet":
            return self.screen()
        if data in ("c:wl:on", "c:wl:on:ok") and self.wallet.settings().locked_reasons:
            # Khoá tài chính (hardening V1): nút cũ hay callback gõ tay đều không bật được.
            return self.screen("🔒 Chưa bật được ví: còn khoá tài chính (xem lý do bên dưới).")
        if data == "c:wl:on":
            return BotReply(WALLET_ENABLE_CONFIRM, inline_keyboard=WALLET_ENABLE_KEYBOARD)
        if data == "c:wl:on:ok":
            try:
                self.wallet.set_enabled(True)
            except PayoutBlocked:
                return self.screen("🔒 Chưa bật được ví: còn khoá tài chính (xem lý do bên dưới).")
            self._log(admin_id, "wallet_enabled", {"on": False}, {"on": True}, now)
            return self.screen("🟢 Đã bật ví. Khách thấy nút 👛 Ví của tôi từ tin kế tiếp.")
        if data == "c:wl:off":
            before = self.repo.get_state(KEY_ENABLED) == "1"  # công tắc đã lưu, không phải trạng thái hiệu lực
            self._log(admin_id, "wallet_enabled", {"on": before}, {"on": False}, now)
            self.wallet.set_enabled(False)
            return self.screen("⏸️ Đã tắt ví. Yêu cầu rút đang chờ vẫn xử lý được ở đây.")
        if data == "c:wl:cfg":
            return self._settings()
        hold = _HOLD.fullmatch(data)
        if hold and int(hold.group(1)) in HOLD_DAY_CHOICES:
            days = int(hold.group(1))
            self._log(admin_id, "wallet_hold_days", {"days": self.wallet.settings().hold_days}, {"days": days}, now)
            self.wallet.set_hold_days(days)
            return self._settings()
        low = _MIN.fullmatch(data)
        if low and int(low.group(1)) in MIN_WITHDRAW_CHOICES:
            amount = int(low.group(1))
            before = {"vnd": self.wallet.settings().min_withdraw_vnd}
            self._log(admin_id, "wallet_min_withdraw", before, {"vnd": amount}, now)
            self.wallet.set_min_withdraw(amount)
            return self._settings()
        if data == "c:wl:members":
            members = self.wallet.members()
            return BotReply(wallet_members_text(members), inline_keyboard=wallet_members_keyboard(members))
        member = _MEMBER.fullmatch(data)
        if member:
            return self._member(int(member.group(1)))
        payout = _PAYOUT.fullmatch(data)
        if payout:
            return self._payout(admin_id, payout.group(1), int(payout.group(2)), bool(payout.group(3)), now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(WALLET_ADMIN_BACK,))

    def screen(self, notice: str = "") -> BotReply:
        settings = self.wallet.settings()
        requests = self.wallet.open_requests()
        return BotReply(
            wallet_admin_text(settings, self.wallet.totals(), requests, notice),
            inline_keyboard=wallet_admin_keyboard(settings, requests),
        )

    def _settings(self) -> BotReply:
        settings = self.wallet.settings()
        return BotReply(
            wallet_settings_text(settings),
            inline_keyboard=wallet_settings_keyboard(settings, HOLD_DAY_CHOICES, MIN_WITHDRAW_CHOICES),
        )

    def _member(self, user_id: int) -> BotReply:
        user = self.repo.get_user(user_id)
        text = wallet_member_text(
            user_id,
            None if user is None else user["username"],
            self.wallet.balance(user_id),
            self.wallet.entries(user_id, limit=10),
            self.wallet.bank(user_id),
        )
        return BotReply(text, inline_keyboard=((("◀️ Thành viên", "c:wl:members"),), WALLET_ADMIN_BACK))

    def _payout(self, admin_id: int, action: str, payout_id: int, confirmed: bool, now: datetime) -> BotReply:
        row = self.wallet.payout(payout_id)
        if row is None:
            return self.screen("Không tìm thấy yêu cầu này.")
        if action == "rq":
            return self._payout_detail(row)
        paid = action == "paid"
        if row["status"] != "requested":
            return self._payout_detail(row, "Yêu cầu này đã được xử lý trước đó.")
        if not confirmed:
            return BotReply(payout_confirm_text(row, paid), inline_keyboard=payout_confirm_keyboard(row, paid))
        try:
            decided = self.wallet.decide_payout(payout_id, paid, admin_id, now)
        except PayoutBlocked as exc:
            return self._payout_detail(row, f"🔒 Chưa xác nhận được: {exc.reason}")
        if decided is None:
            return self._payout_detail(row, "Yêu cầu này đã được xử lý trước đó.")
        self.repo.enqueue_admin_event(
            event_key=f"payout_{'paid' if paid else 'rejected'}:{payout_id}",
            event_type="PAYOUT_DECIDED",
            chat_id=int(decided["telegram_user_id"]),
            message_html=payout_notice(decided, paid),
        )
        return self.screen("✅ Đã ghi nhận chuyển khoản, bot báo khách." if paid else "✖️ Đã từ chối, tiền trở lại ví khách.")

    def _payout_detail(self, row, notice: str = "") -> BotReply:
        user = self.repo.get_user(int(row["telegram_user_id"]))
        locked = self.wallet.settings().locked_reasons
        if row["status"] != "requested":
            photo, qr_problem = None, None
        elif locked:
            # Không đưa mã chuyển khoản khi còn khoá: tránh chuyển tay khoản Shopee chưa trả.
            photo, qr_problem = None, "Không tạo mã QR khi còn khoá tài chính."
        else:
            photo, qr_problem = self._qr(row)
        text = payout_text(
            row,
            None if user is None else user["username"],
            self.wallet.balance(int(row["telegram_user_id"])),
            BANKS.get(row["bank_code"], ("", row["bank_code"]))[1],
            notice,
            qr_sent=photo is not None,
            qr_problem=qr_problem,
        )
        return BotReply(text, inline_keyboard=payout_keyboard(row), photo=photo)

    def _qr(self, row) -> tuple[tuple[str, bytes, str] | None, str | None]:
        """Ảnh QR tự tạo (không gửi thông tin khách ra ngoài). Lỗi thì trả lý do để admin chuyển tay."""
        bank = BANKS.get(row["bank_code"])
        if bank is None:
            return None, f"Ngân hàng {row['bank_code']} không còn trong danh sách hỗ trợ."
        try:
            payload = build_payload(bank[0], row["account_no"], int(row["amount_vnd"]), row["transfer_note"] or "")
        except VietQRError as exc:
            return None, f"Không tạo được mã QR: {exc}."
        image = qr_png(payload)
        if image is None:
            return None, "Máy chủ chưa vẽ được ảnh QR."
        caption = f"{row['transfer_note']} · {format_vnd(int(row['amount_vnd']))} · {bank[1]} ••••{row['account_no'][-4:]}"
        return (f"qr-{row['transfer_note'] or row['id']}.png".replace(" ", "-"), image, caption), None
