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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot.admin_ui import (
    FEE_KEYBOARD,
    MENU_KEYBOARD,
    NAV_KEYBOARD,
    RANK_KEYBOARD,
    command_copy_text,
    decision_keyboard,
    fee_text,
    home_text,
    policy_text,
    rank_text,
    simulation_text,
)
from cashback_bot.messages import BotReply
from cashback_bot.pricing import MAX_SHARE_BPS, share_cashback

logger = logging.getLogger("cashback_bot")

SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "004_admin_policy.sql"
CONFIRM_TTL = timedelta(minutes=10)
TIERS = {"BRONZE": "Đồng", "SILVER": "Bạc", "GOLD": "Vàng"}
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

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def menu(self, user_id: int, now: datetime) -> BotReply:
        if not self.is_admin(user_id):
            return BotReply("Lệnh này chỉ dành cho quản trị.")
        pending = self._pending_count(now)
        text = home_text(
            rate_percent=self.displayed_rate_percent,
            membership_on=self.membership_on,
            calculator=self.calculator_label,
            pending=pending,
        )
        return BotReply(text, inline_keyboard=MENU_KEYBOARD)

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
        menu = _MENU.fullmatch(data or "")
        if menu:
            return self._menu_screen(menu.group(1), user_id, now)
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

    def _menu_screen(self, name: str, user_id: int, now: datetime) -> BotReply:
        if name == "home":
            text = home_text(
                rate_percent=self.displayed_rate_percent,
                membership_on=self.membership_on,
                calculator=self.calculator_label,
                pending=self._pending_count(now),
            )
            return BotReply(text, inline_keyboard=MENU_KEYBOARD)
        if name == "policy":
            text = policy_text(
                rate_percent=self.displayed_rate_percent,
                pending=self._pending_count(now),
            )
            return BotReply(text, inline_keyboard=NAV_KEYBOARD)
        if name == "rank":
            try:
                rates = self._rates()
            except AdminSafetyError:
                rates = dict(DIRECTIONAL_BPS)
            b_cash, b_rem = share_cashback(100_000, rates["BRONZE"])
            s_cash, s_rem = share_cashback(100_000, rates["SILVER"])
            g_cash, g_rem = share_cashback(100_000, rates["GOLD"])
            text = rank_text(
                bronze_percent=_percent(rates["BRONZE"]),
                silver_percent=_percent(rates["SILVER"]),
                gold_percent=_percent(rates["GOLD"]),
                displayed_rate_percent=self.displayed_rate_percent,
                b_cash=b_cash,
                b_rem=b_rem,
                s_cash=s_cash,
                s_rem=s_rem,
                g_cash=g_cash,
                g_rem=g_rem,
            )
            return BotReply(text, inline_keyboard=RANK_KEYBOARD)
        if name == "fee":
            fee_bps = 98
            tax_bps = 1_000
            sim_fee = (100_000 * fee_bps) // 10_000
            sim_tax = (100_000 * tax_bps) // 10_000
            sim_dist = 100_000 - sim_fee - sim_tax
            text = fee_text(
                fee_percent=_percent(fee_bps),
                fee_bps=fee_bps,
                tax_percent=_percent(tax_bps),
                tax_bps=tax_bps,
                sim_fee=sim_fee,
                sim_tax=sim_tax,
                sim_dist=sim_dist,
            )
            return BotReply(text, inline_keyboard=FEE_KEYBOARD)
        if name == "sim":
            try:
                rates = self._rates()
            except AdminSafetyError:
                rates = dict(DIRECTIONAL_BPS)
            text = simulation_text(
                displayed_rate_percent=self.displayed_rate_percent,
                rates=rates,
            )
            return BotReply(text, inline_keyboard=NAV_KEYBOARD)
        if name == "hist":
            return BotReply(self._history_text(), inline_keyboard=NAV_KEYBOARD)
        return BotReply(
            command_copy_text(),
            inline_keyboard=NAV_KEYBOARD,
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
        back_target = "c:menu:rank" if code in TIERS else "c:menu:fee"
        return BotReply(
            f"Bản nháp #{draft_id}. {prompt}",
            inline_keyboard=((("◀️ Quay lại", back_target), ("🏠 Tổng quan", "c:menu:home")),),
        )

    def _preview_number(self, draft: sqlite3.Row, raw: int, now: datetime) -> BotReply:
        parsed = _parse_bps(draft["domain"], raw)
        if parsed is None:
            return BotReply("Giá trị không nằm trong giới hạn. Hạng tối đa 70%. Dự phòng từ 0 đến 10000 phần vạn.")
        if draft["domain"] == "membership_rates":
            rates = self._rates()
            rates[draft["tier"]] = parsed
            ordered = [rates["BRONZE"], rates["SILVER"], rates["GOLD"]]
            if ordered != sorted(ordered):
                return BotReply("Tỷ lệ phải đi theo thứ tự Đồng, Bạc, rồi Vàng.")
            before = self._rates()[draft["tier"]]
            body = _rank_preview(draft["tier"], before, parsed)
        else:
            before = _reserve_default(draft["domain"])
            body = _reserve_preview(draft["domain"], before, parsed)
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
        except AdminSafetyError:
            return BotReply("Database đang chạy chưa được mở để lưu chính sách.")
        return BotReply("Đã hủy bản nháp. Chính sách đã lưu không đổi.", inline_keyboard=MENU_KEYBOARD)

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
        return BotReply(
            "Đã phê duyệt và lưu phiên bản. Chưa kích hoạt, nên khách vẫn nhận báo giá hiện hành. "
            "Báo giá đã lưu không tự tính lại. Chưa chi trả.",
            inline_keyboard=MENU_KEYBOARD,
        )

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

    def _simulation_text(self) -> str:
        lines = [
            "<b>MÔ PHỎNG</b>",
            "Số dưới đây là thử trên quỹ giả định, không phải lợi nhuận và không phát sinh tiền phải trả.",
            f"Khách đang thấy: {self.displayed_rate_percent}% hoa hồng ước tính.",
        ]
        try:
            rates = self._rates()
        except AdminSafetyError:
            rates = dict(DIRECTIONAL_BPS)
        for amount in SAMPLE_VND:
            lines.append(f"\nQuỹ {amount:,}đ".replace(",", "."))
            for code, label in TIERS.items():
                cashback, remain = share_cashback(amount, rates[code])
                lines.append(f"{label} {_percent(rates[code])}: hoàn {cashback:,}đ, phần còn {remain:,}đ".replace(",", "."))
        return "\n".join(lines)

    def _history_text(self) -> str:
        try:
            with self._connect() as conn:
                rows = [
                    (row["action"], row["result"], row["created_at"])
                    for row in conn.execute(
                        """
                        SELECT action, result, created_at
                        FROM admin_change_audit
                        ORDER BY id DESC
                        LIMIT 8
                        """
                    ).fetchall()
                ]
        except AdminSafetyError:
            return "Chưa đọc được lịch sử trên database đang chạy."
        if not rows:
            return "Chưa có thay đổi nào."
        lines = ["<b>LỊCH SỬ CẤU HÌNH</b>"]
        for action, result, created_at in rows:
            lines.append(f"{created_at} · {action} · {result}")
        return "\n".join(lines)

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


def _draft_target(code: str) -> tuple[str, str, str]:
    if code in TIERS:
        return "membership_rates", code, f"Nhập tỷ lệ mới cho hạng {TIERS[code]}, từ 0 đến 70."
    if code == "FEE":
        return "estimate_fee_reserve", "FEE", "Nhập phí dự phòng theo phần vạn. 98 nghĩa là 0,98%. Đây không phải phí đã đối soát."
    return "estimate_tax_reserve", "TAX", "Nhập dự phòng thuế theo phần vạn. Đây là ESTIMATE RESERVE, không phải thuế phải nộp."


def _parse_bps(domain: str, raw: int) -> int | None:
    if domain == "membership_rates":
        if 0 <= raw <= 70:
            return raw * 100
        return None
    if 0 <= raw <= 10_000:
        return raw
    return None


def _reserve_default(domain: str) -> int:
    if domain == "estimate_fee_reserve":
        return 98
    return 1_000


def _rank_preview(tier: str, before_bps: int, after_bps: int) -> str:
    before, after = simulate_share(100_000, before_bps, after_bps)
    return (
        "<b>XEM TRƯỚC THAY ĐỔI CHÍNH SÁCH</b>\n\n"
        f"Hạng: {TIERS[tier]}\n"
        f"Tỷ lệ đã lưu: {_percent(before_bps)}\n"
        f"Tỷ lệ đề xuất: {_percent(after_bps)}\n\n"
        "Mô phỏng quỹ phân chia 100.000đ. Không phải lợi nhuận.\n"
        f"Trước: hoàn {before[0]:,}đ, phần còn {before[1]:,}đ\n"
        f"Sau: hoàn {after[0]:,}đ, phần còn {after[1]:,}đ\n\n"
        "Xác nhận chỉ phê duyệt bản lưu, chưa kích hoạt cho khách. "
        "Báo giá đã lưu không tự tính lại.".replace(",", ".")
    )


def _reserve_preview(domain: str, before_bps: int, after_bps: int) -> str:
    name = "Phí dự phòng" if domain == "estimate_fee_reserve" else "Thuế dự phòng"
    return (
        "<b>XEM TRƯỚC DỰ PHÒNG</b>\n\n"
        f"{name}: {_percent(before_bps)} → {_percent(after_bps)}\n"
        "Nhãn: ESTIMATE RESERVE. Không phải thuế hoặc phí đã đối soát.\n"
        "Không sửa số đã thanh toán. Khách chưa đổi công thức V1.1."
    )
