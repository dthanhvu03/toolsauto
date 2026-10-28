"""Deal hời tự động (PLAN-100, chủ bot 2026-10-28: «tự update tự gửi, cứ có là gửi, 1 deal cũng gửi»).

Thay hai lượt cố định 12:08 / 20:08 (chủ bot duyệt 2026-10-27; reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md mục 2B, 7).

- Khách tự chọn tối đa 3 danh mục ở /thongbao → 🛍️ Deal hời. Chọn danh mục là đồng ý nhận.
- Tắt mặc định: admin bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🔥 Deal hời (`bot_state.deals_enabled`).
- Quét mỗi giờ tròn 7:00–21:00 giờ VN, luồng nền. Giờ chẵn 5 từ khoá đầu của danh mục, giờ lẻ phần còn lại; đủ 10
  danh mục. Với mỗi từ khoá lấy top món bán chạy (AddLiveTag Market Search), kiểm lịch sử giá 30 ngày; «hời thật» =
  giá hôm nay ≤ thấp nhất 30 ngày và rẻ hơn giá thường ngày (trung vị) từ 10%, đánh giá ≥ 4,5, bán ≥ 100 / 30 ngày.
  Không dùng % giảm shop tự ghi (dữ liệu thật: «giảm 36%» mà đắt hơn thường ngày). Số hoàn tính như thẻ link.
- Kho deal `bot_state.deals_pool`: món đạt chuẩn với lần thấy đầu (`first`) và lần gần nhất còn hời (`seen`); 24 giờ
  không thấy lại thì bỏ. Admin ❌ bỏ món (`deals_removed`): không gửi, không hiện ở 🔥 Deal hôm nay.
- Sau mỗi lượt quét, trong 8:00–22:00 và không có tin nhắc sale trong 3 giờ: khách có món mới (thấy lại trong 2 giờ 30,
  chưa gửi khách đó trong 3 ngày) thuộc danh mục của mình thì gửi, 1 món cũng gửi, tối đa 3 món / tin. Mỗi khách tối đa
  4 tin / ngày, cách nhau ≥ 2 giờ. Không duyệt từng lượt (chủ bot muốn tự gửi).
- Gửi qua hàng đợi chung (category `deal`). Khách bấm món (`u:dl:<shop>:<item>`) thì bot tạo link như khi khách tự
  dán link: cùng thẻ, cùng cách tính, đơn tính đúng người. Không tạo sẵn link hàng loạt.
Lượt quét gần nhất ở `bot_state.deals_scan` (JSON): hour · status (building · done · error) · found · new · sent.
"""

from __future__ import annotations

