"""Process polling riêng. Lỗi mạng không làm chết vòng lặp."""

from __future__ import annotations

import fcntl
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BUY_BUTTON
from cashback_bot.product_data import ProductDataClient
from cashback_bot.service import CashbackService
from cashback_bot.telegram_api import TelegramApi, classify_delivery_error

logger = logging.getLogger("cashback_bot")
LOCK_PATH = "/tmp/cashback_bot.lock"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [Cashback] %(levelname)s %(message)s",
    )
    try:
        settings = load_settings(dotenv_path=_default_dotenv())
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc

    lock_handle = _acquire_single_process_lock(LOCK_PATH)
    if lock_handle is None:
        logger.error("another cashback bot process is already running")
        raise SystemExit(3)

    repo = TrackingRepository(settings.db_path)
    repo.migrate()
    client = ProductDataClient(settings.api_key, settings.product_data_url)
    telegram = TelegramApi(settings.bot_token)
    admin_notifier = AdminNotifier(
        repo=repo,
        telegram=telegram,
        enabled=settings.admin_notifications_enabled,
        chat_id=settings.admin_chat_id,
    )
    service = CashbackService(settings, repo, client, admin_notifier=admin_notifier)
    try:
        logger.info("setMyCommands %s", "ok" if telegram.set_my_commands() else "failed")
    except requests.RequestException as exc:
        logger.error("setMyCommands failed: %s", type(exc).__name__)
    logger.info(
        "start db=%s rate=%s max_age_h=%s allowlist=%s public=%s admin_notify=%s",
        settings.db_path,
        settings.cashback_rate_percent,
        settings.product_max_age_hours,
        len(settings.allowed_telegram_ids),
        settings.customer_access_enabled,
        settings.admin_notifications_enabled and settings.admin_chat_id is not None,
    )
    _loop(service, telegram, repo, admin_notifier)


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _markup(button_url: str | None) -> dict | None:
    if not button_url:
        return None
    return {"inline_keyboard": [[{"text": BUY_BUTTON, "url": button_url}]]}


def _next_delivery(service: CashbackService, kind: str, retry_after: int | None, attempts: int, moment: datetime):
    if kind == "permanent" or attempts >= service.settings.delivery_max_attempts:
        return "needs_review", None
    delay = service.settings.delivery_backoff_sec * max(1, attempts)
    if kind == "rate_limited" and retry_after:
        delay = max(delay, retry_after)
    delay = min(max(0, delay), 3600)
    status = "ambiguous" if kind == "ambiguous" else "retry"
    nxt = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    nxt = (nxt + timedelta(seconds=delay)).astimezone(timezone.utc)
    return status, nxt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _send_outbound(service, telegram, repo, admin_notifier, row, moment: datetime, markup=None) -> None:
    attempts = repo.mark_outbound_sending(int(row["id"]))
    update_id = int(row["telegram_update_id"])
    try:
        telegram.send_message(
            int(row["telegram_user_id"]),
            str(row["body_html"]),
            markup if markup is not None else _markup(row["button_url"]),
        )
    except Exception as exc:
        kind, retry_after = classify_delivery_error(exc)
        status, nxt = _next_delivery(service, kind, retry_after, attempts, moment)
        repo.schedule_outbound(int(row["id"]), status, nxt, kind, attempts)
        repo.mark_link_delivery(update_id, status, attempts, nxt, kind)
        saved = repo.get_by_update_id(update_id)
        logger.error(
            "delivery update_id=%s sub_id=%s status=%s attempt=%s kind=%s",
            update_id,
            "-" if saved is None or not saved.sub_id else saved.sub_id,
            status,
            attempts,
            kind,
        )
        if admin_notifier:
            admin_notifier.notify_request_failed(
                error_type="delivery_needs_review" if status == "needs_review" else "telegram_send_customer_failed",
                update_id=update_id,
                telegram_user_id=int(row["telegram_user_id"]),
                status="NEEDS_REVIEW" if status == "needs_review" else "RETRY",
            )
        return
    repo.mark_outbound_sent(int(row["id"]))
    repo.mark_delivered(update_id)
    if admin_notifier:
        admin_notifier.notify_link_sent(update_id)


