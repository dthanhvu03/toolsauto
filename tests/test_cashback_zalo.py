"""PLAN-082 / PLAN-083: kênh Zalo dùng chung lõi với Telegram qua ID nội bộ âm."""

from __future__ import annotations

import inspect
import json
import re
from datetime import datetime, timedelta, timezone

from cashback_bot import deals, messages, terms, zalo_api
from cashback_bot.admin_notify import _update_line, _user_line, _who
from cashback_bot.db import enqueue_event
from cashback_bot.messages import BotReply
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.poller import ZALO_DOWN_AFTER_SEC, ZALO_HEARTBEAT_KEY, _check_zalo_health
from cashback_bot.telegram_api import TelegramDeliveryError
from cashback_bot.terms_content import DRAFT_SECTIONS, DRAFT_TITLE
from cashback_bot.zalo_bot import ZaloChannel, ZaloSender, ZaloStore
from cashback_bot.zalo_render import (
    BUY_LEAD, ERROR_REPLY, FOOD_LEAD, LINK_CARD, MAX_LEN, PHRASES, flatten, render, zalo_wording,
)
from tests.test_cashback_bot import NOW, FakeClient, payload, service
from tests.test_cashback_wallet import _financially_ready, _order

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
    card, buy = zalo.sent[-2][1], zalo.sent[-1][1]
    assert "Đã tạo link hoàn tiền" in card and "sub_id=" not in card
    assert "Bấm link ở tin dưới" in card and "bên dưới" not in card, "Zalo không có nút: chỉ sang tin chứa link"
    assert buy.startswith(BUY_LEAD + "\nhttps://") and f"sub_id={link['sub_id']}" in buy, "link mua là tin riêng cuối"
    assert "Gõ số để chọn:" in buy, "danh sách số nằm cuối cùng"
    assert "<b>" not in text and "&amp;" not in text
    assert all(chat == ZALO_ID for chat, _t, _s in zalo.sent) and zalo.typing == 1
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT delivery_status FROM link_requests").fetchone()[0] == "sent"


def test_zalo_link_shopeefood_bao_sap_co_va_gui_link_dat_mon(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("https://spf.shopee.vn/906KKy82bs"), now=NOW)
    card, buy = zalo.sent[-2][1], zalo.sent[-1][1]
    assert "Hoàn tiền ShopeeFood sắp có" in card and "link ở tin dưới" in card and "nút" not in card
    assert buy.startswith(FOOD_LEAD + "\nhttps://s.shopee.vn/an_redir?") and "&sub_id=" in buy
    assert BUY_LEAD not in buy, "không ghi «sẽ không được hoàn» như link có hoàn"


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


def test_lenh_go_tat_va_trang_huong_dan_rieng_zalo(tmp_path):
    _bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("HD"), now=NOW)
    text = _texts(zalo)
    assert "Cách dùng trên Zalo" in text and "bấm dấu ✕" in text and "link 🛒 Mua trên Shopee" in text
    assert "nút" not in text.split("Cách dùng trên Zalo", 1)[1]


def test_go_so_chay_dung_nut_va_so_sai_bao_het_han(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("menu", "m1"), now=NOW)
    menu = channel.store.menu(-1, NOW)
    assert menu and all(item.startswith("u:") for item in menu)
    assert "Gõ số để chọn:" in _texts(zalo) and "1 · " in _texts(zalo)
    target = menu.index("u:p:guide") + 1
    zalo.sent.clear()
    channel.handle(_update(str(target), "m2"), now=NOW)
    assert "Cách dùng trên Zalo" in _texts(zalo), "số đó là nút Hướng dẫn"
    zalo.sent.clear()
    channel.handle(_update("99", "m3"), now=NOW)
    assert "Không có số 99" in _texts(zalo)
    zalo.sent.clear()
    channel.handle(_update("1", "m4"), now=NOW + timedelta(hours=1))
    assert "hết hạn" in _texts(zalo), "quá 30 phút thì danh sách hết hạn"


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
        assert tuple(conn.execute("SELECT COUNT(*), MAX(delivery_status) FROM link_requests").fetchone()) == (1, "sent")
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


