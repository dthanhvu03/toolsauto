"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale (engagement.py): bật / tắt, lịch 45 ngày tới, xem trước và duyệt từng lượt.

Callback: c:eg:home · c:eg:on · c:eg:off · c:eg:nudge:on|off · c:eg:drop:on|off · c:eg:v:<lượt> · c:eg:ok:<lượt> ·
c:eg:skip:<lượt> · c:eg:undo:<lượt> · 🎟 Báo mã (PLAN-104): c:eg:vc:home · c:eg:vc:on|off · c:eg:vc:bind:<kênh> ·
c:eg:vc:unbind · c:eg:vc:all|test (gửi khách / chỉ admin).
<lượt> = <ngày ISO>:<eve|day>. Ghi 📊 Lịch sử action `sale_reminder`.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import datetime, timezone

from cashback_bot import engagement, price_watch, sale_calendar, voucher, watchlist
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import DORMANT_OPENER, BotReply
from cashback_bot.sale_calendar import ICT, TIER_LABELS

HOME = "c:eg:home"
VOUCHER_HOME = "c:eg:vc:home"
_ACTION = re.compile(r"^c:eg:(v|ok|skip|undo):(\d{4}-\d{2}-\d{2}:(?:eve|day))$")
NAV = ((("◀️ Cài đặt", "c:menu:settings"), ("◀️ Tổng quan", "c:menu:home")),)
STAGES = {"eve": "tối hôm trước", "day": "trưa trong ngày"}

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    if "voucher_channel" in after:
        channel = after["voucher_channel"]
        return f"Báo mã: {'gắn kênh ' + str(after.get('title') or channel) if channel else 'gỡ kênh'}"
    if "voucher_audience" in after:
        return f"Báo mã: {'gửi mọi khách' if after['voucher_audience'] == 'all' else 'chế độ thử, chỉ admin'}"
    if "voucher" in after:
        return f"Báo mã giảm giá: {'bật' if after['voucher'] else 'tắt'}"
    if "drop" in after:
        return f"Báo giảm giá món khách từng xem: {'bật' if after['drop'] else 'tắt'}"
    if "nudge" in after:
        return f"Nhắc link chưa dùng: {'bật' if after['nudge'] else 'tắt'}"
    if "enabled" in after:
        return f"Nhắc mùa sale: {'bật' if after['enabled'] else 'tắt'}"
    return f"Nhắc sale {after.get('slot', '-')}: {engagement.STATUS_LABELS.get(str(after.get('status')), '-')}"


def _watch_scan(repo) -> str:
    record = watchlist.scan_record(repo)
    if not record:
        return "chưa chạy lượt nào"
    hour = str(record.get("hour") or "")[-2:]
    if record.get("status") == "error":
        return f"lượt {hour}h: 🔴 lỗi {record.get('error')}"
    return f"lượt {hour}h: kiểm {record.get('checked', 0)} món, {record.get('sent', 0)} tin"