def flush_outbound(service, telegram, repo, admin_notifier, limit: int = 3, now: datetime | None = None) -> None:
    """Gửi lại tối đa `limit` tin đến hạn. Không tạo link mới."""
    moment = now or datetime.now(timezone.utc)
    now_text = _stamp(moment)
    for row in repo.list_due_outbound(moment, limit):
        if row["status"] == "sending":
            attempts = int(row["attempt_count"] or 0)
            status, nxt = _next_delivery(service, "ambiguous", None, max(1, attempts), moment)
            if attempts >= service.settings.delivery_max_attempts:
                status, nxt = "needs_review", None
            repo.schedule_outbound(int(row["id"]), status, nxt, "ambiguous", attempts)
            repo.mark_link_delivery(int(row["telegram_update_id"]), status, attempts, nxt, "ambiguous")
            continue
        if row["next_retry_at"] and row["next_retry_at"] > now_text:
            continue
        _send_outbound(service, telegram, repo, admin_notifier, row, moment)


def _acquire_single_process_lock(path: str):
    handle = open(path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.write(str(time.time()))
    handle.flush()
    return handle


def _default_dotenv():
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / ".env"


def process_updates(
    service: CashbackService,
    telegram: TelegramApi,
    repo: TrackingRepository,
    updates: list,
    admin_notifier: AdminNotifier,
    now: datetime | None = None,
) -> None:
    moment = now or datetime.now(timezone.utc)
    now_text = _stamp(moment)
    for update in updates:
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            continue
        existing = repo.get_outbound(update_id)
        fresh_markup = None
        if existing is None:
            outcome = service.handle_update(update)
            if outcome is None:
                repo.set_offset(update_id + 1)
                continue
            chat_id, reply = outcome
            query_id = reply.callback_query_id
            if query_id and hasattr(telegram, "answer_callback"):
                telegram.answer_callback(query_id)
            fresh_markup = reply.markup()
            existing = repo.enqueue_outbound(update_id, chat_id, reply.text, reply.button_url)
        status = existing["status"]
        if status in {"sent", "needs_review"}:
            repo.set_offset(update_id + 1)
            continue
        if status == "sending":
            repo.set_offset(update_id + 1)
            continue
        if existing["next_retry_at"] and existing["next_retry_at"] > now_text:
            repo.set_offset(update_id + 1)
            continue
        _send_outbound(service, telegram, repo, admin_notifier, existing, moment, markup=fresh_markup)
        repo.set_offset(update_id + 1)
    admin_notifier.flush_pending(limit=10)


def _loop(service: CashbackService, telegram: TelegramApi, repo: TrackingRepository, admin_notifier: AdminNotifier) -> None:
    while True:
        try:
            flush_outbound(service, telegram, repo, admin_notifier, limit=3)
            offset = repo.get_offset()
            updates = telegram.get_updates(offset)
            process_updates(service, telegram, repo, updates, admin_notifier)
        except KeyboardInterrupt:
            logger.info("stop")
            return
        except requests.RequestException as exc:
            logger.error("telegram poll failed: %s", type(exc).__name__)
            admin_notifier.notify_request_failed(
                error_type="telegram_poll_failed",
                update_id=None,
                telegram_user_id=None,
                status="POLL_ERROR",
            )
            admin_notifier.flush_pending(limit=5)
            time.sleep(5)
        except Exception:
            logger.exception("poll loop failed")
            admin_notifier.notify_request_failed(
                error_type="poll_loop_failed",
                update_id=None,
                telegram_user_id=None,
                status="POLL_ERROR",
            )
            admin_notifier.flush_pending(limit=5)
            time.sleep(5)
