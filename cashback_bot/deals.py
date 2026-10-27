"""Deal hời theo danh mục, mỗi tối 20:08 (chủ bot duyệt 2026-10-27; reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md mục 2B).

- Khách tự chọn tối đa 3 danh mục ở /thongbao → 🛍️ Deal hời. Chọn danh mục là đồng ý nhận; không chọn thì không gửi.
- Tắt mặc định: admin bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời (`bot_state.deals_enabled`).
- 17:30 giờ VN, luồng nền: với mỗi danh mục có người chọn, lấy top món bán chạy (AddLiveTag Market Search), kiểm lịch
  sử giá 30 ngày; «hời thật» = giá hôm nay ≤ thấp nhất 30 ngày và rẻ hơn giá thường ngày (trung vị) từ 10%, đánh giá
  ≥ 4,5, bán ≥ 100 / 30 ngày. Không dùng % giảm shop tự ghi (dữ liệu thật: «giảm 36%» mà đắt hơn thường ngày).
  Mỗi danh mục tối đa 5 món, kèm số hoàn tính như thẻ link (Shopee Comm tối đa 2,5%).
- Xong thì báo admin xem trước. Admin không làm gì thì 20:08 tự gửi; bỏ được cả ngày hoặc từng món.
- 20:08–21:08 gửi qua hàng đợi chung (category `deal`); quá giờ thì bỏ, không gửi muộn. Có lượt nhắc sale trong
  3 giờ (tối 20:30 trước ngày sale) thì nhường; tối đúng ngày sale vẫn gửi.
- Khách bấm món (`u:dl:<shop>:<item>`) thì bot tạo link như khi khách tự dán link: cùng thẻ, cùng cách tính, đơn
  tính đúng người. Không tạo sẵn link hàng loạt.
Trạng thái ngày ở `bot_state.deals:<YYYY-MM-DD>` (JSON): building · draft · empty · error · skipped · sent · missed.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time as clock
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone

import requests

from cashback_bot import engagement, sale_calendar
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import DEALS_CHANGE_HINT, DEALS_PICK_HINT
from cashback_bot.money import format_vnd
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason
from cashback_bot.price_watch import PriceHistoryClient, PriceWatchError
from cashback_bot.pricing import cashback_for
from cashback_bot.product_data import ProductDataError, quote_from_payload
from cashback_bot.sale_calendar import ICT
from cashback_bot.shopee_url import ShopeeTarget

logger = logging.getLogger("cashback_bot")

MARKET_URL = "https://data.addlivetag.com/search/market.php"
ENABLED_KEY = "deals_enabled"
PREFIX = "deals:"
CATS_PREFIX = "deal_cats:"
CATEGORY = "deal"
BUILD_AT = time(17, 30)
SEND_AT = time(20, 8)
SEND_WINDOW = timedelta(minutes=60)
MAX_CATS = 3
PER_CAT = 5
PER_MESSAGE = 5
MIN_DROP = 0.10
MIN_RATING = 4.5
MIN_SOLD = 100
# Dữ liệu thật 2026-10-27: 15 món / từ khoá chỉ ra 0–2 deal mỗi danh mục; 30 món ra khoảng 3.
PER_KEYWORD = 30
# AddLiveTag lịch sử giá giới hạn 600 món / phút / IP (vượt là 429): giãn nhịp ở mức 500 món / phút.
HISTORY_ITEMS_PER_MIN = 500
CATEGORIES = {
    "nu": ("👗 Thời trang nữ", ("áo thun nữ", "váy nữ", "quần jean nữ", "áo khoác nữ", "chân váy")),
    "nam": ("👕 Thời trang nam", ("áo thun nam", "quần jean nam", "áo polo nam", "áo khoác nam", "quần short nam")),
    "dep": ("💄 Làm đẹp", ("kem chống nắng", "sữa rửa mặt", "serum", "son môi", "tẩy trang")),
    "be": ("🍼 Mẹ & Bé", ("bỉm", "sữa bột", "quần áo trẻ em", "bình sữa", "khăn ướt")),
    "nha": ("🏠 Nhà cửa", ("chăn ga gối", "đồ dùng nhà bếp", "hộp đựng thực phẩm", "đèn ngủ", "kệ để đồ")),
    "dien": ("📱 Điện tử & phụ kiện", ("tai nghe bluetooth", "sạc dự phòng", "cáp sạc", "ốp lưng điện thoại",
                                      "loa bluetooth")),
    "thethao": ("🏃 Thể thao", ("giày thể thao", "thảm yoga", "quần áo thể thao", "bình nước thể thao", "dây nhảy")),
    "anvat": ("🍪 Bách hoá & ăn vặt", ("đồ ăn vặt", "bánh kẹo", "cà phê", "mì ăn liền", "nước giặt")),
    "thucung": ("🐾 Thú cưng", ("thức ăn cho mèo", "cát vệ sinh mèo", "thức ăn cho chó", "đồ chơi thú cưng")),
    "dochoi": ("🧸 Đồ chơi", ("đồ chơi lắp ráp", "gấu bông", "mô hình", "đồ chơi giáo dục", "xe đồ chơi")),
}
STATUS_LABELS = {
    "building": "⏳ Đang soạn", "draft": "📝 Chờ 20:08", "empty": "⚪ Không có deal đạt chuẩn",
    "error": "🔴 Lỗi lấy dữ liệu", "skipped": "⏭ Bỏ hôm nay", "sent": "📤 Đã gửi", "missed": "⚪ Lỡ giờ, không gửi",
    "sale": "⏭ Nhường tin nhắc sale",
}
_running = threading.Lock()


@dataclass(frozen=True)
class Deal:
    item_id: int
    shop_id: int
    name: str
    price: int
    usual: int
    lowest_30d: bool
    cashback: int
    rating: float
    sold_30d: int

    @property
    def drop_percent(self) -> int:
        return round((self.usual - self.price) * 100 / self.usual) if self.usual else 0


class MarketSearchClient:
    def __init__(self, api_key: str, url: str = MARKET_URL, timeout: float = 30):
        self._api_key = api_key
        self._url = url
        self._timeout = timeout

    def top(self, keyword: str, limit: int = PER_KEYWORD) -> list[dict]:
        params = {"q": keyword, "sort": "sold_30d", "limit": limit, "price_min": 30000}
        try:
            response = requests.get(self._url, params=params, headers={"X-API-Key": self._api_key},
                                    timeout=self._timeout)
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceWatchError(type(exc).__name__) from exc
        if response.status_code != 200 or not isinstance(payload.get("products"), list):
            raise PriceWatchError(f"market_http_{response.status_code}")
        return [p for p in payload["products"] if isinstance(p, dict)]


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(ENABLED_KEY) == "1"


# --- Danh mục khách chọn ----------------------------------------------------------------------------------------


def user_categories(repo: TrackingRepository, user: int) -> list[str]:
    raw = repo.get_state(f"{CATS_PREFIX}{user}") or ""
    return [key for key in raw.split(",") if key in CATEGORIES]


def toggle_category(repo: TrackingRepository, user: int, key: str) -> tuple[list[str], str]:
    """Bật / tắt một danh mục. Trả (danh mục sau khi đổi, lời nhắn)."""
    current = user_categories(repo, user)
    if key in current:
        current.remove(key)
        notice = f"Đã bỏ {CATEGORIES[key][0]}."
    elif len(current) >= MAX_CATS:
        return current, f"Chọn tối đa {MAX_CATS} danh mục thôi nha, bỏ bớt một mục trước đã."
    else:
        current.append(key)
        notice = f"Đã chọn {CATEGORIES[key][0]}. Tối nào có deal hời bot gửi lúc 20:08 nha 🔥"
    repo.set_state(f"{CATS_PREFIX}{user}", ",".join(current))
    return current, notice


def subscribers(conn: sqlite3.Connection, now: datetime) -> dict[int, list[str]]:
    """Khách đã chọn danh mục, chưa chặn bot."""
    rows = conn.execute("SELECT key, value FROM bot_state WHERE key LIKE ? AND value != ''", (CATS_PREFIX + "%",))
    cfg = NotifyConfig(True)
    found: dict[int, list[str]] = {}
    for key, value in rows:
        try:
            user = int(key.removeprefix(CATS_PREFIX))
        except ValueError:
            continue
        cats = [c for c in value.split(",") if c in CATEGORIES]
        if cats and customer_block_reason(conn, {"category": CATEGORY, "chat_id": user}, cfg, now) is None:
            found[user] = cats
    return found


# --- Soạn deal --------------------------------------------------------------------------------------------------


def record(repo: TrackingRepository, day: str) -> dict:
    try:
        return json.loads(repo.get_state(PREFIX + day) or "{}")
    except ValueError:
        return {}


def save(repo: TrackingRepository, day: str, data: dict) -> None:
    repo.set_state(PREFIX + day, json.dumps(data, ensure_ascii=False, sort_keys=True))


def pick(products: list[dict], stats: dict) -> list[dict]:
    """Món «hời thật» của một danh mục, sắp theo % rẻ hơn thường ngày."""
    chosen, seen = [], set()
    for product in products:
        try:
            item_id, shop_id = int(product.get("itemId")), int(product.get("shopId"))
            rating, sold = float(product.get("rating") or 0), int(product.get("sold30d") or 0)
        except (TypeError, ValueError):
            continue
        stat = stats.get(item_id)
        if item_id in seen or stat is None or rating < MIN_RATING or sold < MIN_SOLD or stat.in_stock is False:
            continue
        if stat.price > stat.lowest or stat.price > stat.usual * (1 - MIN_DROP):
            continue
        seen.add(item_id)
        chosen.append({"item_id": item_id, "shop_id": shop_id, "name": str(product.get("productName") or ""),
                       "price": stat.price, "usual": stat.usual, "lowest_30d": stat.price <= stat.lowest,
                       "rating": rating, "sold_30d": sold})
    chosen.sort(key=lambda d: (d["usual"] - d["price"]) / d["usual"], reverse=True)
    return chosen


def build(repo: TrackingRepository, service, market: MarketSearchClient, history: PriceHistoryClient,
          now: datetime, pause: Callable[[float], None] = clock.sleep) -> dict[str, list[dict]]:
    """Deal của từng danh mục có người chọn. Số hoàn tính như thẻ link, theo chính sách lúc soạn."""
    with repo.connect() as conn:
        wanted = sorted({c for cats in subscribers(conn, now).values() for c in cats})
    resolution = service._resolve_policy(now)
    result: dict[str, list[dict]] = {}
    for key in wanted:
        products: dict[int, dict] = {}
        for keyword in CATEGORIES[key][1]:
            for product in market.top(keyword):
                try:
                    products.setdefault(int(product.get("itemId")), product)
                except (TypeError, ValueError):
                    continue
        stats = history.stats(sorted(products), days=30)
        pause(len(products) * 60 / HISTORY_ITEMS_PER_MIN)
        deals: list[dict] = []
        for deal in pick(list(products.values()), stats):
            try:
                payload = service.client.fetch(ShopeeTarget("", deal["item_id"], deal["shop_id"], None))
                quote = quote_from_payload(payload, now, service.settings.product_max_age_hours)
            except ProductDataError:
                continue
            cashback = cashback_for(quote.sure_commission_vnd, resolution).cashback_vnd
            if cashback <= 0:
                continue
            deals.append(asdict(Deal(cashback=cashback, **deal)))
            if len(deals) >= PER_CAT:
                break
        result[key] = deals
    return result


# --- Tin gửi khách ----------------------------------------------------------------------------------------------


_PROMO_TAG = re.compile(r"^\s*(?:[\[【(][^\]】)]{0,40}[\]】)]\s*)+")


def _short(name: str, limit: int = 42) -> str:
    """Bỏ nhãn khuyến mãi shop gắn ở đầu tên («[MUA 2 TẶNG 1]», «【DAILY】») rồi cắt gọn."""
    text = " ".join(_PROMO_TAG.sub("", name).split()) or " ".join(name.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,.-") + "…"


def _k(vnd: int) -> str:
    """64.500đ → «64,5k» (không làm tròn xuống thành 64k, thấp hơn giá thật)."""
    if vnd < 1000:
        return format_vnd(vnd)
    thousands = round(vnd / 1000, 1)
    return (f"{thousands:.0f}" if thousands == int(thousands) else f"{thousands:.1f}".replace(".", ",")) + "k"


def message_for(cats: list[str], deals: dict[str, list[dict]], removed: set[int]) -> tuple[str, list[dict]] | None:
    """Tin của một khách: tối đa 5 món, chia đều các danh mục khách chọn. Không có món nào thì None."""
    pools = {c: [d for d in deals.get(c, []) if d["item_id"] not in removed] for c in cats}
    picked: list[tuple[str, dict]] = []
    while len(picked) < PER_MESSAGE and any(pools.values()):
        for cat in cats:
            if pools[cat] and len(picked) < PER_MESSAGE:
                picked.append((cat, pools[cat].pop(0)))
    if not picked:
        return None
    lines = ["⏰ <b>20:08 giờ phát lộc! Deal hời hôm nay cho bạn nè</b> 🔥"]
    buttons, number = [], 0
    for cat in cats:
        rows = [d for c, d in picked if c == cat]
        if not rows:
            continue
        lines += ["", f"<b>{CATEGORIES[cat][0]}</b>"]
        for deal in rows:
            number += 1
            low = " · thấp nhất 30 ngày" if deal["lowest_30d"] else ""
            name = _short(deal["name"])
            lines.append(f"{number}. {name}: <b>{_k(deal['price'])}</b> (thường {_k(deal['usual'])}{low}) "
                         f"· hoàn ~{_k(deal['cashback'])}")
            buttons.append({"text": f"{number}. 🛒 {_short(deal['name'], 28)}",
                            "callback_data": f"u:dl:{deal['shop_id']}:{deal['item_id']}"})
    lines += ["", DEALS_PICK_HINT,
              "Giá theo dữ liệu lúc 17:30, có thể đổi khi bạn mở.",
              DEALS_CHANGE_HINT]
    # Nút cuối: đổi danh mục ngay từ tin deal (Zalo: một số trong danh sách).
    return "\n".join(lines), [[b] for b in buttons] + [[{"text": "⚙️ Đổi danh mục", "callback_data": "u:dc:home"}]]


def send(repo: TrackingRepository, day: str, data: dict, now: datetime) -> int:
    deals = data.get("deals") or {}
    removed = set(data.get("removed") or [])
    stamp = _stamp(now)
    sent = 0
    with repo.connect() as conn:
        for user, cats in subscribers(conn, now).items():
            built = message_for(cats, deals, removed)
            if built is None:
                continue
            text, keyboard = built
            enqueue_event(conn, event_key=f"deals:{day}:{user}", event_type="DEALS", chat_id=user, message_html=text,
                          audience="customer", category=CATEGORY,
                          reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False),
                          source_ref=f"deals:{day}", now=stamp)
            sent += 1
    save(repo, day, {**data, "status": "sent", "sent": sent, "at": stamp})
    return sent


# --- Lịch chạy --------------------------------------------------------------------------------------------------


def _sale_soon(repo: TrackingRepository, now: datetime) -> bool:
    if not engagement.enabled(repo):
        return False
    return any(abs(slot.at - now) < timedelta(hours=3) for slot in sale_calendar.upcoming(now - timedelta(days=1), 2))


def _start_build(repo: TrackingRepository, service, market, history, admin_notifier, day: str, now: datetime,
                 pause: Callable[[float], None]) -> None:
    def work() -> None:
        try:
            deals = build(repo, service, market, history, now, pause)
            count = sum(len(v) for v in deals.values())
            if count and admin_notifier is not None:
                try:
                    with repo.connect() as conn:
                        people = len(subscribers(conn, now))
                    admin_notifier.notify_deals_ready(day, count, people)
                except Exception:
                    logger.exception("[Cashback] báo admin deal hời lỗi")
            save(repo, day, {"status": "draft" if count else "empty", "deals": deals, "removed": [],
                             "built": _stamp(now)})
        except PriceWatchError as exc:
            logger.warning("[Cashback] deal hời: AddLiveTag lỗi %s", exc)
            save(repo, day, {"status": "error", "error": str(exc)})
        except Exception:
            logger.exception("[Cashback] deal hời lỗi bất ngờ")
            save(repo, day, {"status": "error", "error": "unexpected"})
        finally:
            _running.release()

    threading.Thread(target=work, name="deals", daemon=True).start()


def tick(repo: TrackingRepository, service, admin_notifier=None, now: datetime | None = None,
         market: MarketSearchClient | None = None, history: PriceHistoryClient | None = None,
         pause: Callable[[float], None] = clock.sleep) -> None:
    """Gọi mỗi vòng poll của bot Telegram."""
    if not enabled(repo):
        return
    moment = now or datetime.now(timezone.utc)
    local = moment.astimezone(ICT)
    day = local.date().isoformat()
    data = record(repo, day)
    state = data.get("status")
    send_at = datetime.combine(local.date(), SEND_AT, ICT)
    if state is None and BUILD_AT <= local.time() < SEND_AT:
        with repo.connect() as conn:
            if not subscribers(conn, moment) or not _running.acquire(blocking=False):
                return
        save(repo, day, {"status": "building"})
        _start_build(repo, service, market or MarketSearchClient(service.settings.api_key),
                     history or service.price_history, admin_notifier, day, moment, pause)
        return
    if state != "draft" or local < send_at:
        return
    if local >= send_at + SEND_WINDOW:
        save(repo, day, {**data, "status": "missed"})
    elif _sale_soon(repo, moment):
        save(repo, day, {**data, "status": "sale"})
    else:
        send(repo, day, data, moment)