def _clock(stamp: str | None) -> str:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(ICT).strftime("%H:%M %d/%m")
    except ValueError:
        return "-"


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
        if data in ("c:eg:drop:on", "c:eg:drop:off"):
            on = data.endswith(":on")
            self.repo.set_state(price_watch.ENABLED_KEY, "1" if on else "0")
            self._log(admin_id, {"drop": not on}, {"drop": on}, now)
            return self._home(now, "Đã bật báo giảm giá." if on else "Đã tắt báo giảm giá.")
        if data.startswith("c:eg:vc:"):
            return self._voucher(admin_id, data, now)
        if data in ("c:eg:pw:on", "c:eg:pw:off"):
            on = data.endswith(":on")
            self.repo.set_state(watchlist.ENABLED_KEY, "1" if on else "0")
            self._log(admin_id, {"price_watch_list": not on}, {"price_watch_list": on}, now)
            return self._home(now, "Đã bật theo dõi giá." if on else "Đã tắt theo dõi giá.")
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
        drop_on = price_watch.enabled(self.repo)
        drop_last = price_watch.last_result_text(self.repo)
        watch_on = watchlist.enabled(self.repo)
        with self.repo.connect() as conn:
            watching, watch_sent = watchlist.stats(conn, now)
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
            f"<b>📉 Báo giảm giá món khách từng xem</b>: {'🟢 Đang bật' if drop_on else '⚪ Đang tắt'} · {drop_last}",
            "Mỗi tối 19:00–21:30 kiểm giá món đã tạo link 30 ngày, chưa mua; giảm từ 15% và còn hàng thì nhắn.",
            "Dùng chung giới hạn 1 tin / 7 ngày với nhắc link.",
            "",
            f"<b>🔔 Theo dõi giá</b>: {'🟢 Đang bật' if watch_on else '⚪ Đang tắt'} · {watching} món đang theo dõi · "
            f"7 ngày qua: {watch_sent} tin · {_watch_scan(self.repo)}",
            "Khách bấm 🔔 trên thẻ link; có giảm là bot nhắn. Mặc định kiểm mỗi giờ 7:00–21:00, khách đặt được giờ riêng.",
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
        drop = ("⚪ Tắt báo giảm giá", "c:eg:drop:off") if drop_on else ("🟢 Bật báo giảm giá", "c:eg:drop:on")
        watch = ("⚪ Tắt theo dõi giá", "c:eg:pw:off") if watch_on else ("🟢 Bật theo dõi giá", "c:eg:pw:on")
        return BotReply("\n".join(lines), inline_keyboard=((toggle, nudge), (drop, watch), (("🔥 Deal hời", "c:dl:home"),
                                                           ("🎟 Báo mã", VOUCHER_HOME)),
                                                           (("📣 Tin giới thiệu", "c:an:home"),), *rows[:8], *NAV))

    def _voucher(self, admin_id: int, data: str, now: datetime, notice: str = "") -> BotReply:
        """🎟 Báo mã giảm giá (voucher.py): gắn kênh trung gian, bật / tắt, số liệu."""
        if data in ("c:eg:vc:on", "c:eg:vc:off"):
            on = data.endswith(":on")
            self.repo.set_state(voucher.ENABLED_KEY, "1" if on else "0")
            self._log(admin_id, {"voucher": not on}, {"voucher": on}, now)
            notice = "Đã bật báo mã." if on else "Đã tắt báo mã."
        elif data.startswith("c:eg:vc:bind:"):
            seen = voucher.seen_channel(self.repo)
            if str(seen.get("id")) != data.removeprefix("c:eg:vc:bind:"):
                notice = "Nút này không còn hiệu lực, mở lại màn Báo mã."
            else:
                self.repo.set_state(voucher.CHANNEL_KEY, str(seen["id"]))
                self._log(admin_id, {"voucher_channel": None},
                          {"voucher_channel": seen["id"], "title": seen.get("title")}, now)
                notice = "✅ Đã gắn kênh. Tin AddLiveTag trong kênh này sẽ được gửi cho khách đã bật."
        elif data in ("c:eg:vc:all", "c:eg:vc:test"):
            live = data.endswith(":all")
            self.repo.set_state(voucher.AUDIENCE_KEY, "all" if live else "test")
            self._log(admin_id, {"voucher_audience": "test" if live else "all"},
                      {"voucher_audience": "all" if live else "test"}, now)
            notice = ("📣 Đã bật gửi khách: bot nhắn mọi khách đã tạo link, theo giờ yên lặng và trần mỗi ngày." if live else
                      "🧪 Đã về chế độ thử: tin báo mã chỉ gửi admin.")
        elif data == "c:eg:vc:unbind":
            old = voucher.channel(self.repo)
            self.repo.set_state(voucher.CHANNEL_KEY, "")
            self._log(admin_id, {"voucher_channel": old}, {"voucher_channel": None}, now)
            notice = "Đã gỡ kênh. Bot không đọc tin kênh nào nữa."
        on, bound, seen = voucher.enabled(self.repo), voucher.channel(self.repo), voucher.seen_channel(self.repo)
        live = voucher.to_customers(self.repo)
        with self.repo.connect() as conn:
            numbers = voucher.stats(conn, now)
            waiting = voucher.queued(conn)
        skipped = self.repo.get_state(voucher.SKIPPED_KEY) or "0"
        lines = ["🎟 <b>Báo mã giảm giá</b>", ""]
        if notice:
            lines += [notice, ""]
        last = numbers["last"]
        lines += [
            f"Trạng thái: {'🟢 Đang bật' if on else '⚪ Đang tắt'}",
            ("Người nhận: 📣 <b>mọi khách</b> đã tạo link, chưa tắt báo mã: " + str(numbers["on"]) + " khách" if live else
             f"Người nhận: 🧪 <b>chỉ admin</b> (chế độ thử). Bật gửi khách thì {numbers['on']} khách sẽ nhận."),
            f"Kênh: {'đã gắn (' + str(bound) + ')' if bound else '⚪ chưa gắn'}",
            f"7 ngày qua: {numbers['posts']} tin mã · {numbers['sent']} tin gửi khách · tin không đọc được: {skipped}",
            f"Mã gần nhất: {html.escape(last[0])} lúc {_clock(last[1])}" if last else "Chưa nhận mã nào.",
            *([f"Đang chờ gửi khách: {waiting} mã"] if live else []),
            "",
            "AddLiveTag Theo dõi Voucher gửi tin vào kênh Telegram riêng tư bằng <b>bot chuyển tin</b> (bot riêng, "
            "không dùng token bot hoàn tiền). Bot hoàn tiền là quản trị kênh, đọc tin rồi gửi cho mọi khách đã tạo link.",
            f"⏰ Khách không nhận tin {voucher.QUIET_FROM}h–{voucher.QUIET_TO}h (8h sáng gửi gộp các mã còn). Mã đến gần "
            f"nhau gộp một tin, một mã không gửi lại trong 24 giờ, tối đa {voucher.DAILY_MAX} tin mỗi ngày. "
            "Admin nhận ngay mọi giờ.",
            "Khách không muốn nhận thì bấm 🔕 Tắt báo mã hoặc vào /magiam.",
        ]
        rows = []
        if seen and seen["id"] != bound:
            lines += ["", f"Kênh vừa đăng tin: <b>{html.escape(str(seen.get('title') or seen['id']))}</b> lúc "
                          f"{_clock(seen.get('at'))}"]
            rows.append(((f"✅ Dùng kênh «{str(seen.get('title') or seen['id'])[:30]}»", f"c:eg:vc:bind:{seen['id']}"),))
        elif not bound:
            lines += ["", "Chưa thấy kênh nào: thêm bot hoàn tiền làm quản trị kênh rồi đăng một tin bất kỳ vào kênh."]
        if bound:
            rows.append((("Gỡ kênh", "c:eg:vc:unbind"),))
        rows.append(((("🧪 Về chế độ thử (chỉ admin)", "c:eg:vc:test") if live else
                      ("📣 Bật gửi khách", "c:eg:vc:all")),))
        rows.append(((("⚪ Tắt báo mã", "c:eg:vc:off") if on else ("🟢 Bật báo mã", "c:eg:vc:on")),))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, (("◀️ Nhắc mùa sale", HOME),), *NAV))

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

