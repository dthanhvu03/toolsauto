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
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import requests

from cashback_bot import ops_watch
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, with_tiktok
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.poller import ZALO_HEARTBEAT_KEY, _acquire_single_process_lock, _default_dotenv, configure_logging
from cashback_bot.product_data import ProductDataClient
from cashback_bot.redact import error_brief
from cashback_bot.service import CashbackService
from cashback_bot.shopee_url import parse_shopee_target
from cashback_bot.tiktok_url import parse_tiktok_target
from cashback_bot.telegram_api import TelegramApi, TelegramDeliveryError
from cashback_bot.zalo_api import ZaloApi
from cashback_bot.zalo_render import (
    ERROR_REPLY,
    INTERRUPTED_REPLY,
    LINK_CARD,
    NON_TEXT,
    NUMBER_STALE,
    WELCOME,
    ZaloMessage,
    menu_choices,
    number_missing,
    render,
)

logger = logging.getLogger("cashback_bot")

LOCK_PATH = "/tmp/cashback_zalo.lock"
CHANNEL = "zalo"
MENU_TTL = timedelta(minutes=30)
# Danh sách số của tin bot tự gửi (deal hời, nhắc sale…): khách thường đọc muộn, giữ một ngày (chủ bot 2026-10-28).
PUSH_MENU_TTL = timedelta(hours=24)
DEAL_ITEM = "u:dl:"
RETRY_LIMIT = 5
# Tin kẹt ở 'received' lúc khởi động mà chưa có câu trả lời: trong khoảng này thì nhắn khách gửi lại, cũ hơn thì bỏ.
INTERRUPTED_APOLOGY_WITHIN = timedelta(hours=6)
TEXT_EVENT = "message.text.received"
UNSUPPORTED_EVENT = "message.unsupported.received"
# PLAN-083: trần gói BASIC và các mốc báo admin. Nhịp sống (ZALO_HEARTBEAT_KEY) do poller._check_zalo_health canh.
BASIC_LIMIT = 50
CAPACITY_ALERTS = (40, 50)
# Lệnh gõ tắt (Zalo không có nút lệnh). Lệnh /… của Telegram vẫn dùng được.
SHORTCUTS = {
    "menu": "/start", "start": "/start", "batdau": "/start", "hd": "/huongdan", "huongdan": "/huongdan",
    "don": "/donhang", "donhang": "/donhang", "vi": "/vi", "hotro": "/hotro", "cachtinh": "/cachtinh",
    "dieukien": "/dieukien", "thongbao": "/thongbao", "hang": "/hang", "deal": "/deal",
}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(messages: list[ZaloMessage]) -> str:
    return json.dumps([[m.text, [list(s) for s in m.styles]] for m in messages], ensure_ascii=False)


def _load(raw: str | None) -> list[ZaloMessage]:
    return [ZaloMessage(text, tuple(tuple(s) for s in styles)) for text, styles in json.loads(raw or "[]")]



