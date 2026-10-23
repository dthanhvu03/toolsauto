"""Nhận link, kiểm tra Product Data, tạo một sub_id, lưu tracking."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cashback_bot.admin_policy import AdminPanel
from cashback_bot.affiliate import build_an_redir, new_sub_id
from cashback_bot.config import Settings
from cashback_bot.pricing import EstimatePolicy, estimate_cashback, quote_displayed_vnd
from cashback_bot.db import LinkRow, TrackingRepository
from cashback_bot.messages import (
    CLOSED,
    CLOSED_ALERT,
    GENERIC_FAIL,
    DIEUKIEN,
    HUONGDAN,
    NOT_FOUND,
    STALE,
    TIP_ALERT,
    BotReply,
    hang_message,
    home_reply,
    how_to_calc,
    invalid_link_reply,
    page_reply,
    rate_limited_reply,
    render_success,
    render_success_v12,
)
from cashback_bot.product_data import ProductDataClient, ProductDataError, quote_from_payload
from cashback_bot.ranks import MEMBERSHIP_CUTOVER
from cashback_bot.shopee_url import parse_shopee_target

logger = logging.getLogger("cashback_bot")

if TYPE_CHECKING:
    from cashback_bot.admin_notify import AdminNotifier


def _command_name(text: str) -> str | None:
    token = text.split(maxsplit=1)[0] if text else ""
    if not token.startswith("/"):
        return None
    return token.split("@", 1)[0].lower()

_NOT_FOUND_CODES = {"not_found"}


class CashbackService:
    def __init__(
        self,
        settings: Settings,
        repo: TrackingRepository,
        client: ProductDataClient,
        admin_notifier: "AdminNotifier | None" = None,
    ):
        self.settings = settings
        self.repo = repo
        self.client = client
        self.admin_notifier = admin_notifier
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
        )

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
        reply = self.handle_text(user_id, sender.get("username"), text, update_id)
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
            reply = self._customer_callback(user_id, data, str(chat.get("type") or ""))
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

    def _customer_callback(self, user_id: int, data: str, chat_type: str) -> BotReply:
        if chat_type != "private":
            return BotReply("")
        if not self.allowed(user_id):
            return BotReply("", toast=CLOSED_ALERT, show_alert=True)
        if data == "u:tip":
            return BotReply("", toast=TIP_ALERT, show_alert=True)
        page = self._page(data.removeprefix("u:p:")) if data.startswith("u:p:") else None
        if page is None:
            return BotReply("", toast="Nút này không còn hiệu lực.")
        return page

    def _page(self, name: str) -> BotReply | None:
        """Trang thông tin dùng chung cho lệnh gõ tay và nút u:p:*."""
        if name == "home":
            return home_reply(show_rank=MEMBERSHIP_CUTOVER)
        if name == "guide":
            return page_reply(HUONGDAN)
        if name == "rules":
            return page_reply(DIEUKIEN)
        if name == "calc":
            return page_reply(how_to_calc(self._v12_ready()))
        if name == "rank":
            return page_reply(hang_message())
        return None

    def handle_text(
        self,
        telegram_user_id: int,
        username: str | None,
        text: str,
        update_id: int | None = None,
        now: datetime | None = None,
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
            consumed = self.admin_panel.consume_text(telegram_user_id, stripped, moment)
            if consumed is not None:
                return consumed

        if not self.allowed(telegram_user_id):
            return BotReply(CLOSED)

        pages = {"/huongdan": "guide", "/dieukien": "rules", "/cachtinh": "calc", "/hang": "rank"}
        if command in pages:
            return self._page(pages[command])
        if command:
            return self._page("home")
        target = parse_shopee_target(stripped)
        moment = now or datetime.now(timezone.utc)
        if not self._within_rate_limit(telegram_user_id, moment):
            return rate_limited_reply(self.settings.user_cooldown_sec)
        if target is None:
            self._reject(update_id, telegram_user_id, stripped[:500], "invalid_link")
            return invalid_link_reply()
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

        try:
            cashback, policy_id, render, rate_percent = self._quote_cashback(quote.commission_vnd, moment)
        except sqlite3.Error:
            logger.exception("[Cashback] đọc mức dự phòng thất bại item=%s", quote.item_id)
            self._reject(update_id, telegram_user_id, target.original_url, "reserve_read_failed")
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="reserve_read_failed",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="REQUEST_FAILED",
                )
            return BotReply(GENERIC_FAIL)
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

        try:
            self.repo.insert_created(
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
                    "estimated_commission": quote.commission_vnd,
                    "estimated_cashback": cashback,
                    "cashback_rate_percent": rate_percent,
                    "estimate_policy": policy_id,
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
                }
            )
        except sqlite3.IntegrityError:
            logger.error("[Cashback] db integrity item=%s", quote.item_id)
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="sqlite_integrity_error",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="FAILED_DB_WRITE",
                )
            return BotReply(GENERIC_FAIL)
        except sqlite3.Error:
            logger.exception("[Cashback] db write failed")
            if self.admin_notifier:
                self.admin_notifier.notify_request_failed(
                    error_type="sqlite_write_error",
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    status="FAILED_DB_WRITE",
                )
            return BotReply(GENERIC_FAIL)

        return render(quote.name, quote.price_vnd, cashback, affiliate_url)

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

    def _quote_cashback(self, commission_vnd: int, now: datetime):
        """Trả (tiền hoàn, mã chính sách, hàm hiển thị, tỷ lệ chia %)."""
        rate = self.settings.cashback_rate_percent
        if not self._v12_ready():
            return quote_displayed_vnd(commission_vnd, rate), None, render_success, rate
        # Mức admin áp dụng (ADR-047, ADR-048); chưa có thì là .env.
        reserve = self.admin_panel.active_reserve(now)
        share = self.admin_panel.active_share(now)
        policy = replace(
            self._estimate_policy(),
            cashback_share_bps=share.share_bps,
            service_fee_bps=reserve.fee_bps,
            tax_risk_reserve_bps=reserve.tax_reserve_bps,
        )
        result = estimate_cashback(commission_vnd, policy, reliable=True)
        policy_id = result.policy_id
        if reserve.policy_id is not None:
            policy_id += f"+r{reserve.policy_id}"
        if share.policy_id is not None:
            policy_id += f"+s{share.policy_id}"
        return result.estimated_cashback_vnd, policy_id, render_success_v12, share.share_bps // 100

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
            )
        if row.reject_reason in _NOT_FOUND_CODES:
            return BotReply(NOT_FOUND)
        if row.reject_reason == "invalid_link":
            return invalid_link_reply()
        return BotReply(STALE)
