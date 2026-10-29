"""Theo dõi giá món khách chọn (PLAN-103, chủ bot 2026-10-29: «cứ có giảm là thông báo»; khách muốn thì điền giờ
kiểm, không điền thì bot kiểm theo lượt chung).

- Khách bấm 🔔 Báo khi giảm giá trên thẻ link Shopee: bot theo dõi món đó 30 ngày, mốc là giá trên thẻ. Tối đa 10 món
  / khách.
- Mặc định: lượt chung mỗi giờ tròn 7:00–21:00 giờ VN, đọc giá mới nhất ở lịch sử giá AddLiveTag (`history.php`); thấy
  rẻ hơn thì đọc giá thật (product-data) để chắc chắn và tính lại số hoàn. Một món báo cách nhau ít nhất 6 giờ.
- Giờ riêng (tối đa 4 giờ trong 6:00–23:00): tới giờ bot đọc giá thật của món đó. Bot tắt quá 30 phút thì bỏ lượt.
- Có giảm là báo: giá thật thấp hơn giá lần trước bot thấy. Giá lên thì ghi giá mới, nên lần giảm sau vẫn báo.
- Tin qua hàng đợi chung (category `price_watch`): khách chặn bot thì không gửi; khách tắt bằng 🔕 từng món.
Không đổi link, cách tính hoàn hay sổ đơn: nút mua dùng lại link cũ (cùng sub_id).
"""

from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, time, timedelta, timezone

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BUY_BUTTON, STALE_BUTTON, BotReply, buyer_name
from cashback_bot.money import format_vnd
from cashback_bot.price_watch import PriceHistoryClient, PriceWatchError
from cashback_bot.pricing import cashback_for
from cashback_bot.product_data import ProductDataError, quote_from_payload
from cashback_bot.sale_calendar import ICT
from cashback_bot.shopee_url import ShopeeTarget

logger = logging.getLogger("cashback_bot")

ENABLED_KEY = "price_watch_list_enabled"  # chưa có = bật; admin tắt thì "0"
SCAN_KEY = "price_watch_list_scan"
WAIT_PREFIX = "price_watch_wait:"
CATEGORY = "price_watch"
EVENT_TYPE = "PRICE_WATCH"
WATCH_DAYS = 30
MAX_PER_USER = 10
MAX_TIMES = 4
SCAN_HOURS = range(7, 22)  # 7:00 … 21:00 giờ VN, mỗi giờ một lượt
DEFAULT_GAP = timedelta(hours=6)
SLOT_LATE = timedelta(minutes=30)
WAIT_FOR = timedelta(minutes=10)
TIME_FROM, TIME_UNTIL = time(6), time(23)
ADD = "u:pw:a:"
LIST = "u:pw:l"
_TIME = re.compile(r"(\d{1,2})\s*(?:h|g|giờ|:)(\d{2})?", re.I)
_DEFAULT_WORDS = {"mặc định", "mac dinh", "macdinh", "mặc đinh"}
_running = threading.Lock()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(ENABLED_KEY) != "0"


def card_row(sub_id: str | None) -> tuple:
    """Hàng nút 🔔 trên thẻ link Shopee."""
    return ((("🔔 Báo khi giảm giá", f"{ADD}{sub_id}"),),) if sub_id else ()


# --- Giờ kiểm riêng ---------------------------------------------------------------------------------------------


def parse_times(text: str) -> tuple[list[str] | None, str]:
    """(giờ «HH:MM» đã sắp, lỗi). [] = về lượt chung. None + lỗi khi gõ sai."""
    cleaned = " ".join((text or "").lower().split())
    if cleaned in _DEFAULT_WORDS:
        return [], ""
    found = _TIME.findall(cleaned)
    if not found:
        return None, "format"
    times = set()
    for hour, minute in found:
        h, m = int(hour), int(minute or 0)
        if h > 23 or m > 59:
            return None, "format"
        if not TIME_FROM <= time(h, m) <= TIME_UNTIL:
            return None, "range"
        times.add(f"{h:02d}:{m:02d}")
    if len(times) > MAX_TIMES:
        return None, "many"
    return sorted(times), ""


