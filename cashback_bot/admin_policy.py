"""Phiên bản chính sách cho /admin.

Xác nhận chỉ lưu bản ghi bất biến với customer_effect=none.
Không đổi báo giá khách, không chi trả, không ghi database production.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
from dataclasses import dataclass, replace
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
    active_reserve,
    active_share,
    next_midnight,
    parse_when,
    recent_commissions,
    upcoming_reserves,
    upcoming_shares,
    vn_time,
)
from cashback_bot.admin_reserve import SCHEMA_PATH as RESERVE_SCHEMA_PATH
from cashback_bot.admin_reserve import SHARE_SCHEMA_PATH
from cashback_bot.admin_ui import (
    FEE_KEYBOARD,
    MENU_KEYBOARD,
    NAV_KEYBOARD,
    POLICY_KEYBOARD,
    RANK_KEYBOARD,
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
    simulation_text,
)
from cashback_bot.messages import BotReply
from cashback_bot.pricing import MAX_SHARE_BPS, EstimatePolicy, estimate_cashback, share_cashback

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
SAMPLE_VND = (10_000, 100_000)
# Admin gõ phần trăm: "10", "0,98", "0.98", "62,5%". Lưu nội bộ bằng bps.
_NUMBER = re.compile(r"^(\d{1,3})(?:[.,](\d{1,2}))?\s*%?$")
_MENU = re.compile(r"^c:menu:(home|policy|rank|fee|sim|hist|copy)$")
_TIER = re.compile(r"^c:tier:(BRONZE|SILVER|GOLD)$")
_RESERVE = re.compile(r"^c:rs:(\d+):([0-9a-f]{8}):(k:[PIH]|keep|w:now|w:tmr|ok|no)$")
_SHARE = re.compile(r"^c:sh:(\d+):([0-9a-f]{8}):(w:now|w:tmr|ok|no)$")
_SHARE_NUMBER = re.compile(r"^(\d{1,3})\s*%?$")
_DECISION = re.compile(r"^c:(ok|no):(\d+):([0-9a-f]{8})$")


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


def simulate_share(amount_vnd: int, before_bps: int, after_bps: int) -> tuple[tuple[int, int], tuple[int, int]]:
    return share_cashback(amount_vnd, before_bps), share_cashback(amount_vnd, after_bps)


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

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def menu(self, user_id: int, now: datetime) -> BotReply:
        if not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị.")
        return self._screen("home", now)

    def consume_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not self.is_admin(user_id):
            return None
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
        if data == "c:rs:new":
            return self._reserve_start(user_id, now)
        if data == "c:sh:new":
            return self._share_start(user_id, now)
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
            text = home_text(
                rate_percent=self._rate_percent(now),
                membership_on=self.membership_on,
                calculator=self.calculator_label,
                pending=self._pending_count(now),
            )
            return BotReply(text, inline_keyboard=MENU_KEYBOARD)
        if name == "policy":
            reserve = None
            live = self.live_policy(now)
            with self._connect() as conn:
                share = active_share(conn, now, self.displayed_rate_percent * 100)
                upcoming = upcoming_shares(conn, now)
            if live is None:
                customer, remain = share_cashback(100_000, self.displayed_rate_percent * 100)
            else:
                result = estimate_cashback(100_000, live)
                customer = result.estimated_cashback_vnd
                remain = result.distributable_vnd - customer
                reserve = (
                    _percent(live.service_fee_bps),
                    _percent(live.tax_risk_reserve_bps),
                    result.fee_reserve_vnd,
                    result.tax_risk_reserve_vnd,
                )
            warning = ""
            if live is None and (share.policy_id is not None or upcoming):
                warning = "Đang chạy V1.1: tỷ lệ admin đặt có tác dụng khi bật V1.2."
            text = policy_text(
                rate_percent=self._rate_percent(now),
                pending=self._pending_count(now),
                customer_vnd=customer,
                remain_vnd=remain,
                reserve=reserve,
                since=vn_time(share.effective_at) if share.effective_at and live is not None else None,
                upcoming=[f"{_percent(item.share_bps)} từ {vn_time(item.effective_at or '')}" for item in upcoming],
                warning=warning,
                notice=notice,
            )
            return BotReply(text, inline_keyboard=POLICY_KEYBOARD)
        if name == "rank":
            rates = self._safe_rates()
            tiers = [
                (TIER_EMOJI[code], label, _percent(rates[code]), *share_cashback(100_000, rates[code]))
                for code, label in TIERS.items()
            ]
            text = rank_text(tiers=tiers, notice=notice)
            return BotReply(text, inline_keyboard=RANK_KEYBOARD)
        if name == "fee":
            with self._connect() as conn:
                active = active_reserve(conn, now, self.fee_default_bps, self.tax_default_bps)
                upcoming = upcoming_reserves(conn, now)
            result = estimate_cashback(100_000, self._policy_with(active, self._share_bps(now)))
            text = fee_text(
                calculator_on=self.estimate_policy is not None,
                kind=_kind_label(active),
                fee=_percent(active.fee_bps),
                tax=_percent(active.tax_reserve_bps),
                since=vn_time(active.effective_at) if active.effective_at else None,
                upcoming=[_upcoming_line(item) for item in upcoming],
                rate_percent=self._rate_percent(now),
                sim_fee=result.fee_reserve_vnd,
                sim_tax=result.tax_risk_reserve_vnd,
                sim_dist=result.distributable_vnd,
                sim_customer=result.estimated_cashback_vnd,
                notice=notice,
            )
            return BotReply(text, inline_keyboard=FEE_KEYBOARD)
        if name == "sim":
            rates = self._safe_rates()
            table = [
                (amount, [(label, _percent(rates[code]), *share_cashback(amount, rates[code])) for code, label in TIERS.items()])
                for amount in SAMPLE_VND
            ]
            text = simulation_text(
                quote=quote_label(self._rate_percent(now), self.estimate_policy is not None),
                table=table,
            )
            return BotReply(text, inline_keyboard=NAV_KEYBOARD)
        if name == "hist":
            return BotReply(history_text(self._history_rows()), inline_keyboard=NAV_KEYBOARD)
        return BotReply(command_copy_text(), inline_keyboard=NAV_KEYBOARD)

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
        before_split, after_split = simulate_share(100_000, before, parsed)
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
                effective = draft["effective_at"] or _stamp(now)
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
            when = vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay bây giờ"
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
            reserve = self.active_reserve(now)
            before, after = self._policy_with(reserve, active.share_bps), self._policy_with(reserve, new_bps)
            old, new = estimate_cashback(100_000, before), estimate_cashback(100_000, after)
            sample = (
                old.estimated_cashback_vnd,
                new.estimated_cashback_vnd,
                old.distributable_vnd - old.estimated_cashback_vnd,
                new.distributable_vnd - new.estimated_cashback_vnd,
            )
            with self._connect() as conn:
                commissions = recent_commissions(conn)
            if commissions:
                recent = (
                    len(commissions),
                    sum(estimate_cashback(c, before).estimated_cashback_vnd for c in commissions),
                    sum(estimate_cashback(c, after).estimated_cashback_vnd for c in commissions),
                )
        text = share_preview_text(
            calculator_on=self.estimate_policy is not None,
            share=(_percent(active.share_bps), _percent(new_bps)),
            when=vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay khi bấm Áp dụng",
            sample=sample,
            recent=recent,
        )
        return BotReply(text, inline_keyboard=reserve_decision_keyboard(draft_id, nonce, "sh"))

    def _history_rows(self) -> list[str] | None:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT a.action, a.result, a.created_at, a.after_json, d.domain, d.tier, d.proposed_bps
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

    def live_policy(self, now: datetime) -> EstimatePolicy | None:
        """Công thức V1.2 đang báo giá, đã gồm mức admin áp dụng. None khi chạy V1.1."""
        if self.estimate_policy is None:
            return None
        return self._policy_with(self.active_reserve(now), self.active_share(now).share_bps)

    def _share_bps(self, now: datetime) -> int:
        if self.estimate_policy is None:
            return self.displayed_rate_percent * 100
        return self.active_share(now).share_bps

    def _rate_percent(self, now: datetime) -> int:
        return self._share_bps(now) // 100

    def _policy_with(self, reserve: AppliedReserve, share_bps: int | None = None) -> EstimatePolicy:
        base = self.estimate_policy or EstimatePolicy(cashback_share_bps=self.displayed_rate_percent * 100)
        return replace(
            base,
            service_fee_bps=reserve.fee_bps,
            tax_risk_reserve_bps=reserve.tax_reserve_bps,
            cashback_share_bps=base.cashback_share_bps if share_bps is None else share_bps,
        )

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
                effective = draft["effective_at"] or _stamp(now)
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
            when = vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay bây giờ"
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
            share_bps = self.active_share(now).share_bps
            before, after = self._policy_with(active, share_bps), self._policy_with(new, share_bps)
            sample = (
                estimate_cashback(100_000, before).estimated_cashback_vnd,
                estimate_cashback(100_000, after).estimated_cashback_vnd,
            )
            with self._connect() as conn:
                commissions = recent_commissions(conn)
            if commissions:
                recent = (
                    len(commissions),
                    sum(estimate_cashback(c, before).estimated_cashback_vnd for c in commissions),
                    sum(estimate_cashback(c, after).estimated_cashback_vnd for c in commissions),
                )
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
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(RESERVE_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(SHARE_SCHEMA_PATH.read_text(encoding="utf-8"))
        return conn

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


def _parse_bps(domain: str, bps: int) -> int | None:
    return bps if 0 <= bps <= MAX_SHARE_BPS else None
