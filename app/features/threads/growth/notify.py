"""Tin Telegram cho Threads Growth (PLAN-158): bài chờ duyệt có nút, báo cuối vòng, báo checkpoint.

Nút ``gr:ok:<id>`` / ``gr:no:<id>`` / ``gr:ab:<id>`` / ``gr:on`` / ``gr:off`` — xử lý ở
``app/features/telegram_bot/event_router.py`` → ``growth.actions``.
"""

from __future__ import annotations

import html
import logging
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
    parts = [
        "🧵 <b>Kéo khách — xong vòng</b>",
        f"Quét {report.get('scanned', 0)} bài · nhận {report.get('ingested', 0)}"
        f" (tự đăng {report.get('auto', 0)}, chờ duyệt {report.get('pending', 0)})",
        f"Đã đăng {report.get('posted', 0)} reply · lỗi {report.get('failed', 0)}",
    ]
    if report.get("quota_note"):
        parts.append(f"⏳ {html.escape(report['quota_note'])}")
    return "\n".join(parts)


def checkpoint_text(reason: str) -> str:
    return (
        "⚠️ <b>Kéo khách đã TỰ TẮT</b>\n"
        f"Threads báo mất đăng nhập / checkpoint: {html.escape(reason[:300])}\n"
        "Vào web «Threads — Kéo khách» bấm «Đăng nhập Threads», xong rồi bật lại."
    )


def summary_text(stats: Dict[str, Any], quota, enabled: bool, login_status: str) -> str:
    rows: List[str] = [
        f"🧵 <b>Kéo khách</b> — {'🟢 đang bật' if enabled else '⚪ đang tắt'} · đăng nhập: {html.escape(login_status)}",
        f"Hạn mức: {quota.posted_last_hour}/giờ · {quota.posted_last_day}/24h"
        + ("" if quota.allowed else f" — chờ ({html.escape(quota.reason)})"),
        "",
    ]
    for bot, variants in stats.items():
        for v, counts in variants.items():
            rows.append(
                f"{BOT_LABEL.get(bot, bot)} {v}: chờ {counts.get('pending', 0)} · đã đăng {counts.get('posted', 0)}"
                f" · bỏ {counts.get('rejected', 0)} · lỗi {counts.get('failed', 0)}"
            )
    return "\n".join(rows)


def toggle_buttons(enabled: bool) -> list:
    return [[{"text": "⚪ Tắt" if enabled else "🟢 Bật", "callback_data": "gr:off" if enabled else "gr:on"}]]
