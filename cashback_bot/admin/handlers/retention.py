"""/admin → 📋 Điều khoản → 🗄 Thời hạn lưu dữ liệu: xem và đổi các mốc trong retention.py.

Callback: c:rt:home · c:rt:e:<mã> (gõ số, 10 phút) · c:rt:d:<mã> (về mặc định). Mỗi lần đổi ghi 📊 Lịch sử
(action `retention`). Đổi mốc không sửa điều khoản đã công bố: muốn khách thấy mốc mới thì tạo phiên bản mới.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta

from cashback_bot import retention
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply

HOME = "c:rt:home"
WAIT = timedelta(minutes=10)
_EDIT = re.compile(r"^c:rt:e:([a-z_]{3,24})$")
_DEFAULT = re.compile(r"^c:rt:d:([a-z_]{3,24})$")
BACK = ((("◀️ Thời hạn lưu", HOME),),)
NAV = ((("◀️ Điều khoản", "c:tm:home"),),)

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def history_line(before: dict, after: dict) -> str:
    """Dòng 📊 Lịch sử cho action `retention`."""
    key = str(after.get("key", ""))
    label = retention.FIELDS[key][0] if key in retention.FIELDS else key
    old = retention.period(key, before["value"]) if key in retention.FIELDS and "value" in before else "-"
    new = retention.period(key, after["value"]) if key in retention.FIELDS and "value" in after else "-"
    return f"Thời hạn lưu dữ liệu: {label} {old} → {new}"


class RetentionAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None, waiting: dict | None = None):
        self.repo = repo
        self.audit = audit
        self.waiting = {} if waiting is None else waiting

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if _EDIT.fullmatch(data) is None:
            self.waiting.pop(admin_id, None)
        if data == HOME:
            return self._home()
        if (found := _EDIT.fullmatch(data)) is not None and found.group(1) in retention.FIELDS:
            return self._ask(admin_id, found.group(1), now)
        if (found := _DEFAULT.fullmatch(data)) is not None and found.group(1) in retention.FIELDS:
            key = found.group(1)
            return self._save(admin_id, key, retention.DEFAULTS[key], now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def consume_text(self, admin_id: int, text: str, now: datetime) -> BotReply | None:
        entry = self.waiting.get(admin_id)
        if entry is None:
            return None
        key, deadline = entry
        stripped = (text or "").strip()
        if deadline <= now or stripped.startswith("/"):
            self.waiting.pop(admin_id, None)
            return None
        _label, unit, _default, low, high = retention.FIELDS[key]
        value = int(stripped) if stripped.isdigit() else None
        if value is None or not retention.valid(key, value):
            return BotReply(f"⚠️ Gõ một số từ {low} đến {high} ({unit}).", inline_keyboard=BACK)
        self.waiting.pop(admin_id, None)
        return self._save(admin_id, key, value, now)

    def _home(self, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            values = retention.load(conn)
        lines = ["⚙️ Quản trị › Điều khoản › <b>🗄 Thời hạn lưu dữ liệu</b>", ""]
        if notice:
            lines += [notice, ""]
        for key, (label, _unit, default, _low, _high) in retention.FIELDS.items():
            mark = "" if values[key] == default else f" (mặc định {retention.period(key, default)})"
            lines.append(f"• {label}: <b>{retention.period(key, values[key])}</b>{mark}")
        lines += [
            "",
            "• Tin nhắn thường: không lưu nội dung. Log hệ thống: 8 tuần (cài ở logrotate).",
            "• Khách yêu cầu xoá: xoá hoặc ẩn danh mọi thứ, trừ sổ ví và chứng từ chi trả (giữ tới hạn trên).",
            "",
            "ⓘ Bản nháp điều khoản tạo sau khi đổi sẽ ghi mốc mới. Điều khoản đã công bố không đổi theo: "
            "muốn khách thấy mốc mới thì tạo và công bố phiên bản mới.",
            "ⓘ Bot chưa tự xoá dữ liệu khi đến hạn; việc xoá trên DB cần chủ bot duyệt riêng.",
        ]
        rows = [((f"✍️ {label[:40]}", f"c:rt:e:{key}"),) for key, (label, *_rest) in retention.FIELDS.items()]
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *NAV))

    def _ask(self, admin_id: int, key: str, now: datetime) -> BotReply:
        self.waiting[admin_id] = (key, now + WAIT)
        label, unit, default, low, high = retention.FIELDS[key]
        with self.repo.connect() as conn:
            current = retention.load(conn)[key]
        return BotReply(
            f"✍️ <b>{label}</b>\n\n"
            f"Đang đặt: {retention.period(key, current)} · mặc định {retention.period(key, default)}.\n"
            f"Gõ số {unit}, từ {low} đến {high}.",
            inline_keyboard=(((f"↩️ Về mặc định ({retention.period(key, default)})", f"c:rt:d:{key}"),),
                             (("✖️ Hủy", HOME),)),
        )

    def _save(self, admin_id: int, key: str, value: int, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            stored = retention.custom(conn)
            before = retention.load(conn)[key]
        if value == retention.DEFAULTS[key]:
            stored.pop(key, None)
        else:
            stored[key] = value
        self.repo.set_state(retention.RETENTION_KEY, json.dumps(stored, sort_keys=True))
        if self.audit is not None and before != value:
            self.audit(admin_id, "retention", {"key": key, "value": before}, {"key": key, "value": value}, now)
        return self._home(f"✅ Đã lưu: {retention.FIELDS[key][0]} {retention.period(key, value)}.")
