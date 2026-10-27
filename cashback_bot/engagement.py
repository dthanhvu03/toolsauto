"""Nhắc mùa sale cho khách (reports/CASHBACK_SALE_REMINDERS.md). Chạy định kỳ trong vòng poll của bot Telegram.

- Tắt mặc định: admin bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale (`bot_state.sale_reminders_enabled`).
- Bot tự lập lịch (sale_calendar) và soạn tin, nhưng **không lượt nào tự gửi**: mỗi lượt admin bấm ✅ Duyệt gửi.
- Trước giờ gửi 48 giờ: báo admin một lần là có lượt chờ duyệt.
- Tới giờ (trễ tối đa 60 phút) mà đã duyệt: đưa vào hàng đợi chung cho từng khách (`category='reminder'`), Dispatcher
  áp tuỳ chọn /thongbao và chặn bot như mọi tin khách. Quá 60 phút thì bỏ lượt, không gửi muộn.
Trạng thái lượt ở `bot_state.sale_reminder:<ngày>:<eve|day>` (JSON): pending · approved · skipped · sent · missed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from cashback_bot import sale_calendar
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import sale_reminder
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason
from cashback_bot.sale_calendar import Slot

ENABLED_KEY = "sale_reminders_enabled"
STATE_PREFIX = "sale_reminder:"
NOTICE_BEFORE = timedelta(hours=48)
SEND_WINDOW = timedelta(minutes=60)
CATEGORY = "reminder"
STATUS_LABELS = {
    "pending": "⏳ Chờ duyệt",
    "approved": "✅ Đã duyệt",
    "skipped": "⏭ Bỏ qua",
    "sent": "📤 Đã gửi",
    "missed": "⚪ Lỡ giờ, không gửi",
}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(ENABLED_KEY) == "1"


def record(repo: TrackingRepository, slot_id: str) -> dict:
    try:
        return json.loads(repo.get_state(STATE_PREFIX + slot_id) or "{}")
    except ValueError:
        return {}


def save(repo: TrackingRepository, slot_id: str, data: dict) -> None:
    repo.set_state(STATE_PREFIX + slot_id, json.dumps(data, ensure_ascii=False, sort_keys=True))


def status(repo: TrackingRepository, slot: Slot) -> str:
    return record(repo, slot.id).get("status", "pending")


def template_kind(event: sale_calendar.SaleEvent) -> str:
    """Loại câu: siêu sale / đỉnh dùng chung câu «siêu sale»; còn lại theo loại dịp."""
    return "super" if event.kind == "double" and event.tier in ("peak", "super") else event.kind


def text_for(slot: Slot) -> str:
    return sale_reminder(template_kind(slot.event), slot.stage, slot.event.label, slot.id)


def recipients(conn: sqlite3.Connection) -> list[int]:
    """Khách đã từng tạo link, không tính khách đã chặn bot hay tắt nhắc mùa sale."""
    users = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created' ORDER BY telegram_user_id")]
    cfg = NotifyConfig(True)
    now = datetime.now(timezone.utc)
    return [u for u in users if customer_block_reason(conn, {"category": CATEGORY, "chat_id": u}, cfg, now) is None]


def tick(repo: TrackingRepository, admin_notifier, now: datetime) -> None:
    if not enabled(repo):
        return
    for slot in sale_calendar.upcoming(now, days=3):
        data = record(repo, slot.id)
        state = data.get("status", "pending")
        if state in ("skipped", "sent", "missed"):
            continue
        if now >= slot.at + SEND_WINDOW:
            save(repo, slot.id, {**data, "status": "missed", "at": _stamp(now)})
            continue
        if state == "approved" and now >= slot.at:
            _send(repo, slot, data, now)
            continue
        if state == "pending" and now >= slot.at - NOTICE_BEFORE and not data.get("noticed"):
            with repo.connect() as conn:
                count = len(recipients(conn))
            if admin_notifier is not None:
                admin_notifier.notify_sale_reminder_pending(slot, count)
            save(repo, slot.id, {**data, "status": "pending", "noticed": _stamp(now)})


def _send(repo: TrackingRepository, slot: Slot, data: dict, now: datetime) -> None:
    html = text_for(slot)
    stamp = _stamp(now)
    with repo.connect() as conn:
        users = recipients(conn)
        for user in users:
            enqueue_event(
                conn, event_key=f"sale_reminder:{slot.id}:{user}", event_type="SALE_REMINDER", chat_id=user,
                message_html=html, audience="customer", category=CATEGORY, source_ref=f"sale_reminder:{slot.id}",
                now=stamp,
            )
    save(repo, slot.id, {**data, "status": "sent", "sent": len(users), "at": stamp})
