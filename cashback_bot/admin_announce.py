"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 📣 Tin giới thiệu: chủ bot tự bấm gửi tin giới thiệu tính năng mới.

Gửi hàng loạt tới khách thật nên chỉ chủ bot bấm (không có lệnh tự động). Mỗi tin có mã riêng; mỗi khách chỉ nhận một
lần (khoá `announce:<mã>:<khách>`), bấm gửi lại chỉ gửi cho khách chưa nhận. Thêm tin mới: thêm một mục vào ANNOUNCEMENTS.
Người nhận: khách đã từng tạo link, chưa chặn bot. Ghi 📊 Lịch sử action `announce`.
Callback: c:an:home · c:an:v:<mã> · c:an:ok:<mã>.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import (
    DEALS_ANNOUNCE,
    DEALS_ANNOUNCE_KEYBOARD,
    WALLET_ANNOUNCE,
    WALLET_ANNOUNCE_KEYBOARD,
    BotReply,
    Keyboard,
)
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason

HOME = "c:an:home"
CATEGORY = "announce"
_ACTION = re.compile(r"^c:an:(v|ok):([a-z0-9-]+)$")
NAV = ((("◀️ Nhắc mùa sale", "c:eg:home"), ("◀️ Tổng quan", "c:menu:home")),)
# mã → (tên, nội dung, nút)
ANNOUNCEMENTS: dict[str, tuple[str, str, Keyboard]] = {
    "deals-v1": ("Deal hời 20:08 · báo giảm giá · TikTok Shop", DEALS_ANNOUNCE, DEALS_ANNOUNCE_KEYBOARD),
    "wallet-v1": ("Ví hoàn tiền xem trước · điều khoản V3", WALLET_ANNOUNCE, WALLET_ANNOUNCE_KEYBOARD),
}

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    title = ANNOUNCEMENTS.get(str(after.get("id")), (str(after.get("id")),))[0]
    return f"Tin giới thiệu «{title}»: gửi {after.get('queued', 0)} khách mới (tổng {after.get('total', 0)})"


def recipients(conn: sqlite3.Connection, now: datetime) -> list[int]:
    users = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created' ORDER BY telegram_user_id")]
    cfg = NotifyConfig(True)
    return [u for u in users if customer_block_reason(conn, {"category": CATEGORY, "chat_id": u}, cfg, now) is None]


def sent_count(conn: sqlite3.Connection, key: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_key LIKE ?",
                            (f"announce:{key}:%",)).fetchone()[0])


class AnnounceAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home(now)
        found = _ACTION.fullmatch(data)
        if found is None or found.group(2) not in ANNOUNCEMENTS:
            return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)
        key = found.group(2)
        if found.group(1) == "v":
            return self._preview(key, now)
        queued, total = self._send(key, now)
        if self.audit is not None:
            self.audit(admin_id, "announce", {}, {"id": key, "queued": queued, "total": total}, now)
        notice = (f"✅ Đã đưa {queued} tin vào hàng đợi, bot gửi ngay (Telegram và Zalo)." if queued
                  else "Mọi khách đã nhận tin này rồi, không gửi thêm.")
        return self._preview(key, now, notice)

    def _send(self, key: str, now: datetime) -> tuple[int, int]:
        _title, text, keyboard = ANNOUNCEMENTS[key]
        markup = json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in keyboard]},
                            ensure_ascii=False)
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        queued = 0
        with self.repo.connect() as conn:
            for user in recipients(conn, now):
                queued += enqueue_event(
                    conn, event_key=f"announce:{key}:{user}", event_type="ANNOUNCE", chat_id=user, message_html=text,
                    audience="customer", category=CATEGORY, reply_markup_json=markup, source_ref=f"announce:{key}",
                    now=stamp,
                )
            total = sent_count(conn, key)
        return queued, total

    def _home(self, now: datetime) -> BotReply:
        lines = ["📣 <b>Tin giới thiệu tính năng</b>", "",
                 "Gửi một lần cho khách đã từng tạo link. Bấm để xem trước rồi mới gửi.", ""]
        rows = []
        with self.repo.connect() as conn:
            people = len(recipients(conn, now))
            for key, (title, _text, _kb) in ANNOUNCEMENTS.items():
                done = sent_count(conn, key)
                lines.append(f"• {title}: đã gửi {done} · còn {max(people - done, 0)} khách chưa nhận")
                rows.append(((f"👁 {title}", f"c:an:v:{key}"),))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *NAV))

    def _preview(self, key: str, now: datetime, notice: str = "") -> BotReply:
        title, text, _keyboard = ANNOUNCEMENTS[key]
        with self.repo.connect() as conn:
            people = recipients(conn, now)
            done = {int(r[0]) for r in conn.execute(
                "SELECT chat_id FROM admin_notifications WHERE event_key LIKE ?", (f"announce:{key}:%",))}
        waiting = [u for u in people if u not in done]
        tele, zalo = sum(u > 0 for u in waiting), sum(u < 0 for u in waiting)
        lines = [f"📣 <b>{title}</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [f"Sẽ gửi: <b>{len(waiting)} khách</b> chưa nhận ({tele} Telegram, {zalo} Zalo) · đã gửi {len(done)}",
                  "", "<b>Khách sẽ nhận:</b>", f"<blockquote>{text}</blockquote>"]
        buttons = [((f"✅ Gửi {len(waiting)} khách", f"c:an:ok:{key}"),)] if waiting else []
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, (("◀️ Tin giới thiệu", HOME),), *NAV))
