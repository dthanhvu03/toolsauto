"""📊 Lịch sử /admin: dòng audit thay đổi chính sách / cài đặt và phiên bản chính sách đã áp dụng. Chỉ đọc."""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cashback_bot import policy_snapshot
from cashback_bot.admin.common import ICT, TIERS, AdminSafetyError, percent, stamp
from cashback_bot.admin.handlers.announce import history_line as announce_history
from cashback_bot.admin.handlers.deals import history_line as deals_history
from cashback_bot.admin.handlers.engagement import history_line as engagement_history
from cashback_bot.admin.handlers.insights import goal_history
from cashback_bot.admin.handlers.reserve import ACCOUNT_KINDS, cancelled_ids, vn_time
from cashback_bot.admin.handlers.retention import history_line as retention_history
from cashback_bot.admin.handlers.tiktok import history_line as tiktok_history
from cashback_bot.money import format_vnd

if TYPE_CHECKING:
    from cashback_bot.admin.panel import AdminPanel

RESERVE_NAMES = {"estimate_fee_reserve": "Phí dự phòng", "estimate_tax_reserve": "Thuế dự phòng"}
_ACTIONS = {
    "draft": "Tạo bản nháp",
    "preview": "Xem trước",
    "confirm": "Xác nhận",
    "cancel": "Hủy",
    "reserve_apply": "Áp dụng cho khách",
    "share_apply": "Áp dụng cho khách",
    "reserve_cancel": "Huỷ lịch hẹn",
    "share_cancel": "Huỷ lịch hẹn",
}
_RESULTS = {
    "collecting": "đang nhập",
    "preview": "chờ xác nhận",
    "confirmed": "đã lưu",
    "cancelled": "đã hủy",
    "expired": "hết hạn",
    "applied": "đã áp dụng",
}


