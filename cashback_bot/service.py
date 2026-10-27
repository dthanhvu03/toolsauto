"""Nhận link, kiểm tra Product Data, tạo một sub_id, lưu tracking."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from cashback_bot import admin_tiktok
from cashback_bot.admin_policy import AdminPanel
from cashback_bot.affiliate import build_an_redir, new_sub_id
from cashback_bot.config import Settings
from cashback_bot.customer_desk import CustomerDesk
from cashback_bot import order_notify, payouts, policy_snapshot
from cashback_bot.pricing import EstimatePolicy, PolicyResolution, cashback_for, estimate_cashback, quote_displayed_vnd
from cashback_bot.db import LinkRow, TrackingRepository, enqueue_event
from cashback_bot.messages import (
    CLOSED,
    CLOSED_ALERT,
    DIEUKIEN,
    STALE_BUTTON,
    GENERIC_FAIL,
    HUONGDAN,
    NOT_FOUND,
    STALE,
    TIKTOK_NO_INFO,
    TIKTOK_NOT_OPEN,
    TIKTOK_NOT_PROMOTABLE,
    TIKTOK_WORKING,
    with_tiktok,
    TIP_ALERT,
    TIPS_KEYBOARD,
    WALLET_CLOSED,
    WALLET_CLOSED_ALERT,
    BotReply,
    bank_pick_reply,
    bank_prompt_reply,
    entry_notice,
    hang_message,
    home_reply,
    how_to_calc,
    food_link_reply,
    invalid_link_reply,
    page_reply,
    rate_limited_reply,
    render_success,
    render_success_v12,
    wallet_reply,
    withdraw_confirm_reply,
    withdraw_done_reply,
    withdraw_error_reply,
)
from cashback_bot.price_watch import PriceHistoryClient
from cashback_bot.product_data import ProductDataClient, ProductDataError, quote_from_payload
from cashback_bot.ranks import MEMBERSHIP_CUTOVER
from cashback_bot.riohub_client import RioHubClient, RioHubError, commission_rate_bps, price_range_vnd, product_title
from cashback_bot.shopee_url import is_shopee_food_link, parse_shopee_target
from cashback_bot.tiktok_url import parse_tiktok_target
from cashback_bot.wallet import BANKS, BankAccount, Split, Wallet, parse_bank_text

logger = logging.getLogger("cashback_bot")

if TYPE_CHECKING:
    from cashback_bot.admin_notify import AdminNotifier


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _row_get(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _command_name(text: str) -> str | None:
    token = text.split(maxsplit=1)[0] if text else ""
    if not token.startswith("/"):
        return None
    return token.split("@", 1)[0].lower()

_NOT_FOUND_CODES = {"not_found"}
# Đơn cũ hơn mức này lần đầu bot thấy thì không báo "có đơn mới" (tránh nhắn dồn đơn cũ).
NEW_ORDER_NOTICE_WINDOW = timedelta(days=7)


class CashbackService:
    def __init__(
        self,
        settings: Settings,
        repo: TrackingRepository,
        client: ProductDataClient,
        admin_notifier: "AdminNotifier | None" = None,
        riohub: RioHubClient | None = None,
    ):
        self.settings = settings
        self.repo = repo
        self.client = client
        self.admin_notifier = admin_notifier
        # PLAN-085: link TikTok Shop qua RioHub; None khi .env chưa có khoá.
        tiktok_configured = bool(settings.riohub_api_key and settings.riohub_creator_username)
        self.riohub = riohub if riohub is not None else (
            RioHubClient(settings.riohub_api_key, settings.riohub_creator_username) if tiktok_configured else None
        )
        # Tạo link TikTok chạy nền (rà soát P3). Test thay bằng hàm chạy ngay; tiến trình bot đặt after_deferred để đẩy
        # tin vừa vào hàng đợi đi luôn (Telegram: flush_pending, Zalo: dispatcher.flush).
        self._tiktok_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tiktok-link")
        self.tiktok_runner: Callable[[Callable[[], None]], object] = self._tiktok_pool.submit
        self.after_deferred: Callable[[], object] | None = None
        # Báo giảm giá món khách từng xem (price_watch): cùng khoá AddLiveTag với báo giá. Chỉ bot Telegram chạy lượt.
        self.price_history = PriceHistoryClient(settings.api_key)
        self.wallet = Wallet(repo)
        notify_cfg = order_notify.NotifyConfig(
            settings.customer_notifications_enabled, settings.customer_notification_test_ids
        )
        self.desk = CustomerDesk(repo, admin_notifier, terms_required=settings.terms_required, orders_live=notify_cfg)
        # PLAN-079: sự kiện thông báo đơn sinh trong transaction ghi đơn. Mốc kích hoạt = lúc bắt đầu chế độ hiện tại.
        order_notify.sync_activation(repo, notify_cfg, datetime.now(timezone.utc))
        repo.conversion_hooks[:] = [order_notify.make_hook(notify_cfg)]
        policy = self._estimate_policy() if self._v12_ready() else None
        calculator = "V1.2" if policy else "V1.1, chưa bật V1.2"
        self.admin_panel = AdminPanel(
            settings.db_path,
            settings.admin_user_ids,
            settings.cashback_rate_percent,
            calculator_label=calculator,
            membership_on=MEMBERSHIP_CUTOVER,
            fee_default_bps=settings.estimate_fee_bps,
            tax_default_bps=settings.estimate_tax_reserve_bps,
            estimate_policy=policy,
            admin_notifier=admin_notifier,
            other_reserve_vnd=settings.estimate_other_reserve_vnd,
            rounding_unit=settings.estimate_rounding_unit,
            customer_notifications_enabled=settings.customer_notifications_enabled,
            customer_notification_test_ids=settings.customer_notification_test_ids,
            auto_sync=settings.auto_sync,
            tiktok_configured=tiktok_configured,
        )
        self._snapshots_on = False
        self._backfill_snapshots()

    def _policy_defaults(self) -> policy_snapshot.PolicyDefaults:
        return policy_snapshot.PolicyDefaults(
            share_bps=self.settings.cashback_rate_percent * 100,
            fee_bps=self.settings.estimate_fee_bps,
            tax_reserve_bps=self.settings.estimate_tax_reserve_bps,
            other_reserve_vnd=self.settings.estimate_other_reserve_vnd,
            rounding_unit=self.settings.estimate_rounding_unit,
        )

    def _backfill_snapshots(self) -> None:
        """Link cũ chưa có snapshot (PLAN-076): ghi một lần lúc khởi động. Lỗi thì lần tính ví dựng tạm, không ghi."""
        try:
            with self.repo.connect() as conn:
                self._snapshots_on = _has_table(conn, "link_policy_snapshots")
                if not self._snapshots_on:
                    return
                counts = policy_snapshot.backfill(conn, self._policy_defaults())
        except sqlite3.Error:
            logger.exception("[Cashback] dựng snapshot chính sách link cũ thất bại")
            return
        if any(counts.values()):
            logger.info("[Cashback] snapshot chính sách link cũ backfilled=%s unresolved=%s", *counts.values())

    def allowed(self, telegram_user_id: int) -> bool:
        if telegram_user_id in self.settings.allowed_telegram_ids:
            return True
        return self.settings.customer_access_enabled

    def handle_update(self, update: dict) -> tuple[int, BotReply] | None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            return self._handle_callback(callback)
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if chat.get("type") != "private" or sender.get("is_bot"):
            return None
        user_id = sender.get("id")
        if not isinstance(user_id, int):
            return None
        text = message.get("text") or ""
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            return None
        message_id = message.get("message_id")
        reply = self.handle_text(
            user_id,
            sender.get("username"),
            text,
            update_id,
            message_id=message_id if isinstance(message_id, int) else None,
        )
        return user_id, reply

    def _handle_callback(self, callback: dict) -> tuple[int, BotReply] | None:
        sender = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        user_id = sender.get("id")
        query_id = callback.get("id")
        message_id = message.get("message_id")
        if not isinstance(user_id, int) or not isinstance(query_id, str):
            return None
        data = str(callback.get("data") or "")
        if data.startswith("u:"):
            chat_id = chat.get("id")
            reply = self._customer_callback(
                user_id, data, str(chat.get("type") or ""), chat_id if isinstance(chat_id, int) else None, query_id
            )
        else:
            reply = self.admin_panel.handle_callback(
                user_id,
                data,
                str(chat.get("type") or ""),
                datetime.now(timezone.utc),
            )
        return user_id, replace(
            reply,
            callback_query_id=query_id,
            edit_message_id=message_id if isinstance(message_id, int) else None,
        )

    def _customer_callback(
        self, user_id: int, data: str, chat_type: str, chat_id: int | None = None, query_id: str | None = None
    ) -> BotReply:
        if chat_type != "private":
            return BotReply("")
        if not self.allowed(user_id):
            return BotReply("", toast=CLOSED_ALERT, show_alert=True)
        if not data.startswith("u:w:bk:"):
            self._set_bank_waiting(user_id, None)
        desk = self.desk.callback(user_id, chat_id, data, datetime.now(timezone.utc))
        if desk is not None:
            return desk
        self.desk.clear(user_id)
        if data == "u:tip":
            return BotReply("", toast=TIP_ALERT, show_alert=True)
        if data.startswith("u:w:"):
            return self._wallet_action(user_id, data.removeprefix("u:w:"), query_id)
        page = self._page(data.removeprefix("u:p:"), user_id) if data.startswith("u:p:") else None
        if page is None:
            return BotReply("", toast=STALE_BUTTON)
        return page

    def tiktok_open(self) -> bool:
        """TikTok Shop đã mở cho mọi khách (🎵 chế độ «all») và có khoá RioHub: trang chung nhắc cả hai sàn."""
        return self.riohub is not None and admin_tiktok.current_mode(self.repo) == "all"

    def _page(self, name: str, user_id: int | None = None) -> BotReply | None:
        """Trang thông tin dùng chung cho lệnh gõ tay và nút u:p:*."""
        page = self._page_body(name, user_id)
        if page is not None and name in ("home", "guide", "calc", "tips") and self.tiktok_open():
            return replace(page, text=with_tiktok(page.text))
        return page

    def _page_body(self, name: str, user_id: int | None = None) -> BotReply | None:
        wallet = self.wallet.settings()
        if name == "home":
            return home_reply(show_rank=MEMBERSHIP_CUTOVER, show_wallet=wallet.enabled)
        if name == "guide":
            return page_reply(HUONGDAN)
        if name == "rules":
            return self.desk.rules_page(user_id, datetime.now(timezone.utc))
        if name == "tips":
            return BotReply(DIEUKIEN, inline_keyboard=TIPS_KEYBOARD)
        if name == "support" and user_id is not None:
            return self.desk.support_page(user_id)
        if name == "orders" and user_id is not None:
            return self.desk.orders_page(user_id)
        if name == "notify" and user_id is not None:
            return self.desk.notify_page(user_id)
        if name == "calc":
            if wallet.enabled:
                return page_reply(how_to_calc(self._v12_ready(), wallet.hold_days, wallet.min_withdraw_vnd))
            return page_reply(how_to_calc(self._v12_ready()))
        if name == "rank":
            return page_reply(hang_message())
        if name == "wallet" and user_id is not None:
            return self._wallet_page(user_id)
        return None

    # --- Ví (PLAN-066) -------------------------------------------------------

    def _wallet_page(self, user_id: int, notice: str = "") -> BotReply:
        settings = self.wallet.settings()
        if not settings.enabled:
            return page_reply(WALLET_CLOSED)
        with self.repo.connect() as conn:
            limits = payouts.active_limits(conn)
        return wallet_reply(
            settings,
            self.wallet.balance(user_id),
            self.wallet.entries(user_id),
            self.wallet.bank(user_id),
            self.wallet.open_request(user_id),
            notice=notice,
            limits=limits,
            request_vnd=self.wallet.request_amount(user_id, datetime.now(timezone.utc)),
        )

    def _wallet_action(self, user_id: int, action: str, query_id: str | None = None) -> BotReply:
        if not self.wallet.settings().enabled:
            return BotReply("", toast=WALLET_CLOSED_ALERT, show_alert=True)
        if action == "bank":
            return bank_pick_reply(BANKS)
        if action.startswith("bk:"):
            code = action.removeprefix("bk:")
            if code not in BANKS:
                return bank_pick_reply(BANKS, notice="Ngân hàng này chưa hỗ trợ.")
            self._set_bank_waiting(user_id, code)
            return bank_prompt_reply(BANKS[code][1])
        if action == "out":
            bank = self.wallet.bank(user_id)
            balance = self.wallet.balance(user_id).withdrawable_vnd
            if bank is None:
                return withdraw_error_reply("no_bank")
            if self.wallet.open_request(user_id) is not None:
                return withdraw_error_reply("pending_exists")
            minimum = self.wallet.settings().min_withdraw_vnd
            if balance < minimum or balance <= 0:
                return withdraw_error_reply("below_min")
            # B6: số dư lớn hơn hạn mức thì rút phần được phép, phần còn lại rút lần sau.
            now = datetime.now(timezone.utc)
            amount = self.wallet.request_amount(user_id, now)
            if amount < minimum:
                with self.repo.connect() as conn:
                    return withdraw_error_reply(payouts.check_limits(conn, user_id, minimum, now) or "over_daily_limit")
            return withdraw_confirm_reply(amount, bank, balance)
        if action == "out:ok":
            # Telegram gửi lại cùng callback: cùng khoá, không tạo yêu cầu thứ hai (PLAN-078).
            key = None if query_id is None else f"cb:{user_id}:{query_id}"
            payout, code = self.wallet.request_payout(user_id, datetime.now(timezone.utc), idempotency_key=key)
            if payout is None:
                return withdraw_error_reply(code)
            if code == "duplicate":
                return withdraw_done_reply(payout)
            if self.admin_notifier:
                user = self.repo.get_user(user_id)
                self.admin_notifier.notify_payout_request(payout, None if user is None else user["username"])
            return withdraw_done_reply(payout)
        return BotReply("", toast=STALE_BUTTON)

    def _bank_waiting(self, user_id: int) -> str | None:
        """Mã ngân hàng khách đã bấm chọn và bot đang chờ số tài khoản; None: không chờ."""
        value = self.repo.get_state(f"wallet_bank_waiting:{user_id}")
        return value if value in BANKS else None

    def _set_bank_waiting(self, user_id: int, bank_code: str | None) -> None:
        key = f"wallet_bank_waiting:{user_id}"
        if bank_code is not None:
            self.repo.set_state(key, bank_code)
        elif self.repo.get_state(key) not in (None, "0"):
            self.repo.set_state(key, "0")

    def _consume_bank(self, user_id: int, bank_code: str, text: str, now: datetime) -> BotReply:
        parsed = parse_bank_text(text, bank_code)
        if not isinstance(parsed, BankAccount):
            return bank_prompt_reply(BANKS[bank_code][1], parsed)
        self.wallet.save_bank(user_id, parsed, now)
        self._set_bank_waiting(user_id, None)
        return self._wallet_page(user_id, notice=f"✅ Đã lưu tài khoản {parsed.masked} · {parsed.account_name}.")

    def refresh_wallet(self, now: datetime | None = None) -> None:
        """Gọi sau mỗi lần đồng bộ Shopee: cập nhật sổ, ví bật thì báo khách đơn đổi trạng thái."""
        moment = now or datetime.now(timezone.utc)
        transitions = self.wallet.refresh(moment, self._real_cashback)
        settings = self.wallet.settings()
        recent = (moment - NEW_ORDER_NOTICE_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        for item in transitions:
            if (item.previous == "available" and item.status == "cancelled" or item.status == "clawback") \
                    and self.admin_notifier:
                self.admin_notifier.notify_wallet_clawback(item)
            if not settings.enabled:
                continue
            if item.previous is None and (item.status == "cancelled" or (item.purchase_time or "") < recent):
                continue
            if item.cashback_vnd <= 0 and item.status != "cancelled":
                continue
            self.repo.enqueue_admin_event(
                event_key=f"wallet:{item.conversion_id}:{item.status}",
                event_type="WALLET_ENTRY",
                chat_id=item.telegram_user_id,
                message_html=entry_notice(
                    item.status, item.item_name, item.cashback_vnd, item.available_at, settings.hold_days,
                    item.estimated_vnd,
                ),
            )

    def _real_cashback(self, commission_vnd: int, row) -> Split:
        """Tiền hoàn cho hoa hồng thật, theo snapshot chính sách của link (PLAN-076, ADR-053).

        Không đọc lại chính sách theo giờ hay theo .env hiện tại. Link không dựng lại được snapshot
        (unresolved) giữ cách tính trước PLAN-076 và hiện ở màn Lịch sử để admin xem.
        """
        link_id = _row_get(row, "matched_link_id")
        found = None
        if link_id is not None and self._snapshots_on:
            with self.repo.connect() as conn:
                found = policy_snapshot.for_link(conn, int(link_id), self._policy_defaults())
        if found is None or found.policy is None:
            return self._legacy_cashback(commission_vnd, row)
        quote = cashback_for(commission_vnd, found.policy)
        return Split(
            quote.cashback_vnd,
            found.label,
            quote.fee_reserve_vnd,
            quote.tax_reserve_vnd + quote.other_reserve_vnd,
        )

    def _legacy_cashback(self, commission_vnd: int, row) -> Split:
        """Cách tính trước PLAN-076, chỉ cho link không có snapshot dùng được."""
        created = datetime.strptime(row["link_created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        reserve = self.admin_panel.active_reserve(created)
        policy = replace(
            self._estimate_policy(),
            service_fee_bps=reserve.fee_bps,
            tax_risk_reserve_bps=reserve.tax_reserve_bps,
        )
        if row["estimate_policy"]:
            policy = replace(policy, cashback_share_bps=self.admin_panel.active_share(created).share_bps)
            result = estimate_cashback(commission_vnd, policy, reliable=True)
            return Split(
                result.estimated_cashback_vnd,
                str(row["estimate_policy"]),
                result.fee_reserve_vnd,
                result.tax_risk_reserve_vnd + result.other_reserve_vnd,
            )
        rate = row["cashback_rate_percent"] or self.settings.cashback_rate_percent
        costs = estimate_cashback(commission_vnd, policy, reliable=True)
        return Split(
            quote_displayed_vnd(commission_vnd, int(rate)),
            f"v1.1:{rate}",
            costs.fee_reserve_vnd,
            costs.tax_risk_reserve_vnd,
        )

    def handle_text(
        self,
        telegram_user_id: int,
        username: str | None,
        text: str,
        update_id: int | None = None,
        now: datetime | None = None,
        message_id: int | None = None,
    ) -> BotReply:
        is_new = self.repo.upsert_user(telegram_user_id, username if isinstance(username, str) else None)
        if is_new and self.admin_notifier:
            self.admin_notifier.notify_new_user(telegram_user_id, username if isinstance(username, str) else None)
        if update_id is not None:
            previous = self.repo.get_by_update_id(update_id)
            if previous is not None:
                return self._render_existing(previous)

        stripped = (text or "").strip()
        command = _command_name(stripped)
        moment = now or datetime.now(timezone.utc)
        if command == "/admin":
            return self.admin_panel.menu(telegram_user_id, moment)
        if self.admin_panel.is_admin(telegram_user_id):
            consumed = self.admin_panel.consume_text(telegram_user_id, stripped, moment, message_id=message_id)
            if consumed is not None:
                return consumed

        if not self.allowed(telegram_user_id):
            return BotReply(CLOSED)

        pages = {
            "/huongdan": "guide", "/dieukien": "rules", "/cachtinh": "calc", "/hang": "rank", "/vi": "wallet",
            "/hotro": "support", "/donhang": "orders", "/thongbao": "notify",
        }
        if command:
            self._set_bank_waiting(telegram_user_id, None)
            self.desk.clear(telegram_user_id)
        if command in pages:
            return self._page(pages[command], telegram_user_id)
        if command:
            return self._page("home")
        tiktok_url = parse_tiktok_target(stripped)
        is_link = parse_shopee_target(stripped) is not None or tiktok_url is not None
        only_link = is_link and len(stripped.split()) == 1
        if not only_link:
            # Đang chờ nội dung yêu cầu hỗ trợ: mọi tin (kể cả kèm link) là nội dung ticket.
            desk = self.desk.consume_text(telegram_user_id, username, stripped, now or datetime.now(timezone.utc), update_id)
            if desk is not None:
                return desk
        else:
            self.desk.clear(telegram_user_id)
        waiting_bank = self._bank_waiting(telegram_user_id)
        if waiting_bank and is_link:
            # Đang khai ngân hàng mà dán link sản phẩm: khách muốn mua, bỏ chờ và tạo link như thường.
            self._set_bank_waiting(telegram_user_id, None)
        elif waiting_bank and self.wallet.settings().enabled:
            return self._consume_bank(telegram_user_id, waiting_bank, stripped, now or datetime.now(timezone.utc))
        target = parse_shopee_target(stripped)
        moment = now or datetime.now(timezone.utc)
        if not self._within_rate_limit(telegram_user_id, moment):
            return rate_limited_reply(self.settings.user_cooldown_sec)
        if target is None and tiktok_url is not None:
            return self._tiktok_link(update_id, telegram_user_id, tiktok_url, moment)
        if target is None:
            # Tin không phải link sản phẩm: không lưu nội dung (PLAN-077, dữ liệu tối thiểu), chỉ lưu độ dài.
            if is_shopee_food_link(stripped):
                self._reject(update_id, telegram_user_id, f"[link ShopeeFood · {len(stripped)} ký tự]", "food_link")
                return food_link_reply()
            self._reject(update_id, telegram_user_id, f"[không phải link · {len(stripped)} ký tự]", "invalid_link")
            return self._invalid_link()
        gate = self.desk.terms_gate(telegram_user_id, moment)
        if gate is not None:
            return gate
        try:
            payload = self.client.fetch(target)
            quote = quote_from_payload(payload, moment, self.settings.product_max_age_hours)
        except ProductDataError as exc:
            logger.info("[Cashback] product data rejected code=%s item=%s", exc.code, target.item_id)
            self._reject(update_id, telegram_user_id, target.original_url, exc.code)
            if self.admin_notifier and exc.code in {"timeout", "transport", "http_error", "invalid_json", "api_status"}:
                self.admin_notifier.notify_request_failed(
                    error_type=f"product_data_{exc.code}",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="REQUEST_FAILED",
                )
            if exc.code in _NOT_FOUND_CODES:
                return BotReply(NOT_FOUND)
            return BotReply(STALE)

        resolution = self._resolve_or_reject(update_id, telegram_user_id, target.original_url, moment)
        if resolution is None:
            return BotReply(GENERIC_FAIL)
        # Báo theo hoa hồng chắc chắn; phần Shopee Comm trên 2,5% chỉ ghi là có thể được thêm.
        priced = cashback_for(quote.sure_commission_vnd, resolution)
        cashback = priced.cashback_vnd
        extra = cashback_for(quote.commission_vnd, resolution).cashback_vnd - cashback
        v12 = resolution.pricing_version == "v1.2"
        render = render_success_v12 if v12 else render_success
        try:
            sub_id = self._unique_sub_id()
            affiliate_url = build_an_redir(quote.product_url, self.settings.affiliate_id, sub_id)
        except (ValueError, ProductDataError):
            logger.error("[Cashback] build link failed item=%s", quote.item_id)
            self._reject(update_id, telegram_user_id, target.original_url, "link_build_failed")
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="affiliate_link_generation_failed",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="REQUEST_FAILED",
                )
            return BotReply(GENERIC_FAIL)

        saved = self._save_link(
            {
                "telegram_update_id": update_id,
                "telegram_user_id": telegram_user_id,
                "sub_id": sub_id,
                "original_url": target.original_url[:500],
                "affiliate_url": affiliate_url,
                "item_id": quote.item_id,
                "shop_id": quote.shop_id,
                "product_name": quote.name[:300],
                "price_vnd": quote.price_vnd,
                "estimated_commission": quote.sure_commission_vnd,
                "estimated_cashback": cashback,
                "cashback_rate_percent": resolution.rate_percent,
                "estimate_policy": resolution.label if v12 else None,
                "api_status": quote.api_status,
                "data_source": quote.data_source,
                "product_last_update": quote.last_update.strftime("%Y-%m-%d %H:%M:%S"),
                "cat_name": quote.category,
                "shop_name": quote.shop_name,
                "seller_commission_vnd": quote.seller_commission_vnd,
                "shopee_commission_vnd": quote.shopee_commission_vnd,
                "commission_rate_bps": quote.commission_rate_bps,
                "is_xtra": quote.is_xtra,
                "is_capped": quote.is_capped,
                "link_status": "created",
                "reject_reason": None,
            },
            update_id, telegram_user_id, resolution, priced, moment,
        )
        if not saved:
            return BotReply(GENERIC_FAIL)
        return render(quote.name, quote.price_vnd, cashback, affiliate_url, extra_vnd=extra, capped=bool(quote.is_capped))

    def _resolve_or_reject(self, update_id: int | None, telegram_user_id: int, original_url: str,
                           moment: datetime) -> PolicyResolution | None:
        """Chính sách báo giá lúc `moment`; đọc DB lỗi thì ghi link bị từ chối, báo admin, trả None."""
        try:
            return self._resolve_policy(moment)
        except sqlite3.Error:
            logger.exception("[Cashback] đọc mức dự phòng thất bại")
            self._reject(update_id, telegram_user_id, original_url, "reserve_read_failed")
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="reserve_read_failed",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="REQUEST_FAILED",
                )
            return None

    def _save_link(self, fields: dict, update_id: int | None, telegram_user_id: int, resolution: PolicyResolution,
                   priced, moment: datetime) -> bool:
        """Ghi link đã tạo cùng snapshot chính sách và điều khoản. Lỗi DB thì báo admin, trả False."""
        try:
            self.repo.insert_created(
                fields,
                snapshot=self._snapshot_record(resolution, priced),
                terms=self.desk.link_terms(telegram_user_id, moment) if self._snapshots_on else None,
            )
        except sqlite3.IntegrityError:
            logger.error("[Cashback] db integrity item=%s", fields.get("item_id"))
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="sqlite_integrity_error",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="FAILED_DB_WRITE",
                )
            return False
        except sqlite3.Error:
            logger.exception("[Cashback] db write failed")
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="sqlite_write_error",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="FAILED_DB_WRITE",
                )
            return False
        return True

    def _tiktok_link(self, update_id: int | None, telegram_user_id: int, url: str, moment: datetime) -> BotReply:
        """PLAN-085 giai đoạn A: link TikTok Shop qua RioHub `/product-links`, báo giá cùng cách tính với Shopee."""
        if self.riohub is None or not admin_tiktok.open_for(self.repo, telegram_user_id, self.settings.admin_user_ids):
            self._reject(update_id, telegram_user_id, url, "tiktok_not_open")
            return BotReply(TIKTOK_NOT_OPEN)
        gate = self.desk.terms_gate(telegram_user_id, moment)
        if gate is not None:
            return gate
        try:
            sub_id = self._unique_sub_id()
        except ProductDataError:
            self._reject(update_id, telegram_user_id, url, "link_build_failed")
            return BotReply(GENERIC_FAIL)
        # Rà soát P3: RioHub có thể treo tới 60–90 giây (3 địa chỉ × 20 giây). Gọi ở luồng riêng để vòng nhận tin
        # không đứng; thẻ link đi qua hàng đợi chung (Telegram + Zalo) và được đẩy đi ngay khi xong.
        self.tiktok_runner(lambda: self._tiktok_deliver(update_id, telegram_user_id, url, sub_id, moment))
        return BotReply(TIKTOK_WORKING)

    def _tiktok_deliver(self, update_id: int | None, telegram_user_id: int, url: str, sub_id: str,
                        moment: datetime) -> None:
        try:
            reply = self._tiktok_build(update_id, telegram_user_id, url, sub_id, moment)
        except Exception:
            logger.exception("[Cashback] tạo link TikTok lỗi")
            reply = BotReply(GENERIC_FAIL)
        markup = reply.markup()
        with self.repo.connect() as conn:
            enqueue_event(
                conn, event_key=f"tiktok_link:{sub_id}", event_type="LINK_READY", chat_id=telegram_user_id,
                message_html=reply.text, audience="customer", category="link_ready",
                reply_markup_json=json.dumps(markup, ensure_ascii=False) if markup else None,
                source_ref=f"update:{update_id}",
            )
        if self.after_deferred is not None:
            try:
                self.after_deferred()
            except Exception:
                logger.exception("[Cashback] gửi thẻ link TikTok ngay lỗi; vòng sau sẽ gửi")

    def _tiktok_build(self, update_id: int | None, telegram_user_id: int, url: str, sub_id: str,
                      moment: datetime) -> BotReply:
        try:
            made = self.riohub.create_product_link(url, sub_id)
        except RioHubError as exc:
            logger.info("[Cashback] riohub từ chối link kind=%s code=%s", exc.kind, exc.code or "-")
            self._reject(update_id, telegram_user_id, url, f"tiktok_{exc.kind}")
            if exc.kind == "not_promotable":
                return BotReply(TIKTOK_NOT_PROMOTABLE)
            if self.admin_notifier and exc.kind in {"auth", "creator", "bad_response", "network", "invalid"}:
                self.admin_notifier.notify_request_failed(
                    error_type=f"riohub_{exc.kind}",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="REQUEST_FAILED",
                )
            return BotReply(GENERIC_FAIL)
        product = made.product or {}
        prices = price_range_vnd(product)
        rate_bps = commission_rate_bps(product)
        name = product_title(product)
        if not prices or rate_bps is None or not name:
            self._reject(update_id, telegram_user_id, url, "tiktok_no_product")
            return BotReply(TIKTOK_NO_INFO)
        price_vnd = prices[0]  # khoảng giá: báo theo mức thấp (PLAN-085 A4)
        commission_vnd = price_vnd * rate_bps // 10_000
        resolution = self._resolve_or_reject(update_id, telegram_user_id, url, moment)
        if resolution is None:
            return BotReply(GENERIC_FAIL)
        priced = cashback_for(commission_vnd, resolution)
        v12 = resolution.pricing_version == "v1.2"
        product_id = made.product_id or ""
        saved = self._save_link(
            {
                "telegram_update_id": update_id,
                "telegram_user_id": telegram_user_id,
                "sub_id": sub_id,
                "original_url": url[:500],
                "affiliate_url": made.affiliate_link,
                "item_id": int(product_id) if product_id.isdigit() else None,
                "shop_id": None,
                "product_name": name[:300],
                "price_vnd": price_vnd,
                "estimated_commission": commission_vnd,
                "estimated_cashback": priced.cashback_vnd,
                "cashback_rate_percent": resolution.rate_percent,
                "estimate_policy": resolution.label if v12 else None,
                "api_status": "riohub",
                "data_source": "riohub",
                "product_last_update": moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "commission_rate_bps": rate_bps,
                "platform": "tiktok",
                "link_status": "created",
                "reject_reason": None,
            },
            update_id, telegram_user_id, resolution, priced, moment,
        )
        if not saved:
            return BotReply(GENERIC_FAIL)
        render = render_success_v12 if v12 else render_success
        return render(name, price_vnd, priced.cashback_vnd, made.affiliate_link, tiktok=True)

    def _invalid_link(self) -> BotReply:
        reply = invalid_link_reply()
        return replace(reply, text=with_tiktok(reply.text)) if self.tiktok_open() else reply

    def _v12_ready(self) -> bool:
        if self.settings.estimate_policy != "v1.2":
            return False
        if "estimate_policy" not in self.repo.column_names("link_requests"):
            logger.warning("[Cashback] policy v1.2 chưa có cột estimate_policy, giữ công thức V1.1")
            return False
        return True

    def _estimate_policy(self) -> EstimatePolicy:
        return EstimatePolicy(
            cashback_share_bps=self.settings.cashback_rate_percent * 100,
            service_fee_bps=self.settings.estimate_fee_bps,
            tax_risk_reserve_bps=self.settings.estimate_tax_reserve_bps,
            other_cost_reserve_vnd=self.settings.estimate_other_reserve_vnd,
            rounding_unit=self.settings.estimate_rounding_unit,
        )

    def _resolve_policy(self, now: datetime) -> PolicyResolution:
        """Một lần chọn chính sách cho link báo giá lúc `now`. Báo giá và snapshot dùng chung kết quả."""
        return self.admin_panel.resolve_policy(now, v12=self._v12_ready())

    def _snapshot_record(self, resolution: PolicyResolution, priced) -> dict | None:
        return policy_snapshot.record(resolution, priced) if self._snapshots_on else None

    def _within_rate_limit(self, telegram_user_id: int, now: datetime) -> bool:
        return self.repo.consume_link_attempt(
            telegram_user_id,
            now,
            self.settings.user_rate_limit,
            self.settings.user_rate_window_sec,
            self.settings.user_cooldown_sec,
        )

    def _unique_sub_id(self) -> str:
        for _ in range(8):
            sub_id = new_sub_id()
            if not self.repo.sub_id_exists(sub_id):
                return sub_id
        raise ProductDataError("sub_id_exhausted")

    def _reject(self, update_id: int | None, telegram_user_id: int, original_url: str, reason: str) -> None:
        try:
            self.repo.insert_rejected(
                {
                    "telegram_update_id": update_id,
                    "telegram_user_id": telegram_user_id,
                    "original_url": (original_url or "")[:500] or "-",
                    "reject_reason": reason,
                    "link_status": "rejected",
                }
            )
        except sqlite3.Error:
            logger.exception("[Cashback] reject log failed")

    def _render_existing(self, row: LinkRow) -> BotReply:
        if row.link_status == "created" and row.affiliate_url and row.product_name is not None:
            render = render_success_v12 if row.estimate_policy else render_success
            return render(
                row.product_name,
                row.price_vnd or 0,
                row.estimated_cashback or 0,
                row.affiliate_url,
                tiktok=row.platform == "tiktok",
            )
        if row.reject_reason in _NOT_FOUND_CODES:
            return BotReply(NOT_FOUND)
        if row.reject_reason == "invalid_link":
            return self._invalid_link()
        if row.reject_reason == "food_link":
            return food_link_reply()
        # Link TikTok bị từ chối: trả đúng lý do như lần đầu (rà soát 2026-10-26).
        tiktok = {"tiktok_not_open": TIKTOK_NOT_OPEN, "tiktok_not_promotable": TIKTOK_NOT_PROMOTABLE,
                  "tiktok_no_product": TIKTOK_NO_INFO}
        if (row.reject_reason or "").startswith("tiktok_"):
            return BotReply(tiktok.get(row.reject_reason, GENERIC_FAIL))
        return BotReply(STALE)
