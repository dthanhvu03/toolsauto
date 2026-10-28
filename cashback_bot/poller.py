"""Process polling riêng. Lỗi mạng không làm chết vòng lặp."""

from __future__ import annotations

import fcntl
import json
import logging
import queue
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_policy import AdminSafetyError
from cashback_bot import addlivetag_orders, deals, engagement, price_watch, tiktok_sync
from cashback_bot.backup import run_scheduled_backup
from cashback_bot.calculator import CalculationError, ReconciliationRequired
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.notify_dispatch import NotifyConfig
from cashback_bot.messages import (
    ADMIN_COMMANDS,
    BOT_COMMANDS,
    BUY_BUTTON,
    DESCRIPTION,
    DESCRIPTION_WALLET,
    SHORT_DESCRIPTION,
    WALLET_COMMAND,
)
from cashback_bot.product_data import ProductDataClient
from cashback_bot.redact import RedactingFormatter, error_brief
from cashback_bot.service import CashbackService
from cashback_bot import ops_watch, reconciliation
from cashback_bot.sync_scheduler import SyncCoordinator, SyncWorker
from cashback_bot.telegram_api import TelegramApi, TelegramDeliveryError, classify_delivery_error

logger = logging.getLogger("cashback_bot")
LOCK_PATH = "/tmp/cashback_bot.lock"
LOG_FORMAT = "%(asctime)s [Cashback] %(levelname)s %(message)s"

# Xử lý lỗi từng update (hardening P0-4). Nhóm thử lại: số lần tối đa trước khi cách ly.
# Nhóm vĩnh viễn: thử lại vẫn lỗi y hệt, nên cách ly ngay sau khi đã ghi bền vững.
UPDATE_RETRY_LIMITS = {"network": 5, "telegram_send": 5, "database": 5, "unknown": 3}
PERMANENT_UPDATE_ERRORS = {"business", "invalid_update", "telegram_rejected"}
_BUSINESS_ERRORS = (CalculationError, ReconciliationRequired, AdminSafetyError)
_INVALID_UPDATE_ERRORS = (KeyError, TypeError, AttributeError, IndexError, ValueError, UnicodeError)


