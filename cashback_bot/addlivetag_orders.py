"""PLAN-098: đơn Shopee qua API AddLiveTag (không chính thống) để đối soát chéo với nguồn cookie. Chỉ đọc.

- AddLiveTag đọc cùng báo cáo Shopee từ tài khoản chủ bot đã gắn cookie trên AddLiveTag. Không có order_id (khoá đơn
  của bot) và không có is_fraud, nên KHÔNG BAO GIỜ ghi vào shopee_conversions / cashback_entries; nguồn cookie vẫn là
  nguồn chính. Kết quả chỉ nằm ở bot_state và tin báo admin.
- Bước A (ở đây): mỗi ngày từ 09:00 giờ VN so 30 ngày theo order_sn, chỉ đơn có sub_id là link bot. Báo admin khi:
  AddLiveTag có đơn mà bot chưa có / chưa gán link (mua quá 6 giờ), lệch huỷ, lệch hoa hồng (từ 100đ và từ 2%).
  Bot có mà AddLiveTag chưa có (mua quá 3 ngày) chỉ đếm: AddLiveTag vốn chậm hơn bot.
- Bước B (dự phòng): có sự cố đồng bộ đang mở, cookie không ở trạng thái kết nối, hoặc đồng bộ thành công gần nhất
  đã quá 6 giờ → mỗi 60 phút đọc 3 ngày. Đơn qua link bot mà order_sn chưa có trong DB (chưa huỷ): báo admin và báo
  khách «có đơn mới» (cùng hàng đợi, cùng điều kiện gửi như tin đơn thường), ghi bot_state alt_order:<order_sn>.
  Cookie chạy lại thì đồng bộ chính ghi đơn như cũ; order_notify thấy alt_order đã xếp gửi thì không báo khách lần hai.
- Khoá dùng ADDLIVETAG_API_KEY sẵn có. Không log khoá, không lưu dữ liệu thô.
"""

from __future__ import annotations

import html
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import order_new_notice
from cashback_bot.money import format_vnd
from cashback_bot.notify_dispatch import BASELINE_KEY, NotifyConfig, customer_block_reason
from cashback_bot.order_notify import ALT_NOTIFIED_KEY, cashback_of, short_order
from cashback_bot.shopee_sync import _bot_sub_id

logger = logging.getLogger("cashback_bot")

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
URL = "https://addlivetag.com/api/v1/conversions.php"
PAGE_SIZE = 50
MAX_PAGES = 40
PAGE_PAUSE_SEC = 1.0
TIMEOUT_SEC = 20
WINDOW_DAYS = 30
RUN_HOUR = 9  # giờ VN
MISSING_AFTER = timedelta(hours=6)
LAG_AFTER = timedelta(days=3)
DIFF_MIN_VND = 100
DIFF_MIN_RATIO = 0.02
REPORT_LIMIT = 5
DAY_KEY = "alt_crosscheck_day"
RESULT_KEY = "alt_crosscheck_result"
FALLBACK_STALE = timedelta(hours=6)
FALLBACK_EVERY = timedelta(minutes=60)
FALLBACK_DAYS = 3
FALLBACK_KEY = "alt_fallback_last"
FALLBACK_NOTE = "ⓘ Số tiền sẽ cập nhật khi bot đồng bộ lại với Shopee."
# status_code AddLiveTag → order_status kiểu Shopee cho nhãn tình trạng đơn
STATUS_MAP = {"completed": "COMPLETED", "paid": "PAID", "pending": "PENDING", "unpaid": "UNPAID"}
ORDERS_KEYBOARD = json.dumps({"inline_keyboard": [[
    {"text": "📦 Đơn hàng của tôi", "callback_data": "u:o:l:1"}, {"text": "📩 Hỗ trợ", "callback_data": "u:p:support"},
]]})

_running = threading.Lock()
_fallback_running = threading.Lock()


