"""PLAN-095 (PLAN-085 giai đoạn B): kéo đơn TikTok Shop từ RioHub mỗi 2 giờ, ghi như đơn Shopee.

- Mỗi dòng RioHub (một SKU, khoá `order_id` + `sku_id`) thành một dòng `shopee_conversions` mã `tt:<order>:<sku>`, đi
  qua `record_conversion_snapshot`. Sổ ví, thông báo đơn cho khách, dashboard và 🔍 Tìm dùng chung với Shopee.
- Trạng thái: 1 → PENDING · 2 → COMPLETED (hoa hồng `actual_commission`) · 3 hoặc hoàn hết → CANCELLED.
  Không bao giờ gán APPROVED hay SETTLED: ví TikTok vẫn khoá như Shopee cho tới khi có nguồn đối soát tiền thật.
- Cột `pit` (thuế TNCN) giữ trong raw_json. Đơn thật 26/10 có pit = 0; cách tính hoàn dùng chung chính sách Shopee.
- Chạy trong luồng nền của bot Telegram (không chặn vòng poll); mốc lần trước lưu ở bot_state, chồng lấn 10 phút.
  Chỉ đọc RioHub (`GET /orders`), không gọi Shopee.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from cashback_bot.commission_validation import PENDING, REJECTED, Assessment
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import TIKTOK_CONVERSION_PREFIX
from cashback_bot.riohub_client import RioHubClient, RioHubError, parse_order, sync_window, to_vnd

logger = logging.getLogger("cashback_bot")

INTERVAL_SEC = 2 * 3600
# RioHub có thể ghi đơn trễ: mỗi lượt đọc lại 24 giờ trước mốc cũ (ghi lại y hệt không tạo dòng mới).
OVERLAP_SEC = 24 * 3600
RETRY_SEC = 15 * 60
SEEN_SOURCE = "riohub_orders"
LAST_END_KEY = "tiktok_sync_last_end"
ATTEMPT_KEY = "tiktok_sync_last_attempt"
OK_KEY = "tiktok_sync_last_ok"
ERROR_KEY = "tiktok_sync_last_error"
COUNT_KEY = "tiktok_sync_last_count"
STATUS = {1: "PENDING", 2: "COMPLETED", 3: "CANCELLED"}
_running = threading.Lock()


@dataclass(frozen=True)
class SyncResult:
    rows: int
    matched_new: int
    skipped: int


def _stamp(unix: int | None) -> str | None:
    if not unix:
        return None
    return datetime.fromtimestamp(int(unix), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(value: object) -> str | None:
    """`settled_at_iso` / `time_delivered_iso` → mốc UTC của bot. Sai dạng → None."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(repo: TrackingRepository, row: dict, now: datetime) -> bool | None:
    """Ghi một dòng đơn. True: lần đầu khớp link bot · False: đã ghi · None: dòng thiếu khoá / trạng thái lạ (bỏ qua)."""
    order = parse_order(row)
    if order is None:
        return None
    status = "CANCELLED" if order.fully_refunded else STATUS[order.status]
    commission = order.actual_commission_vnd if status == "COMPLETED" and order.actual_commission_vnd is not None \
        else order.est_commission_vnd
    if status == "CANCELLED":
        commission = None  # giữ số đã ghi: đơn huỷ không được làm «hoàn tạm tính» tăng lên
    if status == "CANCELLED":
        assessment = Assessment(REJECTED, "order_cancelled", 0, None, order.settlement_status, True)
    else:
        reason = "tiktok_settled_unverified" if status == "COMPLETED" else "tiktok_pending"
        assessment = Assessment(PENDING, reason, 0, None, order.settlement_status, True)
    complete = None
    if status == "COMPLETED":
        complete = _iso(row.get("settled_at_iso")) or _iso(row.get("time_delivered_iso")) or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    quantity = row.get("quantity")
    gmv = to_vnd(row.get("commission_gmv"))
    if gmv is None and (price := to_vnd(row.get("price"))) is not None and isinstance(quantity, int):
        gmv = price * quantity
    result = repo.record_conversion_snapshot(
        conversion_id=f"{TIKTOK_CONVERSION_PREFIX}{order.order_id}:{order.sku_id}",
        sub_id=order.sub_id,
        order_sn=order.order_id,
        order_status=status,
        conversion_status=str(order.status),
        purchase_time=_stamp(order.create_time) or _iso(row.get("time_created_iso")),
        gross_commission_vnd=commission,
        net_commission_vnd=commission,
        raw_json=json.dumps({"riohub": row}, ensure_ascii=False),
        details={
            "item_name": (row.get("product_name") or None),
            "gmv_vnd": gmv,
            "item_qty": quantity if isinstance(quantity, int) else None,
            "complete_time": complete,
        },
        assessment=assessment,
        seen_source=SEEN_SOURCE,
        platform="tiktok",
    )
    return result.is_new and result.is_matched