def configure_logging() -> None:
    """Mọi dòng log của process đi qua RedactingFormatter: che token, cookie, API key (P1-8)."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(LOG_FORMAT))


def main() -> None:
    configure_logging()
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
        customer_notifications_enabled=settings.customer_notifications_enabled,
        customer_notification_test_ids=settings.customer_notification_test_ids,
    )
    ops_watch.record_version(repo, "telegram")
    if settings.admin_chat_id is not None and settings.admin_chat_id not in settings.admin_user_ids:
        # C4: tin admin có nội dung ticket và số tài khoản; chỉ nên gửi vào chat riêng của admin.
        logger.warning("[Cashback] CASHBACK_ADMIN_CHAT_ID không phải chat riêng của admin (nhóm hoặc người khác)")
    stuck = repo.recover_sending()
    if stuck:
        logger.warning("[Cashback] %s tin đang gửi dở lúc dừng bot, chuyển 'unknown' (không tự gửi lại)", stuck)
    service = CashbackService(settings, repo, client, admin_notifier=admin_notifier)
    service.after_deferred = lambda: admin_notifier.flush_pending(limit=5)
    resumed = service.resume_tiktok_jobs(zalo=False)
    if resumed:
        logger.warning("[Cashback] làm tiếp %s link TikTok dở dang lúc dừng bot", resumed)
    _register_profile(telegram, settings.admin_user_ids, wallet_on=service.wallet.settings().enabled)
    logger.info(
        "start db=%s rate=%s max_age_h=%s allowlist=%s public=%s admin_notify=%s",
        settings.db_path,
        settings.cashback_rate_percent,
        settings.product_max_age_hours,
        len(settings.allowed_telegram_ids),
        settings.customer_access_enabled,
        settings.admin_notifications_enabled and settings.admin_chat_id is not None,
    )
    # PLAN-080: đồng bộ Shopee (tay và tự động) chạy ở một luồng nền duy nhất, khoá một lượt trong DB.
    coordinator = SyncCoordinator(repo, admin_notifier, settings.auto_sync)
    coordinator.start()
    SyncWorker(coordinator).start()
    logger.info(
        "shopee auto sync enabled=%s interval_min=%s reconcile_lookup=%s max=%s",
        settings.auto_sync.enabled,
        settings.auto_sync.interval_minutes,
        settings.auto_sync.reconcile_lookup,
        settings.auto_sync.reconcile_lookup_max,
    )
    _loop(service, telegram, repo, admin_notifier, coordinator)


def _register_profile(telegram: TelegramApi, admin_user_ids, wallet_on: bool = False) -> None:
    """Lệnh, mô tả và lệnh /admin theo scope chat. Lỗi chỉ ghi log, không chặn bot."""
    extra = (WALLET_COMMAND,) if wallet_on else ()
    steps = [
        ("setMyCommands", lambda: telegram.set_my_commands(BOT_COMMANDS + extra)),
        ("setMyDescription", lambda: telegram.set_my_description(DESCRIPTION_WALLET if wallet_on else DESCRIPTION)),
        ("setMyShortDescription", lambda: telegram.set_my_short_description(SHORT_DESCRIPTION)),
    ]
    for admin_id in sorted(admin_user_ids):
        scope = {"type": "chat", "chat_id": admin_id}
        steps.append(("setMyCommands admin", lambda scope=scope: telegram.set_my_commands(ADMIN_COMMANDS + extra, scope)))
    for name, step in steps:
        try:
            logger.info("%s %s", name, "ok" if step() else "failed")
        except requests.RequestException as exc:
            logger.error("%s failed: %s", name, type(exc).__name__)


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _markup(button_url: str | None) -> dict | None:
    if not button_url:
        return None
    return {"inline_keyboard": [[{"text": BUY_BUTTON, "url": button_url}]]}


def _row_markup(row) -> dict | None:
    """Bàn phím đã lưu lúc xếp hàng. Dòng cũ chưa có cột thì dựng lại nút Mua."""
    raw = row["reply_markup_json"] if "reply_markup_json" in row.keys() else None
    if raw:
        try:
            return json.loads(raw)
        except ValueError:
            logger.error("outbound id=%s reply_markup_json hỏng", row["id"])
    return _markup(row["button_url"])


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


def _send_outbound(
    service,
    telegram,
    repo,
    admin_notifier,
    row,
    moment: datetime,
    markup=None,
    edit_message_id: int | None = None,
) -> None:
    attempts = repo.mark_outbound_sending(int(row["id"]))
    update_id = int(row["telegram_update_id"])
    target_user_id = int(row["telegram_user_id"])
    target_body = str(row["body_html"])
    target_markup = markup if markup is not None else _row_markup(row)
    edit_id = edit_message_id
    if edit_id is None and "edit_message_id" in row.keys() and row["edit_message_id"]:
        edit_id = int(row["edit_message_id"])

    try:
        sent_via_edit = False
        if edit_id and hasattr(telegram, "edit_message_text"):
            sent_via_edit = telegram.edit_message_text(
                target_user_id,
                edit_id,
                target_body,
                target_markup,
            )
        if not sent_via_edit:
            telegram.send_message(
                target_user_id,
                target_body,
                target_markup,
            )
    except Exception as exc:
        kind, retry_after = classify_delivery_error(exc)
        if kind == "offline":
            # Chưa kết nối được: tin chưa đi. Không tính lượt thử, không báo admin, gửi lại khi có mạng.
            attempts = max(0, attempts - 1)
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
        if admin_notifier and kind != "offline":
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
    return Path(__file__).resolve().parents[1] / ".env"


def classify_update_error(exc: BaseException) -> str:
    """Nhóm lỗi khi xử lý một update. Thứ tự quan trọng: lỗi nghiệp vụ cũng là ValueError."""
    if isinstance(exc, _BUSINESS_ERRORS):
        return "business"
    if isinstance(exc, TelegramDeliveryError):
        return "telegram_rejected" if exc.kind == "permanent" else "telegram_send"
    if isinstance(exc, requests.RequestException):
        kind, _retry_after = classify_delivery_error(exc)
        return "telegram_rejected" if kind == "permanent" else "network"
    if isinstance(exc, sqlite3.Error):
        return "database"
    if isinstance(exc, _INVALID_UPDATE_ERRORS):
        return "invalid_update"
    return "unknown"


def _update_meta(update: dict) -> tuple[str, int | None]:
    """Loại update và người gửi, để admin tra lại. Không lưu nội dung tin."""
    for kind in ("message", "callback_query", "edited_message"):
        body = update.get(kind)
        if isinstance(body, dict):
            sender = body.get("from") or {}
            user_id = sender.get("id") if isinstance(sender, dict) else None
            return kind, user_id if isinstance(user_id, int) else None
    return "other", None


def _handle_update_failure(repo, admin_notifier, update: dict, update_id: int, exc: Exception, sleep) -> bool:
    """Ghi lỗi bền vững rồi quyết định. True: đã cách ly, được tiến offset. False: thử lại sau.

    Không ghi được bản ghi (DB hỏng) thì ném lỗi ra vòng ngoài: offset giữ nguyên.
    """
    category = classify_update_error(exc)
    update_type, user_id = _update_meta(update)
    attempts = repo.record_update_failure(
        update_id, update_type, user_id, category, type(exc).__name__, error_brief(exc)
    )
    limit = UPDATE_RETRY_LIMITS.get(category)
    if category not in PERMANENT_UPDATE_ERRORS and limit is not None and attempts < limit:
        logger.warning(
            "update_id=%s lỗi %s lần %s/%s, thử lại: %s", update_id, category, attempts, limit, error_brief(exc)
        )
        sleep(min(2 ** (attempts - 1), 30))
        return False
    repo.quarantine_update(update_id)
    logger.error("update_id=%s cách ly sau %s lần (%s): %s", update_id, attempts, category, error_brief(exc))
    if admin_notifier:
        admin_notifier.notify_request_failed(
            error_type=f"update_quarantined_{category}",
            update_id=update_id,
            telegram_user_id=user_id,
            status="QUARANTINED",
        )
    return True


def process_updates(
    service: CashbackService,
    telegram: TelegramApi,
    repo: TrackingRepository,
    updates: list,
    admin_notifier: AdminNotifier,
    now: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Xử lý tuần tự. Một update lỗi không chặn các update sau (hardening P0-4):

    - thành công → tiến offset;
    - lỗi tạm → ghi failed_updates, giữ offset, dừng lô này, lần poll sau thử lại (có giãn cách);
    - lỗi vĩnh viễn hoặc hết lượt thử → cách ly bền vững, báo admin, rồi mới tiến offset.
    """
    moment = now or datetime.now(timezone.utc)
    now_text = _stamp(moment)
    for update in updates:
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            continue
        try:
            _process_one(service, telegram, repo, admin_notifier, update, update_id, moment, now_text)
        except Exception as exc:
            if not _handle_update_failure(repo, admin_notifier, update, update_id, exc, sleep):
                break
            repo.set_offset(update_id + 1)
            continue
        if repo.update_failure(update_id) is not None:
            repo.resolve_update_failure(update_id)
    admin_notifier.flush_pending(limit=10)