def history_rows(panel: AdminPanel) -> list[str] | None:
    try:
        with panel._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.action, a.result, a.created_at, a.before_json, a.after_json, d.domain, d.tier, d.proposed_bps
                FROM admin_change_audit a
                LEFT JOIN admin_drafts d ON d.id = a.draft_id
                ORDER BY a.id DESC
                LIMIT 8
                """
            ).fetchall()
    except AdminSafetyError:
        return None
    return [history_line(row) for row in rows]


def policy_versions(panel: AdminPanel, now: datetime) -> list[str] | None:
    """Phiên bản tỷ lệ chia và dự phòng đã áp dụng, kèm trạng thái; và độ phủ snapshot link."""
    try:
        with panel._connect() as conn:
            live = panel.resolve_policy(now)
            shares = conn.execute("SELECT * FROM share_policies ORDER BY effective_at DESC, id DESC LIMIT 5").fetchall()
            reserves = conn.execute("SELECT * FROM reserve_policies ORDER BY effective_at DESC, id DESC LIMIT 5").fetchall()
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            coverage = policy_snapshot.coverage(conn) if "link_policy_snapshots" in tables else None
            cancelled = {"share": cancelled_ids(conn, "share"), "reserve": cancelled_ids(conn, "reserve")}
    except (AdminSafetyError, sqlite3.Error):
        return None
    stamp_now = stamp(now)

    def state(row: sqlite3.Row, active_id: int | None, kind: str) -> str:
        if int(row["id"]) in cancelled[kind]:
            return "✖️ ĐÃ HUỶ TRƯỚC MỐC"
        if str(row["effective_at"]) > stamp_now:
            return "🗓️ ĐÃ HẸN GIỜ"
        return "🟢 ĐANG ÁP DỤNG" if int(row["id"]) == active_id else "⚪ ĐÃ THAY"

    share_active = live.share_policy_id if live.pricing_version == "v1.2" else None
    lines = [f"<b>Tỷ lệ chia</b> (V1.2){'' if live.pricing_version == 'v1.2' else ' · đang chạy V1.1, chưa dùng'}"]
    lines += [
        f"• #{row['id']} {percent(int(row['share_bps']))} từ {vn_time(str(row['effective_at']))} · {state(row, share_active, 'share')}"
        for row in shares
    ] or [f"• Mặc định cấu hình {panel.displayed_rate_percent}% · 🟢 ĐANG ÁP DỤNG"]
    lines.append("<b>Dự phòng phí và thuế</b>")
    lines += [
        f"• #{row['id']} phí {percent(int(row['fee_bps']))}, thuế {percent(int(row['tax_reserve_bps']))} "
        f"từ {vn_time(str(row['effective_at']))} · {state(row, live.reserve_policy_id, 'reserve')}"
        for row in reserves
    ] or [f"• Mặc định cấu hình phí {percent(panel.fee_default_bps)}, thuế {percent(panel.tax_default_bps)} · 🟢 ĐANG ÁP DỤNG"]
    if coverage is not None:
        done = coverage[policy_snapshot.CAPTURED] + coverage[policy_snapshot.BACKFILLED]
        lines.append(
            f"<b>Link đã chốt chính sách</b>: {done} · chưa xác định: "
            f"{coverage[policy_snapshot.UNRESOLVED] + coverage['missing']}"
        )
    return lines


def policy_subject(kind: str, row) -> str:
    if kind == "share":
        return f"tỷ lệ chia {percent(int(row['share_bps']))}"
    return f"dự phòng phí {percent(int(row['fee_bps']))}, thuế {percent(int(row['tax_reserve_bps']))}"


def history_line(row: sqlite3.Row) -> str:
    moment = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    when = moment.astimezone(ICT).strftime("%d/%m %H:%M")
    if row["action"] == "reserve_apply" and row["after_json"]:
        data = json.loads(row["after_json"])
        subject = (
            f"Dự phòng {ACCOUNT_KINDS.get(data['account_kind'], '-')}: phí {percent(data['fee_bps'])}, "
            f"thuế {percent(data['tax_reserve_bps'])}, từ {vn_time(data['effective_at'])}"
        )
        return f"{when} · {subject} · {_ACTIONS['reserve_apply']}: {_RESULTS['applied']}"
    if row["action"] == "share_apply" and row["after_json"]:
        data = json.loads(row["after_json"])
        subject = f"Tỷ lệ chia → {percent(data['share_bps'])}, từ {vn_time(data['effective_at'])}"
        return f"{when} · {subject} · {_ACTIONS['share_apply']}: {_RESULTS['applied']}"
    if row["action"] in {"share_cancel", "reserve_cancel"} and row["before_json"]:
        data = json.loads(row["before_json"])
        kind = "share" if row["action"] == "share_cancel" else "reserve"
        subject = f"#{data.get('id')} {policy_subject(kind, data)}, mốc {vn_time(data['effective_at'])}"
        return f"{when} · {subject} · {_ACTIONS[row['action']]}: {_RESULTS['cancelled']}"
    setting = setting_line(row)
    if setting is not None:
        return f"{when} · {setting}"
    domain = row["domain"]
    if domain == "membership_rates":
        subject = f"Hạng {TIERS.get(row['tier'], row['tier'])}"
    else:
        subject = RESERVE_NAMES.get(domain, domain or "-")
    if row["action"] in {"preview", "confirm"} and row["proposed_bps"] is not None:
        subject += f" → {percent(int(row['proposed_bps']))}"
    action = _ACTIONS.get(row["action"], row["action"])
    result = _RESULTS.get(row["result"], row["result"])
    return f"{when} · {subject} · {action}: {result}"


def setting_line(row: sqlite3.Row) -> str | None:
    """Dòng lịch sử cho cài đặt đổi ngay (PLAN-066). None: không phải loại này."""
    action = row["action"]
    if action not in {
        "wallet_enabled", "wallet_hold_days", "wallet_min_withdraw", "wallet_limits", "shopee_cookie", "shopee_auto_sync",
        "commission_review_ack", "terms_draft", "terms_publish", "bank_verified", "customer_notify_retry",
        "shopee_auto_sync_pause", "customer_notify_smoke", "customer_notify_intro", "ops_cost",
        "goal", "retention", "tiktok_mode", "sale_reminder", "deals", "announce",
    }:
        return None
    after = json.loads(row["after_json"]) if row["after_json"] else {}
    before = json.loads(row["before_json"]) if "before_json" in row.keys() and row["before_json"] else {}
    if action == "wallet_enabled":
        return "Ví khách → " + ("bật" if after.get("on") else "tắt")
    if action == "wallet_hold_days":
        return f"Ví khách: giữ tiền {before.get('days', '-')} → {after.get('days')} ngày sau khi đơn hoàn thành"
    if action == "wallet_min_withdraw":
        old = format_vnd(int(before["vnd"])) if "vnd" in before else "-"
        return f"Ví khách: rút tối thiểu {old} → {format_vnd(int(after['vnd']))}"
    if action == "wallet_limits":
        parts = [
            f"{label} {format_vnd(int(before[key]))} → {format_vnd(int(after[key]))}"
            for key, label in (("min", "tối thiểu"), ("req", "mỗi lần"), ("day", "mỗi ngày"), ("month", "mỗi tháng"))
            if key in after and before.get(key) != after[key]
        ]
        return "Ví khách: hạn mức rút " + ", ".join(parts)
    if action == "customer_notify_retry":
        return f"Thông báo khách: gửi lại tin #{after.get('id', '-')}"
    if action in {"customer_notify_smoke", "customer_notify_intro"}:
        # ID Telegram chỉ hiện 3 số cuối, như các màn khác.
        who = "…" + html.escape(str(after.get("chat_id", "-"))[-3:])
        if action == "customer_notify_intro":
            return f"Thông báo khách: tin giới thiệu thông báo đơn tới khách {who}"
        kind = "xử lý lại sự kiện thử (chống trùng)" if after.get("repeat") else "tin thử mới"
        return f"Thông báo khách: {kind} tới tài khoản test {who}"
    if action == "bank_verified":
        target = f"khách …{str(after['user'])[-3:]}" if "user" in after else f"yêu cầu #{after.get('payout', '-')}"
        return f"Ví khách: xác minh tài khoản ••••{html.escape(str(after.get('last4', '-')))} ({html.escape(target)})"
    if action == "ops_cost":
        old = format_vnd(int(before["vnd"])) if "vnd" in before else "chưa nhập"
        return f"Chi phí vận hành / hạ tầng: {old} → {format_vnd(int(after['vnd']))} mỗi tháng"
    if action == "goal":
        return goal_history(before, after)
    if action == "retention":
        return retention_history(before, after)
    if action == "tiktok_mode":
        return tiktok_history(before, after)
    if action == "sale_reminder":
        return engagement_history(before, after)
    if action == "deals":
        return deals_history(before, after)
    if action == "announce":
        return announce_history(before, after)
    if action in {"terms_draft", "terms_publish"}:
        verb = "tạo bản nháp" if action == "terms_draft" else "công bố"
        return f"Điều khoản: {verb} {html.escape(str(after.get('version', '-')))}"
    if action == "commission_review_ack":
        return f"Duyệt hoa hồng: đã kiểm tra cảnh báo đơn …{html.escape(str(after.get('conversion', '-'))[-4:])}"
    if action == "shopee_auto_sync":
        return "Shopee Affiliate: tự đồng bộ 4 giờ → " + ("bật" if after.get("on") else "tắt")
    if action == "shopee_auto_sync_pause":
        return "Shopee Affiliate: tự đồng bộ → " + ("tạm dừng" if after.get("paused") else "tiếp tục")
    return f"Shopee Affiliate: kết nối cookie ({html.escape(str(after.get('account', '-')))})"
