"""Báo mã giảm giá Shopee (PLAN-104): đọc tin AddLiveTag «Theo dõi Voucher» trong kênh trung gian, gửi khách đã bật.

AddLiveTag gửi tin bằng bot chuyển tin của chủ bot vào một kênh Telegram riêng tư. Bot hoàn tiền là quản trị kênh nên
nhận `channel_post` / `edited_channel_post`. Chỉ đọc kênh đã gắn ở /admin; kênh lạ chỉ ghi tên + id để admin gắn.
Không gọi AddLiveTag hay Shopee.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from cashback_bot.affiliate import build_voucher_redir
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BotReply
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason

ENABLED_KEY = "voucher_enabled"  # vắng = bật; chỉ chạy khi đã gắn kênh
CHANNEL_KEY = "voucher_channel"
SEEN_KEY = "voucher_seen_channel"
SKIPPED_KEY = "voucher_skipped"
ON_PREFIX = "voucher_on:"
# Người nhận: "all" = mọi khách; vắng = chế độ thử, chỉ admin (chủ bot 2026-10-30: «cần test trước cho admin đã»).
AUDIENCE_KEY = "voucher_audience"
TEST_NOTE = "🧪 <i>Tin thử: chỉ admin nhận. Bật gửi khách ở /admin → 📣 Nhắc mùa sale → 🎟 Báo mã.</i>"
CATEGORY = "voucher"
EVENT_TYPE = "VOUCHER"
LIST = "u:vc:l"
ON = "u:vc:on"
OFF = "u:vc:off"
LIVE_FOR = timedelta(hours=24)
LIST_MAX = 8
# PLAN-107 B1 (chủ bot 2026-10-31, thay «không giới hạn» ngày 30/10): khách không nhận tin 22h–8h giờ VN, mã đến gần
# nhau gộp một tin, một mã không gửi lại trong 24 giờ, tối đa 2 tin mã mỗi ngày. Admin vẫn nhận ngay để kiểm tra.
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
QUIET_FROM, QUIET_TO = 22, 8
GROUP_WAIT = timedelta(minutes=2)  # chờ thêm mã đến sau; mã đầu đợi tối đa GROUP_MAX_WAIT
GROUP_MAX_WAIT = timedelta(minutes=10)
DAILY_MAX = 2
BATCH_MAX = 5
QUEUED = -1  # voucher_posts.sent: đang chờ lượt gửi khách (tick)
_SHOPEE_HOSTS = ("shp.ee", "shope.ee")

# Mẫu mặc định AddLiveTag: «{icon} {gio}: {ten} {ma} đã dùng {dadung}% - Giảm {giam}% - Tối đa {toida} - Đơn tối thiểu
# {toithieu}». Tin Telegram tới bot là chữ trơn (thẻ <b> thành entities).
_DASH = r"\s*[-–—]\s*"
_DEFAULT = re.compile(
    r"(?P<code>[A-Za-z0-9]{3,40})\s+đã dùng\s+(?P<used>\d{1,3})\s*%" + _DASH + r"Giảm\s+(?P<giam>.+?)" + _DASH
    + r"Tối đa\s+(?P<toida>.+?)" + _DASH + r"Đơn tối thiểu\s+(?P<toithieu>.+?)\s*$", re.I | re.M)
_OUT = re.compile(r"HẾT MÃ\s*[-–—:]\s*(?P<name>.*?)\s*\((?P<code>[A-Za-z0-9]{3,40})\)", re.I)
_LEAD = re.compile(r"^[^\w]*(?:\d{1,2}[:h]\d{2}(?::\d{2})?(?:\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?)?\s*:\s*)?", re.U)
# Mẫu có nhãn dòng (chủ bot tự soạn hoặc báo mã tay): «Mã: X», «Giảm: 20%», «Tối đa: 50K», «Đơn tối thiểu: 0».
_LABELS = {
    "ten": r"Tên", "code": r"Mã", "giam": r"Giảm", "toida": r"Tối đa", "toithieu": r"Đơn (?:tối thiểu|từ)",
    "used": r"Đã dùng",
}
_URL = re.compile(r"https?://[^\s<>\"']+")


@dataclass(frozen=True)
class Voucher:
    code: str
    name: str = ""
    discount: str = ""
    max_discount: str = ""
    min_spend: str = ""
    used: int | None = None
    out: bool = False


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value: str, limit: int = 60) -> str:
    return " ".join(value.split())[:limit]


def parse(text: str) -> Voucher | None:
    """Đọc một tin AddLiveTag. None: không phải tin báo mã."""
    text = text or ""
    found = _OUT.search(text)
    if found:
        return Voucher(code=found.group("code").upper(), name=_clean(_LEAD.sub("", found.group("name"))), out=True)
    found = _DEFAULT.search(text)
    if found:
        line = text[text.rfind("\n", 0, found.start()) + 1:found.start()]
        used = int(found.group("used"))
        return Voucher(code=found.group("code").upper(), name=_clean(_LEAD.sub("", line)),
                       discount=_clean(found.group("giam"), 20), max_discount=_clean(found.group("toida"), 20),
                       min_spend=_clean(found.group("toithieu"), 20), used=used, out=used >= 100)
    values = {}
    for key, label in _LABELS.items():
        hit = re.search(rf"^[^\w\n]*{label}\s*:\s*(.+?)\s*$", text, re.I | re.M)
        if hit:
            values[key] = hit.group(1)
    code = re.fullmatch(r"[A-Za-z0-9]{3,40}", (values.get("code") or "").strip())
    if not code:
        return None
    used_hit = re.search(r"\d{1,3}", values.get("used") or "")
    used = int(used_hit.group()) if used_hit else None
    return Voucher(code=code.group().upper(), name=_clean(values.get("ten", "")), discount=_clean(values.get("giam", ""), 20),
                   max_discount=_clean(values.get("toida", ""), 20), min_spend=_clean(values.get("toithieu", ""), 20),
                   used=used, out=used is not None and used >= 100)


def _shopee(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "shopee.vn" or host.endswith(".shopee.vn") or host in _SHOPEE_HOSTS


def find_url(post: dict) -> str | None:
    """Link Shopee trong tin: link gắn chữ, nút, link trần. Ưu tiên link có «voucher»."""
    found: list[str] = []
    for entity in (post.get("entities") or []) + (post.get("caption_entities") or []):
        if isinstance(entity, dict) and entity.get("type") == "text_link" and isinstance(entity.get("url"), str):
            found.append(entity["url"])
    for row in ((post.get("reply_markup") or {}).get("inline_keyboard") or []):
        found += [b["url"] for b in row if isinstance(b, dict) and isinstance(b.get("url"), str)]
    found += _URL.findall(post.get("text") or post.get("caption") or "")
    shopee = [url.rstrip(".,)") for url in found if url.startswith("https://") and _shopee(url)]
    return next((url for url in shopee if "voucher" in url), shopee[0] if shopee else None)


# --- Cài đặt ----------------------------------------------------------------------------------------------------


def enabled(repo: TrackingRepository) -> bool:
    return repo.get_state(ENABLED_KEY) != "0"


def channel(repo: TrackingRepository) -> int | None:
    raw = repo.get_state(CHANNEL_KEY) or ""
    return int(raw) if re.fullmatch(r"-?\d+", raw) else None


def ready(repo: TrackingRepository) -> bool:
    """Đã gắn kênh và đang bật: hiện 🎟 cho khách."""
    return enabled(repo) and channel(repo) is not None


def seen_channel(repo: TrackingRepository) -> dict:
    try:
        value = json.loads(repo.get_state(SEEN_KEY) or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) and isinstance(value.get("id"), int) else {}


def to_customers(repo: TrackingRepository) -> bool:
    return repo.get_state(AUDIENCE_KEY) == "all"


def is_on(repo: TrackingRepository, user: int) -> bool:
    """Mặc định nhận (chủ bot 2026-10-30: «cứ có mã là báo»); khách tắt thì `voucher_on:<id>` = "0"."""
    return repo.get_state(f"{ON_PREFIX}{user}") != "0"


def subscribers(conn: sqlite3.Connection, now: datetime) -> list[int]:
    """Khách đã tạo link hoặc tự bật, trừ khách tắt báo mã hay chặn bot."""
    users = {int(r[0]) for r in conn.execute(
        "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created'")}
    for key, value in conn.execute("SELECT key, value FROM bot_state WHERE key LIKE ?", (ON_PREFIX + "%",)):
        try:
            user = int(key.removeprefix(ON_PREFIX))
        except ValueError:
            continue
        if value == "1":
            users.add(user)
        elif value == "0":
            users.discard(user)
    cfg = NotifyConfig(True)
    return sorted(u for u in users if customer_block_reason(conn, {"category": CATEGORY, "chat_id": u}, cfg, now) is None)


# --- Tin trong kênh ---------------------------------------------------------------------------------------------


def _with_affiliate(url: str | None, affiliate_id: str | None) -> str | None:
    """Link lưu mã gắn affiliate (sub_id chung). Không bọc được (link rút gọn…) thì giữ link gốc."""
    if not url or not affiliate_id:
        return url
    try:
        return build_voucher_redir(url, affiliate_id)
    except ValueError:
        return url


def handle_post(repo: TrackingRepository, post: dict, edited: bool, now: datetime,
                affiliate_id: str | None = None, admins: frozenset[int] = frozenset()) -> int:
    """Một tin trong kênh. Trả số tin đã xếp hàng. Link lưu mã lưu sẵn dạng đã gắn affiliate.
    Chế độ thử (mặc định): chỉ gửi `admins`."""
    chat = post.get("chat") or {}
    chat_id, message_id = chat.get("id"), post.get("message_id")
    if chat.get("type") != "channel" or not isinstance(chat_id, int) or not isinstance(message_id, int):
        return 0
    if chat_id != channel(repo):
        repo.set_state(SEEN_KEY, json.dumps({"id": chat_id, "title": _clean(str(chat.get("title") or ""), 60),
                                             "at": _stamp(now)}, ensure_ascii=False))
        return 0
    voucher = parse(post.get("text") or post.get("caption") or "")
    if voucher is None:
        repo.set_state(SKIPPED_KEY, str(int(repo.get_state(SKIPPED_KEY) or 0) + 1))
        return 0
    stamp = _stamp(now)
    with repo.connect() as conn:
        if voucher.out and voucher.used is None:
            conn.execute("UPDATE voucher_posts SET status = 'out', updated_at = ? WHERE channel_id = ? AND code = ? "
                         "AND status = 'live'", (stamp, chat_id, voucher.code))
            return 0
        url = _with_affiliate(find_url(post), affiliate_id)
        status = "out" if voucher.out else "live"
        row = conn.execute("SELECT id FROM voucher_posts WHERE channel_id = ? AND message_id = ?",
                           (chat_id, message_id)).fetchone()
        if row is not None:
            # AddLiveTag sửa tin cũ: % đã dùng nhảy hoặc hết mã. Không gửi lại khách.
            conn.execute("UPDATE voucher_posts SET used_percent = COALESCE(?, used_percent), status = ?, "
                         "url = COALESCE(?, url), updated_at = ? WHERE id = ?", (voucher.used, status, url, stamp, row[0]))
            return 0
        cursor = conn.execute(
            "INSERT INTO voucher_posts (channel_id, message_id, code, name, discount, max_discount, min_spend, "
            "used_percent, url, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, voucher.code, voucher.name, voucher.discount, voucher.max_discount,
             voucher.min_spend, voucher.used, url, status, stamp, stamp))
        # Tin AddLiveTag sửa lại (% đã dùng) thì không gửi lại. Gửi khách: xếp hàng cho tick (giờ yên lặng, gộp, trần).
        if edited or voucher.out or not enabled(repo):
            return 0
        if not to_customers(repo):
            return _send(conn, cursor.lastrowid, voucher, url, now, sorted(admins), test=True)
        sent = _send(conn, cursor.lastrowid, voucher, url, now, sorted(admins))
        conn.execute("UPDATE voucher_posts SET sent = ? WHERE id = ?", (QUEUED, cursor.lastrowid))
        return sent


def _send(conn: sqlite3.Connection, post_id: int, voucher: Voucher, url: str | None, now: datetime,
          targets: list[int], test: bool = False) -> int:
    text, keyboard = alert(voucher, url)
    if test:
        text = f"{TEST_NOTE}\n\n{text}"
    stamp = _stamp(now)
    sent = 0
    for user in targets:
        if enqueue_event(conn, event_key=f"voucher:{post_id}:{user}", event_type=EVENT_TYPE, chat_id=user,
                         message_html=text, audience="customer", category=CATEGORY, source_ref=f"voucher:{post_id}",
                         reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False), now=stamp):
            sent += 1
    conn.execute("UPDATE voucher_posts SET sent = ? WHERE id = ?", (sent, post_id))
    return sent


def quiet(now: datetime) -> bool:
    hour = now.astimezone(ICT).hour
    return hour >= QUIET_FROM or hour < QUIET_TO


def _when(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _recent_codes(conn: sqlite3.Connection, user: int, now: datetime) -> set[str]:
    ids: set[int] = set()
    for (ref,) in conn.execute("SELECT source_ref FROM admin_notifications WHERE event_type = ? AND chat_id = ? "
                               "AND created_at >= ?", (EVENT_TYPE, user, _stamp(now - LIVE_FOR))):
        ids |= {int(part) for part in (ref or "").removeprefix("voucher:").split(",") if part.isdigit()}
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    return {r[0] for r in conn.execute(f"SELECT code FROM voucher_posts WHERE id IN ({marks})", tuple(ids))}


def tick(repo: TrackingRepository, now: datetime | None = None) -> int:
    """Gửi khách các mã đang chờ (vòng lặp poller). Trả số tin đã xếp hàng."""
    now = now or datetime.now(timezone.utc)
    if not ready(repo) or not to_customers(repo) or quiet(now):
        return 0
    with repo.connect() as conn:
        rows = conn.execute("SELECT * FROM voucher_posts WHERE sent = ? ORDER BY id", (QUEUED,)).fetchall()
        if not rows or (now - _when(rows[-1]["created_at"]) < GROUP_WAIT
                        and now - _when(rows[0]["created_at"]) < GROUP_MAX_WAIT):
            return 0
        latest: dict[str, sqlite3.Row] = {}
        for row in rows:
            if row["status"] == "live" and _when(row["created_at"]) >= now - LIVE_FOR:
                latest[row["code"]] = row
        batch = sorted(latest.values(), key=lambda r: r["id"], reverse=True)[:BATCH_MAX]
        counts = {row["id"]: 0 for row in rows}
        today = _stamp(now.astimezone(ICT).replace(hour=0, minute=0, second=0, microsecond=0))
        total = 0
        for user in subscribers(conn, now) if batch else []:
            seen = _recent_codes(conn, user, now)
            picks = [row for row in batch if row["code"] not in seen]
            if not picks or conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type = ? AND chat_id = ? "
                                         "AND created_at >= ?", (EVENT_TYPE, user, today)).fetchone()[0] >= DAILY_MAX:
                continue
            first = conn.execute("SELECT 1 FROM admin_notifications WHERE event_type = ? AND chat_id = ? LIMIT 1",
                                 (EVENT_TYPE, user)).fetchone() is None
            text, keyboard = alert_many(picks, first)
            ids = [str(row["id"]) for row in picks]
            if enqueue_event(conn, event_key=f"voucher:{'-'.join(ids)}:{user}", event_type=EVENT_TYPE, chat_id=user,
                             message_html=text, audience="customer", category=CATEGORY,
                             source_ref=f"voucher:{','.join(ids)}",
                             reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False),
                             now=_stamp(now)):
                total += 1
                for row in picks:
                    counts[row["id"]] += 1
        conn.executemany("UPDATE voucher_posts SET sent = ? WHERE id = ?", [(n, i) for i, n in counts.items()])
    return total


def queued(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM voucher_posts WHERE sent = ?", (QUEUED,)).fetchone()[0])


# --- Chữ cho khách ----------------------------------------------------------------------------------------------

BUY_HINT = "👉 Lưu mã xong, dán link món vào bot để mua có hoàn tiền nha."
DISCOUNT_NOTE = "ⓘ Dùng mã thì số hoàn tính trên giá sau giảm."
NO_LINK = "Nhập mã này ở mục Shopee Voucher lúc thanh toán."
OFF_TEXT = "Báo mã giảm giá đang tạm tắt."
FIRST_NOTE = "ⓘ Không muốn nhận? Bấm 🔕 Tắt báo mã bên dưới."
RULES_NOTE = "Bot nhắn tối đa 2 tin mã mỗi ngày và không nhắn từ 22h đến 8h."


def _terms(voucher) -> str:
    parts = [f"giảm {html.escape(voucher['discount'])}" if voucher["discount"] else "",
             f"tối đa {html.escape(voucher['max_discount'])}" if voucher["max_discount"] else "",
             f"đơn từ {html.escape(voucher['min_spend'])}" if voucher["min_spend"] else ""]
    return " · ".join(part for part in parts if part)


def _fields(voucher: Voucher) -> dict:
    return {"code": voucher.code, "name": voucher.name, "discount": voucher.discount,
            "max_discount": voucher.max_discount, "min_spend": voucher.min_spend, "used_percent": voucher.used}


def alert(voucher: Voucher, url: str | None) -> tuple[str, list]:
    """Tin báo mã cho khách và bàn phím (dạng Telegram)."""
    row = _fields(voucher)
    lines = ["🎟 <b>Có mã giảm giá Shopee nè!</b>"]
    if voucher.name:
        lines.append(f"<b>{html.escape(voucher.name)}</b>")
    terms = _terms(row)
    lines.append(f"Mã <code>{html.escape(voucher.code)}</code>" + (f": {terms}" if terms else ""))
    if voucher.used is not None:
        lines.append(f"Đã dùng {voucher.used}%, lưu nhanh kẻo hết nha!")
    if not url:
        lines.append(NO_LINK)
    lines += ["", BUY_HINT, DISCOUNT_NOTE]
    keyboard = [[{"text": "🎟 Lưu mã trên Shopee", "url": url}]] if url else []
    keyboard.append([{"text": "🔕 Tắt báo mã", "callback_data": OFF}, {"text": "📋 Mã đang còn", "callback_data": LIST}])
    return "\n".join(lines), keyboard


def alert_many(rows: list, first: bool = False) -> tuple[str, list]:
    """Tin gộp các mã chờ gửi (hàng voucher_posts). Nút lưu mã đầu; mã sau có link «Lưu mã» trong chữ (Zalo một nút)."""
    if len(rows) == 1:
        row = rows[0]
        text, keyboard = alert(Voucher(code=row["code"], name=row["name"] or "", discount=row["discount"] or "",
                                       max_discount=row["max_discount"] or "", min_spend=row["min_spend"] or "",
                                       used=row["used_percent"]), row["url"])
        return (f"{text}\n{FIRST_NOTE}" if first else text), keyboard
    lines = [f"🎟 <b>Có {len(rows)} mã giảm giá Shopee nè!</b>", ""]
    for number, row in enumerate(rows, 1):
        name = f"<b>{html.escape(row['name'])}</b>: " if row["name"] else ""
        terms = _terms(row)
        used = f" · đã dùng {row['used_percent']}%" if row["used_percent"] is not None else ""
        save = f' · <a href="{html.escape(row["url"])}">Lưu mã</a>' if row["url"] and number > 1 else ""
        lines.append(f"{number}. {name}<code>{html.escape(row['code'])}</code>"
                     + (f" ({terms})" if terms else "") + used + save)
    lines += ["", BUY_HINT, DISCOUNT_NOTE] + ([FIRST_NOTE] if first else [])
    keyboard = ([[{"text": f"🎟 Lưu mã {rows[0]['code']}", "url": rows[0]["url"]}]] if rows[0]["url"] else [])
    keyboard.append([{"text": "🔕 Tắt báo mã", "callback_data": OFF}, {"text": "📋 Mã đang còn", "callback_data": LIST}])
    return "\n".join(lines), keyboard


def live(conn: sqlite3.Connection, now: datetime) -> list[sqlite3.Row]:
    """Mã còn: tin mới nhất mỗi mã trong 24 giờ, chưa hết."""
    return conn.execute(
        "SELECT * FROM voucher_posts WHERE id IN (SELECT MAX(id) FROM voucher_posts WHERE created_at >= ? GROUP BY code) "
        "AND status = 'live' ORDER BY id DESC LIMIT ?", (_stamp(now - LIVE_FOR), LIST_MAX)).fetchall()


def list_reply(repo: TrackingRepository, user: int, now: datetime, notice: str = "") -> BotReply:
    with repo.connect() as conn:
        rows = live(conn, now)
    on = is_on(repo, user)
    lines = ["🎟 <b>Mã giảm giá Shopee</b>", ""]
    if notice:
        lines += [notice, ""]
    if rows:
        lines.append("Mã đang còn:")
        for number, row in enumerate(rows, 1):
            name = f"{html.escape(row['name'])}: " if row["name"] else ""
            terms = _terms(row)
            used = f" · đã dùng {row['used_percent']}%" if row["used_percent"] is not None else ""
            save = f' · <a href="{html.escape(row["url"])}">Lưu mã</a>' if row["url"] and number > 1 else ""
            lines.append(f"{number}. {name}<code>{html.escape(row['code'])}</code>"
                         + (f" ({terms})" if terms else "") + used + save)
        lines += ["", BUY_HINT, DISCOUNT_NOTE]
    else:
        lines.append("Chưa có mã nào đang còn. Bật báo mã để bot nhắn khi có mã mới nha.")
    lines += ["", f"Báo mã mới: {'🟢 Đang bật' if on else '⚪ Đang tắt'}", f"<i>{RULES_NOTE}</i>"]
    toggle = ("🔕 Tắt báo mã", OFF) if on else ("🔔 Bật báo mã mới", ON)
    first = rows[0] if rows and rows[0]["url"] else None
    return BotReply("\n".join(lines), button_url=first["url"] if first else None,
                    button_label=f"🎟 Lưu mã {first['code']}" if first else None,
                    inline_keyboard=((toggle,), (("◀️ Trang chủ", "u:p:home"),)))


def action(repo: TrackingRepository, user: int, data: str, now: datetime) -> BotReply:
    """Nút u:vc:* của khách."""
    if not enabled(repo):
        return BotReply("", toast=OFF_TEXT, show_alert=True)
    if data == ON:
        repo.set_state(f"{ON_PREFIX}{user}", "1")
        return list_reply(repo, user, now, "🔔 Đã bật. Có mã mới bot sẽ nhắn bạn nha!")
    if data == OFF:
        repo.set_state(f"{ON_PREFIX}{user}", "0")
        return list_reply(repo, user, now, "🔕 Đã tắt báo mã. Muốn bật lại thì gõ /magiam nha.")
    return list_reply(repo, user, now)


# --- Admin ------------------------------------------------------------------------------------------------------


def stats(conn: sqlite3.Connection, now: datetime) -> dict:
    week = _stamp(now - timedelta(days=7))
    on = len(subscribers(conn, now))
    posts = conn.execute("SELECT COUNT(*) FROM voucher_posts WHERE created_at >= ?", (week,)).fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type = ? AND created_at >= ?",
                        (EVENT_TYPE, week)).fetchone()[0]
    last = conn.execute("SELECT code, created_at FROM voucher_posts ORDER BY id DESC LIMIT 1").fetchone()
    return {"on": int(on), "posts": int(posts), "sent": int(sent), "last": tuple(last) if last else None}