def _periodic(name: str, call, admin_notifier=None) -> None:
    """Việc định kỳ trong vòng poll: lỗi chỉ ghi log và báo admin (mỗi việc tối đa 10 phút một lần), không chặn
    các việc sau (backup, đồng bộ TikTok…) như khi cả vòng chung một khối try."""
    try:
        call()
    except Exception:
        now = time.time()
        if now - _periodic_failed.get(name, 0.0) < PERIODIC_REPORT_SEC:
            return
        _periodic_failed[name] = now
        logger.exception("[Cashback] việc định kỳ %s lỗi", name)
        if admin_notifier is not None:
            _side_call("notify periodic failure", lambda: admin_notifier.notify_request_failed(
                error_type=f"periodic_{name}", update_id=None, telegram_user_id=None, status="PERIODIC_ERROR"))


def _side_call(name: str, call) -> None:
    """Gọi Telegram phụ (typing, xoá tin, trả lời nút, gửi file). Lỗi chỉ ghi log, không chặn tin chính."""
    try:
        call()
    except Exception as exc:
        logger.warning("[Cashback] %s failed: %s", name, error_brief(exc))


def _process_one(service, telegram, repo, admin_notifier, update: dict, update_id: int, moment, now_text) -> None:
    existing = repo.get_outbound(update_id)
    fresh_markup = None
    target_edit_id = None
    if existing is None:
        _side_call("send_chat_action", lambda: _typing(telegram, update))
        outcome = service.handle_update(update)
        if outcome is None:
            repo.set_offset(update_id + 1)
            return
        chat_id, reply = outcome
        if reply.delete_message_id and hasattr(telegram, "delete_message"):
            _side_call("delete_message", lambda: telegram.delete_message(chat_id, reply.delete_message_id))
        if reply.document and hasattr(telegram, "send_document"):
            _side_call("send_document", lambda: telegram.send_document(chat_id, *reply.document))
        if reply.photo and hasattr(telegram, "send_photo"):
            # Ảnh QR chỉ để tiện; lỗi gửi ảnh không được chặn tin chính (số TK dạng chữ).
            _side_call("send_photo", lambda: telegram.send_photo(chat_id, *reply.photo))
        query_id = reply.callback_query_id
        if query_id and hasattr(telegram, "answer_callback"):
            if reply.toast:
                _side_call("answer_callback", lambda: telegram.answer_callback(query_id, reply.toast, reply.show_alert))
            else:
                _side_call("answer_callback", lambda: telegram.answer_callback(query_id))
        if not reply.text:
            repo.set_offset(update_id + 1)
            return
        fresh_markup = reply.markup()
        target_edit_id = reply.edit_message_id
        existing = repo.enqueue_outbound(
            update_id,
            chat_id,
            reply.text,
            reply.button_url,
            edit_message_id=target_edit_id,
            reply_markup_json=None if fresh_markup is None else json.dumps(fresh_markup, ensure_ascii=False),
        )
    status = existing["status"]
    if status in {"sent", "needs_review", "sending"} or (existing["next_retry_at"] and existing["next_retry_at"] > now_text):
        repo.set_offset(update_id + 1)
        return
    if target_edit_id is None and "edit_message_id" in existing.keys() and existing["edit_message_id"]:
        target_edit_id = int(existing["edit_message_id"])
    _send_outbound(
        service,
        telegram,
        repo,
        admin_notifier,
        existing,
        moment,
        markup=fresh_markup,
        edit_message_id=target_edit_id,
    )
    repo.set_offset(update_id + 1)


