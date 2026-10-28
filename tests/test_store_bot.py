"""Bot bán hàng (PLAN-097): tiền, kho, khóa API, webhook nạp, luồng Telegram. Không gọi mạng."""

from __future__ import annotations

import threading

import pytest
import requests as requests_lib
from fastapi.testclient import TestClient

from store_bot import messages as msg
from store_bot.api_server import create_app
from store_bot.bot import StoreBot
from store_bot.config import BankAccount, ConfigError, Settings, load_settings
from store_bot.db import StoreError, StoreRepository, unit_price
from store_bot.fulfill import Fulfiller
from store_bot.telegram_api import TelegramApi
from store_bot.upstream import DELIVERED, PENDING, REJECTED, BuyResult, FatCatClient, retail_price

ADMIN = 1
BUYER = 2
RESELLER = 3


class FakeTelegram:
    def __init__(self):
        self.sent: list[tuple] = []
        self.edits: list[tuple] = []
        self.photos: list[tuple] = []
        self.documents: list[tuple] = []
        self.answers: list[tuple] = []
        self.broadcasts: list[tuple] = []
        self.blocked_ids: set[int] = set()
        self._next_id = 100

    def send_broadcast(self, chat_id, html, reply_markup=None):
        if chat_id in self.blocked_ids:
            return "blocked", 0
        self.broadcasts.append((chat_id, html, reply_markup))
        return "ok", 0

    def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
        self._next_id += 1
        self.sent.append((chat_id, html, reply_markup))
        return self._next_id

    def edit_message_text(self, chat_id, message_id, html, reply_markup=None):
        self.edits.append((chat_id, message_id, html, reply_markup))
        return True

    def answer_callback(self, callback_query_id, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    def send_photo(self, chat_id, data, caption, reply_markup=None):
        self.photos.append((chat_id, caption))
        return True

    def send_document(self, chat_id, filename, data, caption=None):
        self.documents.append((chat_id, filename, data))
        return True

    def download_file(self, file_id, max_bytes=2_000_000):
        return b"file-1\nfile-2\n"

    def texts_to(self, chat_id) -> list[str]:
        return [html for cid, html, _ in self.sent if cid == chat_id]


def _settings(**extra) -> Settings:
    base = dict(
        bot_token="t", admin_ids=frozenset({ADMIN}), shop_name="Test Shop", channel_id="@kenh",
        bank=BankAccount("970422", "0123456789", "NGUYEN VAN A", "MB"),
        api_public_url="https://api.example.com", sepay_webhook_key="sepay-secret",
    )
    base.update(extra)
    return Settings(**base)


@pytest.fixture
def repo(tmp_path):
    repository = StoreRepository(str(tmp_path / "store.sqlite"))
    repository.migrate()
    for user_id, name in ((ADMIN, "boss"), (BUYER, "khach"), (RESELLER, "Zusem10")):
        repository.touch_user(user_id, name, name)
    return repository


@pytest.fixture
def product(repo):
    product_id = repo.add_product("Link Gemini Pro 18 tháng", 20_000, "Dùng trong 1 tiếng")
    repo.add_stock(product_id, [f"https://g.co/{i}" for i in range(5)])
    return product_id


def _private(user_id: int, text: str, username: str = "khach", **extra) -> dict:
    message = {"chat": {"id": user_id, "type": "private"}, "from": {"id": user_id, "username": username,
                                                                     "first_name": username}, "text": text}
    message.update(extra)
    return {"message": message}


def _click(user_id: int, data: str, username: str = "khach") -> dict:
    return {"callback_query": {"id": "cb", "from": {"id": user_id, "username": username},
                               "message": {"chat": {"id": user_id}, "message_id": 55}, "data": data}}


# ---------- tiền & kho ----------

def test_buy_moves_money_and_stock_together(repo, product):
    repo.adjust_balance(BUYER, 50_000, "test", "admin")
    order = repo.buy(BUYER, product, 2)
    assert order.total == 40_000
    assert order.items == ["https://g.co/0", "https://g.co/1"]
    assert order.balance_after == 10_000
    assert repo.get_user(BUYER).balance == 10_000
    assert repo.get_product(product).stock == 3


def test_failed_buy_changes_nothing(repo, product):
    repo.adjust_balance(BUYER, 30_000, "test", "admin")
    with pytest.raises(StoreError) as low:
        repo.buy(BUYER, product, 2)
    assert low.value.code == "insufficient_balance"
    assert low.value.info == {"need": 40_000, "balance": 30_000}
    with pytest.raises(StoreError) as empty:
        repo.buy(BUYER, product, 6)
    assert empty.value.code == "out_of_stock"
    assert repo.get_user(BUYER).balance == 30_000
    assert repo.get_product(product).stock == 5


def test_same_client_ref_never_charges_twice(repo, product):
    repo.adjust_balance(BUYER, 100_000, "test", "admin")
    first = repo.buy(BUYER, product, 1, client_ref="tg:abc")
    again = repo.buy(BUYER, product, 1, client_ref="tg:abc")
    assert again.replayed and again.id == first.id and again.items == first.items
    assert repo.get_user(BUYER).balance == 80_000


def test_concurrent_buys_never_oversell(repo):
    product_id = repo.add_product("Hàng hiếm", 1_000)
    repo.add_stock(product_id, ["only-one"])
    buyers = list(range(10, 18))
    for user_id in buyers:
        repo.touch_user(user_id, f"u{user_id}", None)
        repo.adjust_balance(user_id, 5_000, "test", "admin")
    results: list[str] = []

    def attempt(user_id: int) -> None:
        try:
            results.append(repo.buy(user_id, product_id, 1).items[0])
        except StoreError as exc:
            results.append(exc.code)

    threads = [threading.Thread(target=attempt, args=(u,)) for u in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("only-one") == 1
    assert results.count("out_of_stock") == len(buyers) - 1
    assert sum(repo.get_user(u).balance for u in buyers) == 5_000 * len(buyers) - 1_000


def test_add_stock_skips_duplicates_and_blank_lines(repo, product):
    added, dup, stock = repo.add_stock(product, ["https://g.co/0", "", "  new-1  ", "new-1", "new-2"])
    assert (added, dup, stock) == (2, 1, 7)


def test_topup_credits_once(repo):
    topup = repo.create_topup(BUYER, 100_000)
    assert topup.code.startswith("NAP") and len(topup.code) == 9
    _, balance, newly = repo.confirm_topup(topup.id, "admin:1")
    _, balance_again, newly_again = repo.confirm_topup(topup.id, "admin:1")
    assert (balance, newly, balance_again, newly_again) == (100_000, True, 100_000, False)
    assert repo.cancel_topup(topup.id, "admin:1") is False


def test_find_topup_in_mangled_bank_content(repo):
    topup = repo.create_topup(BUYER, 50_000)
    mangled = f"MBVCB.123 {topup.code[:4].lower()}-{topup.code[4:]} chuyen tien"
    assert repo.find_topup_in_text(mangled).id == topup.id
    assert repo.find_topup_in_text("chuyen tien an trua") is None


def test_negative_adjust_cannot_go_below_zero(repo):
    repo.adjust_balance(BUYER, 10_000, "test", "admin")
    with pytest.raises(StoreError):
        repo.adjust_balance(BUYER, -20_000, "test", "admin")
    assert repo.get_user(BUYER).balance == 10_000


# ---------- khóa API ----------

def test_reissue_key_revokes_old_and_keeps_blocks(repo, product):
    raw_old, old = repo.issue_key(RESELLER, 200)
    assert repo.toggle_block(old.id, product) is True
    raw_new, new = repo.issue_key(RESELLER, 200)
    assert repo.key_for_raw(raw_old) is None
    assert repo.key_for_raw(raw_new).id == new.id
    assert repo.blocked_products(new.id) == {product}
    assert raw_new not in str(repo.list_keys())


def test_unit_price_discount():
    assert unit_price(155_000, 200) == 151_900
    assert unit_price(19_999, 200) == 19_600  # 399,98đ giảm làm tròn xuống 399đ


@pytest.fixture
def api(repo, product):
    telegram = FakeTelegram()
    client = TestClient(create_app(_settings(), repo, telegram))
    raw, key = repo.issue_key(RESELLER, 200)
    return client, {"X-API-Key": raw}, key, telegram


def test_api_requires_valid_key(api):
    client, _, _, _ = api
    assert client.get("/api/v1/products").status_code == 401
    assert client.get("/api/v1/products", headers={"X-API-Key": "sk_wrong"}).status_code == 401


def test_api_lists_discounted_products_without_blocked(api, repo, product):
    client, headers, key, _ = api
    other = repo.add_product("Chat GPT Plus", 155_000)
    repo.toggle_block(key.id, other)
    body = client.get("/api/v1/products", headers={"Authorization": f"Bearer {headers['X-API-Key']}"}).json()
    assert [(p["id"], p["price"], p["list_price"], p["stock"]) for p in body["products"]] == [(product, 19_600, 20_000, 5)]


def test_api_order_is_idempotent_and_notifies_admin(api, repo, product):
    client, headers, _, telegram = api
    repo.adjust_balance(RESELLER, 100_000, "test", "admin")
    payload = {"product_id": product, "quantity": 2, "request_id": "r-1"}
    first = client.post("/api/v1/orders", json=payload, headers=headers)
    second = client.post("/api/v1/orders", json=payload, headers=headers)
    assert first.status_code == 200 and first.json()["total"] == 39_200
    assert second.json()["order_id"] == first.json()["order_id"] and second.json()["replayed"] is True
    assert repo.get_user(RESELLER).balance == 60_800
    assert sum("qua API" in html for html in telegram.texts_to(ADMIN)) == 1
    order_id = first.json()["order_id"]
    assert client.get(f"/api/v1/orders/{order_id}", headers=headers).json()["items"] == first.json()["items"]


def test_api_errors_have_codes(api, repo, product):
    client, headers, key, _ = api
    poor = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1}, headers=headers)
    assert poor.status_code == 402 and poor.json()["error"] == "insufficient_balance"
    repo.toggle_block(key.id, product)
    blocked = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1}, headers=headers)
    assert blocked.status_code == 403
    too_many = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1000}, headers=headers)
    assert too_many.status_code == 400


