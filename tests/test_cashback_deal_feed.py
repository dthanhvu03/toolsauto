"""🔥 Deal hôm nay ngay trong bot (PLAN-099): khách mở xem lúc nào cũng được. Không gọi mạng."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cashback_bot import deals
from tests.test_cashback_deals import _ready
from tests.test_cashback_wallet import USER, _callback

ROW = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)
EVENING_AFTER = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)  # 21:00 giờ VN
NOON_AFTER = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)  # 13:00 hôm sau


def _pool() -> dict:
    return {"dep": [dict(ROW, item_id=i, name=f"Đẹp {i}", price=200_000 - i * 1_000) for i in range(1, 5)],
            "nu": [dict(ROW, item_id=10 + i, name=f"Nữ {i}") for i in range(1, 4)],
            "nam": [dict(ROW, item_id=20 + i, name=f"Nam {i}") for i in range(1, 6)],
            "be": [dict(ROW, item_id=30 + i, name=f"Bé {i}") for i in range(1, 6)],
            "nha": [dict(ROW, item_id=4, name="Đẹp 4 trùng món")],
            "dien": []}


def _ids(keyboard) -> list[str]:
    return [row[0]["callback_data"] for row in keyboard if row[0]["callback_data"].startswith("u:dl:")]


def test_chi_hien_luot_da_toi_gio_gui_va_khong_bi_bo(tmp_path):
    bot, _admin = _ready(tmp_path)
    deals.save(bot.repo, "2026-10-21", {"status": "draft", "deals": _pool()})
    assert deals.latest_released(bot.repo, EVENING_AFTER) is None, "bản nháp chưa gửi: admin còn đang duyệt"
    for status in ("sent", "sale", "missed"):
        deals.save(bot.repo, "2026-10-21", {"status": status, "deals": _pool()})
        assert deals.latest_released(bot.repo, EVENING_AFTER)[:2] == ("2026-10-21", deals.EVENING)
    deals.save(bot.repo, "2026-10-21", {"status": "skipped", "deals": _pool()})
    assert deals.latest_released(bot.repo, EVENING_AFTER) is None, "lượt admin bỏ thì không hiện"
    deals.save(bot.repo, "2026-10-21", {"status": "sent", "deals": _pool()})
    deals.save(bot.repo, "2026-10-22", {"status": "sent", "deals": {"dep": [dict(ROW, item_id=99, name="Trưa")]}},
               deals.NOON)
    day, slot, _data = deals.latest_released(bot.repo, NOON_AFTER)
    assert (day, slot) == ("2026-10-22", deals.NOON), "lượt mới nhất trước"
    assert deals.latest_released(bot.repo, datetime(2026, 10, 23, 17, 0, tzinfo=timezone.utc)) is None, "chỉ hôm nay, hôm qua"


def test_tin_deal_hom_nay_8_mon_danh_muc_khach_truoc():
    found = ("2026-10-21", deals.EVENING, {"status": "sent", "deals": _pool(), "removed": [3]})
    text, keyboard = deals.feed_message(found, [], None, EVENING_AFTER)
    ids = _ids(keyboard)
    assert len(ids) == deals.FEED_ITEMS and ids[:2] == ["u:dl:9:4", "u:dl:9:2"], \
        "rẻ nhất trước, bỏ món admin bỏ (3), mỗi danh mục tối đa 2"
    assert sum(i == "u:dl:9:4" for i in ids) == 1, "một món hai danh mục chỉ hiện một lần"
    assert "🔥 <b>Deal hời hôm nay</b>" in text and "💄 Đẹp 4: <b>196k</b> (thường 250k, −22%) · hoàn ~3k" in text
    chips = [b["callback_data"] for row in keyboard for b in row if b["callback_data"].startswith("u:dh")]
    assert chips == ["u:dh:dep", "u:dh:nu", "u:dh:nam", "u:dh:be", "u:dh:nha"], "danh mục trống thì không có nút"
    _text, mine = deals.feed_message(found, ["be"], None, EVENING_AFTER)
    assert _ids(mine)[:2] == ["u:dl:9:31", "u:dl:9:32"], "danh mục khách đã chọn xếp trước"
    only, only_kb = deals.feed_message(found, [], "nam", EVENING_AFTER)
    assert "👕 Thời trang nam" in only and len(_ids(only_kb)) == 5 and only_kb[len(_ids(only_kb))][0]["callback_data"] == "u:dh"
    old, _kb = deals.feed_message(found, [], None, NOON_AFTER)
    assert "Deal hời hôm qua" in old and "lúc 17:30 hôm qua" in old
    empty, empty_kb = deals.feed_message(None, [], None, EVENING_AFTER)
    assert "Chưa có deal" in empty and [b["callback_data"] for b in empty_kb[-1]] == ["u:dc:home", "u:p:home"]


def test_khach_mo_deal_hom_nay_tu_trang_chu_lenh_va_bam_mon(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert "u:dh" not in [d for row in _callback(bot, USER, "u:p:home").inline_keyboard for _l, d in row]
    assert "Deal hời" not in bot.handle_text(USER, "buyer", "/deal", update_id=50).text, "deal tắt: /deal về trang chủ"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    assert "u:dh" in [d for row in _callback(bot, USER, "u:p:home").inline_keyboard for _l, d in row]
    now = datetime.now(timezone.utc)
    today = now.astimezone(deals.ICT).date()
    for day in (today, today - timedelta(days=1)):  # lúc nào chạy test cũng có lượt đã tới giờ gửi
        for slot in deals.SLOTS:
            deals.save(bot.repo, day.isoformat(), {"status": "sent", "deals": _pool()}, slot)
    feed = bot.handle_text(USER, "buyer", "/deal", update_id=51)
    assert "🔥 <b>Deal hời hôm" in feed.text and "🛒" in feed.inline_keyboard[0][0][0]
    by_cat = _callback(bot, USER, "u:dh:be")
    assert "Mẹ &amp; Bé</b>" in by_cat.text and by_cat.edit_message_id == 5, "đổi danh mục: sửa tại chỗ"
    bot.client.payload["productInfo"]["lastUpdate"] = now.strftime("%Y-%m-%d %H:%M:%S")
    update = {"callback_query": {"id": "q-feed", "from": {"id": USER}, "data": "u:dl:9:8",
                                 "message": {"message_id": 6, "chat": {"id": USER, "type": "private"}}}}
    _chat, card = bot.handle_update(update)
    assert "Đã tạo link hoàn tiền" in card.text and card.edit_message_id is None, "thẻ link là tin mới, giữ danh sách"
