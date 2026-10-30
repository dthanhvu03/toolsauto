"""PLAN-104: báo mã giảm giá AddLiveTag qua kênh trung gian. SQLite tạm, không gọi AddLiveTag, Shopee hay Telegram."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from cashback_bot import voucher
from cashback_bot.admin_engagement import VOUCHER_HOME, EngagementAdmin, history_line
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_zalo import _channel, _update

USER, OTHER = 111, 222
CHANNEL = -1001234
NOW = datetime(2026, 10, 30, 7, 0, tzinfo=timezone.utc)  # 14:00 giờ VN
DEFAULT = "🟢 14:00: Mã Instagram METAPARIGDOCT2211 đã dùng 45% - Giảm 22% - Tối đa 300K - Đơn tối thiểu 0"
VOUCHER_URL = "https://shopee.vn/voucher/details?evcode=TUVUQVBBUklHRE9DVDIyMTE%3D"
_ids = iter(range(1, 10_000))


def _client() -> FakeClient:
    """Dữ liệu sản phẩm mới so với NOW: link tạo được (khách «đã tạo link»)."""
    return FakeClient(payload(last_update=(NOW - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")))


def _bot(tmp_path):
    bot = service(tmp_path, _client())
    for user in (USER, OTHER):
        bot.handle_text(user, "u", "/start", update_id=next(_ids), now=NOW)
    return bot


def _post(text: str, message_id: int = 1, chat: int = CHANNEL, **extra) -> dict:
    return {"chat": {"id": chat, "type": "channel", "title": "Kênh mã"}, "message_id": message_id, "text": text, **extra}


def _bind(bot) -> None:
    voucher.handle_post(bot.repo, _post("xin chào"), False, NOW)
    admin = EngagementAdmin(bot.repo)
    screen = admin.route(1, VOUCHER_HOME, NOW)
    [bind] = [data for row in screen.inline_keyboard for _label, data in row if data.startswith("c:eg:vc:bind:")]
    assert "Đã gắn kênh" in admin.route(1, bind, NOW).text


def _rows(bot, sql: str, *args):
    with bot.repo.connect() as conn:
        return conn.execute(sql, args).fetchall()


def _sent(bot) -> list:
    return _rows(bot, "SELECT * FROM admin_notifications WHERE event_type = 'VOUCHER' ORDER BY id")


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


def test_doc_mau_mac_dinh_mau_nhan_tin_het_ma_va_tin_la():
    found = voucher.parse(DEFAULT)
    assert found == voucher.Voucher(code="METAPARIGDOCT2211", name="Mã Instagram", discount="22%",
                                    max_discount="300K", min_spend="0", used=45)
    labeled = voucher.parse("🎟 Mã tay\nMã: freeship50\nGiảm: 50K\nĐơn từ: 99K\nĐã dùng: 10%")
    assert (labeled.code, labeled.discount, labeled.min_spend, labeled.used) == ("FREESHIP50", "50K", "99K", 10)
    out = voucher.parse("🔴 HẾT MÃ — Mã Instagram (METAPARIGDOCT2211)\n⏰ Hết lúc 15:02 · đã dùng 100%")
    assert out.out and out.code == "METAPARIGDOCT2211" and out.used is None
    assert voucher.parse(DEFAULT.replace("45%", "100%")).out
    assert voucher.parse("xin chào cả nhà") is None


def test_lay_link_shopee_tu_link_gan_chu_nut_va_link_tran():
    assert voucher.find_url({"text": "x", "entities": [{"type": "text_link", "url": VOUCHER_URL}]}) == VOUCHER_URL
    markup = {"inline_keyboard": [[{"text": "Lưu", "url": "https://s.shopee.vn/abc"}]]}
    assert voucher.find_url({"text": "x", "reply_markup": markup}) == "https://s.shopee.vn/abc"
    assert voucher.find_url({"text": f"lưu tại {VOUCHER_URL}."}) == VOUCHER_URL
    assert voucher.find_url({"text": "https://evil.example/shopee.vn/voucher"}) is None
    assert voucher.find_url({"text": "http://shopee.vn/voucher/x"}) is None, "chỉ nhận https"


def test_kenh_la_chi_ghi_ten_admin_gan_va_go_kenh(tmp_path):
    bot = _bot(tmp_path)
    bot.repo.set_state(f"{voucher.ON_PREFIX}{USER}", "1")
    assert bot.handle_update({"update_id": 9, "channel_post": _post(DEFAULT)}) is None
    assert not _rows(bot, "SELECT * FROM voucher_posts") and not _sent(bot), "kênh chưa gắn: không đọc mã"
    assert voucher.seen_channel(bot.repo)["id"] == CHANNEL
    assert not voucher.ready(bot.repo)
    admin = EngagementAdmin(bot.repo)
    assert "c:eg:vc:home" in _buttons(admin.route(1, "c:eg:home", NOW))
    screen = admin.route(1, VOUCHER_HOME, NOW)
    assert "Kênh mã" in screen.text and f"c:eg:vc:bind:{CHANNEL}" in _buttons(screen)
    assert "không còn hiệu lực" in admin.route(1, "c:eg:vc:bind:-999", NOW).text
    assert voucher.channel(bot.repo) is None
    admin.route(1, f"c:eg:vc:bind:{CHANNEL}", NOW)
    assert voucher.channel(bot.repo) == CHANNEL and voucher.ready(bot.repo)
    voucher.handle_post(bot.repo, _post(DEFAULT, 2, chat=-1009999), False, NOW)
    assert not _rows(bot, "SELECT * FROM voucher_posts"), "kênh khác kênh đã gắn: không đọc"
    assert "Đã gỡ kênh" in admin.route(1, "c:eg:vc:unbind", NOW).text
    assert voucher.channel(bot.repo) is None
    assert history_line({}, {"voucher_channel": CHANNEL, "title": "Kênh mã"}) == "Báo mã: gắn kênh Kênh mã"
    assert history_line({}, {"voucher_channel": None}) == "Báo mã: gỡ kênh"
    assert history_line({}, {"voucher": False}) == "Báo mã giảm giá: tắt"


def test_mac_dinh_gui_moi_khach_da_tao_link_tru_khach_tat_hay_chan(tmp_path):
    bot = _bot(tmp_path)
    _bind(bot)
    third = 333
    for update_id, user in enumerate((USER, OTHER, third), 100):
        bot.handle_text(user, "u", "https://shopee.vn/product/9/8", update_id=update_id, now=NOW)
    bot.repo.set_state(f"{voucher.ON_PREFIX}{third}", "0")
    with bot.repo.connect() as conn:
        conn.execute("UPDATE telegram_users SET notify_blocked_at = ? WHERE telegram_user_id = ?", ("x", OTHER))
        assert voucher.subscribers(conn, NOW) == [USER], "khách tạo link nhận mặc định; tắt báo mã hay chặn bot thì bỏ"
    post = _post(DEFAULT, 5, entities=[{"type": "text_link", "url": VOUCHER_URL, "offset": 0, "length": 2}])
    assert voucher.handle_post(bot.repo, post, False, NOW) == 1
    [row] = _sent(bot)
    assert row["chat_id"] == USER and row["category"] == "voucher"
    assert "METAPARIGDOCT2211" in row["message_html"] and "giảm 22% · tối đa 300K · đơn từ 0" in row["message_html"]
    assert "Đã dùng 45%" in row["message_html"] and "dán link món vào bot" in row["message_html"]
    keyboard = json.loads(row["reply_markup_json"])["inline_keyboard"]
    assert keyboard[0][0]["url"] == VOUCHER_URL
    assert [b["callback_data"] for b in keyboard[1]] == [voucher.OFF, voucher.LIST]
    [stored] = _rows(bot, "SELECT * FROM voucher_posts")
    assert stored["sent"] == 1 and stored["status"] == "live" and stored["url"] == VOUCHER_URL


def test_co_ma_la_gui_moi_gio_khong_gioi_han_so_tin(tmp_path):
    bot = _bot(tmp_path)
    _bind(bot)
    bot.repo.set_state(f"{voucher.ON_PREFIX}{USER}", "1")
    midnight = datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc)  # 0:00 giờ VN
    assert voucher.handle_post(bot.repo, _post(DEFAULT, 10), False, midnight) == 1, "0h nạp mã: gửi ngay"
    assert voucher.handle_post(bot.repo, _post(DEFAULT, 11), False, midnight + timedelta(hours=2)) == 1, "đợt mới cùng mã"
    for number, code in enumerate(("AAA111", "BBB222", "CCC333", "DDD444"), 13):
        voucher.handle_post(bot.repo, _post(DEFAULT.replace("METAPARIGDOCT2211", code), number), False, NOW)
    assert len(_sent(bot)) == 6, "không giới hạn số tin / ngày"


def test_sua_tin_cap_nhat_phan_tram_het_ma_va_khong_gui_lai(tmp_path):
    bot = _bot(tmp_path)
    _bind(bot)
    bot.repo.set_state(f"{voucher.ON_PREFIX}{USER}", "1")
    bot.handle_update({"update_id": 20, "channel_post": _post(DEFAULT, 30)})
    bot.handle_update({"update_id": 21, "edited_channel_post": _post(DEFAULT.replace("45%", "80%"), 30)})
    [row] = _rows(bot, "SELECT * FROM voucher_posts")
    assert row["used_percent"] == 80 and row["status"] == "live"
    assert len(_sent(bot)) <= 1, "sửa tin không gửi lại"
    voucher.handle_post(bot.repo, _post("🔴 HẾT MÃ — Mã Instagram (METAPARIGDOCT2211)", 31), False, NOW)
    assert _rows(bot, "SELECT status FROM voucher_posts WHERE message_id = 30")[0]["status"] == "out"
    with bot.repo.connect() as conn:
        assert voucher.live(conn, NOW) == []
    voucher.handle_post(bot.repo, _post("tin linh tinh", 32), False, NOW)
    assert bot.repo.get_state(voucher.SKIPPED_KEY) == "1"


def test_magiam_bat_tat_va_trang_chu(tmp_path):
    bot = _bot(tmp_path)
    assert "Mã giảm giá Shopee" not in bot.handle_text(USER, "u", "/magiam", update_id=next(_ids), now=NOW).text
    assert "u:vc:l" not in _buttons(bot.handle_text(USER, "u", "/start", update_id=next(_ids), now=NOW))
    _bind(bot)
    assert "u:vc:l" in _buttons(bot.handle_text(USER, "u", "/start", update_id=next(_ids), now=NOW))
    voucher.handle_post(bot.repo, _post(DEFAULT, 40, entities=[{"type": "text_link", "url": VOUCHER_URL}]), False, NOW)
    screen = voucher.list_reply(bot.repo, USER, NOW)
    assert "METAPARIGDOCT2211" in screen.text and "🟢 Đang bật" in screen.text, "mặc định nhận"
    assert screen.button_url == VOUCHER_URL and voucher.OFF in _buttons(screen)
    off = bot.handle_update({"callback_query": {"id": "q1", "from": {"id": USER}, "data": voucher.OFF,
                                                "message": {"message_id": 3, "chat": {"id": USER, "type": "private"}}}})
    assert "Đã tắt báo mã" in off[1].text and not voucher.is_on(bot.repo, USER) and voucher.ON in _buttons(off[1])
    on = voucher.action(bot.repo, USER, voucher.ON, NOW)
    assert "Đã bật" in on.text and voucher.is_on(bot.repo, USER)
    bot.repo.set_state(voucher.ENABLED_KEY, "0")
    assert voucher.action(bot.repo, USER, voucher.LIST, NOW).toast == voucher.OFF_TEXT
    assert "u:vc:l" not in _buttons(bot.handle_text(USER, "u", "/start", update_id=next(_ids), now=NOW))


def test_zalo_go_magiam_va_chon_so_bat(tmp_path):
    bot, channel, zalo = _channel(tmp_path, _client())
    channel.handle(_update("menu", "m0"), now=NOW)
    _bind(bot)
    channel.handle(_update("https://shopee.vn/product/9/8", "m1"), now=NOW)
    channel.handle(_update("magiam", "m2"), now=NOW)
    assert "Mã giảm giá Shopee" in zalo.sent[-1][1] and "1 · 🔕 Tắt báo mã" in zalo.sent[-1][1]
    assert voucher.handle_post(bot.repo, _post(DEFAULT, 50), False, NOW) == 1, "khách Zalo đã tạo link nhận mặc định"
    [row] = _sent(bot)
    assert row["chat_id"] < 0, "khách Zalo có id âm"
    channel.handle(_update("magiam", "m3"), now=NOW)
    channel.handle(_update("1", "m4"), now=NOW)
    assert "Đã tắt báo mã" in zalo.sent[-1][1]
    assert voucher.handle_post(bot.repo, _post(DEFAULT.replace("METAPARIGDOCT2211", "NEW111"), 51), False, NOW) == 0