def test_sepay_webhook_credits_once_and_flags_unknown(api, repo):
    client, _, _, telegram = api
    topup = repo.create_topup(BUYER, 100_000)
    hook = {"id": 9001, "transferType": "in", "transferAmount": 100_000, "content": f"{topup.code} ck"}
    auth = {"Authorization": "Apikey sepay-secret"}
    assert client.post("/webhooks/sepay", json=hook).status_code == 401
    assert client.post("/webhooks/sepay", json=hook, headers=auth).json() == {"success": True}
    assert client.post("/webhooks/sepay", json=hook, headers=auth).status_code == 200  # SePay gửi lại
    assert repo.get_user(BUYER).balance == 100_000
    assert any("Đã cộng" in html for html in telegram.texts_to(BUYER))
    client.post("/webhooks/sepay", json={**hook, "id": 9002, "content": "khong co ma"}, headers=auth)
    assert any("không khớp" in html for html in telegram.texts_to(ADMIN))
    assert repo.get_user(BUYER).balance == 100_000


# ---------- luồng Telegram ----------

@pytest.fixture
def bot(repo):
    telegram = FakeTelegram()
    return StoreBot(_settings(), repo, telegram, "test_store_bot", executor=InlineExecutor()), telegram


def test_admin_creates_product_imports_stock_and_announces(bot, repo):
    store, telegram = bot
    store.handle_update(_click(ADMIN, "apn", "boss"))
    store.handle_update(_private(ADMIN, "Chat GPT Plus Google Pay BH1D | 155k | Bảo hành 1 ngày", "boss"))
    product = repo.list_products()[0]
    assert (product.name, product.price, product.description) == ("Chat GPT Plus Google Pay BH1D", 155_000, "Bảo hành 1 ngày")

    store.handle_update(_click(ADMIN, f"a:st:{product.id}", "boss"))
    store.handle_update(_private(ADMIN, "acc-1\nacc-2\nacc-3", "boss"))
    store.handle_update(_private(ADMIN, "acc-3\nacc-4", "boss"))
    store.handle_update(_private(ADMIN, "", "boss", document={"file_id": "f", "file_name": "kho.txt"}))
    store.handle_update(_click(ADMIN, f"a:sd:{product.id}:1", "boss"))

    channel = telegram.texts_to("@kenh")
    assert len(channel) == 1
    assert "HÀNG MỚI VỀ" in channel[0] and "Thêm: <b>6</b>" in channel[0] and "Tồn kho hiện tại: <b>6</b>" in channel[0]
    markup = [m for cid, _, m in telegram.sent if cid == "@kenh"][0]
    assert markup["inline_keyboard"][0][0]["url"] == f"https://t.me/test_store_bot?start=buy_{product.id}"


