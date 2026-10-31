"""Màn /admin → 🔗 Shopee Affiliate → ⏱ Tự động đồng bộ (PLAN-080). Chỉ đọc, trừ tạm dừng / tiếp tục.

Bật tự đồng bộ hay đổi chu kỳ là cấu hình của chủ bot (.env: SHOPEE_AUTO_SYNC_ENABLED, …), không có nút bật ở đây.
Nút tạm dừng / tiếp tục chỉ hiện khi cờ đã bật; trạng thái lưu bền trong shopee_sync_state, có audit ở 📊 Lịch sử.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot.config import AutoSyncConfig
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.sync_scheduler import derived_status, history, snapshot

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:sy:home"
STATUS_LABELS = {
    "DISABLED": "⚪ <b>TẮT</b> (chủ bot bật bằng SHOPEE_AUTO_SYNC_ENABLED trong .env)",
    "PAUSED": "⏸️ <b>TẠM DỪNG</b>",
    "RUNNING": "🔄 <b>ĐANG CHẠY</b>",
    "SCHEDULED": "🟢 <b>BẬT</b>",
    "RETRY_WAIT": "🟠 <b>CHỜ THỬ LẠI</b>",
    "FAILED": "🔴 <b>LỖI LIÊN TIẾP</b>",
    "NEEDS_AUTH": "🔑 <b>CẦN KIỂM TRA PHIÊN SHOPEE</b> (tự đồng bộ đã dừng)",
}
RESULT_LABELS = {
    "success": "✅ thành công", "partial": "⚠️ chưa đủ dữ liệu", "failed": "❌ lỗi",
    "running": "🔄 đang chạy", "interrupted": "⏹ bị ngắt",
}
TRIGGER_LABELS = {"auto": "tự động", "manual": "thủ công"}
CATEGORY_LABELS = {
    "AUTH_EXPIRED": "phiên Shopee hết hạn", "ACCESS_DENIED": "Shopee từ chối quyền truy cập",
    "CHALLENGE": "Shopee yêu cầu xác minh", "RATE_LIMITED": "Shopee giới hạn tần suất (429)",
    "NETWORK_TIMEOUT": "hết thời gian chờ mạng", "NETWORK_ERROR": "lỗi mạng", "TRANSIENT_SERVER_ERROR": "Shopee lỗi máy chủ",
    "PARSE_ERROR": "dữ liệu Shopee đổi định dạng", "PARTIAL_SYNC": "đọc thiếu một phần", "DATABASE_ERROR": "lỗi cơ sở dữ liệu",
    "UNKNOWN_ERROR": "lỗi khác", "INTERRUPTED": "bot dừng giữa lượt", "LEASE_LOST": "lượt mất khoá",
}


def _vn(stamp: str | None) -> str:
    try:
        moment = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "-"
    return moment.astimezone(ICT).strftime("%d/%m %H:%M")


def _duration(row) -> str:
    try:
        start = datetime.strptime(row["started_at"], "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(row["completed_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return "-"
    seconds = int((end - start).total_seconds())
    return f"{seconds} giây" if seconds < 120 else f"{seconds // 60} phút"


def _counts(row) -> str:
    if int(row["pages_fetched"] or 0) == 0 and row["window_start"] is None:
        # Lượt trước PLAN-080: chỉ có tổng số đơn đọc được.
        return f"{int(row['conversions_synced'] or 0)} đơn"
    return (
        f"{int(row['conversions_synced'] or 0)} đơn · {int(row['conversions_new'] or 0)} mới · "
        f"{int(row['conversions_changed'] or 0)} đổi · tin khách {int(row['notifications_queued'] or 0)}"
    )


def _cookie_health(repo: TrackingRepository, state: dict) -> str:
    with repo.connect() as conn:
        cookie = conn.execute("SELECT status FROM shopee_cookies WHERE id = 1").fetchone()
    if state.get("needs_auth_since") or (cookie is not None and cookie["status"] == "expired"):
        return "🔴 cần kiểm tra"
    if cookie is not None and cookie["status"] == "connected":
        return "🟢 bình thường" if state.get("last_result") == "success" else "🟡 chưa rõ (lượt gần nhất chưa thành công)"
    return "⚪ chưa kết nối"


def status_label(repo: TrackingRepository, cfg: AutoSyncConfig, now: datetime) -> str:
    """Một dòng cho màn 🔗 Shopee Affiliate."""
    state = snapshot(repo)
    status = derived_status(state, cfg, now)
    if status == "DISABLED":
        return "⏸️ <b>tắt</b> · bấm 🔄 khi cần"
    if status == "SCHEDULED":
        return f"🟢 <b>mỗi {cfg.interval_minutes} phút</b> · lần tới {_vn(state.get('next_due_at'))}"
    return STATUS_LABELS[status].split(" (")[0]


class AutoSyncAdmin:
    def __init__(self, repo: TrackingRepository, cfg: AutoSyncConfig):
        self.repo = repo
        self.cfg = cfg

    def route(self, data: str, now: datetime, notice: str = "") -> BotReply:
        if data == HOME:
            return self.home(now, notice)
        if data == "c:sy:hist":
            return self._history()
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=((("◀️ Tự động đồng bộ", HOME),),))

    def home(self, now: datetime, notice: str = "") -> BotReply:
        state = snapshot(self.repo)
        status = derived_status(state, self.cfg, now)
        runs = history(self.repo, 15)
        last = runs[0] if runs else None
        last_auto = next((run for run in runs if run["trigger_type"] == "auto"), None)
        lines = ["⚙️ Quản trị › Shopee Affiliate › <b>Tự động đồng bộ</b>", ""]
        if notice:
            lines += [notice, ""]
        lines.append(f"Trạng thái: {STATUS_LABELS[status]}")
        if status == "RUNNING":
            lines.append(f"Lượt đang chạy: #{state.get('lease_run_id')} ({TRIGGER_LABELS.get(state.get('lease_trigger'), '-')}), "
                         f"bắt đầu {_vn(state.get('lease_started_at'))}")
        if self.cfg.enabled:
            lines.append(f"Chu kỳ: {self.cfg.interval_minutes} phút · lần dự kiến tiếp theo: "
                         f"{_vn(state.get('next_due_at')) if state.get('next_due_at') else '-'}")
        lines.append(f"Phiên Shopee: {_cookie_health(self.repo, state)}")
        lines.append("")
        if last is None:
            lines.append("Chưa có lượt chạy.")
        else:
            lines.append(
                f"Lần chạy gần nhất: #{last['id']} {_vn(last['started_at'])} ({TRIGGER_LABELS.get(last['trigger_type'], '-')}) · "
                f"{RESULT_LABELS.get(last['status'], last['status'])} · {_duration(last)}"
            )
            lines.append(f"  {_counts(last)}")
        lines.append(f"Lần thành công gần nhất: {_vn(state.get('last_success_at')) if state.get('last_success_at') else '-'}")
        lines.append("Lượt tự động: " + ("chưa có lượt chạy" if last_auto is None else
                                          f"gần nhất #{last_auto['id']} {_vn(last_auto['started_at'])}"))
        failures = int(state.get("consecutive_failures") or 0)
        category = state.get("last_error_category")
        lines.append(f"Lỗi liên tiếp: {failures}"
                     + (f" · lỗi gần nhất: {CATEGORY_LABELS.get(category, html.escape(str(category)))}" if category else ""))
        incident = state.get("open_incident")
        if incident:
            lines.append(f"⚠️ Sự cố #{incident['id']} đang mở từ {_vn(incident['opened_at'])} "
                         f"({html.escape(str(incident['category']))})")
        lines += [
            "",
            "ⓘ Tự động và 🔄 thủ công dùng chung một khoá: chỉ một lượt chạy tại một thời điểm. "
            "Đơn mới / thay đổi đi qua đúng luồng thông báo khách hiện có.",
        ]
        rows = [(("📜 Lịch sử 15 lượt", "c:sy:hist"),)]
        if self.cfg.enabled:
            rows.append((("▶️ Tiếp tục", "c:shopee:auto:on"),) if state.get("paused") else (("⏸️ Tạm dừng", "c:shopee:auto:off"),))
        rows.append((("◀️ Shopee Affiliate", "c:menu:shopee"),))
        return BotReply("\n".join(lines), inline_keyboard=tuple(rows))

    def _history(self) -> BotReply:
        lines = ["⚙️ Quản trị › Shopee Affiliate › Tự động đồng bộ › <b>Lịch sử</b>", ""]
        runs = history(self.repo, 15)
        for run in runs:
            error = ""
            if run["status"] != "success" and run["error_category"]:
                error = f" · {CATEGORY_LABELS.get(run['error_category'], html.escape(str(run['error_category'])))}"
            lines.append(
                f"#{run['id']} {_vn(run['started_at'])} · {TRIGGER_LABELS.get(run['trigger_type'], run['trigger_type'])} · "
                f"{RESULT_LABELS.get(run['status'], html.escape(str(run['status'])))} · {_counts(run)}{error}"
            )
        if not runs:
            lines.append("Chưa có lượt chạy.")
        return BotReply("\n".join(lines), inline_keyboard=((("◀️ Tự động đồng bộ", HOME),),))