def test_cau_chu_telegram_doi_sang_lenh_go_tat_zalo():
    assert zalo_wording("Gửi yêu cầu tại /hotro.") == "Gửi yêu cầu bằng cách gõ <b>hotro</b>."
    assert zalo_wording("Gõ /vi để xem số dư.") == "Gõ <b>vi</b> để xem số dư."
    assert zalo_wording("Mở /dieukien, đọc") == "Gõ <b>dieukien</b>, đọc"
    assert zalo_wording("xem /cachtinh.") == "xem bằng cách gõ <b>cachtinh</b>."
    assert zalo_wording("xem ở /dieukien.") == "xem bằng cách gõ <b>dieukien</b>."
    assert zalo_wording("https://shopee.vn/vi/hotro") == "https://shopee.vn/vi/hotro", "không đụng URL"
    assert zalo_wording(messages.INVALID_LINK).endswith("Gõ <b>hd</b> để xem cách lấy link.")


def test_cau_goc_can_doi_van_con_trong_messages():
    source = inspect.getsource(messages)
    missing = [old for old, _new in PHRASES if old not in source]
    assert missing == [], "câu Telegram đã đổi: cập nhật zalo_render.PHRASES"


def test_loi_xu_ly_tra_loi_xin_loi_va_bao_admin(tmp_path, monkeypatch):
    bot, channel, zalo = _channel(tmp_path)
    admin = _Admin()
    channel.admin_notifier = admin

    def boom(*args, **kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr(bot, "handle_text", boom)
    channel.handle(_update("don"), now=NOW)
    assert flatten(ERROR_REPLY)[0] in _texts(zalo)
    assert admin.failed and admin.failed[0]["error_type"] == "zalo_update_failed"
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT status FROM zalo_inbox").fetchone()[0] == "replied"


def test_bao_admin_khi_khach_zalo_thu_40(tmp_path):
    bot, channel, _zalo = _channel(tmp_path)
    admin = _Admin()
    channel.admin_notifier = admin
    for number in range(39):
        channel.store.identity(f"u{number}", None, NOW)
    channel.handle(_update("hd", sender="khach-40"), now=NOW)
    assert admin.capacity == [(40, 50)]


def test_nhip_song_zalo_bao_dung_mot_lan_va_bao_chay_lai(tmp_path):
    bot, _channel_, _zalo = _channel(tmp_path)
    admin = _Admin()
    _check_zalo_health(bot.repo, admin, now=1_000.0)
    assert admin.health == [], "chưa từng chạy Zalo thì không báo"
    bot.repo.set_state(ZALO_HEARTBEAT_KEY, "1000")
    _check_zalo_health(bot.repo, admin, now=1_000.0 + ZALO_DOWN_AFTER_SEC + 1)
    _check_zalo_health(bot.repo, admin, now=1_000.0 + ZALO_DOWN_AFTER_SEC + 400)
    assert admin.health == [True], "báo dừng một lần"
    bot.repo.set_state(ZALO_HEARTBEAT_KEY, "2000")
    _check_zalo_health(bot.repo, admin, now=2_400.0)
    assert admin.health == [True, False]


def test_admin_dong_chi_tiet_zalo():
    assert _user_line(-1) == "Zalo <code>#1</code>" and _update_line(-5) == "Tin Zalo <code>#5</code>"
    assert _user_line(111) == "User <code>111</code>" and _update_line(None) == "Update <code>-</code>"


def test_dong_y_dieu_khoan_qua_zalo_ghi_nguon_zalo_va_hien_xac_nhan(tmp_path):
    bot, channel, zalo = _channel(tmp_path)
    with bot.repo.connect() as conn:
        version = _publish_terms(conn)
    channel.handle(_update("dieukien", "m1"), now=NOW)
    menu = channel.store.menu(-1, NOW)
    assert "Gõ số của từng mục để đọc." in _texts(zalo)
    zalo.sent.clear()
    channel.handle(_update(str(menu.index(f"u:t:ok:{version}") + 1), "m2"), now=NOW)
    assert _texts(zalo).startswith("Đã ghi nhận bạn đồng ý điều khoản.")
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT telegram_user_id, acceptance_source FROM customer_terms_acceptances").fetchone()
    assert tuple(row) == (-1, "zalo_choice")


def test_cai_dat_thong_bao_go_so_de_bat_tat(tmp_path):
    _bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("thongbao"), now=NOW)
    assert "Gõ số để bật / tắt." in _texts(zalo) and "Bấm" not in _texts(zalo).split("Cài đặt thông báo", 1)[1]