import html
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
from cashback_bot.messages import DEALS_CHANGE_HINT, DEALS_INFER_HINT, DEALS_PICK_HINT, PROMO_TAG
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
CATS_PREFIX = "deal_cats:"
CATEGORY = "deal"
REPEAT_GAP = timedelta(days=3)
MAX_CATS = 3
PER_CAT = 5
PER_MESSAGE = 3
MIN_DROP = 0.10
MIN_RATING = 4.5
MIN_SOLD = 100
# Dữ liệu thật 2026-10-27: 15 món / từ khoá chỉ ra 0–2 deal mỗi danh mục; 30 món ra khoảng 3.
# Từ khoá: 5 đầu cho lượt giờ chẵn, phần sau cho lượt giờ lẻ (`keywords_for`).
PER_KEYWORD = 30
# AddLiveTag lịch sử giá giới hạn 600 món / phút / IP (vượt là 429): giãn nhịp ở mức 500 món / phút.
HISTORY_ITEMS_PER_MIN = 500
CATEGORIES = {
    "nu": ("👗 Thời trang nữ", ("áo thun nữ", "váy nữ", "quần jean nữ", "áo khoác nữ", "chân váy",
                               "áo sơ mi nữ", "đầm công sở", "quần ống rộng nữ", "áo croptop", "túi xách nữ")),
    "nam": ("👕 Thời trang nam", ("áo thun nam", "quần jean nam", "áo polo nam", "áo khoác nam", "quần short nam",
                                 "áo sơ mi nam", "quần kaki nam", "quần jogger nam", "ví nam", "dép nam")),
    "dep": ("💄 Làm đẹp", ("kem chống nắng", "sữa rửa mặt", "serum", "son môi", "tẩy trang",
                          "toner", "kem dưỡng ẩm", "mặt nạ", "dầu gội", "sữa tắm")),
    "be": ("🍼 Mẹ & Bé", ("bỉm", "sữa bột", "quần áo trẻ em", "bình sữa", "khăn ướt",
                         "sữa tắm cho bé", "xe đẩy em bé", "giày trẻ em", "balo trẻ em", "yếm ăn dặm")),
    "nha": ("🏠 Nhà cửa", ("chăn ga gối", "đồ dùng nhà bếp", "hộp đựng thực phẩm", "đèn ngủ", "kệ để đồ",
                          "cây lau nhà", "móc treo quần áo", "khăn tắm", "giỏ đựng đồ", "rèm cửa")),
    "dien": ("📱 Điện tử & phụ kiện", ("tai nghe bluetooth", "sạc dự phòng", "cáp sạc", "ốp lưng điện thoại",
                                      "loa bluetooth", "chuột không dây", "bàn phím", "giá đỡ điện thoại",
                                      "đồng hồ thông minh", "củ sạc nhanh")),
    "thethao": ("🏃 Thể thao", ("giày thể thao", "thảm yoga", "quần áo thể thao", "bình nước thể thao", "dây nhảy",
                               "tạ tay", "găng tay tập gym", "balo thể thao", "vợt cầu lông", "tất thể thao")),
    "anvat": ("🍪 Bách hoá & ăn vặt", ("đồ ăn vặt", "bánh kẹo", "cà phê", "mì ăn liền", "nước giặt",
                                      "hạt dinh dưỡng", "trà", "khô gà", "nước xả vải", "giấy vệ sinh")),
    "thucung": ("🐾 Thú cưng", ("thức ăn cho mèo", "cát vệ sinh mèo", "thức ăn cho chó", "đồ chơi thú cưng",
                               "pate cho mèo", "sữa tắm cho chó", "vòng cổ thú cưng", "nhà cho mèo")),
    "dochoi": ("🧸 Đồ chơi", ("đồ chơi lắp ráp", "gấu bông", "mô hình", "đồ chơi giáo dục", "xe đồ chơi",
                             "búp bê", "đồ chơi xếp hình", "slime", "xe điều khiển từ xa", "bộ đồ chơi nấu ăn")),
}
POOL_KEY = "deals_pool"
REMOVED_KEY = "deals_removed"
SCAN_KEY = "deals_scan"
SCAN_HOURS = range(7, 22)  # 7:00 … 21:00 giờ VN, mỗi giờ một lượt
SEND_FROM, SEND_UNTIL = time(8), time(22)
DAILY_MAX = 4
USER_GAP = timedelta(hours=2)
FRESH = timedelta(hours=2, minutes=30)  # hai nửa từ khoá chạy xen kẽ: món được kiểm lại ít nhất 2 giờ / lần
FEED_FRESH = timedelta(hours=12)  # 🔥 Deal hôm nay ban đêm vẫn còn deal của lượt 21:00
POOL_KEEP = timedelta(hours=24)
HEADER = "🔥 <b>Deal mới vừa lên! Món rẻ thật cho bạn nè</b>"
INFER_HEADER = "🔥 <b>Deal mới vừa lên! Vài món hợp gu bạn</b>"
# Trạng thái lượt quét, và trạng thái lượt trưa / tối cũ (📊 Lịch sử cũ còn ghi).
STATUS_LABELS = {
    "building": "⏳ Đang quét", "done": "✅ Xong", "error": "🔴 Lỗi lấy dữ liệu",
    "draft": "📝 Chờ giờ gửi", "empty": "⚪ Không có deal đạt chuẩn", "skipped": "⏭ Bỏ hôm nay", "sent": "📤 Đã gửi",
    "missed": "⚪ Lỡ giờ, không gửi", "sale": "⏭ Nhường tin nhắc sale",
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
        notice = f"Đã chọn {CATEGORIES[key][0]}. Có món mới rẻ thật là bot gửi bạn liền nha 🔥"
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


# --- Khách chưa chọn: bot đoán gu (chủ bot 2026-10-27: «khách chưa chọn thì gửi luôn, mà gửi phải thông minh») ----
# Thưa hơn và chặt hơn khách đã chọn: tối đa 2 tin / tuần, món rẻ hơn thường ngày ≥ 12%, tối đa 3 món, nói rõ vì sao
# đoán, có nút chọn danh mục / không nhận. Nhận 3 tin không tạo link nào thì dừng tới khi khách tạo link mới.
# Không gửi: khách đã chọn hay đã bỏ hết danh mục (`deal_cats:<id>` có mặt, kể cả rỗng), tắt 🛒 Nhắc ở /thongbao,
# chặn bot, 60 ngày không tạo link.
INFER_KEY = "deals_infer_enabled"  # bật mặc định; admin tắt thì = "0"
INFER_ACTIVE = timedelta(days=60)
INFER_GAP = timedelta(days=3)
INFER_MIN_DROP = 0.12
INFER_ITEMS = 3
INFER_STOP_AFTER = 3
HINTS = {
    "nu": ("nữ", "váy", "đầm", "croptop"),
    "nam": ("nam", "polo", "quần âu"),
    "dep": ("kem", "son", "serum", "trang điểm", "tẩy trang", "dưỡng", "cọ", "mặt nạ", "rửa mặt", "nước hoa", "phấn"),
    "be": ("bé", "trẻ em", "bỉm", "sơ sinh"),
    "nha": ("nhà", "bếp", "chăn ga", "gối nằm", "gối ngủ", "nệm", "topper", "đèn ngủ", "đèn bàn", "quạt", "nồi", "chảo",
            "kệ", "khung", "trải giường", "tủ lạnh"),
    "dien": ("điện thoại", "tai nghe", "sạc", "cáp", "loa", "bàn phím", "chuột", "ốp lưng", "laptop", "máy tính"),
    "thethao": ("thể thao", "giày", "yoga", "gym", "chạy bộ"),
    "anvat": ("ăn vặt", "bánh", "kẹo", "cà phê", "snack", "gà rán"),
    "thucung": ("chó", "mèo", "thú cưng"),
    "dochoi": ("đồ chơi", "lắp ráp", "mô hình", "gấu bông", "lego"),
}


def infer_enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(INFER_KEY) != "0"


def _words(text: str | None) -> str:
    return " " + re.sub(r"[^\w]+", " ", (text or "").lower()) + " "


def guess(names: list[tuple[str | None, str | None]]) -> tuple[list[str], str]:
    """(danh mục đoán, tên món làm lý do) từ các link khách đã tạo (mới nhất trước). Món mới nặng ký hơn."""
    scores: dict[str, float] = {}
    reason: dict[str, str] = {}
    for rank, (product, category) in enumerate(names):
        text = _words(f"{product} {category}")
        unisex = " nam " in text and " nữ " in text  # «cho nam nữ»: không nói được gu theo giới tính
        for key, words in HINTS.items():
            if unisex and key in ("nam", "nu"):
                continue
            hits = sum(f" {w} " in text for w in words)  # khớp nhiều từ (sạc + cáp) nặng hơn một từ lẻ
            if hits:
                scores[key] = scores.get(key, 0) + hits / (1 + rank)
                reason.setdefault(key, product or category or "")
    top = sorted(scores, key=scores.get, reverse=True)[:2]
    return top, (reason[top[0]] if top else "")


def inferred(conn: sqlite3.Connection, now: datetime) -> dict[int, tuple[list[str], str]]:
    """Khách chưa chọn danh mục mà lượt này được gửi theo gu bot đoán."""
    since = _stamp(now - INFER_ACTIVE)
    users = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created' AND created_at >= ?", (since,))]
    cfg = NotifyConfig(True)
    found: dict[int, tuple[list[str], str]] = {}
    for user in users:
        if conn.execute("SELECT 1 FROM bot_state WHERE key = ?", (f"{CATS_PREFIX}{user}",)).fetchone():
            continue
        if customer_block_reason(conn, {"category": engagement.CATEGORY, "chat_id": user}, cfg, now) is not None:
            continue
        last_link = conn.execute("SELECT MAX(created_at) FROM link_requests WHERE telegram_user_id = ? "
                                 "AND link_status = 'created'", (user,)).fetchone()[0]
        sent = conn.execute("SELECT COUNT(*), MAX(created_at) FROM admin_notifications WHERE event_type = 'DEALS' "
                            "AND chat_id = ? AND created_at >= ?", (user, last_link)).fetchone()
        if sent[0] >= INFER_STOP_AFTER:
            continue
        recent = conn.execute("SELECT MAX(created_at) FROM admin_notifications WHERE event_type = 'DEALS' AND chat_id = ?",
                              (user,)).fetchone()[0]
        if recent and recent >= _stamp(now - INFER_GAP):
            continue
        names = conn.execute("SELECT product_name, cat_name FROM link_requests WHERE telegram_user_id = ? "
                             "AND link_status = 'created' ORDER BY created_at DESC LIMIT 10", (user,)).fetchall()
        cats, reason = guess([(r[0], r[1]) for r in names])
        if cats:
            found[user] = (cats, reason)
    return found


# --- Soạn deal --------------------------------------------------------------------------------------------------


def _load(repo: TrackingRepository, key: str, default):
    try:
        value = json.loads(repo.get_state(key) or "null")
    except ValueError:
        return default
    return value if isinstance(value, type(default)) else default


def _save(repo: TrackingRepository, key: str, value) -> None:
    repo.set_state(key, json.dumps(value, ensure_ascii=False, sort_keys=True))


def pool(repo: TrackingRepository) -> dict[str, dict]:
    """Kho deal: mã món → deal + `cat`, `first`, `seen`."""
    return _load(repo, POOL_KEY, {})


def removed_items(repo: TrackingRepository) -> set[int]:
    return {int(i) for i in _load(repo, REMOVED_KEY, []) if str(i).isdigit()}


def set_removed(repo: TrackingRepository, item: int, removed: bool) -> None:
    items = removed_items(repo)
    _save(repo, REMOVED_KEY, sorted(items | {item} if removed else items - {item}))


def scan_record(repo: TrackingRepository) -> dict:
    return _load(repo, SCAN_KEY, {})


def merge(current: dict[str, dict], found: dict[str, list[dict]], now: datetime) -> tuple[dict[str, dict], int]:
    """Gộp kết quả một lượt quét vào kho. Trả (kho mới, số món mới). Món 24 giờ không thấy lại thì bỏ."""
    stamp = _stamp(now)
    keep = _stamp(now - POOL_KEEP)
    merged = {key: deal for key, deal in current.items() if deal.get("seen", "") >= keep}
    new = 0
    for cat, deals in found.items():
        for deal in deals:
            key = str(deal["item_id"])
            old = merged.get(key)
            new += old is None
            merged[key] = {**deal, "cat": old["cat"] if old else cat, "first": old["first"] if old else stamp,
                           "seen": stamp}
    return merged, new


def current_deals(repo: TrackingRepository, now: datetime, fresh: timedelta = FRESH) -> tuple[dict[str, list[dict]],
                                                                                                str | None]:
    """Món còn hời (thấy lại trong `fresh`), admin chưa bỏ, theo danh mục, rẻ nhất trước; kèm lần thấy gần nhất."""
    since = _stamp(now - fresh)
    removed = removed_items(repo)
    by_cat: dict[str, list[dict]] = {}
    latest = None
    for deal in pool(repo).values():
        if deal.get("seen", "") < since or deal["item_id"] in removed or deal.get("cat") not in CATEGORIES:
            continue
        by_cat.setdefault(deal["cat"], []).append(deal)
        latest = max(latest or "", deal["seen"])
    for rows in by_cat.values():
        rows.sort(key=lambda d: d["price"] / d["usual"])
    return by_cat, latest


def _clock(stamp: str | None) -> str:
    """«2026-10-28T07:00:00Z» → «14:00» giờ VN."""
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(ICT) \
            .strftime("%H:%M")
    except ValueError:
        return ""


_SHOWN = re.compile(r"u:dl:\d+:(\d+)")


def recently_shown(conn: sqlite3.Connection, user: int, now: datetime) -> set[int]:
    """Món đã gửi cho khách trong REPEAT_GAP (đọc từ nút của các tin deal đã xếp hàng)."""
    rows = conn.execute("SELECT reply_markup_json FROM admin_notifications WHERE event_type = 'DEALS' AND chat_id = ? "
                        "AND created_at >= ?", (user, _stamp(now - REPEAT_GAP)))
    return {int(item) for (markup,) in rows for item in _SHOWN.findall(markup or "")}


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


def keywords_for(now: datetime) -> slice:
    """Giờ chẵn 5 từ khoá đầu, giờ lẻ phần còn lại: hai lượt liền nhau ra món khác nhau."""
    return slice(0, 5) if now.astimezone(ICT).hour % 2 == 0 else slice(5, None)


def build(repo: TrackingRepository, service, market: MarketSearchClient, history: PriceHistoryClient,
          now: datetime, pause: Callable[[float], None] = clock.sleep) -> dict[str, list[dict]]:
    """Deal của mọi danh mục trong một lượt quét. Số hoàn tính như thẻ link, theo chính sách lúc quét."""
    resolution = service._resolve_policy(now)
    result: dict[str, list[dict]] = {}
    for key in CATEGORIES:
        products: dict[int, dict] = {}
        for keyword in CATEGORIES[key][1][keywords_for(now)]:
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


def _short(name: str, limit: int = 42) -> str:
    """Bỏ nhãn khuyến mãi shop gắn ở đầu tên («[MUA 2 TẶNG 1]», «【DAILY】») rồi cắt gọn."""
    text = " ".join(PROMO_TAG.sub("", name).split()) or " ".join(name.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,.-") + "…"


def _k(vnd: int) -> str:
    """64.500đ → «64,5k» (không làm tròn xuống thành 64k, thấp hơn giá thật)."""
    if vnd < 1000:
        return format_vnd(vnd)
    thousands = round(vnd / 1000, 1)
    return (f"{thousands:.0f}" if thousands == int(thousands) else f"{thousands:.1f}".replace(".", ",")) + "k"


def message_for(cats: list[str], deals: dict[str, list[dict]], removed: set[int], *, limit: int = PER_MESSAGE,
                min_drop: float = 0.0, reason: str | None = None, at: str = "") -> tuple[str, list[dict]] | None:
    """Tin của một khách: chia đều các danh mục, tối đa `limit` món. Không có món nào thì None.
    `removed`: món admin bỏ và món đã gửi khách này trong 3 ngày. `at`: giờ dữ liệu giá («14:00»).

    `reason` có giá trị: khách chưa chọn danh mục, bot đoán gu từ món khách từng xem (thưa hơn, chặt hơn, có nút tắt)."""
    def strong(deal: dict) -> bool:
        return deal["item_id"] not in removed and deal["price"] <= deal["usual"] * (1 - min_drop)

    pools = {c: [d for d in deals.get(c, []) if strong(d)] for c in cats}
    picked: list[tuple[str, dict]] = []
    while len(picked) < limit and any(pools.values()):
        for cat in cats:
            if pools[cat] and len(picked) < limit:
                picked.append((cat, pools[cat].pop(0)))
    if not picked:
        return None
    if reason is None:
        lines = [HEADER]
    else:
        guessed = ", ".join(CATEGORIES[c][0] for c in cats)
        lines = [INFER_HEADER,
                 f"Bot đoán bạn thích {guessed} vì bạn từng xem <i>{html.escape(_short(reason, 40))}</i>"
                 + ("" if _short(reason, 40).endswith("…") else ".")]
    buttons, number = [], 0
    for cat in cats:
        rows = [d for c, d in picked if c == cat]
        if not rows:
            continue
        lines += ["", f"<b>{CATEGORIES[cat][0]}</b>"]
        for deal in rows:
            number += 1
            low = " · thấp nhất 30 ngày" if deal["lowest_30d"] else ""
            name = html.escape(_short(deal["name"]))
            lines.append(f"{number}. {name}: <b>{_k(deal['price'])}</b> (thường {_k(deal['usual'])}{low}) "
                         f"· hoàn ~{_k(deal['cashback'])}")
            buttons.append([{"text": f"{number}. 🛒 {_short(deal['name'], 28)}",
                             "callback_data": f"u:dl:{deal['shop_id']}:{deal['item_id']}"}])
    lines += ["", DEALS_PICK_HINT, f"Giá theo dữ liệu lúc {at}, có thể đổi khi bạn mở." if at else
              "Giá có thể đổi khi bạn mở."]
    if reason is None:
        lines.append(DEALS_CHANGE_HINT)
        # Nút cuối: đổi danh mục ngay từ tin deal (Zalo: một số trong danh sách).
        return "\n".join(lines), buttons + [[{"text": "⚙️ Đổi danh mục", "callback_data": "u:dc:home"}]]
    lines.append(DEALS_INFER_HINT)
    return "\n".join(lines), buttons + [[{"text": "🛍️ Chọn danh mục chuẩn hơn", "callback_data": "u:dc:home"}],
                                         [{"text": "🔕 Không nhận deal", "callback_data": "u:dc:off"}]]


def _today_start(now: datetime) -> str:
    local = now.astimezone(ICT)
    return _stamp(datetime.combine(local.date(), time(0), ICT))


def quota_ok(conn: sqlite3.Connection, user: int, now: datetime) -> bool:
    """Tối đa DAILY_MAX tin deal / ngày (giờ VN), hai tin cách nhau ít nhất USER_GAP."""
    count, last = conn.execute("SELECT COUNT(*), MAX(created_at) FROM admin_notifications WHERE event_type = 'DEALS' "
                               "AND chat_id = ? AND created_at >= ?", (user, _today_start(now))).fetchone()
    return count < DAILY_MAX and not (last and last > _stamp(now - USER_GAP))


def in_send_window(now: datetime) -> bool:
    return SEND_FROM <= now.astimezone(ICT).time() < SEND_UNTIL


def send_round(repo: TrackingRepository, now: datetime) -> int:
    """Gửi món mới cho từng khách theo danh mục; trả số tin đã xếp hàng."""
    if not in_send_window(now) or _sale_soon(repo, now):
        return 0
    deals, latest = current_deals(repo, now)
    if not deals:
        return 0
    stamp, at = _stamp(now), _clock(latest)
    sent = 0
    with repo.connect() as conn:
        targets = {user: (cats, None) for user, cats in subscribers(conn, now).items()}
        if infer_enabled(repo):
            targets.update({user: guessed for user, guessed in inferred(conn, now).items() if user not in targets})
        for user, (cats, reason) in targets.items():
            if not quota_ok(conn, user, now):
                continue
            skip = recently_shown(conn, user, now)
            built = (message_for(cats, deals, skip, at=at) if reason is None else
                     message_for(cats, deals, skip, limit=INFER_ITEMS, min_drop=INFER_MIN_DROP, reason=reason, at=at))
            if built is None:
                continue
            text, keyboard = built
            enqueue_event(conn, event_key=f"deals:{stamp}:{user}", event_type="DEALS", chat_id=user,
                          message_html=text, audience="customer", category=CATEGORY,
                          reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False),
                          source_ref=SCAN_KEY, now=stamp)
            sent += 1
    return sent


# --- 🔥 Deal hôm nay ngay trong bot (PLAN-099, chủ bot 2026-10-28: «làm kênh deal ngay trong bot») ---------------
# Khách mở xem lúc nào cũng được (nút trang chủ, /deal): món trong kho thấy lại trong 12 giờ, admin chưa bỏ.
FEED = "u:dh"
FEED_ITEMS = 8
FEED_PER_CAT = 2


def feed_message(pools: dict[str, list[dict]], mine: list[str], only: str | None, at: str = "") -> tuple[str, list]:
    """Tin 🔥 Deal hôm nay. `pools`: món theo danh mục (rẻ nhất trước). `mine`: danh mục khách đã chọn (xếp trước).
    `only`: chỉ xem một danh mục. `at`: giờ dữ liệu giá."""
    tail = [[{"text": "⚙️ Chọn danh mục nhận tin", "callback_data": "u:dc:home"},
             {"text": "◀️ Trang chủ", "callback_data": "u:p:home"}]]
    pools = {key: rows for key, rows in pools.items() if rows and key in CATEGORIES}
    if not pools:
        return ("🔥 <b>Deal hời hôm nay</b>\n\nChưa có deal đạt chuẩn. Bot quét deal mới mỗi giờ từ 7:00 tới 21:00, "
                "bạn ghé lại sau nha 🫶", tail)
    if only in pools:
        picked = [(only, d) for d in pools[only]]
        title = f"🔥 <b>Deal hời hôm nay: {html.escape(CATEGORIES[only][0])}</b>"
    else:
        only = None
        ranked = sorted(((key, d) for key, rows in pools.items() for d in rows),
                        key=lambda pair: (pair[0] not in mine, pair[1]["price"] / pair[1]["usual"]))
        picked, per_cat, seen = [], {}, set()
        for key, deal in ranked:
            if deal["item_id"] in seen or per_cat.get(key, 0) >= FEED_PER_CAT or len(picked) >= FEED_ITEMS:
                continue
            seen.add(deal["item_id"])
            per_cat[key] = per_cat.get(key, 0) + 1
            picked.append((key, deal))
        title = "🔥 <b>Deal hời hôm nay</b>"
    lines = [title, "Giá thấp nhất 30 ngày và rẻ hơn thường ngày, bot đã kiểm lịch sử giá.", ""]
    buttons = []
    for number, (key, deal) in enumerate(picked, 1):
        icon = CATEGORIES[key][0].split()[0]
        drop = round((deal["usual"] - deal["price"]) * 100 / deal["usual"])
        lines.append(f"{number}. {icon} {html.escape(_short(deal['name']))}: <b>{_k(deal['price'])}</b> "
                     f"(thường {_k(deal['usual'])}, −{drop}%) · hoàn ~{_k(deal['cashback'])}")
        buttons.append([{"text": f"{number}. 🛒 {_short(deal['name'], 28)}",
                         "callback_data": f"u:dl:{deal['shop_id']}:{deal['item_id']}"}])
    lines += ["", DEALS_PICK_HINT, f"Giá theo dữ liệu lúc {at}, có thể đổi khi bạn mở." if at else
              "Giá có thể đổi khi bạn mở.", "Xem theo danh mục: bấm nút bên dưới."]
    chips = [{"text": CATEGORIES[key][0], "callback_data": f"{FEED}:{key}"} for key in pools if key != only]
    if only:
        chips.insert(0, {"text": "🔥 Tất cả", "callback_data": FEED})
    rows = [chips[i:i + 2] for i in range(0, len(chips), 2)]
    return "\n".join(lines), buttons + rows + tail


def feed_for(repo: TrackingRepository, user: int, only: str | None, now: datetime) -> tuple[str, list]:
    pools, latest = current_deals(repo, now, FEED_FRESH)
    return feed_message(pools, user_categories(repo, user), only, _clock(latest))


# --- Lịch chạy --------------------------------------------------------------------------------------------------


def _sale_soon(repo: TrackingRepository, now: datetime) -> bool:
    if not engagement.enabled(repo):
        return False
    return any(abs(slot.at - now) < timedelta(hours=3) for slot in sale_calendar.upcoming(now - timedelta(days=1), 2))


def _hour_key(now: datetime) -> str:
    return now.astimezone(ICT).strftime("%Y-%m-%dT%H")


def scan(repo: TrackingRepository, service, market: MarketSearchClient, history: PriceHistoryClient, now: datetime,
         pause: Callable[[float], None] = clock.sleep) -> dict:
    """Một lượt quét: soạn, gộp kho, gửi. Trả bản ghi lượt (cũng lưu ở SCAN_KEY)."""
    hour = _hour_key(now)
    try:
        found = build(repo, service, market, history, now, pause)
    except PriceWatchError as exc:
        logger.warning("[Cashback] deal hời: AddLiveTag lỗi %s", exc)
        result = {"hour": hour, "status": "error", "error": str(exc), "at": _stamp(now)}
        _save(repo, SCAN_KEY, result)
        return result
    merged, new = merge(pool(repo), found, now)
    _save(repo, POOL_KEY, merged)
    sent = send_round(repo, now)
    result = {"hour": hour, "status": "done", "at": _stamp(now), "found": sum(len(v) for v in found.values()),
              "new": new, "sent": sent}
    _save(repo, SCAN_KEY, result)
    return result


def _start_scan(repo: TrackingRepository, service, market, history, now: datetime,
                pause: Callable[[float], None]) -> None:
    def work() -> None:
        try:
            scan(repo, service, market, history, now, pause)
        except Exception:
            logger.exception("[Cashback] deal hời lỗi bất ngờ")
            _save(repo, SCAN_KEY, {"hour": _hour_key(now), "status": "error", "error": "unexpected", "at": _stamp(now)})
        finally:
            _running.release()

    threading.Thread(target=work, name="deals", daemon=True).start()


def tick(repo: TrackingRepository, service, admin_notifier=None, now: datetime | None = None,
         market: MarketSearchClient | None = None, history: PriceHistoryClient | None = None,
         pause: Callable[[float], None] = clock.sleep) -> None:
    """Gọi mỗi vòng poll của bot Telegram: giờ tròn 7:00–21:00 chưa quét thì quét (luồng nền, một lượt / giờ)."""
    if not enabled(repo):
        return
    moment = now or datetime.now(timezone.utc)
    if moment.astimezone(ICT).hour not in SCAN_HOURS or scan_record(repo).get("hour") == _hour_key(moment):
        return
    if not _running.acquire(blocking=False):
        return
    _save(repo, SCAN_KEY, {**scan_record(repo), "hour": _hour_key(moment), "status": "building", "at": _stamp(moment)})
    _start_scan(repo, service, market or MarketSearchClient(service.settings.api_key),
                history or service.price_history, moment, pause)