def set_waiting(repo: TrackingRepository, user: int, watch_id: int, now: datetime) -> None:
    repo.set_state(f"{WAIT_PREFIX}{user}", f"{watch_id}|{(now + WAIT_FOR).timestamp():.0f}")


def waiting(repo: TrackingRepository, user: int, now: datetime) -> int | None:
    value = repo.get_state(f"{WAIT_PREFIX}{user}")
    if not value or value == "0":
        return None
    try:
        watch_id, until = value.split("|")
        if float(until) >= now.timestamp():
            return int(watch_id)
    except ValueError:
        pass
    clear_waiting(repo, user)
    return None


def clear_waiting(repo: TrackingRepository, user: int) -> None:
    if repo.get_state(f"{WAIT_PREFIX}{user}") not in (None, "0"):
        repo.set_state(f"{WAIT_PREFIX}{user}", "0")


# --- Bảng price_watches -------------------------------------------------------------------------------------------


def active(conn: sqlite3.Connection, user: int, now: datetime) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM price_watches WHERE telegram_user_id = ? AND stopped_at IS NULL AND expires_at > ? "
        "ORDER BY id", (user, _stamp(now))).fetchall()


def _get(conn: sqlite3.Connection, user: int, watch_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM price_watches WHERE id = ? AND telegram_user_id = ?",
                        (watch_id, user)).fetchone()


def start(repo: TrackingRepository, user: int, sub_id: str, now: datetime) -> tuple[sqlite3.Row | None, str]:
    """Theo dõi món của link `sub_id` (link của chính khách). (dòng, lỗi): lỗi «no_link» · «limit»."""
    with repo.connect() as conn:
        link = conn.execute(
            "SELECT * FROM link_requests WHERE sub_id = ? AND telegram_user_id = ? AND link_status = 'created' "
            "AND platform = 'shopee' AND item_id IS NOT NULL AND shop_id IS NOT NULL AND COALESCE(price_vnd, 0) > 0",
            (sub_id, user)).fetchone()
        if link is None:
            return None, "no_link"
        watching = active(conn, user, now)
        same = next((w for w in watching if w["item_id"] == link["item_id"]), None)
        if same is not None:
            return same, ""
        if len(watching) >= MAX_PER_USER:
            return None, "limit"
        cursor = conn.execute(
            "INSERT INTO price_watches (telegram_user_id, link_id, item_id, shop_id, product_name, start_price_vnd, "
            "last_price_vnd, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user, link["id"], link["item_id"], link["shop_id"], link["product_name"], link["price_vnd"],
             link["price_vnd"], _stamp(now), _stamp(now + timedelta(days=WATCH_DAYS))))
        return _get(conn, user, int(cursor.lastrowid)), ""


def stop(repo: TrackingRepository, user: int, watch_id: int, now: datetime) -> sqlite3.Row | None:
    with repo.connect() as conn:
        conn.execute("UPDATE price_watches SET stopped_at = ? WHERE id = ? AND telegram_user_id = ? "
                     "AND stopped_at IS NULL", (_stamp(now), watch_id, user))
        return _get(conn, user, watch_id)


def _slot_key(moment: datetime) -> str:
    return moment.astimezone(ICT).strftime("%Y-%m-%d %H:%M")


def set_times(repo: TrackingRepository, user: int, watch_id: int, times: list[str], now: datetime) -> None:
    """Đổi giờ kiểm. Giờ đã qua trong hôm nay không kiểm bù (lượt riêng tính từ bây giờ)."""
    with repo.connect() as conn:
        conn.execute("UPDATE price_watches SET check_times = ?, last_slot = ? WHERE id = ? AND telegram_user_id = ?",
                     (",".join(times) or None, _slot_key(now), watch_id, user))


# --- Kiểm giá -----------------------------------------------------------------------------------------------------


def _due_slot(row: sqlite3.Row, now: datetime) -> str | None:
    """Lượt giờ riêng tới giờ mà chưa kiểm (trễ tối đa SLOT_LATE)."""
    local = now.astimezone(ICT)
    for value in reversed((row["check_times"] or "").split(",")):
        try:
            hour, minute = (int(p) for p in value.split(":"))
        except ValueError:
            continue
        at = datetime.combine(local.date(), time(hour, minute), ICT)
        key = _slot_key(at)
        if at <= local and local - at <= SLOT_LATE and key > (row["last_slot"] or ""):
            return key
    return None