def _typing(telegram, update: dict) -> None:
    """Gửi link thì Product Data mất vài giây. Báo "đang gõ" trước, lệnh thì bỏ qua."""
    if not hasattr(telegram, "send_chat_action"):
        return
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    if chat.get("type") != "private" or not text or text.startswith("/"):
        return
    chat_id = chat.get("id")
    if isinstance(chat_id, int):
        telegram.send_chat_action(chat_id, "typing")


def drain_sync_results(coordinator: SyncCoordinator, service: CashbackService, admin_notifier: AdminNotifier) -> None:
    """Luồng chính làm tiếp sau lượt đồng bộ của luồng nền (PLAN-080).

    Cập nhật sổ trước để tin kết quả có phần chia tiền; lượt thủ công thì nhắn kết quả cho admin. Lượt tự động
    không nhắn tóm tắt (đơn mới / hoa hồng đổi đã có tin riêng; lỗi báo theo sự cố). Rồi gửi hàng đợi ngay.
    """
    results = []
    while True:
        try:
            results.append(coordinator.completed.get_nowait())
        except queue.Empty:
            break
    if not results:
        return
    try:
        service.refresh_wallet()
    except Exception:
        logger.exception("[Cashback] cập nhật sổ hoàn tiền sau đồng bộ thất bại")
    for trigger, result in results:
        if trigger == "manual":
            admin_notifier.notify_shopee_sync_result(result.ok, result.message, result.bot_orders)
    admin_notifier.flush_pending(limit=10)


