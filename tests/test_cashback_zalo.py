"""PLAN-082: kênh Zalo dùng chung lõi với Telegram qua ID nội bộ âm."""

from __future__ import annotations

from cashback_bot import zalo_api
from cashback_bot.admin_notify import _who
from cashback_bot.messages import HUONGDAN, BotReply
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.telegram_api import TelegramDeliveryError
from cashback_bot.zalo_bot import ZaloChannel, ZaloSender, ZaloStore
from cashback_bot.zalo_render import LINK_CARD, MAX_LEN, flatten, render
from tests.test_cashback_bot import NOW, FakeClient, payload, service

ZALO_ID = "f06e3b4f5605bf5be614"


class FakeZalo:
    def __init__(self, fail: list[TelegramDeliveryError] | None = None):
        self.sent: list[tuple[str, str, list]] = []
        self.fail = list(fail or [])
        self.typing = 0

    def send_message(self, chat_id, text, styles=None):
        if self.fail:
            raise self.fail.pop(0)
        self.sent.append((chat_id, text, styles or []))
        return "m"

    def send_chat_action(self, chat_id, action="typing"):
        self.typing += 1


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, html, **kwargs):
        self.sent.append(chat_id)
        return 1


def _update(text: str | None, message_id: str = "m1", event: str = "message.text.received", sender: str = ZALO_ID):
    message = {"chat": {"id": sender, "chat_type": "PRIVATE"}, "message_id": message_id,
               "from": {"id": sender, "is_bot": False, "display_name": "Tuan"}}
    if text is not None:
        message["text"] = text
    return {"message": message, "event_name": event}


def _channel(tmp_path, client=None, zalo=None):
    bot = service(tmp_path, client or FakeClient(payload()), customer_access_enabled=True)
    zalo = zalo or FakeZalo()
    return bot, ZaloChannel(bot, ZaloStore(bot.repo), zalo), zalo


def _texts(zalo) -> str:
    return "\n".join(text for _chat, text, _styles in zalo.sent)


def test_gui_link_tao_link_affiliate_gan_id_am(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("https://s.shopee.vn/abc123"), now=NOW)
    with bot.repo.connect() as conn:
        link = conn.execute("SELECT telegram_user_id, telegram_update_id, sub_id FROM link_requests").fetchone()
    assert link["telegram_user_id"] == -1 and link["telegram_update_id"] < 0 and link["sub_id"]
    text = _texts(zalo)
    assert "Chào bạn" in text and "bot tự động" in text, "tin đầu tiên báo đây là bot tự động"
    assert f"sub_id={link['sub_id']}" in text and "🛒 Mua trên Shopee: https://" in text, "link mua là URL trần"
    assert "<b>" not in text and "&amp;" not in text
    assert all(chat == ZALO_ID for chat, _t, _s in zalo.sent) and zalo.typing == 1


def test_zalo_gui_lai_cung_message_id_khong_tao_link_moi(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("https://s.shopee.vn/abc123"), now=NOW)
    sent = len(zalo.sent)
    channel.handle(_update("https://s.shopee.vn/abc123"), now=NOW)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 1
    assert len(zalo.sent) == sent


def test_hai_khach_zalo_hai_id_am_khac_nhau_chao_mot_lan(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("hd", "m1"), now=NOW)
    channel.handle(_update("hd", "m2"), now=NOW)
    channel.handle(_update("hd", "m3", sender="aaaa"), now=NOW)
    with bot.repo.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT internal_user_id FROM channel_identities ORDER BY created_at, internal_user_id DESC")]
    assert sorted(ids) == [-2, -1]
    assert _texts(zalo).count("Chào bạn") == 2


def test_the_xem_truoc_tra_huong_dan_bam_x(tmp_path):
    _bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update(None, event="message.unsupported.received"), now=NOW)
    assert "bấm dấu ✕" in _texts(zalo) and "s.shopee.vn/abc123" in _texts(zalo)


def test_lenh_go_tat_va_huong_dan_co_meo_zalo(tmp_path):
    _bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("HD"), now=NOW)
    assert "Trên Zalo" in _texts(zalo)


def test_go_so_chay_dung_nut_va_so_sai_bao_het_han(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("menu", "m1"), now=NOW)
    menu = channel.store.menu(-1, NOW)
    assert menu and all(item.startswith("u:") for item in menu)
    assert "Gõ số để chọn:" in _texts(zalo) and "1 · " in _texts(zalo)
    target = menu.index("u:p:guide") + 1
    zalo.sent.clear()
    channel.handle(_update(str(target), "m2"), now=NOW)
    assert flatten(HUONGDAN)[0].splitlines()[0] in _texts(zalo), "số đó là nút Hướng dẫn"
    zalo.sent.clear()
    channel.handle(_update("99", "m3"), now=NOW)
    assert "hết hạn" in _texts(zalo)