def _publish_terms(conn) -> int:
    version_id = terms.create_draft(conn, "V1", DRAFT_TITLE, DRAFT_SECTIONS, "admin:test", NOW)
    terms.publish(conn, version_id, terms.get(conn, version_id).content_hash, "admin:test", NOW)
    return version_id


class _Admin:
    def __init__(self):
        self.failed, self.capacity, self.health = [], [], []

    def notify_request_failed(self, **kwargs):
        self.failed.append(kwargs)

    def notify_zalo_capacity(self, count, limit):
        self.capacity.append((count, limit))

    def notify_zalo_health(self, down, last_beat):
        self.health.append(down)

    def notify_new_user(self, *args):
        pass

    def notify_link_sent(self, update_id):
        pass


def test_dieu_khoan_mau_noi_ca_telegram_va_zalo():
    body = "\n".join(text for _key, _label, text in DRAFT_SECTIONS)
    assert body.count("Telegram hoặc Zalo") == 2
    assert "tài khoản Telegram," not in body and "tài khoản Telegram đã" not in body


# --- Ví trên Zalo (2026-10-26: trước khi mở ví, giữ luồng chạy tay bằng test) -------------------------


def _zalo_wallet(tmp_path, accepted: bool):
    """Khách Zalo -1 có 70.000đ rút được; `accepted`: đã đồng ý điều khoản chi trả."""
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("https://s.shopee.vn/abc123", message_id="w0"), now=NOW)
    with bot.repo.connect() as conn:
        sub = conn.execute("SELECT sub_id FROM link_requests").fetchone()[0]
    _financially_ready(bot, users=(-1,) if accepted else ())
    _order(bot, sub, status="COMPLETED", commission=100_000, complete="2026-09-01T10:00:00Z", cid="z1", approved=True)
    bot.wallet.set_enabled(True)
    bot.refresh_wallet(NOW + timedelta(days=60))
    step = iter(range(1, 100))

    def say(text: str) -> str:
        before = len(zalo.sent)
        channel.handle(_update(text, message_id=f"w{next(step)}"), now=NOW + timedelta(minutes=next(step)))
        return "\n".join(t for _c, t, _s in zalo.sent[before:])

    return bot, say


def _number(text: str, label: str) -> str:
    return re.search(rf"(\d+) · [^\n]*{label}", text).group(1)


def test_vi_tren_zalo_khai_tai_khoan_va_rut(tmp_path):
    bot, say = _zalo_wallet(tmp_path, accepted=True)
    wallet = say(_number(say("menu"), "Ví của tôi"))
    assert "Có thể rút: 70.000đ" in wallet and "Chưa khai tài khoản" in wallet
    banks = say(_number(wallet, "Tài khoản nhận tiền"))
    assert "Gõ số để chọn ngân hàng" in banks
    say(_number(banks, "Vietcombank"))
    saved = say("0123456789 NGUYEN VAN TUAN")
    assert "Đã lưu tài khoản Vietcombank ••••6789" in saved and "0123456789" not in saved
    confirm = say(_number(saved, "Rút 70.000đ"))
    assert "Xác nhận rút tiền" in confirm and "3–7 ngày làm việc" in confirm
    done = say(_number(confirm, "Xác nhận rút"))
    assert "Đã gửi yêu cầu rút" in done and "Hoan tien 000001" in done
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT telegram_user_id, amount_vnd, status FROM cashback_payouts").fetchone()
    assert tuple(row) == (-1, 70_000, "requested")


def test_vi_tren_zalo_chua_dong_y_dieu_khoan_thi_chua_rut(tmp_path):
    bot, say = _zalo_wallet(tmp_path, accepted=False)
    wallet = say(_number(say("menu"), "Ví của tôi"))
    banks = say(_number(wallet, "Tài khoản nhận tiền"))
    say(_number(banks, "Vietcombank"))
    saved = say("0123456789 NGUYEN VAN TUAN")
    reply = say(_number(saved, "Rút 70.000đ"))
    reply += say(_number(reply, "Xác nhận rút")) if "Xác nhận rút" in reply else ""
    assert "Cần đồng ý điều khoản chi trả" in reply and "/dieukien" not in reply, "Zalo không có lệnh /"
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0] == 0