def _check_wallet_refresh(service: CashbackService, repo: TrackingRepository, interval_sec: int = 3600) -> None:
    """Đơn đủ ngày giữ thì vào ví đúng hạn dù tự đồng bộ tắt. Chỉ đọc DB của bot, không gọi Shopee."""
    now = time.time()
    last = repo.get_state("wallet_last_refresh")
    try:
        if last and now - float(last) < interval_sec:
            return
    except ValueError:
        pass
    repo.set_state("wallet_last_refresh", str(now))
    try:
        service.refresh_wallet()
    except Exception:
        logger.exception("[Cashback] cập nhật sổ hoàn tiền định kỳ thất bại")


def _check_reconciliation(repo: TrackingRepository, admin_notifier: AdminNotifier, interval_sec: int = 3600) -> None:
    """PLAN-081: mỗi giờ cập nhật nhãn theo dõi theo tuổi đơn, kể cả khi không có lượt đồng bộ. Không gọi Shopee."""
    now = time.time()
    last = repo.get_state("recon_last_eval")
    try:
        if last and now - float(last) < interval_sec:
            return
    except ValueError:
        pass
    repo.set_state("recon_last_eval", str(now))
    try:
        reconciliation.evaluate(repo, datetime.now(timezone.utc), admin_notifier=admin_notifier)
    except Exception:
        logger.exception("[Cashback] cập nhật theo dõi đối soát định kỳ thất bại")


ZALO_HEARTBEAT_KEY = "zalo_heartbeat"
ZALO_CHECK_INTERVAL_SEC = 300
ZALO_DOWN_AFTER_SEC = 600


def _check_zalo_health(repo: TrackingRepository, admin_notifier: AdminNotifier, now: float | None = None) -> None:
    """PLAN-083: tiến trình Zalo ghi nhịp sống mỗi lần nhận tin thành công (~30 giây). Im quá 10 phút → báo admin
    một lần; chạy lại → báo đã chạy lại. Chưa từng chạy Zalo thì không báo."""
    moment = time.time() if now is None else now
    last = repo.get_state("zalo_check_last")
    try:
        if last and moment - float(last) < ZALO_CHECK_INTERVAL_SEC:
            return
        repo.set_state("zalo_check_last", str(moment))
        beat = repo.get_state(ZALO_HEARTBEAT_KEY)
        if not beat:
            return
        last_beat = float(beat)
        down = moment - last_beat > ZALO_DOWN_AFTER_SEC
        alerted = repo.get_state("zalo_down_alerted") == "1"
        if down != alerted:
            admin_notifier.notify_zalo_health(down, last_beat)
            repo.set_state("zalo_down_alerted", "1" if down else "0")
    except (ValueError, sqlite3.Error):
        logger.exception("[Cashback] kiểm tra nhịp sống bot Zalo thất bại")


NET_DOWN_KEY = "net_down_since"
NET_ALERT_AFTER_SEC = 60
NET_STILL_DOWN_SEC = 300


def _net_failed(repo: TrackingRepository, admin_notifier: AdminNotifier, now: float | None = None) -> None:
    """PLAN-084: lỗi mạng khi nhận tin Telegram không báo ngay. Ghi mốc lỗi đầu; kéo dài quá 5 phút thì báo
    "đang mất kết nối" một lần (gửi được nếu chỉ getUpdates lỗi)."""
    moment = time.time() if now is None else now
    try:
        since = repo.get_state(NET_DOWN_KEY)
        if not since:
            repo.set_state(NET_DOWN_KEY, str(moment))
            repo.set_state("net_down_alerted", "0")
            return
        if moment - float(since) >= NET_STILL_DOWN_SEC and repo.get_state("net_down_alerted") != "1":
            admin_notifier.notify_connection(float(since))
            repo.set_state("net_down_alerted", "1")
    except (ValueError, sqlite3.Error):
        logger.exception("[Cashback] ghi trạng thái mất kết nối thất bại")


def _net_recovered(repo: TrackingRepository, admin_notifier: AdminNotifier, now: float | None = None) -> None:
    """PLAN-084: nhận tin được lại. Mất kết nối từ 1 phút trở lên → một tin "đã kết nối lại"; ngắn hơn chỉ có log."""
    moment = time.time() if now is None else now
    try:
        since = repo.get_state(NET_DOWN_KEY)
        if not since:
            return
        repo.set_state(NET_DOWN_KEY, "")
        if moment - float(since) >= NET_ALERT_AFTER_SEC:
            admin_notifier.notify_connection(float(since), moment)
        else:
            logger.info("telegram poll recovered after %ds", int(moment - float(since)))
    except (ValueError, sqlite3.Error):
        logger.exception("[Cashback] ghi trạng thái kết nối lại thất bại")