def _watching(conn: sqlite3.Connection, now: datetime, custom: bool) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT w.*, l.affiliate_url FROM price_watches w JOIN link_requests l ON l.id = w.link_id "
        "WHERE w.stopped_at IS NULL AND w.expires_at > ? AND w.check_times IS " + ("NOT NULL" if custom else "NULL")
        + " ORDER BY w.id", (_stamp(now),)).fetchall()


def _quote(service, row: sqlite3.Row, now: datetime):
    try:
        payload = service.client.fetch(ShopeeTarget("", int(row["item_id"]), int(row["shop_id"]), None))
        return quote_from_payload(payload, now, service.settings.product_max_age_hours)
    except ProductDataError as exc:
        logger.info("[Cashback] theo dõi giá: product-data lỗi %s item=%s", exc.code, row["item_id"])
        return None


def _seen(conn: sqlite3.Connection, row: sqlite3.Row, price: int | None, now: datetime, slot: str | None = None) -> None:
    """Ghi lần kiểm. Giá lên thì lấy giá mới làm mốc (lần giảm sau vẫn báo)."""
    last = int(row["last_price_vnd"])
    conn.execute("UPDATE price_watches SET last_checked_at = ?, last_price_vnd = ?, last_slot = COALESCE(?, last_slot) "
                 "WHERE id = ?", (_stamp(now), max(last, price) if price else last, slot, row["id"]))


def _alert(conn: sqlite3.Connection, service, row: sqlite3.Row, quote, now: datetime, slot: str | None = None) -> None:
    old, new = int(row["last_price_vnd"]), int(quote.price_vnd)
    cashback = cashback_for(quote.sure_commission_vnd, service._resolve_policy(now)).cashback_vnd
    keyboard = [[{"text": BUY_BUTTON, "url": row["affiliate_url"]}]] if row["affiliate_url"] else []
    keyboard.append([{"text": "🔕 Ngừng theo dõi", "callback_data": f"u:pw:x:{row['id']}"},
                     {"text": "📋 Món đang theo dõi", "callback_data": LIST}])
    enqueue_event(conn, event_key=f"price_watch:{row['id']}:{_stamp(now)}", event_type=EVENT_TYPE,
                  chat_id=int(row["telegram_user_id"]), message_html=alert_text(row, old, new, cashback),
                  audience="customer", category=CATEGORY, source_ref=f"price_watch:{row['id']}",
                  reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False), now=_stamp(now))
    conn.execute("UPDATE price_watches SET last_price_vnd = ?, last_alert_at = ?, last_checked_at = ?, "
                 "last_slot = COALESCE(?, last_slot), alerts = alerts + 1 WHERE id = ?",
                 (new, _stamp(now), _stamp(now), slot, row["id"]))


def run_default(repo: TrackingRepository, service, history: PriceHistoryClient, now: datetime) -> dict:
    """Lượt chung: món không đặt giờ riêng. Trả số liệu lượt."""
    with repo.connect() as conn:
        rows = _watching(conn, now, custom=False)
    if not rows:
        return {"checked": 0, "sent": 0}
    prices = history.latest(sorted({int(r["item_id"]) for r in rows}))
    sent = 0
    for row in rows:
        point = prices.get(int(row["item_id"]))
        last_alert = _parse(row["last_alert_at"])
        quote = None
        if (point is not None and point.price < int(row["last_price_vnd"]) and point.in_stock is not False
                and (last_alert is None or now - last_alert >= DEFAULT_GAP)):
            quote = _quote(service, row, now)  # lịch sử giá báo rẻ hơn: đọc giá thật cho chắc
        with repo.connect() as conn:
            if quote is not None and quote.price_vnd < int(row["last_price_vnd"]):
                _alert(conn, service, row, quote, now)
                sent += 1
            else:
                observed = quote.price_vnd if quote is not None else (point.price if point is not None else None)
                _seen(conn, row, observed, now)
    return {"checked": len(rows), "sent": sent}


