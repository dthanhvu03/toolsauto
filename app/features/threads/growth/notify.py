"""Tin Telegram cho Threads Growth (PLAN-158): bài chờ duyệt có nút, báo cuối vòng, báo checkpoint.

Nút ``gr:ok:<id>`` / ``gr:no:<id>`` / ``gr:ab:<id>`` / ``gr:on`` / ``gr:off`` — xử lý ở
``app/features/telegram_bot/event_router.py`` → ``growth.actions``.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app import config
from app.core.notifier import TelegramNotifier

logger = logging.getLogger(__name__)

BOT_LABEL = {"cashbot": "Cashbot", "ai_store": "AI Store"}

_notifier: Optional[TelegramNotifier] = None


def _client() -> Optional[TelegramNotifier]:
    global _notifier
    if _notifier is None and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        _notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    return _notifier


def send(text: str, buttons: Optional[list] = None) -> bool:
    client = _client()
    if client is None:
        logger.info("growth.notify: chưa cấu hình Telegram — bỏ qua")
        return False
    try:
        return client.send_with_buttons(text, buttons) if buttons else client.send(text)
    except Exception as exc:  # Telegram lỗi không được làm hỏng vòng worker
        logger.warning("growth.notify: gửi Telegram lỗi: %s", exc)
        return False


def post_buttons(post: Dict[str, Any]) -> list:
    other = "B" if post["variant"] == "A" else "A"
    return [[
        {"text": "✅ Đăng", "callback_data": f"gr:ok:{post['id']}"},
        {"text": "🚫 Bỏ", "callback_data": f"gr:no:{post['id']}"},
        {"text": f"🔄 Sang {other}", "callback_data": f"gr:ab:{post['id']}"},
    ]]


def pending_text(post: Dict[str, Any]) -> str:
    e = html.escape
    content = post["content"] if len(post["content"]) <= 400 else post["content"][:400] + "…"
    return (
        f"🧵 <b>Kéo khách — chờ duyệt #{post['id']}</b>\n"
        f"{BOT_LABEL.get(post['target_bot'], post['target_bot'])} · biến thể {post['variant']}"
        f" · điểm {post['relevance_score']}\n"
        f"👤 @{e(post['author'])} — <a href=\"{e(post['post_url'])}\">mở bài</a>\n\n"
        f"{e(content)}\n\n"
        f"💬 <i>{e(post['suggested_reply'])}</i>"
    )


def notify_pending(post: Dict[str, Any]) -> bool:
    return send(pending_text(post), post_buttons(post))


def cycle_text(report: Dict[str, Any]) -> str:
    e = html.escape
    head = [f"đã reply {report.get('posted', 0)} bài"]
    if report.get("own_posts"):
        head.append(f"đăng {len(report['own_posts'])} bài riêng")
    if report.get("followups"):
        head.append(f"trả lời lại {len(report['followups'])} người")
    parts = [
        f"🧵 <b>Kéo khách — {' · '.join(head)}</b>"
        + (f" · lỗi {report['failed']}" if report.get("failed") else ""),
        f"Vòng này quét {report.get('scanned', 0)} bài · nhận {report.get('ingested', 0)} bài mới",
    ]
    for it in report.get("posted_items", []):
        link = it.get("reply_url") or it.get("post_url")
        parts.append(
            f"\n• {BOT_LABEL.get(it['bot'], it['bot'])} {it['variant']} → @{e(it['author'])} "
            f"(<a href=\"{e(link)}\">xem</a>)\n  <i>{e(it['text'][:160])}</i>"
        )
    for it in report.get("own_posts", []):
        link = f' (<a href="{e(it["url"])}">xem</a>)' if it.get("url") else ""
        label = "nhắc sale" if it.get("kind") == "sale" else "deal"
        parts.append(f"\n📝 Bài riêng — {label}{link}\n  <i>{e(it['text'][:200])}</i>")
    for it in report.get("followups", []):
        parts.append(
            f"\n💬 @{e(it['author'])}: «{e(it['comment'][:100])}»\n  → <i>{e(it['text'][:160])}</i>"
            f" (<a href=\"{e(it['url'])}\">xem</a>)"
        )
    if report.get("rewritten"):
        parts.append(f"\n✍️ AI viết lại {report['rewritten']} bài đang dùng câu mẫu")
    if report.get("customers"):
        parts.append("\n" + customers_line(report["customers"]))
    if report.get("quota_note"):
        parts.append(f"\n⏳ {e(report['quota_note'])}")
    if report.get("errors"):
        parts.append("⚠️ " + e("; ".join(report["errors"])[:300]))
    return "\n".join(parts)


def checkpoint_text(reason: str) -> str:
    return (
        "⚠️ <b>Kéo khách đã TỰ TẮT</b>\n"
        f"Threads báo mất đăng nhập / checkpoint: {html.escape(reason[:300])}\n"
        "Vào web «Threads — Kéo khách» bấm «Đăng nhập Threads», xong rồi bật lại."
    )


_VN = timezone(timedelta(hours=7))


def vn_time(ts: Optional[str]) -> str:
    """'2026-11-06T01:03:18Z' → '06/11 08:03' (giờ Việt Nam)."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(ts or "")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_VN).strftime("%d/%m %H:%M")


def customers_line(customers: Optional[Dict[str, Any]]) -> str:
    if not customers:
        return ""
    line = (f"👥 Khách mới từ Threads: <b>{customers.get('total', 0)}</b>"
            f" (24h qua {customers.get('last_24h', 0)}, đã dùng bot {customers.get('active', 0)})")
    channels = customers.get("by_channel") or {}
    if channels:
        line += "\n   theo kênh: " + " · ".join(f"{html.escape(k)} {v['customers']}" for k, v in channels.items())
    return line


def summary_text(stats: Dict[str, Any], quota, enabled: bool, login_status: str,
                 customers: Optional[Dict[str, Any]] = None) -> str:
    rows: List[str] = [
        f"🧵 <b>Kéo khách</b> — {'🟢 đang bật' if enabled else '⚪ đang tắt'} · đăng nhập: {html.escape(login_status)}",
        f"Hạn mức: {quota.posted_last_hour}/giờ · {quota.posted_last_day}/24h"
        + ("" if quota.allowed else f" — chờ ({html.escape(quota.reason)})"),
        "",
    ]
    if customers:
        rows.insert(2, customers_line(customers))
    conv = (customers or {}).get("by_variant", {})
    for bot, variants in stats.items():
        for v, counts in variants.items():
            n = conv.get(bot, {}).get(v, {}).get("customers", 0)
            rows.append(
                f"{BOT_LABEL.get(bot, bot)} {v}: đã đăng {counts.get('posted', 0)} → khách {n}"
                f" · chờ {counts.get('pending', 0) + counts.get('approved', 0)} · lỗi {counts.get('failed', 0)}"
            )
    for c in (customers or {}).get("customers", [])[:5]:
        who = f"@{c['username']}" if c.get("username") else f"id {c['user_id']}"
        rows.append(f"• {BOT_LABEL.get(c['bot'], c['bot'])} {c.get('variant') or '?'} — {html.escape(who)}"
                    f" ({vn_time(c.get('joined_at'))}): {html.escape(c['activity'])}")
    return "\n".join(rows)


def toggle_buttons(enabled: bool) -> list:
    return [[{"text": "⚪ Tắt" if enabled else "🟢 Bật", "callback_data": "gr:off" if enabled else "gr:on"}]]
