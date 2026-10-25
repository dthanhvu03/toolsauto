"""Gửi hàng đợi `admin_notifications` cho admin và khách (PLAN-079, ADR-056). Một bộ gửi duy nhất.

- Đánh dấu 'sending' trước khi gọi Telegram, không giữ transaction SQLite trong lúc gọi.
- 429: thử lại sau retry_after. 5xx / lỗi tạm: thử lại có giãn cách, tối đa MAX_ATTEMPTS rồi 'failed'.
- 4xx: 'failed'. Chỉ 403 (khách chặn bot) mới đánh dấu khách đã chặn; khách nhắn lại thì bỏ đánh dấu. 400 thường
  là lỗi nội dung tin, không phải lỗi của khách.
- Chưa kết nối được (DNS, mất mạng): tin chắc chắn chưa đi → 'retry', hoàn lượt thử, dừng vòng gửi tới vòng sau.
- Hết giờ / đứt kết nối giữa chừng khi gửi tin khách: 'unknown', KHÔNG tự gửi lại (Telegram có thể đã nhận).
  Admin xem và gửi lại tay. Tin admin thì thử lại (trùng tin admin chấp nhận được).
- Tin khách kiểm tra lại lúc gửi: cờ toàn cục (thông báo đơn), tài khoản test (Gate B), tin trước lần bật gần nhất,
  tuỳ chọn của khách, khách đã chặn bot, tin quá cũ.
- 429 là giới hạn của cả bot: dừng vòng gửi, các tin còn lại đợi vòng sau.
- Thông báo admin tắt thì không lấy tin admin, để tin khách phía sau không bị kẹt.
Không đảm bảo đúng-một-lần với Telegram; chọn tối-đa-một-lần cho tin khách khi không rõ kết quả.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from cashback_bot.db import TrackingRepository
from cashback_bot.redact import redact
from cashback_bot.telegram_api import TelegramDeliveryError, never_sent

logger = logging.getLogger("cashback_bot")

MAX_ATTEMPTS = 5
OFFLINE_RETRY_SEC = 30
ORDER_STALE = timedelta(hours=72)
SILENT_EVENTS = {"NEW_USER", "LINK_SENT"}
# Loại tin khách → cột tuỳ chọn. Tin đơn hàng còn cần cờ CUSTOMER_NOTIFICATIONS_ENABLED.
PREF_COLUMNS = {"order_new": "orders", "order_update": "updates", "support": "support", "wallet": "wallet"}
ORDER_CATEGORIES = ("order_new", "order_update")
# Mốc lần bật thông báo đơn gần nhất (bot_state). order_notify.sync_activation đặt lúc khởi động.
BASELINE_KEY = "customer_notify_baseline_at"


@dataclass(frozen=True)
class NotifyConfig:
    """Cờ CUSTOMER_NOTIFICATIONS_ENABLED và danh sách tài khoản test (CUSTOMER_NOTIFICATIONS_TEST_IDS).

    Có danh sách test thì tin đơn chỉ gửi cho các tài khoản đó; khách khác ghi «bỏ qua» như khi cờ tắt.
    """

    enabled: bool
    test_ids: frozenset[int] = frozenset()

    def live_for(self, user_id: int) -> bool:
        return self.enabled and (not self.test_ids or int(user_id) in self.test_ids)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def customer_block_reason(conn, row, cfg: NotifyConfig, now: datetime) -> str | None:
    """Lý do không gửi một tin khách, hoặc None. Dùng cả lúc ghi sự kiện và lúc gửi."""
    category = row["category"]
    if category in ORDER_CATEGORIES:
        if not cfg.enabled:
            return "feature_off"
        if not cfg.live_for(row["chat_id"]):
            return "not_test_account"
        baseline = conn.execute("SELECT value FROM bot_state WHERE key = ?", (BASELINE_KEY,)).fetchone()
        if baseline is None or (row["created_at"] or "") < baseline[0]:
            # Tin ghi trước lần bật gần nhất (bật → tắt → bật): không gửi dồn.
            return "before_activation"
        created = _parse(row["created_at"])
        if created is not None and now - created > ORDER_STALE:
            return "stale"
    user = conn.execute(
        "SELECT * FROM telegram_users WHERE telegram_user_id = ?", (row["chat_id"],)
    ).fetchone()
    if user is None:
        return "not_started"
    if "notify_blocked_at" in user.keys() and user["notify_blocked_at"]:
        return "blocked"
    column = PREF_COLUMNS.get(category or "")
    if column:
        pref = conn.execute(
            f"SELECT {column} FROM customer_notification_prefs WHERE telegram_user_id = ?", (row["chat_id"],)
        ).fetchone()
        if pref is not None and not pref[0]:
            return "pref_off"
    return None


@dataclass
class DispatchResult:
    sent: int = 0
    retry: int = 0
    failed: int = 0
    suppressed: int = 0
    unknown: int = 0


class Dispatcher:
    """`telegram`: bộ gửi có send_message(chat_id, html, ...). PLAN-082: channel='zalo' chỉ lấy tin khách ID âm,
    gửi qua ZaloSender; channel='telegram' không bao giờ lấy tin của khách Zalo."""

    def __init__(self, repo: TrackingRepository, telegram, admin_enabled: bool, admin_chat_id: int | None,
                 customer_enabled: bool, test_ids: frozenset[int] = frozenset(), channel: str = "telegram"):
        self.repo = repo
        self.telegram = telegram
        self.channel = channel
        self.admin_active = admin_enabled and admin_chat_id is not None and channel == "telegram"
        self.cfg = NotifyConfig(customer_enabled, test_ids)

    def flush(self, limit: int = 10, now: datetime | None = None) -> DispatchResult:
        moment = now or datetime.now(timezone.utc)
        result = DispatchResult()
        audiences = ("admin", "customer") if self.admin_active else ("customer",)
        rows = self.repo.list_pending_admin_events(
            limit=limit, max_attempts=MAX_ATTEMPTS, now=_stamp(moment), audiences=audiences, channel=self.channel
        )
        for row in rows:
            customer = row["audience"] == "customer"
            if customer:
                with self.repo.connect() as conn:
                    reason = customer_block_reason(conn, row, self.cfg, moment)
                if reason:
                    self.repo.suppress_admin_event(int(row["id"]), reason)
                    result.suppressed += 1
                    continue
            if not self.repo.claim_admin_event(int(row["id"])):
                continue
            if self._send(row, customer, moment, result) in ("rate_limited", "offline"):
                break
        return result

    def _send(self, row, customer: bool, moment: datetime, result: DispatchResult) -> str | None:
        """Gửi một tin; trả loại lỗi (để vòng gửi dừng khi bị 429) hoặc None."""
        event_id = int(row["id"])
        markup = None
        if "reply_markup_json" in row.keys() and row["reply_markup_json"]:
            markup = json.loads(row["reply_markup_json"])
        attempts = int(row["attempt_count"]) + 1
        try:
            kwargs = {"disable_notification": row["event_type"] in SILENT_EVENTS}
            if markup:
                kwargs["reply_markup"] = markup
            message_id = self.telegram.send_message(int(row["chat_id"]), str(row["message_html"]), **kwargs)
        except TelegramDeliveryError as exc:
            self._failed(row, customer, exc.kind, exc.retry_after, exc.status_code, attempts, moment, result)
            return exc.kind
        except requests.RequestException as exc:
            kind = "offline" if never_sent(exc) else "ambiguous"
            self._failed(row, customer, kind, None, None, attempts, moment, result, redact(type(exc).__name__))
            return kind
        self.repo.finish_admin_event(event_id, "sent", message_id=message_id if isinstance(message_id, int) else None)
        result.sent += 1
        return None

    def _failed(self, row, customer: bool, kind: str, retry_after: int | None, status_code: int | None,
                attempts: int, moment: datetime, result: DispatchResult, detail: str | None = None) -> None:
        event_id = int(row["id"])
        error = f"{kind}:{status_code or ''}{':' + detail if detail else ''}"
        if kind == "offline":
            self.repo.release_admin_event(event_id, error, _stamp(moment + timedelta(seconds=OFFLINE_RETRY_SEC)))
            result.retry += 1
            return
        if kind == "permanent":
            self.repo.finish_admin_event(event_id, "failed", error)
            if customer and status_code == 403:
                with self.repo.connect() as conn:
                    conn.execute(
                        "UPDATE telegram_users SET notify_blocked_at = ? WHERE telegram_user_id = ?",
                        (_stamp(moment), int(row["chat_id"])),
                    )
            result.failed += 1
            return
        if kind == "ambiguous" and customer:
            self.repo.finish_admin_event(event_id, "unknown", error)
            result.unknown += 1
            return
        if attempts >= MAX_ATTEMPTS:
            self.repo.finish_admin_event(event_id, "failed", error)
            result.failed += 1
            return
        delay = retry_after if kind == "rate_limited" and retry_after else 30 * 2 ** (attempts - 1)
        self.repo.finish_admin_event(event_id, "retry", error, next_retry_at=_stamp(moment + timedelta(seconds=delay)))
        result.retry += 1
