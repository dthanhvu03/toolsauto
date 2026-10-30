"""Cashback bot V1. Không gọi Telegram thật, không đụng bot đăng bài."""

from __future__ import annotations

import sqlite3
import tempfile
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.affiliate import build_an_redir, build_food_redir, is_valid_sub_id
from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import FOOD_BUTTON, STALE
from cashback_bot.money import estimated_cashback
from cashback_bot.product_data import ProductDataClient, ProductDataError, quote_from_payload
from cashback_bot.service import CashbackService
from cashback_bot.shopee_url import food_url, is_shopee_food_link, parse_shopee_target

NOW = datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, payload=None, error: ProductDataError | None = None):
        self.payload = payload
        self.error = error
        self.calls = 0
        self.targets = []

    def fetch(self, target):
        self.calls += 1
        self.targets.append(target)
        if self.error:
            raise self.error
        return self.payload


def settings(tmp_path, **overrides):
    base = dict(
        bot_token="cashback-token",
        affiliate_id="17300001",
        api_key="test-key",
        cashback_rate_percent=70,
        product_max_age_hours=3,
        db_path=str(tmp_path / "cashback.sqlite"),
        customer_access_enabled=False,
        allowed_telegram_ids=frozenset({111}),
        admin_notifications_enabled=False,
        admin_chat_id=None,
    )
    base.update(overrides)
    from cashback_bot.config import Settings

    return Settings(**base)


def repo(tmp_path) -> TrackingRepository:
    store = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    store.migrate()
    return store


def payload(last_update="2026-10-21 07:00:00", warning=None, **info):
    body = {
        "itemId": 8,
        "shopId": 9,
        "productName": "Áo Polo Nam",
        "price": 250000,
        "commission": 20000,
        "dataSource": "db",
        "lastUpdate": last_update,
        "productLink": "https://shopee.vn/product/9/8",
    }
    body.update(info)
    data = {"status": "success", "productInfo": body}
    if warning is not None:
        data["warning"] = warning
    return data


def service(tmp_path, client, **overrides) -> CashbackService:
    return CashbackService(settings(tmp_path, **overrides), repo(tmp_path), client)


class _CollectAdmin:
    def __init__(self):
        self.new_users = []
        self.link_sent = []
        self.failed = []
        self.flush_calls = 0

    def notify_new_user(self, telegram_user_id, username):
        self.new_users.append((telegram_user_id, username))

    def notify_link_sent(self, update_id):
        self.link_sent.append(update_id)

    def notify_request_failed(self, **kwargs):
        self.failed.append(kwargs)

    def flush_pending(self, limit=10):
        self.flush_calls += 1


class _DummyCustomerTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
        self.sent.append((chat_id, html, reply_markup))


class _DummyAdminTelegram:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent = []

    def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
        if self.should_fail:
            raise requests.ConnectionError("admin down")
        self.sent.append((chat_id, html, reply_markup))


