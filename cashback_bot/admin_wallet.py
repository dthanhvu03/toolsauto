"""Màn /admin → 👛 Ví khách (PLAN-066): bật ví, cài đặt, thành viên, duyệt yêu cầu rút."""

from __future__ import annotations

import re
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
from cashback_bot.wallet import BANKS, HOLD_DAY_CHOICES, MIN_WITHDRAW_CHOICES, Wallet, vietqr_url

_PAYOUT = re.compile(r"^c:wl:(rq|paid|rej):(\d+)(:ok)?$")
_MEMBER = re.compile(r"^c:wl:u:(\d+)$")
_HOLD = re.compile(r"^c:wl:hold:(\d+)$")
_MIN = re.compile(r"^c:wl:min:(\d+)$")


class WalletAdmin:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo
        self.wallet = Wallet(repo)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == "c:menu:wallet":
            return self.screen()
        if data == "c:wl:on":
            return BotReply(WALLET_ENABLE_CONFIRM, inline_keyboard=WALLET_ENABLE_KEYBOARD)
        if data == "c:wl:on:ok":
            self.wallet.set_enabled(True)
            return self.screen("🟢 Đã bật ví. Khách thấy nút 👛 Ví của tôi từ tin kế tiếp.")
        if data == "c:wl:off":
            self.wallet.set_enabled(False)
            return self.screen("⏸️ Đã tắt ví. Yêu cầu rút đang chờ vẫn xử lý được ở đây.")
        if data == "c:wl:cfg":
            return self._settings()
        hold = _HOLD.fullmatch(data)
        if hold and int(hold.group(1)) in HOLD_DAY_CHOICES:
            self.wallet.set_hold_days(int(hold.group(1)))
            return self._settings()
        low = _MIN.fullmatch(data)
        if low and int(low.group(1)) in MIN_WITHDRAW_CHOICES:
            self.wallet.set_min_withdraw(int(low.group(1)))
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
        decided = self.wallet.decide_payout(payout_id, paid, admin_id, now)
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
        qr = vietqr_url(
            row["bank_code"], row["account_no"], row["account_name"], int(row["amount_vnd"]), row["transfer_note"] or ""
        )
        text = payout_text(
            row,
            None if user is None else user["username"],
            self.wallet.balance(int(row["telegram_user_id"])),
            qr,
            BANKS.get(row["bank_code"], ("", row["bank_code"]))[1],
            notice,
        )
        return BotReply(text, inline_keyboard=payout_keyboard(row))
