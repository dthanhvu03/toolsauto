"""Báo giảm giá món khách từng xem (reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md, mục 2A; chủ bot duyệt 2026-10-27).

- Tắt mặc định: admin bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale (`bot_state.price_drop_enabled`).
- Mỗi tối một lượt, trong khung 19:00–21:30 giờ VN, chạy ở luồng nền như đồng bộ TikTok.
- Món xét: link Shopee 30 ngày gần nhất, có hoàn, chưa có đơn khớp. Giá hôm nay lấy từ AddLiveTag
  `price-tracking/history.php` (50 món / lần, khoá `ADDLIVETAG_API_KEY`).
- Giá hôm nay thấp hơn giá lúc tạo link từ 15% và còn hàng thì nhắn khách, kèm nút mua bằng link cũ.
- Mỗi khách tối đa 1 món / lượt; dùng chung ngân sách 1 tin / 7 ngày với nhắc link chưa dùng; mỗi link báo 1 lần;
  nhường tối có nhắc sale; tôn trọng mục 🛒 Nhắc ở /thongbao và chặn bot.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from cashback_bot import engagement, sale_calendar
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BUY_BUTTON, price_drop
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason

logger = logging.getLogger("cashback_bot")

HISTORY_URL = "https://data.addlivetag.com/price-tracking/history.php"
ENABLED_KEY = "price_drop_enabled"
LAST_DAY_KEY = "price_drop_last_day"
RESULT_KEY = "price_drop_last_result"
DROP_MIN = 0.15
WATCH_DAYS = 30
BATCH = 50
MAX_ITEMS = 200
_running = threading.Lock()


class PriceWatchError(Exception):
    pass


@dataclass(frozen=True)
class PricePoint:
    price: int
    flash_sale: bool
    in_stock: bool | None


def _point(raw: dict) -> PricePoint | None:
    """Giá 0 (flash sale ẩn giá) thì bỏ. Dữ liệu thật 2026-10-27: `stockAvailable` = 0 ở cả món đang bán bình thường,
    trường này chỉ là suất flash sale, nên chỉ coi là hết hàng khi đang flash sale mà suất bằng 0."""
    try:
        price = int(float(raw.get("price")))
    except (TypeError, ValueError):
        return None
    flash = bool(raw.get("flashSale"))
    stock = raw.get("stockAvailable")
    in_stock = None if not flash or stock is None else bool(stock)
    return PricePoint(price, flash, in_stock) if price > 0 else None


@dataclass(frozen=True)
class PriceStats:
    """Giá hôm nay so với 30 ngày (bỏ điểm giá 0 của flash sale ẩn giá)."""

    price: int
    usual: int  # trung vị
    lowest: int
    flash_sale: bool
    in_stock: bool | None
    last_date: str


class PriceHistoryClient:
    def __init__(self, api_key: str, url: str = HISTORY_URL, timeout: float = 20):
        self._api_key = api_key
        self._url = url
        self._timeout = timeout

    def points(self, item_ids: list[int], days: int = 7) -> dict[int, list[dict]]:
        """Các điểm giá theo ngày của từng món (đã sắp theo ngày). Lỗi mạng hay phản hồi lạ: PriceWatchError."""
        found: dict[int, list[dict]] = {}
        for start in range(0, len(item_ids), BATCH):
            body = {"item_ids": item_ids[start:start + BATCH], "type": "price", "days": days, "no_product": 1}
            try:
                response = requests.post(self._url, json=body, headers={"X-API-Key": self._api_key},
                                         timeout=self._timeout)
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise PriceWatchError(type(exc).__name__) from exc
            if response.status_code != 200 or not isinstance(payload.get("items"), list):
                raise PriceWatchError(f"http_{response.status_code}")
            for item in payload["items"]:
                raw = ((item.get("price") or {}).get("points") or []) if item.get("status") == "success" else []
                rows = sorted((p for p in raw if isinstance(p, dict)),
                              key=lambda p: (str(p.get("date") or ""), str(p.get("recordedTime") or "")))
                try:
                    item_id = int(item.get("itemId"))
                except (TypeError, ValueError):
                    continue
                if rows:
                    found[item_id] = rows
        return found

    def latest(self, item_ids: list[int]) -> dict[int, PricePoint]:
        """Giá mới nhất của từng món (bỏ món không có dữ liệu hay điểm cuối không đọc được)."""
        found: dict[int, PricePoint] = {}
        for item_id, rows in self.points(item_ids).items():
            point = _point(rows[-1])
            if point is not None:
                found[item_id] = point
        return found

    def stats(self, item_ids: list[int], days: int = 30) -> dict[int, PriceStats]:
        found: dict[int, PriceStats] = {}
        for item_id, rows in self.points(item_ids, days).items():
            last = _point(rows[-1])
            prices = sorted(p.price for p in (_point(r) for r in rows) if p is not None)
            if last is None or len(prices) < 7:
                continue  # điểm cuối ẩn giá hay quá ít ngày: không đủ để nói «rẻ hơn thường ngày»
            usual = prices[len(prices) // 2]
            found[item_id] = PriceStats(last.price, usual, prices[0], last.flash_sale, last.in_stock,
                                        str(rows[-1].get("date") or ""))
        return found


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(ENABLED_KEY) == "1"


def last_result_text(repo: TrackingRepository) -> str:
    try:
        data = json.loads(repo.get_state(RESULT_KEY) or "{}")
    except ValueError:
        data = {}
    if not data:
        return "chưa chạy lần nào"
    when = (data.get("at") or "")[:10]
    return f"lượt {when}: 🔴 lỗi {data['error']}" if data.get("error") else f"lượt {when}: {data.get('sent', 0)} tin"


def candidates(conn: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    """Link Shopee mới nhất của mỗi (khách, món) trong 30 ngày: có hoàn, chưa có đơn, chưa từng báo giảm giá. Món khách
    đang tự theo dõi (watchlist, PLAN-103) thì bỏ để không nhắn trùng."""
    rows = conn.execute(
        """
        SELECT l.* FROM link_requests l
        WHERE l.link_status = 'created' AND l.platform = 'shopee' AND l.item_id IS NOT NULL
          AND COALESCE(l.price_vnd, 0) > 0 AND COALESCE(l.estimated_cashback, 0) > 0 AND l.affiliate_url IS NOT NULL
          AND l.created_at >= ?
          AND l.id = (SELECT MAX(x.id) FROM link_requests x WHERE x.telegram_user_id = l.telegram_user_id
                      AND x.item_id = l.item_id AND x.link_status = 'created')
          AND NOT EXISTS (SELECT 1 FROM shopee_conversions c WHERE c.matched_link_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM admin_notifications n WHERE n.event_key = 'price_drop:' || l.id)
          AND NOT EXISTS (SELECT 1 FROM price_watches w WHERE w.telegram_user_id = l.telegram_user_id
                          AND w.item_id = l.item_id AND w.stopped_at IS NULL)
        ORDER BY l.created_at DESC LIMIT ?
        """,
        (_stamp(now - timedelta(days=WATCH_DAYS)), MAX_ITEMS),
    ).fetchall()
    cfg = NotifyConfig(True)
    return [r for r in rows
            if customer_block_reason(conn, {"category": engagement.CATEGORY, "chat_id": r["telegram_user_id"]},
                                     cfg, now) is None
            and not engagement.recently_nudged(conn, int(r["telegram_user_id"]), now)]


def pick(rows: list[sqlite3.Row], prices: dict[int, PricePoint]) -> list[tuple[sqlite3.Row, PricePoint, int]]:
    """Mỗi khách một món giảm sâu nhất (từ 15%, còn hàng): (link, giá mới, % giảm)."""
    best: dict[int, tuple[sqlite3.Row, PricePoint, int]] = {}
    for row in rows:
        point = prices.get(int(row["item_id"]))
        if point is None or point.in_stock is False:
            continue
        old = int(row["price_vnd"])
        if point.price > old * (1 - DROP_MIN):
            continue
        percent = round((old - point.price) * 100 / old)
        user = int(row["telegram_user_id"])
        if user not in best or percent > best[user][2]:
            best[user] = (row, point, percent)
    return list(best.values())


def run(repo: TrackingRepository, client: PriceHistoryClient, now: datetime) -> int:
    with repo.connect() as conn:
        rows = candidates(conn, now)
    if not rows:
        return 0
    prices = client.latest(sorted({int(r["item_id"]) for r in rows}))
    chosen = pick(rows, prices)
    stamp = _stamp(now)
    with repo.connect() as conn:
        for row, point, percent in chosen:
            markup = {"inline_keyboard": [[{"text": BUY_BUTTON, "url": row["affiliate_url"]}]]}
            enqueue_event(
                conn, event_key=f"price_drop:{row['id']}", event_type="PRICE_DROP", chat_id=int(row["telegram_user_id"]),
                message_html=price_drop(row["product_name"], point.price, percent, point.flash_sale),
                audience="customer", category=engagement.CATEGORY,
                reply_markup_json=json.dumps(markup, ensure_ascii=False), source_ref=f"link:{row['id']}", now=stamp,
            )
    return len(chosen)


def due(repo: TrackingRepository, now: datetime) -> bool:
    local = now.astimezone(sale_calendar.ICT)
    start, end = engagement.NUDGE_HOURS
    return (enabled(repo) and start <= local.time() <= end and repo.get_state(LAST_DAY_KEY) != local.date().isoformat()
            and not engagement.near_sale(repo, now))


def maybe_start(repo: TrackingRepository, client: PriceHistoryClient | None, admin_notifier=None,
                now: datetime | None = None) -> threading.Thread | None:
    """Gọi mỗi vòng poll. Tới lượt tối nay và chưa có lượt nào đang chạy thì chạy một lượt trong luồng nền."""
    moment = now or datetime.now(timezone.utc)
    if client is None or not due(repo, moment) or not _running.acquire(blocking=False):
        return None
    # Ghi ngày trước khi chạy: lỗi thì tối mai thử lại, không gọi AddLiveTag liên tục cả tối.
    repo.set_state(LAST_DAY_KEY, moment.astimezone(sale_calendar.ICT).date().isoformat())

    def work() -> None:
        try:
            sent = run(repo, client, moment)
            repo.set_state(RESULT_KEY, json.dumps({"at": _stamp(moment), "sent": sent}))
        except PriceWatchError as exc:
            logger.warning("[Cashback] báo giảm giá: AddLiveTag lỗi %s", exc)
            repo.set_state(RESULT_KEY, json.dumps({"at": _stamp(moment), "error": str(exc)}))
            if admin_notifier is not None:
                admin_notifier.notify_request_failed(error_type="price_drop_failed", status="PRICE_DROP_FAILED")
        except Exception:
            logger.exception("[Cashback] báo giảm giá lỗi bất ngờ")
            repo.set_state(RESULT_KEY, json.dumps({"at": _stamp(moment), "error": "unexpected"}))
        finally:
            _running.release()

    thread = threading.Thread(target=work, name="price-drop", daemon=True)
    thread.start()
    return thread
