"""PLAN-173: cohort khách mới theo nguồn, chỉ đọc SQLite; CLI: python -m cashback_bot.growth_funnel --json.

Nguồn là first-touch của bot, không phải từng bài Threads. Bước sử dụng đếm độc lập;
QR không bắt buộc trước mua. Không xuất tên/ID khách và không import luồng vận hành bot.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from cashback_bot import all_users

NO_SOURCE = "không ghi nhận nguồn"
STAGES = {
    "ai_store": {"product": "xem món", "confirm": "chọn số lượng", "qr": "tạo QR mua",
                 "paid": "nạp thành công", "order": "có đơn đã giao"},
    "cashbot_tg": {"link": "tạo link", "click": "có click ghi nhận", "order": "có đơn ghi nhận"},
    "cashbot_zalo": {"link": "tạo link", "click": "có click ghi nhận", "order": "có đơn ghi nhận"},
}
NOTES = [
    "Cohort [từ, đến); mỗi khách đếm một lần trong từng bot và từng bước, các bước độc lập; QR là nhánh tùy chọn.",
    "24h: chỉ khách đã đủ 24 giờ; Store tính thời điểm đặt đơn hiện đã giao (done/partial, chưa hoàn hết), "
    "Cashbot tính link created. Chưa đo chính xác thời gian giao hàng.",
    "Quay lại: Store có >=2 đơn đã giao; Cashbot tạo link >=2 ngày VN. Chỉ xét khách mới trong cohort.",
    "Nguồn first-touch: mã dùng chung không truy về từng bài; thiếu mã không đồng nghĩa tự vào. Zalo có thể thiếu mã.",
    "Step Store chỉ bắt đầu ghi từ 16/11; thiếu step/click không chứng minh khách chưa đi qua bước đó. "
    "Timestamp thiếu/sai bị bỏ; trạng thái là hiện tại, chưa hỗ trợ tái dựng lịch sử.",
]


@dataclass
class _Customer:
    bot: str
    source: str
    joined: datetime
    events: dict[str, dict[str, datetime]] = field(default_factory=dict)


def _moment(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return all_users._parse(value)


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _customers(conn, bot: str, since: datetime, until: datetime) -> dict[int, _Customer]:
    store = bot == "ai_store"
    table, uid, state = ("users", "user_id", "state") if store else ("telegram_users", "telegram_user_id", "bot_state")
    rows = conn.execute(
        f"SELECT u.{uid} AS uid, u.created_at, s.value AS source FROM {table} u "
        f"LEFT JOIN {state} s ON s.key = 'src:' || u.{uid} "
        "WHERE julianday(u.created_at) >= julianday(?) AND julianday(u.created_at) < julianday(?)",
        (since.isoformat(), until.isoformat()),
    )
    return {int(r["uid"]): _Customer("ai_store" if store else "cashbot_zalo" if r["uid"] < 0 else "cashbot_tg",
                                     r["source"] or NO_SOURCE, _moment(r["created_at"])) for r in rows}


def _add(people, uid, stage: str, key, stamp, until: datetime) -> None:
    person, time = people.get(int(uid)), _moment(stamp)
    if person is not None and time is not None and person.joined <= time < until:
        person.events.setdefault(stage, {})[str(key)] = time


def _store(conn, people, since: datetime, until: datetime) -> None:
    for r in conn.execute("SELECT key, value FROM state WHERE key LIKE 'step:product:%' OR key LIKE 'step:confirm:%'"):
        _, stage, uid = r["key"].split(":", 2)
        if uid.isdigit():
            _add(people, uid, stage, r["key"], r["value"].partition("@")[2], until)
    bounds = (since.isoformat(), until.isoformat())
    for r in conn.execute("SELECT id, user_id, created_at, resolved_at, intent_product_id, status FROM topups "
                          "WHERE julianday(created_at) >= julianday(?) AND julianday(created_at) < julianday(?)", bounds):
        if r["intent_product_id"] is not None:
            _add(people, r["user_id"], "qr", r["id"], r["created_at"], until)
        if r["status"] == "paid":
            _add(people, r["user_id"], "paid", r["id"], r["resolved_at"], until)
    for r in conn.execute("SELECT id, user_id, created_at FROM orders WHERE status IN ('done','partial') "
                          "AND total > COALESCE(refunded,0) AND julianday(created_at) >= julianday(?) "
                          "AND julianday(created_at) < julianday(?)", bounds):
        _add(people, r["user_id"], "order", r["id"], r["created_at"], until)


def _cashbot(conn, people, since: datetime, until: datetime) -> None:
    bounds = (since.isoformat(), until.isoformat())
    for r in conn.execute("SELECT id, telegram_user_id, created_at FROM link_requests WHERE link_status='created' "
                          "AND julianday(created_at) >= julianday(?) AND julianday(created_at) < julianday(?)", bounds):
        _add(people, r["telegram_user_id"], "link", r["id"], r["created_at"], until)
    for r in conn.execute("SELECT c.click_id, c.click_time, l.telegram_user_id, l.created_at AS link_at "
                          "FROM shopee_clicks c JOIN link_requests l ON l.sub_id=c.sub_id "
                          "WHERE l.link_status='created' AND julianday(c.click_time) >= julianday(?) "
                          "AND julianday(c.click_time) < julianday(?)", bounds):
        if (_moment(r["click_time"]) or until) >= (_moment(r["link_at"]) or until):
            _add(people, r["telegram_user_id"], "click", r["click_id"], r["click_time"], until)
    for r in conn.execute("SELECT conversion_id, order_sn, telegram_user_id, purchase_time FROM shopee_conversions "
                          "WHERE telegram_user_id IS NOT NULL AND UPPER(COALESCE(order_status,'')) "
                          "NOT IN ('CANCELLED','CANCELED','INVALID','REJECTED') "
                          "AND UPPER(COALESCE(validation_status,'')) NOT IN ('FRAUD','REJECTED') "
                          "AND COALESCE(fraud_flag,0)=0 AND julianday(purchase_time) >= julianday(?) "
                          "AND julianday(purchase_time) < julianday(?)", bounds):
        _add(people, r["telegram_user_id"], "order", r["order_sn"] or r["conversion_id"], r["purchase_time"], until)


def _stats(bot: str, people: list[_Customer], until: datetime, source: str | None = None) -> dict:
    primary = "order" if bot == "ai_store" else "link"
    mature = [p for p in people if p.joined + timedelta(hours=24) <= until]
    converted = sum(any(t < p.joined + timedelta(hours=24) for t in p.events.get(primary, {}).values()) for p in mature)
    repeat = sum(len(p.events.get("order", {})) >= 2 if bot == "ai_store" else
                 len({t.astimezone(all_users.ICT).date() for t in p.events.get("link", {}).values()}) >= 2 for p in people)
    return {
        "bot": bot, "source": source, "customers": len(people),
        "stages": {stage: sum(bool(p.events.get(stage)) for p in people) for stage in STAGES[bot]},
        "mature_24h": len(mature), "converted_24h": converted, "not_converted_24h": len(mature) - converted,
        "conversion_24h_pct": round(100 * converted / len(mature), 1) if mature else None,
        "repeat_customers": repeat,
    }


def report(now: datetime | None = None, days: int = 7, cashback_path: Path | None = None,
           store_path: Path | None = None) -> dict:
    """Snapshot cohort hiện tại; DB một bot lỗi không làm mất dữ liệu bot kia."""
    if not 1 <= days <= 90:
        raise ValueError("days phải từ 1 đến 90")
    until = _moment(now or datetime.now(timezone.utc))
    since = until - timedelta(days=days)
    people, available, errors = [], [], []
    for bot, path, loader, bots in (
        ("cashbot", cashback_path or all_users.cashback_db(), _cashbot, ("cashbot_tg", "cashbot_zalo")),
        ("ai_store", store_path or all_users.store_db(), _store, ("ai_store",)),
    ):
        try:
            with closing(_open(path)) as conn:
                conn.execute("BEGIN")  # một snapshot nhất quán trong mỗi DB; không ghi
                cohort = _customers(conn, bot, since, until)
                loader(conn, cohort, since, until)
            people.extend(cohort.values())
            available.extend(bots)
        except (sqlite3.Error, OSError) as exc:
            errors.append(f"{bot}: không đọc được dữ liệu ({exc})")
    rows, totals = [], []
    for bot in available:
        members = [p for p in people if p.bot == bot]
        totals.append(_stats(bot, members, until))
        rows.extend(_stats(bot, [p for p in members if p.source == source], until, source)
                    for source in sorted({p.source for p in members}))
    rows.sort(key=lambda r: (-r["customers"], r["bot"], r["source"]))
    return {"generated_at": until.isoformat(), "since": since.isoformat(), "days": days,
            "bots": totals, "sources": rows, "notes": NOTES, "errors": errors}


def summary(rep: dict, limit: int = 3) -> str:
    """Tóm tắt giới hạn độ dài cho báo cáo sáng hiện có. HTML escape mã nguồn."""
    start = _moment(rep["since"]).astimezone(all_users.ICT).strftime("%d/%m %H:%M")
    end = _moment(rep["generated_at"]).astimezone(all_users.ICT).strftime("%d/%m %H:%M")
    lines = [f"<b>Phễu theo nguồn · {rep['days']} ngày gần nhất</b>", f"Khách vào từ {start} đến {end} (VN)"]
    for row in rep["bots"]:
        action = "đặt đơn đã giao" if row["bot"] == "ai_store" else "tạo link"
        rate = "chưa đủ 24h" if row["conversion_24h_pct"] is None else f"{row['conversion_24h_pct']:g}%"
        lines.append(f"• {all_users.BOT_LABEL[row['bot']]}: {action} trong 24h "
                     f"{row['converted_24h']}/{row['mature_24h']} ({rate}); quay lại {row['repeat_customers']}")
    for row in rep["sources"][:limit]:
        first = row["stages"].get("link", row["stages"].get("product", 0))
        lines.append(f"• {all_users.BOT_LABEL[row['bot']]} / {escape(row['source'][:32])}: {row['customers']} vào · "
                     f"{first} {'tạo link' if row['bot'] != 'ai_store' else 'xem món'} · {row['stages']['order']} có đơn")
    lines.append("24h chỉ xét khách đủ thời gian; bước độc lập, lượt xem món Store mới ghi từ 16/11.")
    lines.extend(f"⚠️ {escape(error[:140])}" for error in rep["errors"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--cashback-db", type=Path)
    parser.add_argument("--store-db", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 90:
        parser.error("--days phải từ 1 đến 90")
    rep = report(days=args.days, cashback_path=args.cashback_db, store_path=args.store_db)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else summary(rep, limit=len(rep["sources"])))
    return int(bool(rep["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
