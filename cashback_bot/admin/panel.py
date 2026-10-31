"""Phiên bản chính sách cho /admin.

Xác nhận chỉ lưu bản ghi bất biến với customer_effect=none.
Không đổi báo giá khách, không chi trả, không ghi database production.

AdminPanel giữ cấu hình, trạng thái chờ nhập (RAM) và các màn tổng quan / cài đặt / chính sách / hạng / phí /
lịch sử. Nút bấm và chữ gõ của từng phân hệ đi qua AdminRouter (bảng đăng ký ở `admin/routes.py`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from cashback_bot import insights, payouts
from cashback_bot.admin.common import (
    DIRECTIONAL_BPS,
    SAMPLE_VND,
    TIER_EMOJI,
    TIERS,
    AdminSafetyError,
    expired_button,
    kind_label,
    percent,
    split,
    stamp,
)
from cashback_bot.admin.handlers.history import history_rows, policy_versions
from cashback_bot.admin.handlers.reserve import (
    ACCOUNT_KINDS,
    CANCEL_SCHEMA_PATH,
    SHARE_SCHEMA_PATH,
    AppliedReserve,
    AppliedShare,
    active_reserve,
    active_share,
    resolve_policy,
    upcoming_reserves,
    upcoming_shares,
    vn_time,
)
from cashback_bot.admin.handlers.reserve import SCHEMA_PATH as RESERVE_SCHEMA_PATH
from cashback_bot.admin.handlers.shopee import ShopeeAdmin
from cashback_bot.admin.handlers.simulation import SIM_AMOUNTS, SimulationAdmin, parse_sim_amount, simulate_share
from cashback_bot.admin.handlers.insights import InsightsAdmin
from cashback_bot.admin.handlers.retention import RetentionAdmin
from cashback_bot.admin.handlers.support import SupportAdmin
from cashback_bot.admin.handlers.validation import LISTS as VALIDATION_LISTS
from cashback_bot.admin.handlers.wallet import WalletAdmin
from cashback_bot.admin.notify.admin_notify import AdminNotifier
from cashback_bot.admin.router import AdminRouter
from cashback_bot.admin.routes import build_router
from cashback_bot.admin.ui import (
    BACK_HOME,
    FEE_KEYBOARD,
    GLOSSARY,
    MENU_KEYBOARD,
    NAV_KEYBOARD,
    ORDERS_MENU_KEYBOARD,
    POLICY_KEYBOARD,
    RANK_KEYBOARD,
    SETTINGS_MENU_KEYBOARD,
    command_copy_text,
    fee_text,
    history_text,
    home_text,
    policy_text,
    rank_text,
    settings_text,
    with_rows,
)
from cashback_bot.config import AutoSyncConfig
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd
from cashback_bot.pricing import EstimatePolicy, PolicyResolution, cashback_for
from cashback_bot.wallet import Wallet

# Tên cũ import từ cashback_bot.admin_policy vẫn dùng được.
__all__ = [
    "AdminPanel",
    "AdminSafetyError",
    "SCHEMA_PATH",
    "SIM_AMOUNTS",
    "customer_policy_due",
    "parse_sim_amount",
    "simulate_share",
]

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "migrations" / "004_admin_policy.sql"
_SEARCH_COMMAND = re.compile(r"^/tim(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
_MENU = re.compile(r"^c:menu:(home|policy|rank|fee|sim|hist|copy|settings|orders|glossary)$")


def customer_policy_due(rows: list[dict], now: datetime) -> dict | None:
    """Chỉ bản customer_effect=apply và đã tới ngày hiệu lực. Bản none không được chọn."""
    now_stamp = stamp(now)
    chosen: dict | None = None
    for row in rows:
        if row.get("status") != "confirmed" or row.get("customer_effect") != "apply":
            continue
        effective = row.get("effective_at")
        if not effective or effective > now_stamp:
            continue
        if chosen is None or int(row["version"]) > int(chosen["version"]):
            chosen = row
    return chosen


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
    # Dựng lại mỗi lần tạo panel (kể cả dataclasses.replace) để handler trỏ đúng panel mới.
    _router: AdminRouter = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_router", build_router(self))

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def menu(self, user_id: int, now: datetime) -> BotReply:
        if not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị.")
        ShopeeAdmin(self).clear_state(user_id)
        return self._screen("home", now)

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        if not self.is_admin(user_id):
            return None
        # /tim <mã>: tìm link, đơn, ticket, yêu cầu rút, khách (PLAN-091).
        if (search := _SEARCH_COMMAND.fullmatch(text or "")) is not None:
            return self._insights().search(user_id, search.group(1) or "", now)
        return self._router.dispatch_text(user_id, text, now, message_id)

    def handle_callback(self, user_id: int, data: str, chat_type: str, now: datetime) -> BotReply:
        if chat_type != "private" or not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị trong cuộc trò chuyện riêng.")
        self._router.clear_states(user_id, data)
        reply = self._route_callback(user_id, data, now)
        if reply.inline_keyboard is None:
            # Callback sửa đè tin cũ. Thiếu nút thì admin kẹt ở màn chỉ có chữ.
            return replace(reply, inline_keyboard=NAV_KEYBOARD)
        return reply

    def _route_callback(self, user_id: int, data: str, now: datetime) -> BotReply:
        menu = _MENU.fullmatch(data or "")
        if menu:
            return self._screen(menu.group(1), now)
        reply = self._router.dispatch_callback(user_id, data or "", now)
        return expired_button() if reply is None else reply

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
                    percent(live.fee_bps),
                    percent(live.tax_reserve_bps),
                    result.fee_reserve_vnd,
                    result.tax_reserve_vnd,
                ),
                v12=v12,
                since=vn_time(share.effective_at) if share.effective_at and v12 else None,
                upcoming=[f"{percent(item.share_bps)} từ {vn_time(item.effective_at or '')}" for item in upcoming],
                warning=warning,
                notice=notice,
            )
            buttons = [
                (f"🗑 Huỷ lịch #{item.policy_id}: {percent(item.share_bps)} từ {vn_time(item.effective_at or '')}",
                 f"c:pc:s:{item.policy_id}")
                for item in upcoming
            ]
            return BotReply(text, inline_keyboard=with_rows(POLICY_KEYBOARD, buttons))
        if name == "rank":
            rates = self._safe_rates()
            live = self.resolve_policy(now)
            tiers = [
                (TIER_EMOJI[code], label, percent(rates[code]), *split(cashback_for(SAMPLE_VND, replace(live, share_bps=rates[code]))))
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
                kind=kind_label(active),
                fee=percent(active.fee_bps),
                tax=percent(active.tax_reserve_bps),
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
                (f"🗑 Huỷ lịch #{item.policy_id}: phí {percent(item.fee_bps)}, thuế {percent(item.tax_reserve_bps)}",
                 f"c:pc:r:{item.policy_id}")
                for item in upcoming
            ]
            return BotReply(text, inline_keyboard=with_rows(FEE_KEYBOARD, buttons))
        if name == "sim":
            return SimulationAdmin(self).render(now, SAMPLE_VND)
        if name == "hist":
            return BotReply(
                history_text(history_rows(self), policy_versions(self, now)),
                inline_keyboard=NAV_KEYBOARD,
            )
        if name == "shopee":
            return ShopeeAdmin(self).screen(now, notice)
        return BotReply(command_copy_text(), inline_keyboard=NAV_KEYBOARD)

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
                    (stamp(now),),
                ).fetchone()
                return int(row[0])
        except AdminSafetyError:
            return None

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
            (user_id, action, draft_id, before, after, result, stamp(now)),
        )


def _upcoming_line(reserve: AppliedReserve) -> str:
    return (
        f"{ACCOUNT_KINDS.get(reserve.account_kind or '', '-')} · phí {percent(reserve.fee_bps)} · "
        f"thuế {percent(reserve.tax_reserve_bps)} · từ {vn_time(reserve.effective_at or '')}"
    )
