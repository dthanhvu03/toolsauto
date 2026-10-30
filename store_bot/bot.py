"""Bot Telegram bán hàng số: khách mua bằng số dư, admin quản lý sản phẩm, kho, nạp tiền, khóa API đại lý.

Chỉ nhận chat riêng. Màn hình mở từ nút thì sửa tại chỗ; màn hình mở từ tin gõ thì gửi tin mới.
Thao tác chờ gõ chữ (số lượng, số tiền, nhập kho…) lưu ở state `await:<user_id>`.
"""

from __future__ import annotations

import fcntl
import json
import logging
import secrets
import threading
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from cashback_bot import vietqr
from store_bot import messages as msg
from store_bot import pricing
from store_bot.config import ConfigError, Settings, default_dotenv, load_settings
from store_bot.db import Order, Product, StoreError, StoreRepository, Topup, User
from store_bot.pricing import Markup
from store_bot.fulfill import Fulfiller
from store_bot.telegram_api import TelegramApi
from store_bot.upstream import BuyResult, FatCatClient, UpstreamError, retail_price

logger = logging.getLogger("store_bot")
LOCK_PATH = "/tmp/store_bot.lock"
QUICK_QUANTITIES = (1, 2, 3, 5, 10)
QUICK_TOPUPS = (50_000, 100_000, 200_000, 500_000, 1_000_000)
RETRY_EVERY_SEC = 10  # FatCat khuyên gọi lại cùng request_id sau khoảng 10 giây
RETRY_AFTER_SEC = 40  # đơn mới để luồng mua xử lý trước, quá mốc này luồng nền mới gọi lại
STUCK_ALERT_SEC = 15 * 60
ANNOUNCE_GAP_SEC = 20 * 60  # một món không đăng kênh dày hơn mức này
BROADCAST_DELAY_SEC = 0.05  # ~20 tin/giây, dưới giới hạn 30 tin/giây của Telegram
MARKUP_DAYS = 30  # xem trước dòng tăng giá theo số món bán trong 30 ngày qua
CALLBACK_GAP_SEC = 24 * 3600  # /supportadmin: mỗi khách 1 lần/ngày


def button(text: str, data: str, icon_id: str | None = None) -> dict:
    """icon_id: logo hãng (custom_emoji_id) hiện trước chữ trên nút."""
    result = {"text": text, "callback_data": data}
    if icon_id:
        result["icon_custom_emoji_id"] = icon_id
    return result


def keyboard(*rows: list[dict]) -> dict:
    return {"inline_keyboard": [row for row in rows if row]}


def main_menu(is_admin: bool) -> dict:
    """Bàn phím cố định dưới ô chat (reply keyboard), luôn hiện kể cả khi khách cuộn mất tin cũ."""
    rows = [
        [{"text": msg.MENU_SHOP}],
        [{"text": msg.MENU_PROFILE}, {"text": msg.MENU_ORDERS}],
        [{"text": msg.MENU_WALLET}, {"text": msg.MENU_SUPPORT}],
    ]
    if is_admin:
        rows.append([{"text": msg.MENU_ADMIN}])
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": msg.MENU_PLACEHOLDER}


