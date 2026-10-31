"""Bảng đăng ký handler cho AdminRouter của AdminPanel.

Thứ tự đăng ký = thứ tự hỏi khi admin gõ chữ (sau lệnh /tim):
cookie Shopee → mô phỏng → hỗ trợ → ví → giữ chân → insights → chính sách (dự phòng → chia → số %).
Callback không trùng nhau giữa các handler (router kiểm lúc đăng ký), nên thứ tự không ảnh hưởng nút bấm.

Màn domain cũ (ví, insights, TikTok…) giữ nguyên lớp và chữ ký; `DomainRoute` bọc chúng về
`route(user_id, data, now)` và khai báo luật giữ trạng thái chờ của từng màn.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from cashback_bot import showcase
from cashback_bot.admin.base import BaseAdminHandler
from cashback_bot.admin.common import ICT, expired_button
from cashback_bot.admin.handlers.announce import AnnounceAdmin
from cashback_bot.admin.handlers.deals import DealsAdmin
from cashback_bot.admin.handlers.engagement import EngagementAdmin
from cashback_bot.admin.handlers.policy import PolicyAdmin
from cashback_bot.admin.handlers.readiness import ReadinessAdmin
from cashback_bot.admin.handlers.reconciliation import ReconciliationAdmin
from cashback_bot.admin.handlers.settlement import SettlementAdmin
from cashback_bot.admin.handlers.shopee import ShopeeAdmin
from cashback_bot.admin.handlers.simulation import SimulationAdmin
from cashback_bot.admin.handlers.stats import PERIODS, collect
from cashback_bot.admin.handlers.sync import AutoSyncAdmin
from cashback_bot.admin.handlers.terms import TermsAdmin
from cashback_bot.admin.handlers.tiktok import TikTokAdmin
from cashback_bot.admin.handlers.validation import ValidationAdmin
from cashback_bot.admin.notify.customer_notify import CustomerNotifyAdmin
from cashback_bot.admin.router import AdminRouter
from cashback_bot.admin.ui import stats_detail_text, stats_keyboard, stats_text
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply

if TYPE_CHECKING:
    from cashback_bot.admin.panel import AdminPanel

logger = logging.getLogger("cashback_bot")

Handle = Callable[[int, str, datetime], BotReply]
TextHandle = Callable[[int, str, datetime], "BotReply | None"]

_STATS = re.compile(r"^c:st:(today|7d|30d|all)(:more)?$")


class DomainRoute(BaseAdminHandler):
    """Adapter: một màn domain (lớp *Admin dựng theo từng lần bấm) thành BaseAdminHandler."""

    def __init__(
        self,
        name: str,
        handle: Handle,
        *,
        prefixes: tuple[str, ...] = (),
        exact: tuple[str, ...] = (),
        text: TextHandle | None = None,
        waiting: dict | None = None,
        keeps: Callable[[str], bool] | None = None,
    ) -> None:
        self.name = name
        self.callback_prefixes = prefixes
        self.callback_exact = exact
        self._handle = handle
        self._text = text
        self._waiting = waiting
        self._keeps = keeps

    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        return self._handle(user_id, data, now)

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        return None if self._text is None else self._text(user_id, text, now)

    def keeps_state(self, data: str) -> bool:
        return self.can_handle(data) if self._keeps is None else self._keeps(data)

    def clear_state(self, user_id: int) -> None:
        if self._waiting is not None:
            self._waiting.pop(user_id, None)


def build_router(panel: AdminPanel) -> AdminRouter:
    router = AdminRouter()
    audit = panel._log_setting

    def repo() -> TrackingRepository:
        # Mỗi lần bấm một repo mới, như trước khi có router.
        return TrackingRepository(panel.db_path)

    # --- Có trạng thái chờ gõ chữ: đăng ký theo thứ tự ưu tiên -------------------------------
    router.register(ShopeeAdmin(panel))
    router.register(SimulationAdmin(panel))
    router.register(DomainRoute(
        "support", lambda u, d, n: panel._support().route(u, d, n), prefixes=("c:hp:",),
        text=lambda u, t, n: panel._support().consume_text(u, t, n), waiting=panel._support_waiting,
    ))
    router.register(DomainRoute(
        "wallet", lambda u, d, n: panel._wallet_admin().route(u, d, n), prefixes=("c:wl:",), exact=("c:menu:wallet",),
        text=lambda u, t, n: panel._wallet_admin().consume_text(u, t, n), waiting=panel._wallet_waiting,
        keeps=lambda d: d.startswith(("c:wl:mv:", "c:wl:vb:")),
    ))
    router.register(DomainRoute(
        "retention", lambda u, d, n: panel._retention().route(u, d, n), prefixes=("c:rt:",),
        text=lambda u, t, n: panel._retention().consume_text(u, t, n), waiting=panel._retention_waiting,
        keeps=lambda d: d.startswith("c:rt:e:"),
    ))
    # Màn khác (kể cả ◀️ Tổng quan, ✖️ Hủy) là thôi chờ gõ: tin kế tiếp không bị hiểu nhầm là từ khoá / số.
    router.register(DomainRoute(
        "insights", lambda u, d, n: panel._insights().route(u, d, n), prefixes=("c:in:",),
        text=lambda u, t, n: panel._insights().consume_text(u, t, n), waiting=panel._insights_waiting,
        keeps=lambda d: d in ("c:in:cost", "c:in:f") or d.startswith("c:in:t:"),
    ))
    router.register(PolicyAdmin(panel))

    # --- Chỉ nút bấm ------------------------------------------------------------------------
    router.register(DomainRoute("stats", lambda u, d, n: _stats(panel, d, n), prefixes=("c:st:",)))
    router.register(DomainRoute("showcase", lambda u, d, n: _showcase(panel, d, n), prefixes=("c:pb:",)))
    router.register(DomainRoute(
        "announce", lambda u, d, n: AnnounceAdmin(repo(), audit=audit).route(u, d, n), prefixes=("c:an:",)))
    router.register(DomainRoute(
        "deals", lambda u, d, n: DealsAdmin(repo(), audit=audit).route(u, d, n), prefixes=("c:dl:",)))
    router.register(DomainRoute(
        "engagement", lambda u, d, n: EngagementAdmin(repo(), audit=audit).route(u, d, n), prefixes=("c:eg:",)))
    router.register(DomainRoute(
        "tiktok", lambda u, d, n: TikTokAdmin(repo(), panel.tiktok_configured, audit=audit).route(u, d, n),
        prefixes=("c:tk:",),
    ))
    router.register(DomainRoute(
        "validation", lambda u, d, n: ValidationAdmin(repo(), audit=audit).route(u, d, n), prefixes=("c:cv:",)))
    router.register(DomainRoute(
        "settlement", lambda u, d, n: SettlementAdmin(repo()).route(u, d, n), prefixes=("c:sm:",)))
    router.register(DomainRoute(
        "terms", lambda u, d, n: TermsAdmin(repo(), audit=audit).route(u, d, n), prefixes=("c:tm:",)))
    router.register(DomainRoute(
        "customer_notify",
        lambda u, d, n: CustomerNotifyAdmin(
            repo(), panel.customer_notifications_enabled, audit=audit,
            test_ids=panel.customer_notification_test_ids,
        ).route(u, d, n),
        prefixes=("c:nt:",),
    ))
    router.register(DomainRoute(
        "readiness", lambda u, d, n: ReadinessAdmin(repo()).route(u, d, n), prefixes=("c:rd:",)))
    # Hai màn có chữ ký route khác: (data) và (data, now).
    router.register(DomainRoute(
        "reconciliation", lambda u, d, n: ReconciliationAdmin(repo(), panel.auto_sync.reconcile_lookup).route(d),
        prefixes=("c:rc:",),
    ))
    router.register(DomainRoute(
        "sync", lambda u, d, n: AutoSyncAdmin(repo(), panel.auto_sync).route(d, n), prefixes=("c:sy:",)))
    return router


def _stats(panel: AdminPanel, data: str, now: datetime) -> BotReply:
    matched = _STATS.fullmatch(data or "")
    if matched is None:
        return expired_button()
    period, detail = matched.group(1), bool(matched.group(2))
    try:
        with panel._connect() as conn:
            stats = collect(conn, period, now)
    except sqlite3.OperationalError:
        logger.exception("[Cashback] thống kê lỗi")
        return BotReply("Chưa đọc được dữ liệu thống kê trên database này.", inline_keyboard=stats_keyboard(period))
    since = stats.since.astimezone(ICT).strftime("00:00 %d/%m/%Y") if stats.since else None
    render = stats_detail_text if detail else stats_text
    text = render(stats, period_label=PERIODS[period][0], since=since)
    return BotReply(text, inline_keyboard=stats_keyboard(period, detail))


def _showcase(panel: AdminPanel, data: str, now: datetime) -> BotReply:
    """🖼 Ảnh đăng bài: chỉnh mục hiển thị rồi tạo ảnh số liệu thật (showcase.py)."""
    try:
        return showcase.ShowcaseAdmin(TrackingRepository(panel.db_path)).route(data, now)
    except sqlite3.OperationalError:
        logger.exception("[Cashback] ảnh đăng bài lỗi")
        return BotReply("Chưa đọc được dữ liệu trên database này.", inline_keyboard=showcase.NAV)
