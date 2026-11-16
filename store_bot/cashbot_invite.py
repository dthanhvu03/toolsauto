"""PLAN-172 T4: sau đơn Store done → mời dùng Cashbot (một lần / khách) + nhắc lại nếu chưa vào.

    python -m store_bot.cashbot_invite              # chạy thử hàng đợi lần đầu
    python -m store_bot.cashbot_invite --send
    python -m store_bot.cashbot_invite --nudge      # chạy thử nhắc lại
    python -m store_bot.cashbot_invite --nudge --send
    python -m store_bot.cashbot_invite --nudge --send --now   # bỏ qua chờ 48h

Tin tự động cũng gửi trong ``StoreBot.after_sale`` khi đơn bot vừa giao hàng.
Mã nguồn Cashbot: ``store_xsell``. Tắt nhanh: state ``cashbot_invite:off``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from store_bot.config import default_dotenv, load_settings
from store_bot.db import StoreRepository
from store_bot.telegram_api import TelegramApi

logger = logging.getLogger("store_bot")

CODE = "v1"
NUDGE_CODE = "nudge1"
START = "store_xsell"
OFF_KEY = "cashbot_invite:off"
DEFAULT_USERNAME = "zt_shopee_bot"
BROADCAST_DELAY_SEC = 0.05  # cùng nhịp store_bot.bot (dưới 30 tin/giây)
NUDGE_AFTER = timedelta(hours=48)  # mặc định; --now bỏ qua


def state_key(user_id: int) -> str:
    return f"cashbot_invite:{CODE}:{user_id}"


def nudge_key(user_id: int) -> str:
    return f"cashbot_invite:{NUDGE_CODE}:{user_id}"


def username_from_env(raw: str | None = None) -> str:
    value = (raw if raw is not None else os.environ.get("STORE_CASHBOT_USERNAME", "")).strip().lstrip("@")
    return value or DEFAULT_USERNAME


def cashbot_url(username: str | None = None) -> str:
    return f"https://t.me/{username_from_env(username)}?start={START}"


def text() -> str:
    """Bản ngắn: lợi ích 1 câu + 1 nút (bản dài sáng 16/11: 0/11 bấm)."""
    return (
        "💰 <b>Mua Shopee hôm nay — xem hoàn bao nhiêu trong 30 giây</b>\n\n"
        "Không cần nạp ví, không thu phí. Bấm nút → dán link món Shopee → bot báo số hoàn trước khi mua."
    )


def nudge_text() -> str:
    return (
        "👋 <b>Nhắc nhẹ: bot hoàn Shopee vẫn mở</b>\n\n"
        "Bạn đã mua ở AI Pass Store. Muốn thử hoàn tiền khi mua Shopee thì bấm nút dưới — "
        "chỉ dán link món, xem số hoàn, không bắt buộc mua."
    )


def markup(username: str | None = None) -> dict:
    return {"inline_keyboard": [[{"text": "👉 Xem hoàn Shopee (miễn phí)", "url": cashbot_url(username)}]]}


def eligible(repo: StoreRepository, user_id: int) -> bool:
    """Còn được mời lần đầu: chưa tắt tính năng, chưa nhận, chưa tắt tin, chưa chặn bot."""
    if repo.get_state(OFF_KEY):
        return False
    if repo.get_state(state_key(user_id)):
        return False
    with repo._read() as conn:
        row = conn.execute(
            "SELECT notify_off, blocked_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return bool(row and not row["notify_off"] and row["blocked_at"] is None)


def _already_on_cashbot() -> set[int]:
    """Telegram id đã tạo link Cashbot — backfill/nudge bỏ qua (chỉ đọc DB)."""
    path = (os.environ.get("CASHBACK_DB_PATH") or "./data/cashback.sqlite").strip()
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            rows = conn.execute(
                "SELECT DISTINCT telegram_user_id FROM link_requests WHERE link_status = 'created'"
            ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("[Store] cashbot_invite: đọc Cashbot DB lỗi (%s) — không lọc trùng", exc)
        return set()
    return {int(r[0]) for r in rows}


def _used_store_xsell() -> set[int]:
    """Đã bấm link store_xsell (có src) — không nhắc lại."""
    path = (os.environ.get("CASHBACK_DB_PATH") or "./data/cashback.sqlite").strip()
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            rows = conn.execute(
                "SELECT key FROM bot_state WHERE value = ?", (START,)
            ).fetchall()
    except sqlite3.Error:
        return set()
    out: set[int] = set()
    for (key,) in rows:
        if isinstance(key, str) and key.startswith("src:"):
            try:
                out.add(int(key.split(":", 1)[1]))
            except ValueError:
                pass
    return out


def targets(repo: StoreRepository) -> list[int]:
    """Khách đã có đơn done, còn đủ điều kiện nhận tin mời lần đầu."""
    if repo.get_state(OFF_KEY):
        return []
    skip = _already_on_cashbot()
    with repo._read() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT o.user_id FROM orders o
            JOIN users u ON u.user_id = o.user_id
            WHERE o.status = 'done' AND u.notify_off = 0 AND u.blocked_at IS NULL
            ORDER BY o.user_id
            """
        ).fetchall()
    out = []
    for row in rows:
        uid = int(row["user_id"])
        if uid in skip or repo.get_state(state_key(uid)):
            continue
        out.append(uid)
    return out


