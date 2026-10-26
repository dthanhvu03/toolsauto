"""/admin → 🎵 TikTok Shop (PLAN-085 giai đoạn A): ai được tạo link TikTok Shop qua RioHub.

Chế độ ở `bot_state.tiktok_mode`: off (tắt) · admin (chỉ admin thử, mặc định) · all (mở cho khách).
Giai đoạn A tạo link và báo giá. Giai đoạn B (PLAN-095, tiktok_sync.py) kéo đơn mỗi 2 giờ, ghi sổ và báo đơn như Shopee;
ví vẫn khoá.
Callback: c:tk:home · c:tk:m:<chế độ> · c:tk:m:all:ok (mở cho khách cần xác nhận). Ghi 📊 Lịch sử action `tiktok_mode`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
MODE_KEY = "tiktok_mode"
MODES = {"off": "⚪ Tắt", "admin": "🧪 Chỉ admin thử", "all": "🟢 Mở cho khách"}
DEFAULT_MODE = "admin"
HOME = "c:tk:home"
_MODE = re.compile(r"^c:tk:m:(off|admin|all)(:ok)?$")
NAV = ((("◀️ Tổng quan", "c:menu:home"),),)

AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


def current_mode(repo: TrackingRepository) -> str:
    mode = repo.get_state(MODE_KEY)
    return mode if mode in MODES else DEFAULT_MODE


def open_for(repo: TrackingRepository, user_id: int, admin_ids: frozenset[int]) -> bool:
    mode = current_mode(repo)
    return mode == "all" or (mode == "admin" and user_id in admin_ids)


def _sync_line(repo: TrackingRepository, now: datetime) -> str:
    error = repo.get_state("tiktok_sync_last_error") or ""
    try:
        last = float(repo.get_state("tiktok_sync_last_ok") or 0)
        counts = json.loads(repo.get_state("tiktok_sync_last_count") or "{}")
    except ValueError:
        last, counts = 0.0, {}
    if not last and not error:
        return "chưa chạy lần nào"
    text = "chưa thành công lần nào" if not last else (
        datetime.fromtimestamp(last, timezone.utc).astimezone(ICT).strftime("%H:%M %d/%m")
        + f" · {counts.get('rows', 0)} dòng, {counts.get('matched_new', 0)} đơn mới qua link bot"
    )
    return text + (f" · 🔴 lỗi gần nhất: {error}" if error else "")


def history_line(before: dict, after: dict) -> str:
    old = MODES.get(str(before.get("mode")), "-")
    new = MODES.get(str(after.get("mode")), "-")
    return f"TikTok Shop: {old} → {new}"


class TikTokAdmin:
    def __init__(self, repo: TrackingRepository, configured: bool, audit: AuditFn | None = None):
        self.repo = repo
        self.configured = configured
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home(now)
        if (found := _MODE.fullmatch(data)) is not None:
            mode, confirmed = found.group(1), bool(found.group(2))
            if mode == "all" and not confirmed and current_mode(self.repo) != "all":
                return self._confirm_open()
            return self._set(admin_id, mode, now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=NAV)

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        mode = current_mode(self.repo)
        since = (now - timedelta(days=7)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.repo.connect() as conn:
            total, week = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(created_at >= ?), 0) FROM link_requests "
                "WHERE platform = 'tiktok' AND link_status = 'created'",
                (since,),
            ).fetchone()
            refused = conn.execute(
                "SELECT COUNT(*) FROM link_requests WHERE reject_reason LIKE 'tiktok%' AND created_at >= ?", (since,)
            ).fetchone()[0]
            orders, matched = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(matched_link_id IS NOT NULL), 0) FROM shopee_conversions "
                "WHERE platform = 'tiktok'"
            ).fetchone()
        lines = ["⚙️ Quản trị › <b>🎵 TikTok Shop</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            "RioHub: " + ("✅ đã có khoá trong .env" if self.configured else "🔴 chưa có RIOHUB_API_KEY / RIOHUB_CREATOR_USERNAME"),
            f"Chế độ: <b>{MODES[mode]}</b>",
            f"Link TikTok đã tạo: {total} (7 ngày: {week}) · bị từ chối 7 ngày: {refused}",
            "",
            f"Đơn TikTok đã ghi: {orders} (qua link bot: {matched})",
            "Đồng bộ đơn (mỗi 2 giờ): " + _sync_line(self.repo, now),
            "",
            "ⓘ Báo giá dùng chung cách tính với Shopee. Đơn qua link bot được ghi sổ và báo khách như Shopee; "
            "ví vẫn khoá.",
        ]
        rows = [((("• " if key == mode else "") + label, f"c:tk:m:{key}"),) for key, label in MODES.items()]
        return BotReply("\n".join(lines), inline_keyboard=(*rows, *NAV))

    def _confirm_open(self) -> BotReply:
        return BotReply(
            "⚙️ Quản trị › 🎵 TikTok Shop › <b>Mở cho khách?</b>\n\n"
            "Mọi khách dán link TikTok Shop sẽ nhận link mua và số hoàn dự kiến.\n"
            "Đơn mua qua link được đồng bộ mỗi 2 giờ, ghi sổ và báo khách như đơn Shopee; ví vẫn khoá.\n"
            "⚠️ Nên có xác nhận bằng văn bản của RioHub cho phép dùng làm bot hoàn tiền trước khi mở.",
            inline_keyboard=((("✅ Mở cho khách", "c:tk:m:all:ok"),), (("◀️ Quay lại", HOME),)),
        )

    def _set(self, admin_id: int, mode: str, now: datetime) -> BotReply:
        before = current_mode(self.repo)
        if before != mode:
            self.repo.set_state(MODE_KEY, mode)
            if self.audit is not None:
                self.audit(admin_id, "tiktok_mode", {"mode": before}, {"mode": mode}, now)
        return self._home(now, f"✅ Chế độ TikTok Shop: {MODES[mode]}.")