def test_ac01_link_hop_le_va_cashback_70(tmp_path):
    client = FakeClient(payload())
    reply = service(tmp_path, client).handle_text(
        111, "buyer", "mua https://shopee.vn/product/9/8 nhe", update_id=1, now=NOW
    )
    assert "Áo Polo Nam" in reply.text
    assert "giá tham khảo 250.000đ" in reply.text
    assert "Mua thẳng trong app" in reply.text and "xoá đi rồi mở lại" in reply.text, "nhắc mua qua link của bot"
    assert "20.000đ" not in reply.text
    assert "✅ <b>Đã tạo link hoàn tiền</b>" in reply.text
    assert "💰 <b>Hoàn dự kiến:" in reply.text
    assert "<b>14.000đ</b>" in reply.text
    assert "70%" not in reply.text
    assert "an_redir" not in reply.text
    assert "Shopee xác nhận đơn hợp lệ" in reply.text
    assert "Chưa phải tiền có thể rút." in reply.text
    assert reply.markup()["inline_keyboard"][0][0]["text"] == "🛒 Mua trên Shopee"
    query = parse_qs(urlparse(reply.button_url).query)
    sub_id = query["sub_id"][0]
    assert is_valid_sub_id(sub_id)
    assert query["affiliate_id"] == ["17300001"]
    assert query["origin_link"] == ["https://shopee.vn/product/9/8"]
    assert "-" not in sub_id and "_" not in sub_id
    assert "111" not in sub_id

    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    row = conn.execute("SELECT * FROM link_requests").fetchone()
    user = conn.execute("SELECT telegram_user_id FROM telegram_users").fetchone()
    tables = {item[0] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert user[0] == 111
    assert row[2] == 111  # telegram_user_id column index checked below by name
    saved = conn.execute(
        "SELECT sub_id, telegram_user_id, estimated_cashback, link_status, affiliate_url FROM link_requests"
    ).fetchone()
    assert saved == (sub_id, 111, 14000, "created", build_an_redir("https://shopee.vn/product/9/8", "17300001", sub_id))
    assert tables.isdisjoint({"wallet", "payouts", "withdrawals", "transactions"})


def test_ac02_moi_luot_mot_sub_id(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    bot.handle_text(111, "buyer", "https://shopee.vn/Ao-i.9.8", update_id=2, now=NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    rows = conn.execute("SELECT sub_id FROM link_requests ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert all(is_valid_sub_id(item[0]) for item in rows)


def test_cung_update_khong_tao_them_sub_id(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    first = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=20, now=NOW)
    second = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=20, now=NOW)
    assert first == second
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 1


def test_ac02_trung_sub_id_thi_sinh_lai(tmp_path, monkeypatch):
    store = repo(tmp_path)
    store.upsert_user(111, "buyer")
    store.insert_created(
        {
            "telegram_update_id": 99,
            "telegram_user_id": 111,
            "sub_id": "takenid1",
            "original_url": "https://shopee.vn/product/1/1",
            "affiliate_url": "https://s.shopee.vn/an_redir?x=1",
            "link_status": "created",
            "cashback_rate_percent": 70,
        }
    )
    issued = iter(["takenid1", "freenew1"])
    monkeypatch.setattr("cashback_bot.service.new_sub_id", lambda: next(issued))
    reply = CashbackService(settings(tmp_path), store, FakeClient(payload())).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=3, now=NOW
    )
    assert "sub_id=freenew1" in reply.button_url
    assert "an_redir" not in reply.text


def test_ac03_cache_cu_va_warning_khong_dua_so(tmp_path):
    stale = payload(
        last_update="2026-10-05 02:50:09",
        warning="Using cached data - API fetch failed",
        price=145820,
        commission=8021,
        productName="Gối chữ U",
    )
    reply = service(tmp_path, FakeClient(stale)).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=4, now=NOW
    )
    assert reply.text == STALE
    assert reply.button_url is None
    assert "8.021" not in reply.text
    assert "145.820" not in reply.text
    assert "an_redir" not in reply.text
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    saved = conn.execute(
        "SELECT link_status, estimated_cashback, affiliate_url, reject_reason FROM link_requests"
    ).fetchone()
    assert saved == ("rejected", None, None, "stale")


def test_ac03_qua_han_du_khong_co_warning(tmp_path):
    old = payload(last_update="2026-10-05 02:50:09")
    reply = service(tmp_path, FakeClient(old)).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=5, now=NOW
    )
    assert reply.text == STALE
    assert "14.000đ" not in reply.text


def test_ac03_api_loi_va_timeout(tmp_path):
    for code, update_id in (("timeout", 6), ("http_error", 7)):
        reply = service(tmp_path, FakeClient(error=ProductDataError(code))).handle_text(
            111, "buyer", "https://shopee.vn/product/9/8", update_id=update_id, now=NOW
        )
        assert reply.text == STALE
        assert reply.button_url is None


def test_cashback_bang_0_hien_thi_trung_thuc(tmp_path):
    no_commission = payload(commission=0)
    reply = service(tmp_path, FakeClient(no_commission)).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=12, now=NOW
    )
    assert "💰 <b>Hoàn dự kiến:" in reply.text
    assert "<b>0đ</b>" in reply.text
    assert "Chưa phải tiền có thể rút." in reply.text
    assert reply.button_url is not None


def test_thieu_cau_hinh_khong_lo_secret():
    with pytest.raises(ConfigError) as caught:
        load_settings(
            {
                "TELEGRAM_BOT_TOKEN": "publisher-secret",
                "CASHBACK_RATE_PERCENT": "70",
            }
        )
    assert "CASHBACK_BOT_TOKEN" in caught.value.missing
    assert "publisher-secret" not in str(caught.value)


