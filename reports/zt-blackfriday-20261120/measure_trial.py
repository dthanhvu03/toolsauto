"""Read-only channel totals and Cashbot first-touch cohorts; no invite or sending methods."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.features.threads.growth.conversions import cashback_db
from app.features.threads.growth.strategy_review import get_exclusions
from cashback_bot.config import load_settings

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]


def business(path, source, since, until, excluded=()):
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            omit = " AND u.telegram_user_id NOT IN (" + ",".join("?" for _ in excluded) + ")" if excluded else ""
            row = db.execute(
                "SELECT COUNT(DISTINCT u.telegram_user_id),"
                "COUNT(DISTINCT CASE WHEN l.link_status='created' THEN u.telegram_user_id END),"
                "COUNT(DISTINCT CASE WHEN l.link_status='created' THEN l.id END) "
                "FROM telegram_users u JOIN bot_state s ON s.key='src:' || u.telegram_user_id "
                "LEFT JOIN link_requests l ON l.telegram_user_id=u.telegram_user_id "
                "AND julianday(l.created_at)>=julianday(u.created_at) AND julianday(l.created_at)<julianday(?) "
                "WHERE s.value=? AND julianday(u.created_at)>=julianday(?) "
                "AND julianday(u.created_at)<julianday(?)" + omit,
                (until, source, since, until, *excluded)).fetchone()
            return {"status": "available", "new_customers": row[0], "new_customers_created_link": row[1],
                    "created_links": row[2], "configured_exclusions": len(excluded)}
    except (OSError, sqlite3.Error) as exc:
        return {"status": "unavailable", "error_type": type(exc).__name__, "new_customers": None,
                "new_customers_created_link": None, "created_links": None}


def read_api(token, method, target):
    if method not in {"getChat", "getChatMemberCount"}:
        raise ValueError("Read methods only")
    response = requests.post("https://api.telegram.org/bot" + token + "/" + method,
                             json={"chat_id": target}, timeout=(5, 10))
    data = response.json()
    if response.status_code != 200 or data.get("ok") is not True:
        raise ValueError("Telegram read unavailable")
    return data["result"]


def measure():
    content = json.loads((FOLDER / "content.json").read_text())
    state_file = FOLDER / "channel-state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    now = datetime.now(timezone.utc)
    since = state.get("started_at", content["prepared_at"])
    settings = load_settings(dotenv_path=ROOT / ".env")
    db_path = cashback_db()
    result = {
        "plan": "PLAN-181", "observed_at": now.isoformat(), "since": since,
        "source": content["source"], "baseline_member_count": state.get("baseline_member_count"),
        "channel": {"status": "unavailable", "member_count": None, "guide_still_pinned": None},
        "business": business(db_path, content["source"], since, now.isoformat(), get_exclusions()["cashbot"]),
        "joins_attributed_to_invite": None, "impressions": None, "cash_received_vnd": None,
        "customer_or_public_actions": 0,
        "limitations": ["Member totals include administrators/bots and do not prove acquisition source.",
                        "No chat_member/join-per-invite handler is deployed; invite attribution is unavailable.",
                        "Cashbot source is first-touch for new users, not returning users or causal proof.",
                        "A created product link is use, not a purchase or received commission."],
    }
    try:
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            target = int(db.execute("SELECT value FROM bot_state WHERE key='voucher_channel'").fetchone()[0])
        chat = read_api(settings.bot_token, "getChat", target)
        count = read_api(settings.bot_token, "getChatMemberCount", target)
        if chat.get("id") != target or chat.get("title") != content["channel_title"] or chat.get("type") != "channel":
            raise ValueError("Channel changed")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError("Invalid count")
        pin = chat.get("pinned_message") or {}
        result["channel"] = {"status": "available", "member_count": count,
                             "still_private": not bool(chat.get("username")),
                             "guide_still_pinned": (pin.get("message_id") == state.get("guide", {}).get("message_id")
                                                     and pin.get("text") == content["guide_text"])
                             if state.get("guide", {}).get("message_id") else None}
    except (requests.RequestException, OSError, sqlite3.Error, ValueError, TypeError) as exc:
        result["channel"]["error_type"] = type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    path = FOLDER / ("measurement-baseline.json" if args.baseline else "measurement.json")
    if args.baseline and path.exists():
        raise SystemExit("Baseline already exists")
    result = measure()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
