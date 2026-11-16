"""PLAN-172 T4: sau đơn Store done → mời dùng Cashbot (một lần / khách).

    python -m store_bot.cashbot_invite            # chạy thử: in số khách + nội dung
    python -m store_bot.cashbot_invite --send     # gửi thật cho hàng đợi (đã mua, chưa mời)

Tin tự động cũng gửi trong ``StoreBot.after_sale`` khi đơn bot vừa giao hàng.
Mã nguồn Cashbot: ``store_xsell`` (đo khách từ Store). Tắt nhanh: state ``cashbot_invite:off``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone

from store_bot.config import default_dotenv, load_settings
from store_bot.db import StoreRepository
from store_bot.telegram_api import TelegramApi

logger = logging.getLogger("store_bot")

CODE = "v1"
START = "store_xsell"
OFF_KEY = "cashbot_invite:off"
DEFAULT_USERNAME = "zt_shopee_bot"
BROADCAST_DELAY_SEC = 0.05  # cùng nhịp store_bot.bot (dưới 30 tin/giây)


def state_key(user_id: int) -> str:
    return f"cashbot_invite:{CODE}:{user_id}"


def username_from_env(raw: str | None = None) -> str:
    value = (raw if raw is not None else os.environ.get("STORE_CASHBOT_USERNAME", "")).strip().lstrip("@")
    return value or DEFAULT_USERNAME


def cashbot_url(username: str | None = None) -> str:
    return f"https://t.me/{username_from_env(username)}?start={START}"


def text() -> str:
    return (
        "💰 <b>Mua xong rồi — thử hoàn tiền Shopee miễn phí?</b>\n\n"
        "Bot hoàn tiền đọc link Shopee rồi báo số hoàn trước khi bạn mua. Không thu phí, "
        "không cần nạp ví.\n\n"
        "Cách dùng 30 giây: mở món trên Shopee → <b>Chia sẻ</b> → <b>Sao chép liên kết</b> → "
        "dán vào bot hoàn tiền.\n\n"
        "Bấm nút dưới để mở bot (cùng tài khoản Telegram)."
    )


def markup(username: str | None = None) -> dict:
    return {"inline_keyboard": [[{"text": "💰 Mở bot hoàn Shopee", "url": cashbot_url(username)}]]}


def eligible(repo: StoreRepository, user_id: int) -> bool:
    """Còn được mời: chưa tắt tính năng, chưa nhận, chưa tắt tin, chưa chặn bot."""
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
    """Telegram id đã tạo link Cashbot — backfill bỏ qua (chỉ đọc DB, lỗi thì coi như chưa ai)."""
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


def targets(repo: StoreRepository) -> list[int]:
    """Khách đã có đơn done, còn đủ điều kiện nhận tin mời (hàng đợi backfill)."""
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


def send_one(repo: StoreRepository, tg: TelegramApi, user_id: int, username: str | None = None) -> str:
    """ok · skipped · blocked · failed. Đánh dấu đã gửi chỉ khi Telegram nhận."""
    if not eligible(repo, user_id):
        return "skipped"
    status, wait = "retry", 0
    for _ in range(3):
        status, wait = tg.send_broadcast(user_id, text(), markup(username))
        if status != "retry":
            break
        time.sleep(min(wait or 1, 60))
    if status == "ok":
        repo.set_state(state_key(user_id), datetime.now(timezone.utc).isoformat())
        return "ok"
    if status == "blocked":
        repo.mark_blocked(user_id)
        return "blocked"
    logger.warning("[Store] cashbot_invite gửi %s lỗi: %s", user_id, status)
    return "failed"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Mời khách Store đã mua sang Cashbot (PLAN-172 T4)")
    parser.add_argument("--send", action="store_true", help="gửi thật (mặc định chỉ chạy thử)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings(dotenv_path=default_dotenv())
    repo = StoreRepository(settings.db_path)
    repo.migrate()
    users = targets(repo)
    name = settings.cashbot_username
    print(f"Khách sẽ nhận: {len(users)}\nLink: {cashbot_url(name)}\n\n{text()}")
    if not args.send:
        print("\n(chạy thử — thêm --send để gửi thật)")
        return
    sent, blocked = send_backfill(repo, TelegramApi(settings.bot_token), users, name)
    print(f"\nĐã gửi {sent} khách, {blocked} đã chặn bot.")


if __name__ == "__main__":
    main()