class StoreBot:
    def __init__(self, settings: Settings, repo: StoreRepository, telegram: TelegramApi, bot_username: str,
                 fulfiller: Fulfiller | None = None, executor: Executor | None = None):
        self.settings = settings
        self.repo = repo
        self.tg = telegram
        self.bot_username = bot_username
        self.fulfiller = fulfiller or Fulfiller(repo, None)
        # Gọi FatCat có thể mất tới 40 giây: chạy ở luồng riêng để vòng nhận tin không bị đứng.
        self.executor = executor or ThreadPoolExecutor(max_workers=4, thread_name_prefix="fulfill")
        # Nhiều món về cùng lúc thì gửi lần lượt, không chạy song song vượt giới hạn tốc độ Telegram.
        self._broadcast_lock = threading.Lock()
        self.load_icons()

    # ---------- tiện ích ----------

    def load_icons(self) -> None:
        """Nạp logo hãng admin đã gắn (state `icon:<hãng>`) cho messages dùng."""
        msg.CUSTOM_ICONS.clear()
        for brand in msg.BRANDS:
            emoji_id = self.repo.get_state(f"icon:{brand.key}")
            if emoji_id:
                msg.CUSTOM_ICONS[brand.key] = emoji_id

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.settings.admin_ids

    def _show(self, chat_id: int, message_id: int | None, html: str, markup: dict | None = None) -> None:
        if message_id is None or not self.tg.edit_message_text(chat_id, message_id, html, markup):
            self.tg.send_message(chat_id, html, markup)

    def _await(self, user_id: int) -> dict | None:
        raw = self.repo.get_state(f"await:{user_id}")
        return json.loads(raw) if raw else None

    def _set_await(self, user_id: int, kind: str, **data) -> None:
        self.repo.set_state(f"await:{user_id}", json.dumps({"kind": kind, **data}))

    def _clear_await(self, user_id: int) -> None:
        self.repo.delete_state(f"await:{user_id}")

    def notify_admins(self, html: str, markup: dict | None = None, quiet: bool = False) -> None:
        for admin_id in self.settings.admin_ids:
            self.tg.send_message(admin_id, html, markup, disable_notification=quiet)

    def _buy_url(self, product_id: int) -> str:
        return f"https://t.me/{self.bot_username}?start=buy_{product_id}"

    # ---------- vào ----------

    def handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            self._on_callback(update["callback_query"])
        elif "message" in update:
            self._on_message(update["message"])

    def _on_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if chat.get("type") != "private" or not sender.get("id"):
            return
        user = self.repo.touch_user(sender["id"], sender.get("username"), sender.get("first_name"))
        chat_id = chat["id"]
        text = (message.get("text") or "").strip()

        if text.startswith("/"):
            command, _, arg = text.partition(" ")
            command = command.split("@")[0].lower()
            if command in {"/start", "/menu"}:
                self._clear_await(user.user_id)
                payload = arg.strip()
                if payload.startswith("buy_") and payload[4:].isdigit():
                    # Bấm "Mua ngay" trên kênh: vào thẳng món đó. Khách mới thì gửi kèm bàn phím menu một lần.
                    if not self.repo.get_state(f"menu_sent:{user.user_id}"):
                        self.send_welcome(chat_id, user)
                    self.show_product(chat_id, None, user, int(payload[4:]))
                else:
                    self.send_welcome(chat_id, user)
                    self.show_home(chat_id, None, user)
                return
            if command == "/support":
                self._clear_await(user.user_id)
                self.show_support(chat_id, None)
                return
            if command == "/supportadmin":
                self._clear_await(user.user_id)
                self.request_callback(chat_id, user)
                return
            if command == "/huy":
                self._clear_await(user.user_id)
                self.tg.send_message(chat_id, "Đã huỷ.", keyboard([button("🏠 Trang chủ", "home")]))
                return
            if command == "/admin" and self.is_admin(user.user_id):
                self._clear_await(user.user_id)
                self.show_admin(chat_id, None)
                return

        menu = {
            msg.MENU_SHOP: lambda: self.show_shop(chat_id, None),
            msg.MENU_PROFILE: lambda: self.show_account(chat_id, None, user),
            msg.MENU_ORDERS: lambda: self.show_orders(chat_id, None, user),
            msg.MENU_WALLET: lambda: self.show_wallet(chat_id, None, user),
            msg.MENU_SUPPORT: lambda: self.show_support(chat_id, None),
        }
        if self.is_admin(user.user_id):
            menu[msg.MENU_ADMIN] = lambda: self.show_admin(chat_id, None)
        menu_action = menu.get(text)
        if menu_action is not None:
            self._clear_await(user.user_id)
            menu_action()
            return

        pending = self._await(user.user_id)
        if pending:
            document = message.get("document")
            if document and pending["kind"] == "stock" and self.is_admin(user.user_id):
                self._stock_from_document(chat_id, user, pending, document)
                return
            if pending["kind"] == "icon" and self.is_admin(user.user_id) and not text.startswith("/"):
                self._set_icon(chat_id, user, pending, message)
                return
            if text and not text.startswith("/"):
                self._on_input(chat_id, user, pending, text)
                return
        self.show_home(chat_id, None, user)

    def _on_callback(self, query: dict) -> None:
        sender = query.get("from") or {}
        message = query.get("message") or {}
        data = query.get("data") or ""
        if not sender.get("id") or not message:
            return
        user = self.repo.touch_user(sender["id"], sender.get("username"), sender.get("first_name"))
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        parts = data.split(":")
        answer: str | None = None
        alert = False
        try:
            if parts[0] == "a" or data in {"adm", "ap", "apn", "ak", "akn", "at", "aa", "as", "al", "async", "abt", "aic", "amk", "amp"}:
                if not self.is_admin(user.user_id):
                    answer = "Không có quyền."
                else:
                    answer = self._on_admin_callback(chat_id, message_id, user, data, parts)
            else:
                answer, alert = self._on_customer_callback(chat_id, message_id, user, data, parts)
        finally:
            self.tg.answer_callback(query.get("id", ""), answer, alert)

    # ---------- khách ----------

    def _on_customer_callback(self, chat_id: int, message_id: int, user: User, data: str,
                              parts: list[str]) -> tuple[str | None, bool]:
        self._clear_await(user.user_id)
        if data == "home":
            self.show_home(chat_id, message_id, user)
        elif data == "shop":
            self.show_shop(chat_id, message_id)
        elif parts[0] == "p":
            self.show_product(chat_id, message_id, user, int(parts[1]))
        elif parts[0] == "q":
            self.show_confirm(chat_id, message_id, user, int(parts[1]), int(parts[2]))
        elif parts[0] == "qx":
            product = self.repo.get_product(int(parts[1]))
            if product:
                self._set_await(user.user_id, "qty", pid=product.id)
                self._show(chat_id, message_id, msg.ask_quantity(product, self.settings.max_order_quantity),
                           keyboard([button("⬅️ Quay lại", f"p:{product.id}")]))
        elif parts[0] == "bc":
            return self.do_buy(chat_id, message_id, user, int(parts[1]), int(parts[2]), parts[3])
        elif data == "top":
            self.show_topup_menu(chat_id, message_id, user)
        elif data == "wal":
            self.show_wallet(chat_id, message_id, user)
        elif data == "sup":
            self.show_support(chat_id, message_id)
        elif data == "callme":
            self.request_callback(chat_id, user)
        elif data == "noff":
            self.repo.set_notify(user.user_id, False)
            return msg.NOTIFY_OFF_DONE, True
        elif data == "ntog":
            self.repo.set_notify(user.user_id, user.notify_off)
            self.show_account(chat_id, message_id, self.repo.get_user(user.user_id))
        elif parts[0] == "bq":
            self.pay_by_qr(chat_id, message_id, user, int(parts[1]), int(parts[2]))
        elif parts[0] == "ta":
            self.create_topup(chat_id, user, int(parts[1]))
        elif data == "tx":
            self._set_await(user.user_id, "topup")
            self._show(chat_id, message_id, msg.ask_topup_amount(self.settings.min_topup_vnd),
                       keyboard([button("⬅️ Quay lại", "top")]))
        elif data == "acc":
            self.show_account(chat_id, message_id, user)
        elif data == "ord":
            self.show_orders(chat_id, message_id, user)
        elif parts[0] == "o":
            order = self.repo.get_order(int(parts[1]), user.user_id)
            if order is None:
                return "Không tìm thấy đơn.", True
            if order.status == "pending":
                return "Đơn đang lấy hàng, có hàng bot gửi ngay.", True
            if not order.items:
                return f"Đơn #{order.id} không có hàng, đã hoàn {msg.vnd(order.refunded)}.", True
            self.send_items(chat_id, order)
        return None, False

    def show_home(self, chat_id: int, message_id: int | None, user: User) -> None:
        rows = [
            [button("🛒 Mua hàng", "shop")],
            [button("💰 Nạp tiền", "top"), button("👤 Tài khoản", "acc")],
            [button("🧾 Đơn hàng", "ord"), button("☎️ Hỗ trợ", "sup")],
        ]
        if self.is_admin(user.user_id):
            rows.append([button("⚙️ Quản lý shop", "adm")])
        self._show(chat_id, message_id, msg.home(self.settings.shop_name, user), keyboard(*rows))

    def send_welcome(self, chat_id: int, user: User) -> None:
        auto = self.settings.sepay_webhook_key is not None
        self.tg.send_message(chat_id, msg.welcome(self.settings.shop_name, auto), main_menu(self.is_admin(user.user_id)))
        self.repo.set_state(f"menu_sent:{user.user_id}", "1")

    def show_wallet(self, chat_id: int, message_id: int | None, user: User) -> None:
        self._show(chat_id, message_id, msg.wallet(user),
                   keyboard([button("➕ Nạp tiền", "top")], [button("⬅️ Quay lại", "home")]))

    def support_contacts(self) -> tuple[str, str]:
        telegram = self.settings.support_telegram
        if not telegram:
            admins = [self.repo.get_user(admin_id) for admin_id in sorted(self.settings.admin_ids)]
            telegram = next((f"@{a.username}" for a in admins if a and a.username), "")
        return telegram, self.settings.support_zalo

    def show_support(self, chat_id: int, message_id: int | None) -> None:
        self._show(chat_id, message_id, msg.support(*self.support_contacts()),
                   keyboard([button("🆘 Nhờ admin nhắn cho tôi", "callme")], [button("🏠 Menu chính", "home")]))

    def request_callback(self, chat_id: int, user: User) -> None:
        last = float(self.repo.get_state(f"callme:{user.user_id}") or 0)
        if time.time() - last < CALLBACK_GAP_SEC:
            self.tg.send_message(chat_id, msg.CALLBACK_ALREADY)
            return
        self.repo.set_state(f"callme:{user.user_id}", str(time.time()))
        self.notify_admins(msg.admin_callback_request(user))
        self.tg.send_message(chat_id, msg.CALLBACK_DONE)

    def show_shop(self, chat_id: int, message_id: int | None) -> None:
        products = self.repo.list_products()
        rows = [[button(msg.product_button(p), f"p:{p.id}", msg.icon_id(p.name))] for p in products]
        rows.append([button("🏠 Trang chủ", "home")])
        self._show(chat_id, message_id, msg.shop_list(products), keyboard(*rows))

    def show_product(self, chat_id: int, message_id: int | None, user: User, product_id: int) -> None:
        product = self.repo.get_product(product_id)
        if product is None or not product.on_sale:
            self._show(chat_id, message_id, "Sản phẩm này hiện không bán.", keyboard([button("🛒 Xem sản phẩm khác", "shop")]))
            return
        limit = self._max_quantity(product)
        quick = [button(str(q), f"q:{product.id}:{q}") for q in QUICK_QUANTITIES if q <= limit]
        rows = [quick]
        if limit > 1:
            rows.append([button("✍️ Số lượng khác", f"qx:{product.id}")])
        rows.append([button("⬅️ Sản phẩm", "shop"), button("💰 Nạp tiền", "top")])
        if limit >= 1:
            # Khách hay gõ thẳng số lượng thay vì bấm nút: nhận luôn. Gõ chữ khác thì về trang chủ như thường.
            self._set_await(user.user_id, "qty", pid=product.id, soft=True)
        self._show(chat_id, message_id, msg.product_detail(product, user.balance), keyboard(*rows))

    def show_confirm(self, chat_id: int, message_id: int | None, user: User, product_id: int, quantity: int) -> None:
        product = self.repo.get_product(product_id)
        if product is None or not product.on_sale:
            self._show(chat_id, message_id, "Sản phẩm này hiện không bán.", keyboard([button("🛒 Sản phẩm", "shop")]))
            return
        limit = self._max_quantity(product)
        if not 1 <= quantity <= limit:
            self._show(chat_id, message_id, f"Mỗi lần mua được 1–{limit} món.",
                       keyboard([button("⬅️ Quay lại", f"p:{product.id}")]))
            return
        nonce = secrets.token_hex(4)
        missing = product.price * quantity - user.balance
        if missing <= 0:
            first = [button("✅ Xác nhận mua", f"bc:{product.id}:{quantity}:{nonce}")]
        elif self.settings.bank is not None:
            first = [button(f"📱 Thanh toán QR {msg.vnd(missing)}", f"bq:{product.id}:{quantity}")]
        else:
            first = [button("💰 Nạp tiền", "top")]
        self._show(chat_id, message_id, msg.confirm_buy(product, quantity, user.balance),
                   keyboard(first, [button("⬅️ Quay lại", f"p:{product.id}")]))

    def pay_by_qr(self, chat_id: int, message_id: int | None, user: User, product_id: int, quantity: int) -> None:
        """Mua thẳng: tạo mã QR đúng số tiền còn thiếu cho đơn này; tiền được xác nhận thì bot tự mua."""
        product = self.repo.get_product(product_id)
        if product is None or not product.on_sale or not 1 <= quantity <= self._max_quantity(product):
            self.show_product(chat_id, message_id, user, product_id)
            return
        missing = product.price * quantity - user.balance
        if missing <= 0:
            self.show_confirm(chat_id, message_id, user, product_id, quantity)
            return
        self.create_topup(chat_id, user, missing, product=product, quantity=quantity)

    def do_buy(self, chat_id: int, message_id: int, user: User, product_id: int, quantity: int,
               nonce: str) -> tuple[str | None, bool]:
        return self.buy_and_deliver(chat_id, message_id, user, product_id, quantity, f"tg:{nonce}")

    def buy_and_deliver(self, chat_id: int, message_id: int | None, user: User, product_id: int, quantity: int,
                        client_ref: str) -> tuple[str | None, bool]:
        try:
            order = self.repo.buy(user.user_id, product_id, quantity, client_ref=client_ref)
        except StoreError as exc:
            self._show(chat_id, message_id, "❌ " + msg.error_text(exc),
                       keyboard([button("💰 Nạp tiền", "top"), button("🛒 Sản phẩm", "shop")]))
            return msg.error_text(exc), True
        if order.status == "pending":
            self._show(chat_id, message_id, msg.order_waiting(order))
            if order.replayed:
                return "Đơn đang lấy hàng.", False
            self.executor.submit(self._fulfill_now, order.id, chat_id, message_id)
            return "Đang lấy hàng…", False
        if order.replayed and order.status == "failed":
            self._show(chat_id, message_id, msg.order_failed(order), keyboard([button("🛒 Sản phẩm", "shop")]))
            return "Đơn này đã xử lý rồi.", False
        self._show(chat_id, message_id, msg.order_done(order),
                   keyboard([button("🛒 Mua tiếp", "shop"), button("🏠 Trang chủ", "home")]))
        if order.replayed:
            return "Đơn này đã mua rồi.", False
        self.send_items(chat_id, order)
        self.after_sale(order, user)
        return "Mua thành công!", False

    def _max_quantity(self, product: Product) -> int:
        return min(product.stock, product.max_quantity or self.settings.max_order_quantity,
                   self.settings.max_order_quantity)

    def _fulfill_now(self, order_id: int, chat_id: int, message_id: int | None) -> None:
        try:
            order, result, newly = self.fulfiller.attempt(order_id)
            if newly:
                self.report_resolved(order, result, chat_id, message_id)
        except Exception:
            logger.exception("[Store] lấy hàng đơn %s lỗi; luồng nền sẽ thử lại", order_id)

    def report_resolved(self, order: Order, result: BuyResult | None, chat_id: int | None,
                        message_id: int | None) -> None:
        """Đơn FatCat vừa chốt: báo khách (khi mua qua bot) và báo admin."""
        if order.source == "bot" and chat_id is not None:
            if order.items:
                self._show(chat_id, message_id, msg.order_done(order),
                           keyboard([button("🛒 Mua tiếp", "shop"), button("🏠 Trang chủ", "home")]))
                self.send_items(chat_id, order)
            else:
                self._show(chat_id, message_id, msg.order_failed(order), keyboard([button("🛒 Sản phẩm", "shop")]))
        if order.items:
            self.after_sale(order, self.repo.get_user(order.user_id))
        if order.status == "failed" and result is not None:
            self.notify_admins(msg.admin_upstream_rejected(order, result.status_code, result.message))

    def retry_pending(self) -> None:
        """Luồng nền: gọi lại FatCat cho đơn còn chờ, báo admin một lần nếu chờ quá lâu."""
        now = datetime.now(timezone.utc)
        for order_id in self.repo.pending_upstream_orders(RETRY_AFTER_SEC):
            order, result, newly = self.fulfiller.attempt(order_id)
            if newly:
                self.report_resolved(order, result, order.user_id, None)
                continue
            if order and (now - datetime.fromisoformat(order.created_at)).total_seconds() > STUCK_ALERT_SEC:
                if not self.repo.get_state(f"stuck_alerted:{order_id}"):
                    self.repo.set_state(f"stuck_alerted:{order_id}", "1")
                    self.notify_admins(msg.admin_upstream_stuck(order))

    def sync_upstream(self) -> tuple[int, int | None]:
        """Đồng bộ FatCat và đăng kênh món vừa có thêm hàng. Trả (số món FatCat, số dư ví FatCat)."""
        restocked, balance = self.fulfiller.sync()
        now = time.time()
        for product, added in restocked:
            before = product.stock - added
            if not product.on_sale or (added < self.settings.restock_announce_min and before > 0):
                continue
            last = float(self.repo.get_state(f"announced:{product.id}") or 0)
            if now - last < ANNOUNCE_GAP_SEC:
                continue
            self.announce_restock(product.id, added)
            self.repo.set_state(f"announced:{product.id}", str(now))
        count = sum(1 for p in self.repo.list_products(include_inactive=True) if p.upstream_id is not None and p.available)
        return count, balance

    def after_sale(self, order: Order, user: User | None) -> None:
        """Báo admin (im lặng) mỗi đơn và báo (có chuông) khi vừa hết hàng. Bot và API cùng dùng."""
        self.notify_admins(msg.admin_sale(order, user), quiet=True)
        product = self.repo.get_product(order.product_id)
        if product and product.upstream_id is None and product.stock == 0:
            self.notify_admins(msg.admin_sold_out(product),
                                keyboard([button("➕ Nhập kho", f"a:st:{product.id}")]))

    def send_items(self, chat_id: int, order: Order) -> None:
        if msg.items_fit_inline(order):
            self.tg.send_message(chat_id, msg.order_items(order))
        else:
            data = ("\n".join(order.items) + "\n").encode("utf-8")
            self.tg.send_document(chat_id, f"don_{order.id}.txt", data,
                                  f"📦 Đơn #{order.id} · {msg.esc(order.product_name)} × {order.quantity}")

    def show_topup_menu(self, chat_id: int, message_id: int | None, user: User) -> None:
        if self.settings.bank is None:
            self._show(chat_id, message_id, msg.TOPUP_UNAVAILABLE, keyboard([button("🏠 Trang chủ", "home")]))
            return
        self._set_await(user.user_id, "topup", soft=True)
        amounts = [a for a in QUICK_TOPUPS if a >= self.settings.min_topup_vnd]
        rows = [[button(msg.vnd(a), f"ta:{a}") for a in amounts[i:i + 3]] for i in range(0, len(amounts), 3)]
        rows += [[button("✍️ Số khác", "tx")], [button("🏠 Trang chủ", "home")]]
        self._show(chat_id, message_id, msg.topup_menu(self.settings.min_topup_vnd), keyboard(*rows))

    def create_topup(self, chat_id: int, user: User, amount: int, product: Product | None = None,
                     quantity: int | None = None) -> None:
        bank = self.settings.bank
        if bank is None:
            self.tg.send_message(chat_id, msg.TOPUP_UNAVAILABLE)
            return
        # Thanh toán cho một đơn thì trả đúng số còn thiếu, không áp mức nạp tối thiểu.
        if product is None and amount < self.settings.min_topup_vnd:
            self.tg.send_message(chat_id, f"Tối thiểu {msg.vnd(self.settings.min_topup_vnd)}.")
            return
        topup = self.repo.create_topup(user.user_id, amount, product.id if product else None, quantity)
        auto = self.settings.sepay_webhook_key is not None
        product_name = product.name if product else None
        text = msg.topup_instructions(topup, bank.bank_name, bank.account_no, bank.owner, auto, product_name)
        markup = keyboard([button("🏠 Trang chủ", "home")])
        png = None
        try:
            png = vietqr.qr_png(vietqr.build_payload(bank.bin_code, bank.account_no, amount, topup.code))
        except vietqr.VietQRError:
            logger.exception("[Store] tạo VietQR lỗi")
        if png is None or not self.tg.send_photo(chat_id, png, text, markup):
            self.tg.send_message(chat_id, text, markup)
        self.notify_admins(
            msg.admin_topup(topup, user, auto, product_name),
            keyboard([button("✅ Đã nhận tiền", f"a:tc:{topup.id}"), button("❌ Huỷ", f"a:tx:{topup.id}")]),
            quiet=auto,
        )

    def show_account(self, chat_id: int, message_id: int | None, user: User) -> None:
        key = next((k for k in self.repo.list_keys() if k.user_id == user.user_id), None)
        notify = "🔔 Bật báo hàng mới" if user.notify_off else "🔕 Tắt báo hàng mới"
        self._show(chat_id, message_id, msg.account(user, key, self.settings.api_public_url),
                   keyboard([button("💰 Nạp tiền", "top"), button("🧾 Đơn hàng", "ord")],
                            [button(notify, "ntog")],
                            [button("🏠 Trang chủ", "home")]))

    def show_orders(self, chat_id: int, message_id: int | None, user: User) -> None:
        orders = self.repo.list_orders(user.user_id)
        rows = [[button(msg.order_button(o), f"o:{o.id}", msg.icon_id(o.product_name))] for o in orders]
        rows.append([button("🏠 Trang chủ", "home")])
        self._show(chat_id, message_id, msg.orders_list(orders), keyboard(*rows))

    # ---------- gõ chữ ----------

    def _on_input(self, chat_id: int, user: User, pending: dict, text: str) -> None:
        kind = pending["kind"]
        soft = pending.get("soft", False)  # chờ ngầm từ màn sản phẩm / nạp tiền, khác với bấm "✍️ … khác"
        if kind == "qty":
            if not text.isdigit():
                if soft:
                    self._clear_await(user.user_id)
                    self.show_home(chat_id, None, user)
                else:
                    self.tg.send_message(chat_id, "Gõ một số, ví dụ <code>4</code>. Gõ /huy để thôi.")
                return
            self._clear_await(user.user_id)
            self.show_confirm(chat_id, None, user, pending["pid"], int(text))
        elif kind == "topup":
            amount = msg.parse_amount(text)
            if amount is None and soft:
                self._clear_await(user.user_id)
                self.show_home(chat_id, None, user)
                return
            if amount is None or amount < self.settings.min_topup_vnd:
                self.tg.send_message(chat_id, msg.ask_topup_amount(self.settings.min_topup_vnd))
                return
            self._clear_await(user.user_id)
            self.create_topup(chat_id, user, amount)
        elif self.is_admin(user.user_id):
            self._on_admin_input(chat_id, user, pending, text)
        else:
            self._clear_await(user.user_id)
            self.show_home(chat_id, None, user)

    # ---------- admin ----------

    def _on_admin_callback(self, chat_id: int, message_id: int, user: User, data: str, parts: list[str]) -> str | None:
        if parts[:2] != ["a", "sd"]:  # "Xong nhập kho" cần đọc số món đã nhập trong state trước khi xoá
            self._clear_await(user.user_id)
        if data == "adm":
            self.show_admin(chat_id, message_id)
        elif data == "ap":
            self.show_admin_products(chat_id, message_id)
        elif data == "apn":
            self._set_await(user.user_id, "new_product")
            self._show(chat_id, message_id, msg.ASK_NEW_PRODUCT, keyboard([button("⬅️ Quay lại", "ap")]))
        elif data == "ak":
            self.show_admin_keys(chat_id, message_id)
        elif data == "akn":
            self._set_await(user.user_id, "grant")
            self._show(chat_id, message_id, msg.ASK_GRANT, keyboard([button("⬅️ Quay lại", "ak")]))
        elif data == "at":
            self.show_admin_topups(chat_id, message_id)
        elif data == "aa":
            self._set_await(user.user_id, "adjust")
            self._show(chat_id, message_id, msg.ASK_ADJUST, keyboard([button("⬅️ Quay lại", "adm")]))
        elif data == "abt":
            self.repo.set_state("restock_dm", "0" if self.restock_dm_enabled() else "1")
            self.show_admin(chat_id, message_id)
        elif data == "amk":
            self.show_markup(chat_id, message_id)
        elif data == "amp":
            self.show_markup_products(chat_id, message_id)
        elif data == "aic":
            self.show_admin_icons(chat_id, message_id)
        elif data == "async":
            try:
                count, balance = self.sync_upstream()
            except UpstreamError as exc:
                return f"Không đồng bộ được FatCat: {exc}"
            self._show(chat_id, message_id, msg.admin_sync_result(count, balance), keyboard([button("⬅️ Quay lại", "adm")]))
        elif data == "as":
            self._show(chat_id, message_id, msg.admin_stats(self.repo.stats(), self._upstream_balance()),
                       keyboard([button("💸 Giao dịch gần đây", "al")], [button("⬅️ Quay lại", "adm")]))
        elif data == "al":
            self._show(chat_id, message_id, msg.admin_ledger(self.repo.recent_ledger()),
                       keyboard([button("📊 Thống kê", "as"), button("⬅️ Quản lý", "adm")]))
        else:
            return self._on_admin_item(chat_id, message_id, user, parts)
        return None

    def _on_admin_item(self, chat_id: int, message_id: int, user: User, parts: list[str]) -> str | None:
        action, ident = parts[1], int(parts[2])
        by = f"admin:{user.user_id}"
        if action == "p":
            self.show_admin_product(chat_id, message_id, ident)
        elif action == "tg":
            product = self.repo.get_product(ident)
            if product:
                self.repo.update_product(ident, active=not product.active)
            self.show_admin_product(chat_id, message_id, ident)
        elif action in {"pr", "ed"}:
            kind = "price" if action == "pr" else "edit_product"
            self._set_await(user.user_id, kind, pid=ident)
            text = msg.ASK_PRICE if action == "pr" else msg.ASK_EDIT_PRODUCT
            self._show(chat_id, message_id, text, keyboard([button("⬅️ Quay lại", f"a:p:{ident}")]))
        elif action == "st":
            product = self.repo.get_product(ident)
            if product is None:
                return "Không tìm thấy sản phẩm."
            self._set_await(user.user_id, "stock", pid=ident, added=0)
            self._show(chat_id, message_id, msg.ask_stock(product), keyboard([button("⬅️ Quay lại", f"a:p:{ident}")]))
        elif action == "sd":
            pending = self._await(user.user_id) or {}
            added = pending.get("added", 0) if pending.get("kind") == "stock" and pending.get("pid") == ident else 0
            self._clear_await(user.user_id)
            announce = parts[3] == "1"
            note = ""
            if announce and added:
                note = "\n\n" + ("📢 Đã đăng kênh." if self.announce_restock(ident, added) else "⚠️ Không đăng được lên kênh.")
            product = self.repo.get_product(ident)
            self._show(chat_id, message_id, f"✅ Nhập xong {added} món. Tồn kho: {product.stock if product else 0}.{note}",
                       keyboard([button("⬅️ Sản phẩm", f"a:p:{ident}")]))
        elif action in {"mkh", "mkp", "mka", "mkx"}:
            return self._on_markup(chat_id, message_id, user, action, ident, parts[3] if len(parts) > 3 else "")
        elif action in {"ic", "icx"}:
            brand = msg.BRANDS[ident]
            if action == "icx":
                self.repo.delete_state(f"icon:{brand.key}")
                self.load_icons()
                self.show_admin_icons(chat_id, message_id)
                return f"Đã bỏ logo {brand.label}."
            self._set_await(user.user_id, "icon", brand=ident)
            rows = [[button("🗑 Bỏ logo", f"a:icx:{ident}")]] if brand.key in msg.CUSTOM_ICONS else []
            self._show(chat_id, message_id, msg.ask_icon(brand), keyboard(*rows, [button("⬅️ Quay lại", "aic")]))
        elif action == "an":
            return "📢 Đã đăng kênh." if self.announce(ident, 0) else "Không đăng được (kiểm tra STORE_CHANNEL_ID)."
        elif action == "k":
            self.show_admin_key(chat_id, message_id, ident)
        elif action == "kb":
            self.show_admin_key_blocks(chat_id, message_id, ident)
        elif action == "kt":
            self.repo.toggle_block(ident, int(parts[3]))
            self.show_admin_key_blocks(chat_id, message_id, ident)
        elif action == "kd":
            self._set_await(user.user_id, "discount", kid=ident)
            self._show(chat_id, message_id, msg.ASK_DISCOUNT, keyboard([button("⬅️ Quay lại", f"a:k:{ident}")]))
        elif action == "kn":
            key = self.repo.get_key(ident)
            if key is None:
                return "Không tìm thấy khóa."
            raw, new_key = self.repo.issue_key(key.user_id, key.discount_bps)
            self._show(chat_id, message_id, msg.key_granted(new_key, raw, self.settings.api_public_url),
                       keyboard([button("⬅️ Khóa API", "ak")]))
        elif action == "kr":
            self.repo.revoke_key(ident)
            self.show_admin_keys(chat_id, message_id)
            return "Đã thu hồi khóa."
        elif action == "tc":
            return self._confirm_topup(chat_id, message_id, ident, by)
        elif action == "tx":
            done = self.repo.cancel_topup(ident, by)
            topup = self.repo.get_topup(ident)
            status = "❌ Đã huỷ." if done else f"Yêu cầu đã ở trạng thái: {topup.status if topup else '?'}."
            self._show(chat_id, message_id, f"💳 Nạp #{ident}: {status}")
        return None

    def _confirm_topup(self, chat_id: int, message_id: int, topup_id: int, by: str) -> str:
        topup, balance, newly = self.repo.confirm_topup(topup_id, by)
        if not newly:
            self._show(chat_id, message_id, f"💳 Nạp #{topup_id} đã xử lý trước đó ({topup.status}).")
            return "Đã xử lý trước đó."
        self._show(chat_id, message_id, f"💳 Nạp #{topup_id}: ✅ đã cộng {msg.vnd(topup.credited or 0)}.")
        self.on_topup_credited(topup, balance)
        return "Đã cộng tiền."

    def on_topup_credited(self, topup: Topup, balance: int) -> None:
        """Tiền nạp vừa được cộng (admin bấm ✅ hoặc SePay). Nạp để mua một đơn thì tự mua luôn."""
        self.tg.send_message(topup.user_id, msg.topup_credited(topup.credited or 0, balance))
        if topup.intent_product_id is None:
            return
        user = self.repo.get_user(topup.user_id)
        if user is not None:
            self.buy_and_deliver(topup.user_id, None, user, topup.intent_product_id, topup.intent_quantity or 1,
                                 f"topup:{topup.id}")

    def show_admin(self, chat_id: int, message_id: int | None) -> None:
        stats = self.repo.stats()
        pending = f" ({stats['pending_topups']})" if stats["pending_topups"] else ""
        upstream_balance = self._upstream_balance()
        sync_row = [button("🔄 Đồng bộ FatCat", "async")] if self.fulfiller.client else []
        self._show(chat_id, message_id, msg.admin_home(stats, upstream_balance), keyboard(
            [button("📦 Sản phẩm & kho", "ap")],
            sync_row,
            [button(("🔔 Nhắn khách hàng mới: Bật" if self.restock_dm_enabled() else "🔕 Nhắn khách hàng mới: Tắt"),
                    "abt")],
            [button("💲 Tăng giá bán", "amk")] if self.fulfiller.client else [],
            [button("🔑 Khóa API đại lý", "ak"), button("🎨 Logo hãng", "aic")],
            [button(f"💳 Nạp chờ duyệt{pending}", "at"), button("💵 Cộng/trừ tiền", "aa")],
            [button("📊 Thống kê", "as"), button("🏠 Trang chủ", "home")],
        ))

    # ---------- tăng giá bán ----------
    # Callback: a:mkh:<sp> màn chọn mức · a:mkp:<sp>:<mã> xem trước · a:mka:<sp>:<mã> áp dụng · a:mkx:<sp> gõ mức.
    # <sp> = 0: mức chung mọi món FatCat; khác 0: id sản phẩm (giá riêng). <mã> = Markup.code, "x" = bỏ giá riêng.

    def _markup_rows(self, target: int) -> list[list[dict]]:
        presets = [button(msg.markup_button(m), f"a:mkp:{target}:{m.code}") for m in pricing.PRESETS]
        return [presets[i:i + 3] for i in range(0, len(presets), 3)] + [[button("✍️ Mức khác", f"a:mkx:{target}")]]

    def show_markup(self, chat_id: int, message_id: int | None) -> None:
        rows = self.fulfiller.preview(None)
        self._show(chat_id, message_id, msg.admin_markup(self.fulfiller.global_markup(), rows), keyboard(
            *self._markup_rows(0),
            [button("📦 Giá riêng từng món", "amp")],
            [button("⬅️ Quay lại", "adm")],
        ))

    def show_markup_products(self, chat_id: int, message_id: int | None) -> None:
        rows = [[button(f"{'🔒 ' if r.own else ''}{msg.button_icon(r.name)}{r.name} · {msg.vnd(r.price)}",
                        f"a:mkh:{r.product_id}", msg.icon_id(r.name))]
                for r in self.fulfiller.preview(None)]
        rows.append([button("⬅️ Tăng giá bán", "amk")])
        self._show(chat_id, message_id, "📦 <b>Giá riêng từng món</b>\n🔒 = đang có giá riêng. Chọn món:",
                   keyboard(*rows))

    def show_markup_preview(self, chat_id: int, message_id: int | None, target: int, markup: Markup | None) -> None:
        rows = self.fulfiller.preview(markup, target or None)
        back = f"a:mkh:{target}" if target else "amk"
        code = markup.code if markup else "x"
        self._show(chat_id, message_id,
                   msg.markup_preview(markup, rows, MARKUP_DAYS, self._upstream_balance(), single=bool(target)),
                   keyboard([button("✅ Áp dụng", f"a:mka:{target}:{code}")], [button("⬅️ Chọn mức khác", back)]))

    def _on_markup(self, chat_id: int, message_id: int, user: User, action: str, target: int, code: str) -> str | None:
        if target and not self.fulfiller.preview(None, target):
            return "Món này không phải hàng FatCat đang bán."
        if action == "mkh":
            if not target:
                self.show_markup(chat_id, message_id)
                return None
            row = self.fulfiller.preview(None, target)[0]
            extra = [[button("↩️ Theo mức chung", f"a:mkp:{target}:x")]] if row.own else []
            self._show(chat_id, message_id, msg.admin_product_markup(row, self.fulfiller.global_markup()), keyboard(
                *self._markup_rows(target), *extra,
                [button("⬅️ Sản phẩm", f"a:p:{target}"), button("📦 Món khác", "amp")],
            ))
            return None
        if action == "mkx":
            self._set_await(user.user_id, "markup", target=target)
            self._show(chat_id, message_id, msg.ASK_MARKUP,
                       keyboard([button("⬅️ Quay lại", f"a:mkh:{target}" if target else "amk")]))
            return None
        markup = None if code == "x" and target else pricing.decode(code)
        if markup is None and not (code == "x" and target):
            return "Mức tăng không hợp lệ."
        if action == "mkp":
            self.show_markup_preview(chat_id, message_id, target, markup)
            return None
        changed = self.fulfiller.set_markup(markup, target or None)
        name = self.repo.get_product(target).name if target else None
        self._show(chat_id, message_id, msg.markup_applied(markup, changed, name), keyboard(
            [button("💲 Tăng giá bán", "amk"), button("🛒 Xem shop", "shop")],
            [button("⬅️ Quản lý", "adm")],
        ))
        logger.info("[Store] admin %s đổi tăng giá %s → %s (%s món)", user.user_id, target or "chung", code, changed)
        return "Đã đổi giá."

    def show_admin_icons(self, chat_id: int, message_id: int | None) -> None:
        rows = [[button(msg.admin_icon_button(b), f"a:ic:{i}", msg.CUSTOM_ICONS.get(b.key))]
                for i, b in enumerate(msg.BRANDS)]
        rows.append([button("⬅️ Quay lại", "adm")])
        self._show(chat_id, message_id, msg.ADMIN_ICONS, keyboard(*rows))

    def _set_icon(self, chat_id: int, user: User, pending: dict, message: dict) -> None:
        """Admin gửi emoji logo: lấy custom_emoji_id đầu tiên trong tin."""
        brand = msg.BRANDS[pending["brand"]]
        emoji_id = next((e.get("custom_emoji_id") for e in message.get("entities") or []
                         if e.get("type") == "custom_emoji" and e.get("custom_emoji_id")), None)
        if not emoji_id:
            self.tg.send_message(chat_id, msg.ICON_NOT_FOUND)
            return
        self.repo.set_state(f"icon:{brand.key}", str(emoji_id))
        self.load_icons()
        self._clear_await(user.user_id)
        index = pending["brand"]
        self.tg.send_message(chat_id, msg.icon_saved(brand), keyboard(
            [button(brand.label, "aic", msg.CUSTOM_ICONS.get(brand.key))],
            [button("🗑 Bỏ logo", f"a:icx:{index}"), button("🎨 Hãng khác", "aic")]))

    def _upstream_balance(self) -> int | None:
        raw = self.repo.get_state("upstream_balance")
        return int(raw) if raw and self.fulfiller.client else None

    def show_admin_products(self, chat_id: int, message_id: int | None) -> None:
        products = self.repo.list_products(include_inactive=True)
        rows = [[button(msg.admin_product_button(p), f"a:p:{p.id}", msg.icon_id(p.name))] for p in products]
        rows += [[button("➕ Thêm sản phẩm", "apn")], [button("⬅️ Quay lại", "adm")]]
        self._show(chat_id, message_id, f"📦 <b>Sản phẩm</b> ({len(products)})", keyboard(*rows))

    def show_admin_product(self, chat_id: int, message_id: int | None, product_id: int) -> None:
        product = self.repo.get_product(product_id)
        if product is None:
            self._show(chat_id, message_id, "Không tìm thấy sản phẩm.", keyboard([button("⬅️ Quay lại", "ap")]))
            return
        pid = product.id
        toggle = "⏸ Ẩn khỏi shop" if product.active else "▶️ Mở bán lại"
        # Hàng FatCat: giá, tên, kho đi theo FatCat nên không có nút sửa / nhập kho.
        local_rows = [[button("💲 Tăng giá món này", f"a:mkh:{pid}")]] if product.upstream_id is not None else [
            [button("➕ Nhập kho", f"a:st:{pid}")],
            [button("💰 Đổi giá", f"a:pr:{pid}"), button("✏️ Sửa tên/mô tả", f"a:ed:{pid}")],
        ]
        base = rule = None
        if product.upstream_id is not None and product.cost is not None:
            base = retail_price(product.cost, self.fulfiller.discount_bps)
            own = self.fulfiller.own_markup(product.upstream_id)
            rule = f"🔒 {msg.markup_label(own)} (giá riêng)" if own else msg.markup_label(self.fulfiller.global_markup())
        self._show(chat_id, message_id, msg.admin_product(product, base, rule or ""), keyboard(
            *local_rows,
            [button(toggle, f"a:tg:{pid}"), button("📢 Đăng kênh", f"a:an:{pid}")],
            [button("⬅️ Sản phẩm", "ap")],
        ))

    def show_admin_keys(self, chat_id: int, message_id: int | None) -> None:
        keys = self.repo.list_keys()
        rows = [[button(msg.admin_key_button(k, len(self.repo.blocked_products(k.id))), f"a:k:{k.id}")] for k in keys]
        rows += [[button("➕ Cấp khóa mới", "akn")], [button("⬅️ Quay lại", "adm")]]
        url = msg.esc(self.settings.api_public_url) or "(chưa cài STORE_API_PUBLIC_URL)"
        self._show(chat_id, message_id, f"🔑 <b>Khóa API đại lý</b> ({len(keys)})\nĐịa chỉ API: {url}", keyboard(*rows))

    def show_admin_key(self, chat_id: int, message_id: int | None, key_id: int) -> None:
        key = self.repo.get_key(key_id)
        if key is None or not key.active:
            self.show_admin_keys(chat_id, message_id)
            return
        self._show(chat_id, message_id, msg.admin_key(key, len(self.repo.blocked_products(key_id))), keyboard(
            [button("📦 Sản phẩm được bán", f"a:kb:{key_id}")],
            [button("% Đổi mức giảm", f"a:kd:{key_id}"), button("🔄 Cấp lại khóa", f"a:kn:{key_id}")],
            [button("🗑 Thu hồi khóa", f"a:kr:{key_id}")],
            [button("⬅️ Khóa API", "ak")],
        ))

    def show_admin_key_blocks(self, chat_id: int, message_id: int | None, key_id: int) -> None:
        key = self.repo.get_key(key_id)
        if key is None:
            self.show_admin_keys(chat_id, message_id)
            return
        blocked = self.repo.blocked_products(key_id)
        rows = [[button(("🚫 " if p.id in blocked else "✅ ") + p.name, f"a:kt:{key_id}:{p.id}")]
                for p in self.repo.list_products(include_inactive=True)]
        rows.append([button("⬅️ Quay lại", f"a:k:{key_id}")])
        self._show(chat_id, message_id, msg.admin_key_blocks(key), keyboard(*rows))

    def show_admin_topups(self, chat_id: int, message_id: int | None) -> None:
        topups = self.repo.pending_topups()
        if not topups:
            self._show(chat_id, message_id, "💳 Không có yêu cầu nạp nào đang chờ.", keyboard([button("⬅️ Quay lại", "adm")]))
            return
        rows = [[button("✅ " + msg.admin_topup_button(t), f"a:tc:{t.id}"), button("❌", f"a:tx:{t.id}")] for t in topups]
        rows.append([button("⬅️ Quay lại", "adm")])
        self._show(chat_id, message_id, "💳 <b>Nạp chờ duyệt</b>\n\n✅ cộng tiền · ❌ huỷ. Chỉ bấm khi đã thấy tiền vào.",
                   keyboard(*rows))

    def restock_dm_enabled(self) -> bool:
        return self.repo.get_state("restock_dm") != "0"

    def announce_restock(self, product_id: int, added: int) -> bool:
        """Hàng mới về: đăng kênh + nhắn từng khách trong bot (như FatCat). Trả True nếu đăng kênh được."""
        posted = self.announce(product_id, added)
        if self.restock_dm_enabled():
            self.executor.submit(self.broadcast_restock, product_id, added)
        return posted

    def broadcast_restock(self, product_id: int, added: int) -> None:
        product = self.repo.get_product(product_id)
        if product is None or not product.on_sale:
            return
        text = msg.restock_announcement(product, added)
        markup = keyboard([button("🛒 Mua ngay", f"p:{product.id}")], [button("🔕 Tắt báo hàng mới", "noff")])
        sent = blocked = 0
        with self._broadcast_lock:
            for user_id in self.repo.broadcast_targets():
                status, wait = "retry", 0
                for _ in range(3):
                    status, wait = self.tg.send_broadcast(user_id, text, markup)
                    if status != "retry":
                        break
                    time.sleep(min(wait, 60))
                if status == "ok":
                    sent += 1
                elif status == "blocked":
                    self.repo.mark_blocked(user_id)
                    blocked += 1
                time.sleep(BROADCAST_DELAY_SEC)
        logger.info("[Store] báo hàng mới #%s: %s khách, %s đã chặn bot", product.id, sent, blocked)
        self.notify_admins(msg.admin_broadcast_done(product, sent, blocked), quiet=True)

    def announce(self, product_id: int, added: int) -> bool:
        product = self.repo.get_product(product_id)
        if not self.settings.channel_id or product is None:
            return False
        markup = {"inline_keyboard": [[{"text": "🛒 Mua ngay", "url": self._buy_url(product.id)}]]}
        return self.tg.send_message(self.settings.channel_id, msg.restock_announcement(product, added), markup) is not None

    def _stock_done_markup(self, product_id: int) -> dict:
        rows = [[button("✅ Xong, không đăng", f"a:sd:{product_id}:0")]]
        if self.settings.channel_id:
            rows.insert(0, [button("📢 Xong + đăng kênh", f"a:sd:{product_id}:1")])
        return keyboard(*rows)

    def _add_stock(self, chat_id: int, user: User, pending: dict, lines: list[str]) -> None:
        added, dup, _ = self.repo.add_stock(pending["pid"], lines)
        session_added = pending.get("added", 0) + added
        self._set_await(user.user_id, "stock", pid=pending["pid"], added=session_added)
        product = self.repo.get_product(pending["pid"])
        self.tg.send_message(chat_id, msg.stock_progress(product, added, dup, session_added),
                             self._stock_done_markup(pending["pid"]))

    def _stock_from_document(self, chat_id: int, user: User, pending: dict, document: dict) -> None:
        name = (document.get("file_name") or "").lower()
        if not (name.endswith(".txt") or document.get("mime_type") == "text/plain"):
            self.tg.send_message(chat_id, "Chỉ nhận file .txt, mỗi dòng một món.")
            return
        data = self.tg.download_file(document["file_id"])
        if data is None:
            self.tg.send_message(chat_id, "Không tải được file (tối đa 2 MB).")
            return
        self._add_stock(chat_id, user, pending, data.decode("utf-8-sig", errors="replace").splitlines())

    def _on_admin_input(self, chat_id: int, user: User, pending: dict, text: str) -> None:
        kind = pending["kind"]
        by = f"admin:{user.user_id}"
        try:
            if kind == "stock":
                self._add_stock(chat_id, user, pending, text.splitlines())
                return
            if kind == "new_product":
                name, price_raw, desc = (text.split("|") + ["", ""])[:3]
                price = msg.parse_amount(price_raw)
                if not name.strip() or price is None:
                    self.tg.send_message(chat_id, msg.ASK_NEW_PRODUCT)
                    return
                product_id = self.repo.add_product(name, price, desc)
                self._clear_await(user.user_id)
                self.show_admin_product(chat_id, None, product_id)
            elif kind == "price":
                price = msg.parse_amount(text)
                if price is None:
                    self.tg.send_message(chat_id, msg.ASK_PRICE)
                    return
                self.repo.update_product(pending["pid"], price=price)
                self._clear_await(user.user_id)
                self.show_admin_product(chat_id, None, pending["pid"])
            elif kind == "edit_product":
                name, _, desc = text.partition("|")
                if not name.strip():
                    self.tg.send_message(chat_id, msg.ASK_EDIT_PRODUCT)
                    return
                self.repo.update_product(pending["pid"], name=name.strip(), description=desc.strip())
                self._clear_await(user.user_id)
                self.show_admin_product(chat_id, None, pending["pid"])
            elif kind == "markup":
                markup = pricing.parse(text, msg.parse_amount)
                if markup is None:
                    self.tg.send_message(chat_id, "Không hiểu mức tăng (tối đa +200% hoặc +5.000.000đ).\n\n" + msg.ASK_MARKUP)
                    return
                self._clear_await(user.user_id)
                self.show_markup_preview(chat_id, None, pending["target"], markup)
            elif kind == "grant":
                target = self.repo.find_user(text)
                if target is None:
                    self.tg.send_message(chat_id, msg.error_text(StoreError("user_not_found")))
                    return
                raw, key = self.repo.issue_key(target.user_id, self.settings.reseller_discount_bps)
                self._clear_await(user.user_id)
                self.tg.send_message(chat_id, msg.key_granted(key, raw, self.settings.api_public_url),
                                     keyboard([button("📦 Sản phẩm được bán", f"a:kb:{key.id}")],
                                              [button("⬅️ Khóa API", "ak")]))
            elif kind == "discount":
                value = text.replace(",", ".").rstrip("%").strip()
                try:
                    bps = round(float(value) * 100)
                except ValueError:
                    bps = -1
                if not 0 <= bps <= 5_000:
                    self.tg.send_message(chat_id, "Mức giảm từ 0 đến 50%. " + msg.ASK_DISCOUNT)
                    return
                self.repo.set_discount(pending["kid"], bps)
                self._clear_await(user.user_id)
                self.show_admin_key(chat_id, None, pending["kid"])
            elif kind == "adjust":
                ref, amount_raw, note = (text.split(maxsplit=2) + ["", ""])[:3]
                sign = -1 if amount_raw.startswith("-") else 1
                amount = msg.parse_amount(amount_raw.lstrip("+-"))
                target = self.repo.find_user(ref)
                if target is None or not amount:
                    self.tg.send_message(chat_id, msg.ASK_ADJUST if target else msg.error_text(StoreError("user_not_found")))
                    return
                balance = self.repo.adjust_balance(target.user_id, sign * amount, note, by)
                self._clear_await(user.user_id)
                self.tg.send_message(target.user_id, msg.balance_adjusted(sign * amount, balance, note))
                self.tg.send_message(chat_id, f"✅ {msg.esc(target.label)}: {'+' if sign > 0 else '-'}{msg.vnd(amount)}. "
                                              f"Số dư: {msg.vnd(balance)}", keyboard([button("⬅️ Quản lý", "adm")]))
        except StoreError as exc:
            self.tg.send_message(chat_id, "❌ " + msg.error_text(exc))


