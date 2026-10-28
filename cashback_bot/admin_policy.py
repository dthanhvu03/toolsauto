"""Phiên bản chính sách cho /admin.

Xác nhận chỉ lưu bản ghi bất biến với customer_effect=none.
Không đổi báo giá khách, không chi trả, không ghi database production.
"""

from __future__ import annotations

import html
import json
import logging
import re
import secrets
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cashback_bot.admin_reserve import (
    ACCOUNT_KINDS,
    KIND_CODES,
    MAX_RESERVE_BPS,
    OPEN_STEPS,
    SHARE_OPEN_STEPS,
    AppliedReserve,
    AppliedShare,
    POLICY_TABLES,
    active_reserve,
    active_share,
    cancel_scheduled,
    cancelled_ids,
    effective_from,
    next_midnight,
    parse_when,
    recent_commissions,
    resolve_policy,
    upcoming_reserves,
    upcoming_shares,
    vn_time,
)
from cashback_bot.admin_reserve import SCHEMA_PATH as RESERVE_SCHEMA_PATH
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_reserve import CANCEL_SCHEMA_PATH, SHARE_SCHEMA_PATH
from cashback_bot.admin_stats import PERIODS, collect, conversions_csv
from cashback_bot.admin_ui import (
    BACK_HOME,
    FEE_KEYBOARD,
    GLOSSARY,
    MENU_KEYBOARD,
    NAV_KEYBOARD,
    ORDERS_MENU_KEYBOARD,
    POLICY_KEYBOARD,
    RANK_KEYBOARD,
    SHOPEE_KEYBOARD_DISCONNECTED,
    SETTINGS_MENU_KEYBOARD,
    SHOPEE_PROMPT_KEYBOARD,
    collecting_keyboard,
    collecting_text,
    command_copy_text,
    decision_keyboard,
    fee_text,
    history_text,
    home_text,
    policy_text,
    quote_label,
    rank_preview_text,
    rank_text,
    settings_text,
    reserve_decision_keyboard,
    reserve_keep_keyboard,
    reserve_kind_keyboard,
    reserve_kind_text,
    reserve_preview_text,
    reserve_value_text,
    reserve_when_keyboard,
    reserve_when_text,
    share_cancel_keyboard,
    share_preview_text,
    share_value_text,
    share_when_text,
    shopee_connected_keyboard,
    shopee_prompt_cookie_text,
    shopee_text,
    SIM_PROMPT_KEYBOARD,
    policy_cancel_text,
    simulation_keyboard,
    simulation_prompt_text,
    simulation_text,
    with_rows,
    stats_detail_text,
    stats_keyboard,
    stats_text,
)
from cashback_bot.config import AutoSyncConfig
from cashback_bot.admin_customer_notify import CustomerNotifyAdmin
from cashback_bot.admin_reconciliation import ReconciliationAdmin
from cashback_bot.admin_sync import AutoSyncAdmin, status_label
from cashback_bot.admin_readiness import ReadinessAdmin
from cashback_bot.admin_settlement import SettlementAdmin
from cashback_bot.admin_support import SupportAdmin
from cashback_bot.admin_terms import TermsAdmin
from cashback_bot.admin_validation import LISTS as VALIDATION_LISTS
from cashback_bot.admin_validation import ValidationAdmin
from cashback_bot.admin_insights import InsightsAdmin, goal_history
from cashback_bot.admin_retention import RetentionAdmin
from cashback_bot.admin_tiktok import TikTokAdmin
from cashback_bot.admin_tiktok import history_line as tiktok_history
from cashback_bot.admin_retention import history_line as retention_history
from cashback_bot.admin_engagement import EngagementAdmin
from cashback_bot.admin_engagement import history_line as engagement_history
from cashback_bot.admin_announce import AnnounceAdmin
from cashback_bot.admin_announce import history_line as announce_history
from cashback_bot.admin_deals import DealsAdmin
from cashback_bot.admin_deals import history_line as deals_history
from cashback_bot.admin_wallet import WalletAdmin
from cashback_bot.wallet import Wallet
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd
from cashback_bot import insights, payouts, policy_snapshot, showcase
from cashback_bot.pricing import MAX_SHARE_BPS, CashbackQuote, EstimatePolicy, PolicyResolution, cashback_for
from cashback_bot.shopee_client import ShopeeAffiliateClient
from cashback_bot.shopee_cookie import IncompleteCookieError, parse_cookies, save_cookies
from cashback_bot.sync_scheduler import SyncCoordinator, request_manual

logger = logging.getLogger("cashback_bot")

SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "004_admin_policy.sql"
CONFIRM_TTL = timedelta(minutes=10)
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
TIERS = {"BRONZE": "Đồng", "SILVER": "Bạc", "GOLD": "Vàng"}
TIER_EMOJI = {"BRONZE": "🥉", "SILVER": "🥈", "GOLD": "🥇"}
RESERVE_NAMES = {"estimate_fee_reserve": "Phí dự phòng", "estimate_tax_reserve": "Thuế dự phòng"}
_ACTIONS = {
    "draft": "Tạo bản nháp",
    "preview": "Xem trước",
    "confirm": "Xác nhận",
    "cancel": "Hủy",
    "reserve_apply": "Áp dụng cho khách",
    "share_apply": "Áp dụng cho khách",
    "reserve_cancel": "Huỷ lịch hẹn",
    "share_cancel": "Huỷ lịch hẹn",
}
_RESULTS = {
    "collecting": "đang nhập",
    "preview": "chờ xác nhận",
    "confirmed": "đã lưu",
    "cancelled": "đã hủy",
    "expired": "hết hạn",
    "applied": "đã áp dụng",
}
DIRECTIONAL_BPS = {"BRONZE": 6_000, "SILVER": 6_500, "GOLD": 7_000}
SAMPLE_VND = 100_000
# Hoa hồng giả định admin chọn ở 🧮 Mô phỏng. Chỉ các mốc này, không nhận số tự do qua callback.
SIM_AMOUNTS = (10_000, 50_000, 100_000, 500_000)
# Nhập số tự do: một hoa hồng một đơn, từ 1đ tới 100 triệu. Chờ nhập giữ trong RAM, không ghi DB.
SIM_MAX_VND = 100_000_000
SIM_WAIT_TTL = timedelta(minutes=10)
_SEARCH_COMMAND = re.compile(r"^/tim(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_SIM_PLAIN = re.compile(r"^(\d{1,3}(?:[.,]\d{3})+|\d{1,9})\s*(?:đ|vnd|vnđ)?$")
_SIM_UNIT = re.compile(r"^(\d{1,6})(?:[.,](\d{1,3}))?\s*(k|nghìn|ngàn|tr|triệu)$")
_SIM_UNITS = {"k": 1_000, "nghìn": 1_000, "ngàn": 1_000, "tr": 1_000_000, "triệu": 1_000_000}
# Admin gõ phần trăm: "10", "0,98", "0.98", "62,5%". Lưu nội bộ bằng bps.
_NUMBER = re.compile(r"^(\d{1,3})(?:[.,](\d{1,2}))?\s*%?$")
_MENU = re.compile(r"^c:menu:(home|policy|rank|fee|sim|hist|copy|settings|orders|glossary)$")
_TIER = re.compile(r"^c:tier:(BRONZE|SILVER|GOLD)$")
_RESERVE = re.compile(r"^c:rs:(\d+):([0-9a-f]{8}):(k:[PIH]|keep|w:now|w:tmr|ok|no)$")
_SHARE = re.compile(r"^c:sh:(\d+):([0-9a-f]{8}):(w:now|w:tmr|ok|no)$")
_STATS = re.compile(r"^c:st:(today|7d|30d|all)(:more)?$")
_SIM = re.compile(r"^c:sim:(10000|50000|100000|500000|input)$")
_POLICY_CANCEL = re.compile(r"^c:pc:(s|r):(\d{1,9})(:ok)?$")
_CANCEL_KINDS = {"s": "share", "r": "reserve"}
_SHARE_NUMBER = re.compile(r"^(\d{1,3})\s*%?$")
_DECISION = re.compile(r"^c:(ok|no):(\d+):([0-9a-f]{8})$")
# Telegram tách tin dài hơn 4.096 ký tự. Gom các phần JSON cookie trong RAM, không ghi DB.
COOKIE_PART_TTL = timedelta(minutes=2)
MAX_COOKIE_CHARS = 64_000


class AdminSafetyError(RuntimeError):
    pass


def _stamp(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percent(bps: int) -> str:
    whole, frac = divmod(bps, 100)
    if frac == 0:
        return f"{whole}%"
    return f"{whole}.{frac:02d}".rstrip("0").replace(".", ",") + "%"


def customer_policy_due(rows: list[dict], now: datetime) -> dict | None:
    """Chỉ bản customer_effect=apply và đã tới ngày hiệu lực. Bản none không được chọn."""
    stamp = _stamp(now)
    chosen: dict | None = None
    for row in rows:
        if row.get("status") != "confirmed" or row.get("customer_effect") != "apply":
            continue
        effective = row.get("effective_at")
        if not effective or effective > stamp:
            continue
        if chosen is None or int(row["version"]) > int(chosen["version"]):
            chosen = row
    return chosen


def parse_sim_amount(text: str) -> int | None:
    """Hoa hồng giả định admin gõ: 150000, 150.000, 150k, 1,5tr. Số nguyên VND, không dùng float."""
    value = " ".join((text or "").lower().split())
    plain = _SIM_PLAIN.fullmatch(value)
    amount: int | None = None
    if plain:
        amount = int(re.sub(r"[.,]", "", plain.group(1)))
    unit = _SIM_UNIT.fullmatch(value) if amount is None else None
    if unit:
        whole, frac, name = unit.groups()
        scale = _SIM_UNITS[name]
        frac = frac or ""
        amount = int(whole) * scale + (int(frac) * scale) // (10 ** len(frac)) if frac else int(whole) * scale
    if amount is None or not 1 <= amount <= SIM_MAX_VND:
        return None
    return amount


def simulate_share(
    amount_vnd: int, policy: PolicyResolution, before_bps: int, after_bps: int
) -> tuple[tuple[int, int], tuple[int, int]]:
    """(hoàn, phần còn) trước và sau khi đổi tỷ lệ, cùng công thức báo giá đang chạy."""
    before = cashback_for(amount_vnd, replace(policy, share_bps=before_bps))
    after = cashback_for(amount_vnd, replace(policy, share_bps=after_bps))
    return (before.cashback_vnd, before.remainder_vnd), (after.cashback_vnd, after.remainder_vnd)


@dataclass(frozen=True)
class AdminPanel:
    db_path: str
    admin_user_ids: frozenset[int]
    displayed_rate_percent: int
    calculator_label: str = "V1.1, chưa bật V1.2"
    membership_on: bool = False
    fee_default_bps: int = 98
    tax_default_bps: int = 1_000
    # V1.2 khách đang nhận; None nghĩa là V1.1.
    estimate_policy: EstimatePolicy | None = None
    admin_notifier: AdminNotifier | None = None
    # Dự phòng khác và đơn vị làm tròn của V1.2 (.env). Dùng cả khi so sánh V1.2 lúc đang chạy V1.1.
    other_reserve_vnd: int = 0
    rounding_unit: int = 1
    # PLAN-079: cờ CUSTOMER_NOTIFICATIONS_ENABLED, để màn 🔔 nói đúng trạng thái.
    customer_notifications_enabled: bool = False
    customer_notification_test_ids: frozenset[int] = frozenset()
    # PLAN-080: cấu hình tự đồng bộ (.env), để màn ⏱ nói đúng và chỉ cho tạm dừng khi cờ đã bật.
    auto_sync: AutoSyncConfig = AutoSyncConfig()
    # PLAN-085: .env có khoá RioHub (RIOHUB_API_KEY + RIOHUB_CREATOR_USERNAME).
    tiktok_configured: bool = False
    _cookie_parts: dict[int, tuple[str, datetime]] = field(default_factory=dict, compare=False, repr=False)
    # Admin đang được hỏi hoa hồng giả định cho 🧮 Mô phỏng: user_id → hạn chờ.
    _sim_waiting: dict[int, datetime] = field(default_factory=dict, compare=False, repr=False)
    # Admin đang gõ lý do / câu trả lời cho ticket hỗ trợ (PLAN-077).
    _support_waiting: dict[int, tuple] = field(default_factory=dict, compare=False, repr=False)
    # Admin đang gõ lý do / chứng từ cho một bước của yêu cầu rút (PLAN-078).
    _wallet_waiting: dict[int, tuple] = field(default_factory=dict, compare=False, repr=False)
    # Admin đang gõ chi phí vận hành / tháng (PLAN-089) hoặc mục tiêu tháng (PLAN-090): user_id → (loại, hạn chờ).
    _insights_waiting: dict[int, tuple[str, datetime]] = field(default_factory=dict, compare=False, repr=False)
    # Admin đang gõ một mốc thời hạn lưu dữ liệu (C2): user_id → (mã mốc, hạn chờ).
    _retention_waiting: dict[int, tuple[str, datetime]] = field(default_factory=dict, compare=False, repr=False)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def menu(self, user_id: int, now: datetime) -> BotReply:
        if not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị.")
        self._clear_shopee_waiting(user_id)
        return self._screen("home", now)

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        if not self.is_admin(user_id):
            return None
        # /tim <mã>: tìm link, đơn, ticket, yêu cầu rút, khách (PLAN-091).
        if (search := _SEARCH_COMMAND.fullmatch(text or "")) is not None:
            return self._insights().search(user_id, search.group(1) or "", now)
        # Kiểm tra trạng thái chờ dán cookie Shopee
        try:
            with self._connect() as conn:
                waiting = conn.execute(
                    "SELECT value FROM bot_state WHERE key = ?",
                    (f"shopee_auth_waiting:{user_id}",),
                ).fetchone()
            if waiting and waiting[0] == "1":
                return self._consume_shopee_cookie(user_id, text, now, message_id=message_id)
        except sqlite3.Error:
            pass
        sim = self._sim_text(user_id, text, now)
        if sim is not None:
            return sim
        ticket = self._support().consume_text(user_id, text, now)
        if ticket is not None:
            return ticket
        payout = self._wallet_admin().consume_text(user_id, text, now)
        if payout is not None:
            return payout
        kept = self._retention().consume_text(user_id, text, now)
        if kept is not None:
            return kept
        cost = self._insights().consume_text(user_id, text, now)
        if cost is not None:
            return cost

        reserve = self._reserve_text(user_id, (text or "").strip(), now)
        if reserve is not None:
            return reserve
        share = self._share_text(user_id, (text or "").strip(), now)
        if share is not None:
            return share
        matched = _NUMBER.fullmatch((text or "").strip())
        if matched is None:
            return None
        try:
            draft = self._open_collecting(user_id, now)
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        if draft is None:
            return None
        bps = int(matched.group(1)) * 100 + int((matched.group(2) or "0").ljust(2, "0"))
        return self._preview_number(draft, bps, now)

    def handle_callback(self, user_id: int, data: str, chat_type: str, now: datetime) -> BotReply:
        if chat_type != "private" or not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị trong cuộc trò chuyện riêng.")
        if data != "c:shopee:auth":
            # Bấm bất kỳ nút nào khác (kể cả ✖️ Hủy) là thôi chờ cookie.
            self._clear_shopee_waiting(user_id)
        if data != "c:sim:input":
            self._sim_waiting.pop(user_id, None)
        if not data.startswith("c:hp:"):
            self._support_waiting.pop(user_id, None)
        if not (data.startswith("c:wl:mv:") or data.startswith("c:wl:vb:")):
            self._wallet_waiting.pop(user_id, None)
        # Màn khác (kể cả ◀️ Tổng quan, ✖️ Hủy) là thôi chờ gõ: tin kế tiếp không bị hiểu nhầm là từ khoá / số.
        if data not in ("c:in:cost", "c:in:f") and not data.startswith("c:in:t:"):
            self._insights_waiting.pop(user_id, None)
        if not data.startswith("c:rt:e:"):
            self._retention_waiting.pop(user_id, None)
        reply = self._route_callback(user_id, data, now)
        if reply.inline_keyboard is None:
            # Callback sửa đè tin cũ. Thiếu nút thì admin kẹt ở màn chỉ có chữ.
            return replace(reply, inline_keyboard=NAV_KEYBOARD)
        return reply

    def _route_callback(self, user_id: int, data: str, now: datetime) -> BotReply:
        menu = _MENU.fullmatch(data or "")
        if menu:
            return self._screen(menu.group(1), now)
        tier = _TIER.fullmatch(data or "")
        if tier:
            return self._begin(user_id, tier.group(1), now)
        sim = _SIM.fullmatch(data or "")
        if sim and sim.group(1) == "input":
            self._sim_waiting[user_id] = now + SIM_WAIT_TTL
            return BotReply(simulation_prompt_text(), inline_keyboard=SIM_PROMPT_KEYBOARD)
        if sim:
            return self._simulation(now, int(sim.group(1)))
        cancel = _POLICY_CANCEL.fullmatch(data or "")
        if cancel:
            kind = _CANCEL_KINDS[cancel.group(1)]
            return self._policy_cancel(user_id, kind, int(cancel.group(2)), bool(cancel.group(3)), now)
        stats = _STATS.fullmatch(data or "")
        if stats:
            return self._stats(stats.group(1), now, detail=bool(stats.group(2)))
        if data.startswith("c:pb:"):
            return self._showcase(data, now)
        if data == "c:rs:new":
            return self._reserve_start(user_id, now)
        if data == "c:sh:new":
            return self._share_start(user_id, now)
        if data == "c:menu:wallet" or data.startswith("c:wl:"):
            return self._wallet_admin().route(user_id, data, now)
        if data.startswith("c:in:"):
            return self._insights().route(user_id, data, now)
        if data.startswith("c:rt:"):
            return self._retention().route(user_id, data, now)
        if data.startswith("c:an:"):
            return AnnounceAdmin(TrackingRepository(self.db_path), audit=self._log_setting).route(user_id, data, now)
        if data.startswith("c:dl:"):
            return DealsAdmin(TrackingRepository(self.db_path), audit=self._log_setting).route(user_id, data, now)
        if data.startswith("c:eg:"):
            return EngagementAdmin(TrackingRepository(self.db_path), audit=self._log_setting).route(user_id, data, now)
        if data.startswith("c:tk:"):
            return TikTokAdmin(TrackingRepository(self.db_path), self.tiktok_configured, audit=self._log_setting).route(
                user_id, data, now)
        if data.startswith("c:cv:"):
            return ValidationAdmin(TrackingRepository(self.db_path), audit=self._log_setting).route(user_id, data, now)
        if data.startswith("c:sm:"):
            return SettlementAdmin(TrackingRepository(self.db_path)).route(user_id, data, now)
        if data.startswith("c:hp:"):
            return self._support().route(user_id, data, now)
        if data.startswith("c:tm:"):
            return TermsAdmin(TrackingRepository(self.db_path), audit=self._log_setting).route(user_id, data, now)
        if data.startswith("c:nt:"):
            return CustomerNotifyAdmin(
                TrackingRepository(self.db_path), self.customer_notifications_enabled, audit=self._log_setting,
                test_ids=self.customer_notification_test_ids,
            ).route(user_id, data, now)
        if data.startswith("c:rd:"):
            return ReadinessAdmin(TrackingRepository(self.db_path)).route(user_id, data, now)
        if data.startswith("c:rc:"):
            return ReconciliationAdmin(TrackingRepository(self.db_path), self.auto_sync.reconcile_lookup).route(data)
        if data.startswith("c:sy:"):
            return AutoSyncAdmin(TrackingRepository(self.db_path), self.auto_sync).route(data, now)
        if data == "c:menu:shopee":
            return self._shopee_screen(now)
        if data == "c:shopee:sync":
            return self._shopee_sync(now)
        if data == "c:shopee:csv":
            return self._shopee_csv(now)
        if data in {"c:shopee:auto:on", "c:shopee:auto:off"}:
            return self._shopee_auto(user_id, data.endswith(":on"), now)
        if data == "c:shopee:auth":
            return self._shopee_auth_start(user_id, now)
        share = _SHARE.fullmatch(data or "")
        if share:
            return self._share_action(user_id, int(share.group(1)), share.group(2), share.group(3), now)
        reserve = _RESERVE.fullmatch(data or "")
        if reserve:
            return self._reserve_action(user_id, int(reserve.group(1)), reserve.group(2), reserve.group(3), now)
        decision = _DECISION.fullmatch(data or "")
        if decision is None:
            return BotReply("Nút này không còn hiệu lực.")
        action, draft_id, nonce = decision.group(1), int(decision.group(2)), decision.group(3)
        if action == "no":
            return self._cancel(user_id, draft_id, nonce, now)
        return self._confirm(user_id, draft_id, nonce, now)

    def _screen(self, name: str, now: datetime, notice: str = "") -> BotReply:
        if name == "home":
            todo, today = self._todo(now)
            text = home_text(
                rate_percent=self._rate_percent(now),
                calculator=self.calculator_label,
                pending=self._pending_count(now),
                todo=todo,
                today=today,
                wallet_on=self._wallet_on(),
            )
            return BotReply(text, inline_keyboard=MENU_KEYBOARD)
        if name == "settings":
            text = settings_text(rate_percent=self._rate_percent(now), membership_on=self.membership_on,
                                 calculator=self.calculator_label, pending=self._pending_count(now))
            return BotReply(text, inline_keyboard=SETTINGS_MENU_KEYBOARD)
        if name == "orders":
            return BotReply(self._orders_text(), inline_keyboard=ORDERS_MENU_KEYBOARD)
        if name == "glossary":
            return BotReply(GLOSSARY, inline_keyboard=((("◀️ Cài đặt", "c:menu:settings"),), BACK_HOME))
        if name == "policy":
            live = self.resolve_policy(now)
            with self._connect() as conn:
                share = active_share(conn, now, self.displayed_rate_percent * 100)
                upcoming = upcoming_shares(conn, now)
            v12 = live.pricing_version == "v1.2"
            result = cashback_for(SAMPLE_VND, live)
            warning = ""
            if not v12 and (share.policy_id is not None or upcoming):
                warning = "Đang chạy V1.1: tỷ lệ admin đặt có tác dụng khi bật V1.2."
            text = policy_text(
                rate_percent=live.rate_percent,
                pending=self._pending_count(now),
                customer_vnd=result.cashback_vnd,
                remain_vnd=result.remainder_vnd,
                reserve=(
                    _percent(live.fee_bps),
                    _percent(live.tax_reserve_bps),
                    result.fee_reserve_vnd,
                    result.tax_reserve_vnd,
                ),
                v12=v12,
                since=vn_time(share.effective_at) if share.effective_at and v12 else None,
                upcoming=[f"{_percent(item.share_bps)} từ {vn_time(item.effective_at or '')}" for item in upcoming],
                warning=warning,
                notice=notice,
            )
            buttons = [
                (f"🗑 Huỷ lịch #{item.policy_id}: {_percent(item.share_bps)} từ {vn_time(item.effective_at or '')}",
                 f"c:pc:s:{item.policy_id}")
                for item in upcoming
            ]
            return BotReply(text, inline_keyboard=with_rows(POLICY_KEYBOARD, buttons))
        if name == "rank":
            rates = self._safe_rates()
            live = self.resolve_policy(now)
            tiers = [
                (TIER_EMOJI[code], label, _percent(rates[code]), *_split(cashback_for(SAMPLE_VND, replace(live, share_bps=rates[code]))))
                for code, label in TIERS.items()
            ]
            text = rank_text(tiers=tiers, notice=notice)
            return BotReply(text, inline_keyboard=RANK_KEYBOARD)
        if name == "fee":
            live = self.resolve_policy(now)
            with self._connect() as conn:
                active = active_reserve(conn, now, self.fee_default_bps, self.tax_default_bps)
                upcoming = upcoming_reserves(conn, now)
            result = cashback_for(SAMPLE_VND, live)
            text = fee_text(
                calculator_on=live.pricing_version == "v1.2",
                kind=_kind_label(active),
                fee=_percent(active.fee_bps),
                tax=_percent(active.tax_reserve_bps),
                since=vn_time(active.effective_at) if active.effective_at else None,
                upcoming=[_upcoming_line(item) for item in upcoming],
                rate_percent=live.rate_percent,
                sim_fee=result.fee_reserve_vnd,
                sim_tax=result.tax_reserve_vnd,
                sim_dist=result.distributable_vnd,
                sim_customer=result.cashback_vnd,
                notice=notice,
            )
            buttons = [
                (f"🗑 Huỷ lịch #{item.policy_id}: phí {_percent(item.fee_bps)}, thuế {_percent(item.tax_reserve_bps)}",
                 f"c:pc:r:{item.policy_id}")
                for item in upcoming
            ]
            return BotReply(text, inline_keyboard=with_rows(FEE_KEYBOARD, buttons))
        if name == "sim":
            return self._simulation(now, SAMPLE_VND)
        if name == "hist":
            return BotReply(
                history_text(self._history_rows(), self._policy_versions(now)),
                inline_keyboard=NAV_KEYBOARD,
            )
        if name == "shopee":
            return self._shopee_screen(now, notice)
        return BotReply(command_copy_text(), inline_keyboard=NAV_KEYBOARD)

    def _shopee_screen(self, now: datetime, notice: str = "") -> BotReply:
        with self._connect() as conn:
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

        auto_sync = status_label(TrackingRepository(self.db_path), self.auto_sync, now)
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
        )
        return BotReply(text, inline_keyboard=kb)

    def _shopee_auto(self, user_id: int, resume: bool, now: datetime) -> BotReply:
        """Tạm dừng / tiếp tục tự đồng bộ. Không bật được khi cờ .env tắt (không có đường vượt cờ qua Telegram)."""
        repo = TrackingRepository(self.db_path)
        if not self.auto_sync.enabled:
            return AutoSyncAdmin(repo, self.auto_sync).home(
                now, "ⓘ Tự đồng bộ đang tắt trong cấu hình. Chủ bot bật bằng SHOPEE_AUTO_SYNC_ENABLED trong .env."
            )
        changed = SyncCoordinator(repo, cfg=self.auto_sync, clock=lambda: now).set_paused(user_id, not resume)
        if changed:
            self._log_setting(user_id, "shopee_auto_sync_pause", {"paused": resume}, {"paused": not resume}, now)
        notice = "▶️ Đã tiếp tục tự đồng bộ (lượt tới sau 5 phút)." if resume else "⏸️ Đã tạm dừng tự đồng bộ. 🔄 thủ công vẫn dùng được."
        return AutoSyncAdmin(repo, self.auto_sync).home(now, notice)

    def _shopee_sync(self, now: datetime) -> BotReply:
        # Không gọi Shopee trong lúc trả lời nút: xếp lượt, luồng nền chạy rồi nhắn kết quả (PLAN-080).
        current = request_manual(TrackingRepository(self.db_path), now)
        if current is not None:
            run_id, trigger = current
            label = "tự động" if trigger == "auto" else "thủ công"
            return self._shopee_screen(now, notice=(
                f"🔄 Shopee đang được đồng bộ {label}. Mã lượt: #{run_id}. "
                "Bạn có thể xem tiến độ tại màn ⏱ Tự động đồng bộ."
            ))
        return self._shopee_screen(now, notice="⏳ Đã bắt đầu đồng bộ. Xong bot sẽ nhắn kết quả.")

    def _shopee_csv(self, now: datetime) -> BotReply:
        since = now - timedelta(days=30)
        with self._connect() as conn:
            data, count = conversions_csv(conn, since)
        name = f"shopee-don-30-ngay-{now.astimezone(ICT).strftime('%Y%m%d')}.csv"
        reply = self._shopee_screen(now, notice=f"📤 Đã gửi file {count} dòng đơn 30 ngày.")
        return replace(reply, document=(name, data))

    def _clear_shopee_waiting(self, user_id: int) -> None:
        self._cookie_parts.pop(user_id, None)
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM bot_state WHERE key = ?", (f"shopee_auth_waiting:{user_id}",))
        except sqlite3.Error:
            pass

    def _shopee_auth_start(self, user_id: int, now: datetime) -> BotReply:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES (?, '1')
                ON CONFLICT(key) DO UPDATE SET value = '1'
                """,
                (f"shopee_auth_waiting:{user_id}",),
            )
        return BotReply(shopee_prompt_cookie_text(), inline_keyboard=SHOPEE_PROMPT_KEYBOARD)

    def _consume_shopee_cookie(
        self,
        user_id: int,
        text: str,
        now: datetime,
        message_id: int | None = None,
    ) -> BotReply:
        pending = self._cookie_parts.pop(user_id, None)
        if pending and now - pending[1] <= COOKIE_PART_TTL:
            text = pending[0] + text
        try:
            cookies = parse_cookies(text)
        except IncompleteCookieError:
            if len(text) > MAX_COOKIE_CHARS:
                self._clear_shopee_waiting(user_id)
                return BotReply(
                    "❌ <b>Cookie quá dài.</b> Hãy dán chuỗi <code>name=value;</code> thay vì JSON.",
                    inline_keyboard=SHOPEE_PROMPT_KEYBOARD,
                    delete_message_id=message_id,
                )
            # Vẫn chờ: phần tiếp theo cũng đi vào đây và cũng bị xoá khỏi chat.
            self._cookie_parts[user_id] = (text, now)
            return BotReply(
                "📥 Đã nhận một phần cookie, đang chờ phần còn lại…",
                inline_keyboard=SHOPEE_PROMPT_KEYBOARD,
                delete_message_id=message_id,
            )
        except ValueError as exc:
            self._clear_shopee_waiting(user_id)
            return BotReply(
                f"❌ <b>Không tìm thấy cookie hợp lệ:</b> {html.escape(str(exc))}.\n\nBấm 🔑 để dán lại.",
                inline_keyboard=SHOPEE_KEYBOARD_DISCONNECTED,
                delete_message_id=message_id,
            )

        self._clear_shopee_waiting(user_id)
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
        self._log_setting(user_id, "shopee_cookie", None, {"account": status_res.username or "Shopee Affiliate"}, now)
        with self._connect() as conn:
            now_str = _stamp(now)
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

    def _begin(self, user_id: int, code: str, now: datetime) -> BotReply:
        domain, tier, prompt = _draft_target(code)
        try:
            base = self._latest_version(domain)
            nonce = secrets.token_hex(4)
            expires = _stamp(now + CONFIRM_TTL)
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO admin_drafts (
                        admin_user_id, domain, tier, proposed_bps, base_version,
                        status, nonce, expires_at, created_at
                    ) VALUES (?, ?, ?, NULL, ?, 'collecting', ?, ?, ?)
                    """,
                    (user_id, domain, tier, base, nonce, expires, _stamp(now)),
                )
                draft_id = int(cursor.lastrowid)
                self._audit(conn, user_id, "draft", draft_id, None, None, "collecting", now)
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        current = _percent(self._safe_rates()[code])
        return BotReply(
            collecting_text(draft_id=draft_id, current=current, **prompt),
            inline_keyboard=collecting_keyboard(draft_id, nonce),
        )

    def _preview_number(self, draft: sqlite3.Row, bps: int, now: datetime) -> BotReply:
        parsed = _parse_bps(draft["domain"], bps)
        retry = collecting_keyboard(int(draft["id"]), draft["nonce"])
        if parsed is None:
            return BotReply(
                "Giá trị không nằm trong giới hạn. Hạng từ 0 đến 70%. Gửi lại số khác.",
                inline_keyboard=retry,
            )
        rates = self._rates()
        rates[draft["tier"]] = parsed
        ordered = [rates["BRONZE"], rates["SILVER"], rates["GOLD"]]
        if ordered != sorted(ordered):
            return BotReply("Tỷ lệ phải đi theo thứ tự Đồng ≤ Bạc ≤ Vàng. Gửi lại số khác.", inline_keyboard=retry)
        before = self._rates()[draft["tier"]]
        before_split, after_split = simulate_share(SAMPLE_VND, self.resolve_policy(now), before, parsed)
        body = rank_preview_text(
            tier_name=TIERS[draft["tier"]],
            before=_percent(before),
            after=_percent(parsed),
            before_split=before_split,
            after_split=after_split,
        )
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE admin_drafts
                SET status = 'preview', proposed_bps = ?
                WHERE id = ? AND status = 'collecting' AND expires_at > ?
                """,
                (parsed, draft["id"], _stamp(now)),
            )
            if updated.rowcount != 1:
                return BotReply("Bản nháp đã hết hạn hoặc đã được xử lý.")
            self._audit(conn, int(draft["admin_user_id"]), "preview", int(draft["id"]), None, body, "preview", now)
        return BotReply(body, inline_keyboard=decision_keyboard(int(draft["id"]), draft["nonce"]))

    def _cancel(self, user_id: int, draft_id: int, nonce: str, now: datetime) -> BotReply:
        try:
            with self._connect() as conn:
                updated = conn.execute(
                    """
                    UPDATE admin_drafts
                    SET status = 'cancelled'
                    WHERE id = ? AND admin_user_id = ? AND nonce = ?
                      AND status IN ('collecting', 'preview')
                    """,
                    (draft_id, user_id, nonce),
                )
                if updated.rowcount != 1:
                    return BotReply("Không hủy được. Bản này đã xử lý hoặc không phải của bạn.")
                self._audit(conn, user_id, "cancel", draft_id, None, None, "cancelled", now)
                domain = conn.execute("SELECT domain FROM admin_drafts WHERE id = ?", (draft_id,)).fetchone()[0]
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        notice = f"✖️ Đã hủy bản nháp #{draft_id}. Chính sách đã lưu không đổi."
        return replace(self._screen(_screen_of(domain), now, notice), toast="Đã hủy bản nháp")

    def _confirm(self, user_id: int, draft_id: int, nonce: str, now: datetime) -> BotReply:
        domain = ""
        try:
            with self._connect() as conn:
                draft = conn.execute("SELECT * FROM admin_drafts WHERE id = ?", (draft_id,)).fetchone()
                if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                    return BotReply("Nút xác nhận không hợp lệ.")
                domain = str(draft["domain"])
                if draft["status"] != "preview" or draft["proposed_bps"] is None:
                    return BotReply("Bản này đã được xử lý.")
                if draft["expires_at"] <= _stamp(now):
                    conn.execute(
                        "UPDATE admin_drafts SET status = 'expired' WHERE id = ? AND status = 'preview'",
                        (draft_id,),
                    )
                    self._audit(conn, user_id, "confirm", draft_id, None, None, "expired", now)
                    return BotReply("Bản nháp đã hết hạn. Chưa lưu chính sách.")
                latest = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM policy_versions WHERE domain = ?",
                    (domain,),
                ).fetchone()[0]
                if int(latest) != int(draft["base_version"]):
                    return BotReply("Đã có phiên bản mới hơn. Hãy tạo lại bản nháp.")
                claimed = conn.execute(
                    """
                    UPDATE admin_drafts
                    SET status = 'confirmed'
                    WHERE id = ? AND status = 'preview' AND nonce = ?
                    """,
                    (draft_id, nonce),
                )
                if claimed.rowcount != 1:
                    return BotReply("Bản này đã được xử lý.")
                config = self._config_for(conn, draft)
                version = int(latest) + 1
                before = json.dumps(self._stored_rates(conn), ensure_ascii=False, sort_keys=True)
                conn.execute(
                    """
                    INSERT INTO policy_versions (
                        domain, version, status, config_json, effective_at,
                        customer_effect, created_by, created_at
                    ) VALUES (?, ?, 'confirmed', ?, ?, 'none', ?, ?)
                    """,
                    (domain, version, json.dumps(config, sort_keys=True), _stamp(now), user_id, _stamp(now)),
                )
                self._audit(
                    conn,
                    user_id,
                    "confirm",
                    draft_id,
                    before,
                    json.dumps(config, sort_keys=True),
                    "confirmed",
                    now,
                )
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        except sqlite3.IntegrityError:
            return BotReply("Đã có phiên bản mới hơn. Hãy tạo lại bản nháp.")
        logger.info("[Cashback] admin policy confirmed domain=%s", domain)
        notice = (
            f"✅ Đã lưu phiên bản v{version}. Chưa kích hoạt, khách vẫn nhận báo giá hiện hành. "
            "Báo giá đã lưu không tự tính lại. Chưa chi trả."
        )
        return replace(self._screen(_screen_of(domain), now, notice), toast=f"Đã lưu phiên bản v{version}")

    def _config_for(self, conn: sqlite3.Connection, draft: sqlite3.Row) -> dict:
        if draft["domain"] == "membership_rates":
            rates = self._stored_rates(conn)
            rates[draft["tier"]] = int(draft["proposed_bps"])
            return {
                "label": "ESTIMATE_RESERVE",
                "bronze_bps": rates["BRONZE"],
                "silver_bps": rates["SILVER"],
                "gold_bps": rates["GOLD"],
                "max_share_bps": MAX_SHARE_BPS,
                "customer_effect": "none",
            }
        return {
            "label": "ESTIMATE_RESERVE",
            "domain": draft["domain"],
            "bps": int(draft["proposed_bps"]),
            "not_statutory_tax": True,
            "customer_effect": "none",
        }

    def _share_start(self, user_id: int, now: datetime) -> BotReply:
        with self._connect() as conn:
            _cancel_open_wizards(conn, user_id)
            cursor = conn.execute(
                """
                INSERT INTO share_drafts (admin_user_id, step, nonce, expires_at, created_at)
                VALUES (?, 'share', ?, ?, ?)
                """,
                (user_id, secrets.token_hex(4), _stamp(now + CONFIRM_TTL), _stamp(now)),
            )
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._share_prompt(draft, now)

    def _share_action(self, user_id: int, draft_id: int, nonce: str, action: str, now: datetime) -> BotReply:
        applied_id: int | None = None
        with self._connect() as conn:
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                return BotReply("Nút này không hợp lệ.")
            if draft["step"] not in SHARE_OPEN_STEPS:
                return BotReply("Bản này đã được xử lý. Bấm Đổi tỷ lệ chia để làm lại.")
            if draft["expires_at"] <= _stamp(now):
                conn.execute("UPDATE share_drafts SET step = 'expired' WHERE id = ?", (draft_id,))
                return BotReply("Bản nháp đã hết hạn sau 10 phút. Tỷ lệ đang áp dụng không đổi.")
            step = draft["step"]
            changes: dict | None = None
            if action == "no":
                changes = {"step": "cancelled"}
            elif action == "w:now" and step == "when":
                changes = {"step": "preview", "effective_at": None}
            elif action == "w:tmr" and step == "when":
                changes = {"step": "preview", "effective_at": _stamp(next_midnight(now))}
            elif action == "ok" and step == "preview":
                active = active_share(conn, now, self.displayed_rate_percent * 100)
                effective = effective_from(draft["effective_at"], now)
                cursor = conn.execute(
                    """
                    INSERT INTO share_policies (share_bps, effective_at, draft_id, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (draft["share_bps"], effective, draft_id, user_id, _stamp(now)),
                )
                applied_id = int(cursor.lastrowid)
                after = {"id": applied_id, "share_bps": int(draft["share_bps"]), "effective_at": effective}
                before = {"id": active.policy_id, "share_bps": active.share_bps}
                self._audit(
                    conn, user_id, "share_apply", None,
                    json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), "applied", now,
                )
                changes = {"step": "applied"}
            if changes is not None:
                changes.setdefault("expires_at", _stamp(now + CONFIRM_TTL))
                _update_draft(conn, draft_id, changes, table="share_drafts")
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft_id,)).fetchone()
        if draft["step"] == "cancelled":
            return replace(self._screen("policy", now, "✖️ Đã hủy. Tỷ lệ đang áp dụng không đổi."), toast="Đã hủy")
        if applied_id is not None:
            # Mốc đã qua lúc bấm Áp dụng thì effective_from ghi giờ bấm, không hồi tố.
            scheduled = draft["effective_at"] and draft["effective_at"] > _stamp(now)
            when = vn_time(draft["effective_at"]) if scheduled else "ngay bây giờ"
            notice = (
                f"✅ Đã áp dụng tỷ lệ chia {_percent(int(draft['share_bps']))} (#{applied_id}) cho link mới, "
                f"hiệu lực {when}. Link đã gửi giữ số cũ."
            )
            return replace(self._screen("policy", now, notice), toast=f"Đã áp dụng tỷ lệ #{applied_id}")
        return self._share_prompt(draft, now)

    def _share_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not text or "shopee" in text.lower() or text.lower().startswith("http") or text.startswith("/"):
            return None
        with self._connect() as conn:
            draft = conn.execute(
                """
                SELECT * FROM share_drafts
                WHERE admin_user_id = ? AND step IN ('share', 'when') AND expires_at > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, _stamp(now)),
            ).fetchone()
            if draft is None:
                return None
            error = ""
            changes: dict | None = None
            if draft["step"] == "share":
                matched = _SHARE_NUMBER.fullmatch(text)
                if matched is None:
                    error = "Gửi một số nguyên, ví dụ 65."
                elif int(matched.group(1)) * 100 > MAX_SHARE_BPS:
                    error = "Tỷ lệ chia tối đa 70%."
                else:
                    changes = {"step": "when", "share_bps": int(matched.group(1)) * 100}
            else:
                moment, error = parse_when(text, now)
                if moment is None and not error:
                    error = "Chưa đọc được ngày. Gửi dạng 01/11 hoặc 01/11 08:00."
                if moment is not None:
                    changes = {"step": "preview", "effective_at": _stamp(moment)}
            if changes is not None:
                changes["expires_at"] = _stamp(now + CONFIRM_TTL)
                _update_draft(conn, int(draft["id"]), changes, table="share_drafts")
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft["id"],)).fetchone()
        return self._share_prompt(draft, now, error or "")

    def _share_prompt(self, draft: sqlite3.Row, now: datetime, error: str = "") -> BotReply:
        draft_id, nonce, step = int(draft["id"]), draft["nonce"], draft["step"]
        active = self.active_share(now)
        if step == "share":
            return BotReply(
                share_value_text(current=_percent(active.share_bps), error=error),
                inline_keyboard=share_cancel_keyboard(draft_id, nonce),
            )
        if step == "when":
            return BotReply(
                share_when_text(share=_percent(int(draft["share_bps"])), error=error),
                inline_keyboard=reserve_when_keyboard(draft_id, nonce, "sh"),
            )
        new_bps = int(draft["share_bps"])
        sample = recent = None
        if self.estimate_policy is not None:
            before = self.resolve_policy(now)
            after = replace(before, share_bps=new_bps)
            old, new = cashback_for(SAMPLE_VND, before), cashback_for(SAMPLE_VND, after)
            sample = (old.cashback_vnd, new.cashback_vnd, old.remainder_vnd, new.remainder_vnd)
            recent = self._recent_totals(before, after)
        text = share_preview_text(
            calculator_on=self.estimate_policy is not None,
            share=(_percent(active.share_bps), _percent(new_bps)),
            when=vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay khi bấm Áp dụng",
            sample=sample,
            recent=recent,
        )
        return BotReply(text, inline_keyboard=reserve_decision_keyboard(draft_id, nonce, "sh"))

    def _stats(self, period: str, now: datetime, detail: bool = False) -> BotReply:
        try:
            with self._connect() as conn:
                stats = collect(conn, period, now)
        except sqlite3.OperationalError:
            logger.exception("[Cashback] thống kê lỗi")
            return BotReply("Chưa đọc được dữ liệu thống kê trên database này.", inline_keyboard=stats_keyboard(period))
        since = stats.since.astimezone(ICT).strftime("00:00 %d/%m/%Y") if stats.since else None
        render = stats_detail_text if detail else stats_text
        text = render(stats, period_label=PERIODS[period][0], since=since)
        return BotReply(text, inline_keyboard=stats_keyboard(period, detail))

    def _showcase(self, data: str, now: datetime) -> BotReply:
        """🖼 Ảnh đăng bài: chỉnh mục hiển thị rồi tạo ảnh số liệu thật (showcase.py)."""
        try:
            return showcase.ShowcaseAdmin(TrackingRepository(self.db_path)).route(data, now)
        except sqlite3.OperationalError:
            logger.exception("[Cashback] ảnh đăng bài lỗi")
            return BotReply("Chưa đọc được dữ liệu trên database này.", inline_keyboard=showcase.NAV)

    def _history_rows(self) -> list[str] | None:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT a.action, a.result, a.created_at, a.before_json, a.after_json, d.domain, d.tier, d.proposed_bps
                    FROM admin_change_audit a
                    LEFT JOIN admin_drafts d ON d.id = a.draft_id
                    ORDER BY a.id DESC
                    LIMIT 8
                    """
                ).fetchall()
        except AdminSafetyError:
            return None
        return [_history_line(row) for row in rows]

    def _safe_rates(self) -> dict[str, int]:
        try:
            return self._rates()
        except AdminSafetyError:
            return dict(DIRECTIONAL_BPS)

    def active_reserve(self, now: datetime) -> AppliedReserve:
        """Mức dự phòng khách đang nhận (ADR-047). Chưa áp dụng lần nào thì là mặc định cấu hình."""
        with self._connect() as conn:
            return active_reserve(conn, now, self.fee_default_bps, self.tax_default_bps)

    def active_share(self, now: datetime) -> AppliedShare:
        """Tỷ lệ chia khách đang nhận (ADR-048). Chưa áp dụng lần nào thì là CASHBACK_RATE_PERCENT."""
        with self._connect() as conn:
            return active_share(conn, now, self.displayed_rate_percent * 100)

    def resolve_policy(self, now: datetime, v12: bool | None = None) -> PolicyResolution:
        """Chính sách báo giá link mới lúc `now` (PLAN-076). Màn admin, báo giá và snapshot dùng chung."""
        on = self.estimate_policy is not None if v12 is None else v12
        with self._connect() as conn:
            return resolve_policy(
                conn,
                now,
                v12=on,
                default_share_bps=self.displayed_rate_percent * 100,
                fee_default=self.fee_default_bps,
                tax_default=self.tax_default_bps,
                other_reserve_vnd=self.other_reserve_vnd,
                rounding_unit=self.rounding_unit,
            )

    def _rate_percent(self, now: datetime) -> int:
        return self.resolve_policy(now).rate_percent

    def _recent_totals(self, before: PolicyResolution, after: PolicyResolution) -> tuple[int, int, int] | None:
        """Tổng tiền hoàn trên hoa hồng ước tính của các link gần nhất, trước và sau thay đổi."""
        with self._connect() as conn:
            commissions = recent_commissions(conn)
        if not commissions:
            return None
        return (
            len(commissions),
            sum(cashback_for(c, before).cashback_vnd for c in commissions),
            sum(cashback_for(c, after).cashback_vnd for c in commissions),
        )

    def _simulation(self, now: datetime, amount: int) -> BotReply:
        """🧮 Mô phỏng: chỉ đọc. Cùng cashback_for với báo giá khách; không ghi gì, không bật gì."""
        live = self.resolve_policy(now)
        v12 = live.pricing_version == "v1.2"
        # Cột so sánh dùng cùng tỷ lệ và dự phòng, chỉ đổi công thức. Không bật công thức nào.
        if v12:
            other = replace(live, pricing_version="v1.1", other_reserve_vnd=0, rounding_unit=1)
        else:
            other = replace(live, pricing_version="v1.2", other_reserve_vnd=self.other_reserve_vnd, rounding_unit=self.rounding_unit)
        current, compare = cashback_for(amount, live), cashback_for(amount, other)
        scheduled = []
        with self._connect() as conn:
            moments = sorted(
                {item.effective_at for item in upcoming_shares(conn, now) if v12 and item.effective_at}
                | {item.effective_at for item in upcoming_reserves(conn, now) if item.effective_at}
            )[:3]
        for moment in moments:
            at = datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            future = self.resolve_policy(at)
            result = cashback_for(amount, future)
            scheduled.append(
                f"Từ {vn_time(moment)}: chia {_percent(future.share_bps)}, phí {_percent(future.fee_bps)}, "
                f"thuế {_percent(future.tax_reserve_bps)} → khách {format_vnd(result.cashback_vnd)}"
            )
        rates = self._safe_rates()
        ranks = [
            (label, _percent(rates[code]), *_split(cashback_for(amount, replace(live, share_bps=rates[code]))))
            for code, label in TIERS.items()
        ]
        text = simulation_text(
            quote=quote_label(live.rate_percent, v12),
            amount=amount,
            settings=(_percent(live.share_bps), _percent(live.fee_bps), _percent(live.tax_reserve_bps)),
            columns=(("V1.2" if v12 else "V1.1", current), ("V1.1" if v12 else "V1.2", compare)),
            scheduled=scheduled,
            ranks=ranks,
        )
        return BotReply(text, inline_keyboard=simulation_keyboard(SIM_AMOUNTS, amount))

    def _wallet_admin(self) -> WalletAdmin:
        return WalletAdmin(TrackingRepository(self.db_path), audit=self._log_setting, waiting=self._wallet_waiting)

    def _insights(self) -> InsightsAdmin:
        repo = TrackingRepository(self.db_path)
        return InsightsAdmin(
            self.db_path, audit=self._log_setting, waiting=self._insights_waiting,
            sync_interval_minutes=self.auto_sync.interval_minutes,
            locked_reasons=lambda: Wallet(repo).settings().locked_reasons,
        )

    def _retention(self) -> RetentionAdmin:
        return RetentionAdmin(TrackingRepository(self.db_path), audit=self._log_setting, waiting=self._retention_waiting)

    def _support(self) -> SupportAdmin:
        return SupportAdmin(TrackingRepository(self.db_path), self._support_waiting)

    def _sim_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        """Admin gõ hoa hồng giả định sau khi bấm ✏️ Nhập số khác. None: không chờ, để luồng khác xử lý."""
        deadline = self._sim_waiting.get(user_id)
        if deadline is None:
            return None
        stripped = (text or "").strip()
        lowered = stripped.lower()
        if deadline <= now or not stripped or stripped.startswith("/") or "shopee" in lowered or lowered.startswith("http"):
            self._sim_waiting.pop(user_id, None)
            return None
        amount = parse_sim_amount(stripped)
        if amount is None:
            error = f"Chưa đọc được số. Gửi số tiền từ 1đ tới {format_vnd(SIM_MAX_VND)}, ví dụ 150000, 150.000 hoặc 150k."
            return BotReply(simulation_prompt_text(error=error), inline_keyboard=SIM_PROMPT_KEYBOARD)
        self._sim_waiting.pop(user_id, None)
        return self._simulation(now, amount)

    def _policy_cancel(self, user_id: int, kind: str, policy_id: int, confirm: bool, now: datetime) -> BotReply:
        """Huỷ chính sách đã hẹn giờ, chỉ trước mốc hiệu lực. Bước 1 hỏi lại, bước 2 ghi dòng huỷ + audit."""
        back = "policy" if kind == "share" else "fee"
        code = "s" if kind == "share" else "r"
        with self._connect() as conn:
            if confirm:
                conn.execute("BEGIN IMMEDIATE")
                row, result = cancel_scheduled(conn, kind, policy_id, user_id, now)
                if result == "ok":
                    before = {key: row[key] for key in row.keys() if key in {"id", "share_bps", "fee_bps", "tax_reserve_bps", "account_kind", "effective_at"}}
                    self._audit(conn, user_id, f"{kind}_cancel", None, json.dumps(before, sort_keys=True), None, "cancelled", now)
            else:
                row = conn.execute(f"SELECT * FROM {POLICY_TABLES[kind]} WHERE id = ?", (policy_id,)).fetchone()
                result = "preview"
                if row is not None and policy_id in cancelled_ids(conn, kind):
                    result = "cancelled_before"
                elif row is not None and str(row["effective_at"]) <= _stamp(now):
                    result = "already_effective"
        if row is None or result == "not_found":
            return replace(self._screen(back, now, "Không thấy lịch hẹn này."), toast="Không thấy lịch hẹn")
        subject = _policy_subject(kind, row)
        if result == "cancelled_before":
            return replace(self._screen(back, now, f"Lịch #{policy_id} đã được huỷ trước đó."), toast="Đã huỷ trước đó")
        if result == "already_effective":
            notice = (
                f"⚠️ #{policy_id} ({subject}) đã tới giờ hiệu lực, không huỷ được vì có thể đã áp cho link. "
                "Muốn đổi thì áp dụng mức mới."
            )
            return replace(self._screen(back, now, notice), toast="Đã có hiệu lực, không huỷ được")
        if result == "preview":
            text = policy_cancel_text(policy_id=policy_id, subject=subject, when=vn_time(str(row["effective_at"])))
            keyboard = (
                (("✅ Huỷ lịch này", f"c:pc:{code}:{policy_id}:ok"),),
                (("◀️ Giữ lịch", f"c:menu:{back}"),),
            )
            return BotReply(text, inline_keyboard=keyboard)
        after = self.resolve_policy(datetime.strptime(str(row["effective_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
        notice = (
            f"✖️ Đã huỷ lịch #{policy_id} ({subject}). Từ {vn_time(str(row['effective_at']))} link mới vẫn theo "
            f"chia {_percent(after.share_bps)}, phí {_percent(after.fee_bps)}, thuế {_percent(after.tax_reserve_bps)}. "
            "Link đã tạo không đổi."
        )
        return replace(self._screen(back, now, notice), toast=f"Đã huỷ lịch #{policy_id}")

    def _policy_versions(self, now: datetime) -> list[str] | None:
        """Phiên bản tỷ lệ chia và dự phòng đã áp dụng, kèm trạng thái; và độ phủ snapshot link."""
        try:
            with self._connect() as conn:
                live = self.resolve_policy(now)
                shares = conn.execute("SELECT * FROM share_policies ORDER BY effective_at DESC, id DESC LIMIT 5").fetchall()
                reserves = conn.execute("SELECT * FROM reserve_policies ORDER BY effective_at DESC, id DESC LIMIT 5").fetchall()
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                coverage = policy_snapshot.coverage(conn) if "link_policy_snapshots" in tables else None
                cancelled = {"share": cancelled_ids(conn, "share"), "reserve": cancelled_ids(conn, "reserve")}
        except (AdminSafetyError, sqlite3.Error):
            return None
        stamp_now = _stamp(now)

        def state(row: sqlite3.Row, active_id: int | None, kind: str) -> str:
            if int(row["id"]) in cancelled[kind]:
                return "✖️ ĐÃ HUỶ TRƯỚC MỐC"
            if str(row["effective_at"]) > stamp_now:
                return "🗓️ ĐÃ HẸN GIỜ"
            return "🟢 ĐANG ÁP DỤNG" if int(row["id"]) == active_id else "⚪ ĐÃ THAY"

        share_active = live.share_policy_id if live.pricing_version == "v1.2" else None
        lines = [f"<b>Tỷ lệ chia</b> (V1.2){'' if live.pricing_version == 'v1.2' else ' · đang chạy V1.1, chưa dùng'}"]
        lines += [
            f"• #{row['id']} {_percent(int(row['share_bps']))} từ {vn_time(str(row['effective_at']))} · {state(row, share_active, 'share')}"
            for row in shares
        ] or [f"• Mặc định cấu hình {self.displayed_rate_percent}% · 🟢 ĐANG ÁP DỤNG"]
        lines.append("<b>Dự phòng phí và thuế</b>")
        lines += [
            f"• #{row['id']} phí {_percent(int(row['fee_bps']))}, thuế {_percent(int(row['tax_reserve_bps']))} "
            f"từ {vn_time(str(row['effective_at']))} · {state(row, live.reserve_policy_id, 'reserve')}"
            for row in reserves
        ] or [f"• Mặc định cấu hình phí {_percent(self.fee_default_bps)}, thuế {_percent(self.tax_default_bps)} · 🟢 ĐANG ÁP DỤNG"]
        if coverage is not None:
            done = coverage[policy_snapshot.CAPTURED] + coverage[policy_snapshot.BACKFILLED]
            lines.append(
                f"<b>Link đã chốt chính sách</b>: {done} · chưa xác định: "
                f"{coverage[policy_snapshot.UNRESOLVED] + coverage['missing']}"
            )
        return lines

    def _reserve_start(self, user_id: int, now: datetime) -> BotReply:
        with self._connect() as conn:
            _cancel_open_wizards(conn, user_id)
            cursor = conn.execute(
                """
                INSERT INTO reserve_drafts (admin_user_id, step, nonce, expires_at, created_at)
                VALUES (?, 'kind', ?, ?, ?)
                """,
                (user_id, secrets.token_hex(4), _stamp(now + CONFIRM_TTL), _stamp(now)),
            )
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._reserve_prompt(draft, now)

    def _reserve_action(self, user_id: int, draft_id: int, nonce: str, action: str, now: datetime) -> BotReply:
        applied_id: int | None = None
        with self._connect() as conn:
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                return BotReply("Nút này không hợp lệ.")
            if draft["step"] not in OPEN_STEPS:
                return BotReply("Bản này đã được xử lý. Bấm Đổi mức áp dụng để làm lại.")
            if draft["expires_at"] <= _stamp(now):
                conn.execute("UPDATE reserve_drafts SET step = 'expired' WHERE id = ?", (draft_id,))
                return BotReply("Bản nháp đã hết hạn sau 10 phút. Mức đang áp dụng không đổi.")
            active = active_reserve(conn, now, self.fee_default_bps, self.tax_default_bps)
            step = draft["step"]
            changes: dict | None = None
            if action == "no":
                changes = {"step": "cancelled"}
            elif action.startswith("k:") and step == "kind":
                changes = {"step": "fee", "account_kind": KIND_CODES[action[2:]]}
            elif action == "keep" and step == "fee":
                changes = {"step": "tax", "fee_bps": active.fee_bps}
            elif action == "keep" and step == "tax":
                changes = {"step": "when", "tax_reserve_bps": active.tax_reserve_bps}
            elif action == "w:now" and step == "when":
                changes = {"step": "preview", "effective_at": None}
            elif action == "w:tmr" and step == "when":
                changes = {"step": "preview", "effective_at": _stamp(next_midnight(now))}
            elif action == "ok" and step == "preview":
                effective = effective_from(draft["effective_at"], now)
                cursor = conn.execute(
                    """
                    INSERT INTO reserve_policies (
                        account_kind, fee_bps, tax_reserve_bps, effective_at, draft_id, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (draft["account_kind"], draft["fee_bps"], draft["tax_reserve_bps"], effective, draft_id, user_id, _stamp(now)),
                )
                applied_id = int(cursor.lastrowid)
                after = {
                    "id": applied_id,
                    "account_kind": draft["account_kind"],
                    "fee_bps": int(draft["fee_bps"]),
                    "tax_reserve_bps": int(draft["tax_reserve_bps"]),
                    "effective_at": effective,
                }
                before = {"id": active.policy_id, "fee_bps": active.fee_bps, "tax_reserve_bps": active.tax_reserve_bps}
                self._audit(
                    conn, user_id, "reserve_apply", None,
                    json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), "applied", now,
                )
                changes = {"step": "applied"}
            if changes is not None:
                changes.setdefault("expires_at", _stamp(now + CONFIRM_TTL))
                _update_draft(conn, draft_id, changes)
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft_id,)).fetchone()
        if draft["step"] == "cancelled":
            return replace(
                self._screen("fee", now, "✖️ Đã hủy. Mức đang áp dụng không đổi."),
                toast="Đã hủy",
            )
        if applied_id is not None:
            # Mốc đã qua lúc bấm Áp dụng thì effective_from ghi giờ bấm, không hồi tố.
            scheduled = draft["effective_at"] and draft["effective_at"] > _stamp(now)
            when = vn_time(draft["effective_at"]) if scheduled else "ngay bây giờ"
            notice = f"✅ Đã áp dụng mức #{applied_id} cho link mới, hiệu lực {when}. Link đã gửi giữ số cũ."
            return replace(self._screen("fee", now, notice), toast=f"Đã áp dụng mức #{applied_id}")
        # Nút của bước đã qua: hiện lại bước hiện tại.
        return self._reserve_prompt(draft, now)

    def _reserve_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not text or "shopee" in text.lower() or text.lower().startswith("http") or text.startswith("/"):
            return None
        with self._connect() as conn:
            draft = conn.execute(
                """
                SELECT * FROM reserve_drafts
                WHERE admin_user_id = ? AND step IN ('fee', 'tax', 'when') AND expires_at > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, _stamp(now)),
            ).fetchone()
            if draft is None:
                return None
            step = draft["step"]
            error = ""
            changes: dict | None = None
            if step in ("fee", "tax"):
                matched = _NUMBER.fullmatch(text)
                if matched is None:
                    error = "Gửi một số %, ví dụ 1,5."
                else:
                    bps = int(matched.group(1)) * 100 + int((matched.group(2) or "0").ljust(2, "0"))
                    if bps > MAX_RESERVE_BPS:
                        error = "Mỗi khoản dự phòng tối đa 50%."
                    elif step == "fee":
                        changes = {"step": "tax", "fee_bps": bps}
                    else:
                        changes = {"step": "when", "tax_reserve_bps": bps}
            else:
                moment, error = parse_when(text, now)
                if moment is None and not error:
                    error = "Chưa đọc được ngày. Gửi dạng 01/11 hoặc 01/11 08:00."
                if moment is not None:
                    changes = {"step": "preview", "effective_at": _stamp(moment)}
            if changes is not None:
                changes["expires_at"] = _stamp(now + CONFIRM_TTL)
                _update_draft(conn, int(draft["id"]), changes)
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft["id"],)).fetchone()
        return self._reserve_prompt(draft, now, error or "")

    def _reserve_prompt(self, draft: sqlite3.Row, now: datetime, error: str = "") -> BotReply:
        draft_id, nonce, step = int(draft["id"]), draft["nonce"], draft["step"]
        active = self.active_reserve(now)
        kind = ACCOUNT_KINDS.get(draft["account_kind"] or "", "")
        if step == "kind":
            return BotReply(
                reserve_kind_text(current=_kind_label(active)),
                inline_keyboard=reserve_kind_keyboard(draft_id, nonce),
            )
        if step in ("fee", "tax"):
            fee_step = step == "fee"
            current = _percent(active.fee_bps if fee_step else active.tax_reserve_bps)
            text = reserve_value_text(
                step="Bước 2/4" if fee_step else "Bước 3/4",
                kind=kind,
                subject="Phí dự phòng" if fee_step else "Thuế dự phòng",
                current=current,
                example="<code>0,98</code> hoặc <code>1,5</code>" if fee_step else "<code>10</code> hoặc <code>1,5</code>",
                error=error,
            )
            return BotReply(text, inline_keyboard=reserve_keep_keyboard(draft_id, nonce, current))
        if step == "when":
            text = reserve_when_text(
                kind=kind,
                fee=_percent(int(draft["fee_bps"])),
                tax=_percent(int(draft["tax_reserve_bps"])),
                error=error,
            )
            return BotReply(text, inline_keyboard=reserve_when_keyboard(draft_id, nonce))
        new = AppliedReserve(int(draft["fee_bps"]), int(draft["tax_reserve_bps"]))
        sample = recent = None
        if self.estimate_policy is not None:
            before = replace(self.resolve_policy(now), fee_bps=active.fee_bps, tax_reserve_bps=active.tax_reserve_bps)
            after = replace(before, fee_bps=new.fee_bps, tax_reserve_bps=new.tax_reserve_bps)
            sample = (cashback_for(SAMPLE_VND, before).cashback_vnd, cashback_for(SAMPLE_VND, after).cashback_vnd)
            recent = self._recent_totals(before, after)
        text = reserve_preview_text(
            calculator_on=self.estimate_policy is not None,
            kind=(_kind_label(active) or "Chưa khai báo", kind),
            fee=(_percent(active.fee_bps), _percent(new.fee_bps)),
            tax=(_percent(active.tax_reserve_bps), _percent(new.tax_reserve_bps)),
            when=vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay khi bấm Áp dụng",
            sample=sample,
            recent=recent,
        )
        return BotReply(text, inline_keyboard=reserve_decision_keyboard(draft_id, nonce))

    def _todo(self, now: datetime) -> tuple[list[str], str]:
        """(việc cần làm, dòng số hôm nay) cho trang chủ. Đọc mode=ro; lỗi đọc thì báo một dòng, không vỡ màn."""
        todo: list[str] = []
        try:
            with insights.open_readonly(self.db_path) as conn:
                tickets = conn.execute(
                    "SELECT COUNT(*) FROM support_tickets WHERE status NOT IN ('RESOLVED', 'REJECTED', 'CLOSED')"
                ).fetchone()[0]
                marks = ", ".join("?" for _ in payouts.OPEN)
                requests = conn.execute(
                    f"SELECT COUNT(*) FROM cashback_payouts WHERE status IN ({marks})", payouts.OPEN
                ).fetchone()[0]
                review = conn.execute(
                    f"SELECT COUNT(*) FROM shopee_conversions WHERE matched_link_id IS NOT NULL AND {VALIDATION_LISTS['alert'][1]}"
                ).fetchone()[0]
                red = [c for c in insights.operations(conn, now, self.auto_sync.interval_minutes) if not c.ok]
                day = insights.day_stats(conn, now)
        except sqlite3.Error:
            return ["⚠️ Chưa đọc được số liệu (thử lại sau ít phút)."], ""
        if tickets:
            todo.append(f"📩 {tickets} yêu cầu hỗ trợ đang mở")
        if requests:
            todo.append(f"👛 {requests} yêu cầu rút đang chờ")
        if review:
            todo.append(f"🧾 {review} đơn cần kiểm tra (🧾 Đơn & hoa hồng)")
        todo += [f"🔴 {c.label}: {c.value}" for c in red if c.code not in ("tickets", "payouts")]
        today = (f"📅 <b>Hôm nay</b>: {day.orders} đơn · HH ròng {format_vnd(day.net)} · {day.new} khách mới · "
                 f"{day.links} link")
        return todo, today

    def _wallet_on(self) -> bool:
        try:
            return TrackingRepository(self.db_path).get_state("wallet_enabled") == "1"
        except sqlite3.Error:
            return False

    def _orders_text(self) -> str:
        with insights.open_readonly(self.db_path) as conn:
            counts = dict(conn.execute(
                "SELECT platform, COUNT(*) FROM shopee_conversions WHERE matched_link_id IS NOT NULL GROUP BY platform"
            ).fetchall())
            review = conn.execute(
                f"SELECT COUNT(*) FROM shopee_conversions WHERE matched_link_id IS NOT NULL AND {VALIDATION_LISTS['alert'][1]}"
            ).fetchone()[0]
        return (
            "⚙️ Quản trị › <b>Đơn &amp; hoa hồng</b>\n\n"
            f"Đơn qua link bot: 🛒 Shopee <b>{counts.get('shopee', 0)}</b> · 🎵 TikTok <b>{counts.get('tiktok', 0)}</b>\n"
            f"Cần kiểm tra: <b>{review}</b>\n\n"
            "• 🧾 Duyệt hoa hồng: trạng thái hoa hồng từng đơn (cả Shopee và TikTok).\n"
            "• 💳 Đối soát thanh toán: khớp báo cáo Shopee đã trả với đơn.\n"
            "• 🔎 Đơn cần đối soát: đơn chờ lâu hoặc vắng trong báo cáo Shopee."
        )

    def _pending_count(self, now: datetime) -> int | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM admin_drafts
                    WHERE status IN ('collecting', 'preview') AND expires_at > ?
                    """,
                    (_stamp(now),),
                ).fetchone()
                return int(row[0])
        except AdminSafetyError:
            return None

    def _open_collecting(self, user_id: int, now: datetime) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                    """
                    SELECT * FROM admin_drafts
                    WHERE admin_user_id = ? AND status = 'collecting' AND expires_at > ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id, _stamp(now)),
                ).fetchone()
            if row is None:
                return None
            return {key: row[key] for key in row.keys()}

    def _latest_version(self, domain: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM policy_versions WHERE domain = ?",
                (domain,),
            ).fetchone()
            return int(row[0])

    def _rates(self) -> dict[str, int]:
        with self._connect() as conn:
            return self._stored_rates(conn)

    def _stored_rates(self, conn: sqlite3.Connection) -> dict[str, int]:
        row = conn.execute(
            """
            SELECT config_json FROM policy_versions
            WHERE domain = 'membership_rates' AND status = 'confirmed'
            ORDER BY version DESC
            LIMIT 1
            """
        ).fetchone()
        rates = dict(DIRECTIONAL_BPS)
        if row is None:
            return rates
        payload = json.loads(row["config_json"])
        for code in TIERS:
            key = code.lower() + "_bps"
            rates[code] = int(payload[key])
        return rates

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=15)  # như TrackingRepository.connect: chờ khoá ghi, không lỗi ngay
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(RESERVE_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(SHARE_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(CANCEL_SCHEMA_PATH.read_text(encoding="utf-8"))
        return conn

    def _log_setting(self, user_id: int, action: str, before: dict | None, after: dict | None, now: datetime) -> None:
        """Cài đặt đổi ngay, không qua bản nháp (ví, cookie Shopee). Vẫn phải hiện ở 📊 Lịch sử."""
        with self._connect() as conn:
            self._audit(
                conn,
                user_id,
                action,
                None,
                None if before is None else json.dumps(before, ensure_ascii=False),
                None if after is None else json.dumps(after, ensure_ascii=False),
                "applied",
                now,
            )

    def _audit(
        self,
        conn: sqlite3.Connection,
        user_id: int,
        action: str,
        draft_id: int | None,
        before: str | None,
        after: str | None,
        result: str,
        now: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO admin_change_audit (
                admin_user_id, action, draft_id, before_json, after_json, result, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, draft_id, before, after, result, _stamp(now)),
        )


def _draft_target(code: str) -> tuple[str, str, dict]:
    return "membership_rates", code, {
        "screen": "Hạng thành viên",
        "subject": f"Hạng {TIERS[code]}",
        "ask": "Gửi tỷ lệ mới theo %, từ 0 đến 70. Ví dụ: <code>62</code> hoặc <code>62,5</code>",
    }


def _policy_subject(kind: str, row) -> str:
    if kind == "share":
        return f"tỷ lệ chia {_percent(int(row['share_bps']))}"
    return f"dự phòng phí {_percent(int(row['fee_bps']))}, thuế {_percent(int(row['tax_reserve_bps']))}"


def _split(quote: CashbackQuote) -> tuple[int, int]:
    return quote.cashback_vnd, quote.remainder_vnd


def _screen_of(domain: str) -> str:
    return "rank" if domain == "membership_rates" else "fee"


def _kind_label(reserve: AppliedReserve) -> str | None:
    return ACCOUNT_KINDS.get(reserve.account_kind or "")


def _upcoming_line(reserve: AppliedReserve) -> str:
    return (
        f"{ACCOUNT_KINDS.get(reserve.account_kind or '', '-')} · phí {_percent(reserve.fee_bps)} · "
        f"thuế {_percent(reserve.tax_reserve_bps)} · từ {vn_time(reserve.effective_at or '')}"
    )


def _update_draft(conn: sqlite3.Connection, draft_id: int, changes: dict, table: str = "reserve_drafts") -> None:
    columns = ", ".join(f"{name} = ?" for name in changes)
    conn.execute(f"UPDATE {table} SET {columns} WHERE id = ?", (*changes.values(), draft_id))


def _cancel_open_wizards(conn: sqlite3.Connection, user_id: int) -> None:
    """Mỗi admin chỉ một wizard nhập số tại một lúc; mở cái mới thì hủy cái đang dở."""
    conn.execute(
        f"UPDATE reserve_drafts SET step = 'cancelled' WHERE admin_user_id = ? AND step IN {OPEN_STEPS}",
        (user_id,),
    )
    conn.execute(
        f"UPDATE share_drafts SET step = 'cancelled' WHERE admin_user_id = ? AND step IN {SHARE_OPEN_STEPS}",
        (user_id,),
    )


def _history_line(row: sqlite3.Row) -> str:
    moment = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    when = moment.astimezone(ICT).strftime("%d/%m %H:%M")
    if row["action"] == "reserve_apply" and row["after_json"]:
        data = json.loads(row["after_json"])
        subject = (
            f"Dự phòng {ACCOUNT_KINDS.get(data['account_kind'], '-')}: phí {_percent(data['fee_bps'])}, "
            f"thuế {_percent(data['tax_reserve_bps'])}, từ {vn_time(data['effective_at'])}"
        )
        return f"{when} · {subject} · {_ACTIONS['reserve_apply']}: {_RESULTS['applied']}"
    if row["action"] == "share_apply" and row["after_json"]:
        data = json.loads(row["after_json"])
        subject = f"Tỷ lệ chia → {_percent(data['share_bps'])}, từ {vn_time(data['effective_at'])}"
        return f"{when} · {subject} · {_ACTIONS['share_apply']}: {_RESULTS['applied']}"
    if row["action"] in {"share_cancel", "reserve_cancel"} and row["before_json"]:
        data = json.loads(row["before_json"])
        kind = "share" if row["action"] == "share_cancel" else "reserve"
        subject = f"#{data.get('id')} {_policy_subject(kind, data)}, mốc {vn_time(data['effective_at'])}"
        return f"{when} · {subject} · {_ACTIONS[row['action']]}: {_RESULTS['cancelled']}"
    setting = _setting_line(row)
    if setting is not None:
        return f"{when} · {setting}"
    domain = row["domain"]
    if domain == "membership_rates":
        subject = f"Hạng {TIERS.get(row['tier'], row['tier'])}"
    else:
        subject = RESERVE_NAMES.get(domain, domain or "-")
    if row["action"] in {"preview", "confirm"} and row["proposed_bps"] is not None:
        subject += f" → {_percent(int(row['proposed_bps']))}"
    action = _ACTIONS.get(row["action"], row["action"])
    result = _RESULTS.get(row["result"], row["result"])
    return f"{when} · {subject} · {action}: {result}"


def _setting_line(row: sqlite3.Row) -> str | None:
    """Dòng lịch sử cho cài đặt đổi ngay (PLAN-066). None: không phải loại này."""
    action = row["action"]
    if action not in {
        "wallet_enabled", "wallet_hold_days", "wallet_min_withdraw", "wallet_limits", "shopee_cookie", "shopee_auto_sync",
        "commission_review_ack", "terms_draft", "terms_publish", "bank_verified", "customer_notify_retry",
        "shopee_auto_sync_pause", "customer_notify_smoke", "customer_notify_intro", "ops_cost",
        "goal", "retention", "tiktok_mode", "sale_reminder", "deals", "announce",
    }:
        return None
    after = json.loads(row["after_json"]) if row["after_json"] else {}
    before = json.loads(row["before_json"]) if "before_json" in row.keys() and row["before_json"] else {}
    if action == "wallet_enabled":
        return "Ví khách → " + ("bật" if after.get("on") else "tắt")
    if action == "wallet_hold_days":
        return f"Ví khách: giữ tiền {before.get('days', '-')} → {after.get('days')} ngày sau khi đơn hoàn thành"
    if action == "wallet_min_withdraw":
        old = format_vnd(int(before["vnd"])) if "vnd" in before else "-"
        return f"Ví khách: rút tối thiểu {old} → {format_vnd(int(after['vnd']))}"
    if action == "wallet_limits":
        parts = [
            f"{label} {format_vnd(int(before[key]))} → {format_vnd(int(after[key]))}"
            for key, label in (("min", "tối thiểu"), ("req", "mỗi lần"), ("day", "mỗi ngày"), ("month", "mỗi tháng"))
            if key in after and before.get(key) != after[key]
        ]
        return "Ví khách: hạn mức rút " + ", ".join(parts)
    if action == "customer_notify_retry":
        return f"Thông báo khách: gửi lại tin #{after.get('id', '-')}"
    if action in {"customer_notify_smoke", "customer_notify_intro"}:
        # ID Telegram chỉ hiện 3 số cuối, như các màn khác.
        who = "…" + html.escape(str(after.get("chat_id", "-"))[-3:])
        if action == "customer_notify_intro":
            return f"Thông báo khách: tin giới thiệu thông báo đơn tới khách {who}"
        kind = "xử lý lại sự kiện thử (chống trùng)" if after.get("repeat") else "tin thử mới"
        return f"Thông báo khách: {kind} tới tài khoản test {who}"
    if action == "bank_verified":
        target = f"khách …{str(after['user'])[-3:]}" if "user" in after else f"yêu cầu #{after.get('payout', '-')}"
        return f"Ví khách: xác minh tài khoản ••••{html.escape(str(after.get('last4', '-')))} ({html.escape(target)})"
    if action == "ops_cost":
        old = format_vnd(int(before["vnd"])) if "vnd" in before else "chưa nhập"
        return f"Chi phí vận hành / hạ tầng: {old} → {format_vnd(int(after['vnd']))} mỗi tháng"
    if action == "goal":
        return goal_history(before, after)
    if action == "retention":
        return retention_history(before, after)
    if action == "tiktok_mode":
        return tiktok_history(before, after)
    if action == "sale_reminder":
        return engagement_history(before, after)
    if action == "deals":
        return deals_history(before, after)
    if action == "announce":
        return announce_history(before, after)
    if action in {"terms_draft", "terms_publish"}:
        verb = "tạo bản nháp" if action == "terms_draft" else "công bố"
        return f"Điều khoản: {verb} {html.escape(str(after.get('version', '-')))}"
    if action == "commission_review_ack":
        return f"Duyệt hoa hồng: đã kiểm tra cảnh báo đơn …{html.escape(str(after.get('conversion', '-'))[-4:])}"
    if action == "shopee_auto_sync":
        return "Shopee Affiliate: tự đồng bộ 4 giờ → " + ("bật" if after.get("on") else "tắt")
    if action == "shopee_auto_sync_pause":
        return "Shopee Affiliate: tự đồng bộ → " + ("tạm dừng" if after.get("paused") else "tiếp tục")
    return f"Shopee Affiliate: kết nối cookie ({html.escape(str(after.get('account', '-')))})"


def _parse_bps(domain: str, bps: int) -> int | None:
    return bps if 0 <= bps <= MAX_SHARE_BPS else None
