"""🧮 Mô phỏng trong /admin: chỉ đọc, cùng cashback_for với báo giá khách; không ghi gì, không bật gì."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from cashback_bot.admin.base import BaseAdminHandler
from cashback_bot.admin.common import TIERS, expired_button, percent, split
from cashback_bot.admin.handlers.reserve import upcoming_reserves, upcoming_shares, vn_time
from cashback_bot.admin.ui import (
    SIM_PROMPT_KEYBOARD,
    quote_label,
    simulation_keyboard,
    simulation_prompt_text,
    simulation_text,
)
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd
from cashback_bot.pricing import PolicyResolution, cashback_for

if TYPE_CHECKING:
    from cashback_bot.admin.panel import AdminPanel

# Hoa hồng giả định admin chọn ở 🧮 Mô phỏng. Chỉ các mốc này, không nhận số tự do qua callback.
SIM_AMOUNTS = (10_000, 50_000, 100_000, 500_000)
# Nhập số tự do: một hoa hồng một đơn, từ 1đ tới 100 triệu. Chờ nhập giữ trong RAM, không ghi DB.
SIM_MAX_VND = 100_000_000
SIM_WAIT_TTL = timedelta(minutes=10)
INPUT = "c:sim:input"
_SIM = re.compile(r"^c:sim:(10000|50000|100000|500000|input)$")
_SIM_PLAIN = re.compile(r"^(\d{1,3}(?:[.,]\d{3})+|\d{1,9})\s*(?:đ|vnd|vnđ)?$")
_SIM_UNIT = re.compile(r"^(\d{1,6})(?:[.,](\d{1,3}))?\s*(k|nghìn|ngàn|tr|triệu)$")
_SIM_UNITS = {"k": 1_000, "nghìn": 1_000, "ngàn": 1_000, "tr": 1_000_000, "triệu": 1_000_000}


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


class SimulationAdmin(BaseAdminHandler):
    name = "simulation"
    callback_prefixes = ("c:sim:",)

    def __init__(self, panel: AdminPanel) -> None:
        self.panel = panel

    def keeps_state(self, data: str) -> bool:
        return data == INPUT

    def clear_state(self, user_id: int) -> None:
        self.panel._sim_waiting.pop(user_id, None)

    def route(self, user_id: int, data: str, now: datetime) -> BotReply:
        sim = _SIM.fullmatch(data or "")
        if sim is None:
            return expired_button()
        if sim.group(1) == "input":
            self.panel._sim_waiting[user_id] = now + SIM_WAIT_TTL
            return BotReply(simulation_prompt_text(), inline_keyboard=SIM_PROMPT_KEYBOARD)
        return self.render(now, int(sim.group(1)))

    def consume_text(self, user_id: int, text: str, now: datetime, message_id: int | None = None) -> BotReply | None:
        """Admin gõ hoa hồng giả định sau khi bấm ✏️ Nhập số khác. None: không chờ, để luồng khác xử lý."""
        waiting = self.panel._sim_waiting
        deadline = waiting.get(user_id)
        if deadline is None:
            return None
        stripped = (text or "").strip()
        lowered = stripped.lower()
        if deadline <= now or not stripped or stripped.startswith("/") or "shopee" in lowered or lowered.startswith("http"):
            waiting.pop(user_id, None)
            return None
        amount = parse_sim_amount(stripped)
        if amount is None:
            error = f"Chưa đọc được số. Gửi số tiền từ 1đ tới {format_vnd(SIM_MAX_VND)}, ví dụ 150000, 150.000 hoặc 150k."
            return BotReply(simulation_prompt_text(error=error), inline_keyboard=SIM_PROMPT_KEYBOARD)
        waiting.pop(user_id, None)
        return self.render(now, amount)

    def render(self, now: datetime, amount: int) -> BotReply:
        panel = self.panel
        live = panel.resolve_policy(now)
        v12 = live.pricing_version == "v1.2"
        # Cột so sánh dùng cùng tỷ lệ và dự phòng, chỉ đổi công thức. Không bật công thức nào.
        if v12:
            other = replace(live, pricing_version="v1.1", other_reserve_vnd=0, rounding_unit=1)
        else:
            other = replace(live, pricing_version="v1.2", other_reserve_vnd=panel.other_reserve_vnd, rounding_unit=panel.rounding_unit)
        current, compare = cashback_for(amount, live), cashback_for(amount, other)
        scheduled = []
        with panel._connect() as conn:
            moments = sorted(
                {item.effective_at for item in upcoming_shares(conn, now) if v12 and item.effective_at}
                | {item.effective_at for item in upcoming_reserves(conn, now) if item.effective_at}
            )[:3]
        for moment in moments:
            at = datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            future = panel.resolve_policy(at)
            result = cashback_for(amount, future)
            scheduled.append(
                f"Từ {vn_time(moment)}: chia {percent(future.share_bps)}, phí {percent(future.fee_bps)}, "
                f"thuế {percent(future.tax_reserve_bps)} → khách {format_vnd(result.cashback_vnd)}"
            )
        rates = panel._safe_rates()
        ranks = [
            (label, percent(rates[code]), *split(cashback_for(amount, replace(live, share_bps=rates[code]))))
            for code, label in TIERS.items()
        ]
        text = simulation_text(
            quote=quote_label(live.rate_percent, v12),
            amount=amount,
            settings=(percent(live.share_bps), percent(live.fee_bps), percent(live.tax_reserve_bps)),
            columns=(("V1.2" if v12 else "V1.1", current), ("V1.1" if v12 else "V1.2", compare)),
            scheduled=scheduled,
            ranks=ranks,
        )
        return BotReply(text, inline_keyboard=simulation_keyboard(SIM_AMOUNTS, amount))
