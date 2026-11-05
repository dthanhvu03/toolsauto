"""🔥 Deal hôm nay ngay trong bot (PLAN-099, kho deal PLAN-100): khách mở xem lúc nào cũng được. Không gọi mạng."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cashback_bot import deals
from tests.test_cashback_deals import _ready, _stock
from tests.test_cashback_wallet import USER, _callback

ROW = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)


def _pool() -> dict:
    return {"dep": [dict(ROW, item_id=i, name=f"Đẹp {i}", price=200_000 - i * 1_000) for i in (4, 2, 1)],
            "nu": [dict(ROW, item_id=10 + i, name=f"Nữ {i}") for i in range(1, 4)],
            "nam": [dict(ROW, item_id=20 + i, name=f"Nam {i}") for i in range(1, 6)],
            "be": [dict(ROW, item_id=30 + i, name=f"Bé {i}") for i in range(1, 6)],
            "nha": [dict(ROW, item_id=4, name="Đẹp 4 trùng món")],
            "dien": []}


def _ids(keyboard) -> list[str]:
    return [row[0]["url"] for row in keyboard if "url" in row[0]]


def test_tin_deal_hom_nay_8_mon_danh_muc_khach_truoc():
    text, keyboard = deals.feed_message(_pool(), [], None, "14:00")
    ids = _ids(keyboard)
    assert len(ids) == deals.FEED_ITEMS and all("shopee.vn" in u for u in ids), "rẻ nhất trước, mỗi danh mục 2"
    assert "🔥 <b>Deal hời hôm nay</b>" in text and "💄 Đẹp 4: <b>196k</b> (thường 250k, −22%) · hoàn ~3k" in text
    assert "dữ liệu lúc 14:00" in text
    chips = [b["callback_data"] for row in keyboard for b in row if "callback_data" in b and b["callback_data"].startswith("u:dh")]
    assert chips == ["u:dh:dep", "u:dh:nu", "u:dh:nam", "u:dh:be", "u:dh:nha"], "danh mục trống thì không có nút"
    _text, mine = deals.feed_message(_pool(), ["be"], None)
    assert len(_ids(mine)) == deals.FEED_ITEMS, "danh mục khách đã chọn xếp trước"
    only, only_kb = deals.feed_message(_pool(), [], "nam")
    count = len(_ids(only_kb))
    assert "👕 Thời trang nam" in only and count == 5 and only_kb[count][0]["callback_data"] == "u:dh"
    empty, empty_kb = deals.feed_message({}, [], None)
    assert "Chưa có deal" in empty and [b["callback_data"] for b in empty_kb[-1]] == ["u:dc:home", "u:p:home"]


def test_khach_mo_deal_hom_nay_tu_trang_chu_lenh_va_bam_mon(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert "u:dh" not in [d for row in _callback(bot, USER, "u:p:home").inline_keyboard for _l, d in row]
    assert "Deal hời" not in bot.handle_text(USER, "buyer", "/deal", update_id=50).text, "deal tắt: /deal về trang chủ"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    assert "u:dh" in [d for row in _callback(bot, USER, "u:p:home").inline_keyboard for _l, d in row]
    now = datetime.now(timezone.utc)
    _stock(bot, _pool(), now - timedelta(hours=20))
    assert "Chưa có deal" in bot.handle_text(USER, "buyer", "/deal", update_id=51).text, "món quá 12 giờ không hiện"
    _stock(bot, _pool(), now)
    deals.set_removed(bot.repo, 4, True)
    feed = bot.handle_text(USER, "buyer", "/deal", update_id=52)
    assert "🔥 <b>Deal hời hôm nay</b>" in feed.text and "Đẹp 4" not in feed.text, "món admin bỏ không hiện"
    assert "🛒" in feed.inline_keyboard[0][0][0]
    by_cat = _callback(bot, USER, "u:dh:be")
    assert "Mẹ &amp; Bé</b>" in by_cat.text and by_cat.edit_message_id == 5, "đổi danh mục: sửa tại chỗ"
    bot.client.payload["productInfo"]["lastUpdate"] = now.strftime("%Y-%m-%d %H:%M:%S")
    update = {"callback_query": {"id": "q-feed", "from": {"id": USER}, "data": "u:dl:9:8",
                                 "message": {"message_id": 6, "chat": {"id": USER, "type": "private"}}}}
    _chat, card = bot.handle_update(update)
    assert "Hoàn dự kiến" in card.text and card.edit_message_id is None, "thẻ link là tin mới, giữ danh sách"


# --- Rà soát 2026-11-05: bấm «Deal hôm nay» không rút gọn link trong lúc khách chờ ------------------------


def test_bam_deal_hom_nay_khong_goi_rut_gon_va_dung_link_da_luu(monkeypatch):
    calls = []
    monkeypatch.setattr(deals, "shorten_shopee_url", lambda *a, **k: calls.append(a) or "https://s.shopee.vn/X")
    pool = _pool()
    pool["dep"][0]["url"] = "https://s.shopee.vn/SAVED"
    _text, keyboard = deals.feed_message(pool, [], None)
    urls = _ids(keyboard)
    assert calls == [] and urls[0] == "https://s.shopee.vn/SAVED"
    assert all("an_redir" in u or "s.shopee.vn" in u for u in urls), "món chưa có link rút gọn dùng an_redir"


def test_quet_giu_link_cu_va_rut_gon_san_mon_moi(monkeypatch):
    calls = []
    monkeypatch.setattr(deals, "shorten_shopee_url",
                        lambda url, **k: calls.append(url) or (None if url.endswith("/22") else f"https://s.shopee.vn/{url[-2:]}"))
    now = datetime(2026, 11, 5, 4, tzinfo=timezone.utc)
    current = {"21": dict(ROW, item_id=21, name="Nam 1", cat="nam", first="x", seen="old", url="https://s.shopee.vn/KEEP")}
    found = {"nam": [dict(ROW, item_id=i, name=f"Nam {i}") for i in (21, 22, 23)]}
    merged, new = deals.merge(current, found, now)
    assert new == 2 and merged["21"]["url"] == "https://s.shopee.vn/KEEP", "gộp lượt quét không làm mất link đã lưu"
    assert deals.prefill_links(merged, deals._stamp(now)) == 1
    assert "url" not in merged["22"], "rút gọn lỗi: không lưu, lượt sau thử lại"
    assert merged["23"]["url"] == "https://s.shopee.vn/23" and len(calls) == 2
