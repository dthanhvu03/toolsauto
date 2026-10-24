"""Màn /admin → 🔗 Shopee Affiliate → 🧾 Duyệt hoa hồng (PLAN-074).

Chỉ xem, lọc, xem lịch sử và đánh dấu "đã kiểm tra cảnh báo" (có audit). Không sửa hoa hồng,
không gán APPROVED, không đụng ví hay chi trả. Số liệu lấy thẳng từ DB, không suy diễn thêm.
"""

from __future__ import annotations

import html
import re
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.admin_notify import change_value, short_order
from cashback_bot.commission_validation import APPROVED, FRAUD, NEEDS_REVIEW, PENDING, REJECTED, UNKNOWN
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, buyer_name
from cashback_bot.money import format_vnd

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:cv:home"
BACK_SHOPEE = (("◀️ Shopee Affiliate", "c:menu:shopee"),)
BACK_HOME_ROW = (("◀️ Duyệt hoa hồng", HOME),)
NO_APPROVAL_NOTE = "⚠️ Chưa có dữ liệu đủ điều kiện xác nhận hoa hồng đã được Shopee duyệt."
SOURCE_NOTE = (
    "ⓘ Trạng thái suy ra từ báo cáo Shopee (độ tin cậy: <b>suy luận</b>). "
    "Tiền Shopee đã trả: <b>chưa xác minh</b>. Màn này không mở ví hay chi trả."
)

_CONV = re.compile(r"^c:cv:(o|ack):([0-9A-Za-z:_-]{1,48})$")
_LIST = re.compile(r"^c:cv:l:(pending|approved|rejected|alert|changed)$")

STATUS_LABELS = {
    UNKNOWN: "❔ Chưa xác định",
    PENDING: "⏳ Chờ Shopee duyệt",
    APPROVED: "✅ Shopee đã duyệt",
    REJECTED: "❌ Bị từ chối",
    FRAUD: "🚨 Gian lận",
    NEEDS_REVIEW: "🔎 Cần kiểm tra",
}
REASON_LABELS = {
    "awaiting_shopee_validation": "Shopee chưa duyệt hoa hồng",
    "completed_awaiting_validation": "đơn đã hoàn thành, hoa hồng chưa được xác nhận duyệt",
    "fraud_flag": "Shopee gắn cờ gian lận",
    "order_cancelled": "đơn bị huỷ",
    "fraud_status_conflict": "mã gian lận mâu thuẫn",
    "unmapped_status": "mã trạng thái Shopee chưa biết nghĩa",
    "commission_zero_unexplained": "hoa hồng về 0, không rõ lý do",
    "status_regression": "trạng thái lùi lại (dữ liệu cũ hoặc Shopee sửa)",
    "missing_fields": "báo cáo thiếu dữ liệu",
    "missing_commission": "báo cáo thiếu hoa hồng",
}
ORDER_LABELS = {
    "UNPAID": "Chưa thanh toán",
    "PAID": "Đã thanh toán",
    "COMPLETED": "Đã hoàn thành",
    "CANCELLED": "Đã huỷ",
    "CANCELED": "Đã huỷ",
}
LISTS = {
    "pending": ("📋 Chờ xác minh", f"validation_status IN ('{PENDING}', '{UNKNOWN}')"),
    "approved": ("✅ Đã duyệt", f"validation_status = '{APPROVED}'"),
    "rejected": ("❌ Bị từ chối", f"validation_status = '{REJECTED}'"),
    "alert": (
        "🚨 Gian lận / cần kiểm tra",
        f"(validation_status IN ('{FRAUD}', '{NEEDS_REVIEW}') OR review_status = 'needs_review')",
    ),
    "changed": (
        "🔄 Hoa hồng thay đổi",
        "conversion_id IN (SELECT conversion_id FROM shopee_conversion_changes WHERE field = 'net_commission_vnd')",
    ),
}
_BOT = "matched_link_id IS NOT NULL"

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def _vn(stamp: str | None) -> str:
    if not stamp:
        return "-"
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return html.escape(stamp)
    return moment.astimezone(ICT).strftime("%H:%M %d/%m")


def _title(*path: str) -> str:
    return "⚙️ Quản trị › " + " › ".join(path[:-1] + (f"<b>{path[-1]}</b>",))


def _order_label(status: str | None) -> str:
    return ORDER_LABELS.get((status or "").upper(), "Chưa xác định")


class ValidationAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self.home()
        if data == "c:cv:h":
            return self.history()
        listed = _LIST.fullmatch(data)
        if listed:
            return self.listing(listed.group(1))
        conv = _CONV.fullmatch(data)
        if conv and conv.group(1) == "o":
            return self.detail(conv.group(2))
        if conv and conv.group(1) == "ack":
            return self.acknowledge(admin_id, conv.group(2), now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME_ROW,))

    def _counts(self, conn: sqlite3.Connection) -> dict[str, int]:
        counts = {"total": int(conn.execute(f"SELECT COUNT(*) FROM shopee_conversions WHERE {_BOT}").fetchone()[0])}
        for key, (_label, where) in LISTS.items():
            counts[key] = int(conn.execute(f"SELECT COUNT(*) FROM shopee_conversions WHERE {_BOT} AND {where}").fetchone()[0])
        counts["fraud"] = int(
            conn.execute(f"SELECT COUNT(*) FROM shopee_conversions WHERE {_BOT} AND validation_status = '{FRAUD}'").fetchone()[0]
        )
        counts["review"] = int(
            conn.execute(
                f"SELECT COUNT(*) FROM shopee_conversions WHERE {_BOT} AND "
                f"(validation_status = '{NEEDS_REVIEW}' OR review_status = 'needs_review')"
            ).fetchone()[0]
        )
        return counts

    def home(self) -> BotReply:
        with self.repo.connect() as conn:
            counts = self._counts(conn)
            last = conn.execute("SELECT status, completed_at FROM shopee_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        rows = [
            ("Chờ xác minh", counts["pending"]),
            ("Shopee đã duyệt", counts["approved"]),
            ("Bị từ chối", counts["rejected"]),
            ("Gian lận", counts["fraud"]),
            ("Cần kiểm tra", counts["review"]),
            ("Hoa hồng đã đổi", counts["changed"]),
        ]
        table = "\n".join(f"{label:<16}{value:>4}" for label, value in rows)
        sync = "chưa đồng bộ" if last is None else f"{_vn(last['completed_at'])} ({html.escape(str(last['status']))})"
        lines = [
            _title("Shopee Affiliate", "Duyệt hoa hồng"),
            "",
            f"Đơn qua bot: <b>{counts['total']}</b> · Đồng bộ gần nhất: {sync}",
            f"<pre>{table}</pre>",
        ]
        if counts["approved"] == 0:
            lines.append(NO_APPROVAL_NOTE)
        lines += ["", SOURCE_NOTE]
        keyboard = (
            ((f"📋 Chờ xác minh ({counts['pending']})", "c:cv:l:pending"), (f"✅ Đã duyệt ({counts['approved']})", "c:cv:l:approved")),
            ((f"❌ Bị từ chối ({counts['rejected']})", "c:cv:l:rejected"), (f"🚨 Cần kiểm tra ({counts['alert']})", "c:cv:l:alert")),
            ((f"🔄 Hoa hồng thay đổi ({counts['changed']})", "c:cv:l:changed"), ("🕘 Lịch sử", "c:cv:h")),
            BACK_SHOPEE,
        )
        return BotReply("\n".join(lines), inline_keyboard=keyboard)

    def listing(self, key: str) -> BotReply:
        label, where = LISTS[key]
        with self.repo.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT conversion_id, order_sn, item_name, net_commission_vnd, validation_status
                FROM shopee_conversions WHERE {_BOT} AND {where}
                ORDER BY COALESCE(purchase_time, created_at) DESC LIMIT 10
                """
            ).fetchall()
        lines = [_title("Shopee Affiliate", "Duyệt hoa hồng", label.split(" ", 1)[1]), ""]
        if not rows:
            lines.append(NO_APPROVAL_NOTE if key == "approved" else "Chưa có đơn nào trong mục này.")
        else:
            lines.append("Bấm một đơn để xem chi tiết và lịch sử.")
        buttons = []
        for row in rows:
            icon = STATUS_LABELS.get(row["validation_status"], "❔").split(" ", 1)[0]
            name = buyer_name(row["item_name"] or row["order_sn"] or "-")[:28]
            amount = "-" if row["net_commission_vnd"] is None else format_vnd(int(row["net_commission_vnd"]))
            buttons.append(((f"{icon} {name} · {amount}", f"c:cv:o:{row['conversion_id']}"),))
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, BACK_HOME_ROW))

    def detail(self, conversion_id: str, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            row = conn.execute(
                f"""
                SELECT c.*, u.username FROM shopee_conversions c
                LEFT JOIN telegram_users u ON u.telegram_user_id = c.telegram_user_id
                WHERE c.conversion_id = ? AND c.{_BOT}
                """,
                (conversion_id,),
            ).fetchone()
        if row is None:
            return BotReply("Không tìm thấy đơn qua bot này.", inline_keyboard=(BACK_HOME_ROW,))
        first, current = row["first_commission_vnd"], row["net_commission_vnd"]
        diff = "-" if first is None or current is None else format_vnd(int(current) - int(first))
        if first is not None and current is not None and current > first:
            diff = "+" + diff
        who = f"@{html.escape(row['username'])}" if row["username"] else f"<code>{row['telegram_user_id']}</code>"
        reason = REASON_LABELS.get(row["validation_reason"] or "", row["validation_reason"] or "-")
        lines = [_title("Shopee Affiliate", "Duyệt hoa hồng", "Chi tiết đơn"), ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"🛍️ {html.escape(buyer_name(row['item_name'] or '-'))}",
            f"• Mã đơn: <code>{html.escape(short_order(row['order_sn']))}</code> · Sub ID: <code>{html.escape(row['sub_id'] or '-')}</code>",
            f"• Người được ghi nhận: {who}",
            f"• Trạng thái đơn: <b>{_order_label(row['order_status'])}</b>",
            f"• Duyệt hoa hồng: <b>{STATUS_LABELS.get(row['validation_status'], row['validation_status'])}</b> · {html.escape(reason)}",
            "• Tiền Shopee đã trả: <b>chưa xác minh</b>",
            f"• Hoa hồng ban đầu: {_money(first)} · hiện tại: <b>{_money(current)}</b> · chênh: {diff}",
            f"• Đồng bộ gần nhất: {_vn(row['updated_at'])} · nguồn: báo cáo Shopee · độ tin cậy: suy luận",
        ]
        if row["review_status"] == "needs_review":
            lines.append("• 🔎 <b>Có cảnh báo chưa kiểm tra</b>")
        elif row["review_status"] == "reviewed":
            lines.append(f"• ✔️ Admin đã kiểm tra lúc {_vn(row['reviewed_at'])}")
        changes = self.repo.conversion_changes(conversion_id, limit=8)
        lines += ["", "🕘 <b>Lịch sử thay đổi</b>"]
        lines += [_change_line(change) for change in changes] or ["Chưa có thay đổi nào sau lần ghi nhận đầu."]
        keyboard = []
        if row["review_status"] == "needs_review":
            keyboard.append((("✔️ Đã kiểm tra cảnh báo", f"c:cv:ack:{conversion_id}"),))
        keyboard.append(BACK_HOME_ROW)
        return BotReply("\n".join(lines), inline_keyboard=tuple(keyboard))

    def acknowledge(self, admin_id: int, conversion_id: str, now: datetime) -> BotReply:
        """Chỉ đánh dấu đã xem cảnh báo. Không đổi hoa hồng, trạng thái duyệt hay quyền rút."""
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.repo.mark_conversion_reviewed(conversion_id, admin_id, stamp):
            return self.detail(conversion_id, "Không có cảnh báo nào đang chờ ở đơn này.")
        if self.audit is not None:
            self.audit(admin_id, "commission_review_ack", {"conversion": conversion_id, "review": "needs_review"},
                       {"conversion": conversion_id, "review": "reviewed"}, now)
        return self.detail(conversion_id, "✔️ Đã ghi nhận bạn đã kiểm tra cảnh báo.")

    def history(self) -> BotReply:
        with self.repo.connect() as conn:
            rows = conn.execute(
                """
                SELECT h.*, c.order_sn FROM shopee_conversion_changes h
                JOIN shopee_conversions c ON c.conversion_id = h.conversion_id
                WHERE c.matched_link_id IS NOT NULL
                ORDER BY h.id DESC LIMIT 15
                """
            ).fetchall()
        lines = [_title("Shopee Affiliate", "Duyệt hoa hồng", "Lịch sử"), ""]
        if not rows:
            lines.append("Chưa có thay đổi nào được ghi nhận.")
        for row in rows:
            lines.append(f"<code>{html.escape(short_order(row['order_sn']))}</code> {_change_line(row)}")
        return BotReply("\n".join(lines), inline_keyboard=(BACK_HOME_ROW,))


def _money(value) -> str:
    return "-" if value is None else format_vnd(int(value))


_FIELD_LABELS = {
    "net_commission_vnd": "hoa hồng",
    "order_status": "trạng thái đơn",
    "validation_status": "duyệt",
    "fraud_flag": "cờ gian lận",
    "attribution": "Sub ID trỏ link khác (giữ người cũ)",
}


def _change_line(row) -> str:
    field = row["field"]
    old, new = change_value(field, row["old_value"]), change_value(field, row["new_value"])
    if field == "validation_status":
        old = STATUS_LABELS.get(row["old_value"], old)
        new = STATUS_LABELS.get(row["new_value"], new)
    mark = "⚠️ " if row["significant"] else ""
    return f"• {_vn(row['detected_at'])} · {mark}{_FIELD_LABELS.get(field, field)}: {old} → <b>{new}</b>"
