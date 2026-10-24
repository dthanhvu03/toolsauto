"""Màn /admin → 🔔 Thông báo khách (PLAN-079). Theo dõi hàng đợi tin gửi khách.

Xem số tin theo trạng thái và loại, lý do lỗi / bỏ qua, khách chặn bot, khách tắt thông báo, xem mẫu tin.
Thao tác ghi: gửi lại một tin cụ thể đang 'failed' hoặc 'unknown' (đúng sự kiện đó, không tạo sự kiện mới, vẫn áp
tuỳ chọn của khách lúc gửi); và 🧪 tin thử Gate B, chỉ tới tài khoản trong CUSTOMER_NOTIFICATIONS_TEST_IDS, đi qua
đúng bộ gửi và các điều kiện của tin đơn thật. Không có nút gửi hàng loạt, sửa đơn, gán APPROVED / SETTLED hay tạo
khoản chi.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BotReply, order_new_notice, order_update_notice
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason
from cashback_bot.order_notify import BASELINE_KEY, HISTORY_KEY

HOME = "c:nt:home"
BACK_MENU = (("◀️ Tổng quan", "c:menu:home"),)
BACK_HOME = (("◀️ Thông báo khách", HOME),)
STATUS_LABELS = {
    "pending": "⏳ Chờ gửi", "retry": "🔁 Chờ thử lại", "sending": "📤 Đang gửi", "sent": "✅ Đã gửi",
    "failed": "❌ Gửi lỗi", "unknown": "❔ Không rõ kết quả", "suppressed": "⏭ Bỏ qua",
}
CATEGORY_LABELS = {"order_new": "đơn mới", "order_update": "cập nhật đơn", "support": "hỗ trợ", "wallet": "ví / chi trả"}
REASON_LABELS = {
    "feature_off": "cờ thông báo đơn đang tắt", "historical": "đơn trước mốc kích hoạt", "pref_off": "khách tắt loại tin",
    "blocked": "khách đã chặn bot", "not_started": "khách chưa bắt đầu bot", "stale": "tin quá cũ",
    "interrupted_while_sending": "bot dừng giữa lúc gửi", "not_test_account": "không phải tài khoản test",
    "before_activation": "ghi trước lần bật gần nhất", "no_purchase_time": "Shopee không trả thời điểm mua",
}
MODE_LABELS = {"off": "TẮT", "test": "THỬ VỚI TÀI KHOẢN TEST", "on": "BẬT cho mọi khách"}
_LIST = re.compile(r"^c:nt:l:(failed|unknown|suppressed|pending)$")
_RETRY = re.compile(r"^c:nt:r:(\d{1,9})(:ok)?$")
_SMOKE = re.compile(r"^c:nt:s:(n|r):(\d{1,15})$")
SMOKE_BODY = "🧪 <b>Tin thử của chủ bot</b>: không phải đơn thật, không có tiền.\n\n"
SMOKE_MARKUP = json.dumps({"inline_keyboard": [[
    {"text": "📦 Đơn hàng của tôi", "callback_data": "u:o:l:1"}, {"text": "📩 Hỗ trợ", "callback_data": "u:p:support"},
]]})


def _reason(error: str | None) -> str:
    if not error:
        return "-"
    return REASON_LABELS.get(error, html.escape(error[:60]))


class CustomerNotifyAdmin:
    def __init__(self, repo: TrackingRepository, customer_enabled: bool, audit=None, test_ids: frozenset[int] = frozenset()):
        self.repo = repo
        self.customer_enabled = customer_enabled
        self.audit = audit
        self.cfg = NotifyConfig(customer_enabled, test_ids)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home()
        if data == "c:nt:pv":
            return self._preview()
        if (matched := _LIST.fullmatch(data)) is not None:
            return self._list(matched.group(1))
        if (matched := _RETRY.fullmatch(data)) is not None:
            return self._retry(admin_id, int(matched.group(1)), bool(matched.group(2)), now)
        if data == "c:nt:s":
            return self._smoke_page()
        if (matched := _SMOKE.fullmatch(data)) is not None:
            return self._smoke(admin_id, matched.group(1) == "r", int(matched.group(2)), now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME,))

    def _home(self, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            counts = dict(conn.execute(
                "SELECT status, COUNT(*) FROM admin_notifications WHERE audience = 'customer' GROUP BY status"
            ).fetchall())
            categories = conn.execute(
                "SELECT category, COUNT(*) FROM admin_notifications WHERE audience = 'customer' AND status = 'sent' "
                "GROUP BY category"
            ).fetchall()
            blocked = int(conn.execute("SELECT COUNT(*) FROM telegram_users WHERE notify_blocked_at IS NOT NULL").fetchone()[0])
            opted_out = int(conn.execute(
                "SELECT COUNT(*) FROM customer_notification_prefs WHERE orders = 0 OR updates = 0 OR support = 0 OR wallet = 0"
            ).fetchone()[0])
            last = conn.execute(
                "SELECT MAX(sent_at) FROM admin_notifications WHERE audience = 'customer' AND status = 'sent'"
            ).fetchone()[0]
            baseline = conn.execute("SELECT value FROM bot_state WHERE key = ?", (BASELINE_KEY,)).fetchone()
            history = conn.execute("SELECT value FROM bot_state WHERE key = ?", (HISTORY_KEY,)).fetchone()
        mode = "off" if not self.cfg.enabled else "test" if self.cfg.test_ids else "on"
        lines = ["⚙️ Quản trị › <b>Thông báo khách</b>", ""]
        if notice:
            lines += [notice, ""]
        lines.append(
            f"Thông báo đơn hàng tự động: <b>{MODE_LABELS[mode]}</b>"
            + (" (cờ CUSTOMER_NOTIFICATIONS_ENABLED, chờ chủ bot duyệt)" if mode == "off" else "")
            + (f" · {len(self.cfg.test_ids)} tài khoản" if mode == "test" else "")
        )
        if mode != "off":
            lines.append(f"Mốc kích hoạt: {baseline[0] if baseline else 'chưa có'} (đơn mua trước mốc không báo «đơn mới»)")
        changes = json.loads(history[0]) if history else []
        if changes:
            lines.append("Đổi chế độ gần đây: " + " · ".join(
                f"{c['at'][5:16].replace('T', ' ')} {MODE_LABELS.get(c.get('mode'), c.get('mode'))}" for c in changes[-3:]
            ))
        lines.append("")
        lines += [f"{label}: <b>{int(counts.get(status, 0))}</b>" for status, label in STATUS_LABELS.items()]
        if categories:
            lines.append("Đã gửi theo loại: " + " · ".join(f"{CATEGORY_LABELS.get(c, c)} {n}" for c, n in categories))
        lines += [
            f"Khách chặn bot: <b>{blocked}</b> · khách tắt ít nhất một loại tin: <b>{opted_out}</b>",
            f"Gửi gần nhất: {last or 'chưa có'}",
            "",
            "ⓘ Chỉ gửi tin khi dữ liệu đơn đã ghi. Tin không rõ kết quả không tự gửi lại để tránh trùng.",
        ]
        rows = [
            (("❌ Gửi lỗi", "c:nt:l:failed"), ("❔ Không rõ", "c:nt:l:unknown")),
            (("⏭ Bỏ qua", "c:nt:l:suppressed"), ("⏳ Chờ gửi", "c:nt:l:pending")),
            (("👁 Xem mẫu tin", "c:nt:pv"),),
        ]
        if self.cfg.test_ids:
            rows.append((("🧪 Tin thử tới tài khoản test", "c:nt:s"),))
        rows.append(BACK_MENU)
        return BotReply("\n".join(lines), inline_keyboard=tuple(rows))

    def _list(self, status: str) -> BotReply:
        statuses = ("pending", "retry") if status == "pending" else (status,)
        marks = ", ".join("?" for _ in statuses)
        with self.repo.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM admin_notifications WHERE audience = 'customer' AND status IN ({marks}) "
                "ORDER BY id DESC LIMIT 8",
                statuses,
            ).fetchall()
        lines = [f"⚙️ Quản trị › Thông báo khách › <b>{STATUS_LABELS[status]}</b>", ""]
        lines += [
            f"• #{row['id']} {CATEGORY_LABELS.get(row['category'], row['category'] or '-')} · khách <code>{row['chat_id']}</code> · "
            f"{row['created_at'][5:16].replace('T', ' ')} · {_reason(row['last_error'])}"
            for row in rows
        ] or ["Không có tin nào."]
        buttons = [((f"🔁 Gửi lại #{row['id']}", f"c:nt:r:{row['id']}"),) for row in rows if status in ("failed", "unknown")]
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, BACK_HOME))

    def _retry(self, admin_id: int, event_id: int, confirmed: bool, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT * FROM admin_notifications WHERE id = ? AND audience = 'customer'", (event_id,)
            ).fetchone()
        if row is None or row["status"] not in ("failed", "unknown"):
            return self._home("⚠️ Chỉ gửi lại được tin đang «gửi lỗi» hoặc «không rõ kết quả».")
        if not confirmed:
            warn = (
                "⚠️ Tin này có thể đã tới khách (Telegram không trả kết quả). Gửi lại có thể thành 2 tin.\n\n"
                if row["status"] == "unknown" else ""
            )
            text = (
                f"🔁 <b>Gửi lại tin #{event_id}</b> ({CATEGORY_LABELS.get(row['category'], row['category'])})\n\n"
                + warn
                + "Gửi lại đúng tin của sự kiện này; vẫn áp lựa chọn thông báo của khách lúc gửi."
            )
            return BotReply(text, inline_keyboard=(
                (("✅ Gửi lại", f"c:nt:r:{event_id}:ok"),), (("◀️ Quay lại", f"c:nt:l:{row['status']}"),),
            ))
        with self.repo.connect() as conn:
            conn.execute(
                "UPDATE admin_notifications SET status = 'pending', attempt_count = 0, next_retry_at = NULL "
                "WHERE id = ? AND status IN ('failed', 'unknown')",
                (event_id,),
            )
        if self.audit:
            self.audit(admin_id, "customer_notify_retry", None, {"id": event_id}, now)
        return self._home(f"🔁 Đã xếp gửi lại tin #{event_id}.")

    def _smoke_page(self, notice: str = "") -> BotReply:
        if not self.cfg.test_ids:
            return self._home("⚠️ Chưa có CUSTOMER_NOTIFICATIONS_TEST_IDS nên không có tin thử.")
        lines = ["⚙️ Quản trị › Thông báo khách › <b>Tin thử</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            "Tin thử là một tin «đơn mới» mẫu, chỉ gửi tới tài khoản test, đi qua đúng bộ gửi của tin thật: cờ, tuỳ chọn",
            "/thongbao của tài khoản đó, chặn bot, thử lại.",
            "• 🧪 Sự kiện mới: tạo một sự kiện thử mới.",
            "• ♻️ Xử lý lại: ghi lại đúng sự kiện thử gần nhất, để kiểm tra chống trùng (không được thành tin thứ hai).",
        ]
        rows = [
            ((f"🧪 Sự kiện mới · {uid}", f"c:nt:s:n:{uid}"), (f"♻️ Xử lý lại · {uid}", f"c:nt:s:r:{uid}"))
            for uid in sorted(self.cfg.test_ids)
        ]
        return BotReply("\n".join(lines), inline_keyboard=(*rows, BACK_HOME))

    def _smoke(self, admin_id: int, repeat: bool, chat_id: int, now: datetime) -> BotReply:
        if chat_id not in self.cfg.test_ids:
            return self._home("⚠️ Chỉ gửi tin thử tới tài khoản trong CUSTOMER_NOTIFICATIONS_TEST_IDS.")
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.repo.connect() as conn:
            count = int(conn.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE event_key LIKE ?", (f"smoke:{chat_id}:%",)
            ).fetchone()[0])
            if repeat and count == 0:
                return self._smoke_page("⚠️ Tài khoản này chưa có sự kiện thử để xử lý lại.")
            key = f"smoke:{chat_id}:{count if repeat else count + 1}"
            row = {"category": "order_new", "chat_id": chat_id, "created_at": stamp}
            reason = customer_block_reason(conn, row, self.cfg, now)
            enqueue_event(
                conn, event_key=key, event_type="ORDER_SMOKE", chat_id=chat_id,
                message_html=SMOKE_BODY + order_new_notice("••••TEST", 1_000, "PENDING", "PENDING"),
                audience="customer", category="order_new", reply_markup_json=SMOKE_MARKUP, source_ref="smoke",
                suppressed_reason=reason, now=stamp,
            )
            saved = conn.execute("SELECT id, status, last_error, created_at FROM admin_notifications WHERE event_key = ?",
                                 (key,)).fetchone()
            total = int(conn.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE event_key LIKE ?", (f"smoke:{chat_id}:%",)
            ).fetchone()[0])
        if self.audit:
            self.audit(admin_id, "customer_notify_smoke", None, {"chat_id": chat_id, "key": key, "repeat": repeat}, now)
        state = STATUS_LABELS.get(saved["status"], saved["status"])
        if repeat:
            notice = (
                f"♻️ Sự kiện <code>{key}</code> đã có (#{saved['id']}, {state}). Không tạo tin thứ hai: "
                f"tài khoản này vẫn có {total} sự kiện thử."
            )
        else:
            notice = f"🧪 Đã xếp tin thử #{saved['id']} cho <code>{chat_id}</code>: {state}"
            if saved["status"] == "suppressed":
                notice += f" ({_reason(saved['last_error'])})"
        return self._smoke_page(notice)

    def _preview(self) -> BotReply:
        samples = [
            ("Đơn mới", order_new_notice("••••0309", 12_157, "PENDING", "PENDING")),
            ("Hoa hồng đổi", order_update_notice("••••0309", statuses=[], ineligible=False, approved=False,
                                                 old_cashback=12_157, new_cashback=8_400)),
            ("Không đủ điều kiện", order_update_notice("••••0309", statuses=[], ineligible=True, approved=False,
                                                       old_cashback=None, new_cashback=None)),
            ("Đã duyệt (mẫu, chưa có nguồn APPROVED nên chưa dùng)", order_update_notice(
                "••••0309", statuses=[], ineligible=False, approved=True, old_cashback=None, new_cashback=None)),
        ]
        text = "⚙️ Quản trị › Thông báo khách › <b>Mẫu tin</b>\n\nSố liệu trong mẫu là ví dụ.\n\n" + "\n\n— — —\n\n".join(
            f"<i>{title}</i>\n{body}" for title, body in samples
        )
        return BotReply(text[:4000], inline_keyboard=(BACK_HOME,))
