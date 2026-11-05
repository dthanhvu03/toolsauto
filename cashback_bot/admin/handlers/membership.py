"""/admin → ➕ Thêm → ⚙️ Cài đặt → 🎖️ Hạng thành viên → 🎯 Điều kiện lên hạng (PLAN-154).

Callback: c:mb:home · c:mb:e:<mã> (gõ số, 10 phút) · c:mb:d:<mã> (về mặc định). Mỗi lần đổi ghi 📊 Lịch sử
(action `membership_thresholds`). Điều kiện mới dùng từ lần xét kế tiếp; hạng khách đang có giữ nguyên.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta

from cashback_bot import membership
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd

HOME = "c:mb:home"
WAIT = timedelta(minutes=10)
_EDIT = re.compile(r"^c:mb:e:([a-z_]{3,24})$")
_DEFAULT = re.compile(r"^c:mb:d:([a-z_]{3,24})$")
BACK = ((("◀️ Điều kiện lên hạng", HOME),),)
NAV = ((("◀️ Hạng thành viên", "c:menu:rank"),),)

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def show(key: str, value: int) -> str:
    return format_vnd(value) if membership.FIELDS[key][1] == "đ" else f"{value} {membership.FIELDS[key][1]}"


def history_line(before: dict, after: dict) -> str:
    """Dòng 📊 Lịch sử cho action `membership_thresholds`."""
    key = str(after.get("key", ""))
    if key not in membership.FIELDS:
        return f"Điều kiện lên hạng: {key}"
    old = show(key, int(before["value"])) if "value" in before else "-"
    return f"Điều kiện lên hạng: {membership.FIELDS[key][0]} {old} → {show(key, int(after['value']))}"


class MembershipAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None, waiting: dict | None = None,
                 enabled: bool = False):
        self.repo = repo
        self.audit = audit
        self.waiting = {} if waiting is None else waiting
        self.enabled = enabled

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if _EDIT.fullmatch(data) is None:
            self.waiting.pop(admin_id, None)
        if data == HOME:
            return self._home()
        if (found := _EDIT.fullmatch(data)) is not None and found.group(1) in membership.FIELDS:
            return self._ask(admin_id, found.group(1), now)
        if (found := _DEFAULT.fullmatch(data)) is not None and found.group(1) in membership.FIELDS:
            key = found.group(1)
            return self._save(admin_id, key, membership.DEFAULTS[key], now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def consume_text(self, admin_id: int, text: str, now: datetime) -> BotReply | None:
        entry = self.waiting.get(admin_id)
        if entry is None:
            return None
        key, deadline = entry
        stripped = (text or "").strip().replace(".", "").replace(",", "").removesuffix("đ").strip()
        if deadline <= now or stripped.startswith("/"):
            self.waiting.pop(admin_id, None)
            return None
        _label, unit, _default, low, high = membership.FIELDS[key]
        value = int(stripped) if stripped.isdigit() else None
        if value is None or not membership.valid(key, value):
            return BotReply(f"⚠️ Gõ một số từ {low:,} đến {high:,} ({unit}).".replace(",", "."), inline_keyboard=BACK)
        self.waiting.pop(admin_id, None)
        return self._save(admin_id, key, value, now)

    def _home(self, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            membership.ensure_schema(conn)
            values = membership.thresholds(conn)
            counts = membership.counts(conn)
        lines = ["⚙️ Quản trị › Hạng thành viên › <b>🎯 Điều kiện lên hạng</b>", ""]
        if notice:
            lines += [notice, ""]
        lines.append(f"• Trạng thái: <b>{'Đang chạy' if self.enabled else 'Chưa bật'}</b> "
                     "(cờ CASHBACK_MEMBERSHIP_ENABLED trong .env)")
        lines.append(f"• Khách đang ở 🥇 Vàng: <b>{counts.get('GOLD', 0)}</b> · 🥈 Bạc: <b>{counts.get('SILVER', 0)}</b> "
                     "· còn lại là 🥉 Đồng")
        lines.append("")
        lines.append("<b>Điều kiện</b> (đơn hoàn thành trong tháng trước + tháng này, đủ cả đơn và tiền):")
        for key, (label, _unit, default, _low, _high) in membership.FIELDS.items():
            mark = "" if values[key] == default else f" (mặc định {show(key, default)})"
            lines.append(f"• {label}: <b>{show(key, values[key])}</b>{mark}")
        lines += [
            "",
            "ⓘ Đủ điều kiện là lên ngay. Đầu tháng xét lại theo 2 tháng vừa qua, thiếu thì xuống một bậc; "
            f"ngày {membership.REMIND_DAY} nhắc khách sắp xuống hạng. Khách cũ giữ Vàng tới hết "
            f"{membership.GRANDFATHER_UNTIL_TEXT}.",
            "ⓘ Điều kiện mới dùng từ lần xét kế tiếp; hạng khách đang có không đổi ngay. "
            "Vàng phải không thấp hơn Bạc.",
        ]
        rows = [((f"✍️ {label}", f"c:mb:e:{key}"),) for key, (label, *_rest) in membership.FIELDS.items()]
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *NAV))

    def _ask(self, admin_id: int, key: str, now: datetime) -> BotReply:
        self.waiting[admin_id] = (key, now + WAIT)
        label, unit, default, low, high = membership.FIELDS[key]
        with self.repo.connect() as conn:
            current = membership.thresholds(conn)[key]
        return BotReply(
            f"✍️ <b>{label}</b>\n\n"
            f"Đang đặt: {show(key, current)} · mặc định {show(key, default)}.\n"
            f"Gõ số {unit}, từ {show(key, low)} đến {show(key, high)}.",
            inline_keyboard=(((f"↩️ Về mặc định ({show(key, default)})", f"c:mb:d:{key}"),), (("✖️ Hủy", HOME),)),
        )

    def _save(self, admin_id: int, key: str, value: int, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            stored = membership.custom(conn)
            before = membership.thresholds(conn)[key]
        merged = {**membership.DEFAULTS, **stored, key: value}
        if not membership.ordered(merged):
            return self._home("⚠️ Chưa lưu: điều kiện Vàng phải không thấp hơn Bạc (cả số đơn và tiền).")
        if value == membership.DEFAULTS[key]:
            stored.pop(key, None)
        else:
            stored[key] = value
        self.repo.set_state(membership.THRESHOLDS_KEY, json.dumps(stored, sort_keys=True))
        if self.audit is not None and before != value:
            self.audit(admin_id, "membership_thresholds", {"key": key, "value": before}, {"key": key, "value": value},
                       now)
        return self._home(f"✅ Đã lưu: {membership.FIELDS[key][0]} {show(key, value)}.")
