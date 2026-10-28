"""/admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời (deals.py): bật / tắt, xem trước deal hôm nay (trưa và tối),
bỏ lượt, bỏ món.

Callback: c:dl:home · c:dl:on · c:dl:off · c:dl:infer:on|off · c:dl:noon:on|off · c:dl:skip[:<lượt>] ·
c:dl:unskip[:<lượt>] · c:dl:rm[:<lượt>]:<item> · c:dl:back[:<lượt>]:<item>. Lượt: trua · toi (thiếu là toi, nút cũ).
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
_ITEM = re.compile(r"^c:dl:(rm|back):(?:(trua|toi):)?(\d+)$")
_SKIP = re.compile(r"^c:dl:(skip|unskip)(?::(trua|toi))?$")
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
    when = after.get("day", "-") + (" trưa" if after.get("slot") == "trua" else "")
    if "item" in after:
        verb = "bỏ món" if after.get("removed") else "lấy lại món"
        return f"Deal hời {when}: {verb} {after['item']}"
    return f"Deal hời {when}: {deals.STATUS_LABELS.get(str(after.get('status')), '-')}"


class DealsAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None):
        self.repo = repo
        self.audit = audit

    def _log(self, admin_id: int, before: dict, after: dict, now: datetime) -> None:
        if self.audit is not None:
            self.audit(admin_id, "deals", before, after, now)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        day = now.astimezone(ICT).date().isoformat()
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
        if data in ("c:dl:noon:on", "c:dl:noon:off"):
            on = data.endswith(":on")
            self.repo.set_state(deals.NOON_KEY, "1" if on else "0")
            self._log(admin_id, {"noon": not on}, {"noon": on}, now)
            return self._home(now, "Đã bật lượt trưa 12:08." if on else "Đã tắt lượt trưa, chỉ gửi tối 20:08.")
        found = _SKIP.fullmatch(data)
        if found:
            slot = deals.SLOT_BY_KEY[found.group(2) or "toi"]
            current = deals.record(self.repo, day, slot)
            if current.get("status") not in ("draft", "skipped"):
                return self._home(now, "Lượt này chưa có bản deal để bỏ, hoặc đã gửi rồi.")
            status = "skipped" if found.group(1) == "skip" else "draft"
            deals.save(self.repo, day, {**current, "status": status}, slot)
            self._log(admin_id, {"day": day, "slot": slot.key, "status": current.get("status")},
                      {"day": day, "slot": slot.key, "status": status}, now)
            return self._home(now, f"⏭ {slot.label} nay không gửi deal." if status == "skipped"
                              else f"↩️ {slot.label}: gửi lại như lịch {slot.send_text}.")
        found = _ITEM.fullmatch(data)
        if found:
            slot = deals.SLOT_BY_KEY[found.group(2) or "toi"]
            current = deals.record(self.repo, day, slot)
            item = int(found.group(3))
            if current.get("status") not in ("draft", "skipped"):
                return self._home(now, "Bản deal lượt này không còn sửa được.")
            removed = set(current.get("removed") or [])
            removed = removed | {item} if found.group(1) == "rm" else removed - {item}
            deals.save(self.repo, day, {**current, "removed": sorted(removed)}, slot)
            self._log(admin_id, {}, {"day": day, "slot": slot.key, "item": item, "removed": found.group(1) == "rm"},
                      now)
            return self._home(now)
        if data == HOME:
            return self._home(now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        day = now.astimezone(ICT).date().isoformat()
        on = deals.enabled(self.repo)
        infer_on = deals.infer_enabled(self.repo)
        noon_on = deals.noon_enabled(self.repo)
        with self.repo.connect() as conn:
            people = deals.subscribers(conn, now)
            guessed = deals.inferred(conn, now)
        per_cat = {key: sum(key in cats for cats in people.values()) for key in deals.CATEGORIES}
        lines = ["🔥 <b>Deal hời theo danh mục</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"Trạng thái: {'🟢 Đang bật' if on else '⚪ Đang tắt'} · {len(people)} khách đã chọn danh mục",
            f"Mỗi ngày: 🍱 trưa soạn 10:30, gửi 12:08 ({'🟢 bật' if noon_on else '⚪ tắt'}) · 🌙 tối soạn 17:30, "
            "gửi 20:08. Mỗi lượt tìm bộ từ khoá khác nhau.",
            "Chuẩn: món bán chạy, đánh giá ≥ 4,5, giá hôm nay thấp nhất 30 ngày và rẻ hơn thường ngày ≥ 10%. Mỗi khách "
            "tối đa 5 món / lượt, không lặp món đã gửi khách đó trong 3 ngày; hết món mới thì lượt đó không gửi khách ấy.",
            "Anh bỏ được cả lượt hoặc từng món trước giờ gửi.",
            "",
            "Khách theo danh mục: " + (" · ".join(f"{deals.CATEGORIES[k][0]} {n}" for k, n in per_cat.items() if n)
                                      or "chưa ai chọn"),
            f"🤖 Khách chưa chọn, bot đoán gu: {'🟢 bật' if infer_on else '⚪ tắt'} · lượt tới đủ điều kiện "
            f"{len(guessed)} khách (tối đa 2 tin / tuần, món rẻ ≥ 12%, 3 món, nhận 3 tin không tạo link thì dừng)",
            "",
            f"<b>Hôm nay {day[8:]}/{day[5:7]}</b>",
        ]
        buttons, skips = [], []
        for slot in deals.SLOTS:
            data = deals.record(self.repo, day, slot)
            status = data.get("status")
            if slot is deals.NOON and not noon_on and status is None:
                lines.append(f"{slot.label}: ⚪ Lượt trưa đang tắt")
                continue
            label = deals.STATUS_LABELS.get(str(status), f"⏳ Chưa soạn ({slot.build_at:%H:%M})")
            if status == "draft":
                label = f"📝 Chờ {slot.send_text}"
            lines.append(f"<b>{slot.label} {slot.send_text}</b>: {label}"
                         + (f" · {data['sent']} tin" if status == "sent" else ""))
            removed = set(data.get("removed") or [])
            editable = status in ("draft", "skipped")
            for key, rows in (data.get("deals") or {}).items():
                if not rows:
                    continue
                lines.append(f"<b>{deals.CATEGORIES[key][0]}</b>")
                for deal in rows:
                    mark = "❌ " if deal["item_id"] in removed else "• "
                    lines.append(f"{mark}{html.escape(deals._short(deal['name']))}: {format_vnd(deal['price'])} "
                                 f"(thường {format_vnd(deal['usual'])}, "
                                 f"−{round((deal['usual'] - deal['price']) * 100 / deal['usual'])}%)"
                                 f" · ⭐{deal['rating']} · hoàn {format_vnd(deal['cashback'])}")
                    if editable and len(buttons) < MAX_BUTTONS:
                        verb, code = ("↩️ Lấy lại", "back") if deal["item_id"] in removed else ("❌ Bỏ", "rm")
                        buttons.append(((f"{slot.label[0]} {verb} {deals._short(deal['name'], 24)}",
                                         f"c:dl:{code}:{slot.key}:{deal['item_id']}"),))
            if status == "draft":
                skips.append((f"⏭ Bỏ lượt {slot.label.split()[-1].lower()}", f"c:dl:skip:{slot.key}"))
            elif status == "skipped":
                skips.append((f"↩️ Gửi lại lượt {slot.label.split()[-1].lower()}", f"c:dl:unskip:{slot.key}"))
        toggle = ("⚪ Tắt deal hời", "c:dl:off") if on else ("🟢 Bật deal hời", "c:dl:on")
        infer = ("⚪ Tắt đoán gu", "c:dl:infer:off") if infer_on else ("🤖 Bật đoán gu", "c:dl:infer:on")
        noon = ("⚪ Tắt lượt trưa", "c:dl:noon:off") if noon_on else ("🍱 Bật lượt trưa", "c:dl:noon:on")
        rows = [(toggle, infer), (noon,)]
        if skips:
            rows.append(tuple(skips))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *buttons, *NAV))