BACKUP_INTERVAL_SEC = 86_400
PERIODIC_REPORT_SEC = 600
_periodic_failed: dict[str, float] = {}
BACKUP_RETRY_SEC = 3_600


def _check_backup(
    service: CashbackService,
    repo: TrackingRepository,
    admin_notifier: AdminNotifier,
    now: float | None = None,
) -> None:
    """Backup tự động mỗi ngày (hardening P1-9). Lỗi: ghi log, báo admin, thử lại sau 1 giờ.

    Chỉ một cơ chế lịch: bot tự chạy. Không cài thêm cron cho cùng việc này.
    """
    moment = time.time() if now is None else now
    try:
        last_ok = float(repo.get_state("backup_last_ok") or 0)
        last_try = float(repo.get_state("backup_last_attempt") or 0)
    except ValueError:
        last_ok, last_try = 0.0, 0.0
    if moment - last_ok < BACKUP_INTERVAL_SEC or moment - last_try < BACKUP_RETRY_SEC:
        return
    repo.set_state("backup_last_attempt", str(moment))
    settings = service.settings
    try:
        run_scheduled_backup(Path(settings.db_path), Path(settings.backup_dir), keep=settings.backup_keep)
    except Exception as exc:
        logger.error("[Cashback] backup tự động thất bại: %s", error_brief(exc))
        admin_notifier.notify_request_failed(error_type="backup_failed", status="BACKUP_FAILED")
        return
    repo.set_state("backup_last_ok", str(moment))


def _loop(service: CashbackService, telegram: TelegramApi, repo: TrackingRepository, admin_notifier: AdminNotifier,
          coordinator: SyncCoordinator) -> None:
    alt_orders = addlivetag_orders.AltOrdersClient(service.settings.api_key)
    alt_cfg = NotifyConfig(service.settings.customer_notifications_enabled,
                           service.settings.customer_notification_test_ids)
    while True:
        try:
            ops_watch.beat(repo)
            flush_outbound(service, telegram, repo, admin_notifier, limit=3)
            offset = repo.get_offset()
            updates = telegram.get_updates(offset)
            _net_recovered(repo, admin_notifier)
            process_updates(service, telegram, repo, updates, admin_notifier)
            drain_sync_results(coordinator, service, admin_notifier)
            interval = service.admin_panel.auto_sync.interval_minutes
            for name, call in (
                ("wallet_refresh", lambda: _check_wallet_refresh(service, repo)),
                ("reconciliation", lambda: _check_reconciliation(repo, admin_notifier)),
                ("zalo_health", lambda: _check_zalo_health(repo, admin_notifier)),
                ("versions", lambda: ops_watch.check_versions(repo, admin_notifier)),
                ("delivery_digest", lambda: ops_watch.check_delivery_digest(repo, admin_notifier)),
                ("nightly_brief", lambda: ops_watch.check_nightly_brief(repo, admin_notifier, interval)),
                ("tiktok_sync", lambda: tiktok_sync.maybe_start(repo, service.riohub, admin_notifier)),
                ("sale_reminders", lambda: engagement.tick(repo, admin_notifier, datetime.now(timezone.utc))),
                ("price_drop", lambda: price_watch.maybe_start(repo, service.price_history, admin_notifier)),
                ("alt_crosscheck", lambda: addlivetag_orders.maybe_start(repo, alt_orders, admin_notifier)),
                ("alt_fallback", lambda: addlivetag_orders.maybe_fallback(repo, alt_orders, alt_cfg, admin_notifier)),
                ("deals", lambda: deals.tick(repo, service, admin_notifier)),
                ("backup", lambda: _check_backup(service, repo, admin_notifier)),
            ):
                _periodic(name, call, admin_notifier)
        except KeyboardInterrupt:
            logger.info("stop")
            return
        except requests.RequestException as exc:
            logger.error("telegram poll failed: %s", type(exc).__name__)
            _net_failed(repo, admin_notifier)
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
