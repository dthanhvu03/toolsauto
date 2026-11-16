"""PLAN-172 T5: nhắc khách đang có tiền hoàn trong ví → lấy link mời bạn (một lần).

invite-v1 (tin giới thiệu chung) đã gửi hết người tạo link mà referrals vẫn 0.
Tin này chỉ gửi khách có dòng hoàn ``available`` (không phải thưởng ref), kèm nút ``u:p:invite``.

    python -m cashback_bot.invite_nudge           # chạy thử
    python -m cashback_bot.invite_nudge --send    # xếp hàng đợi (poller gửi)

Tắt: bot_state ``invite_nudge:off``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.referral import SHARE_BPS

logger = logging.getLogger("cashback_bot")

OFF_KEY = "invite_nudge:off"
EVENT = "INVITE_NUDGE"
KEY_PREFIX = "invite_nudge:v1:"
PCT = SHARE_BPS // 100

TEXT = (
    f"🤝 <b>Bạn đang có tiền hoàn trong ví — rủ bạn bè để thêm thưởng?</b>\n\n"
    f"Gửi link mời của bạn. Bạn bè vào bot bằng link đó thì mỗi đơn họ mua qua bot trong "
    f"<b>6 tháng</b>, bạn được thêm <b>{PCT}% hoa hồng</b> của đơn (bạn bè vẫn nhận đủ phần của họ).\n\n"
    f"👉 Bấm nút dưới để lấy link mời (hoặc gõ /moiban).\n"
    f"Phiền thì gõ /thongbao tắt nha 🫶"
)
MARKUP = {"inline_keyboard": [[{"text": "🤝 Lấy link mời bạn", "callback_data": "u:p:invite"}]]}


def targets(repo: TrackingRepository) -> list[int]:
    if repo.get_state(OFF_KEY):
        return []
    with repo.connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT e.telegram_user_id FROM cashback_entries e
            WHERE e.status = 'available' AND instr(e.conversion_id, ':ref') = 0
              AND e.telegram_user_id > 0
              AND NOT EXISTS (
                SELECT 1 FROM admin_notifications n
                WHERE n.event_key = ? || CAST(e.telegram_user_id AS TEXT)
              )
              AND EXISTS (
                SELECT 1 FROM link_requests l
                WHERE l.telegram_user_id = e.telegram_user_id AND l.link_status = 'created'
              )
            ORDER BY e.telegram_user_id
            """,
            (KEY_PREFIX,),
        ).fetchall()
    return [int(r[0]) for r in rows]


def queue(repo: TrackingRepository, users: list[int], now: datetime | None = None) -> int:
    if repo.get_state(OFF_KEY):
        return 0
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    markup = json.dumps(MARKUP, ensure_ascii=False)
    queued = 0
    with repo.connect() as conn:
        for user_id in users:
            if enqueue_event(
                conn,
                event_key=f"{KEY_PREFIX}{user_id}",
                event_type=EVENT,
                chat_id=user_id,
                message_html=TEXT,
                audience="customer",
                category="wallet",
                reply_markup_json=markup,
                source_ref="invite_nudge",
                now=stamp,
            ):
                queued += 1
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description="Nhắc khách có tiền ví lấy link mời bạn (PLAN-172 T5)")
    parser.add_argument("--send", action="store_true", help="xếp hàng đợi gửi thật")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = (os.environ.get("CASHBACK_DB_PATH") or "./data/cashback.sqlite").strip()
    repo = TrackingRepository(path)
    users = targets(repo)
    print(f"Khách sẽ nhận: {len(users)}\n\n{TEXT}")
    if not args.send:
        print("\n(chạy thử — thêm --send để xếp hàng đợi)")
        return
    n = queue(repo, users)
    print(f"\nĐã xếp {n} tin vào hàng đợi (poller gửi).")


if __name__ == "__main__":
    main()
