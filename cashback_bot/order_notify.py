"""Sự kiện thông báo đơn hàng cho khách (PLAN-079, ADR-056).

Chạy trong transaction ghi đơn (hook của TrackingRepository.record_conversion_snapshot), nên tin chỉ có khi dữ liệu
đơn đã ghi; rollback thì không có tin. Người nhận là người tạo link có Sub ID Shopee ghi nhận, không phải người mua.

Quy tắc:
- Đơn khớp link lần đầu → một tin «đã ghi nhận giao dịch» (khoá conversion:<id>:first_matched). Đơn mua trước mốc
  kích hoạt thông báo thì không báo «đơn mới» (vẫn xem được ở /donhang). Mốc = lần bật cờ gần nhất (sync_activation).
- Lần đồng bộ sau có thay đổi có ý nghĩa → gom thành một tin (khoá conversion:<id>:changes:<id thay đổi lớn nhất>).
  Thay đổi hoa hồng nhỏ hơn ngưỡng không báo. Đồng bộ lại y hệt không có thay đổi nên không có tin.
- Có xung đột gán người nhận (Sub ID trỏ link khác) → không báo.
- Cờ CUSTOMER_NOTIFICATIONS_ENABLED tắt hoặc khách tắt loại tin → vẫn ghi để theo dõi nhưng ở trạng thái bỏ qua.
- Không bao giờ báo «đã duyệt» khi chưa có APPROVED, không báo «rút được» hay «đã chuyển tiền» ở đây.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from cashback_bot import policy_snapshot
from cashback_bot.commission_validation import APPROVED, FRAUD, REJECTED
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import lower_than_link, order_new_notice, order_update_notice, source_text
from cashback_bot.notify_dispatch import BASELINE_KEY, NotifyConfig, customer_block_reason
from cashback_bot.pricing import cashback_for

logger = logging.getLogger("cashback_bot")

STATE_KEY = "customer_notify_state"
HISTORY_KEY = "customer_notify_history"
MIN_CHANGE_VND = 500
MIN_CHANGE_RATIO = 0.10
MEANINGFUL_STATUS = {"PAID", "COMPLETED", "CANCELLED", "CANCELED"}

__all__ = ["BASELINE_KEY", "NotifyConfig", "make_hook", "sync_activation"]


def sync_activation(repo: TrackingRepository, cfg: NotifyConfig, now: datetime) -> str | None:
    """Lúc khởi động: ghi chế độ thông báo đơn (off / test / on), đặt mốc kích hoạt khi đổi chế độ. Trả mốc hiện tại.

    Mốc là lúc bắt đầu chế độ đang chạy, lưu trong bot_state (không ở RAM). Restart cùng chế độ giữ nguyên mốc.
    Tắt rồi bật lại, hoặc chuyển từ thử với tài khoản test sang bật cho mọi khách, đặt mốc mới: đơn mua và tin ghi
    trước mốc không được gửi dồn. Lịch sử đổi chế độ chỉ thêm (HISTORY_KEY).
    """
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "off" if not cfg.enabled else "test" if cfg.test_ids else "on"
    with repo.connect() as conn:
        found = dict(conn.execute(
            "SELECT key, value FROM bot_state WHERE key IN (?, ?, ?)", (BASELINE_KEY, STATE_KEY, HISTORY_KEY)
        ).fetchall())
        baseline = found.get(BASELINE_KEY)
        # Bản Gate A chỉ ghi mốc khi bật, chưa ghi chế độ: có mốc nghĩa là đang bật.
        previous = found.get(STATE_KEY) or ("on" if baseline else "off")
        writes = {}
        if mode != "off" and (mode != previous or baseline is None):
            baseline = writes[BASELINE_KEY] = stamp
        if mode != found.get(STATE_KEY):
            history = json.loads(found.get(HISTORY_KEY) or "[]")
            history.append({"at": stamp, "mode": mode, "baseline": None if mode == "off" else baseline})
            writes[STATE_KEY] = mode
            writes[HISTORY_KEY] = json.dumps(history, separators=(",", ":"))
            logger.info("[Cashback] thông báo đơn: %s → %s, mốc %s", previous, mode, baseline)
        for key, value in writes.items():
            conn.execute(
                "INSERT INTO bot_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    return None if mode == "off" else baseline


def short_order(order_sn: str | None, conversion_id: str) -> str:
    return "••••" + (order_sn or conversion_id)[-4:]


def keyboard(conversion_id: str) -> str:
    return json.dumps({"inline_keyboard": [[
        {"text": "📦 Xem đơn", "callback_data": f"u:o:d:{conversion_id}"},
        {"text": "📩 Hỗ trợ", "callback_data": "u:p:support"},
    ]]})


def cashback_of(conn: sqlite3.Connection, link_id: int | None, commission: int | None) -> int | None:
    """Tiền hoàn tạm tính theo snapshot chính sách của link. Không có snapshot dùng được hay thiếu hoa hồng → None."""
    if link_id is None or commission is None:
        return None
    found = policy_snapshot.load(conn, int(link_id))
    if found is None or found.policy is None:
        return None
    return cashback_for(max(0, int(commission)), found.policy).cashback_vnd


def significant_change(old: int | None, new: int | None) -> bool:
    if old is None or new is None or old == new:
        return False
    if new == 0:
        return True
    delta = abs(new - old)
    return delta >= MIN_CHANGE_VND or (old > 0 and delta / old >= MIN_CHANGE_RATIO)


def bought_items(raw_json: str | None) -> set[int]:
    try:
        items = json.loads(raw_json or "{}").get("order", {}).get("items") or []
        return {int(item["item_id"]) for item in items if item.get("item_id") is not None}
    except (ValueError, TypeError, AttributeError, KeyError):
        return set()


def why_lower(conn: sqlite3.Connection, link_id: int, cashback: int | None, values: dict) -> str:
    """Hoàn thực thấp hơn hẳn số báo lúc tạo link thì nói lý do (mua món khác / trả ít hơn / Shopee tính thấp hơn)."""
    link = conn.execute("SELECT estimated_cashback, price_vnd, item_id FROM link_requests WHERE id = ?",
                        (link_id,)).fetchone()
    if link is None or link[0] is None or cashback is None:
        return ""
    estimated, price, item_id = int(link[0]), link[1], link[2]
    if cashback >= estimated or not significant_change(estimated, cashback):
        return ""
    bought = bought_items(values.get("raw_json"))
    other_item = bool(bought) and item_id is not None and int(item_id) not in bought
    paid = values.get("gmv_vnd")
    # Đã trừ phần do trả ít hơn mà vẫn thấp hơn hẳn: Shopee tính mức thấp hơn số AddLiveTag báo.
    expected = estimated * int(paid) // int(price) if paid and price and int(paid) < int(price) else estimated
    rate_lower = not other_item and cashback < expected and significant_change(expected, cashback)
    return lower_than_link(estimated, other_item=other_item, paid_vnd=paid, price_vnd=price, rate_lower=rate_lower)


def _first_order(conn: sqlite3.Connection, user: int, conversion_id: str) -> bool:
    """Khách chưa có đơn nào khác khớp link của bot."""
    return conn.execute(
        "SELECT 1 FROM shopee_conversions WHERE telegram_user_id = ? AND conversion_id != ? AND matched_link_id IS NOT NULL",
        (user, conversion_id),
    ).fetchone() is None


def _attribution_conflict(conn: sqlite3.Connection, conversion_id: str, recorded) -> bool:
    if any(change.field == "attribution" for change, _id in recorded):
        return True
    row = conn.execute(
        """
        SELECT 1 FROM shopee_conversion_changes c JOIN shopee_conversions v ON v.conversion_id = c.conversion_id
        WHERE c.conversion_id = ? AND c.field = 'attribution' AND COALESCE(v.review_status, '') != 'reviewed' LIMIT 1
        """,
        (conversion_id,),
    ).fetchone()
    return row is not None


def _queue(conn, cfg: NotifyConfig, *, key: str, category: str, user: int, html: str, conversion_id: str, now: str) -> None:
    row = {"category": category, "chat_id": user, "created_at": now}
    reason = customer_block_reason(conn, row, cfg, _parse_now(now))
    enqueue_event(
        conn, event_key=key, event_type="ORDER_" + category.upper(), chat_id=user, message_html=html,
        audience="customer", category=category, reply_markup_json=keyboard(conversion_id),
        source_ref=f"conversion:{conversion_id}", suppressed_reason=reason, now=now,
    )


def _parse_now(now: str) -> datetime:
    return datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def make_hook(cfg: NotifyConfig):
    def hook(conn: sqlite3.Connection, conversion_id: str, prev, values: dict, recorded, now: str) -> None:
        user, link_id = values.get("telegram_user_id"), values.get("matched_link_id")
        if user is None or link_id is None:
            return
        if _attribution_conflict(conn, conversion_id, recorded):
            return
        order = short_order(values.get("order_sn"), conversion_id)
        status = (values.get("order_status") or "").upper()
        net = values.get("net_commission_vnd")
        first = prev is None or prev["matched_link_id"] is None
        if first:
            baseline = conn.execute("SELECT value FROM bot_state WHERE key = ?", (BASELINE_KEY,)).fetchone()
            cashback = cashback_of(conn, link_id, net)
            html = source_text(
                order_new_notice(order, cashback, status, values.get("validation_status"),
                                 why_lower(conn, int(link_id), cashback, values), first=_first_order(conn, user, conversion_id)),
                conversion_id,
            )
            key = f"conversion:{conversion_id}:first_matched"
            purchase = values.get("purchase_time") or ""
            if baseline is None:
                hold = "feature_off"
            elif not purchase:
                hold = "no_purchase_time"  # không biết mua trước hay sau mốc: không báo «đơn mới»
            elif purchase < baseline[0]:
                hold = "historical"
            else:
                hold = None
            if hold:
                # Đơn trước mốc kích hoạt (hoặc chưa kích hoạt): ghi để theo dõi, không gửi.
                enqueue_event(
                    conn, event_key=key, event_type="ORDER_ORDER_NEW", chat_id=int(user), message_html=html,
                    audience="customer", category="order_new", reply_markup_json=keyboard(conversion_id),
                    source_ref=f"conversion:{conversion_id}", suppressed_reason=hold, now=now,
                )
                return
            _queue(conn, cfg, key=key, category="order_new", user=int(user), html=html, conversion_id=conversion_id, now=now)
            return
        lines: list[str] = []
        ineligible = approved = False
        old_cb = new_cb = None
        for change, _change_id in recorded:
            if change.field == "order_status" and (change.new or "").upper() in MEANINGFUL_STATUS:
                lines.append((change.new or "").upper())
            elif change.field == "validation_status":
                if change.new in (REJECTED, FRAUD):
                    ineligible = True
                elif change.new == APPROVED:
                    approved = True
            elif change.field == "net_commission_vnd":
                old = cashback_of(conn, link_id, int(change.old) if change.old not in (None, "") else None)
                new = cashback_of(conn, link_id, int(change.new) if change.new not in (None, "") else None)
                if significant_change(old, new):
                    old_cb, new_cb = old, new
        if not (lines or ineligible or approved or new_cb is not None):
            return
        last = max(change_id for _change, change_id in recorded)
        html = source_text(order_update_notice(order, statuses=lines, ineligible=ineligible, approved=approved,
                                               old_cashback=old_cb, new_cashback=new_cb), conversion_id)
        _queue(conn, cfg, key=f"conversion:{conversion_id}:changes:{last}", category="order_update", user=int(user),
               html=html, conversion_id=conversion_id, now=now)

    return hook
