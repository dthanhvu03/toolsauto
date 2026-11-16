"""📈 Báo cáo tăng trưởng 8h sáng cho chủ bot (PLAN-172, ADR-067).

Một tin mỗi ngày (từ ``REPORT_HOUR`` giờ VN), qua hàng đợi admin của Cashbot. CHỈ ĐỌC hai DB bot (Cashbot + AI Pass Store):
- Chỉ số chính: khách dùng thật 7 ngày (``all_users.report``) so với gốc / mục tiêu.
- Hôm qua: khách mới, đơn, doanh thu Store.
- Phễu khách mới 7 ngày: Store vào → tạo mã nạp → có đơn; Cashbot vào → tạo link → có đơn.
- Thử nghiệm đang chạy: T1 (khách Store mới từ ``T1_START`` có đơn), T2 (số câu AI trả lời tin chữ hôm qua).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot import all_users

logger = logging.getLogger(__name__)

ICT = all_users.ICT
REPORT_HOUR = 8
STATE_KEY = "growth_report_day"
BASELINE_ACTIVE = 24  # 15/11
TARGET_ACTIVE = 60  # 12/12
TARGET_DAY = "12/12"
T1_START = "2026-11-15T17:50:00Z"  # restart đưa T1 + T2 lên
T1_BASELINE = "7%"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pct(part: int, whole: int) -> str:
    return f"{part * 100 // whole}%" if whole else "–"


def _vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"


def _store(path: Path, since_day: datetime, until_day: datetime, since_week: datetime) -> dict:
    with closing(all_users._ro(path)) as c:
        one = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
        new_ids = "SELECT user_id FROM users WHERE created_at >= ?"
        return {
            "new_y": one("SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?", _iso(since_day), _iso(until_day)),
            "orders_y": one("SELECT COUNT(*) FROM orders WHERE status='done' AND created_at >= ? AND created_at < ?",
                            _iso(since_day), _iso(until_day)),
            "revenue_y": one("SELECT COALESCE(SUM(total),0) FROM orders WHERE status='done' AND refunded=0 "
                             "AND created_at >= ? AND created_at < ?", _iso(since_day), _iso(until_day)),
            "new_w": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", _iso(since_week)),
            "product_w": one("SELECT COUNT(*) FROM state WHERE key IN (SELECT 'step:product:' || user_id FROM users "
                             "WHERE created_at >= ?)", _iso(since_week)),
            "confirm_w": one("SELECT COUNT(*) FROM state WHERE key IN (SELECT 'step:confirm:' || user_id FROM users "
                             "WHERE created_at >= ?)", _iso(since_week)),
            "closed": one("SELECT COUNT(*) FROM state WHERE key = 'closed_manual' AND value = '1'"),
            "topup_w": one(f"SELECT COUNT(DISTINCT user_id) FROM topups WHERE user_id IN ({new_ids})", _iso(since_week)),
            "order_w": one(f"SELECT COUNT(DISTINCT user_id) FROM orders WHERE status='done' AND user_id IN ({new_ids})",
                           _iso(since_week)),
            "t1_new": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", T1_START),
            "t1_buy": one(f"SELECT COUNT(DISTINCT user_id) FROM orders WHERE status='done' AND user_id IN ({new_ids})",
                          T1_START),
        }


def _cashbot(path: Path, since_day: datetime, until_day: datetime, since_week: datetime) -> dict:
    with closing(all_users._ro(path)) as c:
        one = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
        new_ids = "SELECT telegram_user_id FROM telegram_users WHERE created_at >= ?"
        return {
            "new_y": one("SELECT COUNT(*) FROM telegram_users WHERE created_at >= ? AND created_at < ?",
                         _iso(since_day), _iso(until_day)),
            "links_y": one("SELECT COUNT(*) FROM link_requests WHERE link_status='created' AND created_at >= ? "
                           "AND created_at < ?", _iso(since_day), _iso(until_day)),
            "new_w": one("SELECT COUNT(*) FROM telegram_users WHERE created_at >= ?", _iso(since_week)),
            "link_w": one(f"SELECT COUNT(DISTINCT telegram_user_id) FROM link_requests WHERE link_status='created' "
                          f"AND telegram_user_id IN ({new_ids})", _iso(since_week)),
            "order_w": one(f"SELECT COUNT(DISTINCT telegram_user_id) FROM shopee_conversions WHERE telegram_user_id IN "
                           f"({new_ids}) AND UPPER(COALESCE(order_status,'')) NOT IN "
                           "('CANCELLED','CANCELED','INVALID','REJECTED')", _iso(since_week)),
            "ai_y": one("SELECT COUNT(*) FROM admin_notifications WHERE event_type='CHAT_AI_ANSWER' "
                        "AND created_at >= ? AND created_at < ?", _iso(since_day), _iso(until_day)),
        }


def build(now: datetime | None = None, cashback_path: Path | None = None, store_path: Path | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    today = moment.astimezone(ICT).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday, week = today - timedelta(days=1), today - timedelta(days=7)
    cb_path, st_path = cashback_path or all_users.cashback_db(), store_path or all_users.store_db()
    rep = all_users.report(moment, cb_path, st_path)
    active = rep.total.active_7d
    lines = [f"📈 <b>Báo cáo tăng trưởng {today.strftime('%d/%m')}</b>", "",
             f"🎯 Khách dùng thật 7 ngày: <b>{active}</b> (gốc 15/11: {BASELINE_ACTIVE} · mục tiêu {TARGET_DAY}: "
             f"{TARGET_ACTIVE})"]
    lines += [f"   {b.label}: {b.active_7d}" for b in rep.bots]
    try:
        st = _store(st_path, yesterday, today, week)
        cb = _cashbot(cb_path, yesterday, today, week)
    except sqlite3.Error as exc:
        logger.exception("[Cashback] báo cáo tăng trưởng: đọc DB lỗi")
        return "\n".join(lines + ["", f"⚠️ Không đọc được DB: {exc}"])
    lines += [
        "", f"<b>Hôm qua {yesterday.strftime('%d/%m')}</b>",
        f"• AI Store: {st['new_y']} khách mới · {st['orders_y']} đơn · {_vnd(st['revenue_y'])}",
        f"• Cashbot: {cb['new_y']} khách mới · {cb['links_y']} link",
        "", "<b>Khách mới 7 ngày đi tới đâu</b>",
        f"• AI Store: {st['new_w']} vào → {st['product_w']} xem món → {st['confirm_w']} chọn số lượng → "
        f"{st['topup_w']} tạo mã nạp ({_pct(st['topup_w'], st['new_w'])}) → "
        f"{st['order_w']} có đơn ({_pct(st['order_w'], st['new_w'])})",
        f"• Cashbot: {cb['new_w']} vào → {cb['link_w']} tạo link ({_pct(cb['link_w'], cb['new_w'])}) → "
        f"{cb['order_w']} có đơn ({_pct(cb['order_w'], cb['new_w'])})",
        "", "<b>Thử nghiệm đang chạy</b>",
        f"• T1 Store vào thẳng danh sách món: khách mới từ 16/11 có đơn {st['t1_buy']}/{st['t1_new']} "
        f"({_pct(st['t1_buy'], st['t1_new'])}, gốc {T1_BASELINE})",
        f"• T2 Cashbot AI trả lời tin chữ: hôm qua {cb['ai_y']} câu",
    ]
    if st["closed"]:
        lines.insert(1, "\n🔴 <b>AI Store đang ĐÓNG TAY</b>: khách xem được món nhưng không mua được. Mở ở ⚙️ Quản lý shop → Giờ nghỉ.")
    if rep.errors:
        lines += ["", "⚠️ " + "; ".join(rep.errors)]
    return "\n".join(lines)


def tick(repo, admin_notifier, now: datetime | None = None) -> bool:
    """Gửi một lần mỗi ngày từ REPORT_HOUR giờ VN. True nếu vừa đưa vào hàng đợi."""
    moment = now or datetime.now(timezone.utc)
    local = moment.astimezone(ICT)
    day = local.strftime("%Y-%m-%d")
    if local.hour < REPORT_HOUR or repo.get_state(STATE_KEY) == day or not admin_notifier._active():
        return False
    repo.set_state(STATE_KEY, day)
    repo.enqueue_admin_event(event_key=f"growth_report:{day}", event_type="GROWTH_REPORT",
                             chat_id=int(admin_notifier.chat_id), message_html=build(moment))
    return True
