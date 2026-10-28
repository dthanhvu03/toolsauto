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
SCAN = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)  # 14:00 giờ VN (giờ chẵn)
SEND = datetime(2026, 10, 21, 13, 10, tzinfo=timezone.utc)  # 20:10 giờ VN


def _product(item: int, rating: float = 4.8, sold: int = 500) -> dict:
    return {"itemId": item, "shopId": 9, "productName": f"Kem chống nắng số {item}", "rating": rating, "sold30d": sold}


class FakeMarket:
    """`only`: chỉ từ khoá của danh mục này ra món (để món không rơi vào danh mục đầu tiên)."""

    def __init__(self, products, only: str | None = "dep"):
        self.products = products
        self.only = only
        self.keywords: list[str] = []

    def top(self, keyword, limit=15):
        self.keywords.append(keyword)
        return self.products if self.only is None or keyword in deals.CATEGORIES[self.only][1] else []


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


def _events(bot, kind):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT * FROM admin_notifications WHERE event_type = ?", (kind,)).fetchall()


def _stock(bot, by_cat: dict, at: datetime) -> None:
    """Đưa món vào kho deal như một lượt quét lúc `at`."""
    merged, _new = deals.merge(deals.pool(bot.repo), by_cat, at)
    bot.repo.set_state(deals.POOL_KEY, json.dumps(merged))


def _wait_scan(bot) -> dict:
    for _ in range(200):
        if deals.scan_record(bot.repo).get("status") not in (None, "building"):
            return deals.scan_record(bot.repo)
        clock.sleep(0.02)
    raise AssertionError("quét deal quá lâu")


def test_tin_toi_da_3_mon_chia_deu_danh_muc():
    row = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)
    pool = {"dep": [dict(row, item_id=i, name=f"Đẹp {i}") for i in range(1, 5)],
            "nu": [dict(row, item_id=i, name=f"Nữ {i}") for i in range(11, 15)]}
    text, keyboard = deals.message_for(["dep", "nu"], pool, removed={2})
    ids = [r[0]["callback_data"].rsplit(":", 1)[1] for r in keyboard if r[0]["callback_data"].startswith("u:dl:")]
    assert keyboard[-1][0]["callback_data"] == "u:dc:home", "nút cuối: đổi danh mục"
    assert ids == ["1", "3", "11"], "tối đa 3 món, chia lần lượt từng danh mục, bỏ món đã gửi (2)"
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
    assert rows[1:3] == ((("📦 Đơn hàng của tôi", "u:p:orders"),), (("🔥 Deal hôm nay", "u:dh"), ("🛍️ Danh mục deal", "u:dc:home"))), \
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
    _stock(bot, pool, SEND)
    assert deals.send_round(bot.repo, SEND) == 1
    (sent,) = _events(bot, "DEALS")
    html = sent["message_html"]
    assert "Vài món hợp gu bạn" in html and "Bot đoán bạn thích 👕 Thời trang nam vì bạn từng xem" in html
    callbacks = [row[0]["callback_data"] for row in json.loads(sent["reply_markup_json"])["inline_keyboard"]]
    assert callbacks == ["u:dl:9:5", "u:dl:9:4", "u:dl:9:1", "u:dc:home", "u:dc:off"], \
        "tối đa 3 món rẻ nhất, chỉ món rẻ hơn ≥ 12% (bỏ 225k, 228k)"
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


# --- Quét mỗi giờ, có món mới là gửi (PLAN-100) -----------------------------------------------------------------


def _row(item: int, name: str = "Kem", price: int = 200_000) -> dict:
    return dict(item_id=item, shop_id=9, name=f"{name} {item}", price=price, usual=250_000, lowest_30d=True,
                cashback=3_000, rating=4.8, sold_30d=500)


def _local(hour: int, minute: int = 0, day: int = 21) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=deals.ICT).astimezone(timezone.utc)