def test_admin_notify_khong_bat_van_load_duoc():
    cfg = load_settings(
        {
            "CASHBACK_BOT_TOKEN": "123:abc",
            "SHOPEE_AFFILIATE_ID": "17300001",
            "ADDLIVETAG_API_KEY": "k",
            "CASHBACK_RATE_PERCENT": "70",
            "PRODUCT_MAX_AGE_HOURS": "3",
            "CUSTOMER_ACCESS_ENABLED": "false",
            "CASHBACK_ALLOWED_TELEGRAM_IDS": "111",
            "CASHBACK_ADMIN_NOTIFICATIONS_ENABLED": "false",
        }
    )
    assert cfg.admin_notifications_enabled is False
    assert cfg.admin_chat_id is None


def test_nguoi_ngoai_allowlist_khong_goi_api(tmp_path):
    client = FakeClient(payload())
    reply = service(tmp_path, client).handle_text(
        999, "stranger", "https://shopee.vn/product/9/8", update_id=8, now=NOW
    )
    assert "chưa được mở" in reply.text
    assert client.calls == 0
    assert reply.button_url is None


def test_new_user_notify_mot_lan(tmp_path):
    client = FakeClient(payload())
    admin = _CollectAdmin()
    bot = CashbackService(settings(tmp_path), repo(tmp_path), client, admin_notifier=admin)
    bot.handle_text(111, "buyer", "/start", update_id=901, now=NOW)
    bot.handle_text(111, "buyer", "/start", update_id=902, now=NOW)
    assert admin.new_users == [(111, "buyer")]


def test_link_khong_phai_shopee(tmp_path):
    client = FakeClient(payload())
    reply = service(tmp_path, client).handle_text(
        111, "buyer", "https://evil.example/product/9/8", update_id=9, now=NOW
    )
    assert "link sản phẩm Shopee" in reply.text
    assert "/huongdan" in reply.text
    assert client.calls == 0


def test_url_shopee_gia_mao_bi_chan(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    for update_id, text in (
        (91, "https://shopee.vn.evil.example/product/9/8"),
        (92, "https://shopee.vn@evil.example/product/9/8"),
        (93, "https://evil.example/?next=https://shopee.vn/product/9/8"),
    ):
        reply = bot.handle_text(111, "buyer", text, update_id=update_id, now=NOW)
        assert "link sản phẩm Shopee" in reply.text
        assert reply.button_url is None
    assert client.calls == 0


def test_link_rut_gon_di_qua_url(tmp_path):
    client = FakeClient(payload())
    service(tmp_path, client).handle_text(
        111, "buyer", "https://s.shopee.vn/abcDEF12", update_id=10, now=NOW
    )
    assert client.targets[0].short_url == "https://s.shopee.vn/abcDEF12"
    assert client.targets[0].item_id is None


def test_ten_san_pham_bi_escape(tmp_path):
    body = payload()
    body["productInfo"]["productName"] = "<script>alert(1)</script>"
    reply = service(tmp_path, FakeClient(body)).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=11, now=NOW
    )
    assert "<script>" not in reply.text
    assert "&lt;script&gt;" in reply.text