# Gõ nhiều số một tin («1 3 5», «1,3,5»): chỉ cho các màn bật / tắt, bấm nhầm cũng bấm lại được.
_MULTI_PICK = re.compile(r"\d{1,2}(?:[\s,;.]+\d{1,2})+")
MULTI_PICK_PREFIXES = ("u:dc:t:", "u:n:t:")
MULTI_PICK_ONLY = ("Gõ nhiều số một lần chỉ dùng để bật / tắt các mục có ✅. "
                   "Số {numbers} là mở màn khác, bạn gõ riêng từng số nha.")

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
        return tuple(data for _label, data in self.menu_entries(internal_id, now))

    def menu_entries(self, internal_id: int, now: datetime) -> list[tuple[str, str]]:
        """(nhãn, callback) theo số 1..n. Menu lưu trước khi có nhãn thì nhãn rỗng."""
        try:
            saved = json.loads(self.repo.get_state(f"zalo_menu:{internal_id}") or "{}")
            at = datetime.strptime(saved.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            ttl = timedelta(seconds=int(saved.get("ttl") or MENU_TTL.total_seconds()))
        except (TypeError, ValueError):
            return []
        if now - at > ttl:
            return []
        items = list(saved.get("items") or ())
        labels = list(saved.get("labels") or ())
        return list(zip(labels if len(labels) == len(items) else [""] * len(items), items))

    def set_menu(self, internal_id: int, choices: list[tuple[str, str]], now: datetime,
                 ttl: timedelta = MENU_TTL) -> None:
        self.repo.set_state(f"zalo_menu:{internal_id}", json.dumps(
            {"at": _stamp(now), "items": [data for _label, data in choices],
             "labels": [label for label, _data in choices], "ttl": int(ttl.total_seconds())}, ensure_ascii=False))

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
        inbox_id, update_id = int(row["id"]), -int(row["id"])
        try:
            messages = self._prepare(row, internal, is_new, update, external, moment)
        except Exception:
            # Lỗi sau khi đã ghi inbox (thường là DB): Zalo không gửi lại tin, nên báo khách thử lại và báo admin
            # thay vì để dòng kẹt ở 'received'.
            logger.exception("[Cashback] zalo inbox=%s lỗi giữa chừng", inbox_id)
            self._rescue(inbox_id, internal, external)
            return
        try:
            if self._deliver(inbox_id, external, messages, 0, moment):
                self._delivered(update_id)
        except Exception:
            # Có thể đã gửi tới khách một phần: không gửi thêm tin báo lỗi, chỉ báo admin.
            logger.exception("[Cashback] zalo inbox=%s lỗi sau khi gửi", inbox_id)
            self._notify_failed(update_id, internal)

    def _prepare(self, row, internal: int, is_new: bool, update: dict, external: str,
                 moment: datetime) -> list[ZaloMessage]:
        """Tính câu trả lời, lưu menu số và câu trả lời trước khi gửi."""
        update_id = -int(row["id"])
        try:
            reply = self._reply(internal, update, update_id, external, moment)
        except Exception:
            # Khách vẫn nhận câu trả lời; admin được báo (chống spam theo loại lỗi ở AdminNotifier).
            logger.exception("[Cashback] zalo xử lý tin inbox=%s thất bại", row["id"])
            reply = BotReply(ERROR_REPLY)
            self._notify_failed(update_id, internal)
        messages, _menu = render(reply)
        if is_new:
            welcome = with_tiktok(WELCOME) if self.service.tiktok_open() else WELCOME
            messages = render(BotReply(welcome))[0] + messages
            self._capacity_check()
        # Câu trả lời không có danh sách (gõ nhầm số, tin chat…) thì giữ danh sách trước: gõ lại số đúng vẫn chạy.
        if choices := menu_choices(reply):
            self.store.set_menu(internal, choices, moment)
        self.store.save_reply(int(row["id"]), messages)
        return messages

    def _rescue(self, inbox_id: int, internal: int, external: str) -> None:
        try:
            self.store.finish(inbox_id, "failed", 0, "handler_error")
        except Exception:
            logger.exception("[Cashback] zalo inbox=%s không ghi được trạng thái lỗi", inbox_id)
        try:
            for message in render(BotReply(ERROR_REPLY))[0]:
                self.api.send_message(external, message.text, message.payload_styles())
        except (TelegramDeliveryError, requests.RequestException) as exc:
            logger.error("[Cashback] zalo inbox=%s không gửi được tin báo lỗi: %s", inbox_id, error_brief(exc))
        self._notify_failed(-inbox_id, internal)

    def _notify_failed(self, update_id: int, internal: int) -> None:
        if not self.admin_notifier:
            return
        try:
            self.admin_notifier.notify_request_failed(
                error_type="zalo_update_failed", update_id=update_id, telegram_user_id=internal, status="ERROR"
            )
        except Exception:
            logger.exception("[Cashback] zalo update_id=%s không báo được admin", update_id)

    def _reply(self, internal: int, update: dict, update_id: int, external: str, now: datetime) -> BotReply:
        event = update.get("event_name")
        if event == UNSUPPORTED_EVENT:
            return BotReply(LINK_CARD)
        if event != TEXT_EVENT:
            return BotReply(NON_TEXT)
        text = str((update.get("message") or {}).get("text") or "").strip()
        key = text.lower()
        picks = _MULTI_PICK.fullmatch(key)
        if picks and len(numbers := [int(n) for n in re.findall(r"\d+", key)]) > 1:
            return self._press_many(internal, numbers, update_id, now)
        if key.isdigit() and len(key) <= 2:
            entries = self.store.menu_entries(internal, now)
            number = int(key)
            if not entries:
                return BotReply(NUMBER_STALE)
            if not 1 <= number <= len(entries):
                return BotReply(number_missing(number, len(entries)))
            data = entries[number - 1][1]
            reply = self._press(internal, data, update_id)
            return _keep_deal_list(reply, entries) if data.startswith(DEAL_ITEM) else reply
        command = SHORTCUTS.get(key, text)
        if parse_shopee_target(command) is not None or parse_tiktok_target(command) is not None:
            try:
                self.api.send_chat_action(external, "typing")
            except requests.RequestException as exc:
                logger.warning("[Cashback] zalo typing failed: %s", error_brief(exc))
        return self.service.handle_text(internal, None, command, update_id=update_id, now=now)

    def _capacity_check(self) -> None:
        count = self.store.customer_count()
        if count in CAPACITY_ALERTS and self.admin_notifier:
            self.admin_notifier.notify_zalo_capacity(count, BASIC_LIMIT)

    def _press_many(self, internal: int, numbers: list[int], update_id: int, now: datetime) -> BotReply:
        """«1 3 5»: bấm lần lượt nhiều mục của một màn bật / tắt (danh mục deal, thông báo). Màn khác chỉ nhận một số."""
        menu = self.store.menu(internal, now)
        if not menu:
            return BotReply(NUMBER_STALE)
        if bad := [n for n in numbers if not 1 <= n <= len(menu)]:
            return BotReply(number_missing(bad[0], len(menu)))
        picked = [menu[n - 1] for n in dict.fromkeys(numbers)]
        others = [str(n) for n in dict.fromkeys(numbers) if not menu[n - 1].startswith(MULTI_PICK_PREFIXES)]
        if others:
            return BotReply(MULTI_PICK_ONLY.format(numbers=", ".join(others)))
        reply = BotReply(NUMBER_STALE)
        for part, data in enumerate(picked):
            reply = self._press(internal, data, update_id, part)
        return reply

    def _press(self, internal: int, data: str, update_id: int, part: int = 0) -> BotReply:
        """Chạy nút u:* qua đúng đường callback của Telegram (chat riêng, chat_id = khách).

        Mã callback theo từng tin Zalo (như query_id Telegram): Zalo gửi lại cùng tin thì cùng mã (chống trùng),
        lần bấm sau là mã mới. Mã chung cho mọi lần bấm làm khách chỉ rút được một lần (B5)."""
        update = {"callback_query": {
            "id": f"zalo:{internal}:{-update_id}" + (f":{part}" if part else ""), "from": {"id": internal}, "data": data,
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
                # Chưa kết nối được thì tin chưa đi: không tính lượt thử.
                attempts += 0 if exc.kind == "offline" else 1
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

    def recover_inbox(self, now: datetime | None = None) -> tuple[int, int]:
        """Lúc khởi động: tin kẹt ở 'received' (tiến trình bị tắt ngang giữa lúc xử lý; Zalo không gửi lại tin).

        Đã có câu trả lời lưu sẵn: chuyển 'retry' để vòng gửi lại gửi nốt (trả lời khách được gửi lại, trùng thì vô
        hại). Chưa có (đang tính dở, nội dung tin không lưu): nhắn khách gửi lại tin. Trả (gửi nốt, nhắn gửi lại)."""
        moment = now or datetime.now(timezone.utc)
        with self.store.repo.connect() as conn:
            rows = conn.execute("SELECT id, reply_json, received_at FROM zalo_inbox WHERE status = 'received'").fetchall()
        resent = apologized = 0
        for row in rows:
            inbox_id = int(row["id"])
            if row["reply_json"]:
                self.store.finish(inbox_id, "retry", 0, "interrupted")
                resent += 1
            elif row["received_at"] >= _stamp(moment - INTERRUPTED_APOLOGY_WITHIN):
                self.store.save_reply(inbox_id, render(BotReply(INTERRUPTED_REPLY))[0])
                self.store.finish(inbox_id, "retry", 0, "interrupted")
                apologized += 1
            else:
                self.store.finish(inbox_id, "failed", 0, "interrupted")
        return resent, apologized

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
        reply = BotReply(html_text, button_url=button_url, inline_keyboard=tuple(keyboard) or None)
        messages, menu = render(reply)
        for index, message in enumerate(messages):
            try:
                self.api.send_message(external, message.text, message.payload_styles())
            except TelegramDeliveryError as exc:
                if index == 0:
                    raise
                # Phần đầu đã tới khách: gửi lại cả tin sẽ trùng. Coi như không rõ, admin xem và gửi lại tay.
                raise TelegramDeliveryError("ambiguous", status_code=exc.status_code) from exc
        if menu:
            self.store.set_menu(int(chat_id), menu_choices(reply), datetime.now(timezone.utc), PUSH_MENU_TTL)
        return None


def _keep_deal_list(reply: BotReply, entries: list[tuple[str, str]]) -> BotReply:
    """Khách gõ số một món trong tin deal: tin link giữ nguyên danh sách của tin deal, cùng số, để gõ tiếp số món khác
    (Zalo chỉ có một danh sách số; trước đây tin link thay danh sách, gõ 2 thì báo hết hạn — chủ bot 2026-10-28).
    Nút riêng của tin link (Lưu ý trước khi mua…) xếp sau."""
    if not reply.text or not all(label for label, _data in entries):
        return reply
    known = {data for _label, data in entries}
    rest = tuple(row for row in reply.inline_keyboard or () if not any(data in known for _label, data in row))
    return replace(reply, inline_keyboard=tuple(((label, data),) for label, data in entries) + rest)


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
    ops_watch.record_version(repo, CHANNEL)
    stuck = repo.recover_sending(channel=CHANNEL)
    if stuck:
        logger.warning("[Cashback] zalo: %s tin đang gửi dở lúc dừng bot, chuyển 'unknown' (không tự gửi lại)", stuck)
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
    # Thẻ link TikTok tạo ở luồng nền: vào hàng đợi rồi gửi ngay, không chờ hết vòng getUpdates 30 giây.
    service.after_deferred = lambda: dispatcher.flush(limit=5)
    resent, apologized = channel.recover_inbox()
    resumed = service.resume_tiktok_jobs(zalo=True)
    if resent or apologized or resumed:
        logger.warning("[Cashback] zalo khởi động: gửi nốt %s, nhắn gửi lại %s, làm tiếp %s link TikTok",
                       resent, apologized, resumed)
    try:
        me = api.get_me()
        logger.info("zalo start bot=%s type=%s customer_notify=%s", me.get("display_name"), me.get("account_type"),
                    settings.customer_notifications_enabled)
        store.beat()
    except requests.RequestException as exc:
        logger.error("zalo getMe failed: %s", type(exc).__name__)
    # PLAN-087: canh bot Telegram; báo thẳng qua API Telegram vì hàng đợi tin admin do bot đó gửi.
    watch_chat = settings.admin_chat_id if settings.admin_notifications_enabled else None
    _loop(channel, dispatcher, api, TelegramApi(settings.bot_token), watch_chat)


def _loop(channel: ZaloChannel, dispatcher: Dispatcher, api: ZaloApi, telegram: TelegramApi | None = None,
          watch_chat: int | None = None) -> None:
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
            ops_watch.check_telegram_health(channel.store.repo, telegram, watch_chat)
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
