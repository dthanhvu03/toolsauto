"""Admin activity notifications for cashback bot.

Queue in SQLite first, then deliver best-effort to avoid breaking customer flow.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence
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


logger = logging.getLogger(__name__)

# Trạng thái đơn Shopee hay gặp; giá trị lạ thì hiện nguyên văn.
_SHOPEE_STATUS = {
    "UNPAID": "Chờ thanh toán",
    "PAID": "Chờ duyệt",
    "PENDING": "Chờ duyệt",
    "COMPLETED": "Hoàn thành",
    "CANCELLED": "Đã huỷ",
    "CANCELED": "Đã huỷ",
}


SYNC_ORDER_LINES = 10


def _num(amount: int | None) -> str:
    return "-" if amount is None else f"{amount:,}".replace(",", ".")


def _orders_table(orders, splits: dict) -> list[str]:
    """Bảng chữ đều (Telegram không có bảng HTML): mỗi đơn một dòng, tên món đánh số bên dưới.

    splits: dòng cashback_entries theo conversion_id; chưa có sổ thì cột chia tiền để "-".
    """
    headers = ("#", "Trả", "HH", "Khách", "Phí+T", "Admin")
    rows: list[tuple[str, ...]] = []
    icons: list[str] = []
    names: list[str] = []
    total = [0, 0, 0, 0, 0]
    for index, order in enumerate(orders, 1):
        status = (order.order_status or "").upper()
        cancelled = status in ("CANCELLED", "CANCELED")
        icon = "✅" if status == "COMPLETED" else "❌" if cancelled else "⏳"
        split = splits.get(order.conversion_id)
        cashback = costs = keep = None
        if split is not None and order.commission_vnd is not None:
            cashback = int(split["cashback_vnd"])
            costs = int(split["fee_vnd"]) + int(split["tax_vnd"])
            keep = int(order.commission_vnd) - cashback - costs
        values = (order.gmv_vnd, order.commission_vnd, cashback, costs, keep)
        if not cancelled:
            total = [t + (v or 0) for t, v in zip(total, values)]
        rows.append((str(index), *(_num(v) for v in values)))
        icons.append(icon)
        name = (order.item_name or order.order_sn).strip()
        name = name if len(name) <= 40 else name[:39].rstrip() + "…"
        label = html.escape(_SHOPEE_STATUS.get(status, order.order_status or "Chờ duyệt"))
        names.append(f"{index}. {'🆕 ' if order.is_new else ''}{html.escape(name)} · {icon} {label}")
    footer = ("Σ", *(_num(v) for v in total)) if len(rows) > 1 else None
    every = [headers, *rows] + ([footer] if footer else [])
    widths = [max(len(row[i]) for row in every) for i in range(len(headers))]

    def fmt(row: tuple[str, ...]) -> str:
        return " ".join(cell.rjust(width) if i else cell.ljust(width) for i, (cell, width) in enumerate(zip(row, widths)))

    table = [fmt(headers) + " TT"] + [fmt(row) + " " + icon for row, icon in zip(rows, icons)]
    if footer:
        table += ["─" * len(fmt(footer)), fmt(footer)]
    return ["<pre>" + html.escape("\n".join(table)) + "</pre>", *names, "<i>Đơn vị: đồng · Phí+T = phí + dự phòng thuế · Σ không tính đơn huỷ</i>"]


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
        # Lỗi không gắn update (poll, vòng lặp) thêm mốc giây: trước đây khoá trùng nên chỉ báo một lần trong đời DB.
        # Chống spam vẫn do cooldown theo error_type ở trên.
        scope = update_id if update_id is not None else f"t{int(now)}"
        self.repo.enqueue_admin_event(
            event_key=f"request_failed:{error_type}:{scope}:{telegram_user_id or 0}",
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

    def notify_shopee_sync_result(self, ok: bool, message: str, bot_orders: Sequence = ()) -> None:
        """Kết quả lần bấm 🔄 (PLAN-066): nút trả lời ngay, kết quả tới sau, kèm HH từng đơn qua bot."""
        if not self._active():
            return
        title = "✅ <b>Đồng bộ Shopee xong</b>" if ok else "⚠️ <b>Đồng bộ Shopee chưa trọn</b>"
        lines = [title, "", html.escape(message)]
        ordered = sorted(bot_orders, key=lambda order: not order.is_new)
        splits = self._entry_splits([order.conversion_id for order in ordered[:SYNC_ORDER_LINES]])
        if ordered:
            lines += _orders_table(ordered[:SYNC_ORDER_LINES], splits)
        if len(ordered) > SYNC_ORDER_LINES:
            lines.append(f"… và {len(ordered) - SYNC_ORDER_LINES} đơn khác (xem 📊 Thống kê).")
        lines.append(f"🕓 {_vn_now_text()}")
        self.repo.enqueue_admin_event(
            event_key=f"shopee_sync_result:{datetime.now(timezone.utc).timestamp()}",
            event_type="SHOPEE_SYNC",
            chat_id=int(self.chat_id),
            message_html="\n".join(lines),
        )

    def _entry_splits(self, conversion_ids: list[str]) -> dict:
        """Phần chia đã ghi sổ của các đơn. Lỗi đọc sổ thì bỏ dòng chia, tin vẫn gửi."""
        ids = [cid for cid in conversion_ids if cid]
        if not ids:
            return {}
        try:
            with self.repo.connect() as conn:
                rows = conn.execute(
                    "SELECT conversion_id, cashback_vnd, fee_vnd, tax_vnd FROM cashback_entries "
                    f"WHERE conversion_id IN ({','.join('?' * len(ids))})",
                    ids,
                ).fetchall()
        except Exception:
            logger.exception("[Cashback] đọc sổ hoàn tiền cho tin đồng bộ lỗi")
            return {}
        return {row["conversion_id"]: row for row in rows}

    def notify_payout_request(self, payout, username: str | None) -> None:
        """Khách bấm Rút (PLAN-066). Chuyển xong thì admin bấm ✅ trong /admin → 👛 Ví khách."""
        if not self._active():
            return
        user_id = int(payout["telegram_user_id"])
        body = (
            f"💸 <b>Yêu cầu rút tiền</b> · {_who(user_id, username)}\n\n"
            f"Số tiền: <b>{format_vnd(int(payout['amount_vnd']))}</b>\n"
            f"Mã: <code>{html.escape(payout['transfer_note'] or '')}</code>\n"
            f"🕓 {_vn_now_text()}\n\n"
            "👉 /admin → <b>👛 Ví khách</b> để xem số tài khoản và xác nhận đã chuyển."
        )
        self.repo.enqueue_admin_event(
            event_key=f"payout_request:{payout['id']}",
            event_type="PAYOUT_REQUEST",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_wallet_clawback(self, transition) -> None:
        """Đơn đã vào ví nhưng Shopee huỷ sau đó: số dư khách bị trừ, có thể âm."""
        if not self._active():
            return
        body = (
            "⚠️ <b>Đơn đã vào ví bị huỷ</b>\n\n"
            f"🛍️ {html.escape(buyer_name(transition.item_name))}\n"
            f"Trừ khỏi ví: <b>{format_vnd(transition.cashback_vnd)}</b>\n"
            f"👤 <code>{transition.telegram_user_id}</code>\n"
            f"🕓 {_vn_now_text()}\n\n"
            "ⓘ Nếu khách đã rút khoản này, số dư sẽ âm cho tới khi có đơn mới bù lại."
        )
        self.repo.enqueue_admin_event(
            event_key=f"wallet_clawback:{transition.conversion_id}",
            event_type="WALLET_CLAWBACK",
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