def test_customer_buys_from_channel_deep_link(bot, repo, product):
    store, telegram = bot
    repo.adjust_balance(BUYER, 50_000, "test", "admin")
    store.handle_update(_private(BUYER, f"/start buy_{product}"))
    assert "Link Gemini Pro 18 tháng" in telegram.texts_to(BUYER)[-1]

    store.handle_update(_click(BUYER, f"q:{product}:2"))
    confirm = telegram.edits[-1][3]["inline_keyboard"][0][0]["callback_data"]
    assert confirm.startswith(f"bc:{product}:2:")
    store.handle_update(_click(BUYER, confirm))
    store.handle_update(_click(BUYER, confirm))  # bấm đúp

    assert repo.get_user(BUYER).balance == 10_000
    deliveries = [html for html in telegram.texts_to(BUYER) if "https://g.co/0" in html]
    assert len(deliveries) == 1 and "https://g.co/1" in deliveries[0]
    assert telegram.answers[-1] == ("Đơn này đã mua rồi.", False)


def test_large_order_delivered_as_file(bot, repo):
    store, telegram = bot
    product_id = repo.add_product("Combo", 1_000)
    repo.add_stock(product_id, [f"tai-khoan-{i}|mat-khau-rat-dai-{i}" * 3 for i in range(60)])
    repo.adjust_balance(BUYER, 100_000, "test", "admin")
    order = repo.buy(BUYER, product_id, 60)
    store.send_items(BUYER, order)
    assert telegram.documents and telegram.documents[0][1] == f"don_{order.id}.txt"


