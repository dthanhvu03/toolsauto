"""Deal hời theo danh mục: Market Search, lịch sử giá và AddLiveTag giả, không gọi mạng."""

from __future__ import annotations

import json
import time as clock
from datetime import datetime, timezone
from unittest.mock import MagicMock

from cashback_bot import deals, engagement
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.db import enqueue_event
from cashback_bot.messages import DEAL_PROMPT
from cashback_bot.price_watch import PriceStats
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback
from tests.test_cashback_zalo import _channel, _update

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
    assert market.keywords == list(deals.CATEGORIES["dep"][1][:5]) and data["deals"]["dep"][0]["cashback"] > 0
    (ready,) = _events(bot, "DEALS_READY")
    assert "2 món" in ready["message_html"] and "1 khách" in ready["message_html"]
    deals.tick(bot.repo, bot, admin, SEND.replace(minute=0), market, history)
    assert _events(bot, "DEALS") == [], "chưa tới 20:08"
    for _ in range(2):
        deals.tick(bot.repo, bot, admin, SEND, market, history)
    (sent,) = _events(bot, "DEALS")
    assert sent["chat_id"] == USER and sent["category"] == "deal" and "20:08 giờ phát lộc" in sent["message_html"]
    assert "200k</b> (thường 250k · thấp nhất 30 ngày)" in sent["message_html"] and "⚙️ Đổi danh mục" in sent["message_html"]
    keyboard = json.loads(sent["reply_markup_json"])["inline_keyboard"]
    assert [row[0]["callback_data"] for row in keyboard] == ["u:dl:9:1", "u:dl:9:2", "u:dc:home"]
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
    ids = [r[0]["callback_data"].rsplit(":", 1)[1] for r in keyboard if r[0]["callback_data"].startswith("u:dl:")]
    assert keyboard[-1][0]["callback_data"] == "u:dc:home", "nút cuối: đổi danh mục"
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


