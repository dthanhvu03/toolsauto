"""Nhắc mùa sale cho khách (reports/CASHBACK_SALE_REMINDERS.md). Chạy định kỳ trong vòng poll của bot Telegram.

- Tắt mặc định: admin bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale (`bot_state.sale_reminders_enabled`).
- Bot tự lập lịch (sale_calendar) và soạn tin, nhưng **không lượt nào tự gửi**: mỗi lượt admin bấm ✅ Duyệt gửi.
- Trước giờ gửi 48 giờ: báo admin một lần là có lượt chờ duyệt.
- Tới giờ (trễ tối đa 60 phút) mà đã duyệt: đưa vào hàng đợi chung cho từng khách (`category='reminder'`), Dispatcher
  áp tuỳ chọn /thongbao và chặn bot như mọi tin khách. Quá 60 phút thì bỏ lượt, không gửi muộn.
Trạng thái lượt ở `bot_state.sale_reminder:<ngày>:<eve|day>` (JSON): pending · approved · skipped · sent · missed.
Khách quá 21 ngày không tạo link: tin nhắc sale có thêm câu mở đầu «Lâu rồi hông thấy bạn ghé», không gửi tin riêng.

Nhắc link chưa dùng (`bot_state.link_nudge_enabled`, tắt mặc định, chủ bot duyệt luật 2026-10-27): tự gửi theo luật,
không duyệt từng tin.
- Link mới nhất của khách, có hoàn, tạo 24–72 giờ trước, chưa có đơn nào khớp (không dựa vào click: về trễ ~1 ngày).
- Chỉ gửi 19:00–21:30 giờ VN; mỗi khách tối đa 1 tin / 7 ngày; mỗi link 1 lần; bỏ nếu trong 24 giờ có lượt nhắc sale.
- Dùng chung mục 🛒 Nhắc ở /thongbao và luật chặn bot như mọi tin khách.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta, timezone

from cashback_bot import sale_calendar
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BUY_BUTTON, TIKTOK_BUY_BUTTON, link_nudge, sale_reminder
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason
from cashback_bot.sale_calendar import Slot

ENABLED_KEY = "sale_reminders_enabled"
NUDGE_KEY = "link_nudge_enabled"
DORMANT_AFTER = timedelta(days=21)
NUDGE_AGE = (timedelta(hours=24), timedelta(hours=72))
NUDGE_GAP = timedelta(days=7)
NUDGE_HOURS = (time(19, 0), time(21, 30))
NUDGE_LIMIT = 20
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


def nudge_enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(NUDGE_KEY) == "1"


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


def text_for(slot: Slot, dormant: bool = False) -> str:
    return sale_reminder(template_kind(slot.event), slot.stage, slot.event.label, slot.id, dormant)


def dormant_users(conn: sqlite3.Connection, now: datetime) -> set[int]:
    """Khách có link gần nhất cũ hơn 21 ngày."""
    cutoff = _stamp(now - DORMANT_AFTER)
    return {int(r[0]) for r in conn.execute(
        "SELECT telegram_user_id FROM link_requests WHERE link_status = 'created' "
        "GROUP BY telegram_user_id HAVING MAX(created_at) < ?", (cutoff,))}


def recipients(conn: sqlite3.Connection) -> list[int]:
    """Khách đã từng tạo link, không tính khách đã chặn bot hay tắt nhắc mùa sale."""
    users = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created' ORDER BY telegram_user_id")]
    cfg = NotifyConfig(True)
    now = datetime.now(timezone.utc)
    return [u for u in users if customer_block_reason(conn, {"category": CATEGORY, "chat_id": u}, cfg, now) is None]


def tick(repo: TrackingRepository, admin_notifier, now: datetime) -> None:
    if nudge_enabled(repo):
        send_nudges(repo, now)
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
    stamp = _stamp(now)
    with repo.connect() as conn:
        users = recipients(conn)
        sleepy = dormant_users(conn, now)
        for user in users:
            enqueue_event(
                conn, event_key=f"sale_reminder:{slot.id}:{user}", event_type="SALE_REMINDER", chat_id=user,
                message_html=text_for(slot, user in sleepy), audience="customer", category=CATEGORY,
                source_ref=f"sale_reminder:{slot.id}", now=stamp,
            )
    save(repo, slot.id, {**data, "status": "sent", "sent": len(users), "dormant": len(sleepy & set(users)), "at": stamp})


def near_sale(repo: TrackingRepository, now: datetime) -> bool:
    """Trong 24 giờ có lượt nhắc sale (khi nhắc sale đang bật): nhường cho tin sale, khỏi nhắn khách hai tin."""
    if not enabled(repo):
        return False
    return any(abs(slot.at - now) < timedelta(hours=24) for slot in sale_calendar.upcoming(now - timedelta(days=1), 3))


def nudge_candidates(conn: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    """Link mới nhất của mỗi khách, có hoàn, 24–72 giờ tuổi, chưa có đơn; khách chưa được nhắc trong 7 ngày."""
    newest, oldest = _stamp(now - NUDGE_AGE[0]), _stamp(now - NUDGE_AGE[1])
    rows = conn.execute(
        """
        SELECT l.* FROM link_requests l
        WHERE l.link_status = 'created' AND COALESCE(l.estimated_cashback, 0) > 0 AND l.affiliate_url IS NOT NULL
          AND l.created_at <= ? AND l.created_at >= ?
          AND l.created_at = (SELECT MAX(created_at) FROM link_requests x
                              WHERE x.telegram_user_id = l.telegram_user_id AND x.link_status = 'created')
          AND NOT EXISTS (SELECT 1 FROM shopee_conversions c WHERE c.matched_link_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM admin_notifications n WHERE n.event_type IN ('LINK_NUDGE', 'PRICE_DROP')
                          AND n.chat_id = l.telegram_user_id AND n.created_at >= ?)
        ORDER BY l.created_at LIMIT ?
        """,
        (newest, oldest, _stamp(now - NUDGE_GAP), NUDGE_LIMIT),
    ).fetchall()
    cfg = NotifyConfig(True)
    return [r for r in rows
            if customer_block_reason(conn, {"category": CATEGORY, "chat_id": r["telegram_user_id"]}, cfg, now) is None]


def recently_nudged(conn: sqlite3.Connection, user: int, now: datetime) -> bool:
    """Khách đã nhận tin nhắc link hay báo giảm giá trong 7 ngày: hai loại dùng chung ngân sách 1 tin / 7 ngày."""
    return conn.execute(
        "SELECT 1 FROM admin_notifications WHERE event_type IN ('LINK_NUDGE', 'PRICE_DROP') AND chat_id = ? "
        "AND created_at >= ?", (user, _stamp(now - NUDGE_GAP))).fetchone() is not None


def nudge_stats(conn: sqlite3.Connection, now: datetime) -> tuple[int, int]:
    """(số tin nhắc link 7 ngày qua, số đã gửi tới khách)."""
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(status = 'sent'), 0) FROM admin_notifications "
        "WHERE event_type = 'LINK_NUDGE' AND created_at >= ?", (_stamp(now - NUDGE_GAP),)).fetchone()
    return int(row[0]), int(row[1])


def send_nudges(repo: TrackingRepository, now: datetime) -> int:
    local = now.astimezone(sale_calendar.ICT).time()
    if not NUDGE_HOURS[0] <= local <= NUDGE_HOURS[1] or near_sale(repo, now):
        return 0
    stamp = _stamp(now)
    with repo.connect() as conn:
        rows = nudge_candidates(conn, now)
        for row in rows:
            tiktok = row["platform"] == "tiktok"
            markup = {"inline_keyboard": [[{"text": TIKTOK_BUY_BUTTON if tiktok else BUY_BUTTON,
                                            "url": row["affiliate_url"]}]]}
            enqueue_event(
                conn, event_key=f"link_nudge:{row['id']}", event_type="LINK_NUDGE", chat_id=int(row["telegram_user_id"]),
                message_html=link_nudge(row["product_name"], tiktok), audience="customer", category=CATEGORY,
                reply_markup_json=json.dumps(markup, ensure_ascii=False), source_ref=f"link:{row['id']}", now=stamp,
            )
    return len(rows)