# ---------- chạy ----------

def _acquire_lock(path: str):
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def run_background(bot: StoreBot, stop: threading.Event) -> None:
    """Luồng nền: gọi lại đơn FatCat đang chờ mỗi 10 giây, đồng bộ sản phẩm mỗi sync_seconds."""
    next_sync = 0.0
    while not stop.is_set():
        if bot.fulfiller.client is not None:
            try:
                bot.retry_pending()
            except Exception:
                logger.exception("[Store] gọi lại đơn FatCat lỗi")
            if time.monotonic() >= next_sync:
                try:
                    count, balance = bot.sync_upstream()
                    logger.info("[Store] đồng bộ FatCat: %s món, ví %s", count, balance)
                except UpstreamError as exc:
                    logger.warning("[Store] đồng bộ FatCat lỗi: %s", exc)
                except Exception:
                    logger.exception("[Store] đồng bộ FatCat lỗi")
                next_sync = time.monotonic() + bot.settings.sync_seconds
        stop.wait(RETRY_EVERY_SEC)


def run_forever(bot: StoreBot, repo: StoreRepository, telegram: TelegramApi) -> None:
    offset = int(repo.get_state("tg_offset") or 0)
    while True:
        try:
            updates = telegram.get_updates(offset)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[Store] getUpdates lỗi: %s", type(exc).__name__)
            time.sleep(5)
            continue
        for update in updates:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            try:
                bot.handle_update(update)
            except Exception:
                # Mua hàng là một giao dịch DB: lỗi giữa chừng không mất tiền; khách xem lại ở 🧾 Đơn hàng.
                logger.exception("[Store] xử lý update %s lỗi", update.get("update_id"))
            repo.set_state("tg_offset", str(offset))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [Store] %(levelname)s %(message)s")
    try:
        settings = load_settings(dotenv_path=default_dotenv())
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc
    lock = _acquire_lock(LOCK_PATH)
    if lock is None:
        logger.error("đã có một store bot khác đang chạy")
        raise SystemExit(3)

    repo = StoreRepository(settings.db_path)
    repo.migrate()
    telegram = TelegramApi(settings.bot_token)
    me = telegram.get_me()
    if not me or not me.get("username"):
        logger.error("không gọi được getMe: kiểm tra STORE_BOT_TOKEN và mạng")
        raise SystemExit(1)
    telegram.set_my_commands(msg.BOT_COMMANDS)
    for admin_id in settings.admin_ids:
        telegram.set_my_commands(msg.ADMIN_COMMANDS, {"type": "chat", "chat_id": admin_id})
    client = FatCatClient(settings.fatcat_api_url, settings.fatcat_api_key) if settings.fatcat_api_key else None
    bot = StoreBot(settings, repo, telegram, me["username"],
                   fulfiller=Fulfiller(repo, client, settings.fatcat_discount_bps))
    threading.Thread(target=run_background, args=(bot, threading.Event()), name="store-bg", daemon=True).start()
    logger.info("store bot @%s sẵn sàng (nguồn FatCat: %s)", me["username"], "bật" if client else "tắt")
    run_forever(bot, repo, telegram)
