"""Admin activity notifications for cashback bot.

Queue in SQLite first, then deliver best-effort to avoid breaking customer flow.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from cashback_bot.db import TrackingRepository
from cashback_bot.messages import buyer_name
from cashback_bot.money import format_vnd
from cashback_bot.telegram_api import TelegramApi, TelegramDeliveryError

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
# Sự kiện thường ngày gửi im lặng; lỗi vẫn kêu chuông.
SILENT_EVENTS = {"NEW_USER", "LINK_SENT"}


def _vn_now_text() -> str:
    return datetime.now(timezone.utc).astimezone(ICT).strftime("%H:%M · %d/%m")


def _who(telegram_user_id: int, username: str | None) -> str:
    """Tiêu đề hiện @username; chưa có username thì hiện ID."""
    if username:
        return f"@{html.escape(username)}"
    return f"<code>{telegram_user_id}</code>"


def _details(*lines: str) -> str:
    """Mã kỹ thuật gom vào khối thu gọn, bấm mới mở."""
    return "<blockquote expandable>" + "\n".join(lines) + "</blockquote>"


# Trạng thái đơn Shopee hay gặp; giá trị lạ thì hiện nguyên văn.
_SHOPEE_STATUS = {
    "PENDING": "Chờ duyệt",
    "COMPLETED": "Hoàn thành",
    "CANCELLED": "Đã huỷ",
    "CANCELED": "Đã huỷ",
}


@dataclass
class AdminNotifier:
    repo: TrackingRepository
    telegram: TelegramApi
    enabled: bool
    chat_id: int | None
    fail_cooldown_sec: int = 60

    def _active(self) -> bool:
        return self.enabled and self.chat_id is not None

    def notify_new_user(self, telegram_user_id: int, username: str | None) -> None:
        if not self._active():
            return
        total = self.repo.count_users()
        body = (
            f"🆕 <b>Người dùng mới</b> · {_who(telegram_user_id, username)}\n\n"
            f"👥 Tổng: <b>{total}</b> người dùng\n"
            f"🕓 {_vn_now_text()}\n"
            + _details(f"User <code>{telegram_user_id}</code>")
        )
        self.repo.enqueue_admin_event(
            event_key=f"new_user:{telegram_user_id}",
            event_type="NEW_USER",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_link_sent(self, update_id: int) -> None:
        if not self._active():
            return
        row = self.repo.get_by_update_id(update_id)
        if row is None or row.sub_id is None or row.link_status != "created":
            return
        user = self.repo.get_user(row.telegram_user_id)
        username = None if user is None else user["username"]
        body = (
            f"🔗 <b>Đã gửi link</b> · {_who(row.telegram_user_id, username)}\n\n"
            f"🛍️ {html.escape(buyer_name(row.product_name or '-'))}\n"
            f"💰 Giá {format_vnd(row.price_vnd or 0)} · Hoàn <b>{format_vnd(row.estimated_cashback or 0)}</b>\n"
            f"🕓 {_vn_now_text()}\n"
            + _details(
                f"User <code>{row.telegram_user_id}</code>",
                f"Item <code>{row.item_id or '-'}</code>",
                f"Sub <code>{row.sub_id}</code>",
                f"Update <code>{update_id}</code>",
            )
        )
        self.repo.enqueue_admin_event(
            event_key=f"link_sent:{update_id}",
            event_type="LINK_SENT",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_request_failed(
        self,
        error_type: str,
        update_id: int | None = None,
        telegram_user_id: int | None = None,
        status: str = "FAILED",
    ) -> None:
        if not self._active():
            return
        # Anti-spam: same error type max 1 notification / minute.
        key = f"admin_fail_last:{error_type}"
        now = datetime.now(timezone.utc).timestamp()
        prev = self.repo.get_state(key)
        if prev:
            try:
                if now - float(prev) < self.fail_cooldown_sec:
                    return
            except ValueError:
                pass
        self.repo.set_state(key, str(now))

        body = (
            "⚠️ <b>Lỗi bot</b>\n\n"
            f"❌ <code>{html.escape(error_type)}</code>\n"
            f"📌 Trạng thái: <b>{html.escape(status)}</b>\n"
            f"🕓 {_vn_now_text()}\n"
            + _details(
                f"Update <code>{'-' if update_id is None else update_id}</code>",
                f"User <code>{'-' if telegram_user_id is None else telegram_user_id}</code>",
            )
        )
        self.repo.enqueue_admin_event(
            event_key=f"request_failed:{error_type}:{update_id or 0}:{telegram_user_id or 0}",
            event_type="REQUEST_FAILED",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_shopee_new_order(
        self,
        order_sn: str,
        sub_id: str,
        telegram_user_id: int | None,
        username: str | None = None,
        commission_vnd: int | None = None,
        order_status: str | None = None,
    ) -> None:
        if not self._active():
            return
        comm_text = format_vnd(commission_vnd) if commission_vnd is not None else "Đang cập nhật"
        status_text = html.escape(_SHOPEE_STATUS.get((order_status or "").upper(), order_status or "Chờ duyệt"))
        who = _who(telegram_user_id or 0, username) if telegram_user_id else "Chưa xác định"
        body = (
            "🎉 <b>Có đơn Shopee mới qua bot!</b>\n\n"
            f"📦 Đơn hàng: <code>{html.escape(order_sn)}</code>\n"
            f"🏷️ Sub ID: <code>{html.escape(sub_id)}</code>\n"
            f"👤 Người tạo link: {who}\n"
            f"💵 Hoa hồng Shopee: <b>{comm_text}</b>\n"
            f"📌 Trạng thái: <b>{status_text}</b>\n"
            f"🕓 {_vn_now_text()}"
        )
        self.repo.enqueue_admin_event(
            event_key=f"shopee_new_order:{order_sn}",
            event_type="SHOPEE_ORDER",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_shopee_cookie_expired(self, reason: str = "") -> None:
        if not self._active():
            return
        body = (
            "⚠️ <b>Cookie Shopee Affiliate đã hết hạn!</b>\n\n"
            "Shopee từ chối xác thực phiên đăng nhập hiện tại.\n"
            f"Lý do: <i>{html.escape(reason or 'Hết hạn phiên')}</i>\n\n"
            "👉 Vui lòng vào /admin → <b>🔗 Shopee Affiliate</b> → <b>🔑 Cập nhật Cookie</b> để dán lại cookie mới."
        )
        self.repo.enqueue_admin_event(
            event_key=f"shopee_cookie_expired:{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H')}",
            event_type="COOKIE_EXPIRED",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def flush_pending(self, limit: int = 10) -> None:
        if not self._active():
            return
        rows = self.repo.list_pending_admin_events(limit=limit, max_attempts=5)
        for row in rows:
            try:
                self.telegram.send_message(
                    int(row["chat_id"]),
                    str(row["message_html"]),
                    disable_notification=row["event_type"] in SILENT_EVENTS,
                )
            except (requests.RequestException, TelegramDeliveryError) as exc:
                self.repo.mark_admin_event_failed(int(row["id"]), type(exc).__name__)
                continue
            self.repo.mark_admin_event_sent(int(row["id"]))