def test_topup_sends_qr_and_admin_confirms(bot, repo):
    store, telegram = bot
    store.handle_update(_click(BUYER, "tx"))
    store.handle_update(_private(BUYER, "150k"))
    assert telegram.photos and "Nội dung: <code>NAP" in telegram.photos[0][1]
    topup = repo.pending_topups()[0]
    assert topup.amount == 150_000
    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))
    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))
    assert repo.get_user(BUYER).balance == 150_000


def test_admin_grants_key_with_expected_message(bot, repo):
    store, telegram = bot
    store.handle_update(_click(ADMIN, "akn", "boss"))
    store.handle_update(_private(ADMIN, "@zusem10", "boss"))
    text = telegram.texts_to(ADMIN)[-1]
    assert text.startswith("✅ Đã cấp khóa cho @Zusem10")
    assert "<code>sk_" in text and "Địa chỉ API: https://api.example.com" in text and "giảm 2%" in text


def test_customer_cannot_use_admin_buttons(bot, repo, product):
    store, telegram = bot
    store.handle_update(_click(BUYER, f"a:tg:{product}"))
    assert telegram.answers[-1][0] == "Không có quyền."
    assert repo.get_product(product).active is True


# ---------- phụ ----------

@pytest.mark.parametrize("text, expected", [
    ("100000", 100_000), ("100.000", 100_000), ("100k", 100_000), ("1tr", 1_000_000),
    ("1.5tr", 1_500_000), ("19.999đ", 19_999), ("abc", None), ("", None),
])
def test_parse_amount(text, expected):
    assert msg.parse_amount(text) == expected


def test_config_requires_token_and_admins():
    with pytest.raises(ConfigError):
        load_settings({"STORE_BOT_TOKEN": "x"})
    settings = load_settings({"STORE_BOT_TOKEN": "x", "STORE_ADMIN_IDS": "1, 2"})
    assert settings.admin_ids == frozenset({1, 2}) and settings.bank is None
    with pytest.raises(ConfigError):
        load_settings({"STORE_BOT_TOKEN": "x", "STORE_ADMIN_IDS": "1", "STORE_BANK_BIN": "970422"})


# ---------- nguồn FatCat ----------

FATCAT_ROWS = [
    {"id": 34, "name": "Chat GPT Plus Google Pay BH1D", "price_vnd": 151_900, "regular_price_vnd": 151_900,
     "sale_qty": 0, "stock": 44, "max_quantity": 100, "description": "BH 1 ngày"},
    {"id": 49, "name": "Link Gemini Pro 18M (Dùng Trong 8P)", "price_vnd": 18_620, "regular_price_vnd": 18_620,
     "sale_qty": 0, "stock": 7, "max_quantity": 2, "description": ""},
]


class FakeFatCat:
    def __init__(self, rows=None):
        self.rows = [dict(r) for r in (rows or FATCAT_ROWS)]
        self.results: list[BuyResult] = []
        self.calls: list[tuple] = []

    def products(self):
        return [dict(r) for r in self.rows]

    def balance(self):
        return 500_000

    def buy(self, product_id, quantity, request_id):
        self.calls.append((product_id, quantity, request_id))
        if self.results:
            return self.results.pop(0)
        return BuyResult(DELIVERED, [f"fc-{product_id}-{i}" for i in range(quantity)], "DH1", None, 200, "complete")


class InlineExecutor:
    def submit(self, fn, *args):
        fn(*args)


