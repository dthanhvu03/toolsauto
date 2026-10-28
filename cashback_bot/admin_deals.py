"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời (deals.py, PLAN-100): bật / tắt, lượt quét gần nhất, món đang
hời trong kho, bỏ món.

Callback: c:dl:home · c:dl:on · c:dl:off · c:dl:infer:on|off · c:dl:rm:<item> · c:dl:back:<item>. Nút lượt trưa / tối
cũ (c:dl:noon:*, c:dl:skip*, c:dl:rm:<lượt>:<item>) trả «không còn hiệu lực». Ghi 📊 Lịch sử action `deals`.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import datetime

from cashback_bot import deals
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.money import format_vnd

HOME = "c:dl:home"
_ITEM = re.compile(r"^c:dl:(rm|back):(\d+)$")
NAV = ((("◀️ Nhắc mùa sale", "c:eg:home"), ("◀️ Tổng quan", "c:menu:home")),)
MAX_BUTTONS = 15

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    if "infer" in after:
        return f"Deal hời cho khách chưa chọn (bot đoán gu): {'bật' if after['infer'] else 'tắt'}"
    if "noon" in after:
        return f"Deal hời lượt trưa 12:08: {'bật' if after['noon'] else 'tắt'}"
    if "enabled" in after:
        return f"Deal hời: {'bật' if after['enabled'] else 'tắt'}"
    when = after.get("day", "") + (" trưa" if after.get("slot") == "trua" else "")
    if "item" in after:
        verb = "bỏ món" if after.get("removed") else "lấy lại món"
        return f"Deal hời{' ' + when if when else ''}: {verb} {after['item']}"
    return f"Deal hời {when or '-'}: {deals.STATUS_LABELS.get(str(after.get('status')), '-')}"


class DealsAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def _log(self, admin_id: int, before: dict, after: dict, now: datetime) -> None:
        if self.audit is not None:
            self.audit(admin_id, "deals", before, after, now)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data in ("c:dl:on", "c:dl:off"):
            on = data == "c:dl:on"
            self.repo.set_state(deals.ENABLED_KEY, "1" if on else "0")
            self._log(admin_id, {"enabled": not on}, {"enabled": on}, now)
            return self._home(now, "Đã bật deal hời." if on else "Đã tắt deal hời.")
        if data in ("c:dl:infer:on", "c:dl:infer:off"):
            on = data.endswith(":on")
            self.repo.set_state(deals.INFER_KEY, "1" if on else "0")
            self._log(admin_id, {"infer": not on}, {"infer": on}, now)
            return self._home(now, "Đã bật gửi cho khách chưa chọn." if on else "Đã tắt gửi cho khách chưa chọn.")
        found = _ITEM.fullmatch(data)
        if found:
            item, removed = int(found.group(2)), found.group(1) == "rm"
            deals.set_removed(self.repo, item, removed)
            self._log(admin_id, {}, {"item": item, "removed": removed}, now)
            return self._home(now)
        if data == HOME:
            return self._home(now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        on = deals.enabled(self.repo)
        infer_on = deals.infer_enabled(self.repo)
        with self.repo.connect() as conn:
            people = deals.subscribers(conn, now)
            guessed = deals.inferred(conn, now)
            sent_today = conn.execute("SELECT COUNT(*), COUNT(DISTINCT chat_id) FROM admin_notifications "
                                      "WHERE event_type = 'DEALS' AND created_at >= ?",
                                      (deals._today_start(now),)).fetchone()
        per_cat = {key: sum(key in cats for cats in people.values()) for key in deals.CATEGORIES}
        lines = ["🔥 <b>Deal hời tự động</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Trạng thái: {'🟢 Đang bật' if on else '⚪ Đang tắt'} · {len(people)} khách đã chọn danh mục",
            f"Quét mỗi giờ {deals.SCAN_HOURS.start}:00–{deals.SCAN_HOURS.stop - 1}:00, đủ 10 danh mục. Có món mới hời "
            f"thật là tự gửi khách hợp danh mục: 1–{deals.PER_MESSAGE} món / tin, mỗi khách tối đa {deals.DAILY_MAX} "
            f"tin / ngày, cách nhau ≥ 2 giờ, chỉ {deals.SEND_FROM:%H:%M}–{deals.SEND_UNTIL:%H:%M}. Không lặp món đã "
            "gửi khách đó trong 3 ngày. Có tin nhắc sale trong 3 giờ thì nhường.",
            "Chuẩn: món bán chạy, đánh giá ≥ 4,5, giá hôm nay thấp nhất 30 ngày và rẻ hơn thường ngày ≥ 10%.",
            "",
            "Khách theo danh mục: " + (" · ".join(f"{deals.CATEGORIES[k][0]} {n}" for k, n in per_cat.items() if n)
                                      or "chưa ai chọn"),
            f"🤖 Khách chưa chọn, bot đoán gu: {'🟢 bật' if infer_on else '⚪ tắt'} · lúc này đủ điều kiện "
            f"{len(guessed)} khách (tối đa 2 tin / tuần, món rẻ ≥ 12%, 3 món, nhận 3 tin không tạo link thì dừng)",
            "",
            self._scan_line(),
            f"📤 Hôm nay đã gửi {sent_today[0]} tin cho {sent_today[1]} khách.",
        ]
        current, _latest = deals.current_deals(self.repo, now, deals.FEED_FRESH)
        removed = deals.removed_items(self.repo)
        shown = [d for d in deals.pool(self.repo).values() if d["item_id"] in removed]
        buttons = []
        if current or shown:
            lines += ["", "<b>Món đang hời</b> (12 giờ qua). ❌ Bỏ thì không gửi, không hiện ở 🔥 Deal hôm nay."]
        for key, rows in current.items():
            lines.append(f"<b>{deals.CATEGORIES[key][0]}</b>")
            for deal in rows:
                lines.append(f"• {html.escape(deals._short(deal['name']))}: {format_vnd(deal['price'])} "
                             f"(thường {format_vnd(deal['usual'])}, "
                             f"−{round((deal['usual'] - deal['price']) * 100 / deal['usual'])}%)"
                             f" · ⭐{deal['rating']} · hoàn {format_vnd(deal['cashback'])}")
                if len(buttons) < MAX_BUTTONS:
                    buttons.append(((f"❌ Bỏ {deals._short(deal['name'], 26)}", f"c:dl:rm:{deal['item_id']}"),))
        for deal in shown:
            lines.append(f"❌ {html.escape(deals._short(deal['name']))} (đã bỏ)")
            if len(buttons) < MAX_BUTTONS:
                buttons.append(((f"↩️ Lấy lại {deals._short(deal['name'], 22)}", f"c:dl:back:{deal['item_id']}"),))
        toggle = ("⚪ Tắt deal hời", "c:dl:off") if on else ("🟢 Bật deal hời", "c:dl:on")
        infer = ("⚪ Tắt đoán gu", "c:dl:infer:off") if infer_on else ("🤖 Bật đoán gu", "c:dl:infer:on")
        return BotReply("\n".join(lines), inline_keyboard=((toggle, infer), *buttons, *NAV))

    def _scan_line(self) -> str:
        scan = deals.scan_record(self.repo)
        if not scan:
            return "🔎 Chưa quét lượt nào."
        label = deals.STATUS_LABELS.get(str(scan.get("status")), "-")
        line = f"🔎 Lượt quét gần nhất {deals._clock(scan.get('at'))}: {label}"
        if scan.get("status") == "done":
            line += f" · {scan.get('found', 0)} món hời · {scan.get('new', 0)} món mới · gửi {scan.get('sent', 0)} tin"
        elif scan.get("status") == "error":
            line += f" ({html.escape(str(scan.get('error') or ''))}), giờ sau quét lại"
        return line