class AltError(Exception):
    """kind: auth · rate_limited · http_error · timeout · transport · invalid_json · not_ok · too_many_pages"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class AltOrder:
    order_sn: str
    sub_id: str | None
    purchase_time: datetime | None
    net_vnd: int  # hoa hồng các món trừ phí MCN
    cancelled: bool
    status_code: str = ""
    item_name: str | None = None


class AltOrdersClient:
    def __init__(self, api_key: str, url: str = URL, timeout: float = TIMEOUT_SEC,
                 sleep=time.sleep, pause: float = PAGE_PAUSE_SEC):
        self._api_key = api_key
        self._url = url
        self._timeout = timeout
        self._sleep = sleep
        self._pause = pause

    def _page(self, start: int, end: int, page: int) -> dict:
        try:
            response = requests.get(
                self._url,
                params={"type": "items", "source": "shopee", "from": start, "to": end, "page": page,
                        "page_size": PAGE_SIZE},
                headers={"X-API-Key": self._api_key},
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise AltError("timeout") from exc
        except requests.RequestException as exc:
            raise AltError("transport") from exc
        if response.status_code in (401, 403):
            raise AltError("auth")
        if response.status_code == 429:
            raise AltError("rate_limited")
        if response.status_code != 200:
            raise AltError("http_error")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AltError("invalid_json") from exc
        if not isinstance(payload, dict) or not payload.get("ok") or not isinstance(payload.get("data"), list):
            raise AltError("not_ok")
        return payload

    def fetch_items(self, start: datetime, end: datetime) -> list[dict]:
        """Mọi dòng món trong khung, đi hết các trang (trần MAX_PAGES)."""
        rows: list[dict] = []
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
        for page in range(1, MAX_PAGES + 1):
            if page > 1:
                self._sleep(self._pause)
            payload = self._page(start_ts, end_ts, page)
            data = [row for row in payload["data"] if isinstance(row, dict)]
            rows.extend(data)
            total = (payload.get("meta") or {}).get("total")
            if not data or (isinstance(total, int) and len(rows) >= total):
                return rows
        raise AltError("too_many_pages")


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _moment(value) -> datetime | None:
    stamp = _int(value)
    return datetime.fromtimestamp(stamp, timezone.utc) if stamp > 0 else None


def _is_cancelled(*values) -> bool:
    text = " ".join(str(v or "") for v in values).lower()
    return "cancel" in text or "huỷ" in text or "hủy" in text


def group_orders(rows: list[dict], bot_sub_ids: set[str]) -> dict[str, AltOrder]:
    """Gộp dòng món theo order_sn, chỉ giữ đơn có sub_id là link bot."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        order_sn = str(row.get("order_sn") or "").strip()
        sub_id = _bot_sub_id(row.get("sub_id1") or row.get("utm"))
        if order_sn and sub_id in bot_sub_ids:
            grouped.setdefault(order_sn, []).append(row)
    orders = {}
    for order_sn, items in grouped.items():
        times = [t for t in (_moment(item.get("purchase_time")) for item in items) if t]
        orders[order_sn] = AltOrder(
            order_sn=order_sn,
            sub_id=_bot_sub_id(items[0].get("sub_id1") or items[0].get("utm")),
            purchase_time=min(times) if times else None,
            net_vnd=sum(_int(item.get("commission")) - _int(item.get("mcn_fee")) for item in items),
            cancelled=all(_is_cancelled(item.get("status_code"), item.get("status")) for item in items),
            status_code=str(items[0].get("status_code") or "").lower(),
            item_name=str(items[0].get("item_name") or "").strip()[:60] or None,
        )
    return orders


@dataclass
class CrossCheck:
    day: str
    at: str
    compared: int = 0  # đơn có ở cả hai nguồn
    matched: int = 0  # trong số đó, khớp huỷ và hoa hồng
    missing_in_bot: list[str] = field(default_factory=list)
    not_linked: list[str] = field(default_factory=list)
    cancel_mismatch: list[str] = field(default_factory=list)
    commission_mismatch: list[str] = field(default_factory=list)  # "order_sn: bot X · AddLiveTag Y"
    alt_lagging: int = 0
    error: str | None = None

    @property
    def problems(self) -> int:
        return len(self.missing_in_bot) + len(self.not_linked) + len(self.cancel_mismatch) + len(self.commission_mismatch)