def test_lenh_huongdan_khong_tao_link(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    for update_id, text in ((60, "/huongdan"), (62, "/huongdan@zt_shopee_bot")):
        reply = bot.handle_text(111, "buyer", text, update_id=update_id, now=NOW)
        assert "📖 <b>Cách dùng</b>" in reply.text
        assert "không thu phí sử dụng" in reply.text
        assert "không bảo đảm đơn hàng được ghi nhận" in reply.text
        assert reply.button_url is None
    help_reply = bot.handle_text(111, "buyer", "/help", update_id=65, now=NOW)
    assert "Xem món Shopee được hoàn bao nhiêu" in help_reply.text
    assert "📖 <b>Cách dùng</b>" not in help_reply.text
    assert help_reply.button_url is None
    assert client.calls == 0
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 0


def test_lenh_start_uu_tien_kich_hoat_gui_link(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    reply = bot.handle_text(111, "buyer", "/start", update_id=61, now=NOW)
    assert "Xem món Shopee được hoàn bao nhiêu" in reply.text
    assert "số tiền hoàn dự kiến" in reply.text
    assert "Dán link sản phẩm Shopee vào đây" in reply.text
    assert "đang thử nghiệm" in reply.text
    assert reply.button_url is None
    assert client.calls == 0


def test_lenh_cach_tinh(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    for update_id, text in ((63, "/cachtinh"), (64, "/cachtinh@zt_shopee_bot")):
        reply = bot.handle_text(111, "buyer", text, update_id=update_id, now=NOW)
        assert "💰 <b>Cách tính tiền hoàn</b>" in reply.text
        assert "%" not in reply.text, "không lộ tỷ lệ chia, phí, thuế cho khách"
        assert "không trừ thêm thuế hay phí" in reply.text
        assert "chưa bật" not in reply.text
        assert "dự phòng" not in reply.text
        assert reply.button_url is None
    assert client.calls == 0


def test_nam_lenh_tach_noi_dung(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    replies = {
        name: bot.handle_text(111, "buyer", command, update_id=index, now=NOW).text
        for index, (name, command) in enumerate(
            (
                ("huongdan", "/huongdan"),
                ("dieukien", "/dieukien"),
                ("cachtinh", "/cachtinh"),
                ("hang", "/hang"),
                ("help", "/help"),
            ),
            start=70,
        )
    }
    assert replies["help"] != replies["huongdan"]
    assert "Xem món Shopee được hoàn bao nhiêu" in replies["help"]
    assert "Dán link sản phẩm Shopee" in replies["help"]
    assert "không bảo đảm Shopee sẽ ghi nhận hoa hồng" in replies["dieukien"]
    assert "60%" not in replies["hang"]
    assert "65%" not in replies["hang"]
    assert "bạn đang ở hạng" not in replies["hang"].lower()
    assert "chưa chính thức áp dụng" in replies["hang"]
    assert "%" not in replies["cachtinh"]
    for text in replies.values():
        assert text.count("<b>") == text.count("</b>")
        assert text.count("<i>") == text.count("</i>")
        assert "chắc chắn được hoàn" not in text
        assert "số dư khả dụng" not in text
        assert "đã duyệt thưởng" not in text
    assert client.calls == 0


def test_set_my_commands_co_lenh_thong_tin(monkeypatch):
    from cashback_bot.telegram_api import TelegramApi

    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("cashback_bot.telegram_api.requests.post", fake_post)
    api = TelegramApi("123:abc")
    assert api.set_my_commands() is True
    commands = captured["json"]["commands"]
    names = [item["command"] for item in commands]
    assert names == ["start", "huongdan", "dieukien", "cachtinh", "donhang", "deal", "theodoi", "magiam", "hotro",
                     "thongbao", "help"]
    assert all(len(item["description"]) <= 256 for item in commands)


def test_ten_dai_cat_o_dau_phay():
    from cashback_bot.messages import buyer_name

    raw = "Mực in cho máy in phun màu HP tank 115, 315, 319, 400, 415, 510 mã Gt52"
    assert buyer_name(raw) == "Mực in cho máy in phun màu HP tank 115"
    assert buyer_name("Áo Polo Nam") == "Áo Polo Nam"


def test_floor_vnd():
    assert estimated_cashback(20000, 70) == 14000
    assert estimated_cashback(19999, 70) == 13999


def test_mau_that_goi_chu_u_bi_loai_va_ban_cache_hom_nay_duoc_nhan():
    stale = {
        "status": "success",
        "warning": "Using cached data - API fetch failed",
        "productInfo": {
            "itemId": 27345778106,
            "shopId": 1703926009,
            "productName": "Gối chữ U",
            "price": 145820,
            "commission": 8021,
            "dataSource": "db",
            "lastUpdate": "2026-10-05 02:50:09",
            "productLink": "https://shopee.vn/product/1703926009/27345778106",
        },
    }
    fresh = {
        "status": "success",
        "productInfo": {
            "itemId": 25171045245,
            "shopId": 1218336683,
            "productName": "Áo mưa",
            "price": 146620,
            "commission": 23459,
            "dataSource": "db",
            "lastUpdate": "2026-10-21 05:56:19",
            "productLink": "https://shopee.vn/product/1218336683/25171045245",
        },
    }
    with pytest.raises(ProductDataError) as caught:
        quote_from_payload(stale, NOW, 3)
    assert caught.value.code == "stale"
    quote = quote_from_payload(fresh, NOW, 3)
    assert quote.commission_vnd == 23459
    assert estimated_cashback(quote.commission_vnd, 70) == 16421


def test_client_http_va_timeout(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise requests.Timeout()

    monkeypatch.setattr("cashback_bot.product_data.requests.get", timeout)
    client = ProductDataClient("k", "https://example.test")
    target = parse_shopee_target("https://shopee.vn/product/9/8")
    with pytest.raises(ProductDataError) as caught:
        client.fetch(target)
    assert caught.value.code == "timeout"

    class Response:
        status_code = 500

        def json(self):
            return {"status": "error"}

    monkeypatch.setattr("cashback_bot.product_data.requests.get", lambda *_a, **_k: Response())
    with pytest.raises(ProductDataError) as caught:
        client.fetch(target)
    assert caught.value.code == "http_error"


def test_product_data_rate_limit_sleep(monkeypatch):
    stamps = iter([10.0, 10.05, 10.05, 10.40])
    slept = []

    monkeypatch.setattr("cashback_bot.product_data.time.monotonic", lambda: next(stamps))
    monkeypatch.setattr("cashback_bot.product_data.time.sleep", lambda sec: slept.append(sec))

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "success", "productInfo": {"itemId": 1, "shopId": 2, "productName": "A", "price": 1, "commission": 0, "dataSource": "db", "lastUpdate": "2026-10-21 07:00:00"}}

    monkeypatch.setattr("cashback_bot.product_data.requests.get", lambda *_a, **_k: Response())
    client = ProductDataClient("k", "https://example.test", min_interval_sec=0.3)
    target = parse_shopee_target("https://shopee.vn/product/2/1")
    client.fetch(target)
    client.fetch(target)
    assert slept and round(slept[0], 2) == 0.30


def test_last_update_tuong_lai_va_db_con_trong_nguong(tmp_path):
    fresh_db = payload(last_update="2026-10-21 05:30:00", dataSource="db")
    quote = quote_from_payload(fresh_db, NOW, 3)
    assert quote.data_source == "db"
    assert quote.last_update.tzinfo == timezone.utc

    almost = (NOW - timedelta(hours=2, minutes=59)).strftime("%Y-%m-%d %H:%M:%S")
    assert quote_from_payload(payload(last_update=almost), NOW, 3).price_vnd == 250000

    older = (NOW - timedelta(hours=3, minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    with pytest.raises(ProductDataError) as too_old:
        quote_from_payload(payload(last_update=older), NOW, 3)
    assert too_old.value.code == "too_old"

    future = (NOW + timedelta(minutes=11)).strftime("%Y-%m-%d %H:%M:%S")
    with pytest.raises(ProductDataError) as ahead:
        quote_from_payload(payload(last_update=future), NOW, 3)
    assert ahead.value.code == "missing_last_update"

    reply = service(tmp_path, FakeClient(payload(last_update=future))).handle_text(
        111, "buyer", "https://shopee.vn/product/9/8", update_id=40, now=NOW
    )
    assert reply.text == STALE
    assert reply.button_url is None


def test_allowlist_khoa_theo_user_id(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    reply = bot.handle_text(222, "111", "https://shopee.vn/product/9/8", update_id=41, now=NOW)
    assert "chưa được mở" in reply.text
    assert client.calls == 0
    ignored = bot.handle_update(
        {
            "update_id": 42,
            "message": {
                "chat": {"type": "supergroup", "id": -100},
                "from": {"id": 222, "username": "stranger"},
                "text": "https://shopee.vn/product/9/8",
            },
        }
    )
    assert ignored is None
    assert client.calls == 0
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 0


def test_gui_tin_that_bai_khong_danh_dau_da_giao(tmp_path, caplog):
    from cashback_bot.poller import process_updates

    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    client = FakeClient(payload(last_update=current))
    bot = service(tmp_path, client, delivery_backoff_sec=0)
    store = bot.repo
    admin = _CollectAdmin()
    update = {
        "update_id": 50,
        "message": {
            "chat": {"type": "private", "id": 111},
            "from": {"id": 111, "username": "buyer"},
            "text": "https://shopee.vn/product/9/8",
        },
    }

    class FlakyTelegram:
        def __init__(self):
            self.attempts = 0

        def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
            self.attempts += 1
            if self.attempts == 1:
                raise requests.ConnectionError("down")
            assert "an_redir" not in html
            assert "Đã tạo link hoàn tiền" in html
            assert reply_markup["inline_keyboard"][0][0]["url"].startswith("https://s.shopee.vn/an_redir?")
            assert chat_id == 111

    telegram = FlakyTelegram()
    with caplog.at_level("ERROR"):
        process_updates(bot, telegram, store, [update], admin)
    saved = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        "SELECT sub_id, delivery_status, link_status FROM link_requests"
    ).fetchone()
    assert saved[1] != "sent"
    assert saved[2] == "created"
    assert store.get_offset() == 51
    assert f"update_id=50 sub_id={saved[0]}" in caplog.text
    assert "down" not in caplog.text
    assert admin.link_sent == []
    assert admin.failed and admin.failed[0]["error_type"] == "telegram_send_customer_failed"

    process_updates(bot, telegram, store, [update], admin)
    again = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        "SELECT sub_id, delivery_status FROM link_requests"
    ).fetchall()
    assert again == [(saved[0], "sent")]
    assert store.get_offset() == 51
    assert client.calls == 1
    assert admin.link_sent == [50]
    assert admin.flush_calls == 2


def test_single_process_lock():
    from cashback_bot.poller import _acquire_single_process_lock

    lock_file = tempfile.NamedTemporaryFile(prefix="cashback-lock-", delete=False)
    lock_file.close()
    first = _acquire_single_process_lock(lock_file.name)
    second = _acquire_single_process_lock(lock_file.name)
    assert first is not None
    assert second is None
    first.close()


def test_khong_import_bot_dang_bai():
    text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "cashback_bot").rglob("*.py"))
    assert "app.features.telegram_bot" not in text
    assert "TELEGRAM_BOT_TOKEN" not in text
    assert "auto_publisher" not in text
    assert "zca-js" not in text
    publisher = (ROOT / "app/features/telegram_bot/poller.py").read_text(encoding="utf-8")
    assert "cashback_bot" not in publisher


def test_link_sent_notify_khong_trung_khi_retry_cung_update(tmp_path):
    from cashback_bot.poller import process_updates

    store = repo(tmp_path)
    admin_tg = _DummyAdminTelegram()
    admin = AdminNotifier(store, admin_tg, enabled=True, chat_id=999)
    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    bot = CashbackService(settings(tmp_path), store, FakeClient(payload(last_update=current)))
    customer_tg = _DummyCustomerTelegram()
    update = {
        "update_id": 701,
        "message": {
            "chat": {"type": "private", "id": 111},
            "from": {"id": 111, "username": "buyer"},
            "text": "https://shopee.vn/product/9/8",
        },
    }
    process_updates(bot, customer_tg, store, [update], admin)
    process_updates(bot, customer_tg, store, [update], admin)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    count = conn.execute(
        "SELECT COUNT(*) FROM admin_notifications WHERE event_type='LINK_SENT'"
    ).fetchone()[0]
    assert count == 1


def test_admin_send_loi_khong_anh_huong_khach(tmp_path):
    from cashback_bot.poller import process_updates

    store = repo(tmp_path)
    admin = AdminNotifier(store, _DummyAdminTelegram(should_fail=True), enabled=True, chat_id=999)
    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    bot = CashbackService(settings(tmp_path), store, FakeClient(payload(last_update=current)))
    customer = _DummyCustomerTelegram()
    update = {
        "update_id": 702,
        "message": {
            "chat": {"type": "private", "id": 111},
            "from": {"id": 111, "username": "buyer"},
            "text": "https://shopee.vn/product/9/8",
        },
    }
    process_updates(bot, customer, store, [update], admin)
    assert len(customer.sent) == 1
    row = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        "SELECT delivery_status FROM link_requests WHERE telegram_update_id=702"
    ).fetchone()
    assert row[0] == "sent"
    ev = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        "SELECT attempt_count, status FROM admin_notifications ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert ev[0] >= 1
    assert ev[1] == "retry", "PLAN-079: lỗi tạm thì chờ thử lại có giãn cách, không chặn tin khách"


def test_api_loi_notify_admin_khong_lo_secret(tmp_path):
    store = repo(tmp_path)
    admin_tg = _DummyAdminTelegram()
    admin = AdminNotifier(store, admin_tg, enabled=True, chat_id=999)
    bot = CashbackService(
        settings(tmp_path),
        store,
        FakeClient(error=ProductDataError("timeout")),
        admin_notifier=admin,
    )
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=703, now=NOW)
    assert reply.text == STALE
    admin.flush_pending()
    assert admin_tg.sent, "admin should receive timeout alert"
    msg = "\n".join(item[1] for item in admin_tg.sent)
    assert "Lỗi bot" in msg
    assert "product_data_timeout" in msg
    assert "https://s.shopee.vn/an_redir" not in msg
    assert not re.search(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", msg)
    assert not re.search(r"\b[a-f0-9]{40,64}\b", msg)


def test_escape_html_trong_admin_notify(tmp_path):
    store = repo(tmp_path)
    admin_tg = _DummyAdminTelegram()
    admin = AdminNotifier(store, admin_tg, enabled=True, chat_id=999)
    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    bot = CashbackService(
        settings(tmp_path),
        store,
        FakeClient(payload(last_update=current, productName="<script>abc</script>, test")),
        admin_notifier=admin,
    )
    from cashback_bot.poller import process_updates

    customer = _DummyCustomerTelegram()
    update = {
        "update_id": 704,
        "message": {
            "chat": {"type": "private", "id": 111},
            "from": {"id": 111, "username": "<b>buyer</b>"},
            "text": "https://shopee.vn/product/9/8",
        },
    }
    process_updates(bot, customer, store, [update], admin)
    # NEW_USER + LINK_SENT
    merged = "\n".join(item[1] for item in admin_tg.sent)
    assert "<script>" not in merged
    assert "&lt;script&gt;" in merged
    assert "<b>buyer</b>" not in merged
    assert "&lt;b&gt;buyer&lt;/b&gt;" in merged


def test_khuon_chu_khach_plan_060(tmp_path):
    """PLAN-060 P2: một dòng ⓘ, không chữ cashback, thẻ kết quả không nhắc hoa hồng."""
    from cashback_bot.messages import (
        CLOSED,
        DIEUKIEN,
        GENERIC_FAIL,
        HOME,
        HUONGDAN,
        INVALID_LINK,
        NOT_FOUND,
        hang_message,
        how_to_calc,
        rate_limited_reply,
        render_success,
        render_success_v12,
    )

    cards = [
        render_success("Áo Polo Nam", 250_000, 14_000, "https://s.shopee.vn/x").text,
        render_success_v12("Áo Polo Nam", 250_000, 12_462, "https://s.shopee.vn/x").text,
    ]
    pages = [HOME, HUONGDAN, DIEUKIEN, how_to_calc(False), how_to_calc(True), hang_message()]
    errors = [CLOSED, INVALID_LINK, STALE, NOT_FOUND, GENERIC_FAIL, rate_limited_reply(300).text]
    for text in cards + pages + errors:
        assert text.count("ⓘ") <= 1
        assert "cashback" not in text.lower()
        assert len(text) < 3500
        assert text.count("<b>") == text.count("</b>")
    for text in cards:
        assert "hoa hồng" not in text
        assert "Chưa phải tiền có thể rút." in text
    zero = render_success("Áo Polo Nam", 250_000, 0, "https://s.shopee.vn/x").text
    assert "Đã tạo link mua" in zero
    assert "Đã tạo link hoàn tiền" not in zero
    assert "Mua thẳng trong app" not in zero, "không có hoàn thì không doạ mất hoàn"


def test_link_shopeefood_tra_loi_ro_chua_ho_tro(tmp_path):
    text = "Khám phá BÁNH TRÁNG CUỐN LÒNG ĐÀO TRỘN trên ShopeeFood nhé! https://spf.shopee.vn/AKbbczw9TO"
    assert is_shopee_food_link(text) and is_shopee_food_link("https://spf.shopee.vn/AKbbczw9TO")
    assert not is_shopee_food_link("https://s.shopee.vn/abc") and not is_shopee_food_link("xin chào")
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    reply = bot.handle_text(111, "u", text, update_id=9101, now=NOW)
    assert "Hoàn tiền ShopeeFood sắp có" in reply.text and "chưa được hoàn tiền" in reply.text
    assert "Chưa nhận ra link" not in reply.text
    assert client.calls == 0, "không gọi nguồn dữ liệu sản phẩm"
    link = urlparse(reply.button_url)
    assert (link.hostname, link.path) == ("s.shopee.vn", "/an_redir")
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT * FROM link_requests WHERE telegram_update_id = 9101").fetchone()
    assert is_valid_sub_id(row["sub_id"]) and row["telegram_user_id"] == 111 and row["platform"] == "shopeefood"
    assert parse_qs(link.query) == {"origin_link": ["https://spf.shopee.vn/AKbbczw9TO"],
                                    "affiliate_id": [bot.settings.affiliate_id], "sub_id": [row["sub_id"]]}
    assert reply.markup()["inline_keyboard"][0] == [{"text": FOOD_BUTTON, "url": reply.button_url}]
    again = bot.handle_text(111, "u", text, update_id=9101, now=NOW)  # Telegram gửi lại cùng update
    assert again.text == reply.text and again.button_url == reply.button_url
    assert row["reject_reason"] == "food_link" and "spf.shopee.vn" not in row["original_url"], "không lưu nội dung tin"
    assert row["affiliate_url"] is None
    other = bot.handle_text(111, "u", text, update_id=9103, now=NOW)
    assert f"sub_id={row['sub_id']}" not in other.button_url, "mỗi lần gửi một sub_id riêng"
    result = bot.repo.record_conversion_snapshot("food-1", row["sub_id"], "SN-food", "COMPLETED", "COMPLETED",
                                                 "2026-10-29 12:00:00", 3_000, 3_000)
    assert not result.is_matched and result.telegram_user_id is None, "đơn trùng sub_id link Food không gắn khách, không thành tiền hoàn"
    assert "Chưa nhận ra link" in bot.handle_text(111, "u", "https://example.com/x", update_id=9102, now=NOW).text


def test_dan_lai_link_bot_da_gui_thi_doc_san_pham_goc(tmp_path):
    # Khách Zalo 29/10/2026 dán lại link an_redir bot gửi hôm trước: trước đây bot hỏi AddLiveTag và báo «chưa lấy được».
    sent = build_an_redir("https://shopee.vn/product/9/8", "17300001", "Ab12Cd34")
    target = parse_shopee_target(f"Mua cái này {sent}")
    assert (target.shop_id, target.item_id, target.short_url) == (9, 8, None)
    assert target.original_url == "https://shopee.vn/product/9/8", "không lưu sub_id cũ của link"
    assert parse_shopee_target("https://s.shopee.vn/an_redir?affiliate_id=1&sub_id=x") is None
    nested = "https://s.shopee.vn/an_redir?origin_link=" + requests.utils.quote(sent, safe="")
    assert parse_shopee_target(nested) is None
    food = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fspf.shopee.vn%2F906KKy82bs&affiliate_id=1&sub_id=x"
    assert parse_shopee_target(food) is None and is_shopee_food_link(food)
    assert food_url(food) == "https://spf.shopee.vn/906KKy82bs"
    client = FakeClient(payload())
    bot = service(tmp_path, client)
    reply = bot.handle_text(111, "u", sent, update_id=9201, now=NOW)
    assert "Đã tạo link hoàn tiền" in reply.text and client.targets[-1].item_id == 8
    assert "sub_id=Ab12Cd34" not in reply.button_url, "link mới, sub_id mới"


def test_link_shopeefood_chi_ghep_link_food():
    assert food_url("Món ngon https://spf.shopee.vn/906KKy82bs.") == "https://spf.shopee.vn/906KKy82bs"
    assert food_url("http://shopeefood.vn/ho-chi-minh/quan") == "https://shopeefood.vn/ho-chi-minh/quan"
    assert food_url("https://s.shopee.vn/abc") is None and food_url("https://u:p@spf.shopee.vn/x") is None
    with pytest.raises(ValueError):
        build_food_redir("https://shopee.vn/product/1/2", "123", "Ab12Cd34")
    with pytest.raises(ValueError):
        build_food_redir("https://spf.shopee.vn/x", "abc", "Ab12Cd34")
    with pytest.raises(ValueError):
        build_food_redir("https://spf.shopee.vn/x", "123", "FOOD")
