"""Đồng bộ dữ liệu Shopee Affiliate qua Cookie và đối soát Sub ID (PLAN-065).

Chức năng:
1. Đọc Cookie an toàn từ storage/db/config/shopee_affiliate_cookies.json.
2. Kiểm tra phiên qua /api/v3/user/status. Nếu hết hạn, gửi thông báo cảnh báo Admin.
3. Kéo Click Report qua /api/v1/click_report/list, lưu vào SQLite.
4. Kéo Conversion Report qua /api/v3/report/list, trích xuất mã đơn và hoa hồng.
5. Đối soát sub_id với link_requests.sub_id:
   - Khớp chính xác 100%.
   - Gán matched_link_id và telegram_user_id.
   - Nếu là đơn mới và có Sub ID của bot -> kích hoạt thông báo admin.
6. Cập nhật lịch sử đồng bộ shopee_sync_runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.commission_validation import assess
from cashback_bot import reconciliation
from cashback_bot.db import NARROW_SOURCE, SEEN_SOURCE, TrackingRepository
from cashback_bot.shopee_client import (
    AUTH_EXPIRED,
    NEEDS_AUTH_CATEGORIES,
    PARSE_ERROR,
    RATE_LIMITED,
    TRANSIENT_CATEGORIES,
    ShopeeAffiliateClient,
    ShopeeApiError,
)
from cashback_bot.shopee_cookie import load_cookies
from cashback_bot.redact import error_brief, redact
from cashback_bot.settlement import SettlementEngine

logger = logging.getLogger(__name__)


def parse_shopee_money_vnd(val: Any) -> int | None:
    """Quy đổi số tiền từ API Shopee về VND.

    API nội bộ của web Shopee luôn nhân số tiền lên 100.000 lần. Đối chiếu response thật
    2026-10-23: item_price 39.900.000.000 = 399.000 đ.
    """
    if val is None or val == "":
        return None
    try:
        num = float(str(val).strip())
    except (ValueError, TypeError):
        return None
    return int(round(num / MONEY_SCALE))


def _iso_time(val: Any) -> str | None:
    """Shopee trả unix giây; lưu dạng ISO UTC để so được với các mốc thống kê."""
    if val in (None, "", 0, "0"):
        return None
    try:
        moment = datetime.fromtimestamp(int(val), timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return str(val)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bot_sub_id(val: Any) -> str | None:
    """Báo cáo click trả sub_id gốc; utm_content của đơn ghép sub1..sub5 bằng '-' ('----' là rỗng).

    Bot chỉ dùng sub1 (8 ký tự chữ số, không có '-'), nên lấy phần đầu.
    """
    if not val:
        return None
    first = str(val).strip().split("-", 1)[0]
    return first or None


MONEY_SCALE = 100_000
# Admin bấm 🔄: chỉ đặt cờ này, poller chạy đồng bộ ở vòng kế tiếp rồi nhắn kết quả (PLAN-066).
SYNC_REQUEST_KEY = "shopee_sync_requested"
# Shopee nhận page_size=100 (đã thử thật 2026-10-23).
PAGE_SIZE = 100
# Trần số trang mỗi loại mỗi lần đồng bộ, tránh vòng lặp vô tận nếu Shopee bỏ qua page_no.
MAX_PAGES = 20


# Lỗi tạm ở một trang: thử lại tối đa 2 lần trong lượt (2 giây, 5 giây), rồi bỏ phần đó (lượt thành PARTIAL).
PAGE_RETRY_DELAYS = (2, 5)
TRUNCATED = "TRUNCATED"
PAGINATION_ANOMALY = "PAGINATION_ANOMALY"


@dataclass
class PageStats:
    pages: int = 0
    failed: int = 0
    # Lý do đọc chưa hết (trang lỗi, cấu trúc lạ, quá MAX_PAGES, Shopee lặp trang). Rỗng = đọc trọn.
    problems: list[str] = field(default_factory=list)


class LeaseLost(Exception):
    """Lượt đồng bộ mất quyền giữ khoá (quá hạn / lượt khác thu hồi): dừng ghi ngay."""


def _paged(fetch, start_time: int, end_time: int, list_keys: tuple[str, ...], stats: PageStats | None = None,
           heartbeat: Callable[[], bool] | None = None, sleep: Callable[[float], None] = time.sleep):
    """Duyệt từng trang tới khi trang trả về ít hơn PAGE_SIZE dòng. Bỏ qua dòng không phải dict.

    Không kết luận «hết đơn» khi dữ liệu bất thường: thiếu `data`, không có khoá danh sách, Shopee lặp lại trang,
    hay chạm MAX_PAGES khi trang vẫn đầy đều ghi vào stats.problems (lượt thành PARTIAL). Lỗi tạm thử lại có giới hạn;
    lỗi phiên, 429 và lỗi khác ném ra cho lượt xử lý.
    """
    stats = stats if stats is not None else PageStats()
    previous_first = None
    for page_no in range(1, MAX_PAGES + 1):
        if heartbeat is not None and not heartbeat():
            raise LeaseLost()
        for attempt in range(len(PAGE_RETRY_DELAYS) + 1):
            try:
                payload = fetch(start_time=start_time, end_time=end_time, page_no=page_no, page_size=PAGE_SIZE)
                break
            except ShopeeApiError as exc:
                if getattr(exc, "category", None) not in TRANSIENT_CATEGORIES or attempt == len(PAGE_RETRY_DELAYS):
                    stats.failed += 1
                    raise
                sleep(PAGE_RETRY_DELAYS[attempt])
        stats.pages += 1
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            stats.problems.append(f"{PARSE_ERROR}:page{page_no}")
            return
        rows: Any = next((data[key] for key in list_keys if data.get(key)), None)
        if rows is not None and not isinstance(rows, list):
            stats.problems.append(f"{PARSE_ERROR}:page{page_no}")
            return
        if not rows:
            if not any(key in data for key in list_keys):
                stats.problems.append(f"{PARSE_ERROR}:page{page_no}")
            return
        if rows[0] == previous_first:
            stats.problems.append(f"{PAGINATION_ANOMALY}:page{page_no}")
            return
        previous_first = rows[0]
        for row in rows:
            if isinstance(row, dict):
                yield row
        if len(rows) < PAGE_SIZE:
            return
    stats.problems.append(f"{TRUNCATED}:{MAX_PAGES}")


def _conversion_id(top_item: dict[str, Any], order_dict: dict[str, Any]) -> str:
    """Khoá đơn trong DB: conversion_id, rồi order_id, rồi checkout:order, rồi order_sn (như PLAN-065)."""
    checkout_id = top_item.get("checkout_id") or top_item.get("id") or ""
    order_id = order_dict.get("order_id") or order_dict.get("id") or ""
    order_sn = str(order_dict.get("order_sn") or order_id or checkout_id)
    return str(
        order_dict.get("conversion_id")
        or order_dict.get("order_id")
        or (f"{checkout_id}:{order_id}" if checkout_id and order_id else order_sn)
    )


# PLAN-081 Phương án A: khung hẹp quanh giờ mua khi tra lại một đơn đã ra khung 30 ngày.
LOOKUP_SPAN_SECONDS = 60


def _int(val: Any) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _order_details(top_item: dict[str, Any], order_dict: dict[str, Any], single_order: bool) -> dict[str, Any]:
    """Các ô Doanh số / Số lượng / phí MCN của Addlivetag, lấy từ items của đơn (PLAN-066)."""
    items = [item for item in order_dict.get("items") or [] if isinstance(item, dict)]
    names = [str(item.get("item_name") or "").strip() for item in items if item.get("item_name")]
    item_name = names[0] if names else None
    if item_name and len(names) > 1:
        item_name += f" (+{len(names) - 1} món)"
    validation = top_item.get("report_payment_validation_info")
    month = top_item.get("estimated_validation_month") or (
        validation.get("estimate_validation_month") if isinstance(validation, dict) else None
    )
    return {
        "gmv_vnd": sum(parse_shopee_money_vnd(item.get("actual_amount")) or 0 for item in items),
        "item_qty": sum(_int(item.get("qty")) for item in items),
        "item_name": item_name[:300] if item_name else None,
        # Phí MCN chỉ có ở cấp checkout; checkout nhiều đơn thì không chia được, để 0.
        "mcn_fee_vnd": (parse_shopee_money_vnd(top_item.get("mcn_management_fee_commission")) or 0) if single_order else 0,
        "complete_time": _iso_time(order_dict.get("complete_time")),
        "validation_month": str(month) if month else None,
    }


@dataclass(frozen=True)
class BotOrder:
    """Một đơn qua link bot trong lần đồng bộ, để tin báo 🔄 liệt kê hoa hồng từng đơn."""

    order_sn: str
    item_name: str | None
    gmv_vnd: int | None
    commission_vnd: int | None
    order_status: str
    is_new: bool
    conversion_id: str = ""


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    message: str
    clicks_synced: int = 0
    conversions_synced: int = 0
    new_matched_orders: int = 0
    bot_orders: tuple[BotOrder, ...] = ()
    changes: int = 0  # số thay đổi đã ghi lịch sử trong lần này (PLAN-074)
    # PLAN-080: kết quả lượt (success / partial / failed), loại lỗi, số liệu để ghi shopee_sync_runs.
    status: str = "success"
    category: str | None = None
    retry_after: int | None = None
    run_id: int | None = None
    stats: dict = field(default_factory=dict)


class ShopeeSyncEngine:
    def __init__(
        self,
        repo: TrackingRepository,
        admin_notifier: AdminNotifier | None = None,
        cookie_path: Path | str | None = None,
    ):
        self.repo = repo
        self.admin_notifier = admin_notifier
        self.cookie_path = cookie_path
        self._run_id: int | None = None
        self._changes: list = []  # (order_sn, ConversionChange) của lần đồng bộ đang chạy

    def sync(
        self,
        trigger: str = "manual",
        days_back: int = 30,
        client: ShopeeAffiliateClient | None = None,
        run_id: int | None = None,
        heartbeat: Callable[[], bool] | None = None,
        alert_auth: bool = True,
        sleep: Callable[[float], None] = time.sleep,
        lookups: list[tuple[str, int]] | None = None,
    ) -> SyncResult:
        """Thực hiện đồng bộ toàn diện Clicks và Conversions.

        run_id có sẵn (PLAN-080, lượt do sync_scheduler mở và giữ khoá): engine không tự đóng lượt, trả SyncResult có
        status / category / stats để bên giữ khoá ghi. Không có run_id: tự mở và đóng lượt như trước.
        heartbeat trả False (mất khoá) thì dừng trước trang kế tiếp. alert_auth=False: không tự báo admin cookie hết
        hạn (bộ lập lịch báo theo sự cố, một lần).
        """
        owned = run_id is None
        # 1. Nạp cookie
        if client is None:
            cookies = load_cookies(self.cookie_path)
            if not cookies:
                return SyncResult(
                    ok=False,
                    message="Chưa có Cookie Shopee Affiliate. Hãy vào /admin → 🔗 Shopee Affiliate để kết nối.",
                    status="failed", category=AUTH_EXPIRED, run_id=run_id,
                )
            client = ShopeeAffiliateClient(cookies)

        # 2. Kiểm tra phiên đăng nhập
        status_res = client.check_status()
        if not status_res.ok:
            category = getattr(status_res, "category", None)
            if status_res.auth_failed:
                if category in (None, AUTH_EXPIRED):
                    self._mark_expired(status_res.error_message, alert=alert_auth)
                else:
                    self.repo.update_shopee_cookie_status(status="connected", last_error=status_res.error_message)
                return SyncResult(
                    ok=False,
                    message=f"Cookie Shopee hết hạn hoặc không hợp lệ: {status_res.error_message}",
                    status="failed", category=category or AUTH_EXPIRED, run_id=run_id,
                )
            # Lỗi tạm (mạng, 5xx, 429): giữ trạng thái kết nối để lần tự đồng bộ sau thử lại.
            self.repo.update_shopee_cookie_status(status="connected", last_error=status_res.error_message)
            return SyncResult(ok=False, message=f"Chưa gọi được Shopee, sẽ thử lại sau: {status_res.error_message}",
                              status="failed", category=category, retry_after=getattr(status_res, "retry_after", None),
                              run_id=run_id)

        self.repo.update_shopee_cookie_status(
            status="connected",
            account_name=status_res.username or None,
            last_error=None,
        )

        if owned:
            run_id = self.repo.record_shopee_sync_run(trigger_type=trigger)
        self._run_id = run_id
        self._changes = []
        self._counts = {"new": 0, "changed": 0, "unchanged": 0, "invalid": 0}
        notify_mark = self.repo.notification_mark()
        now_dt = datetime.now(timezone.utc)
        end_time = int(now_dt.timestamp())
        start_time = end_time - (days_back * 86400)
        window = {
            "window_start": datetime.fromtimestamp(start_time, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        clicks_count = 0
        conversions_count = 0
        new_matched_orders = 0
        bot_orders: list[BotOrder] = []
        failed_parts: list[str] = []
        click_pages, order_pages = PageStats(), PageStats()

        def stats() -> dict:
            queued, skipped = self.repo.order_events_after(notify_mark)
            return {
                **window,
                "pages_fetched": click_pages.pages + order_pages.pages,
                "pages_failed": click_pages.failed + order_pages.failed,
                "conversions_new": self._counts["new"],
                "conversions_changed": self._counts["changed"],
                "conversions_unchanged": self._counts["unchanged"],
                "invalid_records": self._counts["invalid"],
                "notifications_queued": queued,
                "notifications_suppressed": skipped,
                "problems": click_pages.problems + order_pages.problems,
            }

        try:
            # 3. Đồng bộ Click Report
            try:
                for item in _paged(client.fetch_clicks, start_time, end_time, ("list",), click_pages, heartbeat, sleep):
                    sub_id = _bot_sub_id(item.get("sub_id") or item.get("utm_content"))
                    click_time = _iso_time(item.get("click_time"))
                    raw_id = item.get("click_id") or item.get("id")
                    if not raw_id:
                        # Tự tạo id duy nhất từ sub_id và thời gian
                        raw_id = "clk_" + hashlib.sha256(f"{sub_id}:{click_time}".encode()).hexdigest()[:16]
                    if self.repo.record_shopee_click(
                        click_id=str(raw_id),
                        sub_id=sub_id,
                        click_time=click_time,
                        raw_json=json.dumps(item, ensure_ascii=False),
                    ):
                        clicks_count += 1
            except ShopeeApiError as exc:
                if exc.status_code in (401, 403) or getattr(exc, "category", None) in NEEDS_AUTH_CATEGORIES | {RATE_LIMITED}:
                    raise
                logger.warning("[ShopeeSync] Đồng bộ click gặp lỗi: %s", error_brief(exc))
                failed_parts.append("click")
            if click_pages.problems and "click" not in failed_parts:
                failed_parts.append("click")

            # 4. Đồng bộ Conversion Report
            try:
                for item in _paged(client.fetch_conversions, start_time, end_time, ("list", "nodes"), order_pages,
                                   heartbeat, sleep):
                    orders = item.get("orders")
                    if isinstance(orders, list) and orders:
                        orders = [order for order in orders if isinstance(order, dict)]
                        for order in orders:
                            conversions_count += 1
                            if self._process_order_item(item, order, single_order=len(orders) == 1, bot_orders=bot_orders):
                                new_matched_orders += 1
                    else:
                        conversions_count += 1
                        if self._process_order_item(item, item, bot_orders=bot_orders):
                            new_matched_orders += 1
            except ShopeeApiError as exc:
                if exc.status_code in (401, 403) or getattr(exc, "category", None) in NEEDS_AUTH_CATEGORIES | {RATE_LIMITED}:
                    raise
                logger.warning("[ShopeeSync] Đồng bộ conversion gặp lỗi: %s", error_brief(exc))
                failed_parts.append("đơn hàng")
            if order_pages.problems and "đơn hàng" not in failed_parts:
                failed_parts.append("đơn hàng")

            # 4b. PLAN-081 Phương án A: tra lại đơn qua bot đang chờ đã ra khung 30 ngày (khung hẹp quanh giờ mua).
            if lookups:
                self._lookup_outside_window(client, lookups, heartbeat)

            # 5. Ghi nhận hoàn thành. Một phần lỗi thì không được báo "xong".
            failed = ", ".join(failed_parts) or None
            run_stats = stats()
            category = None
            if failed:
                problems = run_stats["problems"]
                category = PARSE_ERROR if any(p.startswith(PARSE_ERROR) for p in problems) else "PARTIAL_SYNC"
            if owned:
                self.repo.complete_shopee_sync_run(
                    run_id=run_id,
                    status="partial" if failed else "success",
                    clicks=clicks_count,
                    conversions=conversions_count,
                    new_orders=new_matched_orders,
                    error=f"Lỗi phần: {failed}" if failed else None,
                    category=category,
                    stats=run_stats,
                )
            now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            self.repo.update_shopee_cookie_status(
                status="connected",
                last_sync_at=now_iso,
                last_error=None,
            )

            msg = (
                f"Đồng bộ xong: {clicks_count} click mới · {conversions_count} đơn hàng, "
                f"qua bot {len(bot_orders)} ({new_matched_orders} mới, "
                f"{len(bot_orders) - new_matched_orders} cập nhật)."
            )
            if self._changes:
                msg += f" {len(self._changes)} thay đổi hoa hồng/trạng thái đã ghi lịch sử."
            if failed:
                msg += f" ⚠️ Shopee từ chối phần {failed}, xem log bot. Đơn chưa đọc được giữ nguyên số cũ."
            queued, skipped = run_stats["notifications_queued"], run_stats["notifications_suppressed"]
            if queued or skipped:
                msg += f" Thông báo khách: {queued} chờ gửi, {skipped} bỏ qua (xem /admin → 🔔)."
            significant = [(sn, change) for sn, change in self._changes if change.significant]
            if significant and self.admin_notifier:
                self.admin_notifier.notify_commission_changes(run_id, significant)
            if self._changes:
                # Đơn đã vào kỳ đối soát khớp mà Shopee giảm/thu hồi: ghi điều chỉnh OPEN (PLAN-075), không thu tiền.
                try:
                    SettlementEngine(self.repo).scan_adjustments(actor=f"sync_run:{run_id}")
                except Exception:
                    logger.exception("[ShopeeSync] quét điều chỉnh đối soát lỗi")
            return SyncResult(
                ok=not failed,
                message=msg,
                clicks_synced=clicks_count,
                conversions_synced=conversions_count,
                new_matched_orders=new_matched_orders,
                bot_orders=tuple(bot_orders),
                changes=len(self._changes),
                status="partial" if failed else "success",
                category=category,
                run_id=run_id,
                stats=run_stats,
            )

        except Exception as exc:
            category = getattr(exc, "category", None) if isinstance(exc, ShopeeApiError) else None
            if isinstance(exc, ShopeeApiError) and category is None and exc.status_code in (401, 403):
                category = AUTH_EXPIRED
            lost = isinstance(exc, LeaseLost)
            auth = category == AUTH_EXPIRED
            if auth:
                self._mark_expired(redact(exc)[:200], alert=alert_auth)
            elif category in NEEDS_AUTH_CATEGORIES:
                self.repo.update_shopee_cookie_status(status="connected", last_error=redact(exc)[:200])
            elif lost:
                logger.warning("[ShopeeSync] lượt %s mất khoá, dừng ghi", run_id)
            elif category is None:
                logger.exception("[ShopeeSync] Lỗi không mong muốn trong quá trình đồng bộ")
            else:
                logger.warning("[ShopeeSync] Lượt dừng: %s", error_brief(exc))
            run_stats = stats()
            # Đã ghi được một phần trước khi dừng: PARTIAL, không xoá phần đã ghi.
            wrote = conversions_count > 0 or clicks_count > 0
            status = "partial" if wrote and not lost else "failed"
            if lost:
                category = "LEASE_LOST"
            elif category is None:
                category = "DATABASE_ERROR" if exc.__class__.__module__.startswith("sqlite3") else "UNKNOWN_ERROR"
            if owned:
                self.repo.complete_shopee_sync_run(
                    run_id=run_id,
                    status=status,
                    clicks=clicks_count,
                    conversions=conversions_count,
                    new_orders=new_matched_orders,
                    error=redact(exc)[:200],
                    category=category,
                    stats=run_stats,
                )
            significant = [(sn, change) for sn, change in self._changes if change.significant]
            if significant and self.admin_notifier:
                # Phần đã đọc được trước khi lỗi vẫn đã ghi lịch sử: báo admin như lần thành công.
                self.admin_notifier.notify_commission_changes(run_id, significant)
            message = "Cookie Shopee hết hạn giữa chừng." if auth else f"Lỗi đồng bộ: {type(exc).__name__}"
            return SyncResult(
                ok=False,
                message=message,
                clicks_synced=clicks_count,
                conversions_synced=conversions_count,
                new_matched_orders=new_matched_orders,
                status=status,
                category=category,
                retry_after=getattr(exc, "retry_after", None),
                run_id=run_id,
                stats=run_stats,
            )

    def _lookup_outside_window(self, client, lookups: list[tuple[str, int]], heartbeat) -> None:
        """Một yêu cầu cho mỗi đơn: report/list với purchase_time ±60 giây, 1 trang. Chỉ ghi đúng đơn cần tra, qua
        record_conversion_snapshot (lịch sử thay đổi, snapshot tiền, thông báo PLAN-079 dùng lại nguyên). Ghi kết quả
        từng lần tra; không thấy đơn thì không đổi gì. Lỗi phiên / 429 dừng cả lượt như phần quét chính."""
        now = datetime.now(timezone.utc)
        for conversion_id, purchase in lookups:
            if heartbeat is not None and not heartbeat():
                raise LeaseLost()
            try:
                payload = client.fetch_conversions(start_time=purchase - LOOKUP_SPAN_SECONDS,
                                                   end_time=purchase + LOOKUP_SPAN_SECONDS, page_no=1, page_size=PAGE_SIZE)
            except ShopeeApiError as exc:
                category = getattr(exc, "category", None) or "UNKNOWN_ERROR"
                reconciliation.record_attempt(self.repo, conversion_id, f"error:{category}", now)
                if exc.status_code in (401, 403) or category in NEEDS_AUTH_CATEGORIES | {RATE_LIMITED}:
                    raise
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            rows = (data.get("list") or data.get("nodes") or []) if isinstance(data, dict) else []
            found = False
            self._seen_source = NARROW_SOURCE
            try:
                for item in rows if isinstance(rows, list) else []:
                    if not isinstance(item, dict):
                        continue
                    orders = [o for o in item.get("orders") or [] if isinstance(o, dict)] or [item]
                    for order in orders:
                        if _conversion_id(item, order) == conversion_id:
                            self._process_order_item(item, order, single_order=len(orders) == 1)
                            found = True
            finally:
                self._seen_source = SEEN_SOURCE
            reconciliation.record_attempt(self.repo, conversion_id, "seen" if found else "not_returned", now)

    def _mark_expired(self, reason: str, alert: bool = True) -> None:
        self.repo.update_shopee_cookie_status(status="expired", last_error=reason)
        if alert and self.admin_notifier:
            self.admin_notifier.notify_shopee_cookie_expired(reason)

    def _process_order_item(
        self,
        top_item: dict[str, Any],
        order_dict: dict[str, Any],
        single_order: bool = True,
        bot_orders: list[BotOrder] | None = None,
    ) -> bool:
        """Xử lý từng đơn hàng, lưu DB và gửi thông báo nếu là đơn mới khớp bot.

        Trả về True nếu là đơn mới khớp bot.
        """
        checkout_id = top_item.get("checkout_id") or top_item.get("id") or ""
        order_id = order_dict.get("order_id") or order_dict.get("id") or ""
        order_sn = str(order_dict.get("order_sn") or order_id or checkout_id)
        conversion_id = _conversion_id(top_item, order_dict)

        if not conversion_id.strip():
            # Không có mã đơn nào dùng được: không ghi (tránh gộp nhiều đơn vào khoá rỗng).
            self._counts["invalid"] = self._counts.get("invalid", 0) + 1
            return False

        sub_id_str = _bot_sub_id(
            order_dict.get("sub_id")
            or order_dict.get("utm_content")
            or top_item.get("sub_id")
            or top_item.get("utm_content")
        )

        order_status = str(order_dict.get("order_status") or top_item.get("order_status") or "")
        conversion_status = str(top_item.get("conversion_status") or order_dict.get("conversion_status") or "")
        purchase_time = _iso_time(order_dict.get("purchase_time") or top_item.get("purchase_time"))

        if single_order:
            # gross_commission chỉ là phần Shopee trả; HH gốc = Shopee + shop (trước phí MCN).
            gross_comm = parse_shopee_money_vnd(top_item.get("estimated_total_commission"))
            if gross_comm is None:
                gross_comm = parse_shopee_money_vnd(top_item.get("gross_commission"))
            net_comm = parse_shopee_money_vnd(top_item.get("affiliate_net_commission"))
            if net_comm is None:
                net_comm = gross_comm
        else:
            # Hoa hồng ở cấp checkout là tổng mọi đơn; gán cho từng đơn thì bị cộng trùng.
            # Mỗi món: item_commission (phần Shopee) + capped_brand_commission (phần shop).
            items = [item for item in order_dict.get("items") or [] if isinstance(item, dict)]
            gross_comm = parse_shopee_money_vnd(
                sum(_int(item.get("item_commission")) + _int(item.get("capped_brand_commission")) for item in items)
            )
            net_comm = gross_comm
            # Phí MCN chỉ có ở cấp checkout: chia cho từng đơn theo tỉ lệ net / (net + phí), làm tròn xuống.
            top_net = parse_shopee_money_vnd(top_item.get("affiliate_net_commission"))
            fee = parse_shopee_money_vnd(top_item.get("mcn_management_fee_commission"))
            if gross_comm is not None and top_net is not None and fee and top_net + fee > 0:
                net_comm = gross_comm * top_net // (top_net + fee)

        details = _order_details(top_item, order_dict, single_order)
        result = self.repo.record_conversion_snapshot(
            conversion_id=conversion_id,
            sub_id=sub_id_str,
            order_sn=order_sn,
            order_status=order_status,
            conversion_status=conversion_status,
            purchase_time=purchase_time,
            gross_commission_vnd=gross_comm,
            net_commission_vnd=net_comm,
            raw_json=json.dumps({"top": top_item, "order": order_dict}, ensure_ascii=False),
            details=details,
            assessment=assess(top_item, order_dict, net_comm),
            sync_run_id=self._run_id,
            seen_source=getattr(self, "_seen_source", SEEN_SOURCE),
        )
        is_new, is_matched, user_id = result.is_new, result.is_matched, result.telegram_user_id
        counts = getattr(self, "_counts", None)
        if counts is not None:
            counts["new" if is_new else "changed" if result.changes else "unchanged"] += 1
        if result.changes:
            self._changes.extend((order_sn, change) for change in result.changes)
        if is_matched and bot_orders is not None:
            bot_orders.append(BotOrder(
                order_sn=order_sn,
                item_name=details["item_name"],
                gmv_vnd=details["gmv_vnd"],
                commission_vnd=net_comm,
                order_status=order_status,
                is_new=is_new,
                conversion_id=conversion_id,
            ))

        if is_new and is_matched:
            logger.info("[ShopeeSync] Phát hiện đơn Shopee mới qua link bot! OrderSN=%s SubID=%s", order_sn, sub_id_str)
            if self.admin_notifier:
                username = None
                with self.repo.connect() as conn:
                    u_row = conn.execute("SELECT username FROM telegram_users WHERE telegram_user_id = ?", (user_id,)).fetchone()
                    if u_row:
                        username = u_row["username"]
                self.admin_notifier.notify_shopee_new_order(
                    order_sn=order_sn,
                    sub_id=sub_id_str or "",
                    telegram_user_id=user_id,
                    username=username,
                    commission_vnd=net_comm,
                    order_status=order_status,
                    conversion_id=conversion_id,
                )
            return True

        return False