def compare(conn: sqlite3.Connection, alt: dict[str, AltOrder], now: datetime, since: datetime,
            result: CrossCheck) -> CrossCheck:
    bot = {}
    for row in conn.execute(
        "SELECT order_sn, order_status, net_commission_vnd, matched_link_id, purchase_time FROM shopee_conversions "
        "WHERE platform = 'shopee' AND order_sn IS NOT NULL"
    ):
        bot.setdefault(str(row[0]), []).append(row)
    for order_sn, order in sorted(alt.items()):
        rows = bot.get(order_sn)
        old = order.purchase_time is None or now - order.purchase_time >= MISSING_AFTER
        if not rows:
            if old:
                result.missing_in_bot.append(order_sn)
            continue
        if all(row[3] is None for row in rows):
            if old:
                result.not_linked.append(order_sn)
            continue
        result.compared += 1
        bot_cancelled = all("CANCEL" in str(row[1] or "").upper() for row in rows)
        if bot_cancelled != order.cancelled:
            result.cancel_mismatch.append(order_sn)
            continue
        bot_net = sum(int(row[2] or 0) for row in rows)
        diff = abs(bot_net - order.net_vnd)
        if not bot_cancelled and diff >= DIFF_MIN_VND and diff >= DIFF_MIN_RATIO * max(bot_net, order.net_vnd):
            result.commission_mismatch.append(
                f"{order_sn}: bot {format_vnd(bot_net)} · AddLiveTag {format_vnd(order.net_vnd)}")
            continue
        result.matched += 1
    for order_sn, rows in bot.items():
        if order_sn in alt or all(row[3] is None for row in rows):
            continue
        bought = min((_parse_iso(row[4]) for row in rows if row[4]), default=None)
        if bought is not None and since <= bought <= now - LAG_AFTER:
            result.alt_lagging += 1
    return result


