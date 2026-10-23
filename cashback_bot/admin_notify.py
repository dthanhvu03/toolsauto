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
from cashback_bot.money import format_vnd
from cashback_bot.telegram_api import TelegramApi

ICT = ZoneInfo("Asia/Ho_Chi_Minh")


def _vn_now_text() -> str:
    return datetime.now(timezone.utc).astimezone(ICT).strftime("%d/%m/%Y %H:%M:%S")


def _short_name(name: str | None, limit: int = 80) -> str:
    text = " ".join((name or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip(" ,.-") + "…"


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
        safe_user = html.escape(username or "-")
        body = (
            "🆕 <b>NEW_USER</b>\n"
            f"User ID: <code>{telegram_user_id}</code>\n"
            f"Username: <code>{safe_user}</code>\n"
            f"Tổng user: <b>{total}</b>\n"
            f"Thời gian (VN): <code>{_vn_now_text()}</code>"
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
        username = "-" if user is None else (user["username"] or "-")
        body = (
            "✅ <b>LINK_SENT</b>\n"
            f"User ID: <code>{row.telegram_user_id}</code>\n"
            f"Username: <code>{html.escape(username)}</code>\n"
            f"Sản phẩm: {html.escape(_short_name(row.product_name))}\n"
            f"Item ID: <code>{row.item_id or '-'}</code>\n"
            f"Giá tham khảo: <b>{format_vnd(row.price_vnd or 0)}</b>\n"
            f"Estimated cashback: <b>{format_vnd(row.estimated_cashback or 0)}</b>\n"
            f"Sub ID: <code>{row.sub_id}</code>\n"
            f"Update ID: <code>{update_id}</code>\n"
            f"Thời gian (VN): <code>{_vn_now_text()}</code>\n"
            "Trạng thái: <b>Đã gửi link</b>"
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
            "⚠️ <b>REQUEST_FAILED</b>\n"
            f"Error: <code>{html.escape(error_type)}</code>\n"
            f"Update ID: <code>{'-' if update_id is None else update_id}</code>\n"
            f"User ID: <code>{'-' if telegram_user_id is None else telegram_user_id}</code>\n"
            f"Thời gian (VN): <code>{_vn_now_text()}</code>\n"
            f"Trạng thái: <b>{html.escape(status)}</b>"
        )
        self.repo.enqueue_admin_event(
            event_key=f"request_failed:{error_type}:{update_id or 0}:{telegram_user_id or 0}",
            event_type="REQUEST_FAILED",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def flush_pending(self, limit: int = 10) -> None:
        if not self._active():
            return
        rows = self.repo.list_pending_admin_events(limit=limit, max_attempts=5)
        for row in rows:
            try:
                self.telegram.send_message(int(row["chat_id"]), str(row["message_html"]))
            except requests.RequestException as exc:
                self.repo.mark_admin_event_failed(int(row["id"]), type(exc).__name__)
                continue
            self.repo.mark_admin_event_sent(int(row["id"]))

