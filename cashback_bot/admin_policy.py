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

from cashback_bot.admin_ui import (
    FEE_KEYBOARD,
    MENU_KEYBOARD,
    NAV_KEYBOARD,
    RANK_KEYBOARD,
    collecting_keyboard,
    collecting_text,
    command_copy_text,
    decision_keyboard,
    fee_text,
    history_text,
    home_text,
    policy_text,
    rank_preview_text,
    rank_text,
    reserve_preview_text,
    simulation_text,
)
from cashback_bot.messages import BotReply
from cashback_bot.pricing import MAX_SHARE_BPS, share_cashback

logger = logging.getLogger("cashback_bot")

SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "004_admin_policy.sql"
CONFIRM_TTL = timedelta(minutes=10)
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
TIERS = {"BRONZE": "Đồng", "SILVER": "Bạc", "GOLD": "Vàng"}
TIER_EMOJI = {"BRONZE": "🥉", "SILVER": "🥈", "GOLD": "🥇"}
RESERVE_NAMES = {"estimate_fee_reserve": "Phí dự phòng", "estimate_tax_reserve": "Thuế dự phòng"}
_ACTIONS = {"draft": "Tạo bản nháp", "preview": "Xem trước", "confirm": "Xác nhận", "cancel": "Hủy"}
_RESULTS = {
    "collecting": "đang nhập",
    "preview": "chờ xác nhận",
    "confirmed": "đã lưu",
    "cancelled": "đã hủy",
    "expired": "hết hạn",
}
DIRECTIONAL_BPS = {"BRONZE": 6_000, "SILVER": 6_500, "GOLD": 7_000}
SAMPLE_VND = (10_000, 100_000)
_NUMBER = re.compile(r"^(\d{1,5})%?$")
_MENU = re.compile(r"^c:menu:(home|policy|rank|fee|sim|hist|copy)$")
_TIER = re.compile(r"^c:tier:(BRONZE|SILVER|GOLD|FEE|TAX)$")
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

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def menu(self, user_id: int, now: datetime) -> BotReply:
        if not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị.")
        return self._screen("home", now)

    def consume_text(self, user_id: int, text: str, now: datetime) -> BotReply | None:
        if not self.is_admin(user_id):
            return None
        matched = _NUMBER.fullmatch((text or "").strip())
        if matched is None:
            return None
        try:
            draft = self._open_collecting(user_id, now)
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        if draft is None:
            return None
        return self._preview_number(draft, int(matched.group(1)), now)

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
                rate_percent=self.displayed_rate_percent,
                membership_on=self.membership_on,
                calculator=self.calculator_label,
                pending=self._pending_count(now),
            )
            return BotReply(text, inline_keyboard=MENU_KEYBOARD)
        if name == "policy":
            customer, remain = share_cashback(100_000, self.displayed_rate_percent * 100)
            text = policy_text(
                rate_percent=self.displayed_rate_percent,
                pending=self._pending_count(now),
                customer_vnd=customer,
                remain_vnd=remain,
            )
            return BotReply(text, inline_keyboard=NAV_KEYBOARD)
        if name == "rank":
            rates = self._safe_rates()
            tiers = [
                (TIER_EMOJI[code], label, _percent(rates[code]), *share_cashback(100_000, rates[code]))
                for code, label in TIERS.items()
            ]
            text = rank_text(tiers=tiers, displayed_rate_percent=self.displayed_rate_percent, notice=notice)
            return BotReply(text, inline_keyboard=RANK_KEYBOARD)
        if name == "fee":
            fee_bps, fee_version = self._reserve("estimate_fee_reserve")
            tax_bps, tax_version = self._reserve("estimate_tax_reserve")
            sim_fee = (100_000 * fee_bps) // 10_000
            sim_tax = (100_000 * tax_bps) // 10_000
            text = fee_text(
                calculator_on=self.calculator_label == "V1.2",
                applied_fee=_percent(self.fee_default_bps),
                applied_tax=_percent(self.tax_default_bps),
                fee_percent=_percent(fee_bps),
                fee_bps=fee_bps,
                fee_source=_source(fee_version),
                tax_percent=_percent(tax_bps),
                tax_bps=tax_bps,
                tax_source=_source(tax_version),
                sim_fee=sim_fee,
                sim_tax=sim_tax,
                sim_dist=100_000 - sim_fee - sim_tax,
                notice=notice,
            )
            return BotReply(text, inline_keyboard=FEE_KEYBOARD)
        if name == "sim":
            rates = self._safe_rates()
            table = [
                (amount, [(label, _percent(rates[code]), *share_cashback(amount, rates[code])) for code, label in TIERS.items()])
                for amount in SAMPLE_VND
            ]
            text = simulation_text(displayed_rate_percent=self.displayed_rate_percent, table=table)
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
        if code in TIERS:
            current = _percent(self._safe_rates()[code])
        else:
            current = _percent(self._reserve(domain)[0])
        return BotReply(
            collecting_text(draft_id=draft_id, current=current, **prompt),
            inline_keyboard=collecting_keyboard(draft_id, nonce),
        )

    def _preview_number(self, draft: sqlite3.Row, raw: int, now: datetime) -> BotReply:
        parsed = _parse_bps(draft["domain"], raw)
        retry = collecting_keyboard(int(draft["id"]), draft["nonce"])
        if parsed is None:
            return BotReply(
                "Giá trị không nằm trong giới hạn. Hạng tối đa 70%. Dự phòng từ 0 đến 10000 phần vạn. Gửi lại số khác.",
                inline_keyboard=retry,
            )
        if draft["domain"] == "membership_rates":
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
        else:
            before = self._reserve(draft["domain"])[0]
            body = reserve_preview_text(
                name=RESERVE_NAMES[draft["domain"]],
                before=_percent(before),
                after=_percent(parsed),
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

    def _history_rows(self) -> list[str] | None:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT a.action, a.result, a.created_at, d.domain, d.tier, d.proposed_bps
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

    def _reserve(self, domain: str) -> tuple[int, int | None]:
        """Dự phòng đã lưu gần nhất và số phiên bản. Chưa lưu thì lấy mặc định cấu hình."""
        default = self.fee_default_bps if domain == "estimate_fee_reserve" else self.tax_default_bps
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT version, config_json FROM policy_versions
                    WHERE domain = ? AND status = 'confirmed'
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (domain,),
                ).fetchone()
        except AdminSafetyError:
            return default, None
        if row is None:
            return default, None
        return int(json.loads(row["config_json"])["bps"]), int(row["version"])

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
        script = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(script)
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
    if code in TIERS:
        return "membership_rates", code, {
            "screen": "Hạng thành viên",
            "subject": f"Hạng {TIERS[code]}",
            "ask": "Gửi tỷ lệ mới, số nguyên từ 0 đến 70. Ví dụ: <code>62</code>",
        }
    if code == "FEE":
        return "estimate_fee_reserve", "FEE", {
            "screen": "Thuế &amp; phí dự phòng",
            "subject": "Phí dự phòng",
            "ask": "Gửi số phần vạn từ 0 đến 10000. Ví dụ: <code>98</code> nghĩa là 0,98%.",
            "note": "Đây không phải phí đã đối soát.",
        }
    return "estimate_tax_reserve", "TAX", {
        "screen": "Thuế &amp; phí dự phòng",
        "subject": "Thuế dự phòng",
        "ask": "Gửi số phần vạn từ 0 đến 10000. Ví dụ: <code>1000</code> nghĩa là 10%.",
        "note": "Đây là ESTIMATE RESERVE, không phải thuế phải nộp.",
    }


def _screen_of(domain: str) -> str:
    return "rank" if domain == "membership_rates" else "fee"


def _source(version: int | None) -> str:
    return "mặc định cấu hình" if version is None else f"đã lưu v{version}"


def _history_line(row: sqlite3.Row) -> str:
    moment = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    when = moment.astimezone(ICT).strftime("%d/%m %H:%M")
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


def _parse_bps(domain: str, raw: int) -> int | None:
    if domain == "membership_rates":
        if 0 <= raw <= 70:
            return raw * 100
        return None
    if 0 <= raw <= 10_000:
        return raw
    return None
