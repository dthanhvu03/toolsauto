"""Deal hời theo danh mục: Market Search, lịch sử giá và AddLiveTag giả, không gọi mạng."""

from __future__ import annotations

import json
import time as clock
from datetime import datetime, timezone
from unittest.mock import MagicMock

from cashback_bot import deals, engagement
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.messages import DEAL_PROMPT
from cashback_bot.price_watch import PriceStats
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback

BUILD = datetime(2026, 10, 21, 10, 40, tzinfo=timezone.utc)  # 17:40 giờ VN
SEND = datetime(2026, 10, 21, 13, 10, tzinfo=timezone.utc)  # 20:10 giờ VN


def _product(item: int, rating: float = 4.8, sold: int = 500) -> dict:
    return {"itemId": item, "shopId": 9, "productName": f"Kem chống nắng số {item}", "rating": rating, "sold30d": sold}


class FakeMarket:
    def __init__(self, products):
        self.products = products
        self.keywords: list[str] = []

    def top(self, keyword, limit=15):
        self.keywords.append(keyword)
        return self.products


class FakeHistory:
    def __init__(self, stats):
        self.stats_map = stats

    def stats(self, item_ids, days=30):
        return {i: s for i, s in self.stats_map.items() if i in item_ids}


GOOD = PriceStats(price=200_000, usual=250_000, lowest=200_000, flash_sale=False, in_stock=None, last_date="2026-10-21")


def test_chi_chon_mon_hoi_that():
    stats = {
        1: GOOD,
        2: PriceStats(240_000, 250_000, 200_000, False, None, "x"),  # chỉ rẻ hơn 4%, không phải thấp nhất
        3: GOOD, 4: GOOD,
        5: PriceStats(150_000, 250_000, 150_000, True, False, "x"),  # flash sale hết suất
        6: PriceStats(150_000, 250_000, 150_000, False, None, "x"),
    }
    products = [_product(1), _product(2), _product(3, rating=4.2), _product(4, sold=50), _product(5), _product(6)]
    assert [d["item_id"] for d in deals.pick(products, stats)] == [6, 1], "sắp theo % rẻ hơn thường ngày"


def _ready(tmp_path):
    bot = _bot(tmp_path)
    bot.client.payload["productInfo"]["lastUpdate"] = "2026-10-21 10:30:00"
    bot.repo.upsert_user(USER, "buyer")
    admin = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
    return bot, admin


def _wait(bot, day="2026-10-21"):
    for _ in range(100):
        if deals.record(bot.repo, day).get("status") not in (None, "building"):
            return deals.record(bot.repo, day)
        clock.sleep(0.02)
    raise AssertionError("soạn deal quá lâu")


def _events(bot, kind):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM admin_notifications WHERE event_type = ?", (kind,)).fetchall()


def test_soan_17h30_bao_admin_20h08_gui_khach_da_chon(tmp_path):
    bot, admin = _ready(tmp_path)
    market, history = FakeMarket([_product(1), _product(2)]), FakeHistory({1: GOOD, 2: GOOD})
    deals.tick(bot.repo, bot, admin, BUILD, market, history, pause=lambda _s: None)
    assert deals.record(bot.repo, "2026-10-21") == {}, "đang tắt thì không làm gì"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.tick(bot.repo, bot, admin, BUILD, market, history, pause=lambda _s: None)
    assert deals.record(bot.repo, "2026-10-21") == {}, "chưa ai chọn danh mục thì không gọi AddLiveTag"
    deals.toggle_category(bot.repo, USER, "dep")
    deals.tick(bot.repo, bot, admin, BUILD, market, history, pause=lambda _s: None)
    data = _wait(bot)
    assert data["status"] == "draft" and [d["item_id"] for d in data["deals"]["dep"]] == [1, 2]
    assert market.keywords == list(deals.CATEGORIES["dep"][1]) and data["deals"]["dep"][0]["cashback"] > 0
    (ready,) = _events(bot, "DEALS_READY")
    assert "2 món" in ready["message_html"] and "1 khách" in ready["message_html"]
    deals.tick(bot.repo, bot, admin, SEND.replace(minute=0), market, history)
    assert _events(bot, "DEALS") == [], "chưa tới 20:08"
    for _ in range(2):
        deals.tick(bot.repo, bot, admin, SEND, market, history)
    (sent,) = _events(bot, "DEALS")
    assert sent["chat_id"] == USER and sent["category"] == "deal" and "20:08 giờ phát lộc" in sent["message_html"]
    assert "200k</b> (thường 250k · thấp nhất 30 ngày)" in sent["message_html"] and "/thongbao" in sent["message_html"]
    keyboard = json.loads(sent["reply_markup_json"])["inline_keyboard"]
    assert [row[0]["callback_data"] for row in keyboard] == ["u:dl:9:1", "u:dl:9:2"]
    assert deals.record(bot.repo, "2026-10-21")["status"] == "sent"