def run(repo: TrackingRepository, client: RioHubClient, now: datetime | None = None) -> SyncResult | None:
    """Một lượt kéo đơn. Lỗi RioHub: ghi lỗi vào bot_state, trả None (mốc không đổi, lần sau kéo lại)."""
    moment = now or datetime.now(timezone.utc)
    stamp = int(moment.timestamp())
    raw_end = repo.get_state(LAST_END_KEY)
    start, end = sync_window(int(raw_end) if raw_end and raw_end.isdigit() else None, stamp, overlap_sec=OVERLAP_SEC)
    rows = matched = skipped = 0
    try:
        for row in client.iter_orders(start, end):
            rows += 1
            outcome = record(repo, row, moment)
            if outcome is None:
                skipped += 1
            elif outcome:
                matched += 1
    except RioHubError as exc:
        repo.set_state(ERROR_KEY, f"{exc.kind}:{exc.code or exc.status_code or '-'}")
        logger.error("[Cashback] đồng bộ đơn TikTok lỗi kind=%s code=%s", exc.kind, exc.code or "-")
        return None
    repo.set_state(LAST_END_KEY, str(end))
    repo.set_state(OK_KEY, str(stamp))
    repo.set_state(COUNT_KEY, json.dumps({"rows": rows, "matched_new": matched, "skipped": skipped}))
    repo.set_state(ERROR_KEY, "")
    logger.info("[Cashback] đồng bộ đơn TikTok ok rows=%s matched_new=%s skipped=%s", rows, matched, skipped)
    return SyncResult(rows, matched, skipped)


def due(repo: TrackingRepository, now: float) -> bool:
    try:
        last = float(repo.get_state(ATTEMPT_KEY) or 0)
    except ValueError:
        last = 0.0
    wait = RETRY_SEC if repo.get_state(ERROR_KEY) else INTERVAL_SEC
    return now - last >= wait


def maybe_start(repo: TrackingRepository, client: RioHubClient | None, admin_notifier=None,
                now: float | None = None) -> threading.Thread | None:
    """Gọi mỗi vòng poll. Tới hạn và chưa có lượt nào đang chạy thì chạy một lượt trong luồng nền."""
    moment = time.time() if now is None else now
    if client is None or not due(repo, moment) or not _running.acquire(blocking=False):
        return None
    repo.set_state(ATTEMPT_KEY, str(moment))

    def work() -> None:
        try:
            result = run(repo, client)
            if admin_notifier is not None:
                day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if result is None:
                    kind = (repo.get_state(ERROR_KEY) or "unknown").split(":", 1)[0]
                    admin_notifier.notify_tiktok_sync_failed(day, kind)
                elif result.matched_new:
                    admin_notifier.notify_tiktok_new_orders(str(int(moment)), result.matched_new)
        except Exception:
            logger.exception("[Cashback] đồng bộ đơn TikTok lỗi bất ngờ")
            repo.set_state(ERROR_KEY, "unexpected")
        finally:
            _running.release()

    thread = threading.Thread(target=work, name="tiktok-sync", daemon=True)
    thread.start()
    return thread