@pytest.fixture
def fatcat(repo):
    telegram = FakeTelegram()
    fake = FakeFatCat()
    fulfiller = Fulfiller(repo, fake, 200)
    store = StoreBot(_settings(), repo, telegram, "test_store_bot", fulfiller=fulfiller, executor=InlineExecutor())
    store.sync_upstream()
    products = {p.upstream_id: p for p in repo.list_products()}
    return store, telegram, fake, products


def test_retail_price_matches_fatcat_channel():
    assert retail_price(151_900, 200) == 155_000
    assert retail_price(20_253, 200) == 20_666
    assert retail_price(980, 200) == 1_000


def test_migrate_twice_is_safe(repo):
    repo.migrate()
    repo.migrate()


def test_sync_lists_fatcat_products_at_retail_price(fatcat, repo):
    _, telegram, fake, products = fatcat
    gpt = products[34]
    assert (gpt.price, gpt.cost, gpt.stock, gpt.on_sale) == (155_000, 151_900, 44, True)
    assert telegram.texts_to("@kenh") == []  # lần đồng bộ đầu không đăng kênh

    fake.rows = [FATCAT_ROWS[0]]  # FatCat ngừng bán món 49
    fatcat[0].sync_upstream()
    assert [p.upstream_id for p in repo.list_products()] == [34]


def test_restock_is_announced_once(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.rows[0]["stock"] = 44 + 34
    fake.rows[1]["stock"] = 8  # +1: dưới ngưỡng 5 và trước đó còn hàng → không đăng
    store.sync_upstream()
    channel = telegram.texts_to("@kenh")
    assert len(channel) == 1
    assert "Chat GPT Plus Google Pay BH1D" in channel[0] and "Thêm: <b>34</b>" in channel[0]
    assert "Tồn kho hiện tại: <b>78</b>" in channel[0] and "155.000đ" in channel[0]
    fake.rows[0]["stock"] = 100
    store.sync_upstream()  # chưa đủ 20 phút
    assert len(telegram.texts_to("@kenh")) == 1


def test_bot_buy_from_fatcat_delivers_items(fatcat, repo):
    store, telegram, fake, products = fatcat
    repo.adjust_balance(BUYER, 400_000, "test", "admin")
    gpt = products[34]
    store.handle_update(_click(BUYER, f"q:{gpt.id}:2"))
    confirm = telegram.edits[-1][3]["inline_keyboard"][0][0]["callback_data"]
    store.handle_update(_click(BUYER, confirm))
    store.handle_update(_click(BUYER, confirm))  # bấm đúp

    assert len(fake.calls) == 1 and fake.calls[0][:2] == (34, 2)
    assert repo.get_user(BUYER).balance == 90_000
    deliveries = [h for h in telegram.texts_to(BUYER) if "fc-34-0" in h]
    assert len(deliveries) == 1 and "fc-34-1" in deliveries[0]
    assert repo.get_product(gpt.id).stock == 42


def test_partial_delivery_refunds_missing(fatcat, repo):
    store, telegram, fake, products = fatcat
    repo.adjust_balance(BUYER, 40_000, "test", "admin")
    gem = products[49]
    fake.results = [BuyResult(DELIVERED, ["only-one"], "DH2", None, 200, "partial")]
    order = repo.buy(BUYER, gem.id, 2, client_ref="tg:p")
    store._fulfill_now(order.id, BUYER, None)
    done = repo.get_order(order.id)
    assert (done.status, done.items, done.refunded) == ("partial", ["only-one"], 19_000)
    assert repo.get_user(BUYER).balance == 40_000 - 19_000
    assert any("chỉ giao 1/2" in h for h in telegram.texts_to(BUYER))


def test_fatcat_wallet_empty_refunds_and_alerts_admin(fatcat, repo):
    store, telegram, fake, products = fatcat
    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    fake.results = [BuyResult(REJECTED, status_code=402, message="Số dư không đủ.")]
    order = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(order.id, BUYER, None)
    assert repo.get_order(order.id).status == "failed"
    assert repo.get_user(BUYER).balance == 200_000
    assert any("chưa lấy được hàng" in h for h in telegram.texts_to(BUYER))
    assert any("Ví FatCat không đủ tiền" in h for h in telegram.texts_to(ADMIN))


def test_slow_source_retried_with_same_request_id(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.RETRY_AFTER_SEC", 0)
    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    fake.results = [BuyResult(PENDING, status_code=202), BuyResult(PENDING, message="ReadTimeout")]
    order = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(order.id, BUYER, None)
    store.retry_pending()
    assert repo.get_order(order.id).status == "pending"
    store.retry_pending()  # lần này FatCat giao
    store.retry_pending()
    assert repo.get_order(order.id).status == "done"
    assert len({call[2] for call in fake.calls}) == 1 and len(fake.calls) == 3
    assert sum("fc-34-0" in h for h in telegram.texts_to(BUYER)) == 1
    assert repo.get_user(BUYER).balance == 45_000


def test_api_reseller_never_below_cost_and_gets_202(fatcat, repo):
    store, telegram, fake, products = fatcat
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller))
    raw, _ = repo.issue_key(RESELLER, 500)  # giảm 5% > biên 2%
    headers = {"X-API-Key": raw}
    listed = {p["id"]: p for p in client.get("/api/v1/products", headers=headers).json()["products"]}
    assert listed[products[34].id]["price"] == 151_900 and listed[products[49].id]["max_quantity"] == 2

    repo.adjust_balance(RESELLER, 500_000, "test", "admin")
    fake.results = [BuyResult(PENDING, status_code=202)]
    body = {"product_id": products[34].id, "quantity": 1, "request_id": "dl-1"}
    first = client.post("/api/v1/orders", json=body, headers=headers)
    assert first.status_code == 202 and first.json()["status"] == "pending"
    again = client.post("/api/v1/orders", json=body, headers=headers)
    assert again.status_code == 200 and again.json()["items"] == ["fc-34-0"]
    assert repo.get_user(RESELLER).balance == 500_000 - 151_900


