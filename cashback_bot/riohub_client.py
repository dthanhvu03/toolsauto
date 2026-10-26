"""Client RioHub × TikTok Shop Affiliate (PLAN-085 giai đoạn A). CHƯA nối vào luồng khách.

Theo spec tích hợp RioHub bản 09/10/2026 (`reports/CASHBACK_TIKTOK_RIOHUB_RESEARCH.md`). Chỉ phần bot cần:
- tạo link riêng cho từng khách theo `sub_id` (`/links`, `/product-links`);
- tra giá + hoa hồng (`/products`) để báo hoàn tiền dự kiến;
- kéo đơn theo thời điểm cập nhật (`/orders`), vì bot không có HTTPS công khai cho webhook.
Không làm: `/general-links` + `event_id` (cần trang chuyển hướng), tìm sản phẩm theo tên, webhook.

Khoá API gửi trong header `X-Riohub-Api-Key`; log chỉ ghi đường dẫn, mã HTTP và mã lỗi, không ghi khoá hay tham số.
Tiền là chuỗi decimal: đổi sang đồng nguyên bằng Decimal, làm tròn xuống, không qua float.

Thử tay (chủ bot chạy, mỗi lần đã được duyệt; cần RIOHUB_API_KEY và RIOHUB_CREATOR_USERNAME trong .env):
    .venv/bin/python -m cashback_bot.riohub_client products <product_id>
    .venv/bin/python -m cashback_bot.riohub_client link <link sản phẩm> <sub_id thử>
    .venv/bin/python -m cashback_bot.riohub_client orders --days 7
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path

import requests

from cashback_bot.config import ConfigError, load_settings
from cashback_bot.redact import RedactingFormatter

logger = logging.getLogger("cashback_bot")

# Thử lần lượt; chỉ đổi tên miền khi lỗi kết nối / DNS / quá giờ, không đổi khi API trả 4xx/5xx.
BASE_URLS = (
    "https://riohub.vn/api/v1",
    "https://riohub.riokupon.com/api/v1",
    "https://riohub.riokupon.me/api/v1",
)
PREFIX = "/partner/tiktok/affiliate"
SUB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_SUB_PARTS = 4
PRODUCTS_PER_CALL = 100
ORDERS_PAGE_SIZE = 200
SYNC_OVERLAP_SEC = 600
RETRY_AFTER_CAP_SEC = 30


class RioHubError(Exception):
    """Lỗi gọi RioHub. kind không chứa khoá hay nội dung khách.

    kind: auth (401 khoá sai) · creator (403 / 404 / 424 token TikTok của creator hỏng: kết nối lại, đừng đổi khoá) ·
    not_promotable (422 sản phẩm không có hoa hồng, không thử lại) · invalid (422 khác) · rate_limited (429) ·
    unavailable (503, thử lại không giúp) · transient (5xx khác, thử lại có giãn cách) · network (cả 3 tên miền lỗi) ·
    bad_response (trả về không đúng dạng spec).
    """

    def __init__(self, kind: str, status_code: int | None = None, code: str | None = None,
                 retry_after: int | None = None, message: str | None = None):
        self.kind = kind
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after
        self.message = message
        super().__init__(kind if code is None else f"{kind}:{code}")


@dataclass(frozen=True)
class ProductLink:
    affiliate_link: str
    product_id: str | None
    product: dict | None
    product_error: str | None


@dataclass(frozen=True)
class TikTokOrder:
    """Một dòng đơn (một SKU). Khoá: (order_id, sku_id)."""

    order_id: str
    sku_id: str
    product_id: str | None
    sub_id: str | None
    trace_id: str | None
    trace_type: str | None
    status: int  # 1 chờ · 2 đã chốt · 3 huỷ / hoàn
    settlement_status: str | None
    fully_refunded: bool
    est_commission_vnd: int | None
    actual_commission_vnd: int | None  # đã trừ chia MCN, TNCN 10%, phí reward; None khi chưa đối soát
    create_time: int | None
    update_time: int | None
    settled_at_iso: str | None


def validate_sub_id(sub_id: str) -> str:
    """1–128 ký tự [A-Za-z0-9_-]; RioHub tách theo dấu `-` thành tối đa 4 phần."""
    if not isinstance(sub_id, str) or not SUB_ID_RE.match(sub_id) or len(sub_id.split("-")) > MAX_SUB_PARTS:
        raise ValueError("sub_id phải 1–128 ký tự [A-Za-z0-9_-], tối đa 4 phần nối bằng '-'")
    return sub_id


def to_vnd(value: object) -> int | None:
    """Chuỗi decimal ("12.50") → đồng nguyên, làm tròn xuống. Rỗng / sai dạng → None."""
    if value is None or isinstance(value, bool) or isinstance(value, float):
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    return int(amount.to_integral_value(rounding=ROUND_DOWN))


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def product_id_of(product: dict) -> str | None:
    """Sản phẩm là dữ liệu TikTok chuyển thẳng: đọc phòng thủ."""
    return _text(product.get("id") or product.get("product_id"))


def product_title(product: dict) -> str | None:
    return _text(product.get("title") or product.get("product_name"))


def product_image(product: dict) -> str | None:
    return _text(product.get("main_image_url") or product.get("cover_url") or product.get("image_url"))


def commission_rate_bps(product: dict) -> int | None:
    """Tỷ lệ hoa hồng TỔNG để báo giá, số thô (600 = 6% = 600 bps).

    `observed_commission.commission_rate` (lấy từ đơn gần nhất) nếu có; không thì `commission.rate` +
    `shop_ads_commission.rate`. `commission.rate` một mình chỉ là tỷ lệ chuẩn, thiếu hoa hồng thưởng.
    """
    observed = product.get("observed_commission")
    if isinstance(observed, dict):
        rate = _int(observed.get("commission_rate"))
        if rate is not None:
            return rate
    commission = product.get("commission")
    base = _int(commission.get("rate")) if isinstance(commission, dict) else _int(product.get("commission_rate"))
    if base is None:
        return None
    ads = product.get("shop_ads_commission")
    extra = _int(ads.get("rate")) if isinstance(ads, dict) else None
    return base + (extra or 0)


def price_range_vnd(product: dict) -> tuple[int, int] | None:
    """(thấp, cao) theo `sales_price`, rỗng thì `original_price`. Không có giá → None."""
    for key in ("sales_price", "original_price"):
        price = product.get(key)
        if not isinstance(price, dict):
            continue
        low, high = to_vnd(price.get("minimum_amount")), to_vnd(price.get("maximum_amount"))
        if low is None and high is None:
            continue
        low = high if low is None else low
        high = low if high is None else high
        return min(low, high), max(low, high)
    return None


def parse_order(row: dict) -> TikTokOrder | None:
    """Chỉ dùng field có trong spec. Thiếu khoá đơn hoặc trạng thái lạ → None (bỏ qua, ghi log ở nơi gọi)."""
    order_id, sku_id, status = _text(row.get("order_id")), _text(row.get("sku_id")), _int(row.get("status"))
    if order_id is None or sku_id is None or status not in (1, 2, 3):
        return None
    return TikTokOrder(
        order_id=order_id,
        sku_id=sku_id,
        product_id=_text(row.get("product_id")),
        sub_id=_text(row.get("sub_id")),
        trace_id=_text(row.get("trace_id")),
        trace_type=_text(row.get("trace_type")),
        status=status,
        settlement_status=_text(row.get("settlement_status")),
        fully_refunded=_int(row.get("fully_refunded")) == 1,
        est_commission_vnd=to_vnd(row.get("est_commission")),
        actual_commission_vnd=to_vnd(row.get("actual_commission")),
        create_time=_int(row.get("create_time")),
        update_time=_int(row.get("update_time")),
        settled_at_iso=_text(row.get("settled_at_iso")),
    )


def sync_window(last_end: int | None, now: int, first_lookback_sec: int = 7 * 86_400) -> tuple[int, int]:
    """Mốc kéo đơn: từ lần trước trừ 10 phút (chồng lấn để không sót) tới bây giờ. Lưu `now` sau khi chạy xong."""
    start = now - first_lookback_sec if last_end is None else last_end - SYNC_OVERLAP_SEC
    return max(0, start), now


class RioHubClient:
    def __init__(self, api_key: str, creator_username: str, timeout: float = 20,
                 base_urls: tuple[str, ...] = BASE_URLS, max_retries: int = 1,
                 sleep: Callable[[float], None] = time.sleep):
        if not api_key or not creator_username:
            raise ValueError("cần RIOHUB_API_KEY và RIOHUB_CREATOR_USERNAME")
        self._headers = {"X-Riohub-Api-Key": api_key, "Accept": "application/json"}
        self._creator = creator_username
        self._timeout = timeout
        self._base_urls = base_urls
        self._max_retries = max_retries
        self._sleep = sleep

    def create_link(self, product: str, sub_id: str) -> str:
        """Link affiliate gắn `sub_id` (`POST /links`)."""
        payload = self._request("POST", "/links", body=self._link_body(product, sub_id))
        link = _text(payload.get("affiliate_link"))
        if link is None:
            raise RioHubError("bad_response", code="no_affiliate_link")
        return link

    def create_product_link(self, product: str, sub_id: str) -> ProductLink:
        """Link + tên / ảnh / giá / hoa hồng trong một lượt (`POST /product-links`).

        Thông tin sản phẩm là best-effort: `product` có thể None (xem `product_error`), link vẫn dùng được.
        """
        payload = self._request("POST", "/product-links", body=self._link_body(product, sub_id))
        link = _text(payload.get("affiliate_link"))
        if link is None:
            raise RioHubError("bad_response", code="no_affiliate_link")
        detail = payload.get("product")
        return ProductLink(
            affiliate_link=link,
            product_id=_text(payload.get("product_id")),
            product=detail if isinstance(detail, dict) else None,
            product_error=_text(payload.get("product_error")),
        )

    def get_products(self, product_ids: list[str]) -> tuple[list[dict], list[str]]:
        """Thông tin sản phẩm, gom tối đa 100 id mỗi lượt (RioHub lưu đệm 24 giờ). Trả (sản phẩm, id không lấy được)."""
        found: list[dict] = []
        missing: list[str] = []
        ids = list(dict.fromkeys(str(item) for item in product_ids))
        for index in range(0, len(ids), PRODUCTS_PER_CALL):
            chunk = ids[index:index + PRODUCTS_PER_CALL]
            payload = self._request("GET", "/products", params={
                "creator_username": self._creator, "product_id": ",".join(chunk),
            })
            found += [item for item in payload.get("products") or [] if isinstance(item, dict)]
            missing += [str(item) for item in payload.get("not_found") or []]
        return found, missing

    def iter_orders(self, update_start: int, update_end: int) -> Iterator[dict]:
        """Mọi đơn có thời điểm cập nhật trong [update_start, update_end), lặp hết trang (200 / trang)."""
        page = 1
        while True:
            payload = self._request("GET", "/orders", params={
                "creator_username": self._creator,
                "update_time_start": update_start,
                "update_time_end": update_end,
                "page": page,
                "page_size": ORDERS_PAGE_SIZE,
            })
            rows = [row for row in payload.get("orders") or [] if isinstance(row, dict)]
            yield from rows
            total = _int(payload.get("total")) or 0
            if not rows or page * ORDERS_PAGE_SIZE >= total:
                return
            page += 1

    def _link_body(self, product: str, sub_id: str) -> dict:
        target = str(product).strip()
        if not target:
            raise ValueError("thiếu link hoặc mã sản phẩm")
        key = "product_id" if target.isdigit() else "product_url"
        return {"creator_username": self._creator, key: target, "sub_id": validate_sub_id(sub_id)}

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        attempt = 0
        while True:
            try:
                return self._send(method, path, params, body)
            except RioHubError as exc:
                if exc.kind != "rate_limited" or attempt >= self._max_retries:
                    raise
                attempt += 1
                self._sleep(min(exc.retry_after or 1, RETRY_AFTER_CAP_SEC))

    def _send(self, method: str, path: str, params: dict | None, body: dict | None) -> dict:
        response = None
        for base in self._base_urls:
            try:
                response = requests.request(method, f"{base}{PREFIX}{path}", headers=self._headers, params=params,
                                            json=body, timeout=self._timeout)
                break
            except (requests.ConnectionError, requests.Timeout) as exc:
                logger.warning("[Cashback] riohub %s %s lỗi mạng: %s", method, path, type(exc).__name__)
        if response is None:
            raise RioHubError("network")
        code = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if code < 400:
            if not isinstance(payload, dict):
                raise RioHubError("bad_response", status_code=code)
            return payload
        # Thử thật 2026-10-25: {"error": {"code": "mcn_membership_required", "message": "..."}}. Vẫn nhận dạng
        # phẳng {"error": "..."} / {"code": "..."} vì spec không ghi tên field.
        error = message = None
        if isinstance(payload, dict):
            raw = payload.get("error")
            if isinstance(raw, dict):
                error, message = _text(raw.get("code")), _text(raw.get("message"))
            else:
                error, message = _text(raw or payload.get("code")), _text(payload.get("message"))
        logger.error("[Cashback] riohub %s %s http=%s error=%s", method, path, code, error or "-")
        raise RioHubError(_kind(code, error), status_code=code, code=error, retry_after=_retry_after(response),
                          message=message)


def _kind(code: int, error: str | None) -> str:
    if code == 401:
        return "auth"
    if code in (403, 404, 424):
        return "creator"
    if code == 422:
        return "not_promotable" if error == "product_not_promotable" else "invalid"
    if code == 429:
        return "rate_limited"
    if code == 503:
        return "unavailable"
    return "transient" if code >= 500 else "invalid"


def _retry_after(response: requests.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    return int(raw) if raw and raw.strip().isdigit() else None


def _default_dotenv() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def configure_logging() -> None:
    """CLI thử tay: log qua RedactingFormatter (che khoá API). Không import poller: poller → service → client."""
    fmt = "%(asctime)s [Cashback] %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(fmt))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m cashback_bot.riohub_client")
    sub = parser.add_subparsers(dest="cmd", required=True)
    products = sub.add_parser("products", help="tra giá + hoa hồng")
    products.add_argument("product_ids", nargs="+")
    link = sub.add_parser("link", help="tạo 1 link thử (kèm thông tin sản phẩm)")
    link.add_argument("product")
    link.add_argument("sub_id")
    orders = sub.add_parser("orders", help="đếm đơn cập nhật trong N ngày (chỉ đọc)")
    orders.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    configure_logging()
    try:
        settings = load_settings(dotenv_path=_default_dotenv())
    except ConfigError as exc:
        raise SystemExit(f"cấu hình: {exc}") from exc
    if not settings.riohub_api_key or not settings.riohub_creator_username:
        raise SystemExit("thiếu RIOHUB_API_KEY hoặc RIOHUB_CREATOR_USERNAME trong .env")
    client = RioHubClient(settings.riohub_api_key, settings.riohub_creator_username)
    try:
        _run(client, args)
    except RioHubError as exc:
        raise SystemExit(f"RioHub lỗi: {exc.kind} http={exc.status_code or '-'} mã={exc.code or '-'}"
                         f" — {exc.message or ''}") from exc


def _run(client: RioHubClient, args: argparse.Namespace) -> None:
    if args.cmd == "products":
        found, missing = client.get_products(args.product_ids)
        for item in found:
            print(product_id_of(item), product_title(item), price_range_vnd(item), commission_rate_bps(item), "bps")
        if missing:
            print("không lấy được:", ", ".join(missing))
    elif args.cmd == "link":
        result = client.create_product_link(args.product, args.sub_id)
        print(result.affiliate_link)
        if result.product:
            item = result.product
            print(product_title(item), price_range_vnd(item), commission_rate_bps(item), "bps")
        else:
            print("không có thông tin sản phẩm:", result.product_error or "-")
    else:
        start, end = sync_window(None, int(time.time()), first_lookback_sec=args.days * 86_400)
        counts = {1: 0, 2: 0, 3: 0}
        skipped = 0
        for row in client.iter_orders(start, end):
            order = parse_order(row)
            if order is None:
                skipped += 1
                continue
            counts[order.status] += 1
        print(f"chờ={counts[1]} đã chốt={counts[2]} huỷ/hoàn={counts[3]} bỏ qua={skipped}")


if __name__ == "__main__":
    main()