def test_quet_moi_gio_co_mon_moi_la_gui(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.client.payload["productInfo"]["lastUpdate"] = "2026-10-21 06:30:00"
    market, history = FakeMarket([_product(1), _product(2)]), FakeHistory({1: GOOD, 2: GOOD})
    deals.tick(bot.repo, bot, admin, SCAN, market, history, pause=lambda _s: None)
    assert deals.scan_record(bot.repo) == {} and market.keywords == [], "đang tắt thì không quét"
    bot.repo.set_state(deals.ENABLED_KEY, "1")
    deals.toggle_category(bot.repo, USER, "dep")
    deals.tick(bot.repo, bot, admin, SCAN, market, history, pause=lambda _s: None)
    scan = _wait_scan(bot)
    assert scan["status"] == "done" and (scan["found"], scan["new"], scan["sent"]) == (2, 2, 1)
    assert market.keywords == [k for _label, words in deals.CATEGORIES.values() for k in words[:5]], \
        "giờ chẵn: 5 từ khoá đầu, đủ 10 danh mục"
    assert {d["cat"] for d in deals.pool(bot.repo).values()} == {"dep"}
    (sent,) = _events(bot, "DEALS")
    assert sent["chat_id"] == USER and sent["category"] == "deal" and "Deal mới vừa lên" in sent["message_html"]
    assert "200k</b> (thường 250k · thấp nhất 30 ngày)" in sent["message_html"] and "dữ liệu lúc 14:00" in \
        sent["message_html"]
    keyboard = json.loads(sent["reply_markup_json"])["inline_keyboard"]
    assert [row[0]["callback_data"] for row in keyboard] == ["u:dl:9:1", "u:dl:9:2", "u:dc:home"]
    searched = len(market.keywords)
    deals.tick(bot.repo, bot, admin, SCAN.replace(minute=40), market, history, pause=lambda _s: None)
    assert len(market.keywords) == searched, "mỗi giờ một lượt"
    deals.tick(bot.repo, bot, admin, SCAN.replace(hour=8), market, history, pause=lambda _s: None)
    scan = _wait_scan(bot)
    assert scan["hour"] == "2026-10-21T15" and (scan["new"], scan["sent"]) == (0, 0), "không có món mới: không gửi"
    assert market.keywords[searched:searched + 5] == list(deals.CATEGORIES["nu"][1][5:]), "giờ lẻ: từ khoá còn lại"
    deals.tick(bot.repo, bot, admin, _local(22, 5), market, history, pause=lambda _s: None)
    assert deals.scan_record(bot.repo)["hour"] == "2026-10-21T15", "ngoài 7:00–21:00 không quét"


def test_mot_mon_cung_gui_toi_da_4_tin_ngay_cach_2_gio(tmp_path):
    bot, _admin = _ready(tmp_path)
    deals.toggle_category(bot.repo, USER, "dep")
    _stock(bot, {"dep": [_row(1)]}, _local(7, 0))
    assert deals.send_round(bot.repo, _local(7, 30)) == 0, "trước 8:00 không gửi"
    assert deals.send_round(bot.repo, _local(8, 0)) == 1, "1 món cũng gửi"
    _stock(bot, {"dep": [_row(2)]}, _local(9, 0))
    assert deals.send_round(bot.repo, _local(9, 0)) == 0, "cách tin trước chưa đủ 2 giờ"
    for hour, item in ((10, 3), (12, 4), (14, 5)):
        _stock(bot, {"dep": [_row(item)]}, _local(hour))
        assert deals.send_round(bot.repo, _local(hour)) == 1
    _stock(bot, {"dep": [_row(6)]}, _local(16))
    assert deals.send_round(bot.repo, _local(16)) == 0, "đủ 4 tin hôm nay"
    sent = [json.loads(e["reply_markup_json"])["inline_keyboard"] for e in _events(bot, "DEALS")]
    assert [[r[0]["callback_data"] for r in k][:-1] for k in sent] == [
        ["u:dl:9:1"], ["u:dl:9:2", "u:dl:9:3"], ["u:dl:9:4"], ["u:dl:9:5"]], "món để dành gửi lượt sau, không lặp món"
    _stock(bot, {"dep": [_row(7)]}, _local(8, day=22))
    assert deals.send_round(bot.repo, _local(8, day=22)) == 1, "sang ngày mới đếm lại"
    _stock(bot, {"dep": [_row(8)]}, _local(22, 30, day=22))
    assert deals.send_round(bot.repo, _local(22, 30, day=22)) == 0, "sau 22:00 không gửi"


def test_kho_cap_nhat_mon_cu_bo_mon_qua_24_gio_va_mon_admin_bo(tmp_path):
    bot, _admin = _ready(tmp_path)
    merged, new = deals.merge({}, {"dep": [_row(1), _row(2)]}, _local(8))
    assert new == 2 and merged["1"]["first"] == merged["1"]["seen"]
    merged, new = deals.merge(merged, {"nu": [_row(1, price=190_000)]}, _local(10))
    assert new == 0 and merged["1"]["cat"] == "dep" and merged["1"]["price"] == 190_000
    assert merged["1"]["first"] < merged["1"]["seen"]
    bot.repo.set_state(deals.POOL_KEY, json.dumps(merged))
    assert deals.current_deals(bot.repo, _local(13))[0] == {}, "quá 2 giờ 30 không thấy lại: không gửi"
    by_cat, latest = deals.current_deals(bot.repo, _local(13), deals.FEED_FRESH)
    assert [d["item_id"] for d in by_cat["dep"]] == [1, 2] and deals._clock(latest) == "10:00", "rẻ nhất trước"
    deals.set_removed(bot.repo, 1, True)
    assert [d["item_id"] for d in deals.current_deals(bot.repo, _local(13), deals.FEED_FRESH)[0]["dep"]] == [2]
    merged, _new = deals.merge(merged, {}, _local(9, day=22))
    assert list(merged) == ["1"], "món 2 không thấy lại 24 giờ thì bỏ"


def test_nhuong_tin_nhac_sale(tmp_path):
    bot, _admin = _ready(tmp_path)
    deals.toggle_category(bot.repo, USER, "dep")
    bot.repo.set_state(engagement.ENABLED_KEY, "1")
    evening = _local(19, 0, day=10).replace(month=11)
    _stock(bot, {"dep": [_row(1)]}, evening)
    assert deals.send_round(bot.repo, evening) == 0, "tối 10/11 có nhắc sale 11.11 lúc 20:30"


def test_man_admin_deal_hoi(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert "c:dl:home" in [d for row in _callback(bot, ADMIN, "c:eg:home").inline_keyboard for _l, d in row]
    _callback(bot, ADMIN, "c:dl:on")
    deals.toggle_category(bot.repo, USER, "dep")
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "Chưa quét lượt nào" in home.text and "Món đang hời" not in home.text
    now = datetime.now(timezone.utc)
    _stock(bot, {"dep": [dict(_row(1), name="Kem A")]}, now)
    bot.repo.set_state(deals.SCAN_KEY, json.dumps({"hour": "x", "status": "done", "at": "2026-10-21T07:00:00Z",
                                                   "found": 1, "new": 1, "sent": 1}))
    home = _callback(bot, ADMIN, "c:dl:home")
    assert "Kem A: 200.000đ (thường 250.000đ, −20%)" in home.text and "💄 Làm đẹp 1" in home.text
    assert "Lượt quét gần nhất 14:00: ✅ Xong · 1 món hời · 1 món mới · gửi 1 tin" in home.text
    after = _callback(bot, ADMIN, "c:dl:rm:1")
    assert deals.removed_items(bot.repo) == {1} and "Kem A (đã bỏ)" in after.text
    assert "c:dl:back:1" in [d for row in after.inline_keyboard for _l, d in row]
    _callback(bot, ADMIN, "c:dl:back:1")
    assert deals.removed_items(bot.repo) == set()
    assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:dl:skip:trua").text, "nút lượt trưa / tối cũ"
    bot.repo.set_state(deals.SCAN_KEY, json.dumps({"status": "error", "error": "market_http_429",
                                                   "at": "2026-10-21T08:00:00Z"}))
    assert "15:00: 🔴 Lỗi lấy dữ liệu (market_http_429), giờ sau quét lại" in _callback(bot, ADMIN, "c:dl:home").text
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "Deal hời: bật" in history and "bỏ món 1" in history and "lấy lại món 1" in history

