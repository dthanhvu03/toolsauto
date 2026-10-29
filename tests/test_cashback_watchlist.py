"""PLAN-103: theo dõi giá món khách chọn (🔔 trên thẻ link, có giảm là báo, giờ kiểm riêng). SQLite tạm, không gọi
AddLiveTag hay Telegram."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from cashback_bot import price_watch, watchlist
from cashback_bot.admin_engagement import EngagementAdmin
from cashback_bot.price_watch import PricePoint, PriceWatchError
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_zalo import _channel, _update

USER = 111
NOW = datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc)  # 15:08 giờ VN
LINK = "https://shopee.vn/product/9/8"


def _fresh(client: FakeClient, at: datetime, price: int) -> None:
    """Giá thật (product-data) lúc `at`."""
    client.payload = payload(last_update=(at - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"), price=price)


class FakeHistory:
    def __init__(self, price: int | None = None, error: Exception | None = None):
        self.price = price
        self.error = error
        self.asked: list[list[int]] = []

    def latest(self, item_ids):
        self.asked.append(list(item_ids))
        if self.error:
            raise self.error
        return {} if self.price is None else {8: PricePoint(self.price, False, None)}


def _bot(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    return bot, client


_presses = iter(range(1, 10_000))


def _press(bot, data: str, user: int = USER):
    update = {"callback_query": {"id": f"q{next(_presses)}", "from": {"id": user}, "data": data,
                                 "message": {"message_id": 5, "chat": {"id": user, "type": "private"}}}}
    return bot.handle_update(update)[1]


def _act(bot, data: str, now: datetime = NOW):
    """Nút u:pw:* với giờ cố định (đường qua service dùng giờ thật)."""
    return watchlist.action(bot.repo, USER, data, now)


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


def _card(bot, update_id: int = 1):
    return bot.handle_text(USER, "u", LINK, update_id=update_id, now=NOW)


def _watch(bot):
    card = _card(bot)
    [add] = [d for d in _buttons(card) if d.startswith(watchlist.ADD)]
    return card, _act(bot, add)


def _rows(bot, sql: str, *args):
    with bot.repo.connect() as conn:
        return conn.execute(sql, args).fetchall()


def _alerts(bot) -> list:
    return _rows(bot, "SELECT * FROM admin_notifications WHERE event_type = 'PRICE_WATCH' ORDER BY id")


def test_the_link_co_nut_bat_theo_doi_va_khong_sua_de_the(tmp_path):
    bot, _client = _bot(tmp_path)
    card = _card(bot)
    sub_id = _rows(bot, "SELECT sub_id FROM link_requests")[0]["sub_id"]
    assert _buttons(card)[0] == f"u:pw:a:{sub_id}" and card.button_url, "🔔 ngay dưới nút mua"
    update = {"callback_query": {"id": "q-add", "from": {"id": USER}, "data": f"u:pw:a:{sub_id}",
                                 "message": {"message_id": 5, "chat": {"id": USER, "type": "private"}}}}
    reply = bot.handle_update(update)[1]
    assert reply.edit_message_id is None, "màn theo dõi là tin mới, thẻ link ở lại"
    assert "Đang theo dõi giá" in reply.text and "250.000đ" in reply.text and "mỗi giờ 7:00–21:00" in reply.text
    [row] = _rows(bot, "SELECT * FROM price_watches")
    assert (row["telegram_user_id"], row["item_id"], row["start_price_vnd"], row["last_price_vnd"]) == (
        USER, 8, 250_000, 250_000)
    created, expires = (datetime.strptime(row[k], "%Y-%m-%dT%H:%M:%SZ") for k in ("created_at", "expires_at"))
    assert expires - created == timedelta(days=30)
    _press(bot, f"u:pw:a:{sub_id}")
    assert len(_rows(bot, "SELECT * FROM price_watches")) == 1, "bấm lại không thêm món"
    again = bot.handle_text(USER, "u", LINK, update_id=1, now=NOW)  # Telegram gửi lại cùng update
    assert f"u:pw:a:{sub_id}" in _buttons(again)
    assert watchlist.start(bot.repo, 222, sub_id, NOW) == (None, "no_link"), "không bật được link của khách khác"


def test_luot_chung_co_giam_la_bao_gia_len_roi_giam_lai_van_bao(tmp_path):
    bot, client = _bot(tmp_path)
    _watch(bot)
    at = NOW + timedelta(hours=1)
    _fresh(client, at, 240_000)
    assert watchlist.run_default(bot.repo, bot, FakeHistory(240_000), at) == {"checked": 1, "sent": 1}
    [alert] = _alerts(bot)
    assert alert["chat_id"] == USER and alert["category"] == "price_watch" and alert["audience"] == "customer"
    assert "<s>250.000đ</s> → <b>240.000đ</b> (−4%)" in alert["message_html"]
    assert "Hoàn dự kiến theo giá mới" in alert["message_html"]
    keyboard = json.loads(alert["reply_markup_json"])["inline_keyboard"]
    link = _rows(bot, "SELECT affiliate_url FROM link_requests")[0][0]
    assert keyboard[0] == [{"text": "🛒 Mua trên Shopee", "url": link}], "link cũ, cùng sub_id"
    assert keyboard[1][0]["callback_data"].startswith("u:pw:x:")
    # Không giảm thêm: không báo.
    assert watchlist.run_default(bot.repo, bot, FakeHistory(240_000), at + timedelta(hours=1))["sent"] == 0
    # Giá lên: ghi giá mới làm mốc, không báo.
    watchlist.run_default(bot.repo, bot, FakeHistory(260_000), at + timedelta(hours=2))
    assert _rows(bot, "SELECT last_price_vnd FROM price_watches")[0][0] == 260_000
    # Giảm lại trong 6 giờ kể từ tin trước: chờ.
    _fresh(client, at + timedelta(hours=3), 255_000)
    assert watchlist.run_default(bot.repo, bot, FakeHistory(255_000), at + timedelta(hours=3))["sent"] == 0
    later = at + timedelta(hours=6)
    _fresh(client, later, 255_000)
    assert watchlist.run_default(bot.repo, bot, FakeHistory(255_000), later)["sent"] == 1
    assert "<s>260.000đ</s> → <b>255.000đ</b>" in _alerts(bot)[-1]["message_html"]


def test_lich_su_bao_re_ma_gia_that_khong_re_thi_khong_bao(tmp_path):
    bot, client = _bot(tmp_path)
    _watch(bot)
    at = NOW + timedelta(hours=1)
    _fresh(client, at, 250_000)
    calls = client.calls
    assert watchlist.run_default(bot.repo, bot, FakeHistory(200_000), at)["sent"] == 0
    assert client.calls == calls + 1, "lịch sử giá báo rẻ thì đọc giá thật một lần"
    assert not _alerts(bot)
    watchlist.run_default(bot.repo, bot, FakeHistory(None), at)
    assert client.calls == calls + 1, "không có giá lịch sử thì không đọc giá thật"


def test_tick_moi_gio_mot_luot_trong_7_21_loi_chi_ghi_trang_thai(tmp_path):
    bot, client = _bot(tmp_path)
    _watch(bot)
    night = datetime(2026, 10, 21, 16, 0, tzinfo=timezone.utc)  # 23:00 giờ VN
    assert watchlist.tick(bot.repo, bot, night, FakeHistory(240_000)) is None
    at = NOW + timedelta(hours=1)
    _fresh(client, at, 240_000)
    thread = watchlist.tick(bot.repo, bot, at, FakeHistory(240_000))
    thread.join(5)
    assert watchlist.scan_record(bot.repo) == {"hour": "2026-10-21T16", "at": "2026-10-21T09:08:00Z",
                                               "status": "done", "checked": 1, "sent": 1}
    assert watchlist.tick(bot.repo, bot, at + timedelta(minutes=20), FakeHistory(230_000)) is None, "một lượt / giờ"
    failing = watchlist.tick(bot.repo, bot, at + timedelta(hours=1), FakeHistory(error=PriceWatchError("http_429")))
    failing.join(5)
    assert watchlist.scan_record(bot.repo)["status"] == "error"
    bot.repo.set_state(watchlist.ENABLED_KEY, "0")
    assert watchlist.tick(bot.repo, bot, at + timedelta(hours=2), FakeHistory(1)) is None


def test_doc_gio_kiem():
    assert watchlist.parse_times("12h 20h30") == (["12:00", "20:30"], "")
    assert watchlist.parse_times("7:15, 21g") == (["07:15", "21:00"], "")
    assert watchlist.parse_times("12 giờ") == (["12:00"], "")
    assert watchlist.parse_times("Mặc định") == ([], "")
    assert watchlist.parse_times("abc") == (None, "format")
    assert watchlist.parse_times("25h") == (None, "format")
    assert watchlist.parse_times("5h") == (None, "range")
    assert watchlist.parse_times("8h 10h 12h 14h 16h") == (None, "many")


def test_gio_rieng_toi_gio_thi_doc_gia_that_tre_qua_30_phut_thi_bo(tmp_path):
    bot, client = _bot(tmp_path)
    _card, item = _watch(bot)
    watch_id = _rows(bot, "SELECT id FROM price_watches")[0]["id"]
    prompt = _act(bot, f"u:pw:t:{watch_id}")
    assert "Đặt giờ kiểm giá" in prompt.text
    wrong = bot.handle_text(USER, "u", "chiều nay", update_id=2, now=NOW)
    assert "chưa đọc được giờ" in wrong.text, "gõ sai thì vẫn chờ, hướng dẫn lại"
    saved = bot.handle_text(USER, "u", "12h 20h30", update_id=3, now=NOW)
    assert "Bot sẽ kiểm giá lúc 12h, 20h30 mỗi ngày" in saved.text
    assert _rows(bot, "SELECT check_times FROM price_watches")[0][0] == "12:00,20:30"
    history = FakeHistory(1)
    assert watchlist.run_default(bot.repo, bot, history, NOW + timedelta(hours=1)) == {"checked": 0, "sent": 0}
    assert history.asked == [], "món có giờ riêng không vào lượt chung"
    noon = datetime(2026, 10, 22, 5, 10, tzinfo=timezone.utc)  # 12:10 giờ VN hôm sau
    _fresh(client, noon, 245_000)
    assert watchlist.run_slots(bot.repo, bot, noon) == 1
    assert watchlist.run_slots(bot.repo, bot, noon + timedelta(minutes=10)) == 0, "mỗi giờ riêng một lượt"
    _fresh(client, noon, 200_000)
    calls = client.calls
    assert watchlist.run_slots(bot.repo, bot, datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)) == 0
    assert client.calls == calls, "tắt quá 30 phút sau 12:00 thì bỏ, không kiểm bù"
    evening = datetime(2026, 10, 22, 13, 35, tzinfo=timezone.utc)  # 20:35
    _fresh(client, evening, 200_000)
    assert watchlist.tick(bot.repo, bot, evening.replace(hour=15), FakeHistory(1)) is None, "22:00 không có lượt"
    thread = watchlist.tick(bot.repo, bot, evening, FakeHistory(1))
    thread.join(5)
    assert len(_alerts(bot)) == 2
    back = _act(bot, f"u:pw:d:{watch_id}")
    assert "mỗi giờ 7:00–21:00" in back.text and _rows(bot, "SELECT check_times FROM price_watches")[0][0] is None


def test_dan_link_luc_dang_cho_gio_thi_tao_link_nhu_thuong(tmp_path):
    bot, _client = _bot(tmp_path)
    _watch(bot)
    watch_id = _rows(bot, "SELECT id FROM price_watches")[0]["id"]
    _act(bot, f"u:pw:t:{watch_id}")
    card = bot.handle_text(USER, "u", LINK, update_id=7, now=NOW)
    assert card.button_url and "Đặt giờ kiểm" not in card.text
    assert watchlist.waiting(bot.repo, USER, NOW) is None
    _act(bot, f"u:pw:t:{watch_id}")
    _press(bot, "u:p:home")
    assert watchlist.waiting(bot.repo, USER, NOW) is None, "bấm nút khác thì bỏ chờ"


def test_ngung_het_han_va_toi_da_10_mon(tmp_path):
    bot, client = _bot(tmp_path)
    _watch(bot)
    watch_id = _rows(bot, "SELECT id FROM price_watches")[0]["id"]
    listing = bot.handle_text(USER, "u", "/theodoi", update_id=9, now=NOW)
    assert "Món đang theo dõi giá" in listing.text and f"u:pw:i:{watch_id}" in _buttons(listing)
    stopped = _act(bot, f"u:pw:x:{watch_id}")
    assert "Đã ngừng theo dõi" in stopped.text and "Bạn chưa theo dõi món nào" in stopped.text
    _fresh(client, NOW + timedelta(hours=1), 1_000)
    assert watchlist.run_default(bot.repo, bot, FakeHistory(1_000), NOW + timedelta(hours=1))["checked"] == 0
    with bot.repo.connect() as conn:
        for item in range(100, 110):
            conn.execute("INSERT INTO price_watches (telegram_user_id, link_id, item_id, shop_id, product_name, "
                         "start_price_vnd, last_price_vnd, created_at, expires_at) VALUES (?, 1, ?, 9, 'x', 1, 1, ?, ?)",
                         (USER, item, "2026-10-21T08:00:00Z", "2026-11-20T08:00:00Z"))
    sub_id = _rows(bot, "SELECT sub_id FROM link_requests")[0]["sub_id"]
    full = _act(bot, f"u:pw:a:{sub_id}")
    assert "tối đa" in full.text and len(_rows(bot, "SELECT * FROM price_watches WHERE stopped_at IS NULL")) == 10
    late = NOW + timedelta(days=31)
    assert watchlist.run_default(bot.repo, bot, FakeHistory(1), late)["checked"] == 0, "hết 30 ngày thì thôi"


def test_che_do_tu_dong_bo_mon_khach_dang_theo_doi(tmp_path):
    bot, _client = _bot(tmp_path)
    _card(bot)
    later = NOW + timedelta(days=1)
    with bot.repo.connect() as conn:
        assert len(price_watch.candidates(conn, later)) == 1
    sub_id = _rows(bot, "SELECT sub_id FROM link_requests")[0]["sub_id"]
    _act(bot, f"u:pw:a:{sub_id}")
    with bot.repo.connect() as conn:
        assert price_watch.candidates(conn, later) == [], "không nhắn trùng"


def test_admin_tat_thi_the_khong_co_nut_va_khong_kiem(tmp_path):
    bot, _client = _bot(tmp_path)
    admin = EngagementAdmin(bot.repo)
    home = admin.route(1, "c:eg:home", NOW)
    assert "🔔 Theo dõi giá</b>: 🟢 Đang bật · 0 món đang theo dõi" in home.text
    assert "c:eg:pw:off" in _buttons(home)
    off = admin.route(1, "c:eg:pw:off", NOW)
    assert "Đã tắt theo dõi giá" in off.text
    card = _card(bot)
    assert not [d for d in _buttons(card) if d.startswith("u:pw:")]
    assert _press(bot, "u:pw:l").toast == watchlist.OFF_TEXT
    assert "Món đang theo dõi" not in bot.handle_text(USER, "u", "/theodoi", update_id=8, now=NOW).text


def test_zalo_chon_so_bat_theo_doi_go_gio_va_lenh_theodoi(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("https://shopee.vn/product/9/8", "m1"), now=NOW)
    assert "1 · 🔔 Báo khi giảm giá" in zalo.sent[-1][1]
    channel.handle(_update("1", "m2"), now=NOW)
    assert "Đang theo dõi giá" in zalo.sent[-1][1]
    [row] = _rows(bot, "SELECT * FROM price_watches")
    assert row["telegram_user_id"] < 0, "khách Zalo có id âm"
    channel.handle(_update("1", "m3"), now=NOW)  # 1 · ⏰ Đặt giờ kiểm
    assert "Đặt giờ kiểm giá" in zalo.sent[-1][1]
    channel.handle(_update("12h 20h", "m4"), now=NOW)
    assert "Bot sẽ kiểm giá lúc 12h, 20h mỗi ngày" in zalo.sent[-1][1], "giờ có chữ h không bị hiểu là số chọn mục"
    channel.handle(_update("theodoi", "m5"), now=NOW)
    assert "Món đang theo dõi giá" in zalo.sent[-1][1]
