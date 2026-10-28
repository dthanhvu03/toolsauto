"""Admin activity notifications for cashback bot.

Queue in SQLite first, then deliver best-effort to avoid breaking customer flow.
"""

from __future__ import annotations

import html
import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


from cashback_bot import insights, ops_watch, policy_snapshot
from cashback_bot.admin_customer_notify import REASON_LABELS
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.order_notify import bought_items
from cashback_bot.messages import buyer_name
from cashback_bot.money import format_vnd
from cashback_bot.pricing import V12, cashback_for
from cashback_bot.product_data import SHOPEE_BASE_BPS
from cashback_bot.support import CATEGORIES
from cashback_bot.telegram_api import TelegramApi

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
# Sự kiện thường ngày gửi im lặng; lỗi vẫn kêu chuông.
def _vn_now_text() -> str:
    return datetime.now(timezone.utc).astimezone(ICT).strftime("%H:%M · %d/%m")


# Dòng 📨 trong tin «Có đơn Shopee mới»: chờ tin «đơn mới» của khách xong rồi sửa tin admin (rà soát 2026-10-28).
RECEIPT_PENDING = "📨 Báo khách: ⏳ đang chờ gửi"
RECEIPT_WINDOW = timedelta(hours=72)
RECEIPT_EDIT_TRIES = 3


