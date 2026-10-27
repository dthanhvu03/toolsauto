"""Giữ chân đợt 1 (reports/CASHBACK_RETENTION_DESIGN_2026-10-27.md): chỉ sửa câu chữ trong tin đã có, đo giữ chân đúng."""

from __future__ import annotations

from datetime import datetime, timezone

from cashback_bot import insights
from cashback_bot.messages import COME_BACK, FIRST_ORDER, order_new_notice, order_update_notice
from tests.test_cashback_order_notifications import _events, _ready
from tests.test_cashback_wallet import _link, _order


def test_don_dau_tien_co_loi_mung_don_sau_thi_khong(tmp_path):
    bot = _ready(tmp_path)
    sub = _link(bot)
    _order(bot, sub, cid="o1")
    _order(bot, sub, cid="o2")
    first, second = (e["message_html"] for e in _events(bot))
    assert FIRST_ORDER in first and FIRST_ORDER not in second
    assert any(line in first for line in COME_BACK) and any(line in second for line in COME_BACK)


def test_cau_moi_quay_lai_khong_co_o_don_huy():
    cancelled = order_new_notice("••••AB12", 0, "CANCELLED", "REJECTED", first=True)
    assert FIRST_ORDER not in cancelled and not any(line in cancelled for line in COME_BACK)
    update = order_update_notice("••••AB12", statuses=["CANCELLED"], ineligible=True, approved=False,
                                 old_cashback=None, new_cashback=None)
    assert not any(line in update for line in COME_BACK)
    approved = order_update_notice("••••AB12", statuses=[], ineligible=False, approved=True,
                                   old_cashback=None, new_cashback=None)
    assert approved.rstrip().endswith(tuple(COME_BACK))
    # Đổi luân phiên theo mã đơn để khỏi nhàm.
    assert len({order_new_notice(f"••••{n:04d}", 1_000, "PAID", "PENDING").rsplit("\n", 1)[1] for n in range(6)}) == 2


def test_giu_chan_tuan_chua_toi_khong_ghi_0_phan_tram(tmp_path):
    bot = _ready(tmp_path)
    now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)
    with bot.repo.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO telegram_users (telegram_user_id, created_at, last_seen_at) VALUES (5, '2026-10-26T02:00:00Z', 'x')")
        conn.execute("INSERT OR REPLACE INTO telegram_users (telegram_user_id, created_at, last_seen_at) VALUES (6, '2026-10-20T02:00:00Z', 'x')")
        rows = {k.week: k for k in insights.cohorts(conn, now) if k.size}
    assert rows["26/10"].next_text == "chưa tới" and rows["26/10"].week4_text == "chưa tới"
    assert rows["19/10"].next_text == "0% (đang đo)" and rows["19/10"].week4_text == "chưa tới"
    done = insights.Cohort("01/09", 4, 1, 0, "done", "done")
    assert (done.next_text, done.week4_text) == ("25%", "0%")