def run_slots(repo: TrackingRepository, service, now: datetime) -> int:
    """Lượt giờ riêng tới giờ: đọc giá thật từng món. Trả số tin."""
    with repo.connect() as conn:
        due = [(row, slot) for row in _watching(conn, now, custom=True) if (slot := _due_slot(row, now))]
    sent = 0
    for row, slot in due:
        quote = _quote(service, row, now)
        with repo.connect() as conn:
            if quote is not None and quote.price_vnd < int(row["last_price_vnd"]):
                _alert(conn, service, row, quote, now, slot)
                sent += 1
            else:
                _seen(conn, row, quote.price_vnd if quote is not None else None, now, slot)
    return sent


def _hour_key(now: datetime) -> str:
    return now.astimezone(ICT).strftime("%Y-%m-%dT%H")


def scan_record(repo: TrackingRepository) -> dict:
    try:
        return json.loads(repo.get_state(SCAN_KEY) or "{}")
    except ValueError:
        return {}


def _slots_due(repo: TrackingRepository, now: datetime) -> bool:
    with repo.connect() as conn:
        return any(_due_slot(row, now) for row in _watching(conn, now, custom=True))


def work(repo: TrackingRepository, service, history: PriceHistoryClient, now: datetime, default: bool) -> None:
    """Một lượt (giờ riêng tới giờ, kèm lượt chung nếu tới giờ tròn). Lỗi AddLiveTag chỉ ghi trạng thái."""
    record = {"hour": _hour_key(now), "at": _stamp(now)} if default else None
    try:
        sent = run_slots(repo, service, now)
        if record is not None:
            record.update(status="done", **run_default(repo, service, history, now))
            record["sent"] += sent
    except PriceWatchError as exc:
        logger.warning("[Cashback] theo dõi giá: AddLiveTag lỗi %s", exc)
        if record is not None:
            record.update(status="error", error=str(exc))
    if record is not None:
        repo.set_state(SCAN_KEY, json.dumps(record))


def tick(repo: TrackingRepository, service, now: datetime | None = None,
         history: PriceHistoryClient | None = None) -> threading.Thread | None:
    """Gọi mỗi vòng poll: giờ riêng tới giờ, hoặc giờ tròn 7:00–21:00 chưa có lượt chung, thì chạy ở luồng nền."""
    if not enabled(repo):
        return None
    moment = now or datetime.now(timezone.utc)
    default = (moment.astimezone(ICT).hour in SCAN_HOURS and scan_record(repo).get("hour") != _hour_key(moment))
    if not default and not _slots_due(repo, moment):
        return None
    if not _running.acquire(blocking=False):
        return None
    if default:
        repo.set_state(SCAN_KEY, json.dumps({**scan_record(repo), "hour": _hour_key(moment), "status": "building"}))

    def run() -> None:
        try:
            work(repo, service, history or service.price_history, moment, default)
        except Exception:
            logger.exception("[Cashback] theo dõi giá lỗi bất ngờ")
            if default:
                repo.set_state(SCAN_KEY, json.dumps({"hour": _hour_key(moment), "status": "error",
                                                     "error": "unexpected", "at": _stamp(moment)}))
        finally:
            _running.release()

    thread = threading.Thread(target=run, name="price-watch-list", daemon=True)
    thread.start()
    return thread


def stats(conn: sqlite3.Connection, now: datetime) -> tuple[int, int]:
    """(món đang theo dõi, tin 7 ngày qua) cho màn admin."""
    watching = conn.execute("SELECT COUNT(*) FROM price_watches WHERE stopped_at IS NULL AND expires_at > ?",
                            (_stamp(now),)).fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type = ? AND created_at >= ?",
                        (EVENT_TYPE, _stamp(now - timedelta(days=7)))).fetchone()[0]
    return int(watching), int(sent)


# --- Chữ gửi khách ------------------------------------------------------------------------------------------------


def _name(row) -> str:
    return html.escape(buyer_name(row["product_name"] or "Món này"))