def test_fatcat_client_maps_http_codes(monkeypatch):
    class Resp:
        def __init__(self, code, payload):
            self.status_code, self._payload, self.text = code, payload, ""

        def json(self):
            return self._payload

    replies = []
    monkeypatch.setattr("store_bot.upstream.requests.post", lambda *a, **k: replies.pop(0)())
    client = FatCatClient("https://x", "mb_test")
    order = {"id": "DH9", "items": ["a"], "price": 1, "fulfillment": "complete"}
    replies += [
        lambda: Resp(200, {"order": order}),
        lambda: Resp(202, {"order": {**order, "fulfillment": "pending"}}),
        lambda: Resp(402, {"error": True, "message": "Số dư không đủ."}),
        lambda: Resp(503, {}),
        lambda: (_ for _ in ()).throw(requests_lib.ReadTimeout()),
    ]
    kinds = [client.buy(1, 1, "r") for _ in range(5)]
    assert [k.kind for k in kinds] == [DELIVERED, PENDING, REJECTED, PENDING, PENDING]
    assert kinds[0].items == ["a"] and kinds[2].message == "Số dư không đủ."


def test_typing_number_on_product_and_topup_screens(bot, repo, product):
    store, telegram = bot
    repo.adjust_balance(BUYER, 50_000, "test", "admin")
    store.handle_update(_click(BUYER, f"p:{product}"))
    store.handle_update(_private(BUYER, "1"))  # gõ thẳng số lượng
    assert "Xác nhận mua" in telegram.texts_to(BUYER)[-1]

    store.handle_update(_click(BUYER, "top"))
    store.handle_update(_private(BUYER, "10000"))  # gõ thẳng số tiền
    assert repo.pending_topups()[0].amount == 10_000
    assert telegram.photos and "Nạp 10.000đ" in telegram.photos[-1][1]

    store.handle_update(_click(BUYER, "top"))
    store.handle_update(_private(BUYER, "xin chào"))  # chữ thường → về trang chủ, không bắt gõ lại
    assert "Xin chào" in telegram.texts_to(BUYER)[-1]


def test_stats_show_cash_flow_and_profit(fatcat, repo):
    store, telegram, fake, products = fatcat
    topup = repo.create_topup(BUYER, 400_000)
    repo.confirm_topup(topup.id, "admin:1")
    good = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(good.id, BUYER, None)
    fake.results = [BuyResult(REJECTED, status_code=402, message="Số dư không đủ.")]
    bad = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(bad.id, BUYER, None)

    stats = repo.stats()
    assert (stats["topup_today"], stats["orders_today"], stats["revenue_today"]) == (400_000, 1, 155_000)
    assert (stats["cost_today"], stats["profit_today"], stats["refunded_today"]) == (151_900, 3_100, 155_000)
    store.handle_update(_click(ADMIN, "al", "boss"))
    ledger = telegram.edits[-1][2]
    assert "↩️ Hoàn" in ledger and "🛒 Mua" in ledger and "💰 Nạp" in ledger


