"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời (deals.py): bật / tắt, xem trước deal hôm nay, bỏ ngày, bỏ món.

Callback: c:dl:home · c:dl:on · c:dl:off · c:dl:infer:on|off · c:dl:skip · c:dl:unskip · c:dl:rm:<item> ·
c:dl:back:<item>.
Ghi 📊 Lịch sử action `deals`.
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
from cashback_bot.sale_calendar import ICT

HOME = "c:dl:home"
_ITEM = re.compile(r"^c:dl:(rm|back):(\d+)$")
NAV = ((("◀️ Nhắc mùa sale", "c:eg:home"), ("◀️ Tổng quan", "c:menu:home")),)
MAX_BUTTONS = 15

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    if "infer" in after:
        return f"Deal hời cho khách chưa chọn (bot đoán gu): {'bật' if after['infer'] else 'tắt'}"
    if "enabled" in after:
        return f"Deal hời: {'bật' if after['enabled'] else 'tắt'}"
    if "item" in after:
        verb = "bỏ món" if after.get("removed") else "lấy lại món"
        return f"Deal hời {after.get('day', '-')}: {verb} {after['item']}"
    return f"Deal hời {after.get('day', '-')}: {deals.STATUS_LABELS.get(str(after.get('status')), '-')}"


class DealsAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def _log(self, admin_id: int, before: dict, after: dict, now: datetime) -> None:
        if self.audit is not None:
            self.audit(admin_id, "deals", before, after, now)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        day = now.astimezone(ICT).date().isoformat()
        current = deals.record(self.repo, day)
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
        if data in ("c:dl:skip", "c:dl:unskip"):
            if current.get("status") not in ("draft", "skipped"):
                return self._home(now, "Hôm nay chưa có bản deal để bỏ, hoặc đã gửi rồi.")
            status = "skipped" if data == "c:dl:skip" else "draft"
            deals.save(self.repo, day, {**current, "status": status})
            self._log(admin_id, {"day": day, "status": current.get("status")}, {"day": day, "status": status}, now)
            return self._home(now, "⏭ Hôm nay không gửi deal." if status == "skipped" else "↩️ Gửi lại như lịch 20:08.")
        found = _ITEM.fullmatch(data)
        if found:
            item = int(found.group(2))
            if current.get("status") not in ("draft", "skipped"):
                return self._home(now, "Bản deal hôm nay không còn sửa được.")
            removed = set(current.get("removed") or [])
            removed = removed | {item} if found.group(1) == "rm" else removed - {item}
            deals.save(self.repo, day, {**current, "removed": sorted(removed)})
            self._log(admin_id, {}, {"day": day, "item": item, "removed": found.group(1) == "rm"}, now)
            return self._home(now)
        if data == HOME:
            return self._home(now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        day = now.astimezone(ICT).date().isoformat()
        data = deals.record(self.repo, day)
        on = deals.enabled(self.repo)
        infer_on = deals.infer_enabled(self.repo)
        with self.repo.connect() as conn:
            people = deals.subscribers(conn, now)
            guessed = deals.inferred(conn, now)
        per_cat = {key: sum(key in cats for cats in people.values()) for key in deals.CATEGORIES}
        lines = ["🔥 <b>Deal hời theo danh mục</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Trạng thái: {'🟢 Đang bật' if on else '⚪ Đang tắt'} · {len(people)} khách đã chọn danh mục",
            "17:30 soạn (món bán chạy, đánh giá ≥ 4,5, giá hôm nay thấp nhất 30 ngày và rẻ hơn thường ngày ≥ 10%);",
            "20:08 tự gửi, mỗi khách tối đa 5 món theo danh mục đã chọn. Anh bỏ được cả ngày hoặc từng món trước giờ gửi.",
            "",
            "Khách theo danh mục: " + (" · ".join(f"{deals.CATEGORIES[k][0]} {n}" for k, n in per_cat.items() if n)
                                      or "chưa ai chọn"),
            f"🤖 Khách chưa chọn, bot đoán gu: {'🟢 bật' if infer_on else '⚪ tắt'} · tối nay đủ điều kiện "
            f"{len(guessed)} khách (tối đa 2 tin / tuần, món rẻ ≥ 12%, 3 món, nhận 3 tin không tạo link thì dừng)",
            "",
            f"<b>Hôm nay {day[8:]}/{day[5:7]}</b>: {deals.STATUS_LABELS.get(str(data.get('status')), '⏳ Chưa soạn (17:30)')}"
            + (f" · {data['sent']} tin" if data.get("status") == "sent" else ""),
        ]
        removed = set(data.get("removed") or [])
        buttons = []
        for key, rows in (data.get("deals") or {}).items():
            if not rows:
                continue
            lines.append(f"<b>{deals.CATEGORIES[key][0]}</b>")
            for deal in rows:
                mark = "❌ " if deal["item_id"] in removed else "• "
                lines.append(f"{mark}{html.escape(deals._short(deal['name']))}: {format_vnd(deal['price'])} "
                             f"(thường {format_vnd(deal['usual'])}, −{round((deal['usual'] - deal['price']) * 100 / deal['usual'])}%)"
                             f" · ⭐{deal['rating']} · hoàn {format_vnd(deal['cashback'])}")
                if data.get("status") in ("draft", "skipped") and len(buttons) < MAX_BUTTONS:
                    verb, code = ("↩️ Lấy lại", "back") if deal["item_id"] in removed else ("❌ Bỏ", "rm")
                    buttons.append(((f"{verb} {deals._short(deal['name'], 26)}", f"c:dl:{code}:{deal['item_id']}"),))
        toggle = ("⚪ Tắt deal hời", "c:dl:off") if on else ("🟢 Bật deal hời", "c:dl:on")
        infer = ("⚪ Tắt đoán gu", "c:dl:infer:off") if infer_on else ("🤖 Bật đoán gu", "c:dl:infer:on")
        rows = [(toggle, infer)]
        if data.get("status") == "draft":
            rows.append((("⏭ Bỏ hôm nay", "c:dl:skip"),))
        elif data.get("status") == "skipped":
            rows.append((("↩️ Gửi lại như lịch", "c:dl:unskip"),))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *buttons, *NAV))