def _short(row, limit: int = 28) -> str:
    name = buyer_name(row["product_name"] or "Món này")
    return name if len(name) <= limit else name[:limit - 1].rstrip() + "…"


def _until(row) -> str:
    moment = _parse(row["expires_at"])
    return moment.astimezone(ICT).strftime("%d/%m") if moment else "-"


def schedule_text(row) -> str:
    times = [t.replace(":00", "h").replace(":", "h") for t in (row["check_times"] or "").split(",") if t]
    return ("lúc " + ", ".join(times) + " mỗi ngày") if times else "mỗi giờ 7:00–21:00"


def alert_text(row, old: int, new: int, cashback: int) -> str:
    percent = max(1, round((old - new) * 100 / old)) if old > 0 else 0
    lines = [
        "📉 <b>Món bạn theo dõi vừa giảm giá</b>",
        f"🛍️ {_name(row)}",
        f"<s>{format_vnd(old)}</s> → <b>{format_vnd(new)}</b> (−{percent}%)",
    ]
    if cashback > 0:
        lines.append(f"💰 Hoàn dự kiến theo giá mới: khoảng <b>{format_vnd(cashback)}</b>")
    lines += ["", "Mua qua link bot vẫn được hoàn như thường nha 😎",
              f"ⓘ <i>Giá có thể đổi nhanh. Bot theo dõi tới {_until(row)}; gõ /theodoi để xem hay bỏ món.</i>"]
    return "\n".join(lines)


def item_reply(row, notice: str = "") -> BotReply:
    stopped = row["stopped_at"] is not None
    lines = [("🔕 <b>Đã ngừng theo dõi</b>" if stopped else "🔔 <b>Đang theo dõi giá</b>"), ""]
    if notice:
        lines += [notice, ""]
    lines += [
        f"🛍️ {_name(row)}",
        f"Giá lúc bắt đầu: {format_vnd(int(row['start_price_vnd']))} · gần nhất: "
        f"{format_vnd(int(row['last_price_vnd']))}",
    ]
    if not stopped:
        lines += [
            f"⏰ Bot kiểm giá {schedule_text(row)} · theo dõi tới {_until(row)}",
            "Có giảm là bot nhắn bạn liền.",
            "",
            "Muốn bot kiểm vào giờ riêng của bạn: chọn ⏰ Đặt giờ kiểm.",
        ]
    keyboard = [] if stopped else [(("⏰ Đặt giờ kiểm", f"u:pw:t:{row['id']}"),),
                                   (("🔕 Ngừng theo dõi", f"u:pw:x:{row['id']}"),)]
    keyboard.append((("📋 Món đang theo dõi", LIST), ("◀️ Trang chủ", "u:p:home")))
    return BotReply("\n".join(lines), inline_keyboard=tuple(keyboard))


def list_reply(rows: list, notice: str = "") -> BotReply:
    lines = ["📋 <b>Món đang theo dõi giá</b>", ""]
    if notice:
        lines += [notice, ""]
    if not rows:
        lines += ["Bạn chưa theo dõi món nào.",
                  "Dán link sản phẩm Shopee vào đây rồi chọn 🔔 Báo khi giảm giá, có giảm là bot nhắn bạn."]
        return BotReply("\n".join(lines), inline_keyboard=((("◀️ Trang chủ", "u:p:home"),),))
    for number, row in enumerate(rows, start=1):
        lines.append(f"{number}. {_name(row)} · {format_vnd(int(row['last_price_vnd']))} · kiểm {schedule_text(row)}")
    lines += ["", f"Theo dõi tối đa {MAX_PER_USER} món. Chọn một món để đổi giờ kiểm hay ngừng theo dõi."]
    keyboard = [((f"🔔 {_short(row)}", f"u:pw:i:{row['id']}"),) for row in rows]
    keyboard.append((("◀️ Trang chủ", "u:p:home"),))
    return BotReply("\n".join(lines), inline_keyboard=tuple(keyboard))


