"""Nhắn một lần cho khách AI Pass Store đã vào bot mà chưa nạp, chưa mua (chủ bot 12/11: mục tiêu 20 khách / bot tuần này,
không có ưu đãi). Chủ bot duyệt câu chữ rồi mới chạy ``--send``.

    python -m store_bot.nudge            # chạy thử: in số khách + nội dung, không gửi
    python -m store_bot.nudge --send     # gửi thật

Người nhận: vào bot quá 1 giờ, chưa có lần nạp ``paid`` nào, chưa có đơn ``done``, chưa tắt tin, chưa chặn bot.
Mỗi khách một lần (khoá state ``nudge:<mã>:<id>``); chạy lại chỉ gửi khách chưa nhận. Cách nhau như tin báo hàng mới.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from store_bot.bot import BROADCAST_DELAY_SEC, button, keyboard
from store_bot.config import default_dotenv, load_settings
from store_bot.db import StoreRepository
from store_bot.telegram_api import TelegramApi

logger = logging.getLogger("store_bot")

CODE = "start-v1"
CANVA_ID = 9  # Slot Canva Pro 1 Tháng BHF: món rẻ nhất, bán chạy nhất
TEXT = (
    "👋 <b>Bạn vào AI Pass Store rồi mà chưa thử món nào nè!</b>\n\n"
    "Rẻ nhất đang có: <b>Canva Pro 1 tháng chỉ 1.100đ</b>, dùng thử xem có hợp không.\n\n"
    "Cách mua 1 phút: bấm <b>💰 Nạp tiền</b> → quét mã chuyển khoản (từ 10.000đ, tiền dư nằm trong ví, mua món khác lúc nào "
    "cũng được) → bot cộng ví tự động → chọn món là nhận ngay.\n\n"
    "Phiền thì bấm 🔕 bên dưới nha 🫶"
)
MARKUP = keyboard([button("🛒 Xem Canva Pro 1.100đ", f"p:{CANVA_ID}")], [button("💰 Nạp tiền", "top")],
                  [button("🔕 Tắt tin nhắn", "noff")])


def targets(repo: StoreRepository, now: datetime) -> list[int]:
    cutoff = (now - timedelta(hours=1)).isoformat()
    with repo._read() as conn:
        rows = conn.execute(
            """
            SELECT u.user_id FROM users u
            WHERE u.notify_off = 0 AND u.blocked_at IS NULL AND u.created_at <= ?
              AND NOT EXISTS (SELECT 1 FROM topups t WHERE t.user_id = u.user_id AND t.status = 'paid')
              AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.user_id AND o.status = 'done')
            ORDER BY u.user_id
            """,
            (cutoff,),
        ).fetchall()
    return [int(r["user_id"]) for r in rows if repo.get_state(f"nudge:{CODE}:{r['user_id']}") is None]


def send(repo: StoreRepository, tg: TelegramApi, users: list[int], pause=time.sleep) -> tuple[int, int]:
    sent = blocked = 0
    for user_id in users:
        status, wait = "retry", 0
        for _ in range(3):
            status, wait = tg.send_broadcast(user_id, TEXT, MARKUP)
            if status != "retry":
                break
            pause(min(wait, 60))
        if status == "ok":
            sent += 1
            repo.set_state(f"nudge:{CODE}:{user_id}", datetime.now(timezone.utc).isoformat())
        elif status == "blocked":
            repo.mark_blocked(user_id)
            blocked += 1
        pause(BROADCAST_DELAY_SEC)
    return sent, blocked


def main() -> None:
    parser = argparse.ArgumentParser(description="Nhắn khách AI Pass Store chưa nạp / chưa mua (một lần mỗi khách)")
    parser.add_argument("--send", action="store_true", help="gửi thật (mặc định chỉ chạy thử)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings(dotenv_path=default_dotenv())
    repo = StoreRepository(settings.db_path)
    users = targets(repo, datetime.now(timezone.utc))
    print(f"Khách sẽ nhận: {len(users)}\n\n{TEXT}")
    if not args.send:
        print("\n(chạy thử — thêm --send để gửi thật)")
        return
    sent, blocked = send(repo, TelegramApi(settings.bot_token), users)
    print(f"\nĐã gửi {sent} khách, {blocked} đã chặn bot.")


if __name__ == "__main__":
    main()