def _parse_iso(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(repo: TrackingRepository, client: AltOrdersClient, now: datetime) -> CrossCheck:
    day = now.astimezone(ICT).date().isoformat()
    result = CrossCheck(day=day, at=_stamp(now))
    since = now - timedelta(days=WINDOW_DAYS)
    with repo.connect() as conn:
        subs = {str(row[0]) for row in conn.execute(
            "SELECT sub_id FROM link_requests WHERE sub_id IS NOT NULL AND platform = 'shopee'")}
    try:
        rows = client.fetch_items(since, now)
    except AltError as exc:
        result.error = exc.kind
        return result
    with repo.connect() as conn:
        return compare(conn, group_orders(rows, subs), now, since, result)


def due(repo: TrackingRepository, now: datetime) -> bool:
    local = now.astimezone(ICT)
    return local.hour >= RUN_HOUR and repo.get_state(DAY_KEY) != local.date().isoformat()


def maybe_start(repo: TrackingRepository, client: AltOrdersClient | None, admin_notifier=None,
                now: datetime | None = None) -> threading.Thread | None:
    """Gọi mỗi vòng poll. Tới giờ và chưa chạy hôm nay thì chạy một lượt trong luồng nền."""
    moment = now or datetime.now(timezone.utc)
    if client is None or not due(repo, moment) or not _running.acquire(blocking=False):
        return None
    # Ghi ngày trước khi chạy: lỗi thì mai thử lại, không gọi AddLiveTag liên tục.
    repo.set_state(DAY_KEY, moment.astimezone(ICT).date().isoformat())

    def work() -> None:
        try:
            result = run(repo, client, moment)
            repo.set_state(RESULT_KEY, json.dumps(asdict(result), ensure_ascii=False))
            if result.error:
                logger.warning("[Cashback] đối soát AddLiveTag lỗi %s", result.error)
            elif result.problems and admin_notifier is not None:
                admin_notifier.notify_alt_crosscheck(result.day, report_text(result))
        except Exception:
            logger.exception("[Cashback] đối soát AddLiveTag lỗi bất ngờ")
            repo.set_state(RESULT_KEY, json.dumps({"day": moment.astimezone(ICT).date().isoformat(),
                                                   "error": "unexpected"}))
        finally:
            _running.release()

    thread = threading.Thread(target=work, name="alt-crosscheck", daemon=True)
    thread.start()
    return thread


def _listed(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    lines = [f"{title} ({len(items)}):"] + [f"• <code>{item}</code>" for item in items[:REPORT_LIMIT]]
    if len(items) > REPORT_LIMIT:
        lines.append(f"… và {len(items) - REPORT_LIMIT} đơn khác")
    return lines


def report_text(r: CrossCheck) -> str:
    day = datetime.fromisoformat(r.day).strftime("%d/%m")
    lines = [f"🔁 <b>Đối soát AddLiveTag {day}: lệch {r.problems} đơn</b>", "",
             "So 30 ngày đơn qua link bot giữa nguồn cookie Shopee của bot và AddLiveTag. Bot không tự sửa gì.", ""]
    for title, items in (
        ("❗ AddLiveTag có, bot chưa có (kiểm cookie / bấm 🔄 đồng bộ)", r.missing_in_bot),
        ("🔗 Bot có đơn nhưng chưa gán link", r.not_linked),
        ("🚫 Lệch huỷ (một bên huỷ, bên kia không)", r.cancel_mismatch),
        ("💸 Lệch hoa hồng", r.commission_mismatch),
    ):
        block = _listed(title, items)
        if block:
            lines += block + [""]
    lines.append(f"Khớp {r.matched}/{r.compared} đơn có ở cả hai nguồn.")
    return "\n".join(lines)


def status_line(repo: TrackingRepository) -> str | None:
    """Một dòng cho màn 🔗 Shopee Affiliate. None khi chưa chạy lần nào."""
    try:
        saved = json.loads(repo.get_state(RESULT_KEY) or "null")
    except ValueError:
        return None
    if not isinstance(saved, dict) or not saved.get("day"):
        return None
    day = datetime.fromisoformat(saved["day"]).strftime("%d/%m")
    if saved.get("error"):
        return f"🔁 Đối soát AddLiveTag {day}: ⚠️ chưa đọc được ({saved['error']}), mai thử lại"
    problems = sum(len(saved.get(key) or ()) for key in
                   ("missing_in_bot", "not_linked", "cancel_mismatch", "commission_mismatch"))
    text = f"🔁 Đối soát AddLiveTag {day}: khớp {saved.get('matched', 0)}/{saved.get('compared', 0)}"
    if problems:
        text += f" · ⚠️ lệch {problems}"
    if saved.get("alt_lagging"):
        text += f" · AddLiveTag chưa có {saved['alt_lagging']} đơn"
    return text


# --- Bước B: nguồn dự phòng khi cookie Shopee lỗi -------------------------------------------------------


def cookie_down(conn: sqlite3.Connection, now: datetime) -> bool:
    """Sự cố đồng bộ đang mở, cookie không kết nối, hoặc lần đồng bộ thành công gần nhất quá 6 giờ."""
    if conn.execute("SELECT 1 FROM shopee_sync_incidents WHERE resolved_at IS NULL LIMIT 1").fetchone():
        return True
    row = conn.execute("SELECT status, last_sync_at FROM shopee_cookies WHERE id = 1").fetchone()
    if row is None or row[0] != "connected" or not row[1]:
        return True
    last = _parse_iso(row[1])
    return last is None or now - last > FALLBACK_STALE


def fallback_due(repo: TrackingRepository, now: datetime) -> bool:
    last = _parse_iso(repo.get_state(FALLBACK_KEY) or "")
    if last is not None and now - last < FALLBACK_EVERY:
        return False
    with repo.connect() as conn:
        return cookie_down(conn, now)


def _notify_customer(conn: sqlite3.Connection, cfg: NotifyConfig, order: AltOrder, link, stamp: str,
                     now: datetime) -> str:
    """Xếp tin «có đơn mới» cho người tạo link. Trả "queued" hoặc "suppressed:<lý do>"."""
    user, link_id = int(link["telegram_user_id"]), int(link["id"])
    status = STATUS_MAP.get(order.status_code, order.status_code.upper() or None)
    first = conn.execute("SELECT 1 FROM shopee_conversions WHERE telegram_user_id = ? AND matched_link_id IS NOT NULL",
                         (user,)).fetchone() is None
    body = order_new_notice(short_order(order.order_sn, order.order_sn), cashback_of(conn, link_id, order.net_vnd),
                            status, None, first=first) + f"\n\n{FALLBACK_NOTE}"
    baseline = conn.execute("SELECT value FROM bot_state WHERE key = ?", (BASELINE_KEY,)).fetchone()
    bought = _stamp(order.purchase_time) if order.purchase_time else ""
    if baseline is not None and bought and bought < baseline[0]:
        reason = "historical"
    else:
        reason = customer_block_reason(conn, {"category": "order_new", "chat_id": user, "created_at": stamp}, cfg, now)
    enqueue_event(
        conn, event_key=f"alt_order:{order.order_sn}:first_matched", event_type="ORDER_ORDER_NEW", chat_id=user,
        message_html=body, audience="customer", category="order_new", reply_markup_json=ORDERS_KEYBOARD,
        source_ref=f"alt_order:{order.order_sn}", suppressed_reason=reason, now=stamp,
    )
    return f"suppressed:{reason}" if reason else "queued"


def run_fallback(repo: TrackingRepository, client: AltOrdersClient, cfg: NotifyConfig, now: datetime) -> list[str]:
    """Một lượt dự phòng. Trả các dòng cho tin admin (mỗi đơn mới một dòng). Không ghi sổ đơn hay sổ hoàn."""
    stamp = _stamp(now)
    with repo.connect() as conn:
        subs = {str(row[0]) for row in conn.execute(
            "SELECT sub_id FROM link_requests WHERE sub_id IS NOT NULL AND platform = 'shopee'")}
    orders = group_orders(client.fetch_items(now - timedelta(days=FALLBACK_DAYS), now), subs)
    lines = []
    with repo.connect() as conn:
        for order_sn, order in sorted(orders.items()):
            key = ALT_NOTIFIED_KEY.format(order_sn)
            if order.cancelled or conn.execute("SELECT 1 FROM bot_state WHERE key = ?", (key,)).fetchone():
                continue
            if conn.execute("SELECT 1 FROM shopee_conversions WHERE order_sn = ? LIMIT 1", (order_sn,)).fetchone():
                continue
            link = conn.execute("SELECT id, telegram_user_id FROM link_requests WHERE sub_id = ? ORDER BY id LIMIT 1",
                                (order.sub_id,)).fetchone()
            if link is None or link["telegram_user_id"] is None:
                continue
            customer = _notify_customer(conn, cfg, order, link, stamp, now)
            conn.execute(
                "INSERT INTO bot_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps({"at": stamp, "user": int(link["telegram_user_id"]), "customer": customer})),
            )
            told = "đã xếp báo khách" if customer == "queued" else f"không báo khách ({customer.split(':', 1)[1]})"
            lines.append(f"• <code>{order_sn}</code> · khách <code>{link['telegram_user_id']}</code> · "
                         f"HH {format_vnd(order.net_vnd)} · {html.escape(order.item_name or '')} · {told}")
    return lines


def fallback_text(lines: list[str]) -> str:
    return "\n".join([
        f"🛟 <b>{len(lines)} đơn mới qua bot (nguồn dự phòng AddLiveTag)</b>", "",
        "Cookie Shopee đang lỗi hoặc chưa đồng bộ được, bot đọc đơn từ AddLiveTag.",
        "Đơn chỉ vào sổ và 👛 Ví khi đồng bộ Shopee chạy lại; lúc đó khách không nhận tin lần hai.", "",
        *lines,
    ])


def maybe_fallback(repo: TrackingRepository, client: AltOrdersClient | None, cfg: NotifyConfig, admin_notifier=None,
                   now: datetime | None = None) -> threading.Thread | None:
    """Gọi mỗi vòng poll. Cookie lỗi và đã quá 60 phút từ lượt trước thì chạy một lượt dự phòng trong luồng nền."""
    moment = now or datetime.now(timezone.utc)
    if client is None or not fallback_due(repo, moment) or not _fallback_running.acquire(blocking=False):
        return None
    repo.set_state(FALLBACK_KEY, _stamp(moment))

    def work() -> None:
        try:
            lines = run_fallback(repo, client, cfg, moment)
            if lines and admin_notifier is not None:
                admin_notifier.notify_alt_fallback_orders(_stamp(moment), fallback_text(lines))
        except AltError as exc:
            logger.warning("[Cashback] dự phòng AddLiveTag lỗi %s", exc.kind)
        except Exception:
            logger.exception("[Cashback] dự phòng AddLiveTag lỗi bất ngờ")
        finally:
            _fallback_running.release()

    thread = threading.Thread(target=work, name="alt-fallback", daemon=True)
    thread.start()
    return thread
