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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.db import TrackingRepository
from cashback_bot.shopee_client import ShopeeAffiliateClient, ShopeeApiError
from cashback_bot.shopee_cookie import load_cookies
from cashback_bot.redact import error_brief, redact

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
# Tự đồng bộ 4 giờ: chỉ chạy khi admin bật ("1"). Mặc định tắt, admin tự bấm 🔄.
AUTO_SYNC_KEY = "shopee_auto_sync"
# Shopee nhận page_size=100 (đã thử thật 2026-10-23).
PAGE_SIZE = 100
# Trần số trang mỗi loại mỗi lần đồng bộ, tránh vòng lặp vô tận nếu Shopee bỏ qua page_no.
MAX_PAGES = 20


def _paged(fetch, start_time: int, end_time: int, list_keys: tuple[str, ...]):
    """Duyệt từng trang tới khi trang trả về ít hơn PAGE_SIZE dòng. Bỏ qua dòng không phải dict."""
    previous_first = None
    for page_no in range(1, MAX_PAGES + 1):
        payload = fetch(start_time=start_time, end_time=end_time, page_no=page_no, page_size=PAGE_SIZE)
        data = payload.get("data") if isinstance(payload, dict) else None
        rows: Any = None
        if isinstance(data, dict):
            rows = next((data[key] for key in list_keys if data.get(key)), None)
        if not isinstance(rows, list) or not rows or rows[0] == previous_first:
            return
        previous_first = rows[0]
        for row in rows:
            if isinstance(row, dict):
                yield row
        if len(rows) < PAGE_SIZE:
            return


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

    def sync(
        self,
        trigger: str = "manual",
        days_back: int = 30,
        client: ShopeeAffiliateClient | None = None,
    ) -> SyncResult:
        """Thực hiện đồng bộ toàn diện Clicks và Conversions."""
        # 1. Nạp cookie
        if client is None:
            cookies = load_cookies(self.cookie_path)
            if not cookies:
                return SyncResult(
                    ok=False,
                    message="Chưa có Cookie Shopee Affiliate. Hãy vào /admin → 🔗 Shopee Affiliate để kết nối.",
                )
            client = ShopeeAffiliateClient(cookies)

        # 2. Kiểm tra phiên đăng nhập
        status_res = client.check_status()
        if not status_res.ok:
            if status_res.auth_failed:
                self._mark_expired(status_res.error_message)
                return SyncResult(
                    ok=False,
                    message=f"Cookie Shopee hết hạn hoặc không hợp lệ: {status_res.error_message}",
                )
            # Lỗi tạm (mạng, 5xx, 429): giữ trạng thái kết nối để lần tự đồng bộ sau thử lại.
            self.repo.update_shopee_cookie_status(status="connected", last_error=status_res.error_message)
            return SyncResult(ok=False, message=f"Chưa gọi được Shopee, sẽ thử lại sau: {status_res.error_message}")

        self.repo.update_shopee_cookie_status(
            status="connected",
            account_name=status_res.username or None,
            last_error=None,
        )

        run_id = self.repo.record_shopee_sync_run(trigger_type=trigger)
        now_dt = datetime.now(timezone.utc)
        end_time = int(now_dt.timestamp())
        start_time = end_time - (days_back * 86400)

        clicks_count = 0
        conversions_count = 0
        new_matched_orders = 0
        bot_orders: list[BotOrder] = []
        failed_parts: list[str] = []

        try:
            # 3. Đồng bộ Click Report
            try:
                for item in _paged(client.fetch_clicks, start_time, end_time, ("list",)):
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
                if exc.status_code in (401, 403):
                    raise
                logger.warning("[ShopeeSync] Đồng bộ click gặp lỗi: %s", error_brief(exc))
                failed_parts.append("click")

            # 4. Đồng bộ Conversion Report
            try:
                for item in _paged(client.fetch_conversions, start_time, end_time, ("list", "nodes")):
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
                if exc.status_code in (401, 403):
                    raise
                logger.warning("[ShopeeSync] Đồng bộ conversion gặp lỗi: %s", error_brief(exc))
                failed_parts.append("đơn hàng")

            # 5. Ghi nhận hoàn thành. Một phần lỗi thì không được báo "xong".
            failed = ", ".join(failed_parts) or None
            self.repo.complete_shopee_sync_run(
                run_id=run_id,
                status="partial" if failed else "success",
                clicks=clicks_count,
                conversions=conversions_count,
                new_orders=new_matched_orders,
                error=f"Lỗi phần: {failed}" if failed else None,
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
            if failed:
                msg += f" ⚠️ Shopee từ chối phần {failed}, xem log bot."
            return SyncResult(
                ok=not failed,
                message=msg,
                clicks_synced=clicks_count,
                conversions_synced=conversions_count,
                new_matched_orders=new_matched_orders,
                bot_orders=tuple(bot_orders),
            )

        except Exception as exc:
            auth = isinstance(exc, ShopeeApiError) and exc.status_code in (401, 403)
            if auth:
                self._mark_expired(redact(exc)[:200])
            else:
                logger.exception("[ShopeeSync] Lỗi không mong muốn trong quá trình đồng bộ")
            self.repo.complete_shopee_sync_run(
                run_id=run_id,
                status="failed",
                clicks=clicks_count,
                conversions=conversions_count,
                new_orders=new_matched_orders,
                error=redact(exc)[:200],
            )
            message = "Cookie Shopee hết hạn giữa chừng." if auth else f"Lỗi đồng bộ: {type(exc).__name__}"
            return SyncResult(
                ok=False,
                message=message,
                clicks_synced=clicks_count,
                conversions_synced=conversions_count,
                new_matched_orders=new_matched_orders,
            )

    def _mark_expired(self, reason: str) -> None:
        self.repo.update_shopee_cookie_status(status="expired", last_error=reason)
        if self.admin_notifier:
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

        conversion_id = str(
            order_dict.get("conversion_id")
            or order_dict.get("order_id")
            or (f"{checkout_id}:{order_id}" if checkout_id and order_id else order_sn)
        )

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

        details = _order_details(top_item, order_dict, single_order)
        is_new, is_matched, link_id, user_id = self.repo.record_shopee_conversion(
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
        )
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
                )
            return True

        return False
