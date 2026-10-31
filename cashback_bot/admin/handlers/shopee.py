"""🛒 Shopee Affiliate trong /admin: màn trạng thái, đồng bộ, CSV, dán cookie.

Chờ dán cookie ghi ở bot_state (`shopee_auth_waiting:<admin>`); phần JSON cookie bị Telegram tách
được gom trong RAM tối đa COOKIE_PART_TTL. Cookie không bao giờ ghi vào lịch sử hay log.
"""

from __future__ import annotations

import html
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from cashback_bot import addlivetag_orders
from cashback_bot.admin.base import BaseAdminHandler
from cashback_bot.admin.common import ICT, expired_button, stamp
from cashback_bot.admin.handlers.reserve import vn_time
from cashback_bot.admin.handlers.stats import conversions_csv
from cashback_bot.admin.handlers.sync import AutoSyncAdmin, status_label
from cashback_bot.admin.ui import (
    NAV_KEYBOARD,
    SHOPEE_KEYBOARD_DISCONNECTED,
    SHOPEE_PROMPT_KEYBOARD,
    shopee_connected_keyboard,
    shopee_prompt_cookie_text,
    shopee_text,
)
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.shopee_client import ShopeeAffiliateClient
from cashback_bot.shopee_cookie import IncompleteCookieError, parse_cookies, save_cookies
from cashback_bot.sync_scheduler import SyncCoordinator, request_manual

if TYPE_CHECKING:
    from cashback_bot.admin.panel import AdminPanel

# Telegram tách tin dài hơn 4.096 ký tự. Gom các phần JSON cookie trong RAM, không ghi DB.
COOKIE_PART_TTL = timedelta(minutes=2)
MAX_COOKIE_CHARS = 64_000
AUTH = "c:shopee:auth"


