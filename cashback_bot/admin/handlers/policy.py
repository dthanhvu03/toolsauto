"""Chính sách trong /admin: bản nháp hạng thành viên, dự phòng phí / thuế (ADR-047), tỷ lệ chia (ADR-048), huỷ lịch hẹn.

Bản nháp hạng chỉ lưu policy_versions với customer_effect=none. Dự phòng và tỷ lệ chia chỉ thêm dòng
(reserve_policies / share_policies), có hẹn giờ và huỷ trước mốc. Mọi bước ghi admin_change_audit.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cashback_bot.admin.base import BaseAdminHandler
from cashback_bot.admin.common import (
    CONFIRM_TTL,
    NUMBER,
    SAMPLE_VND,
    TIERS,
    AdminSafetyError,
    expired_button,
    kind_label,
    percent,
    stamp,
)
from cashback_bot.admin.handlers.history import policy_subject
from cashback_bot.admin.handlers.reserve import (
    ACCOUNT_KINDS,
    KIND_CODES,
    MAX_RESERVE_BPS,
    OPEN_STEPS,
    POLICY_TABLES,
    SHARE_OPEN_STEPS,
    AppliedReserve,
    active_reserve,
    active_share,
    cancel_scheduled,
    cancelled_ids,
    effective_from,
    next_midnight,
    parse_when,
    recent_commissions,
    vn_time,
)
from cashback_bot.admin.handlers.simulation import simulate_share
from cashback_bot.admin.ui import (
    collecting_keyboard,
    collecting_text,
    decision_keyboard,
    policy_cancel_text,
    rank_preview_text,
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
)
from cashback_bot.messages import BotReply
from cashback_bot.pricing import MAX_SHARE_BPS, PolicyResolution, cashback_for

if TYPE_CHECKING:
    from cashback_bot.admin.panel import AdminPanel

logger = logging.getLogger("cashback_bot")

_TIER = re.compile(r"^c:tier:(BRONZE|SILVER|GOLD)$")
_RESERVE = re.compile(r"^c:rs:(\d+):([0-9a-f]{8}):(k:[PIH]|keep|w:now|w:tmr|ok|no)$")
_SHARE = re.compile(r"^c:sh:(\d+):([0-9a-f]{8}):(w:now|w:tmr|ok|no)$")
_POLICY_CANCEL = re.compile(r"^c:pc:(s|r):(\d{1,9})(:ok)?$")
_CANCEL_KINDS = {"s": "share", "r": "reserve"}
_SHARE_NUMBER = re.compile(r"^(\d{1,3})\s*%?$")
_DECISION = re.compile(r"^c:(ok|no):(\d+):([0-9a-f]{8})$")
DB_CLOSED = "Database đang chạy chưa được mở để lưu chính sách."


class PolicyAdmin(BaseAdminHandler):
    """Trạng thái chờ nhập nằm trong bảng bản nháp (có hạn), không cần dọn khi đổi màn."""

    name = "policy"
    callback_prefixes = ("c:tier:", "c:ok:", "c:no:", "c:rs:", "c:sh:", "c:pc:")

    def __init__(self, panel: AdminPanel) -> None:
        self.panel = panel

    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        tier = _TIER.fullmatch(data or "")
        if tier:
            return self._begin(user_id, tier.group(1), now)
        cancel = _POLICY_CANCEL.fullmatch(data or "")
        if cancel:
            kind = _CANCEL_KINDS[cancel.group(1)]
            return self._policy_cancel(user_id, kind, int(cancel.group(2)), bool(cancel.group(3)), now)
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
            return expired_button()
        action, draft_id, nonce = decision.group(1), int(decision.group(2)), decision.group(3)
        if action == "no":
            return self._cancel(user_id, draft_id, nonce, now)
        return self._confirm(user_id, draft_id, nonce, now)

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        """Thứ tự: wizard dự phòng → wizard tỷ lệ chia → số % cho bản nháp hạng đang nhập."""
        stripped = (text or "").strip()
        reserve = self._reserve_text(user_id, stripped, now)
        if reserve is not None:
            return reserve
        share = self._share_text(user_id, stripped, now)
        if share is not None:
            return share
        matched = NUMBER.fullmatch(stripped)
        if matched is None:
            return None
        try:
            draft = self._open_collecting(user_id, now)
        except AdminSafetyError:
            return BotReply(DB_CLOSED)
        if draft is None:
            return None
        bps = int(matched.group(1)) * 100 + int((matched.group(2) or "0").ljust(2, "0"))
        return self._preview_number(draft, bps, now)

    def _begin(self, user_id: int, code: str, now: datetime) -> BotReply:
        domain, tier, prompt = _draft_target(code)
        try:
            base = self._latest_version(domain)
            nonce = secrets.token_hex(4)
            expires = stamp(now + CONFIRM_TTL)
            with self.panel._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO admin_drafts (
                        admin_user_id, domain, tier, proposed_bps, base_version,
                        status, nonce, expires_at, created_at
                    ) VALUES (?, ?, ?, NULL, ?, 'collecting', ?, ?, ?)
                    """,
                    (user_id, domain, tier, base, nonce, expires, stamp(now)),
                )
                draft_id = int(cursor.lastrowid)
                self.panel._audit(conn, user_id, "draft", draft_id, None, None, "collecting", now)
        except AdminSafetyError:
            return BotReply(DB_CLOSED)
        current = percent(self.panel._safe_rates()[code])
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
        rates = self.panel._rates()
        rates[draft["tier"]] = parsed
        ordered = [rates["BRONZE"], rates["SILVER"], rates["GOLD"]]
        if ordered != sorted(ordered):
            return BotReply("Tỷ lệ phải đi theo thứ tự Đồng ≤ Bạc ≤ Vàng. Gửi lại số khác.", inline_keyboard=retry)
        before = self.panel._rates()[draft["tier"]]
        before_split, after_split = simulate_share(SAMPLE_VND, self.panel.resolve_policy(now), before, parsed)
        body = rank_preview_text(
            tier_name=TIERS[draft["tier"]],
            before=percent(before),
            after=percent(parsed),
            before_split=before_split,
            after_split=after_split,
        )
        with self.panel._connect() as conn:
            updated = conn.execute(
                """
                UPDATE admin_drafts
                SET status = 'preview', proposed_bps = ?
                WHERE id = ? AND status = 'collecting' AND expires_at > ?
                """,
                (parsed, draft["id"], stamp(now)),
            )
            if updated.rowcount != 1:
                return BotReply("Bản nháp đã hết hạn hoặc đã được xử lý.")
            self.panel._audit(conn, int(draft["admin_user_id"]), "preview", int(draft["id"]), None, body, "preview", now)
        return BotReply(body, inline_keyboard=decision_keyboard(int(draft["id"]), draft["nonce"]))

    def _cancel(self, user_id: int, draft_id: int, nonce: str, now: datetime) -> BotReply:
        try:
            with self.panel._connect() as conn:
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
                self.panel._audit(conn, user_id, "cancel", draft_id, None, None, "cancelled", now)
                domain = conn.execute("SELECT domain FROM admin_drafts WHERE id = ?", (draft_id,)).fetchone()[0]
        except AdminSafetyError:
            return BotReply(DB_CLOSED)
        notice = f"✖️ Đã hủy bản nháp #{draft_id}. Chính sách đã lưu không đổi."
        return replace(self.panel._screen(_screen_of(domain), now, notice), toast="Đã hủy bản nháp")

    def _confirm(self, user_id: int, draft_id: int, nonce: str, now: datetime) -> BotReply:
        domain = ""
        try:
            with self.panel._connect() as conn:
                draft = conn.execute("SELECT * FROM admin_drafts WHERE id = ?", (draft_id,)).fetchone()
                if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                    return BotReply("Nút xác nhận không hợp lệ.")
                domain = str(draft["domain"])
                if draft["status"] != "preview" or draft["proposed_bps"] is None:
                    return BotReply("Bản này đã được xử lý.")
                if draft["expires_at"] <= stamp(now):
                    conn.execute(
                        "UPDATE admin_drafts SET status = 'expired' WHERE id = ? AND status = 'preview'",
                        (draft_id,),
                    )
                    self.panel._audit(conn, user_id, "confirm", draft_id, None, None, "expired", now)
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
                before = json.dumps(self.panel._stored_rates(conn), ensure_ascii=False, sort_keys=True)
                conn.execute(
                    """
                    INSERT INTO policy_versions (
                        domain, version, status, config_json, effective_at,
                        customer_effect, created_by, created_at
                    ) VALUES (?, ?, 'confirmed', ?, ?, 'none', ?, ?)
                    """,
                    (domain, version, json.dumps(config, sort_keys=True), stamp(now), user_id, stamp(now)),
                )
                self.panel._audit(
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
            return BotReply(DB_CLOSED)
        except sqlite3.IntegrityError:
            return BotReply("Đã có phiên bản mới hơn. Hãy tạo lại bản nháp.")
        logger.info("[Cashback] admin policy confirmed domain=%s", domain)
        notice = (
            f"✅ Đã lưu phiên bản v{version}. Chưa kích hoạt, khách vẫn nhận báo giá hiện hành. "
            "Báo giá đã lưu không tự tính lại. Chưa chi trả."
        )
        return replace(self.panel._screen(_screen_of(domain), now, notice), toast=f"Đã lưu phiên bản v{version}")

    def _config_for(self, conn: sqlite3.Connection, draft: sqlite3.Row) -> dict:
        if draft["domain"] == "membership_rates":
            rates = self.panel._stored_rates(conn)
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
        with self.panel._connect() as conn:
            _cancel_open_wizards(conn, user_id)
            cursor = conn.execute(
                """
                INSERT INTO share_drafts (admin_user_id, step, nonce, expires_at, created_at)
                VALUES (?, 'share', ?, ?, ?)
                """,
                (user_id, secrets.token_hex(4), stamp(now + CONFIRM_TTL), stamp(now)),
            )
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._share_prompt(draft, now)

    def _share_action(self, user_id: int, draft_id: int, nonce: str, action: str, now: datetime) -> BotReply:
        applied_id: int | None = None
        with self.panel._connect() as conn:
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                return BotReply("Nút này không hợp lệ.")
            if draft["step"] not in SHARE_OPEN_STEPS:
                return BotReply("Bản này đã được xử lý. Bấm Đổi tỷ lệ chia để làm lại.")
            if draft["expires_at"] <= stamp(now):
                conn.execute("UPDATE share_drafts SET step = 'expired' WHERE id = ?", (draft_id,))
                return BotReply("Bản nháp đã hết hạn sau 10 phút. Tỷ lệ đang áp dụng không đổi.")
            step = draft["step"]
            changes: dict | None = None
            if action == "no":
                changes = {"step": "cancelled"}
            elif action == "w:now" and step == "when":
                changes = {"step": "preview", "effective_at": None}
            elif action == "w:tmr" and step == "when":
                changes = {"step": "preview", "effective_at": stamp(next_midnight(now))}
            elif action == "ok" and step == "preview":
                active = active_share(conn, now, self.panel.displayed_rate_percent * 100)
                effective = effective_from(draft["effective_at"], now)
                cursor = conn.execute(
                    """
                    INSERT INTO share_policies (share_bps, effective_at, draft_id, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (draft["share_bps"], effective, draft_id, user_id, stamp(now)),
                )
                applied_id = int(cursor.lastrowid)
                after = {"id": applied_id, "share_bps": int(draft["share_bps"]), "effective_at": effective}
                before = {"id": active.policy_id, "share_bps": active.share_bps}
                self.panel._audit(
                    conn, user_id, "share_apply", None,
                    json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), "applied", now,
                )
                changes = {"step": "applied"}
            if changes is not None:
                changes.setdefault("expires_at", stamp(now + CONFIRM_TTL))
                _update_draft(conn, draft_id, changes, table="share_drafts")
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft_id,)).fetchone()
        if draft["step"] == "cancelled":
            return replace(self.panel._screen("policy", now, "✖️ Đã hủy. Tỷ lệ đang áp dụng không đổi."), toast="Đã hủy")
        if applied_id is not None:
            # Mốc đã qua lúc bấm Áp dụng thì effective_from ghi giờ bấm, không hồi tố.
            scheduled = draft["effective_at"] and draft["effective_at"] > stamp(now)
            when = vn_time(draft["effective_at"]) if scheduled else "ngay bây giờ"
            notice = (
                f"✅ Đã áp dụng tỷ lệ chia {percent(int(draft['share_bps']))} (#{applied_id}) cho link mới, "
                f"hiệu lực {when}. Link đã gửi giữ số cũ."
            )
            return replace(self.panel._screen("policy", now, notice), toast=f"Đã áp dụng tỷ lệ #{applied_id}")
        return self._share_prompt(draft, now)

    def _share_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not text or "shopee" in text.lower() or text.lower().startswith("http") or text.startswith("/"):
            return None
        with self.panel._connect() as conn:
            draft = conn.execute(
                """
                SELECT * FROM share_drafts
                WHERE admin_user_id = ? AND step IN ('share', 'when') AND expires_at > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, stamp(now)),
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
                    changes = {"step": "preview", "effective_at": stamp(moment)}
            if changes is not None:
                changes["expires_at"] = stamp(now + CONFIRM_TTL)
                _update_draft(conn, int(draft["id"]), changes, table="share_drafts")
            draft = conn.execute("SELECT * FROM share_drafts WHERE id = ?", (draft["id"],)).fetchone()
        return self._share_prompt(draft, now, error or "")

    def _share_prompt(self, draft: sqlite3.Row, now: datetime, error: str = "") -> BotReply:
        draft_id, nonce, step = int(draft["id"]), draft["nonce"], draft["step"]
        active = self.panel.active_share(now)
        if step == "share":
            return BotReply(
                share_value_text(current=percent(active.share_bps), error=error),
                inline_keyboard=share_cancel_keyboard(draft_id, nonce),
            )
        if step == "when":
            return BotReply(
                share_when_text(share=percent(int(draft["share_bps"])), error=error),
                inline_keyboard=reserve_when_keyboard(draft_id, nonce, "sh"),
            )
        new_bps = int(draft["share_bps"])
        sample = recent = None
        if self.panel.estimate_policy is not None:
            before = self.panel.resolve_policy(now)
            after = replace(before, share_bps=new_bps)
            old, new = cashback_for(SAMPLE_VND, before), cashback_for(SAMPLE_VND, after)
            sample = (old.cashback_vnd, new.cashback_vnd, old.remainder_vnd, new.remainder_vnd)
            recent = self._recent_totals(before, after)
        text = share_preview_text(
            calculator_on=self.panel.estimate_policy is not None,
            share=(percent(active.share_bps), percent(new_bps)),
            when=vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay khi bấm Áp dụng",
            sample=sample,
            recent=recent,
        )
        return BotReply(text, inline_keyboard=reserve_decision_keyboard(draft_id, nonce, "sh"))

    def _recent_totals(self, before: PolicyResolution, after: PolicyResolution) -> tuple[int, int, int] | None:
        """Tổng tiền hoàn trên hoa hồng ước tính của các link gần nhất, trước và sau thay đổi."""
        with self.panel._connect() as conn:
            commissions = recent_commissions(conn)
        if not commissions:
            return None
        return (
            len(commissions),
            sum(cashback_for(c, before).cashback_vnd for c in commissions),
            sum(cashback_for(c, after).cashback_vnd for c in commissions),
        )

    def _policy_cancel(self, user_id: int, kind: str, policy_id: int, confirm: bool, now: datetime) -> BotReply:
        """Huỷ chính sách đã hẹn giờ, chỉ trước mốc hiệu lực. Bước 1 hỏi lại, bước 2 ghi dòng huỷ + audit."""
        back = "policy" if kind == "share" else "fee"
        code = "s" if kind == "share" else "r"
        with self.panel._connect() as conn:
            if confirm:
                conn.execute("BEGIN IMMEDIATE")
                row, result = cancel_scheduled(conn, kind, policy_id, user_id, now)
                if result == "ok":
                    before = {key: row[key] for key in row.keys() if key in {"id", "share_bps", "fee_bps", "tax_reserve_bps", "account_kind", "effective_at"}}
                    self.panel._audit(conn, user_id, f"{kind}_cancel", None, json.dumps(before, sort_keys=True), None, "cancelled", now)
            else:
                row = conn.execute(f"SELECT * FROM {POLICY_TABLES[kind]} WHERE id = ?", (policy_id,)).fetchone()
                result = "preview"
                if row is not None and policy_id in cancelled_ids(conn, kind):
                    result = "cancelled_before"
                elif row is not None and str(row["effective_at"]) <= stamp(now):
                    result = "already_effective"
        if row is None or result == "not_found":
            return replace(self.panel._screen(back, now, "Không thấy lịch hẹn này."), toast="Không thấy lịch hẹn")
        subject = policy_subject(kind, row)
        if result == "cancelled_before":
            return replace(self.panel._screen(back, now, f"Lịch #{policy_id} đã được huỷ trước đó."), toast="Đã huỷ trước đó")
        if result == "already_effective":
            notice = (
                f"⚠️ #{policy_id} ({subject}) đã tới giờ hiệu lực, không huỷ được vì có thể đã áp cho link. "
                "Muốn đổi thì áp dụng mức mới."
            )
            return replace(self.panel._screen(back, now, notice), toast="Đã có hiệu lực, không huỷ được")
        if result == "preview":
            text = policy_cancel_text(policy_id=policy_id, subject=subject, when=vn_time(str(row["effective_at"])))
            keyboard = (
                (("✅ Huỷ lịch này", f"c:pc:{code}:{policy_id}:ok"),),
                (("◀️ Giữ lịch", f"c:menu:{back}"),),
            )
            return BotReply(text, inline_keyboard=keyboard)
        after = self.panel.resolve_policy(datetime.strptime(str(row["effective_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
        notice = (
            f"✖️ Đã huỷ lịch #{policy_id} ({subject}). Từ {vn_time(str(row['effective_at']))} link mới vẫn theo "
            f"chia {percent(after.share_bps)}, phí {percent(after.fee_bps)}, thuế {percent(after.tax_reserve_bps)}. "
            "Link đã tạo không đổi."
        )
        return replace(self.panel._screen(back, now, notice), toast=f"Đã huỷ lịch #{policy_id}")

    def _reserve_start(self, user_id: int, now: datetime) -> BotReply:
        with self.panel._connect() as conn:
            _cancel_open_wizards(conn, user_id)
            cursor = conn.execute(
                """
                INSERT INTO reserve_drafts (admin_user_id, step, nonce, expires_at, created_at)
                VALUES (?, 'kind', ?, ?, ?)
                """,
                (user_id, secrets.token_hex(4), stamp(now + CONFIRM_TTL), stamp(now)),
            )
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._reserve_prompt(draft, now)

    def _reserve_action(self, user_id: int, draft_id: int, nonce: str, action: str, now: datetime) -> BotReply:
        applied_id: int | None = None
        with self.panel._connect() as conn:
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None or int(draft["admin_user_id"]) != user_id or draft["nonce"] != nonce:
                return BotReply("Nút này không hợp lệ.")
            if draft["step"] not in OPEN_STEPS:
                return BotReply("Bản này đã được xử lý. Bấm Đổi mức áp dụng để làm lại.")
            if draft["expires_at"] <= stamp(now):
                conn.execute("UPDATE reserve_drafts SET step = 'expired' WHERE id = ?", (draft_id,))
                return BotReply("Bản nháp đã hết hạn sau 10 phút. Mức đang áp dụng không đổi.")
            active = active_reserve(conn, now, self.panel.fee_default_bps, self.panel.tax_default_bps)
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
                changes = {"step": "preview", "effective_at": stamp(next_midnight(now))}
            elif action == "ok" and step == "preview":
                effective = effective_from(draft["effective_at"], now)
                cursor = conn.execute(
                    """
                    INSERT INTO reserve_policies (
                        account_kind, fee_bps, tax_reserve_bps, effective_at, draft_id, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (draft["account_kind"], draft["fee_bps"], draft["tax_reserve_bps"], effective, draft_id, user_id, stamp(now)),
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
                self.panel._audit(
                    conn, user_id, "reserve_apply", None,
                    json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), "applied", now,
                )
                changes = {"step": "applied"}
            if changes is not None:
                changes.setdefault("expires_at", stamp(now + CONFIRM_TTL))
                _update_draft(conn, draft_id, changes)
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft_id,)).fetchone()
        if draft["step"] == "cancelled":
            return replace(
                self.panel._screen("fee", now, "✖️ Đã hủy. Mức đang áp dụng không đổi."),
                toast="Đã hủy",
            )
        if applied_id is not None:
            # Mốc đã qua lúc bấm Áp dụng thì effective_from ghi giờ bấm, không hồi tố.
            scheduled = draft["effective_at"] and draft["effective_at"] > stamp(now)
            when = vn_time(draft["effective_at"]) if scheduled else "ngay bây giờ"
            notice = f"✅ Đã áp dụng mức #{applied_id} cho link mới, hiệu lực {when}. Link đã gửi giữ số cũ."
            return replace(self.panel._screen("fee", now, notice), toast=f"Đã áp dụng mức #{applied_id}")
        # Nút của bước đã qua: hiện lại bước hiện tại.
        return self._reserve_prompt(draft, now)

    def _reserve_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not text or "shopee" in text.lower() or text.lower().startswith("http") or text.startswith("/"):
            return None
        with self.panel._connect() as conn:
            draft = conn.execute(
                """
                SELECT * FROM reserve_drafts
                WHERE admin_user_id = ? AND step IN ('fee', 'tax', 'when') AND expires_at > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, stamp(now)),
            ).fetchone()
            if draft is None:
                return None
            step = draft["step"]
            error = ""
            changes: dict | None = None
            if step in ("fee", "tax"):
                matched = NUMBER.fullmatch(text)
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
                    changes = {"step": "preview", "effective_at": stamp(moment)}
            if changes is not None:
                changes["expires_at"] = stamp(now + CONFIRM_TTL)
                _update_draft(conn, int(draft["id"]), changes)
            draft = conn.execute("SELECT * FROM reserve_drafts WHERE id = ?", (draft["id"],)).fetchone()
        return self._reserve_prompt(draft, now, error or "")

    def _reserve_prompt(self, draft: sqlite3.Row, now: datetime, error: str = "") -> BotReply:
        draft_id, nonce, step = int(draft["id"]), draft["nonce"], draft["step"]
        active = self.panel.active_reserve(now)
        kind = ACCOUNT_KINDS.get(draft["account_kind"] or "", "")
        if step == "kind":
            return BotReply(
                reserve_kind_text(current=kind_label(active)),
                inline_keyboard=reserve_kind_keyboard(draft_id, nonce),
            )
        if step in ("fee", "tax"):
            fee_step = step == "fee"
            current = percent(active.fee_bps if fee_step else active.tax_reserve_bps)
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
                fee=percent(int(draft["fee_bps"])),
                tax=percent(int(draft["tax_reserve_bps"])),
                error=error,
            )
            return BotReply(text, inline_keyboard=reserve_when_keyboard(draft_id, nonce))
        new = AppliedReserve(int(draft["fee_bps"]), int(draft["tax_reserve_bps"]))
        sample = recent = None
        if self.panel.estimate_policy is not None:
            before = replace(self.panel.resolve_policy(now), fee_bps=active.fee_bps, tax_reserve_bps=active.tax_reserve_bps)
            after = replace(before, fee_bps=new.fee_bps, tax_reserve_bps=new.tax_reserve_bps)
            sample = (cashback_for(SAMPLE_VND, before).cashback_vnd, cashback_for(SAMPLE_VND, after).cashback_vnd)
            recent = self._recent_totals(before, after)
        text = reserve_preview_text(
            calculator_on=self.panel.estimate_policy is not None,
            kind=(kind_label(active) or "Chưa khai báo", kind),
            fee=(percent(active.fee_bps), percent(new.fee_bps)),
            tax=(percent(active.tax_reserve_bps), percent(new.tax_reserve_bps)),
            when=vn_time(draft["effective_at"]) if draft["effective_at"] else "ngay khi bấm Áp dụng",
            sample=sample,
            recent=recent,
        )
        return BotReply(text, inline_keyboard=reserve_decision_keyboard(draft_id, nonce))

    def _open_collecting(self, user_id: int, now: datetime) -> dict | None:
        with self.panel._connect() as conn:
            row = conn.execute(
                    """
                    SELECT * FROM admin_drafts
                    WHERE admin_user_id = ? AND status = 'collecting' AND expires_at > ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id, stamp(now)),
                ).fetchone()
            if row is None:
                return None
            return {key: row[key] for key in row.keys()}

    def _latest_version(self, domain: str) -> int:
        with self.panel._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM policy_versions WHERE domain = ?",
                (domain,),
            ).fetchone()
            return int(row[0])


def _draft_target(code: str) -> tuple[str, str, dict]:
    return "membership_rates", code, {
        "screen": "Hạng thành viên",
        "subject": f"Hạng {TIERS[code]}",
        "ask": "Gửi tỷ lệ mới theo %, từ 0 đến 70. Ví dụ: <code>62</code> hoặc <code>62,5</code>",
    }


def _screen_of(domain: str) -> str:
    return "rank" if domain == "membership_rates" else "fee"


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


def _parse_bps(domain: str, bps: int) -> int | None:
    return bps if 0 <= bps <= MAX_SHARE_BPS else None


