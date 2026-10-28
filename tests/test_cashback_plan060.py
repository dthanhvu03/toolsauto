"""PLAN-060: nút cho khách, popup, gửi lại giữ nút, hồ sơ bot, thông báo admin im lặng."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.messages import (
    ADMIN_COMMANDS,
    BOT_COMMANDS,
    DESCRIPTION,
    DIEUKIEN,
    SHORT_DESCRIPTION,
    TIP_ALERT,
)
from cashback_bot.poller import _register_profile, flush_outbound, process_updates
from cashback_bot.telegram_api import TelegramDeliveryError
from tests.test_cashback_bot import FakeClient, payload, repo, service

ADMIN = 7


class Telegram:
    def __init__(self, fail_first: int = 0):
        self.fail_first = fail_first
        self.sent = []
        self.edited = []
        self.answers = []
        self.actions = []

    def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
        if self.fail_first:
            self.fail_first -= 1
            raise requests.ConnectionError("down")
        self.sent.append({"chat_id": chat_id, "html": html, "markup": reply_markup, "silent": disable_notification})

    def edit_message_text(self, chat_id, message_id, html, reply_markup=None):
        self.edited.append({"message_id": message_id, "html": html, "markup": reply_markup})
        return True

    def answer_callback(self, callback_query_id, text=None, show_alert=False):
        self.answers.append((callback_query_id, text, show_alert))

    def send_chat_action(self, chat_id, action="typing"):
        self.actions.append((chat_id, action))


class Admin:
    def flush_pending(self, limit=10):
        pass

    def notify_link_sent(self, update_id):
        pass

    def notify_request_failed(self, **kwargs):
        pass


def _fresh_client():
    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return FakeClient(payload(last_update=current))


def _message(update_id, text, user_id=111):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"type": "private", "id": user_id},
            "from": {"id": user_id, "username": "buyer"},
            "text": text,
        },
    }


def _callback(update_id, data, user_id=111, message_id=900):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"q{update_id}",
            "data": data,
            "from": {"id": user_id},
            "message": {"message_id": message_id, "chat": {"id": user_id, "type": "private"}},
        },
    }


def _callbacks(markup):
    return [b.get("callback_data") for row in markup["inline_keyboard"] for b in row if "callback_data" in b]


def test_start_co_nut_va_trang_con_doi_bang_edit(tmp_path):
    bot = service(tmp_path, _fresh_client())
    tg = Telegram()
    process_updates(bot, tg, bot.repo, [_message(1, "/start")], Admin())
    home = tg.sent[0]
    assert _callbacks(home["markup"]) == ["u:p:wallet", "u:p:orders", "u:p:guide", "u:p:tips", "u:p:calc", "u:p:support"]
    assert "u:p:rank" not in _callbacks(home["markup"])

    process_updates(bot, tg, bot.repo, [_callback(2, "u:p:calc")], Admin())
    assert len(tg.sent) == 1, "đổi trang không được sinh tin mới"
    page = tg.edited[0]
    assert page["message_id"] == 900
    assert "💰 <b>Cách tính tiền hoàn</b>" in page["html"]
    assert _callbacks(page["markup"]) == ["u:p:home"]
    assert tg.answers[-1] == ("q2", None, False)

    process_updates(bot, tg, bot.repo, [_callback(3, "u:p:home")], Admin())
    assert "Xem món Shopee được hoàn bao nhiêu" in tg.edited[-1]["html"]


def test_lenh_go_tay_co_nut_ve_trang_chu(tmp_path):
    bot = service(tmp_path, _fresh_client())
    for index, command in enumerate(("/huongdan", "/dieukien", "/cachtinh", "/hang"), start=10):
        reply = bot.handle_text(111, "buyer", command, update_id=index)
        assert reply.inline_keyboard == ((("◀️ Trang chủ", "u:p:home"),),)
    unknown = bot.handle_text(111, "buyer", "/abc", update_id=20)
    assert "Xem món Shopee được hoàn bao nhiêu" in unknown.text
    assert unknown.inline_keyboard is not None


def test_the_ket_qua_co_nut_mua_va_nut_luu_y_popup(tmp_path):
    bot = service(tmp_path, _fresh_client())
    tg = Telegram()
    process_updates(bot, tg, bot.repo, [_message(30, "https://shopee.vn/product/9/8")], Admin())
    rows = tg.sent[0]["markup"]["inline_keyboard"]
    assert rows[0][0]["text"] == "🛒 Mua trên Shopee"
    assert rows[0][0]["url"].startswith("https://s.shopee.vn/an_redir?")
    assert rows[1][0]["callback_data"] == "u:tip"

    process_updates(bot, tg, bot.repo, [_callback(31, "u:tip")], Admin())
    assert tg.answers[-1] == ("q31", TIP_ALERT, True)
    assert tg.edited == [], "popup không được đè thẻ kết quả"
    assert len(tg.sent) == 1
    assert len(TIP_ALERT) <= 200
    assert bot.repo.get_outbound(31) is None
    assert bot.repo.get_offset() == 32


def test_gui_lai_giu_du_nut(tmp_path):
    bot = service(tmp_path, _fresh_client(), delivery_backoff_sec=0)
    tg = Telegram(fail_first=1)
    process_updates(bot, tg, bot.repo, [_message(40, "https://shopee.vn/product/9/8")], Admin())
    assert tg.sent == []
    flush_outbound(bot, tg, bot.repo, Admin(), now=datetime.now(timezone.utc))
    markup = tg.sent[0]["markup"]
    assert markup["inline_keyboard"][0][0]["url"].startswith("https://s.shopee.vn/an_redir?")
    assert _callbacks(markup) == ["u:tip"]


def test_dong_cu_chua_co_markup_van_dung_nut_mua(tmp_path):
    store = repo(tmp_path)
    store.enqueue_outbound(50, 111, "cũ", "https://s.shopee.vn/an_redir?x=1")
    from cashback_bot.poller import _row_markup

    row = store.get_outbound(50)
    assert _row_markup(row) == {
        "inline_keyboard": [[{"text": "🛒 Mua trên Shopee", "url": "https://s.shopee.vn/an_redir?x=1"}]]
    }


def test_link_sai_co_nut_cach_lay_link(tmp_path):
    bot = service(tmp_path, _fresh_client())
    reply = bot.handle_text(111, "buyer", "xin chào", update_id=60)
    assert reply.inline_keyboard == ((("📖 Cách dùng", "u:p:guide"),),)
    again = bot.handle_text(111, "buyer", "xin chào", update_id=60)
    assert again.inline_keyboard == reply.inline_keyboard


def test_khach_chua_mo_bam_nut_nhan_popup(tmp_path):
    bot = service(tmp_path, _fresh_client())
    tg = Telegram()
    process_updates(bot, tg, bot.repo, [_callback(70, "u:p:calc", user_id=222)], Admin())
    assert tg.edited == [] and tg.sent == []
    query, text, alert = tg.answers[-1]
    assert alert is True
    assert "chưa được mở" in text


def test_dang_go_chi_khi_gui_link(tmp_path):
    bot = service(tmp_path, _fresh_client())
    tg = Telegram()
    process_updates(bot, tg, bot.repo, [_message(80, "/start"), _message(81, "https://shopee.vn/product/9/8")], Admin())
    assert tg.actions == [(111, "typing")]


def test_nut_admin_khong_vao_nhanh_khach(tmp_path):
    bot = service(tmp_path, _fresh_client(), admin_user_ids=frozenset({ADMIN}))
    tg = Telegram()
    process_updates(bot, tg, bot.repo, [_callback(90, "c:menu:rank", user_id=111)], Admin())
    assert "chỉ dành cho quản trị" in tg.edited[0]["html"]


def test_dang_ky_ho_so_bot():
    calls = []

    class Api:
        def set_my_commands(self, commands=BOT_COMMANDS, scope=None):
            calls.append(("commands", [name for name, _ in commands], scope))
            return True

        def set_my_description(self, text):
            calls.append(("description", text))
            return True

        def set_my_short_description(self, text):
            calls.append(("short", text))
            return True

    _register_profile(Api(), frozenset({9, 7}))
    assert calls[0] == ("commands", ["start", "huongdan", "dieukien", "cachtinh", "donhang", "deal", "hotro", "thongbao", "help"], None)
    assert ("description", DESCRIPTION) in calls
    assert ("short", SHORT_DESCRIPTION) in calls
    admin_calls = [c for c in calls if c[0] == "commands" and c[2]]
    assert [c[2]["chat_id"] for c in admin_calls] == [7, 9]
    assert all(c[1][-1] == "admin" for c in admin_calls)
    assert [name for name, _ in ADMIN_COMMANDS][-1] == "admin"
    assert len(DESCRIPTION) <= 512
    assert len(SHORT_DESCRIPTION) <= 120


def test_thong_bao_admin_im_lang_tru_loi(tmp_path):
    store = repo(tmp_path)
    tg = Telegram()
    notifier = AdminNotifier(store, tg, enabled=True, chat_id=999)
    notifier.notify_new_user(111, "buyer")
    notifier.notify_request_failed(error_type="product_data_timeout", update_id=1, telegram_user_id=111)
    notifier.flush_pending()
    assert [m["silent"] for m in tg.sent] == [True, False]
    assert "Người dùng mới" in tg.sent[0]["html"]
    assert "@buyer" in tg.sent[0]["html"]
    assert "Lỗi bot" in tg.sent[1]["html"]
    for message in tg.sent:
        html = message["html"]
        assert html.count("<blockquote expandable>") == 1
        assert html.endswith("</blockquote>")
        assert "User <code>111</code>" in html


def test_thong_bao_link_gon_ma_ky_thuat_thu_gon(tmp_path):
    store = repo(tmp_path)
    tg = Telegram()
    notifier = AdminNotifier(store, tg, enabled=True, chat_id=999)
    bot = service(tmp_path, _fresh_client())
    bot.client.payload["productInfo"]["productName"] = "Quần Ống Rộng Nữ Túi Xéo Mộc Studio, Thiết Kế Suông Dài"
    customer = Telegram()
    process_updates(bot, customer, store, [_message(95, "https://shopee.vn/product/9/8")], notifier)
    html = [m["html"] for m in tg.sent if "Đã gửi link" in m["html"]][0]
    head, details = html.split("<blockquote expandable>")
    assert "🛍️ Quần Ống Rộng Nữ Túi Xéo Mộc Studio\n" in head
    assert "Thiết Kế" not in head
    assert "💰 Giá 250.000đ · Hoàn <b>14.000đ</b>" in head
    assert "Sub <code>" not in head and "Item <code>" not in head
    assert "Item <code>8</code>" in details


def test_thong_bao_admin_loi_gui_khong_vang_vong_poll(tmp_path):
    store = repo(tmp_path)

    class Broken:
        def send_message(self, *args, **kwargs):
            raise TelegramDeliveryError("permanent", status_code=400)

    notifier = AdminNotifier(store, Broken(), enabled=True, chat_id=999)
    notifier.notify_new_user(111, "buyer")
    notifier.flush_pending()
    row = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        "SELECT status, attempt_count FROM admin_notifications"
    ).fetchone()
    assert row == ("failed", 1), "PLAN-079: 4xx là lỗi vĩnh viễn, không thử lại mãi; vòng poll vẫn chạy"


def test_admin_xac_nhan_quay_ve_man_vua_sua(tmp_path):
    bot = service(tmp_path, _fresh_client(), admin_user_ids=frozenset({ADMIN}))
    panel = bot.admin_panel
    now = datetime.now(timezone.utc)
    panel.handle_callback(ADMIN, "c:tier:SILVER", "private", now)
    preview = panel.consume_text(ADMIN, "66,5", now)
    assert "65% → <b>66,5%</b>" in preview.text
    done = panel.handle_callback(ADMIN, preview.inline_keyboard[0][1][1], "private", now)
    assert done.toast == "Đã lưu phiên bản v1"
    assert "Quản trị › <b>Hạng thành viên</b>" in done.text
    assert "🥈 Bạc: <b>66,5%</b>" in done.text

def test_admin_nhap_so_sai_van_co_nut_huy(tmp_path):
    bot = service(tmp_path, _fresh_client(), admin_user_ids=frozenset({ADMIN}))
    now = datetime.now(timezone.utc)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:GOLD", "private", now)
    bad = bot.admin_panel.consume_text(ADMIN, "99", now)
    assert "không nằm trong giới hạn" in bad.text
    assert bad.inline_keyboard[0][0][0] == "✖️ Hủy bản nháp"
    order = bot.admin_panel.consume_text(ADMIN, "50", now)
    assert "Đồng ≤ Bạc ≤ Vàng" in order.text
    assert order.inline_keyboard[0][0][0] == "✖️ Hủy bản nháp"


def _to_value_step(bot, now, kind="k:P"):
    step = bot.admin_panel.handle_callback(ADMIN, "c:rs:new", "private", now)
    data = [d for row in step.inline_keyboard for _l, d in row if d.endswith(kind)][0]
    return bot.admin_panel.handle_callback(ADMIN, data, "private", now)


def test_admin_go_phan_tram_khong_go_phan_van(tmp_path):
    """User phản hồi 2026-10-23: gõ 10 là 10%, 0,98 là 0,98%."""
    cases = [
        ("fee", "0,98", "0,98%"),
        ("fee", "0.98", "0,98%"),
        ("fee", "1,25", "1,25%"),
        ("tax", "10", "10%"),
        ("tax", "7,5%", "7,5%"),
        ("tax", "0,5", "0,5%"),
    ]
    for index, (field, typed, shown) in enumerate(cases):
        bot = service(tmp_path / str(index), _fresh_client(), admin_user_ids=frozenset({ADMIN}))
        now = datetime.now(timezone.utc)
        prompt = _to_value_step(bot, now)
        assert "phần vạn" not in prompt.text
        if field == "fee":
            bot.admin_panel.consume_text(ADMIN, typed, now)
            when = bot.admin_panel.consume_text(ADMIN, "10", now)
            assert f"phí {shown}" in when.text, (typed, when.text)
        else:
            tax_step = bot.admin_panel.handle_callback(ADMIN, prompt.inline_keyboard[0][0][1], "private", now)
            assert "Thuế dự phòng đang áp dụng" in tax_step.text
            when = bot.admin_panel.consume_text(ADMIN, typed, now)
            assert f"thuế {shown}" in when.text, (typed, when.text)
    bot = service(tmp_path / "rank", _fresh_client(), admin_user_ids=frozenset({ADMIN}))
    now = datetime.now(timezone.utc)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:SILVER", "private", now)
    assert "→ <b>65,5%</b>" in bot.admin_panel.consume_text(ADMIN, "65,5", now).text
    for typed in ("51", "0,987", "abc", "1.000"):
        bot = service(tmp_path / f"bad{typed}", _fresh_client(), admin_user_ids=frozenset({ADMIN}))
        now = datetime.now(timezone.utc)
        _to_value_step(bot, now)
        reply = bot.admin_panel.consume_text(ADMIN, typed, now)
        assert "⚠️" in reply.text and "Bước 2/4" in reply.text, typed

def test_bat_v12_moi_man_khop_cach_tinh(tmp_path):
    store = repo(tmp_path)
    with store.connect() as conn:
        conn.execute("ALTER TABLE link_requests ADD COLUMN estimate_policy TEXT")
    bot = service(tmp_path, _fresh_client(), estimate_policy="v1.2", admin_user_ids=frozenset({ADMIN}))
    now = datetime.now(timezone.utc)

    card = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1)
    assert "<b>12.462đ</b>" in card.text
    assert "sau dự phòng phí và thuế" in card.text
    calc = bot.handle_text(111, "buyer", "/cachtinh", update_id=2)
    assert "đã trừ trước dự phòng phí và thuế" in calc.text
    assert "không phải số thuế bạn phải nộp" in calc.text
    assert "%" not in calc.text

    home = bot.admin_panel.menu(ADMIN, now)
    assert "V1.2 · 70% phần còn lại sau dự phòng phí và thuế" in home.text
    assert "Báo giá đang chạy: V1.2" in home.text
    settings = bot.admin_panel.handle_callback(ADMIN, "c:menu:settings", "private", now)
    assert "cách tính V1.2" in settings.text
    policy = bot.admin_panel.handle_callback(ADMIN, "c:menu:policy", "private", now)
    assert "Phiên bản: <b>V1.2</b>" in policy.text
    assert "Dự phòng phí (0,98%): -980đ" in policy.text
    assert "Dự phòng thuế (10%): -10.000đ" in policy.text
    assert "Phần khách (70% phần còn lại): <b>62.314đ</b>" in policy.text
    assert "Biên (sau dự phòng): <b>26.706đ</b>" in policy.text
    assert "V1.1" not in policy.text
    sim = bot.admin_panel.handle_callback(ADMIN, "c:menu:sim", "private", now)
    assert "Báo giá: <b>V1.2" in sim.text
    fee = bot.admin_panel.handle_callback(ADMIN, "c:menu:fee", "private", now)
    assert "Phí dự phòng: <b>0,98%</b> · Thuế dự phòng: <b>10%</b>" in fee.text
    assert "Phần khách (70%): <b>62.314đ</b>" in fee.text
    assert "Đang chạy V1.1" not in fee.text


def test_bat_v12_thieu_cot_admin_van_bao_v11(tmp_path):
    bot = service(tmp_path, _fresh_client(), estimate_policy="v1.2", admin_user_ids=frozenset({ADMIN}))
    home = bot.admin_panel.menu(ADMIN, datetime.now(timezone.utc))
    assert "V1.1 · 70% hoa hồng ước tính" in home.text
    card = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1)
    assert "<b>14.000đ</b>" in card.text


def test_khach_khong_thay_so_noi_bo(tmp_path):
    """User 2026-10-23: không lộ tỷ lệ chia, phí, thuế ở bất kỳ trang nào khách mở được."""
    from cashback_bot.messages import DESCRIPTION, SHORT_DESCRIPTION

    bot = service(tmp_path, _fresh_client())
    texts = [DESCRIPTION, SHORT_DESCRIPTION]
    for index, command in enumerate(("/start", "/help", "/huongdan", "/dieukien", "/cachtinh", "/hang", "/abc"), start=1):
        texts.append(bot.handle_text(111, "buyer", command, update_id=index).text)
    texts.append(bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=50).text)
    for text in texts:
        assert "%" not in text, text


def test_nut_de_duoc_ghi_nhan_luon_mo_trang_meo(tmp_path):
    """Rà soát 2026-10-26: khi có điều khoản công bố, /dieukien mở điều khoản; nút 🛡️ vẫn mở trang mẹo."""
    bot = service(tmp_path, FakeClient(payload()))
    reply = bot.handle_update({"update_id": 1, "callback_query": {
        "id": "q", "from": {"id": 111}, "data": "u:p:tips", "message": {"message_id": 5, "chat": {"type": "private"}}}})[1]
    assert reply.text == DIEUKIEN and ("📋 Điều khoản", "u:p:rules") in [b for row in reply.inline_keyboard for b in row]
