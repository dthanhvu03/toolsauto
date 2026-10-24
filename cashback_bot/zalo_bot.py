"""Tiến trình kênh Zalo (PLAN-082): python -m cashback_bot.zalo_bot

- Khách Zalo mang ID nội bộ âm (bảng channel_identities) và đi qua cùng CashbackService với khách Telegram:
  link, sub_id, đồng bộ đơn, sổ ví, đối soát dùng chung. Tiến trình này không đồng bộ Shopee, không chạy việc định kỳ.
- Mỗi tin Zalo ghi vào zalo_inbox theo message_id (chống xử lý trùng); −id là update_id cho lõi. Câu trả lời lưu
  trước khi gửi, lỗi mạng thì gửi lại câu đã lưu, không chạy lại thao tác.
- Nút Telegram thành danh sách số (zalo_render); khách gõ số thì chạy đúng nút u:* đó.
- Thông báo cho khách Zalo: Dispatcher(channel='zalo') với ZaloSender; bot Telegram không lấy các tin này.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.poller import ZALO_HEARTBEAT_KEY, _acquire_single_process_lock, _default_dotenv, configure_logging
from cashback_bot.product_data import ProductDataClient
from cashback_bot.redact import error_brief
from cashback_bot.service import CashbackService
from cashback_bot.shopee_url import parse_shopee_target
from cashback_bot.telegram_api import TelegramDeliveryError
from cashback_bot.zalo_api import ZaloApi
from cashback_bot.zalo_render import ERROR_REPLY, LINK_CARD, NON_TEXT, NUMBER_STALE, WELCOME, ZaloMessage, render

logger = logging.getLogger("cashback_bot")

LOCK_PATH = "/tmp/cashback_zalo.lock"
CHANNEL = "zalo"
MENU_TTL = timedelta(minutes=30)
RETRY_LIMIT = 5
TEXT_EVENT = "message.text.received"
UNSUPPORTED_EVENT = "message.unsupported.received"
# PLAN-083: trần gói BASIC và các mốc báo admin. Nhịp sống (ZALO_HEARTBEAT_KEY) do poller._check_zalo_health canh.
BASIC_LIMIT = 50
CAPACITY_ALERTS = (40, 50)
# Lệnh gõ tắt (Zalo không có nút lệnh). Lệnh /… của Telegram vẫn dùng được.
SHORTCUTS = {
    "menu": "/start", "start": "/start", "batdau": "/start", "hd": "/huongdan", "huongdan": "/huongdan",
    "don": "/donhang", "donhang": "/donhang", "vi": "/vi", "hotro": "/hotro", "cachtinh": "/cachtinh",
    "dieukien": "/dieukien", "thongbao": "/thongbao", "hang": "/hang",
}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(messages: list[ZaloMessage]) -> str:
    return json.dumps([[m.text, [list(s) for s in m.styles]] for m in messages], ensure_ascii=False)


def _load(raw: str | None) -> list[ZaloMessage]:
    return [ZaloMessage(text, tuple(tuple(s) for s in styles)) for text, styles in json.loads(raw or "[]")]


class ZaloStore:
    """Bảng channel_identities, zalo_inbox và menu số gần nhất của khách (bot_state)."""

    def __init__(self, repo: TrackingRepository):
        self.repo = repo

    def identity(self, external_id: str, display_name: str | None, now: datetime) -> tuple[int, bool]:
        """ID nội bộ âm của khách Zalo; True nếu vừa tạo."""
        name = (display_name or "").strip()[:80] or None
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT internal_user_id FROM channel_identities WHERE channel = ? AND external_id = ?",
                (CHANNEL, external_id),
            ).fetchone()
            if row is not None:
                conn.execute("UPDATE channel_identities SET display_name = ? WHERE internal_user_id = ?", (name, row[0]))
                return int(row[0]), False
            internal = int(conn.execute("SELECT COALESCE(MIN(internal_user_id), 0) - 1 FROM channel_identities").fetchone()[0])
            conn.execute(
                "INSERT INTO channel_identities (internal_user_id, channel, external_id, display_name, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (internal, CHANNEL, external_id, name, _stamp(now)),
            )
        return internal, True

    def external_id(self, internal_id: int) -> str | None:
        with self.repo.connect() as conn:
            row = conn.execute(
                "SELECT external_id FROM channel_identities WHERE internal_user_id = ? AND channel = ?",
                (internal_id, CHANNEL),
            ).fetchone()
        return None if row is None else str(row[0])

    def receive(self, message_id: str, internal_id: int, event_name: str, now: datetime):
        with self.repo.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO zalo_inbox (message_id, internal_user_id, event_name, status, received_at) "
                "VALUES (?, ?, ?, 'received', ?)",
                (message_id, internal_id, event_name[:64], _stamp(now)),
            )
            return conn.execute("SELECT * FROM zalo_inbox WHERE message_id = ?", (message_id,)).fetchone()

    def save_reply(self, inbox_id: int, messages: list[ZaloMessage]) -> None:
        with self.repo.connect() as conn:
            conn.execute("UPDATE zalo_inbox SET reply_json = ? WHERE id = ?", (_dump(messages), inbox_id))

    def finish(self, inbox_id: int, status: str, attempts: int, error: str | None = None,
               next_retry_at: str | None = None, now: datetime | None = None) -> None:
        replied = _stamp(now or datetime.now(timezone.utc)) if status == "replied" else None
        with self.repo.connect() as conn:
            conn.execute(
                "UPDATE zalo_inbox SET status = ?, attempt_count = ?, last_error = ?, next_retry_at = ?, "
                "replied_at = COALESCE(?, replied_at) WHERE id = ?",
                (status, attempts, error, next_retry_at, replied, inbox_id),
            )

    def due_retries(self, now: datetime, limit: int = 5):
        with self.repo.connect() as conn:
            return conn.execute(
                "SELECT * FROM zalo_inbox WHERE status = 'retry' AND (next_retry_at IS NULL OR next_retry_at <= ?) "
                "ORDER BY id LIMIT ?",
                (_stamp(now), limit),
            ).fetchall()

    def menu(self, internal_id: int, now: datetime) -> tuple[str, ...]:
        try:
            saved = json.loads(self.repo.get_state(f"zalo_menu:{internal_id}") or "{}")
            at = datetime.strptime(saved.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return ()
        return tuple(saved.get("items") or ()) if now - at <= MENU_TTL else ()

    def set_menu(self, internal_id: int, items: tuple[str, ...], now: datetime) -> None:
        self.repo.set_state(f"zalo_menu:{internal_id}", json.dumps({"at": _stamp(now), "items": list(items)}))

    def customer_count(self) -> int:
        with self.repo.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM channel_identities WHERE channel = ?", (CHANNEL,)).fetchone()[0])

    def beat(self, moment: float | None = None) -> None:
        self.repo.set_state(ZALO_HEARTBEAT_KEY, str(time.time() if moment is None else moment))


class ZaloChannel:
    def __init__(self, service: CashbackService, store: ZaloStore, api: ZaloApi, admin_notifier=None):
        self.service = service
        self.store = store
        self.api = api
        self.admin_notifier = admin_notifier

    def handle(self, update: dict, now: datetime | None = None) -> None:
        moment = now or datetime.now(timezone.utc)
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        external = sender.get("id")
        message_id = message.get("message_id")
        if chat.get("chat_type") != "PRIVATE" or sender.get("is_bot"):
            return
        if not isinstance(external, str) or not external or not isinstance(message_id, str) or not message_id:
            return
        internal, is_new = self.store.identity(external, sender.get("display_name"), moment)
        row = self.store.receive(message_id, internal, str(update.get("event_name") or ""), moment)
        if row["status"] != "received":
            return
        update_id = -int(row["id"])
        try:
            reply = self._reply(internal, update, update_id, external, moment)
        except Exception:
            # Khách vẫn nhận câu trả lời; admin được báo (chống spam theo loại lỗi ở AdminNotifier).
            logger.exception("[Cashback] zalo xử lý tin inbox=%s thất bại", row["id"])
            reply = BotReply(ERROR_REPLY)
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="zalo_update_failed", update_id=update_id, telegram_user_id=internal, status="ERROR"
                )
        messages, menu = render(reply)
        if is_new:
            messages = render(BotReply(WELCOME))[0] + messages
            self._capacity_check()
        self.store.set_menu(internal, menu, moment)
        self.store.save_reply(int(row["id"]), messages)
        if self._deliver(int(row["id"]), external, messages, 0, moment):
            self._delivered(update_id)

    def _reply(self, internal: int, update: dict, update_id: int, external: str, now: datetime) -> BotReply:
        event = update.get("event_name")
        if event == UNSUPPORTED_EVENT:
            return BotReply(LINK_CARD)
        if event != TEXT_EVENT:
            return BotReply(NON_TEXT)
        text = str((update.get("message") or {}).get("text") or "").strip()
        key = text.lower()
        if key.isdigit() and len(key) <= 2:
            menu = self.store.menu(internal, now)
            number = int(key)
            if not 1 <= number <= len(menu):
                return BotReply(NUMBER_STALE)
            return self._press(internal, menu[number - 1])
        command = SHORTCUTS.get(key, text)
        if parse_shopee_target(command) is not None:
            try:
                self.api.send_chat_action(external, "typing")
            except requests.RequestException as exc:
                logger.warning("[Cashback] zalo typing failed: %s", error_brief(exc))
        return self.service.handle_text(internal, None, command, update_id=update_id, now=now)

    def _capacity_check(self) -> None:
        count = self.store.customer_count()
        if count in CAPACITY_ALERTS and self.admin_notifier:
            self.admin_notifier.notify_zalo_capacity(count, BASIC_LIMIT)

    def _press(self, internal: int, data: str) -> BotReply:
        """Chạy nút u:* qua đúng đường callback của Telegram (chat riêng, chat_id = khách)."""
        update = {"callback_query": {
            "id": f"zalo:{internal}", "from": {"id": internal}, "data": data,
            "message": {"chat": {"id": internal, "type": "private"}},
        }}
        outcome = self.service.handle_update(update)
        return BotReply(NUMBER_STALE) if outcome is None else outcome[1]

    def _deliver(self, inbox_id: int, external: str, messages: list[ZaloMessage], attempts: int, now: datetime) -> bool:
        """Gửi lần lượt; lỗi thì lưu phần chưa gửi để lần sau gửi tiếp (không gửi lại tin đã tới)."""
        for index, message in enumerate(messages):
            try:
                self.api.send_message(external, message.text, message.payload_styles())
            except TelegramDeliveryError as exc:
                attempts += 1
                self.store.save_reply(inbox_id, messages[index:])
                if exc.kind == "permanent" or attempts >= RETRY_LIMIT:
                    self.store.finish(inbox_id, "failed", attempts, f"{exc.kind}:{exc.status_code or ''}")
                    logger.error("[Cashback] zalo reply inbox=%s failed kind=%s", inbox_id, exc.kind)
                else:
                    delay = exc.retry_after or 30 * 2 ** (attempts - 1)
                    nxt = _stamp(now + timedelta(seconds=min(delay, 3600)))
                    self.store.finish(inbox_id, "retry", attempts, exc.kind, nxt)
                    logger.warning("[Cashback] zalo reply inbox=%s retry=%s kind=%s", inbox_id, attempts, exc.kind)
                return False
        self.store.finish(inbox_id, "replied", attempts, now=now)
        return True

    def retry_due(self, now: datetime | None = None) -> None:
        moment = now or datetime.now(timezone.utc)
        for row in self.store.due_retries(moment):
            external = self.store.external_id(int(row["internal_user_id"]))
            if external is None:
                self.store.finish(int(row["id"]), "failed", int(row["attempt_count"]), "no_identity")
                continue
            if self._deliver(int(row["id"]), external, _load(row["reply_json"]), int(row["attempt_count"]), moment):
                self._delivered(-int(row["id"]))

    def _delivered(self, update_id: int) -> None:
        """Như luồng Telegram: link (nếu tin này tạo link) ghi đã giao, báo admin «Đã gửi link»."""
        self.service.repo.mark_delivered(update_id)
        if self.admin_notifier:
            self.admin_notifier.notify_link_sent(update_id)


class ZaloSender:
    """Bộ gửi cho Dispatcher(channel='zalo'): nhận chat_id âm + HTML + bàn phím Telegram, gửi thành tin Zalo."""

    def __init__(self, api: ZaloApi, store: ZaloStore):
        self.api = api
        self.store = store

    def send_message(self, chat_id: int, html_text: str, reply_markup: dict | None = None,
                     disable_notification: bool = False) -> None:
        external = self.store.external_id(int(chat_id))
        if external is None:
            raise TelegramDeliveryError("permanent")
        keyboard, button_url = [], None
        for row in (reply_markup or {}).get("inline_keyboard") or []:
            buttons = tuple((b["text"], b["callback_data"]) for b in row if b.get("callback_data"))
            button_url = button_url or next((b["url"] for b in row if b.get("url")), None)
            if buttons:
                keyboard.append(buttons)
        messages, menu = render(BotReply(html_text, button_url=button_url, inline_keyboard=tuple(keyboard) or None))
        for message in messages:
            self.api.send_message(external, message.text, message.payload_styles())
        if menu:
            self.store.set_menu(int(chat_id), menu, datetime.now(timezone.utc))
        return None


def main() -> None:
    configure_logging()
    try:
        settings = load_settings(dotenv_path=_default_dotenv())
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc
    if not settings.zalo_bot_token:
        logger.error("ZALO_BOT_TOKEN chưa có trong .env, không chạy kênh Zalo")
        raise SystemExit(2)
    lock_handle = _acquire_single_process_lock(LOCK_PATH)
    if lock_handle is None:
        logger.error("another cashback zalo process is already running")
        raise SystemExit(3)

    repo = TrackingRepository(settings.db_path)
    repo.migrate()
    admin_notifier = AdminNotifier(
        repo=repo,
        telegram=None,
        enabled=settings.admin_notifications_enabled,
        chat_id=settings.admin_chat_id,
        customer_notifications_enabled=settings.customer_notifications_enabled,
        customer_notification_test_ids=settings.customer_notification_test_ids,
    )
    service = CashbackService(settings, repo, ProductDataClient(settings.api_key, settings.product_data_url),
                              admin_notifier=admin_notifier)
    api = ZaloApi(settings.zalo_bot_token)
    store = ZaloStore(repo)
    channel = ZaloChannel(service, store, api, admin_notifier)
    # Tin admin do bot Telegram gửi; tiến trình này chỉ gửi tin khách Zalo (chat_id âm).
    dispatcher = Dispatcher(repo, ZaloSender(api, store), False, None, settings.customer_notifications_enabled,
                            settings.customer_notification_test_ids, channel=CHANNEL)
    try:
        me = api.get_me()
        logger.info("zalo start bot=%s type=%s customer_notify=%s", me.get("display_name"), me.get("account_type"),
                    settings.customer_notifications_enabled)
        store.beat()
    except requests.RequestException as exc:
        logger.error("zalo getMe failed: %s", type(exc).__name__)
    _loop(channel, dispatcher, api)


def _loop(channel: ZaloChannel, dispatcher: Dispatcher, api: ZaloApi) -> None:
    while True:
        try:
            updates = api.get_updates()
            channel.store.beat()
            for update in updates:
                try:
                    channel.handle(update)
                except Exception:
                    logger.exception("zalo update failed")
            channel.retry_due()
            dispatcher.flush(limit=5)
        except KeyboardInterrupt:
            logger.info("zalo stop")
            return
        except requests.RequestException as exc:
            logger.error("zalo poll failed: %s", type(exc).__name__)
            time.sleep(5)
        except Exception:
            logger.exception("zalo loop failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