def test_start_sends_persistent_menu_and_menu_buttons_work(bot, repo, product):
    store, telegram = bot
    store.handle_update(_private(BUYER, "/start"))
    welcome = [(html, markup) for cid, html, markup in telegram.sent if cid == BUYER and "Hướng dẫn nhanh" in html]
    assert welcome and welcome[0][1]["keyboard"][0][0]["text"] == msg.MENU_SHOP
    assert "⚙️" not in str(welcome[0][1])  # khách thường không thấy nút quản lý

    store.handle_update(_private(BUYER, msg.MENU_SHOP))
    assert "Sản phẩm" in telegram.texts_to(BUYER)[-1]
    store.handle_update(_private(BUYER, msg.MENU_WALLET))
    assert "Ví của bạn" in telegram.texts_to(BUYER)[-1]
    store.handle_update(_private(BUYER, msg.MENU_SUPPORT))
    assert "Telegram: @boss" in telegram.texts_to(BUYER)[-1]  # chưa cài liên hệ → dùng @admin


def test_deep_link_sends_menu_only_once(bot, repo, product):
    store, telegram = bot
    store.handle_update(_private(BUYER, f"/start buy_{product}"))
    store.handle_update(_private(BUYER, f"/start buy_{product}"))
    assert sum("Hướng dẫn nhanh" in h for h in telegram.texts_to(BUYER)) == 1


def test_pay_by_qr_buys_automatically_after_admin_confirms(fatcat, repo):
    store, telegram, fake, products = fatcat
    gem = products[49]  # 19.000đ
    repo.adjust_balance(BUYER, 5_000, "test", "admin")
    store.handle_update(_click(BUYER, f"q:{gem.id}:1"))
    pay = telegram.edits[-1][3]["inline_keyboard"][0][0]
    assert pay["text"] == "📱 Thanh toán QR 14.000đ" and pay["callback_data"] == f"bq:{gem.id}:1"

    store.handle_update(_click(BUYER, pay["callback_data"]))
    assert "Thanh toán 14.000đ" in telegram.photos[-1][1] and "tự gửi hàng" in telegram.photos[-1][1]
    topup = repo.pending_topups()[0]
    assert (topup.amount, topup.intent_product_id, topup.intent_quantity) == (14_000, gem.id, 1)
    assert any("Để mua" in h for h in telegram.texts_to(ADMIN))

    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))
    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))  # bấm đúp không mua hai lần
    assert len(fake.calls) == 1
    assert repo.get_user(BUYER).balance == 0
    assert sum("fc-49-0" in h for h in telegram.texts_to(BUYER)) == 1


def test_sepay_payment_with_intent_buys_automatically(fatcat, repo):
    store, telegram, fake, products = fatcat
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller))
    gem = products[49]
    topup = repo.create_topup(BUYER, 19_000, gem.id, 1)
    hook = {"id": 7001, "transferType": "in", "transferAmount": 19_000, "content": topup.code}
    client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    assert repo.get_user(BUYER).balance == 0
    assert len(repo.list_orders(BUYER)) == 1