TIMES_PROMPT = (
    "⏰ <b>Đặt giờ kiểm giá</b>\n\n"
    "Gõ giờ bạn muốn bot kiểm giá món này mỗi ngày, ví dụ: <code>12h 20h30</code> hoặc <code>12:00</code>.\n"
    f"Tối đa {MAX_TIMES} giờ, trong 6:00–23:00.\n"
    "Không đặt giờ thì bot kiểm mỗi giờ 7:00–21:00."
)
TIMES_ERRORS = {
    "format": "Bot chưa đọc được giờ. Gõ kèm chữ h hoặc dấu hai chấm, ví dụ: 12h 20h30 hoặc 12:00.",
    "range": "Bot chỉ kiểm trong 6:00–23:00. Bạn gõ lại giờ trong khoảng đó nha.",
    "many": f"Tối đa {MAX_TIMES} giờ mỗi món. Bạn gõ lại ít giờ hơn nha.",
}
LIMIT_TEXT = (f"Bạn đang theo dõi {MAX_PER_USER} món (tối đa). Bỏ bớt món ở 📋 Món đang theo dõi rồi chọn lại nha.")
OFF_TEXT = "Tính năng theo dõi giá đang tạm tắt."


def times_reply(row, error: str = "") -> BotReply:
    text = TIMES_PROMPT if not error else f"⚠️ {TIMES_ERRORS[error]}\n\n{TIMES_PROMPT}"
    return BotReply(text, inline_keyboard=((("↩️ Kiểm mỗi giờ (mặc định)", f"u:pw:d:{row['id']}"),),
                                           (("◀️ Quay lại", f"u:pw:i:{row['id']}"),)))


def action(repo: TrackingRepository, user: int, data: str, now: datetime) -> BotReply:
    """Nút u:pw:* của khách."""
    if not enabled(repo):
        return BotReply("", toast=OFF_TEXT, show_alert=True)
    if data.startswith(ADD):
        row, error = start(repo, user, data.removeprefix(ADD), now)
        if error == "limit":
            with repo.connect() as conn:
                return list_reply(active(conn, user, now), LIMIT_TEXT)
        if row is None:
            return BotReply("", toast=STALE_BUTTON)
        return item_reply(row, "✅ Đã bật theo dõi. Bot lấy giá trên thẻ làm mốc.")
    if data == LIST:
        clear_waiting(repo, user)
        with repo.connect() as conn:
            return list_reply(active(conn, user, now))
    parts = data.split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        return BotReply("", toast=STALE_BUTTON)
    verb, watch_id = parts[2], int(parts[3])
    with repo.connect() as conn:
        row = _get(conn, user, watch_id)
    if row is None:
        return BotReply("", toast=STALE_BUTTON)
    if verb == "x":
        clear_waiting(repo, user)
        stopped = stop(repo, user, watch_id, now)
        with repo.connect() as conn:
            return list_reply(active(conn, user, now), f"🔕 Đã ngừng theo dõi {_name(stopped)}.")
    if verb == "i":
        clear_waiting(repo, user)
        return item_reply(row)
    if row["stopped_at"] is not None or (_parse(row["expires_at"]) or now) <= now:
        return BotReply("", toast=STALE_BUTTON)
    if verb == "t":
        set_waiting(repo, user, watch_id, now)
        return times_reply(row)
    if verb == "d":
        clear_waiting(repo, user)
        set_times(repo, user, watch_id, [], now)
        with repo.connect() as conn:
            return item_reply(_get(conn, user, watch_id), "✅ Bot kiểm giá mỗi giờ 7:00–21:00.")
    return BotReply("", toast=STALE_BUTTON)


def consume_times(repo: TrackingRepository, user: int, watch_id: int, text: str, now: datetime) -> BotReply:
    """Khách gõ giờ sau khi chọn ⏰ Đặt giờ kiểm."""
    with repo.connect() as conn:
        row = _get(conn, user, watch_id)
    if row is None or row["stopped_at"] is not None:
        clear_waiting(repo, user)
        return BotReply(STALE_BUTTON)
    times, error = parse_times(text)
    if times is None:
        return times_reply(row, error)
    clear_waiting(repo, user)
    set_times(repo, user, watch_id, times, now)
    with repo.connect() as conn:
        row = _get(conn, user, watch_id)
    return item_reply(row, f"✅ Bot sẽ kiểm giá {schedule_text(row)}.")