def receipt_line(row) -> str | None:
    """Kết quả tin «đơn mới» của khách (status, sent_at, last_error). Chưa xong (chờ / đang gửi) → None."""
    status, error = row["status"], row["last_error"] or ""
    if status == "sent":
        try:
            moment = datetime.strptime(row["sent_at"] or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            when = " " + moment.astimezone(ICT).strftime("%H:%M · %d/%m")
        except ValueError:
            when = ""
        return f"📨 Báo khách: ✅ đã gửi{when}"
    if status == "unknown":
        return "📨 Báo khách: ❔ không rõ khách nhận chưa (mạng đứt lúc gửi)"
    if status == "failed":
        why = "khách chặn bot" if error.startswith("permanent:403") else "gửi lỗi, xem /admin → Thông báo khách"
        return f"📨 Báo khách: ❌ không gửi được ({why})"
    if status == "suppressed":
        return f"📨 Báo khách: ⏭ không gửi ({html.escape(REASON_LABELS.get(error, error or 'bỏ qua'))})"
    return None


def _other_item(conn: sqlite3.Connection, conversion_id: str) -> str | None:
    """Tên món khách mua khi đơn không có món trong link (đơn gián tiếp), hoặc None."""
    row = conn.execute(
        """
        SELECT c.raw_json, c.item_name, l.item_id FROM shopee_conversions c
        JOIN link_requests l ON l.id = c.matched_link_id WHERE c.conversion_id = ?
        """,
        (conversion_id,),
    ).fetchone()
    if row is None or row["item_id"] is None:
        return None
    bought = bought_items(row["raw_json"])
    if not bought or int(row["item_id"]) in bought:
        return None
    name = (row["item_name"] or "món khác").strip()
    return name if len(name) <= 60 else name[:59].rstrip() + "…"


def _who(telegram_user_id: int, username: str | None) -> str:
    """Tiêu đề hiện @username; chưa có username thì hiện ID. Khách Zalo (ID âm, PLAN-082) hiện Zalo #N."""
    if telegram_user_id < 0:
        return f"Zalo #{-telegram_user_id}"
    if username:
        return f"@{html.escape(username)}"
    return f"<code>{telegram_user_id}</code>"


def _user_line(user_id: int | None) -> str:
    """Dòng chi tiết người dùng. Khách Zalo mang ID nội bộ âm (PLAN-082): hiện Zalo #N."""
    if user_id is None:
        return "User <code>-</code>"
    return f"Zalo <code>#{-user_id}</code>" if user_id < 0 else f"User <code>{user_id}</code>"


def _update_line(update_id: int | None) -> str:
    """Update Telegram, hoặc tin Zalo thứ N (update âm, PLAN-082)."""
    if update_id is None:
        return "Update <code>-</code>"
    return f"Tin Zalo <code>#{-update_id}</code>" if update_id < 0 else f"Update <code>{update_id}</code>"


def _details(*lines: str) -> str:
    """Mã kỹ thuật gom vào khối thu gọn, bấm mới mở."""
    return "<blockquote expandable>" + "\n".join(lines) + "</blockquote>"


def _pct(bps: int) -> str:
    whole, frac = divmod(int(bps), 100)
    return f"{whole}%" if frac == 0 else f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def link_split_lines(link: sqlite3.Row, found: "policy_snapshot.LinkPolicy | None") -> list[str]:
    """Bảng chia tiền của một link cho admin, theo đúng snapshot chính sách đã dùng để báo giá khách.

    Rỗng khi không có snapshot dùng được hoặc tính lại không ra số đã báo: không hiện số có thể sai.
    """
    commission, quoted = link["estimated_commission"], link["estimated_cashback"]
    if found is None or found.policy is None or commission is None or quoted is None:
        return []
    policy = found.policy
    quote = cashback_for(int(commission), policy)
    if quote.cashback_vnd != int(quoted):
        return []
    keys = link.keys()
    rate = link["commission_rate_bps"] if "commission_rate_bps" in keys else None
    seller = link["seller_commission_vnd"] if "seller_commission_vnd" in keys else None
    shopee = link["shopee_commission_vnd"] if "shopee_commission_vnd" in keys else None
    split = seller is not None and shopee is not None and int(seller) + int(shopee) >= quote.commission_vnd
    # Shopee Comm AddLiveTag báo trên 2,5% không đưa vào báo giá (SHOPEE_BASE_BPS): tỷ lệ hiện theo số đã tính.
    capped = split and int(seller) + int(shopee) > quote.commission_vnd
    if capped and link["price_vnd"]:
        rate = quote.commission_vnd * 10_000 // int(link["price_vnd"])
    rows: list[tuple[str, int, bool]] = [(f"HH ước tính{' ' + _pct(rate) if rate else ''}", quote.commission_vnd, False)]
    if split:
        rows.append(("· từ shop", int(seller), False))
        rows.append((f"· từ Shopee{' Xtra' if link['is_xtra'] else ''}", quote.commission_vnd - int(seller), False))
    v12 = policy.pricing_version == V12
    rows.append((f"Dự phòng phí {_pct(policy.fee_bps)}", quote.fee_reserve_vnd, True))
    rows.append((f"Dự phòng thuế {_pct(policy.tax_reserve_bps)}", quote.tax_reserve_vnd, True))
    if quote.other_reserve_vnd:
        rows.append(("Dự phòng khác", quote.other_reserve_vnd, True))
    if v12 and quote.distributable_vnd is not None:
        rows.append(("Quỹ chia", quote.distributable_vnd, False))
    rows.append((f"Phần khách {_pct(policy.share_bps)}{' quỹ' if v12 else ' HH'}", quote.cashback_vnd, False))
    rows.append(("Biên", quote.remainder_vnd, False))
    cells = [("-" if minus and value else "") + f"{value:,}".replace(",", ".") for _label, value, minus in rows]
    label_w = max(len(label) for label, _v, _m in rows)
    num_w = max(len(cell) for cell in cells)
    table = [f"{label.ljust(label_w)} {cell.rjust(num_w)}" for (label, _v, _m), cell in zip(rows, cells)]
    basis = "V1.2: chia trên quỹ sau dự phòng" if v12 else "V1.1: phần khách tính trên HH gốc, biên chịu dự phòng"
    lines = [
        "<pre>" + html.escape("\n".join(table)) + "</pre>",
        f"<i>{basis}. Ước tính theo giá tham khảo, chốt theo chính sách của link. "
        "Biên = HH − phần khách − dự phòng.</i>",
    ]
    if capped:
        lines.append(f"<i>AddLiveTag báo Shopee Comm {format_vnd(int(shopee))}; bot chỉ tính tối đa "
                     f"{_pct(SHOPEE_BASE_BPS)}, phần dư khách thấy là «có thể được thêm».</i>")
    return lines


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

_CHANGE_LABELS = {
    "net_commission_vnd": "hoa hồng",
    "order_status": "trạng thái đơn",
    "validation_status": "duyệt hoa hồng",
    "fraud_flag": "cờ gian lận",
    "attribution": "Sub ID trỏ link khác (giữ người cũ)",
}


def short_order(order_sn: str | None) -> str:
    """Mã đơn rút gọn cho tin và màn admin: 261023…0N."""
    text = str(order_sn or "-")
    return text if len(text) <= 10 else f"{text[:6]}…{text[-2:]}"


def change_value(field: str, value: str | None) -> str:
    if value is None:
        return "-"
    if field == "net_commission_vnd":
        try:
            return format_vnd(int(value))
        except ValueError:
            return html.escape(value)
    if field == "fraud_flag":
        return "có" if value == "1" else "không"
    if field == "attribution":
        return f"link #{html.escape(value)}"
    if field in ("order_status", "validation_status"):
        return html.escape(insights.status_word(value))
    return html.escape(value)



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
    # PLAN-079: cờ CUSTOMER_NOTIFICATIONS_ENABLED cho thông báo đơn hàng chủ động.
    customer_notifications_enabled: bool = False
    customer_notification_test_ids: frozenset[int] = frozenset()
    # Số lần sửa tin admin lỗi theo id (RAM): restart thì thử lại từ đầu.
    _receipt_failures: dict[int, int] = field(default_factory=dict, repr=False)

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
            + _details(_user_line(telegram_user_id))
        )
        self.repo.enqueue_admin_event(
            event_key=f"new_user:{telegram_user_id}",
            event_type="NEW_USER",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_support_ticket(self, ticket, username: str | None) -> None:
        """Yêu cầu hỗ trợ mới (PLAN-077). Nội dung đã làm sạch ở support.clean_text."""
        if not self._active():
            return
        body = (
            f"📩 <b>Yêu cầu hỗ trợ #{ticket.id}</b> · {_who(ticket.telegram_user_id, username)}\n\n"
            f"{CATEGORIES.get(ticket.category, ticket.category)}\n"
            f"<i>{html.escape(ticket.message[:300])}</i>\n"
            f"🕓 {_vn_now_text()}\n"
            "Mở: /admin → 📩 Hỗ trợ\n"
            + _details(
                _user_line(ticket.telegram_user_id),
                f"Link <code>{ticket.link_id or '-'}</code>",
                f"Đơn <code>{html.escape(short_order(ticket.conversion_id)) if ticket.conversion_id else '-'}</code>",
            )
        )
        self.repo.enqueue_admin_event(
            event_key=f"support_ticket:{ticket.id}",
            event_type="SUPPORT_TICKET",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_support_reply(self, ticket, username: str | None) -> None:
        if not self._active():
            return
        body = (
            f"💬 <b>Khách bổ sung yêu cầu #{ticket.id}</b> · {_who(ticket.telegram_user_id, username)}\n"
            f"🕓 {_vn_now_text()}\n"
            "Mở: /admin → 📩 Hỗ trợ"
        )
        self.repo.enqueue_admin_event(
            event_key=f"support_reply:{ticket.id}:{ticket.updated_at}",
            event_type="SUPPORT_REPLY",
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
        split: list[str] = []
        label = row.estimate_policy or (f"v1.1:{row.cashback_rate_percent}" if row.cashback_rate_percent else None)
        try:
            with self.repo.connect() as conn:
                link = conn.execute("SELECT * FROM link_requests WHERE id = ?", (row.id,)).fetchone()
                found = policy_snapshot.load(conn, row.id)
            split = link_split_lines(link, found)
            label = found.label if found is not None else label
        except sqlite3.Error:
            logger.warning("[Cashback] không đọc được snapshot link id=%s cho tin báo admin", row.id)
        body = (
            f"🔗 <b>Đã gửi link</b>{' · 🎵 TikTok' if row.platform == 'tiktok' else ''} · "
            f"{_who(row.telegram_user_id, username)}\n\n"
            f"🛍️ {html.escape(buyer_name(row.product_name or '-'))}\n"
            f"💰 Giá {format_vnd(row.price_vnd or 0)} · Hoàn <b>{format_vnd(row.estimated_cashback or 0)}</b>\n"
            + "".join(f"{line}\n" for line in split)
            + f"🕓 {_vn_now_text()}\n"
            + _details(
                _user_line(row.telegram_user_id),
                f"Item <code>{row.item_id or '-'}</code>",
                f"Sub <code>{row.sub_id}</code>",
                _update_line(update_id),
                *([f"Chính sách <code>{html.escape(label)}</code>"] if label else []),
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
        )
        if update_id is not None or telegram_user_id is not None:
            body += _details(_update_line(update_id), _user_line(telegram_user_id))
        # Lỗi không gắn update (poll, vòng lặp) thêm mốc giây: trước đây khoá trùng nên chỉ báo một lần trong đời DB.
        # Chống spam vẫn do cooldown theo error_type ở trên.
        scope = update_id if update_id is not None else f"t{int(now)}"
        self.repo.enqueue_admin_event(
            event_key=f"request_failed:{error_type}:{scope}:{telegram_user_id or 0}",
            event_type="REQUEST_FAILED",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_commission_changes(self, run_id: int, changes: Sequence) -> None:
        """Một tin cho mỗi lần đồng bộ có thay đổi đáng kể (PLAN-074): hoa hồng giảm/về 0, gian lận, huỷ,
        trạng thái lùi, Sub ID trỏ link khác. Chỉ báo, không tự sửa tiền hay quyền rút."""
        if not self._active() or not changes:
            return
        # Rà soát 2026-10-26: chỉ gọi «hoa hồng thay đổi» khi số tiền đổi; đổi trạng thái thì báo «cần xem».
        money = any(change.field == "net_commission_vnd" for _order, change in changes)
        lines = ["🔔 <b>Hoa hồng Shopee thay đổi</b>" if money else "🔔 <b>Đơn Shopee có thay đổi cần xem</b>", ""]
        for order_sn, change in list(changes)[:10]:
            label = _CHANGE_LABELS.get(change.field, change.field)
            old = change_value(change.field, change.old)
            new = change_value(change.field, change.new)
            lines.append(f"• <code>{html.escape(short_order(order_sn))}</code> {label}: {old} → <b>{new}</b>")
        if len(changes) > 10:
            lines.append(f"… và {len(changes) - 10} thay đổi khác.")
        lines += ["", "👉 /admin → 🧾 Đơn & hoa hồng → 🧾 Duyệt hoa hồng (🚨 cần kiểm tra).", f"🕓 {_vn_now_text()}"]
        self.repo.enqueue_admin_event(
            event_key=f"commission_changes:{run_id}",
            event_type="COMMISSION_CHANGED",
            chat_id=int(self.chat_id),
            message_html="\n".join(lines),
        )

    def notify_shopee_new_order(
        self,
        order_sn: str,
        sub_id: str,
        telegram_user_id: int | None,
        username: str | None = None,
        commission_vnd: int | None = None,
        order_status: str | None = None,
        conversion_id: str | None = None,
    ) -> None:
        if not self._active():
            return
        other = receipt = None
        if conversion_id:
            with self.repo.connect() as conn:
                other = _other_item(conn, conversion_id)
                # Tin khách ghi cùng transaction với đơn: không có nghĩa là bot không báo (Sub ID trỏ link khác).
                customer = conn.execute(
                    "SELECT status, sent_at, last_error FROM admin_notifications WHERE event_key = ?",
                    (f"conversion:{conversion_id}:first_matched",),
                ).fetchone()
            if customer is None:
                receipt = "📨 Báo khách: ⏭ không gửi (gán người nhận cần xem lại)"
            else:
                receipt = receipt_line(customer) or RECEIPT_PENDING
        comm_text = format_vnd(commission_vnd) if commission_vnd is not None else "Đang cập nhật"
        status_text = html.escape(_SHOPEE_STATUS.get((order_status or "").upper(), order_status or "Chờ duyệt"))
        who = _who(telegram_user_id or 0, username) if telegram_user_id else "Chưa xác định"
        body = (
            "🎉 <b>Có đơn Shopee mới qua bot!</b>\n\n"
            f"📦 Đơn hàng: <code>{html.escape(order_sn)}</code>\n"
            f"🏷️ Sub ID: <code>{html.escape(sub_id)}</code>\n"
            f"👤 Người tạo link: {who}\n"
            + (f"🔀 Mua món khác link: {html.escape(other)}\n" if other else "")
            + f"💵 Hoa hồng Shopee: <b>{comm_text}</b>\n"
            f"📌 Trạng thái: <b>{status_text}</b>\n"
            + (f"{receipt}\n" if receipt else "")
            + f"🕓 {_vn_now_text()}"
        )
        with self.repo.connect() as conn:
            enqueue_event(
                conn, event_key=f"shopee_new_order:{order_sn}", event_type="SHOPEE_ORDER", chat_id=int(self.chat_id),
                message_html=body, source_ref=f"conversion:{conversion_id}" if conversion_id else None,
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
            lines.append(f"… và {len(ordered) - SYNC_ORDER_LINES} đơn khác (xem 🧾 Đơn & hoa hồng → 🗓 Thống kê).")
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
        """Đơn đã vào ví nhưng Shopee huỷ hoặc giảm hoa hồng sau đó (status 'clawback', số âm): số dư khách bị trừ,
        có thể âm."""
        if not self._active():
            return
        title = "Shopee giảm hoa hồng đơn đã vào ví" if transition.status == "clawback" else "Đơn đã vào ví bị huỷ"
        body = (
            f"⚠️ <b>{title}</b>\n\n"
            f"🛍️ {html.escape(buyer_name(transition.item_name))}\n"
            f"Trừ khỏi ví: <b>{format_vnd(abs(transition.cashback_vnd))}</b>\n"
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

    def notify_connection(self, since: float, until: float | None = None) -> None:
        """PLAN-084: bot Telegram không nhận được tin (mạng máy chủ hoặc Telegram lỗi). Một tin khi kéo dài,
        một tin khi kết nối lại; thay cho tin "Lỗi bot" mỗi phút."""
        if not self._active():
            return
        start = datetime.fromtimestamp(since, timezone.utc).astimezone(ICT)
        if until is None:
            body = (
                "📡 <b>Bot đang mất kết nối</b>\n\n"
                f"Không nhận được tin từ Telegram từ {start.strftime('%H:%M · %d/%m')}.\n"
                "Bot tự thử lại, không cần restart."
            )
            key = f"net_down:{int(since)}"
        else:
            end = datetime.fromtimestamp(until, timezone.utc).astimezone(ICT)
            minutes = max(1, round((until - since) / 60))
            body = (
                "📡 <b>Bot đã kết nối lại</b>\n\n"
                f"Mất kết nối {start.strftime('%H:%M')}–{end.strftime('%H:%M · %d/%m')} ({minutes} phút).\n"
                "Bot tự chạy lại, không cần restart.\n"
                "Nếu mạng máy chủ rớt, tin khách Zalo gửi trong lúc này có thể bị mất."
            )
            key = f"net_up:{int(since)}"
        self.repo.enqueue_admin_event(
            event_key=key,
            event_type="NET_DOWN" if until is None else "NET_UP",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_zalo_health(self, down: bool, last_beat: float) -> None:
        """PLAN-083: bot Telegram thấy tiến trình Zalo im quá lâu (dừng hoặc mất kết nối), hoặc đã chạy lại."""
        if not self._active():
            return
        seen = datetime.fromtimestamp(last_beat, timezone.utc).astimezone(ICT).strftime("%H:%M · %d/%m")
        if down:
            body = (
                "🔴 <b>Bot Zalo không hoạt động</b>\n\n"
                f"Lần cuối nhận tin được từ Zalo: {seen}.\n"
                "Tin khách Zalo gửi lúc này sẽ mất (Zalo không giữ lại).\n"
                "Kiểm tra <code>logs/cashback_zalo.log</code>, rồi khởi động lại:\n"
                f"<code>{html.escape(ops_watch.restart_command('zalo'))}</code>"
            )
        else:
            body = f"🟢 <b>Bot Zalo hoạt động lại</b>\n🕓 {_vn_now_text()}"
        self.repo.enqueue_admin_event(
            event_key=f"zalo_{'down' if down else 'up'}:{int(last_beat)}",
            event_type="ZALO_DOWN" if down else "ZALO_UP",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_code_mismatch(self, telegram: str, zalo: str, stale: str, restart: str) -> None:
        """PLAN-087: hai bot chạy khác commit; bot khởi động trước đang chạy code cũ."""
        if not self._active():
            return
        name = "Telegram" if stale == "telegram" else "Zalo"
        body = (
            "⚠️ <b>Hai bot đang chạy code khác nhau</b>\n\n"
            f"Telegram: <code>{html.escape(telegram)}</code> · Zalo: <code>{html.escape(zalo)}</code>\n"
            f"Bot {name} khởi động trước nên đang chạy code cũ. Khởi động lại bot {name}:\n"
            f"<code>{html.escape(restart)}</code>"
        )
        self.repo.enqueue_admin_event(
            event_key=f"code_mismatch:{telegram}:{zalo}",
            event_type="CODE_MISMATCH",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_delivery_digest(self, day: str, counts: dict[str, int]) -> None:
        """PLAN-087: tóm tắt mỗi sáng các tin gửi không thành công trong 24 giờ."""
        if not self._active():
            return
        labels = (
            ("customer_unknown", "Tin khách không rõ đã tới chưa (không tự gửi lại)"),
            ("customer_failed", "Tin khách gửi lỗi"),
            ("admin_failed", "Tin admin gửi lỗi"),
            ("reply_needs_review", "Trả lời khách cần xem lại"),
        )
        lines = [f"• {label}: <b>{counts[key]}</b>" for key, label in labels if counts.get(key)]
        body = (
            "📬 <b>Tin gửi không thành công (24 giờ qua)</b>\n\n" + "\n".join(lines)
            + "\n\nXem và gửi lại ở /admin → 🔔 Thông báo khách."
        )
        self.repo.enqueue_admin_event(
            event_key=f"delivery_digest:{day}",
            event_type="DELIVERY_DIGEST",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_tiktok_new_orders(self, run_key: str, count: int) -> None:
        """PLAN-095 (rà soát đợt 2): có đơn TikTok mới khớp link bot sau một lượt đồng bộ."""
        if not self._active() or count <= 0:
            return
        body = (
            f"🎉 <b>Có {count} đơn TikTok mới qua bot</b>\n\n"
            "Đơn đã ghi sổ (hoàn tạm tính) và khách được báo như đơn Shopee.\n"
            "Xem: /admin → 🎵 TikTok Shop, hoặc 🧾 Duyệt hoa hồng."
        )
        self.repo.enqueue_admin_event(
            event_key=f"tiktok_new:{run_key}", event_type="TIKTOK_NEW_ORDERS", chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_alt_crosscheck(self, day: str, body: str) -> None:
        """PLAN-098: đối soát AddLiveTag có lệch; tối đa một tin mỗi ngày."""
        if not self._active():
            return
        self.repo.enqueue_admin_event(
            event_key=f"alt_crosscheck:{day}", event_type="ALT_CROSSCHECK", chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_tiktok_sync_failed(self, day: str, kind: str) -> None:
        """Lỗi đồng bộ đơn TikTok viết thường; mỗi loại lỗi báo tối đa một lần mỗi ngày (bot tự thử lại 15 phút)."""
        if not self._active():
            return
        reason = {
            "auth": "Khoá RioHub bị từ chối (sai hoặc hết hạn). Kiểm tra RIOHUB_API_KEY trong .env.",
            "creator": "Tài khoản TikTok mất kết nối với RioHub, hoặc chưa còn là thành viên RioMCN. "
                       "Đăng nhập RioHub để kết nối lại.",
        }.get(kind, "Không gọi được RioHub (mạng hoặc RioHub đang lỗi).")
        body = (
            "⚠️ <b>Chưa kéo được đơn TikTok</b>\n\n"
            f"{reason}\nBot tự thử lại sau 15 phút. Trạng thái: /admin → 🎵 TikTok Shop."
        )
        self.repo.enqueue_admin_event(
            event_key=f"tiktok_sync_failed:{kind}:{day}", event_type="TIKTOK_SYNC_FAILED", chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_nightly_brief(self, day: str, body: str) -> None:
        """PLAN-092: 🌙 bản tin tối (mục tiêu, hôm nay, an toàn), mỗi ngày một lần."""
        if not self._active():
            return
        self.repo.enqueue_admin_event(
            event_key=f"nightly_brief:{day}",
            event_type="NIGHTLY_BRIEF",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_sale_reminder_pending(self, slot, count: int) -> None:
        """Nhắc mùa sale: lượt sắp tới chưa được duyệt thì không gửi. Báo một lần, trước giờ gửi 48 giờ."""
        if not self._active():
            return
        at = slot.at.astimezone(ICT).strftime("%H:%M %d/%m")
        body = (
            f"📣 <b>Nhắc sale {slot.event.label} chờ anh duyệt</b>\n\n"
            f"Gửi lúc {at} cho {count} khách. Chưa duyệt thì bot không gửi.\n"
            "Mở /admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale để xem trước và duyệt."
        )
        self.repo.enqueue_admin_event(
            event_key=f"sale_reminder_pending:{slot.id}",
            event_type="SALE_REMINDER_PENDING",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def notify_deals_ready(self, day: str, count: int, people: int, slot: str = "toi", label: str = "🌙 Tối",
                           send_at: str = "20:08") -> None:
        """Một lượt deal hời (trưa / tối) đã soạn: anh xem trước, không làm gì thì tới giờ tự gửi."""
        if not self._active():
            return
        body = (
            f"🔥 <b>Deal hời {label.lower()} nay đã soạn: {count} món</b>\n\n"
            f"{send_at} tự gửi cho {people} khách đã chọn danh mục (và khách bot đoán gu).\n"
            "Xem trước, bỏ món hay bỏ cả lượt: /admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời."
        )
        key = f"deals_ready:{day}" if slot == "toi" else f"deals_ready:{day}:{slot}"
        self.repo.enqueue_admin_event(event_key=key, event_type="DEALS_READY",
                                      chat_id=int(self.chat_id), message_html=body)

    def notify_zalo_capacity(self, count: int, limit: int) -> None:
        """PLAN-083: gói Zalo BASIC giới hạn số người dùng mỗi bot."""
        if not self._active():
            return
        head = "🔴 <b>Bot Zalo đã chạm trần gói miễn phí</b>" if count >= limit else "🟡 <b>Bot Zalo sắp chạm trần</b>"
        body = (
            f"{head}\n\n👥 {count}/{limit} khách Zalo (gói BASIC).\n"
            "Khách mới có thể không nhắn được bot. Cân nhắc lên gói Pro khi Zalo mở bán."
        )
        self.repo.enqueue_admin_event(
            event_key=f"zalo_capacity:{count}",
            event_type="ZALO_CAPACITY",
            chat_id=int(self.chat_id),
            message_html=body,
        )

    def flush_pending(self, limit: int = 10) -> None:
        """Gửi hàng đợi chung qua Dispatcher (PLAN-079): tin admin khi bật thông báo admin, tin khách theo cờ và
        tuỳ chọn của khách."""
        Dispatcher(
            self.repo, self.telegram, self.enabled, self.chat_id, self.customer_notifications_enabled,
            self.customer_notification_test_ids,
        ).flush(limit)
        self.refresh_order_receipts()

    def refresh_order_receipts(self, limit: int = 5, now: datetime | None = None) -> int:
        """Tin «Có đơn Shopee mới» còn dòng RECEIPT_PENDING: tin khách xong (bot Telegram hay bot Zalo gửi) thì thay
        dòng đó bằng kết quả. Tin admin chưa gửi thì chỉ sửa nội dung trong hàng đợi; đã gửi thì sửa tin Telegram.
        Sửa tin lỗi RECEIPT_EDIT_TRIES lần thì thôi, chỉ ghi kết quả vào DB. Trả số tin đã cập nhật."""
        if not self._active():
            return 0
        since = ((now or datetime.now(timezone.utc)) - RECEIPT_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.repo.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.chat_id, a.status AS admin_status, a.telegram_message_id, a.message_html,
                       c.status, c.sent_at, c.last_error
                FROM admin_notifications a JOIN admin_notifications c ON c.event_key = a.source_ref || ':first_matched'
                WHERE a.event_type = 'SHOPEE_ORDER' AND a.status IN ('pending', 'retry', 'sent') AND a.created_at >= ?
                  AND instr(a.message_html, ?) > 0 AND c.status IN ('sent', 'failed', 'unknown', 'suppressed')
                ORDER BY a.id LIMIT ?
                """,
                (since, RECEIPT_PENDING, limit),
            ).fetchall()
        updated = 0
        for row in rows:
            body = str(row["message_html"]).replace(RECEIPT_PENDING, receipt_line(row) or RECEIPT_PENDING)
            if row["admin_status"] == "sent":
                if row["telegram_message_id"] is None:
                    continue
                if not self.telegram.edit_message_text(int(row["chat_id"]), int(row["telegram_message_id"]), body):
                    tries = self._receipt_failures[row["id"]] = self._receipt_failures.get(row["id"], 0) + 1
                    if tries < RECEIPT_EDIT_TRIES:
                        continue
                    logger.warning("[Cashback] không sửa được tin admin #%s, chỉ ghi kết quả báo khách", row["id"])
                guard = "status = 'sent'"
            else:
                guard = "status IN ('pending', 'retry')"  # đang gửi thì để lượt sau, khi đã có mã tin
            with self.repo.connect() as conn:
                updated += conn.execute(
                    f"UPDATE admin_notifications SET message_html = ? WHERE id = ? AND {guard}", (body, row["id"])
                ).rowcount
        return updated