# --- Rà soát câu chữ 2026-10-26 (đợt 3) -------------------------------------------------------------


def test_menu_zalo_khong_danh_so_hai_lan():
    reply = BotReply("x", inline_keyboard=((("1. Áo Polo · 10.500đ", "u:o:d:a"),), (("6. Quần · 5.000đ", "u:o:d:b"),)))
    text = render(reply)[0][-1].text
    assert "1 · Áo Polo · 10.500đ" in text and "2 · Quần" in text and "1. Áo" not in text


def test_cau_lenh_tren_zalo_dung_ngu_phap():
    for source in (messages.SUPPORT_CLOSED, messages.ORDERS_EMPTY, messages.WALLET_CLOSED):
        text = zalo_wording(source)
        assert "dùng gõ" not in text and "trong gõ" not in text and "/" not in text.replace("</b>", ""), text
    assert zalo_wording(messages.STALE_BUTTON) == "Lựa chọn này đã hết hạn. Gõ menu để mở trang chủ."


def test_man_bat_tat_tren_zalo_khong_co_o_xam_khong_lap():
    picked = messages.notify_settings_reply({"orders": True, "updates": False, "support": True, "wallet": True,
                                             "reminders": True}, True)
    text = render(picked)[0][0].text
    assert "⬜" not in text and text.count("Đơn mới được ghi nhận") == 1
    assert "1 · 📦 Đơn mới được ghi nhận ✅" in text and "2 · 🔄 Trạng thái đơn / hoa hồng thay đổi\n" in text
    assert "✅\n\n6 · 📦 Đơn hàng của tôi\n\n7 · Trang chủ" in text, "bật / tắt, mở màn khác, điều hướng: ba nhóm"
    assert "\n\n\n" not in text