def nudge_targets(repo: StoreRepository, now: datetime | None = None, *, ignore_age: bool = False) -> list[int]:
    """Đã nhận tin lần 1, chưa tạo link Cashbot, chưa bấm store_xsell, chưa nhận nudge."""
    if repo.get_state(OFF_KEY):
        return []
    moment = now or datetime.now(timezone.utc)
    skip = _already_on_cashbot() | _used_store_xsell()
    prefix = f"cashbot_invite:{CODE}:"
    with repo._read() as conn:
        rows = conn.execute(
            "SELECT key, value FROM state WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
    out = []
    for row in rows:
        try:
            uid = int(str(row["key"])[len(prefix):])
        except ValueError:
            continue
        if uid in skip or repo.get_state(nudge_key(uid)):
            continue
        with repo._read() as conn:
            user = conn.execute(
                "SELECT notify_off, blocked_at FROM users WHERE user_id = ?", (uid,)
            ).fetchone()
        if not user or user["notify_off"] or user["blocked_at"] is not None:
            continue
        if not ignore_age:
            try:
                sent = datetime.fromisoformat(str(row["value"]))
            except ValueError:
                continue
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            if moment - sent < NUDGE_AFTER:
                continue
        out.append(uid)
    return sorted(out)


def _deliver(repo: StoreRepository, tg: TelegramApi, user_id: int, html: str, mark_key: str,
             username: str | None = None) -> str:
    status, wait = "retry", 0
    for _ in range(3):
        status, wait = tg.send_broadcast(user_id, html, markup(username))
        if status != "retry":
            break
        time.sleep(min(wait or 1, 60))
    if status == "ok":
        repo.set_state(mark_key, datetime.now(timezone.utc).isoformat())
        return "ok"
    if status == "blocked":
        repo.mark_blocked(user_id)
        return "blocked"
    logger.warning("[Store] cashbot_invite gửi %s lỗi: %s", user_id, status)
    return "failed"


def send_one(repo: StoreRepository, tg: TelegramApi, user_id: int, username: str | None = None) -> str:
    """ok · skipped · blocked · failed. Đánh dấu đã gửi chỉ khi Telegram nhận."""
    if not eligible(repo, user_id):
        return "skipped"
    return _deliver(repo, tg, user_id, text(), state_key(user_id), username)


def send_nudge_one(repo: StoreRepository, tg: TelegramApi, user_id: int, username: str | None = None) -> str:
    if repo.get_state(OFF_KEY) or repo.get_state(nudge_key(user_id)):
        return "skipped"
    if user_id in _already_on_cashbot() or user_id in _used_store_xsell():
        return "skipped"
    with repo._read() as conn:
        row = conn.execute(
            "SELECT notify_off, blocked_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row or row["notify_off"] or row["blocked_at"] is not None:
        return "skipped"
    if not repo.get_state(state_key(user_id)):
        return "skipped"
    return _deliver(repo, tg, user_id, nudge_text(), nudge_key(user_id), username)


def send_after_sale(repo: StoreRepository, tg: TelegramApi, user_id: int, *, source: str,
                    username: str | None = None) -> str:
    """Gọi sau đơn done (chỉ đơn mua qua bot Telegram)."""
    if source != "bot":
        return "skipped"
    return send_one(repo, tg, user_id, username)


def send_backfill(repo: StoreRepository, tg: TelegramApi, users: list[int], username: str | None = None,
                  pause=time.sleep) -> tuple[int, int]:
    sent = blocked = 0
    for user_id in users:
        result = send_one(repo, tg, user_id, username)
        if result == "ok":
            sent += 1
        elif result == "blocked":
            blocked += 1
        pause(BROADCAST_DELAY_SEC)
    return sent, blocked


def send_nudges(repo: StoreRepository, tg: TelegramApi, users: list[int], username: str | None = None,
                pause=time.sleep) -> tuple[int, int]:
    sent = blocked = 0
    for user_id in users:
        result = send_nudge_one(repo, tg, user_id, username)
        if result == "ok":
            sent += 1
        elif result == "blocked":
            blocked += 1
        pause(BROADCAST_DELAY_SEC)
    return sent, blocked


def main() -> None:
    parser = argparse.ArgumentParser(description="Mời khách Store đã mua sang Cashbot (PLAN-172 T4)")
    parser.add_argument("--send", action="store_true", help="gửi thật (mặc định chỉ chạy thử)")
    parser.add_argument("--nudge", action="store_true", help="nhắc lại khách đã mời mà chưa vào Cashbot")
    parser.add_argument("--now", action="store_true", help="với --nudge: không chờ đủ 48 giờ")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings(dotenv_path=default_dotenv())
    repo = StoreRepository(settings.db_path)
    repo.migrate()
    name = settings.cashbot_username
    if args.nudge:
        users = nudge_targets(repo, ignore_age=args.now)
        body = nudge_text()
        label = "nhắc lại"
    else:
        users = targets(repo)
        body = text()
        label = "lần đầu"
    print(f"Khách sẽ nhận ({label}): {len(users)}\nLink: {cashbot_url(name)}\n\n{body}")
    if not args.send:
        print("\n(chạy thử — thêm --send để gửi thật)")
        return
    tg = TelegramApi(settings.bot_token)
    if args.nudge:
        sent, blocked = send_nudges(repo, tg, users, name)
    else:
        sent, blocked = send_backfill(repo, tg, users, name)
    print(f"\nĐã gửi {sent} khách, {blocked} đã chặn bot.")


if __name__ == "__main__":
    main()
