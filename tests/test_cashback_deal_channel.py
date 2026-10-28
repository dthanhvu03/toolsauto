"""Kênh Telegram deal hời (PLAN-099): gắn kênh qua tin chuyển tiếp, đăng bài mỗi lượt, nút mở bot. Không gọi mạng."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from cashback_bot import deals
from tests.test_cashback_deals import BUILD, GOOD, SEND, FakeHistory, FakeMarket, _events, _product, _ready, _wait
from tests.test_cashback_wallet import ADMIN, USER, _callback

CHANNEL = {"id": -1001234567890, "title": "Deal hời <mỗi ngày>", "type": "channel", "username": "dealhoi"}
ROW = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)


def _forward(bot, user_id: int, origin: dict | None = None, legacy: bool = False):
    message = {"message_id": 3, "chat": {"id": user_id, "type": "private"}, "from": {"id": user_id},
               "text": "https://shopee.vn/product/9/8"}
    if legacy:
        message["forward_from_chat"] = CHANNEL
    else:
        message["forward_origin"] = origin or {"type": "channel", "chat": CHANNEL, "message_id": 10}
    return bot.handle_update({"update_id": 40 + user_id, "message": message})[1]


def _live(bot) -> None:
    bot.repo.set_state(deals.CHANNEL_KEY, json.dumps({"id": CHANNEL["id"], "title": "Deal", "username": None}))
    bot.repo.set_state(deals.CHANNEL_ON_KEY, "1")
    bot.repo.set_state(deals.BOT_USERNAME_KEY, "hoantien_bot")


def test_admin_chuyen_tiep_bai_kenh_de_gan(tmp_path):
    bot, _admin = _ready(tmp_path)
    customer = _forward(bot, USER)
    assert "Dùng kênh" not in customer.text and deals.channel(bot.repo) is None, "khách chuyển tiếp: xử lý như tin thường"
    offer = _forward(bot, ADMIN)
    assert "«Deal hời &lt;mỗi ngày&gt;» (@dealhoi)" in offer.text
    assert [d for row in offer.inline_keyboard for _l, d in row] == ["c:dl:ch:set", "c:dl:home"]
    assert deals.channel(bot.repo) is None, "chưa bấm ✅ thì chưa gắn"
    done = _callback(bot, ADMIN, "c:dl:ch:set")
    assert deals.channel(bot.repo)["id"] == CHANNEL["id"] and "Đã gắn kênh" in done.text
    assert bot.repo.get_state(deals.CHANNEL_ON_KEY) == "0" and not deals.channel_live(bot.repo), "gắn xong chưa đăng"
    assert "c:dl:ch:on" in [d for row in done.inline_keyboard for _l, d in row]
    assert _forward(bot, ADMIN, legacy=True).text.startswith("📢 Dùng kênh"), "Bot API cũ: forward_from_chat"
    group = _forward(bot, ADMIN, {"type": "chat", "sender_chat": {"id": -5, "type": "supergroup"}})
    assert "Dùng kênh" not in group.text


def test_man_admin_bat_gioi_thieu_bo_kenh(tmp_path):
    bot, _admin = _ready(tmp_path)
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "chưa gắn" in home.text and "c:dl:ch:on" not in [d for row in home.inline_keyboard for _l, d in row]
    _forward(bot, ADMIN)
    _callback(bot, ADMIN, "c:dl:ch:set")
    assert "cần khởi động lại" in _callback(bot, ADMIN, "c:dl:ch:intro").text, "chưa có username bot"
    bot.repo.set_state(deals.BOT_USERNAME_KEY, "hoantien_bot")
    _callback(bot, ADMIN, "c:dl:ch:intro")
    (intro,) = _events(bot, "DEALS_CHANNEL")
    assert intro["chat_id"] == CHANNEL["id"] and intro["audience"] == "admin" and "12:08 trưa và 20:08 tối" in \
        intro["message_html"]
    assert json.loads(intro["reply_markup_json"])["inline_keyboard"] == [
        [{"text": "🤖 Mở bot hoàn tiền", "url": "https://t.me/hoantien_bot"}]]
    on = _callback(bot, ADMIN, "c:dl:ch:on")
    assert deals.channel_live(bot.repo) and "🟢 Đang đăng" in on.text
    _callback(bot, ADMIN, "c:dl:ch:clear")
    assert deals.channel(bot.repo) is None and not deals.channel_live(bot.repo)
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "Kênh deal: gắn Deal hời" in history and "bật đăng bài" in history and "bỏ Deal hời" in history


def test_bai_kenh_toi_da_8_mon_moi_danh_muc_2():
    pool = {"dep": [dict(ROW, item_id=i, name=f"Đẹp {i}", price=200_000 - i * 1_000) for i in range(1, 5)],
            "nu": [dict(ROW, item_id=10 + i, name=f"Nữ {i}") for i in range(1, 4)],
            "nam": [dict(ROW, item_id=20 + i, name=f"Nam {i}") for i in range(1, 6)],
            "be": [dict(ROW, item_id=30 + i, name=f"Bé {i}") for i in range(1, 6)],
            "nha": [dict(ROW, item_id=4, name="Đẹp 4 trùng món")]}
    text, keyboard = deals.channel_post(pool, removed={3}, bot="hoantien_bot", day="2026-10-21")
    urls = [row[0]["url"] for row in keyboard[:-1]]
    assert len(urls) == deals.CHANNEL_ITEMS and keyboard[-1][0]["url"] == "https://t.me/hoantien_bot"
    assert urls[:2] == ["https://t.me/hoantien_bot?start=dl_9_4", "https://t.me/hoantien_bot?start=dl_9_2"], \
        "rẻ nhất trước, bỏ món admin bỏ (3), mỗi danh mục tối đa 2"
    assert sum("start=dl_9_4" in u for u in urls) == 1, "một món hai danh mục chỉ đăng một lần"
    assert "🔥 <b>Deal hời 20:08 · 21/10</b>" in text and "💄 Đẹp 4: <b>196k</b> (thường 250k, −22%) · hoàn ~3k" in text
    assert deals.channel_post({"dep": []}, set(), "hoantien_bot", "2026-10-21") is None


def test_kenh_bat_thi_soan_du_danh_muc_va_dang_luc_gui(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    _live(bot)
    market, history = FakeMarket([_product(1), _product(2)]), FakeHistory({1: GOOD, 2: GOOD})
    deals.tick(bot.repo, bot, admin, BUILD, market, history, pause=lambda _s: None)
    data = _wait(bot)
    assert sorted(data["deals"]) == sorted(deals.CATEGORIES), "chưa ai chọn danh mục vẫn soạn cho kênh, đủ danh mục"
    deals.tick(bot.repo, bot, admin, SEND, market, history)
    assert _events(bot, "DEALS") == [], "không có khách nào chọn: không gửi riêng ai"
    (post,) = _events(bot, "DEALS_CHANNEL")
    assert post["event_key"] == "deals_channel:2026-10-21" and post["chat_id"] == CHANNEL["id"]
    keyboard = json.loads(post["reply_markup_json"])["inline_keyboard"]
    assert keyboard[0][0]["url"].startswith("https://t.me/hoantien_bot?start=dl_9_")
    assert deals.record(bot.repo, "2026-10-21")["channel"] == 1


def test_kenh_tat_hay_thieu_username_thi_khong_dang(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.toggle_category(bot.repo, USER, "dep")
    draft = {"status": "draft", "deals": {"dep": [dict(ROW, item_id=1, name="Kem A")]}}
    for state in ({deals.CHANNEL_ON_KEY: "0"}, {deals.BOT_USERNAME_KEY: ""}):
        _live(bot)
        for key, value in state.items():
            bot.repo.set_state(key, value)
        deals.save(bot.repo, "2026-10-21", dict(draft))
        deals.tick(bot.repo, bot, admin, SEND)
        assert _events(bot, "DEALS_CHANNEL") == [] and "channel" not in deals.record(bot.repo, "2026-10-21")
        with bot.repo.connect() as conn:
            conn.execute("DELETE FROM admin_notifications")


def test_khach_bam_mon_trong_kenh_mo_bot_ra_the_link(tmp_path):
    bot, _admin = _ready(tmp_path)
    bot.client.payload["productInfo"]["lastUpdate"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert deals.start_deal("/start dl_9_8") == "u:dl:9:8" and deals.start_deal("/start abc") is None
    card = bot.handle_text(USER, "buyer", "/start dl_9_8", update_id=77)
    assert "Đã tạo link hoàn tiền" in card.text and card.button_url
    with bot.repo.connect() as conn:
        (row,) = conn.execute("SELECT telegram_user_id, item_id FROM link_requests WHERE link_status = 'created'")
    assert tuple(row) == (USER, 8), "link riêng của người bấm"
    assert "Đã tạo link" not in bot.handle_text(USER, "buyer", "/start", update_id=78).text, "/start thường: trang chủ"