def test_qua_gio_bo_va_bo_hom_nay(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.toggle_category(bot.repo, USER, "dep")
    deals.save(bot.repo, "2026-10-21", {"status": "draft", "deals": {"dep": [dict(item_id=1, shop_id=9, name="A",
               price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)]}})
    deals.tick(bot.repo, bot, admin, SEND.replace(hour=14, minute=30))
    assert deals.record(bot.repo, "2026-10-21")["status"] == "missed" and _events(bot, "DEALS") == []
    bot.repo.set_state(engagement.ENABLED_KEY, "1")
    deals.save(bot.repo, "2026-11-10", {"status": "draft", "deals": {}})
    deals.tick(bot.repo, bot, admin, datetime(2026, 11, 10, 13, 10, tzinfo=timezone.utc))
    assert deals.record(bot.repo, "2026-11-10")["status"] == "sale", "tối 10/11 có nhắc sale 11.11 lúc 20:30"


def test_tin_toi_da_5_mon_chia_deu_danh_muc():
    row = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)
    pool = {"dep": [dict(row, item_id=i, name=f"Đẹp {i}") for i in range(1, 5)],
            "nu": [dict(row, item_id=i, name=f"Nữ {i}") for i in range(11, 15)]}
    text, keyboard = deals.message_for(["dep", "nu"], pool, removed={2})
    ids = [r[0]["callback_data"].rsplit(":", 1)[1] for r in keyboard]
    assert ids == ["1", "3", "4", "11", "12"], "chia lần lượt từng danh mục, bỏ món admin đã bỏ (2)"
    assert "💄 Làm đẹp" in text and "👗 Thời trang nữ" in text
    assert deals.message_for(["thucung"], pool, set()) is None, "không có món thì không gửi"


def test_khach_chon_danh_muc_va_bam_mon_thi_ra_the_link(tmp_path):
    bot, _admin = _ready(tmp_path)
    notify = _callback(bot, USER, "u:p:notify")
    assert "u:dc:home" not in [d for row in notify.inline_keyboard for _l, d in row], "deal đang tắt thì không mời"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    assert DEAL_PROMPT[0][0] in [b for row in _callback(bot, USER, "u:p:notify").inline_keyboard for b in row]
    for key in ("dep", "nu", "nam"):
        _callback(bot, USER, f"u:dc:t:{key}")
    full = _callback(bot, USER, "u:dc:t:be")
    assert "tối đa 3" in full.text and deals.user_categories(bot.repo, USER) == ["dep", "nu", "nam"]
    _callback(bot, USER, "u:dc:t:nu")
    assert deals.user_categories(bot.repo, USER) == ["dep", "nam"]
    bot.client.payload["productInfo"]["lastUpdate"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    update = {"callback_query": {"id": "q-deal", "from": {"id": USER}, "data": "u:dl:9:8",
                                 "message": {"message_id": 5, "chat": {"id": USER, "type": "private"}}}}
    _chat, card = bot.handle_update(update)
    assert "Đã tạo link hoàn tiền" in card.text and card.button_url and card.edit_message_id is None, \
        "thẻ link là tin mới, không sửa đè danh sách deal"


def test_link_dau_tien_moi_chon_danh_muc(tmp_path):
    bot, _admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    first = bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=BUILD)
    assert DEAL_PROMPT[0][0] in [b for row in first.inline_keyboard for b in row]
    second = bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=2, now=BUILD)
    assert DEAL_PROMPT[0][0] not in [b for row in second.inline_keyboard for b in row]


def test_man_admin_deal_hoi(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert "c:dl:home" in [d for row in _callback(bot, ADMIN, "c:eg:home").inline_keyboard for _l, d in row]
    _callback(bot, ADMIN, "c:dl:on")
    deals.toggle_category(bot.repo, USER, "dep")
    day = datetime.now(timezone.utc).astimezone(deals.ICT).date().isoformat()
    deals.save(bot.repo, day, {"status": "draft", "deals": {"dep": [dict(item_id=1, shop_id=9, name="Kem A",
               price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)]}})
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "Kem A: 200.000đ (thường 250.000đ, −20%)" in home.text and "💄 Làm đẹp 1" in home.text
    _callback(bot, ADMIN, "c:dl:rm:1")
    assert deals.record(bot.repo, day)["removed"] == [1]
    _callback(bot, ADMIN, "c:dl:skip")
    assert deals.record(bot.repo, day)["status"] == "skipped"
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "Deal hời: bật" in history and "bỏ món 1" in history and "⏭ Bỏ hôm nay" in history
