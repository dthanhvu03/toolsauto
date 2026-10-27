"""Báo giảm giá món khách từng xem: AddLiveTag giả, không gọi mạng."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from cashback_bot import engagement, price_watch
from cashback_bot.db import enqueue_event
from cashback_bot.price_watch import PriceHistoryClient, PricePoint
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link, _order

EVENING = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)  # 20:00 giờ VN; link tạo 21/10, giá 250.000đ


class FakePrices:
    def __init__(self, prices: dict[int, PricePoint]):
        self.prices = prices
        self.calls: list[list[int]] = []

    def latest(self, item_ids):
        self.calls.append(list(item_ids))
        return {i: p for i, p in self.prices.items() if i in item_ids}


def _events(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT chat_id, message_html, reply_markup_json FROM admin_notifications "
                            "WHERE event_type = 'PRICE_DROP'").fetchall()


def test_giam_tu_15_phan_tram_con_hang_thi_bao_mot_lan(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    client = FakePrices({8: PricePoint(200_000, True, True)})
    assert price_watch.run(bot.repo, client, EVENING) == 1
    ((chat, html, markup),) = _events(bot)
    assert chat == USER and "giảm còn 200.000đ (−20%)" in html and "flash sale" in html and "/thongbao" in html
    assert json.loads(markup)["inline_keyboard"][0][0]["text"] == "🛒 Mua trên Shopee"
    assert price_watch.run(bot.repo, client, EVENING + timedelta(days=8)) == 0, "mỗi link chỉ báo một lần"


def test_khong_bao_khi_giam_it_het_hang_da_mua_hay_vua_nhac(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    for point in (PricePoint(220_000, False, True), PricePoint(150_000, False, False)):
        assert price_watch.run(bot.repo, FakePrices({8: point}), EVENING) == 0, point
    with bot.repo.connect() as conn:
        enqueue_event(conn, event_key="link_nudge:x", event_type="LINK_NUDGE", chat_id=USER, message_html="x",
                      audience="customer", category="reminder", now="2026-10-21T13:00:00Z")
    assert price_watch.run(bot.repo, FakePrices({8: PricePoint(150_000, False, True)}), EVENING) == 0, \
        "dùng chung ngân sách 1 tin / 7 ngày với nhắc link"
    other = _bot(tmp_path / "b")
    sub = _link(other)
    _order(other, sub)
    assert price_watch.run(other.repo, FakePrices({8: PricePoint(150_000, False, True)}), EVENING) == 0, "đã có đơn"
    third = _bot(tmp_path / "c")
    _link(third)
    _callback(third, USER, "u:n:t:reminders")
    assert price_watch.run(third.repo, FakePrices({8: PricePoint(150_000, False, True)}), EVENING) == 0, "khách tắt nhắc"


def test_chi_chay_khi_bat_trong_khung_toi_moi_ngay_mot_lan(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    client = FakePrices({8: PricePoint(200_000, False, True)})
    assert price_watch.maybe_start(bot.repo, client, now=EVENING) is None, "đang tắt"
    bot.repo.set_state(price_watch.ENABLED_KEY, "1")
    assert price_watch.maybe_start(bot.repo, client, now=EVENING.replace(hour=9)) is None, "16:00: ngoài khung"
    thread = price_watch.maybe_start(bot.repo, client, now=EVENING)
    thread.join(5)
    assert len(_events(bot)) == 1 and "1 tin" in price_watch.last_result_text(bot.repo)
    assert price_watch.maybe_start(bot.repo, client, now=EVENING + timedelta(minutes=30)) is None, "mỗi tối một lượt"
    bot.repo.set_state(engagement.ENABLED_KEY, "1")
    near = datetime(2026, 11, 10, 13, 0, tzinfo=timezone.utc)  # tối 10/11 có nhắc sale 11.11
    assert not price_watch.due(bot.repo, near)


def test_doc_phan_hoi_addlivetag(monkeypatch):
    payload = {"status": "success", "items": [
        {"itemId": "8", "status": "success", "price": {"points": [
            {"date": "2026-10-22", "price": "250000.0000", "flashSale": False, "stockAvailable": True},
            {"date": "2026-10-23", "price": "199000.0000", "flashSale": True, "stockAvailable": True},
        ]}},
        {"itemId": "9", "status": "no_data", "price": {"points": []}},
    ]}
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(json=json, key=headers.get("X-API-Key"))
        return MagicMock(status_code=200, json=lambda: payload)

    monkeypatch.setattr(price_watch.requests, "post", fake_post)
    result = PriceHistoryClient("k").latest([8, 9])
    assert result == {8: PricePoint(199_000, True, True)}
    assert sent["json"]["item_ids"] == [8, 9] and sent["json"]["type"] == "price" and sent["key"] == "k"


def test_man_admin_bat_bao_giam_gia(tmp_path):
    bot = _bot(tmp_path)
    home = _callback(bot, ADMIN, "c:eg:home")
    assert "Báo giảm giá món khách từng xem" in home.text and "chưa chạy lần nào" in home.text
    _callback(bot, ADMIN, "c:eg:drop:on")
    assert price_watch.enabled(bot.repo)
    assert "Báo giảm giá món khách từng xem: bật" in _callback(bot, ADMIN, "c:menu:hist").text