def test_restock_is_sent_to_every_bot_user_like_fatcat(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.BROADCAST_DELAY_SEC", 0)
    fake.rows[0]["stock"] = 80
    store.sync_upstream()
    receivers = sorted(cid for cid, _, _ in telegram.broadcasts)
    assert receivers == [ADMIN, BUYER, RESELLER]
    _, html, markup = telegram.broadcasts[0]
    assert "HÀNG MỚI VỀ" in html and "Thêm: <b>36</b>" in html
    assert markup["inline_keyboard"][0][0] == {"text": "🛒 Mua ngay", "callback_data": f"p:{products[34].id}"}
    assert any("Đã báo hàng mới" in h for h in telegram.texts_to(ADMIN))


def test_opt_out_blocked_and_admin_switch(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.BROADCAST_DELAY_SEC", 0)
    store.handle_update(_click(BUYER, "noff"))
    assert telegram.answers[-1] == (msg.NOTIFY_OFF_DONE, True)
    telegram.blocked_ids = {RESELLER}
    store.broadcast_restock(products[34].id, 5)
    assert [cid for cid, _, _ in telegram.broadcasts] == [ADMIN]
    assert repo.broadcast_targets() == [ADMIN]  # khách chặn bot bị bỏ khỏi danh sách

    store.handle_update(_private(RESELLER, "/start"))  # quay lại bot → nhận tin lại
    store.handle_update(_click(BUYER, "ntog"))  # bật lại ở Hồ sơ
    assert repo.broadcast_targets() == [ADMIN, BUYER, RESELLER]

    store.handle_update(_click(ADMIN, "abt", "boss"))  # admin tắt nhắn khách
    telegram.broadcasts.clear()
    fake.rows[0]["stock"] = 200
    store.sync_upstream()
    assert telegram.broadcasts == [] and len(telegram.texts_to("@kenh")) == 1


def test_supportadmin_once_per_day(bot, repo):
    store, telegram = bot
    store.handle_update(_private(BUYER, "/supportadmin"))
    store.handle_update(_click(BUYER, "callme"))
    assert sum("nhờ admin nhắn" in h for h in telegram.texts_to(ADMIN)) == 1
    assert telegram.texts_to(BUYER)[-2] == msg.CALLBACK_DONE
    assert telegram.texts_to(BUYER)[-1] == msg.CALLBACK_ALREADY


def test_brand_icons_follow_product_name(bot, repo):
    assert msg.brand_of("Capcut Pro 30D BHF acc cấp").key == "capcut"
    assert msg.brand_of("Chat GPT Plus Google Pay BH1D").key == "chatgpt"
    assert msg.brand_of("Slot Microsoft Office 365 12 tháng BHF").key == "office"
    assert msg.brand_of("Link Duolingo Super 12 tháng KBH").key == "duolingo"
    assert msg.brand_of("Hàng lạ") is None and msg.icon("Hàng lạ") == msg.DEFAULT_ICON
    store, telegram = bot
    repo.add_stock(repo.add_product("Capcut Pro 30D", 50_000), ["acc-1"])
    store.handle_update(_click(BUYER, "shop"))
    first = telegram.edits[-1][3]["inline_keyboard"][0][0]
    assert first["text"].startswith("🎬 Capcut Pro 30D") and "icon_custom_emoji_id" not in first


def test_admin_sets_real_brand_logo(bot, repo):
    store, telegram = bot
    capcut = next(i for i, b in enumerate(msg.BRANDS) if b.key == "capcut")
    repo.add_stock(repo.add_product("Capcut Pro 30D", 50_000), ["acc-1"])
    store.handle_update(_click(ADMIN, f"a:ic:{capcut}", "boss"))
    store.handle_update(_private(ADMIN, "chữ thường", "boss"))
    assert telegram.texts_to(ADMIN)[-1] == msg.ICON_NOT_FOUND
    store.handle_update(_private(ADMIN, "🎬", "boss",
                                 entities=[{"type": "custom_emoji", "offset": 0, "length": 2,
                                            "custom_emoji_id": "5368324170671202286"}]))
    assert repo.get_state("icon:capcut") == "5368324170671202286"
    assert "Đã gắn logo" in telegram.texts_to(ADMIN)[-1]

    store.handle_update(_click(BUYER, "shop"))
    first = telegram.edits[-1][3]["inline_keyboard"][0][0]
    assert first == {"text": "Capcut Pro 30D · 50.000đ · còn 1", "callback_data": first["callback_data"],
                     "icon_custom_emoji_id": "5368324170671202286"}
    product = repo.list_products()[0]
    assert '<tg-emoji emoji-id="5368324170671202286">🎬</tg-emoji>' in msg.product_detail(product, 0)
    assert "tg-emoji" not in msg.restock_announcement(product, 5)  # kênh + gửi hàng loạt: emoji thường

    StoreBot(_settings(), repo, FakeTelegram(), "test_store_bot")  # khởi động lại vẫn nhớ logo
    assert msg.icon_id("Capcut Pro 30D") == "5368324170671202286"
    store.handle_update(_click(ADMIN, f"a:icx:{capcut}", "boss"))
    assert repo.get_state("icon:capcut") is None and msg.icon_id("Capcut Pro 30D") is None


def test_rejected_custom_emoji_is_resent_plain(monkeypatch):
    calls = []

    class Response:
        status_code = 400

        def __init__(self, body):
            self.body = body

        def json(self):
            if "tg-emoji" in self.body["text"] or "icon_custom_emoji_id" in str(self.body):
                return {"ok": False, "description": "Bad Request: custom emoji not allowed"}
            return {"ok": True, "result": {"message_id": 7}}

    def fake_post(url, json=None, **_):
        calls.append(json)
        return Response(json)

    monkeypatch.setattr("store_bot.telegram_api.requests.post", fake_post)
    api = TelegramApi("t")
    markup = {"inline_keyboard": [[{"text": "Capcut", "callback_data": "p:1", "icon_custom_emoji_id": "1"}]]}
    assert api.send_message(1, '<tg-emoji emoji-id="1">🎬</tg-emoji> Capcut', markup) == 7
    assert calls[-1]["text"] == "🎬 Capcut"
    assert calls[-1]["reply_markup"] == {"inline_keyboard": [[{"text": "Capcut", "callback_data": "p:1"}]]}
