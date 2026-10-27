"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale (engagement.py): bật / tắt, lịch 45 ngày tới, xem trước và duyệt từng lượt.

Callback: c:eg:home · c:eg:on · c:eg:off · c:eg:nudge:on · c:eg:nudge:off · c:eg:v:<lượt> · c:eg:ok:<lượt> ·
c:eg:skip:<lượt> · c:eg:undo:<lượt>.
<lượt> = <ngày ISO>:<eve|day>. Ghi 📊 Lịch sử action `sale_reminder`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

from cashback_bot import engagement, sale_calendar
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import DORMANT_OPENER, BotReply
from cashback_bot.sale_calendar import ICT, TIER_LABELS

HOME = "c:eg:home"
_ACTION = re.compile(r"^c:eg:(v|ok|skip|undo):(\d{4}-\d{2}-\d{2}:(?:eve|day))$")
NAV = ((("◀️ Cài đặt", "c:menu:settings"), ("◀️ Tổng quan", "c:menu:home")),)
STAGES = {"eve": "tối hôm trước", "day": "trưa trong ngày"}

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    if "nudge" in after:
        return f"Nhắc link chưa dùng: {'bật' if after['nudge'] else 'tắt'}"
    if "enabled" in after:
        return f"Nhắc mùa sale: {'bật' if after['enabled'] else 'tắt'}"
    return f"Nhắc sale {after.get('slot', '-')}: {engagement.STATUS_LABELS.get(str(after.get('status')), '-')}"


def _when(slot: sale_calendar.Slot) -> str:
    return slot.at.astimezone(ICT).strftime("%H:%M %d/%m")


class EngagementAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home(now)
        if data in ("c:eg:on", "c:eg:off"):
            on = data == "c:eg:on"
            self.repo.set_state(engagement.ENABLED_KEY, "1" if on else "0")
            self._log(admin_id, {"enabled": not on}, {"enabled": on}, now)
            return self._home(now, "Đã bật nhắc mùa sale." if on else "Đã tắt nhắc mùa sale.")
        if data in ("c:eg:nudge:on", "c:eg:nudge:off"):
            on = data.endswith(":on")
            self.repo.set_state(engagement.NUDGE_KEY, "1" if on else "0")
            self._log(admin_id, {"nudge": not on}, {"nudge": on}, now)
            return self._home(now, "Đã bật nhắc link chưa dùng." if on else "Đã tắt nhắc link chưa dùng.")
        found = _ACTION.fullmatch(data)
        slot = sale_calendar.find(found.group(2)) if found else None
        if slot is None:
            return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)
        action = found.group(1)
        if action == "v":
            return self._preview(slot, now)
        current = engagement.record(self.repo, slot.id)
        if current.get("status") in ("sent", "missed") or now >= slot.at:
            return self._preview(slot, now, "Lượt này đã qua giờ gửi, không đổi được nữa.")
        state = {"ok": "approved", "skip": "skipped", "undo": "pending"}[action]
        updated = {**current, "status": state, "by": admin_id, "at": now.astimezone(timezone.utc).isoformat()}
        engagement.save(self.repo, slot.id, updated)
        self._log(admin_id, {"slot": slot.id, "status": current.get("status", "pending")},
                  {"slot": slot.id, "status": state}, now)
        notice = {"approved": "✅ Đã duyệt. Bot gửi đúng giờ.", "skipped": "⏭ Đã bỏ qua lượt này.",
                  "pending": "↩️ Đã huỷ duyệt. Lượt này sẽ không gửi nếu không duyệt lại."}[state]
        return self._preview(slot, now, notice)

    def _log(self, admin_id: int, before: dict, after: dict, now: datetime) -> None:
        if self.audit is not None:
            self.audit(admin_id, "sale_reminder", before, after, now)

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        on = engagement.enabled(self.repo)
        nudge_on = engagement.nudge_enabled(self.repo)
        with self.repo.connect() as conn:
            count = len(engagement.recipients(conn))
            sleepy = len(engagement.dormant_users(conn, now) & set(engagement.recipients(conn)))
            nudged = engagement.nudge_stats(conn, now)
        lines = ["📣 <b>Nhắc mùa sale</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Trạng thái: {'🟢 Đang bật' if on else '⚪ Đang tắt'} · {count} khách sẽ nhận (đã tạo link, chưa tắt nhắc)",
            "Lịch cố định: ngày đôi, siêu sale 9.9 · 10.10 · Black Friday, mini 15 · 25. Nhắc 20:30 tối hôm trước;",
            "11.11 và 12.12 thêm 11:30 trong ngày. Dịp nhỏ sát dịp lớn (dưới 5 ngày) thì bỏ.",
            "Mỗi lượt <b>phải bấm duyệt</b> mới gửi. Bot báo anh trước giờ gửi 48 giờ.",
            f"👋 {sleepy} khách lâu không dùng (trên 21 ngày) nhận thêm câu «Lâu rồi hông thấy bạn ghé nè!».",
            "",
            f"<b>👀 Nhắc link chưa dùng</b>: {'🟢 Đang bật' if nudge_on else '⚪ Đang tắt'} · 7 ngày qua: "
            f"{nudged[0]} tin ({nudged[1]} đã gửi)",
            "Tự gửi theo luật, không duyệt từng tin: link mới nhất có hoàn, 24–72 giờ chưa có đơn; 19:00–21:30;",
            "mỗi khách tối đa 1 tin / 7 ngày; nhường ngày có nhắc sale.",
            "",
            "<b>45 ngày tới</b>",
        ]
        slots = sale_calendar.upcoming(now)
        rows = []
        for slot in slots:
            state = engagement.status(self.repo, slot)
            lines.append(f"• {_when(slot)} · {slot.event.label} ({TIER_LABELS[slot.event.tier]}, {STAGES[slot.stage]})"
                         f" · {engagement.STATUS_LABELS[state]}")
            rows.append(((f"👁 {slot.event.label} · {_when(slot)}", f"c:eg:v:{slot.id}"),))
        if not slots:
            lines.append("Không có dịp nào.")
        toggle = ("⚪ Tắt nhắc mùa sale", "c:eg:off") if on else ("🟢 Bật nhắc mùa sale", "c:eg:on")
        nudge = ("⚪ Tắt nhắc link", "c:eg:nudge:off") if nudge_on else ("🟢 Bật nhắc link", "c:eg:nudge:on")
        return BotReply("\n".join(lines), inline_keyboard=((toggle, nudge), *rows[:8], *NAV))

    def _preview(self, slot: sale_calendar.Slot, now: datetime, notice: str = "") -> BotReply:
        state = engagement.status(self.repo, slot)
        with self.repo.connect() as conn:
            count = len(engagement.recipients(conn))
        lines = [f"📣 <b>Nhắc sale {slot.event.label}</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Gửi lúc {_when(slot)} · {count} khách · {engagement.STATUS_LABELS[state]}",
            "" if engagement.enabled(self.repo) else "⚪ Nhắc mùa sale đang tắt: đã duyệt cũng chưa gửi.",
            "<b>Khách sẽ nhận:</b>",
            f"<blockquote>{engagement.text_for(slot)}</blockquote>",
            "Khách lâu không dùng (trên 21 ngày) có thêm dòng đầu: " + DORMANT_OPENER,
        ]
        buttons = []
        if now < slot.at and state not in ("sent", "missed"):
            if state == "approved":
                buttons.append((("↩️ Huỷ duyệt", f"c:eg:undo:{slot.id}"),))
            else:
                buttons.append((("✅ Duyệt gửi", f"c:eg:ok:{slot.id}"), ("⏭ Bỏ qua", f"c:eg:skip:{slot.id}")))
        buttons.append((("◀️ Nhắc mùa sale", HOME),))
        return BotReply("\n".join(lines), inline_keyboard=(*buttons, *NAV))

