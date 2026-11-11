"""Tổng khách của mọi bot (PLAN-168): Cashbot Telegram, Cashbot Zalo, AI Pass Store.

CHỈ ĐỌC: mở SQLite ``mode=ro``, không ghi, không import store_bot (đọc thẳng bảng của bot bán hàng).
Web (/bot-users) và lệnh admin ``/users`` của Cashbot dùng chung hàm ``report()``.

- Cashbot: ``telegram_users`` (ID âm = khách Zalo, tên ở ``channel_identities``); đang dùng = có tạo link;
  có đơn = có đơn Shopee/TikTok ghi nhận không huỷ (``shopee_conversions``); nguồn = ``bot_state['src:<id>']``.
- AI Pass Store: ``users``; đang dùng = có đơn hoặc nạp xong; có đơn = đơn ``done``; nguồn = ``state['src:<id>']``.
Một người dùng cả 2 bot được đếm ở mỗi bot (không gộp).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICT = timezone(timedelta(hours=7))
BOTS = ("cashbot_tg", "cashbot_zalo", "ai_store")
BOT_LABEL = {"cashbot_tg": "Cashbot · Telegram", "cashbot_zalo": "Cashbot · Zalo", "ai_store": "AI Pass Store"}
NO_SOURCE = "tự vào"
DAYS = 14
ACTIVE_DAYS = 7
_CANCELLED = ("CANCELLED", "CANCELED", "INVALID", "REJECTED")


def _path(env_key: str, default: str) -> Path:
    raw = (os.getenv(env_key) or default).strip()
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def cashback_db() -> Path:
    return _path("CASHBACK_DB_PATH", "./data/cashback.sqlite")


def store_db() -> Path:
    return _path("STORE_DB_PATH", "./data/store.sqlite")


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Person:
    bot: str
    user_id: int
    name: str
    joined_at: datetime | None
    last_seen_at: datetime | None
    source: str
    uses: int  # Cashbot: số link; Store: số đơn done
    orders: int  # Cashbot: đơn sàn ghi nhận; Store: đơn done
    last_used_at: datetime | None
    balance: int | None = None  # Store: số dư ví bot
    spent: int | None = None  # Store: tổng tiền đơn done

    def active(self, now: datetime) -> bool:
        return self.last_used_at is not None and self.last_used_at >= now - timedelta(days=ACTIVE_DAYS)


@dataclass
class BotSummary:
    bot: str
    total: int = 0
    new_24h: int = 0
    new_7d: int = 0
    active_7d: int = 0
    buyers: int = 0

    @property
    def label(self) -> str:
        return BOT_LABEL.get(self.bot, self.bot)


@dataclass
class Report:
    now: datetime
    bots: list[BotSummary]
    total: BotSummary
    days: list[tuple[str, dict[str, int]]]  # (dd/mm, {bot: số khách mới}) — mới nhất trước
    sources: dict[str, list[tuple[str, int]]]  # bot → [(mã nguồn, số khách)], nhiều nhất trước
    people: list[Person]
    errors: list[str] = field(default_factory=list)


def _cashback_people(path: Path) -> list[Person]:
    with closing(_ro(path)) as c:
        rows = c.execute(
            f"""
            SELECT u.telegram_user_id AS uid, u.username, u.created_at, u.last_seen_at,
                   (SELECT display_name FROM channel_identities ci WHERE ci.internal_user_id = u.telegram_user_id
                    ORDER BY ci.created_at DESC LIMIT 1) AS zalo_name,
                   (SELECT value FROM bot_state s WHERE s.key = 'src:' || u.telegram_user_id) AS source,
                   (SELECT COUNT(*) FROM link_requests l
                    WHERE l.telegram_user_id = u.telegram_user_id AND l.link_status = 'created') AS links,
                   (SELECT MAX(created_at) FROM link_requests l
                    WHERE l.telegram_user_id = u.telegram_user_id AND l.link_status = 'created') AS last_link,
                   (SELECT COUNT(DISTINCT order_sn) FROM shopee_conversions sc
                    WHERE sc.telegram_user_id = u.telegram_user_id
                      AND UPPER(COALESCE(sc.order_status, '')) NOT IN ({",".join("?" * len(_CANCELLED))})) AS orders
            FROM telegram_users u
            """,
            _CANCELLED,
        ).fetchall()
    out = []
    for r in rows:
        uid = int(r["uid"])
        zalo = uid < 0
        name = (r["zalo_name"] if zalo else (f"@{r['username']}" if r["username"] else None)) or f"ID {uid}"
        out.append(Person(
            bot="cashbot_zalo" if zalo else "cashbot_tg", user_id=uid, name=name,
            joined_at=_parse(r["created_at"]), last_seen_at=_parse(r["last_seen_at"]),
            source=r["source"] or NO_SOURCE, uses=int(r["links"] or 0), orders=int(r["orders"] or 0),
            last_used_at=_parse(r["last_link"]),
        ))
    return out


def _store_people(path: Path) -> list[Person]:
    with closing(_ro(path)) as c:
        rows = c.execute(
            """
            SELECT u.user_id AS uid, u.username, u.first_name, u.balance, u.created_at, u.last_seen_at,
                   (SELECT value FROM state s WHERE s.key = 'src:' || u.user_id) AS source,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.user_id AND o.status = 'done') AS orders,
                   (SELECT COALESCE(SUM(total), 0) FROM orders o
                    WHERE o.user_id = u.user_id AND o.status = 'done' AND o.refunded = 0) AS spent,
                   (SELECT MAX(created_at) FROM orders o WHERE o.user_id = u.user_id AND o.status = 'done') AS last_order,
                   (SELECT MAX(resolved_at) FROM topups t WHERE t.user_id = u.user_id AND t.status = 'paid') AS last_topup
            FROM users u
            """
        ).fetchall()
    out = []
    for r in rows:
        name = f"@{r['username']}" if r["username"] else (r["first_name"] or f"ID {r['uid']}")
        used = [m for m in (_parse(r["last_order"]), _parse(r["last_topup"])) if m is not None]
        orders = int(r["orders"] or 0)
        out.append(Person(
            bot="ai_store", user_id=int(r["uid"]), name=name,
            joined_at=_parse(r["created_at"]), last_seen_at=_parse(r["last_seen_at"]),
            source=r["source"] or NO_SOURCE, uses=orders, orders=orders,
            last_used_at=max(used) if used else None, balance=int(r["balance"] or 0), spent=int(r["spent"] or 0),
        ))
    return out


def _summary(bot: str, people: list[Person], now: datetime) -> BotSummary:
    s = BotSummary(bot)
    for p in people:
        s.total += 1
        if p.joined_at and p.joined_at >= now - timedelta(hours=24):
            s.new_24h += 1
        if p.joined_at and p.joined_at >= now - timedelta(days=7):
            s.new_7d += 1
        s.active_7d += p.active(now)
        s.buyers += p.orders > 0
    return s


def report(now: datetime | None = None, cashback_path: Path | None = None, store_path: Path | None = None) -> Report:
    now = now or datetime.now(timezone.utc)
    people: list[Person] = []
    errors: list[str] = []
    for label, loader, path in (("Cashbot", _cashback_people, cashback_path or cashback_db()),
                                ("AI Pass Store", _store_people, store_path or store_db())):
        try:
            people += loader(path)
        except sqlite3.Error as exc:
            errors.append(f"{label}: không đọc được DB ({exc})")
    by_bot = {bot: [p for p in people if p.bot == bot] for bot in BOTS}
    bots = [_summary(bot, by_bot[bot], now) for bot in BOTS]
    total = _summary("all", people, now)

    today = now.astimezone(ICT).date()
    days = []
    for back in range(DAYS):
        day = today - timedelta(days=back)
        counts = {bot: sum(1 for p in by_bot[bot] if p.joined_at and p.joined_at.astimezone(ICT).date() == day)
                  for bot in BOTS}
        days.append((day.strftime("%d/%m"), counts))

    sources = {}
    for bot in BOTS:
        tally: dict[str, int] = {}
        for p in by_bot[bot]:
            tally[p.source] = tally.get(p.source, 0) + 1
        sources[bot] = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    people.sort(key=lambda p: p.joined_at or epoch, reverse=True)
    return Report(now, bots, total, days, sources, people, errors)


def search(people: list[Person], query: str = "", bot: str = "") -> list[Person]:
    needle = (query or "").strip().lower().lstrip("@")
    return [p for p in people
            if (not bot or p.bot == bot)
            and (not needle or needle in p.name.lower() or needle in str(p.user_id) or needle in p.source.lower())]