class ShopeeAdmin(BaseAdminHandler):
    name = "shopee"
    callback_prefixes = ("c:shopee:",)
    callback_exact = ("c:menu:shopee",)

    def __init__(self, panel: AdminPanel) -> None:
        self.panel = panel

    def keeps_state(self, data: str) -> bool:
        # Bấm bất kỳ nút nào khác (kể cả ✖️ Hủy) là thôi chờ cookie.
        return data == AUTH

    def clear_state(self, user_id: int) -> None:
        self.panel._cookie_parts.pop(user_id, None)
        try:
            with self.panel._connect() as conn:
                conn.execute("DELETE FROM bot_state WHERE key = ?", (f"shopee_auth_waiting:{user_id}",))
        except sqlite3.Error:
            pass

    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        if data == "c:menu:shopee":
            return self.screen(now)
        if data == "c:shopee:sync":
            return self._sync(now)
        if data == "c:shopee:csv":
            return self._csv(now)
        if data in {"c:shopee:auto:on", "c:shopee:auto:off"}:
            return self._auto(user_id, data.endswith(":on"), now)
        if data == AUTH:
            return self._auth_start(user_id)
        return expired_button()

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        try:
            with self.panel._connect() as conn:
                waiting = conn.execute(
                    "SELECT value FROM bot_state WHERE key = ?",
                    (f"shopee_auth_waiting:{user_id}",),
                ).fetchone()
            if waiting and waiting[0] == "1":
                return self._consume_cookie(user_id, text, now, message_id=message_id)
        except sqlite3.Error:
            pass
        return None

    def screen(self, now: datetime, notice: str = "") -> BotReply:
        db_path = self.panel.db_path
        with self.panel._connect() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "shopee_cookies" not in tables:
                return BotReply("Tính năng Shopee Affiliate chưa được khởi tạo bảng trong DB.", inline_keyboard=NAV_KEYBOARD)

            c_row = conn.execute("SELECT * FROM shopee_cookies WHERE id = 1").fetchone()
            status = str(c_row["status"]) if c_row else "disconnected"
            account_name = str(c_row["account_name"]) if c_row and c_row["account_name"] else None
            last_sync = vn_time(str(c_row["last_sync_at"])) if c_row and c_row["last_sync_at"] else None
            last_err = str(c_row["last_error"]) if c_row and c_row["last_error"] else None

            clicks_count = int(conn.execute("SELECT COUNT(*) FROM shopee_clicks").fetchone()[0]) if "shopee_clicks" in tables else 0
            # Màn Shopee chỉ đếm đơn Shopee; đơn TikTok xem ở 🎵 TikTok Shop.
            orders_count = int(conn.execute(
                "SELECT COUNT(*) FROM shopee_conversions WHERE platform = 'shopee'").fetchone()[0]) if "shopee_conversions" in tables else 0
            matched_count = (
                int(conn.execute("SELECT COUNT(*) FROM shopee_conversions WHERE platform = 'shopee' "
                                 "AND matched_link_id IS NOT NULL").fetchone()[0])
                if "shopee_conversions" in tables
                else 0
            )

        auto_sync = status_label(TrackingRepository(db_path), self.panel.auto_sync, now)
        crosscheck = addlivetag_orders.status_line(TrackingRepository(db_path))
        kb = shopee_connected_keyboard() if status == "connected" else SHOPEE_KEYBOARD_DISCONNECTED
        text = shopee_text(
            status=status,
            account_name=account_name,
            last_sync=last_sync,
            total_clicks=clicks_count,
            total_orders=orders_count,
            matched_orders=matched_count,
            last_error=last_err,
            notice=notice,
            auto_sync=auto_sync,
            crosscheck=crosscheck,
        )
        return BotReply(text, inline_keyboard=kb)

    def _auto(self, user_id: int, resume: bool, now: datetime) -> BotReply:
        """Tạm dừng / tiếp tục tự đồng bộ. Không bật được khi cờ .env tắt (không có đường vượt cờ qua Telegram)."""
        repo = TrackingRepository(self.panel.db_path)
        auto_sync = self.panel.auto_sync
        if not auto_sync.enabled:
            return AutoSyncAdmin(repo, auto_sync).home(
                now, "ⓘ Tự đồng bộ đang tắt trong cấu hình. Chủ bot bật bằng SHOPEE_AUTO_SYNC_ENABLED trong .env."
            )
        changed = SyncCoordinator(repo, cfg=auto_sync, clock=lambda: now).set_paused(user_id, not resume)
        if changed:
            self.panel._log_setting(user_id, "shopee_auto_sync_pause", {"paused": resume}, {"paused": not resume}, now)
        notice = "▶️ Đã tiếp tục tự đồng bộ (lượt tới sau 5 phút)." if resume else "⏸️ Đã tạm dừng tự đồng bộ. 🔄 thủ công vẫn dùng được."
        return AutoSyncAdmin(repo, auto_sync).home(now, notice)

    def _sync(self, now: datetime) -> BotReply:
        # Không gọi Shopee trong lúc trả lời nút: xếp lượt, luồng nền chạy rồi nhắn kết quả (PLAN-080).
        current = request_manual(TrackingRepository(self.panel.db_path), now)
        if current is not None:
            run_id, trigger = current
            label = "tự động" if trigger == "auto" else "thủ công"
            return self.screen(now, notice=(
                f"🔄 Shopee đang được đồng bộ {label}. Mã lượt: #{run_id}. "
                "Bạn có thể xem tiến độ tại màn ⏱ Tự động đồng bộ."
            ))
        return self.screen(now, notice="⏳ Đã bắt đầu đồng bộ. Xong bot sẽ nhắn kết quả.")

    def _csv(self, now: datetime) -> BotReply:
        since = now - timedelta(days=30)
        with self.panel._connect() as conn:
            data, count = conversions_csv(conn, since)
        name = f"shopee-don-30-ngay-{now.astimezone(ICT).strftime('%Y%m%d')}.csv"
        reply = self.screen(now, notice=f"📤 Đã gửi file {count} dòng đơn 30 ngày.")
        return replace(reply, document=(name, data))

    def _auth_start(self, user_id: int) -> BotReply:
        with self.panel._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES (?, '1')
                ON CONFLICT(key) DO UPDATE SET value = '1'
                """,
                (f"shopee_auth_waiting:{user_id}",),
            )
        return BotReply(shopee_prompt_cookie_text(), inline_keyboard=SHOPEE_PROMPT_KEYBOARD)

    def _consume_cookie(
        self,
        user_id: int,
        text: str,
        now: datetime,
        message_id: int | None = None,
    ) -> BotReply:
        parts = self.panel._cookie_parts
        pending = parts.pop(user_id, None)
        if pending and now - pending[1] <= COOKIE_PART_TTL:
            text = pending[0] + text
        try:
            cookies = parse_cookies(text)
        except IncompleteCookieError:
            if len(text) > MAX_COOKIE_CHARS:
                self.clear_state(user_id)
                return BotReply(
                    "❌ <b>Cookie quá dài.</b> Hãy dán chuỗi <code>name=value;</code> thay vì JSON.",
                    inline_keyboard=SHOPEE_PROMPT_KEYBOARD,
                    delete_message_id=message_id,
                )
            # Vẫn chờ: phần tiếp theo cũng đi vào đây và cũng bị xoá khỏi chat.
            parts[user_id] = (text, now)
            return BotReply(
                "📥 Đã nhận một phần cookie, đang chờ phần còn lại…",
                inline_keyboard=SHOPEE_PROMPT_KEYBOARD,
                delete_message_id=message_id,
            )
        except ValueError as exc:
            self.clear_state(user_id)
            return BotReply(
                f"❌ <b>Không tìm thấy cookie hợp lệ:</b> {html.escape(str(exc))}.\n\nBấm 🔑 để dán lại.",
                inline_keyboard=SHOPEE_KEYBOARD_DISCONNECTED,
                delete_message_id=message_id,
            )

        self.clear_state(user_id)
        client = ShopeeAffiliateClient(cookies)
        status_res = client.check_status()
        if not status_res.ok:
            return BotReply(
                f"❌ <b>Không thể kết nối Shopee:</b> {html.escape(status_res.error_message)}.\n\nBấm 🔑 để dán cookie mới.",
                inline_keyboard=SHOPEE_KEYBOARD_DISCONNECTED,
                delete_message_id=message_id,
            )

        save_cookies(cookies)
        # Chỉ ghi tên tài khoản, không bao giờ ghi cookie vào lịch sử.
        self.panel._log_setting(user_id, "shopee_cookie", None, {"account": status_res.username or "Shopee Affiliate"}, now)
        with self.panel._connect() as conn:
            now_str = stamp(now)
            conn.execute(
                """
                INSERT INTO shopee_cookies (id, status, account_name, last_error, updated_at)
                VALUES (1, 'connected', ?, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = 'connected',
                    account_name = excluded.account_name,
                    last_error = NULL,
                    updated_at = excluded.updated_at
                """,
                (status_res.username or "Shopee Affiliate", now_str),
            )

        return BotReply(
            f"✅ <b>Đã kết nối Shopee Affiliate thành công!</b>\n\n"
            f"• Tài khoản: <b>{html.escape(status_res.username or 'Affiliate')}</b>\n"
            f"• Cookie đã lưu riêng (quyền 0600). Bot xoá tin nhắn chứa cookie khỏi chat.\n\n"
            f"Bạn có thể bấm 🔄 Đồng bộ ngay.",
            inline_keyboard=shopee_connected_keyboard(),
            delete_message_id=message_id,
        )
