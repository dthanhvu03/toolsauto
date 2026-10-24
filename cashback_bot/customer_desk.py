"""Phía khách của điều khoản và hỗ trợ (PLAN-077): /dieukien, /hotro, nút u:t:* và u:h:*.

Chờ khách gõ nội dung ticket lưu ở bot_state (`support_waiting:<user>`), hết hạn sau 15 phút.
Không đụng tiền, sổ ví hay trạng thái hoa hồng. Không gửi tin cho khách khác; ticket chỉ hiện cho chủ ticket.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from cashback_bot import customer_orders, support, terms
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import (
    DIEUKIEN,
    SUPPORT_ASK,
    SUPPORT_CLOSED,
    SUPPORT_EMPTY,
    SUPPORT_REPLY_ASK,
    ORDERS_EMPTY,
    TERMS_REQUIRED,
    BotReply,
    notify_settings_reply,
    order_detail_reply,
    orders_summary_reply,
    page_reply,
    support_created_reply,
    support_home_reply,
    support_list_reply,
    support_prompt_reply,
    support_ticket_reply,
    terms_home_reply,
    terms_section_reply,
)

if TYPE_CHECKING:
    from cashback_bot.admin_notify import AdminNotifier

logger = logging.getLogger("cashback_bot")

WAIT_TTL = timedelta(minutes=15)
_TICKET = re.compile(r"^u:h:(t|r):(\d{1,9})$")
_CATEGORY = re.compile(r"^u:h:c:([a-z_]{2,16})$")
_SECTION = re.compile(r"^u:t:s:([a-z_]{2,24})$")
_ACCEPT = re.compile(r"^u:t:ok:(\d{1,9})$")
_ORDER_PAGE = re.compile(r"^u:o:l:(\d{1,4})$")
_ORDER = re.compile(r"^u:o:d:([0-9A-Za-z_-]{1,48})$")
_NOTIFY = re.compile(r"^u:n:t:(orders|updates|support|wallet)$")


class CustomerDesk:
    def __init__(self, repo: TrackingRepository, admin_notifier: "AdminNotifier | None" = None, terms_required: bool = False,
                 orders_live: bool = False):
        self.repo = repo
        self.admin_notifier = admin_notifier
        # PLAN-079: CUSTOMER_NOTIFICATIONS_ENABLED, chỉ để nói thật với khách ở /thongbao.
        self.orders_live = orders_live
        # Cổng bắt buộc đồng ý trước khi tạo link mới. Mặc định tắt; chỉ có tác dụng khi đã có bản công bố.
        self.terms_required = terms_required

    # --- Điều khoản ---------------------------------------------------------------------------

    def rules_page(self, user_id: int | None, now: datetime) -> BotReply:
        """Có bản công bố: hiện điều khoản theo phiên bản. Chưa có: giữ trang /dieukien cũ."""
        with self.repo.connect() as conn:
            live = terms.current(conn, now)
            accepted = None if live is None or user_id is None else terms.acceptance(conn, user_id, live.id)
        if live is None:
            return page_reply(DIEUKIEN)
        return terms_home_reply(live, None if accepted is None else accepted["accepted_at"])

    def terms_gate(self, user_id: int, now: datetime) -> BotReply | None:
        """Chỉ khi bật cờ và có bản công bố mà khách chưa đồng ý: chặn tạo link mới, mời đọc điều khoản."""
        if not self.terms_required:
            return None
        with self.repo.connect() as conn:
            live = terms.current(conn, now)
            if live is None or terms.acceptance(conn, user_id, live.id) is not None:
                return None
        page = self.rules_page(user_id, now)
        return BotReply(TERMS_REQUIRED + "\n\n" + page.text, inline_keyboard=page.inline_keyboard)

    def link_terms(self, user_id: int, now: datetime) -> dict:
        with self.repo.connect() as conn:
            return terms.link_context(conn, user_id, now)

    # --- Đơn hàng và thông báo (PLAN-079) -----------------------------------------------------

    def orders_page(self, user_id: int, number: int = 1) -> BotReply:
        with self.repo.connect() as conn:
            stats = customer_orders.summary(conn, user_id)
            if not stats["total"]:
                return BotReply(ORDERS_EMPTY, inline_keyboard=((("📩 Hỗ trợ", "u:p:support"), ("◀️ Trang chủ", "u:p:home")),))
            rows, current, pages = customer_orders.page(conn, user_id, number)
        return orders_summary_reply(stats, rows, current, pages)

    def order_detail(self, user_id: int, conversion_id: str) -> BotReply:
        with self.repo.connect() as conn:
            row = customer_orders.detail(conn, user_id, conversion_id)
        if row is None:
            return BotReply("", toast="Không thấy đơn này trong các đơn của bạn.")
        return order_detail_reply(row)

    def notify_page(self, user_id: int) -> BotReply:
        with self.repo.connect() as conn:
            current = customer_orders.prefs(conn, user_id)
        return notify_settings_reply(current, self.orders_live)

    # --- Hỗ trợ -------------------------------------------------------------------------------

    def support_page(self, user_id: int, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            has = bool(support.user_tickets(conn, user_id, 1))
        return support_home_reply(support.CATEGORIES, has, notice)

    def _set_waiting(self, user_id: int, value: str | None) -> None:
        key = f"support_waiting:{user_id}"
        if value is not None:
            self.repo.set_state(key, value)
        elif self.repo.get_state(key) not in (None, "0"):
            self.repo.set_state(key, "0")

    def _waiting(self, user_id: int, now: datetime) -> tuple[str, str] | None:
        value = self.repo.get_state(f"support_waiting:{user_id}")
        if not value or value == "0":
            return None
        try:
            mode, arg, until = value.split("|")
            expired = float(until) < now.timestamp()
        except ValueError:
            expired = True
        if expired:
            self._set_waiting(user_id, None)
            return None
        return mode, arg

    def clear(self, user_id: int) -> None:
        self._set_waiting(user_id, None)

    def callback(self, user_id: int, chat_id: int | None, data: str, now: datetime) -> BotReply | None:
        """Nút u:t:* và u:h:*. None: không phải nút của module này."""
        if not (data.startswith("u:t:") or data.startswith("u:h:") or data.startswith("u:o:") or data.startswith("u:n:")):
            return None
        if chat_id is not None and chat_id != user_id:
            return BotReply("", toast="Nút này chỉ dùng trong cuộc trò chuyện riêng của bạn.", show_alert=True)
        if not (_CATEGORY.fullmatch(data) or data.startswith("u:h:r:")):
            self._set_waiting(user_id, None)
        until = f"{(now + WAIT_TTL).timestamp():.0f}"
        if (matched := _SECTION.fullmatch(data)) is not None:
            with self.repo.connect() as conn:
                live = terms.current(conn, now)
            reply = None if live is None else terms_section_reply(live, matched.group(1))
            return reply or BotReply("", toast="Mục này không còn trong điều khoản hiện hành.")
        if (matched := _ACCEPT.fullmatch(data)) is not None:
            return self._accept(user_id, int(matched.group(1)), now)
        if (matched := _ORDER_PAGE.fullmatch(data)) is not None:
            return self.orders_page(user_id, int(matched.group(1)))
        if (matched := _ORDER.fullmatch(data)) is not None:
            return self.order_detail(user_id, matched.group(1))
        if (matched := _NOTIFY.fullmatch(data)) is not None:
            with self.repo.connect() as conn:
                current = customer_orders.toggle(conn, user_id, matched.group(1), now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            return notify_settings_reply(current, self.orders_live, "Đã lưu lựa chọn của bạn.")
        if (matched := _CATEGORY.fullmatch(data)) is not None:
            category = matched.group(1)
            if category not in support.CATEGORIES:
                return BotReply("", toast="Nút này không còn hiệu lực.")
            self._set_waiting(user_id, f"new|{category}|{until}")
            return support_prompt_reply(SUPPORT_ASK.format(category=support.CATEGORIES[category]))
        if data == "u:h:mine":
            with self.repo.connect() as conn:
                tickets = support.user_tickets(conn, user_id)
            return support_list_reply(tickets, support.CATEGORIES, support.STATUS_LABELS)
        if (matched := _TICKET.fullmatch(data)) is not None:
            ticket_id = int(matched.group(2))
            with self.repo.connect() as conn:
                ticket = support.get_for_user(conn, ticket_id, user_id)
                history = [] if ticket is None else support.events(conn, ticket_id)
            if ticket is None:
                return BotReply("", toast="Không thấy yêu cầu này.")
            if matched.group(1) == "r":
                if ticket.status in support.FINAL:
                    return BotReply("", toast=SUPPORT_CLOSED, show_alert=True)
                self._set_waiting(user_id, f"reply|{ticket_id}|{until}")
                return support_prompt_reply(SUPPORT_REPLY_ASK.format(ticket=ticket_id))
            replies = [
                ("Hỗ trợ" if row["action"] == "reply" else "Bạn", str(row["note"]))
                for row in history
                if row["action"] in {"reply", "customer_reply"} and row["note"]
            ]
            return support_ticket_reply(
                ticket, support.CATEGORIES, support.STATUS_LABELS, replies, ticket.status not in support.FINAL
            )
        return BotReply("", toast="Nút này không còn hiệu lực.")

    def _accept(self, user_id: int, version_id: int, now: datetime) -> BotReply:
        try:
            with self.repo.connect() as conn:
                _acceptance_id, created = terms.accept(conn, user_id, version_id, "telegram_button", now)
        except terms.TermsError:
            return BotReply("", toast="Phiên bản này không còn hiện hành. Mở lại /dieukien.", show_alert=True)
        page = self.rules_page(user_id, now)
        toast = "Đã ghi nhận bạn đồng ý điều khoản." if created else "Bạn đã đồng ý phiên bản này trước đó."
        return BotReply(page.text, inline_keyboard=page.inline_keyboard, toast=toast)

    def consume_text(self, user_id: int, username: str | None, text: str, now: datetime,
                     update_id: int | None) -> BotReply | None:
        """Nội dung ticket hoặc phần bổ sung khi đang chờ. None: không chờ, để luồng tạo link xử lý."""
        waiting = self._waiting(user_id, now)
        if waiting is None:
            return None
        mode, arg = waiting
        try:
            with self.repo.connect() as conn:
                if mode == "new":
                    ticket, created = support.open_ticket(conn, user_id, arg, text, now, update_id)
                else:
                    ticket = support.customer_reply(conn, int(arg), user_id, text, now, update_id)
                    created = False
        except support.SupportError as exc:
            if exc.args and exc.args[0] == "empty":
                return support_prompt_reply(SUPPORT_EMPTY)
            self._set_waiting(user_id, None)
            return self.support_page(user_id, SUPPORT_CLOSED)
        except sqlite3.Error:
            logger.exception("[Cashback] ghi yêu cầu hỗ trợ thất bại user=%s", user_id)
            return support_prompt_reply("⚠️ Chưa ghi được yêu cầu. Bạn gửi lại sau ít phút nhé.")
        self._set_waiting(user_id, None)
        if self.admin_notifier is not None:
            if mode == "new" and created:
                self.admin_notifier.notify_support_ticket(ticket, username)
            elif mode == "reply":
                self.admin_notifier.notify_support_reply(ticket, username)
        if mode == "reply":
            return BotReply(
                f"✅ Đã gửi bổ sung cho yêu cầu #{ticket.id}. Trạng thái: {support.STATUS_LABELS[ticket.status]}",
                inline_keyboard=((("🗂 Yêu cầu của tôi", "u:h:mine"), ("◀️ Trang chủ", "u:p:home")),),
            )
        return support_created_reply(ticket, support.STATUS_LABELS[ticket.status], created)
