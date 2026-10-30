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

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.messages import BotReply
from cashback_bot.notify_dispatch import NotifyConfig, customer_block_reason

ENABLED_KEY = "voucher_enabled"  # vắng = bật; chỉ chạy khi đã gắn kênh
CHANNEL_KEY = "voucher_channel"
SEEN_KEY = "voucher_seen_channel"
SKIPPED_KEY = "voucher_skipped"
ON_PREFIX = "voucher_on:"
CATEGORY = "voucher"
EVENT_TYPE = "VOUCHER"
LIST = "u:vc:l"
ON = "u:vc:on"
OFF = "u:vc:off"
LIVE_FOR = timedelta(hours=24)
LIST_MAX = 8
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


def handle_post(repo: TrackingRepository, post: dict, edited: bool, now: datetime) -> int:
    """Một tin trong kênh. Trả số tin khách đã xếp hàng."""
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
        url = find_url(post)
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
        # Có mã là gửi ngay, mọi giờ (chủ bot 2026-10-30). Tin AddLiveTag sửa lại (% đã dùng) thì không gửi lại.
        if edited or voucher.out or not enabled(repo):
            return 0
        return _send(conn, cursor.lastrowid, voucher, url, now)


def _send(conn: sqlite3.Connection, post_id: int, voucher: Voucher, url: str | None, now: datetime) -> int:
    text, keyboard = alert(voucher, url)
    stamp = _stamp(now)
    sent = 0
    for user in subscribers(conn, now):
        if enqueue_event(conn, event_key=f"voucher:{post_id}:{user}", event_type=EVENT_TYPE, chat_id=user,
                         message_html=text, audience="customer", category=CATEGORY, source_ref=f"voucher:{post_id}",
                         reply_markup_json=json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False), now=stamp):
            sent += 1
    conn.execute("UPDATE voucher_posts SET sent = ? WHERE id = ?", (sent, post_id))
    return sent


# --- Chữ cho khách ----------------------------------------------------------------------------------------------

BUY_HINT = "👉 Lưu mã xong, dán link món vào bot để mua có hoàn tiền nha."
DISCOUNT_NOTE = "ⓘ Dùng mã thì số hoàn tính trên giá sau giảm."
NO_LINK = "Nhập mã này ở mục Shopee Voucher lúc thanh toán."
OFF_TEXT = "Báo mã giảm giá đang tạm tắt."


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
        lines.append("Chưa có mã nào đang còn. Bật báo mã để bot nhắn liền khi có mã mới nha.")
    lines += ["", f"Báo mã mới: {'🟢 Đang bật' if on else '⚪ Đang tắt'}"]
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
        return list_reply(repo, user, now, "🔔 Đã bật. Có mã mới là bot nhắn bạn liền nha!")
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