def test_tin_deal_go_so_lay_nhieu_mon_va_doc_muon_van_dung_duoc(tmp_path):
    """Chủ bot 2026-10-28: gõ 1 lấy link xong, gõ 2 bị báo hết hạn; tin deal 20:08 đọc muộn cũng hết hạn sau 30 phút."""
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("hd", "m0"), now=NOW)
    bot.client.payload["productInfo"]["lastUpdate"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = dict(shop_id=9, price=200_000, usual=250_000, lowest_30d=True, cashback=3_000, rating=4.8, sold_30d=500)
    text, keyboard = deals.message_for(["dep"], {"dep": [dict(row, item_id=8, name="Kem A"),
                                                         dict(row, item_id=7, name="Kem B")]}, set())
    with bot.repo.connect() as conn:
        enqueue_event(conn, event_key="deals:x:-1", event_type="DEALS", chat_id=-1, message_html=text,
                      audience="customer", category="deal", reply_markup_json=json.dumps({"inline_keyboard": keyboard}))
    Dispatcher(bot.repo, ZaloSender(zalo, channel.store), False, None, False, channel="zalo").flush()
    deal_menu = channel.store.menu(-1, datetime.now(timezone.utc) + timedelta(hours=10))
    assert deal_menu == ("u:dl:9:8", "u:dl:9:7", "u:dc:home"), "tin bot tự gửi: danh sách số giữ một ngày"
    zalo.sent.clear()
    channel.handle(_update("1", "m1"), now=datetime.now(timezone.utc))
    buy = zalo.sent[-1][1]
    assert "Đã tạo link hoàn tiền" in _texts(zalo) and "1 · 🛒 Kem A" in buy and "2 · 🛒 Kem B" in buy
    assert channel.store.menu(-1, datetime.now(timezone.utc))[:3] == deal_menu, "giữ nguyên số của tin deal"
    assert len(channel.store.menu(-1, datetime.now(timezone.utc))) > 3, "nút riêng của tin link xếp sau"
    zalo.sent.clear()
    channel.handle(_update("2", "m2"), now=datetime.now(timezone.utc))
    assert "Đã tạo link hoàn tiền" in _texts(zalo) and "hết hạn" not in _texts(zalo)
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM link_requests WHERE link_status = 'created'").fetchone()[0] == 2


def test_ra_soat_zalo_chat_go_nham_so_va_trang_chu(tmp_path):
    """Rà soát Zalo 2026-10-28: tin chat không ăn suất link; gõ nhầm số không xoá danh sách; trang chủ liền khối."""
    bot, channel, zalo = _channel(tmp_path)
    for index, text in enumerate(["ok", "cảm ơn", "alo", "🙂", "0901234567", "hihi", "dạ", "vâng", "ừ", "ok nha"]):
        channel.handle(_update(text, f"c{index}"), now=NOW)
    assert "Mình là bot tự động" in zalo.sent[-1][1] and "gửi hơi nhiều link" not in _texts(zalo)
    channel.handle(_update("https://lazada.vn/products/i1.html", "c99"), now=NOW)
    assert "Chưa nhận ra link" in zalo.sent[-1][1], "tin có dáng link thì vẫn cảnh báo"
    zalo.sent.clear()
    channel.handle(_update("menu", "h1"), now=NOW)
    assert re.search(r"1 · [^\n]+\n2 · [^\n]+\n3 · ", zalo.sent[-1][1]), "trang chủ không chèn dòng trống giữa các mục"
    count = len(channel.store.menu(-1, NOW))
    channel.handle(_update("99", "h2"), now=NOW)
    assert zalo.sent[-1][1] == f"Không có số 99. Tin gần nhất có số 1 đến {count}, hoặc gõ menu để mở trang chủ."
    assert len(channel.store.menu(-1, NOW)) == count, "gõ nhầm số không xoá danh sách"
    channel.handle(_update(str(channel.store.menu(-1, NOW).index("u:p:guide") + 1), "h3"), now=NOW)
    assert "Cách dùng trên Zalo" in zalo.sent[-1][1]


def test_ten_mon_bo_nhan_khuyen_mai_shop():
    assert messages.buyer_name("[MUA 2 TẶNG 1] Combo 2 Nước Tẩy Trang Dầu") == "Combo 2 Nước Tẩy Trang Dầu"
    assert "[HOT]" not in messages.price_drop("[HOT] Kem chống nắng d'Alba 50ml", 408_000, 11)
    row = dict(item_id=1, shop_id=9, name="Áo", price=200_000, usual=250_000, lowest_30d=True, cashback=3_000,
               rating=4.8, sold_30d=500)
    text, _kb = deals.message_for(["nam"], {"nam": [row]}, set(), reason="Áo Sơ Mi Nam Tay Dài SYLEN – Vải Cotton Lụa")
    assert "Cotton…</i>\n" in text or "…</i>." not in text, "không ra «….»"


def test_khoi_dong_gui_not_tin_ket_va_nhan_khach_gui_lai(tmp_path):
    """Chỗ hở 2 (rà soát timeout / chống trùng 2026-10-28): tiến trình bị tắt ngang, tin kẹt ở 'received'."""
    bot, channel, zalo = _channel(tmp_path)
    channel.handle(_update("hd", "m0"), now=NOW)
    reply = render(BotReply("Câu trả lời đã soạn"))[0]
    with bot.repo.connect() as conn:
        for message_id, received, saved in (("a", "2026-10-21T08:00:00Z", True), ("b", "2026-10-21T08:05:00Z", False),
                                            ("c", "2026-10-20T00:00:00Z", False)):
            conn.execute("INSERT INTO zalo_inbox (message_id, internal_user_id, event_name, status, received_at, "
                         "reply_json) VALUES (?, -1, 'message.text.received', 'received', ?, ?)",
                         (message_id, received, json.dumps([[m.text, []] for m in reply]) if saved else None))
    assert channel.recover_inbox(NOW) == (1, 1)
    zalo.sent.clear()
    channel.retry_due(NOW)
    texts = [t for _c, t, _s in zalo.sent]
    assert texts == ["Câu trả lời đã soạn", "🙏 Bot vừa khởi động lại đúng lúc đọc tin của bạn nên chưa trả lời được. "
                                              "Bạn gửi lại tin giúp mình nhé."]
    with bot.repo.connect() as conn:
        status = dict(conn.execute("SELECT message_id, status FROM zalo_inbox WHERE message_id IN ('a', 'b', 'c')"))
    assert status == {"a": "replied", "b": "replied", "c": "failed"}, "tin quá 6 giờ thì bỏ, không nhắn"
    assert channel.recover_inbox(NOW) == (0, 0)
