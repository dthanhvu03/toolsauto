"""Màn /admin → 📩 Hỗ trợ (PLAN-077).

Xem ticket theo trạng thái, chi tiết kèm dữ liệu đối chiếu (link, snapshot chính sách, điều khoản, đơn Shopee,
trạng thái duyệt / đối soát, khoản ví), đổi trạng thái theo bảng cho phép, trả lời khách qua bot.
Chỉ đọc dữ liệu tiền: không có nút sửa hoa hồng, gán APPROVED / SETTLED, đổi sổ ví hay chi trả.
Chờ admin gõ lý do / câu trả lời lưu trong RAM (`waiting`), hết hạn 10 phút.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cashback_bot import insights, policy_snapshot, support, terms
from cashback_bot.admin.notify.admin_notify import short_order
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, fit_html
from cashback_bot.money import format_vnd

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:hp:home"
BACK_MENU = (("◀️ Tổng quan", "c:menu:home"),)
BACK_HOME = (("◀️ Hỗ trợ", HOME),)
WAIT_TTL = timedelta(minutes=10)
GROUPS = {
    "new": ("🆕 Mới", ("OPEN",)),
    "review": ("🔎 Đang xử lý", ("IN_REVIEW",)),
    "customer": ("💬 Chờ khách", ("WAITING_CUSTOMER",)),
    "shopee": ("⏳ Chờ Shopee", ("WAITING_SHOPEE",)),
    "done": ("✅ Đã kết luận", ("RESOLVED", "REJECTED", "CLOSED")),
}
STATUS_BUTTONS = {
    "IN_REVIEW": "🔎 Đang xử lý",
    "WAITING_CUSTOMER": "💬 Chờ khách",
    "WAITING_SHOPEE": "⏳ Chờ Shopee",
    "RESOLVED": "✅ Giải quyết",
    "REJECTED": "✖️ Không chấp nhận",
    "CLOSED": "🔒 Đóng",
}
SNAPSHOT_LABELS = {
    "captured": "đã chốt lúc tạo link",
    "backfilled": "dựng lại, khớp số đã báo",
    "unresolved": "⚠️ chưa xác định chính sách",
}
TERMS_LABELS = {
    "LEGACY_NOT_RECORDED": "link trước khi có điều khoản phiên bản",
    "NO_PUBLISHED_TERMS": "lúc tạo link chưa có điều khoản công bố",
    "ACCEPTED": "đã đồng ý",
    "NOT_ACCEPTED": "chưa đồng ý",
}
_LIST = re.compile(r"^c:hp:l:(new|review|customer|shopee|done)$")
_TICKET = re.compile(r"^c:hp:(t|r):(\d{1,9})$")
_STATUS = re.compile(r"^c:hp:s:(\d{1,9}):(IN_REVIEW|WAITING_CUSTOMER|WAITING_SHOPEE|RESOLVED|REJECTED|CLOSED)$")


def _vn(stamp: str | None) -> str:
    if not stamp:
        return "-"
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return moment.astimezone(ICT).strftime("%H:%M %d/%m")


# Rà soát 2026-10-26: màn ticket không hiện mã thô (user:111 · open, PENDING, NOT_VERIFIED, v1.1:70…).
ACTION_WORDS = {"open": "mở yêu cầu", "status": "đổi trạng thái", "reply": "trả lời khách",
                "customer_reply": "khách bổ sung"}
SETTLEMENT_WORDS = {"SETTLED": "đã đối soát", "NOT_VERIFIED": "chưa xác minh"}
ENTRY_WORDS = {"pending": "chờ", "holding": "đang giữ", "available": "đã vào ví", "cancelled": "không được hoàn"}


def _actor(actor: str | None) -> str:
    kind = (actor or "").split(":", 1)[0]
    return {"user": "Khách", "admin": "Admin"}.get(kind, html.escape(actor or "-"))


def _status(code: str | None) -> str:
    return support.STATUS_LABELS.get(code or "", code or "-")


def _policy_name(label: str | None) -> str:
    """«v1.1:70» → «V1.1 · 70%»; «v1.2-reserve-…» → «V1.2»."""
    text = label or "-"
    if text.startswith("v1.1:"):
        return f"V1.1 · {text.split(':', 1)[1]}%"
    return "V1.2" if text.startswith("v1.2") else text

class SupportAdmin:
    def __init__(self, repo: TrackingRepository, waiting: dict[int, tuple[str, int, str, datetime]], audit=None):
        self.repo = repo
        # admin_id → (việc, ticket_id, trạng thái đích hoặc "", hạn chờ)
        self.waiting = waiting
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data != HOME and not data.startswith("c:hp:s:") and not data.startswith("c:hp:r:"):
            self.waiting.pop(admin_id, None)
        if data == HOME:
            self.waiting.pop(admin_id, None)
            return self._home()
        if (matched := _LIST.fullmatch(data)) is not None:
            return self._list(matched.group(1))
        if (matched := _TICKET.fullmatch(data)) is not None:
            ticket_id = int(matched.group(2))
            if matched.group(1) == "t":
                return self._ticket(ticket_id)
            return self._ask(admin_id, "reply", ticket_id, "", now)
        if (matched := _STATUS.fullmatch(data)) is not None:
            ticket_id, target = int(matched.group(1)), matched.group(2)
            if target in support.NEEDS_REASON:
                return self._ask(admin_id, "status", ticket_id, target, now)
            return self._apply(admin_id, ticket_id, target, None, now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME,))

    # --- Màn ------------------------------------------------------------------------------

    def _home(self, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            counts = support.counts(conn)
        lines = [
            "⚙️ Quản trị › <b>Hỗ trợ &amp; khiếu nại</b>",
            "",
        ]
        if notice:
            lines += [notice, ""]
        rows = []
        for code, (label, statuses) in GROUPS.items():
            total = sum(counts[status] for status in statuses)
            lines.append(f"{label}: <b>{total}</b>")
            rows.append(((f"{label} ({total})", f"c:hp:l:{code}"),))
        lines += [
            "",
            "ⓘ Ticket chỉ để kiểm tra và trả lời. Không sửa được hoa hồng, trạng thái duyệt, sổ ví hay chi trả. "
            "Chưa có thời hạn xử lý chính thức (chờ chủ bot duyệt).",
        ]
        return BotReply("\n".join(lines), inline_keyboard=(*rows, BACK_MENU))

    def _list(self, group: str) -> BotReply:
        label, statuses = GROUPS[group]
        with self.repo.connect() as conn:
            tickets = support.by_status(conn, statuses)
        if not tickets:
            return BotReply(f"⚙️ Quản trị › Hỗ trợ › <b>{label}</b>\n\nKhông có yêu cầu nào.", inline_keyboard=(BACK_HOME,))
        rows = tuple(
            ((f"#{t.id} · {support.CATEGORIES.get(t.category, t.category)[:22]} · {_vn(t.updated_at)}", f"c:hp:t:{t.id}"),)
            for t in tickets
        )
        text = f"⚙️ Quản trị › Hỗ trợ › <b>{label}</b>\n\n10 yêu cầu gần nhất, mới cập nhật trước."
        return BotReply(text, inline_keyboard=(*rows, BACK_HOME))

    def _ticket(self, ticket_id: int, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            ticket = support.get(conn, ticket_id)
            if ticket is None:
                return BotReply("Không thấy yêu cầu này.", inline_keyboard=(BACK_HOME,))
            user = conn.execute(
                "SELECT username FROM telegram_users WHERE telegram_user_id = ?", (ticket.telegram_user_id,)
            ).fetchone()
            facts = self._facts(conn, ticket)
            history = support.events(conn, ticket_id)
        who = f"@{html.escape(user[0])}" if user and user[0] else "chưa có username"
        lines = [
            f"⚙️ Quản trị › Hỗ trợ › <b>#{ticket.id}</b>",
            "",
        ]
        if notice:
            lines += [notice, ""]
        lines += [
            f"{support.CATEGORIES.get(ticket.category, ticket.category)} · {support.STATUS_LABELS[ticket.status]}",
            f"Khách: {who} · <code>{ticket.telegram_user_id}</code>",
            f"Mở {_vn(ticket.created_at)} · cập nhật {_vn(ticket.updated_at)}",
            "",
            f"<i>{html.escape(ticket.message)}</i>",
        ]
        if ticket.resolution:
            lines += ["", f"Kết luận: {html.escape(ticket.resolution)}"]
        lines += ["", "🔎 <b>Dữ liệu đối chiếu</b> (chỉ đọc)"] + facts
        lines += ["", "🕘 <b>Lịch sử</b>"] + [
            f"• {_vn(row['created_at'])} {_actor(row['actor'])} · {ACTION_WORDS.get(row['action'], row['action'])}"
            + (f" {_status(row['from_status'])} → {_status(row['to_status'])}" if row["action"] == "status" else "")
            + (f": {html.escape(str(row['note'])[:120])}" if row["note"] else "")
            for row in history[-6:]
        ]
        rows = [
            ((label, f"c:hp:s:{ticket.id}:{target}"),)
            for target, label in STATUS_BUTTONS.items()
            if target in support.TRANSITIONS[ticket.status]
        ]
        if ticket.status != "CLOSED":
            rows.insert(0, (("💬 Trả lời khách", f"c:hp:r:{ticket.id}"),))
        text = "\n".join(lines)
        return BotReply(fit_html(text), inline_keyboard=(*rows, BACK_HOME))

    def _facts(self, conn, ticket: support.Ticket) -> list[str]:
        """Dữ liệu chỉ của chính khách mở ticket: link gắn với ticket, đơn gắn với ticket, 5 link gần nhất."""
        lines: list[str] = []
        link_ids = []
        if ticket.link_id:
            link_ids.append(int(ticket.link_id))
        recent = conn.execute(
            "SELECT id FROM link_requests WHERE telegram_user_id = ? AND link_status = 'created' ORDER BY id DESC LIMIT 3",
            (ticket.telegram_user_id,),
        ).fetchall()
        link_ids += [int(row[0]) for row in recent if int(row[0]) not in link_ids]
        if not link_ids:
            lines.append("• Khách chưa tạo link nào.")
        for link_id in link_ids:
            link = conn.execute("SELECT * FROM link_requests WHERE id = ?", (link_id,)).fetchone()
            found = policy_snapshot.load(conn, link_id)
            status, version, _accepted = terms.link_terms(conn, link_id)
            snap = ("chưa lưu cách tính" if found is None else
                    f"{SNAPSHOT_LABELS.get(found.provenance, found.provenance)} ({html.escape(_policy_name(found.label))})")
            mark = "📌" if link_id == ticket.link_id else "•"
            # Click theo báo cáo Shopee (tới lần đồng bộ gần nhất), khớp sub_id của link.
            clicks = conn.execute("SELECT COUNT(*) FROM shopee_clicks WHERE sub_id = ?", (link["sub_id"],)).fetchone()[0]
            lines.append(
                f"{mark} Link <code>{html.escape(link['sub_id'] or '-')}</code> {_vn(link['created_at'])} · "
                f"{clicks} click · "
                f"báo {format_vnd(int(link['estimated_cashback'] or 0))} · {snap} · điều khoản: "
                f"{TERMS_LABELS[status]}{'' if version is None else ' ' + html.escape(version.version)}"
            )
            orders = conn.execute(
                """
                SELECT c.conversion_id, c.order_sn, c.order_status, c.validation_status, c.settlement_status,
                       e.cashback_vnd, e.status AS entry_status
                FROM shopee_conversions c LEFT JOIN cashback_entries e ON e.conversion_id = c.conversion_id
                WHERE c.matched_link_id = ? AND c.telegram_user_id = ?
                """,
                (link_id, ticket.telegram_user_id),
            ).fetchall()
            for order in orders:
                lines.append(
                    f"   ↳ Đơn …{html.escape(short_order(order['order_sn']))} · {insights.status_word(order['order_status'])} · "
                    f"duyệt: {insights.status_word(order['validation_status'])} · "
                    f"đối soát: {SETTLEMENT_WORDS.get(order['settlement_status'] or '', '-')} · "
                    f"ví: {ENTRY_WORDS.get(order['entry_status'] or '', '-')} {format_vnd(int(order['cashback_vnd'] or 0))}"
                )
        if ticket.conversion_id and not any(ticket.conversion_id in line for line in lines):
            lines.append(f"📌 Đơn gắn với ticket: <code>{html.escape(short_order(ticket.conversion_id))}</code>")
        return lines

    # --- Thao tác ---------------------------------------------------------------------------

    def _ask(self, admin_id: int, job: str, ticket_id: int, target: str, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            ticket = support.get(conn, ticket_id)
        if ticket is None:
            return BotReply("Không thấy yêu cầu này.", inline_keyboard=(BACK_HOME,))
        if job == "status" and target not in support.TRANSITIONS[ticket.status]:
            return self._ticket(ticket_id, "⚠️ Không chuyển được sang trạng thái này từ trạng thái hiện tại.")
        if job == "reply" and ticket.status == "CLOSED":
            return self._ticket(ticket_id, "⚠️ Ticket đã đóng.")
        self.waiting[admin_id] = (job, ticket_id, target, now + WAIT_TTL)
        if job == "reply":
            ask = f"✍️ Gõ câu trả lời gửi khách cho #{ticket_id} (tối đa 1.000 ký tự). Bot gửi đúng nội dung này."
        else:
            ask = f"✍️ Gõ lý do chuyển #{ticket_id} sang <b>{support.STATUS_LABELS[target]}</b>. Khách sẽ thấy lý do này."
        return BotReply(ask + "\nChờ trong 10 phút.", inline_keyboard=((("✖️ Hủy", f"c:hp:t:{ticket_id}"),),))

    def consume_text(self, admin_id: int, text: str, now: datetime) -> BotReply | None:
        job = self.waiting.get(admin_id)
        if job is None:
            return None
        kind, ticket_id, target, deadline = job
        stripped = (text or "").strip()
        if deadline <= now or not stripped or stripped.startswith("/"):
            self.waiting.pop(admin_id, None)
            return None
        self.waiting.pop(admin_id, None)
        if kind == "reply":
            return self._reply(admin_id, ticket_id, stripped, now)
        return self._apply(admin_id, ticket_id, target, stripped, now)

    def _apply(self, admin_id: int, ticket_id: int, target: str, note: str | None, now: datetime) -> BotReply:
        try:
            with self.repo.connect() as conn:
                ticket = support.transition(conn, ticket_id, admin_id, target, note, now)
        except support.SupportError as exc:
            code = exc.args[0] if exc.args else ""
            message = {"reason": "Cần lý do.", "transition": "Không chuyển được từ trạng thái hiện tại."}.get(code, "Không thấy yêu cầu.")
            return self._ticket(ticket_id, f"⚠️ {message}")
        if target in {"RESOLVED", "REJECTED", "WAITING_CUSTOMER", "WAITING_SHOPEE"}:
            self._tell_customer(ticket, f"Trạng thái: {support.STATUS_LABELS[target]}" + (f"\n{html.escape(note)}" if note else ""), now)
        return self._ticket(ticket_id, f"✅ Đã chuyển sang {support.STATUS_LABELS[target]}.")

    def _reply(self, admin_id: int, ticket_id: int, text: str, now: datetime) -> BotReply:
        try:
            with self.repo.connect() as conn:
                ticket, reply = support.admin_reply(conn, ticket_id, admin_id, text, now)
        except support.SupportError:
            return self._ticket(ticket_id, "⚠️ Không gửi được: ticket đã đóng hoặc nội dung rỗng.")
        self._tell_customer(ticket, html.escape(reply), now)
        return self._ticket(ticket_id, "✅ Đã gửi trả lời cho khách.")

    def _tell_customer(self, ticket: support.Ticket, body_html: str, now: datetime) -> None:
        """Một tin riêng cho chủ ticket qua hàng đợi gửi của bot. Không gửi cho ai khác."""
        self.repo.enqueue_admin_event(
            event_key=f"support_customer:{ticket.id}:{now.timestamp():.0f}",
            event_type="SUPPORT_CUSTOMER",
            chat_id=ticket.telegram_user_id,
            message_html=(
                f"📩 <b>Yêu cầu hỗ trợ #{ticket.id}</b>\n\n{body_html}\n\n"
                "Xem lại hoặc bổ sung: /hotro → 🗂 Yêu cầu của tôi"
            ),
        )