def test_zalo_go_nhieu_so_mot_tin_de_chon_danh_muc(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    channel.handle(_update("thongbao", message_id="a"), now=BUILD)
    with bot.repo.connect() as conn:
        internal = conn.execute("SELECT internal_user_id FROM channel_identities").fetchone()[0]
    number = channel.store.menu(internal, BUILD).index("u:dc:home") + 1
    channel.handle(_update(str(number), message_id="b"), now=BUILD)
    channel.handle(_update("1 3, 5", message_id="c"), now=BUILD)
    assert deals.user_categories(bot.repo, internal) == ["nu", "dep", "nha"]
    last = zalo.sent[-1][1]
    assert "1 · 👗 Thời trang nữ ✅" in last and "ví dụ: 1 3 5" in last and "⬜" not in last
    channel.handle(_update("2 4", message_id="d"), now=BUILD)
    assert deals.user_categories(bot.repo, internal) == ["nu", "dep", "nha"], "đủ 3 mục thì không thêm"
    channel.handle(_update("menu", message_id="e"), now=BUILD)
    channel.handle(_update("1 2", message_id="f"), now=BUILD)
    assert "Số 1, 2 là mở màn khác" in zalo.sent[-1][1], "nút mở màn khác không gõ gộp được"


def test_ten_mon_bo_nhan_khuyen_mai_va_gia_le():
    assert deals._short("[MUA 2 TẶNG 1] Combo 2 Nước Tẩy Trang") == "Combo 2 Nước Tẩy Trang"
    assert deals._short("【DAILY】[HOT] Kem Chống Nắng d'Alba") == "Kem Chống Nắng d'Alba"
    assert deals._short("[Chỉ có nhãn]") == "[Chỉ có nhãn]"
    assert (deals._k(64_500), deals._k(75_000), deals._k(89_499), deals._k(500)) == ("64,5k", "75k", "89,5k", "500đ")


def test_trang_chu_co_loi_vao_deal_khi_bat(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert "u:dc:home" not in [d for row in _callback(bot, USER, "u:p:home").inline_keyboard for _l, d in row]
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    rows = _callback(bot, USER, "u:p:home").inline_keyboard
    assert rows[1:3] == ((("📦 Đơn hàng của tôi", "u:p:orders"),), (("🛍️ Deal hời của tôi", "u:dc:home"),)), \
        "ngay dưới Đơn hàng của tôi"


# --- Khách chưa chọn danh mục: bot đoán gu ----------------------------------------------------------------------


def test_doan_gu_tu_mon_da_xem():
    assert deals.guess([("Sơ Mi Nam Dài Tay SIXMEN", None)]) == (["nam"], "Sơ Mi Nam Dài Tay SIXMEN")
    assert deals.guess([("RII Pulse 45W Bộ Sạc Nhanh Kèm Cáp Có Đèn LED", None)])[0] == ["dien"], "sạc + cáp hơn chữ đèn"
    assert deals.guess([("Áo Thun Thể Thao Nam Nữ Ricxie", "Áo Thể Thao")])[0] == ["thethao"], "nam nữ: không đoán giới tính"
    assert deals.guess([("Gấu Bông Rái Cá gối ôm", None)])[0] == ["dochoi"]
    assert deals.guess([("Cúp pha lê in logo", "Khác")]) == ([], "")


def _deal_row(item: int, price: int, usual: int = 250_000) -> dict:
    return dict(item_id=item, shop_id=9, name=f"Áo Polo Nam {item}", price=price, usual=usual, lowest_30d=True,
                cashback=3_000, rating=4.8, sold_30d=500)


def test_khach_chua_chon_nhan_tin_doan_gu_thua_va_chat_hon(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=BUILD)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE link_requests SET product_name = 'Áo Polo Nam GALIO' WHERE telegram_user_id = ?", (USER,))
        assert deals.inferred(conn, SEND) == {USER: (["nam"], "Áo Polo Nam GALIO")}
    pool = {"nam": [_deal_row(1, 200_000), _deal_row(2, 225_000), _deal_row(3, 228_000), _deal_row(4, 190_000),
                    _deal_row(5, 180_000)]}
    deals.save(bot.repo, "2026-10-21", {"status": "draft", "deals": pool, "removed": []})
    deals.tick(bot.repo, bot, admin, SEND)
    (sent,) = _events(bot, "DEALS")
    html = sent["message_html"]
    assert "Vài deal hợp gu bạn nè" in html and "Bot đoán bạn thích 👕 Thời trang nam vì bạn từng xem" in html
    callbacks = [row[0]["callback_data"] for row in json.loads(sent["reply_markup_json"])["inline_keyboard"]]
    assert callbacks == ["u:dl:9:1", "u:dl:9:4", "u:dl:9:5", "u:dc:home", "u:dc:off"], \
        "tối đa 3 món, chỉ món rẻ hơn ≥ 12% (bỏ 225k, 228k)"
    with bot.repo.connect() as conn:
        assert deals.inferred(conn, SEND) == {}, "vừa gửi: 3 ngày sau mới gửi tiếp"


def test_khach_chua_chon_khong_nhan_khi_tat_hay_lo_qua_3_tin(tmp_path):
    bot, _admin = _ready(tmp_path)
    bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=BUILD)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE link_requests SET product_name = 'Áo Polo Nam GALIO', created_at = '2026-10-21T10:40:00Z'")
        for day in (22, 25, 28):  # 3 tin deal sau link cuối (21/10), khách không tạo link nào
            enqueue_event(conn, event_key=f"deals:2026-10-{day}:{USER}", event_type="DEALS", chat_id=USER,
                          message_html="x", audience="customer", category="deal", now=f"2026-10-{day}T13:08:00Z")
        assert deals.inferred(conn, datetime(2026, 11, 1, 13, 0, tzinfo=timezone.utc)) == {}, "3 tin không tạo link"
    other, _ = _ready(tmp_path / "b")
    other.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=BUILD)
    _callback(other, USER, "u:n:t:reminders")
    with other.repo.connect() as conn:
        assert deals.inferred(conn, SEND) == {}, "tắt 🛒 Nhắc"
    third, _ = _ready(tmp_path / "c")
    third.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=BUILD)
    off = _callback(third, USER, "u:dc:off")
    assert "Đã tắt deal hời" in off.text and third.repo.get_state(f"{deals.CATS_PREFIX}{USER}") == ""
    with third.repo.connect() as conn:
        assert deals.inferred(conn, SEND) == {}, "bấm Không nhận deal"


def test_admin_tat_doan_gu(tmp_path):
    bot, _admin = _ready(tmp_path)
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "Khách chưa chọn, bot đoán gu: 🟢 bật" in home.text
    _callback(bot, ADMIN, "c:dl:infer:off")
    assert not deals.infer_enabled(bot.repo)
    assert "Deal hời cho khách chưa chọn (bot đoán gu): tắt" in _callback(bot, ADMIN, "c:menu:hist").text


# --- Lượt trưa 12:08 và không lặp món (chủ bot 2026-10-28: «thông báo cho khách trưa và tối») ---------------------