def test_loi_mang_luu_cau_tra_loi_gui_lai_khong_chay_lai(tmp_path):
    zalo = FakeZalo(fail=[TelegramDeliveryError("ambiguous")])
    bot, channel, zalo = _channel(tmp_path, zalo=zalo)
    channel.handle(_update("https://s.shopee.vn/abc123"), now=NOW)
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT status, attempt_count, next_retry_at FROM zalo_inbox").fetchone()
    assert row["status"] == "retry" and zalo.sent == []
    client_calls = bot.client.calls
    channel.retry_due(now=NOW.replace(hour=23))
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT status FROM zalo_inbox").fetchone()[0] == "replied"
        assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 1
    assert bot.client.calls == client_calls, "gửi lại câu đã lưu, không gọi lại nguồn giá"
    assert "sub_id=" in _texts(zalo)


def test_loi_vinh_vien_danh_dau_failed(tmp_path):
    bot, channel, _zalo = _channel(tmp_path, zalo=FakeZalo(fail=[TelegramDeliveryError("permanent", status_code=403)]))
    channel.handle(_update("hd"), now=NOW)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT status FROM zalo_inbox").fetchone()[0] == "failed"


def test_tin_khach_zalo_khong_di_qua_telegram_va_nguoc_lai(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("hd"), now=NOW)
    bot.repo.upsert_user(111, "tg")
    bot.repo.enqueue_admin_event("support:z", "SUPPORT_CUSTOMER", -1, "<b>Trả lời</b> hỗ trợ &amp; cảm ơn")
    bot.repo.enqueue_admin_event("support:t", "SUPPORT_CUSTOMER", 111, "Trả lời Telegram")
    telegram = FakeTelegram()
    Dispatcher(bot.repo, telegram, False, None, False).flush()
    assert telegram.sent == [111]
    zalo.sent.clear()
    Dispatcher(bot.repo, ZaloSender(zalo, channel.store), False, None, False, channel="zalo").flush()
    assert [chat for chat, _t, _s in zalo.sent] == [ZALO_ID]
    assert zalo.sent[0][1] == "Trả lời hỗ trợ & cảm ơn"
    with bot.repo.connect() as conn:
        statuses = dict(conn.execute("SELECT event_key, status FROM admin_notifications WHERE audience = 'customer'"))
    assert statuses == {"support:z": "sent", "support:t": "sent"}


def test_render_style_utf16_link_va_cat_tin():
    text, styles = flatten('🎉 <b>Đậm</b> &amp; <a href="https://x.vn/a">bấm</a> <code>mã</code>')
    assert text == "🎉 Đậm & bấm: https://x.vn/a mã"
    assert styles == [(3, 3, "b")], "emoji chiếm 2 đơn vị UTF-16"
    messages, menu = render(BotReply("dòng\n" * 900, inline_keyboard=((("📦 Đơn", "u:p:orders"), ("Admin", "c:x")),)))
    assert len(messages) > 1 and all(len(m.text.encode("utf-16-le")) // 2 <= MAX_LEN for m in messages)
    assert menu == ("u:p:orders",), "chỉ nút của khách thành số"
    assert render(BotReply("", toast="Đã lưu"))[0][0].text == "Đã lưu"
    assert render(BotReply(LINK_CARD))[0][0].styles


def test_admin_thay_khach_zalo_dang_zalo_so():
    assert _who(-3, None) == "Zalo #3" and _who(111, "tg") == "@tg"


def test_zalo_api_tu_choi_dinh_dang_thi_gui_chu_thuan(monkeypatch):
    bodies = []

    class Response:
        def __init__(self, ok):
            self.status_code = 200
            self._ok = ok

        def json(self):
            return {"ok": True, "result": {"message_id": "x"}} if self._ok else {"ok": False, "error_code": 400}

    def post(url, json=None, timeout=None):
        bodies.append(json)
        return Response("text_styles" not in json)

    monkeypatch.setattr(zalo_api.requests, "post", post)
    assert zalo_api.ZaloApi("1:t").send_message("c", "chào", [{"start": 0, "len": 4, "st": ["b"]}]) == "x"
    assert "text_styles" in bodies[0] and "text_styles" not in bodies[1] and len(bodies) == 2