NOON_BUILD = datetime(2026, 10, 21, 3, 40, tzinfo=timezone.utc)  # 10:40 giờ VN
NOON_SEND = datetime(2026, 10, 21, 5, 10, tzinfo=timezone.utc)  # 12:10 giờ VN


def test_luot_trua_tu_khoa_rieng_va_toi_khong_lap_mon(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.client.payload["productInfo"]["lastUpdate"] = "2026-10-21 03:30:00"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.toggle_category(bot.repo, USER, "dep")
    market, history = FakeMarket([_product(1), _product(2)]), FakeHistory({1: GOOD, 2: GOOD})
    deals.tick(bot.repo, bot, admin, NOON_BUILD, market, history, pause=lambda _s: None)
    for _ in range(100):
        if deals.record(bot.repo, "2026-10-21", deals.NOON).get("status") not in (None, "building"):
            break
        clock.sleep(0.02)
    assert deals.record(bot.repo, "2026-10-21", deals.NOON)["status"] == "draft"
    assert deals.record(bot.repo, "2026-10-21") == {}, "lượt tối chưa soạn"
    assert market.keywords == list(deals.CATEGORIES["dep"][1][5:]), "lượt trưa tìm bộ từ khoá khác lượt tối"
    (ready,) = _events(bot, "DEALS_READY")
    assert "trưa" in ready["message_html"] and "12:08 tự gửi" in ready["message_html"]
    deals.tick(bot.repo, bot, admin, NOON_SEND, market, history)
    (noon,) = _events(bot, "DEALS")
    assert noon["event_key"] == f"deals:2026-10-21:trua:{USER}" and "12:08 nghỉ trưa" in noon["message_html"]
    assert "dữ liệu lúc 10:30" in noon["message_html"]
    row = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)
    deals.save(bot.repo, "2026-10-21", {"status": "draft", "deals": {"dep": [dict(row, item_id=1, name="Kem 1"),
               dict(row, item_id=3, name="Kem 3")]}})
    deals.tick(bot.repo, bot, admin, SEND)
    evening = [e for e in _events(bot, "DEALS") if e["event_key"] == f"deals:2026-10-21:{USER}"][0]
    callbacks = [r[0]["callback_data"] for r in json.loads(evening["reply_markup_json"])["inline_keyboard"]]
    assert callbacks == ["u:dl:9:3", "u:dc:home"], "món 1 đã gửi trưa nay, tối chỉ gửi món mới"
    deals.save(bot.repo, "2026-10-22", {"status": "draft", "deals": {"dep": [dict(row, item_id=3, name="Kem 3")]}})
    deals.tick(bot.repo, bot, admin, SEND.replace(day=22))
    assert len(_events(bot, "DEALS")) == 2 and deals.record(bot.repo, "2026-10-22")["sent"] == 0, \
        "không có món mới thì không gửi"


def test_admin_tat_luot_trua_va_bo_luot_trua(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.toggle_category(bot.repo, USER, "dep")
    day = datetime.now(timezone.utc).astimezone(deals.ICT).date().isoformat()
    deals.save(bot.repo, day, {"status": "draft", "deals": {"dep": [dict(item_id=1, shop_id=9, name="Kem A",
               price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)]}}, deals.NOON)
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "🍱 Trưa 12:08</b>: 📝 Chờ 12:08" in home.text and "🌙 Tối 20:08</b>: ⏳ Chưa soạn (17:30)" in home.text
    buttons = [d for row in home.inline_keyboard for _l, d in row]
    assert "c:dl:skip:trua" in buttons and "c:dl:rm:trua:1" in buttons
    _callback(bot, ADMIN, "c:dl:rm:trua:1")
    assert deals.record(bot.repo, day, deals.NOON)["removed"] == [1]
    _callback(bot, ADMIN, "c:dl:skip:trua")
    assert deals.record(bot.repo, day, deals.NOON)["status"] == "skipped" and deals.record(bot.repo, day) == {}
    _callback(bot, ADMIN, "c:dl:noon:off")
    assert not deals.noon_enabled(bot.repo)
    market = FakeMarket([_product(1)])
    deals.tick(bot.repo, bot, admin, NOON_BUILD, market, FakeHistory({1: GOOD}), pause=lambda _s: None)
    assert market.keywords == [] and deals.record(bot.repo, "2026-10-21", deals.NOON) == {}, "tắt trưa thì không soạn"
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "lượt trưa 12:08: tắt" in history and f"Deal hời {day} trưa: bỏ món 1" in history
