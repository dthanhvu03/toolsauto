"""Bot bán hàng (PLAN-097): tiền, kho, khóa API, webhook nạp, luồng Telegram. Không gọi mạng."""

from __future__ import annotations

import threading

import pytest
import requests as requests_lib
from fastapi.testclient import TestClient

from store_bot import messages as msg
from store_bot import pricing
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
    client = TestClient(create_app(_settings(), repo, telegram, executor=InlineExecutor()))
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
    no_id = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1}, headers=headers)
    assert no_id.status_code == 422  # thiếu request_id: không cho mua (gọi lại khi mạng chập sẽ thành 2 đơn)
    poor = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1, "request_id": "e1"},
                       headers=headers)
    assert poor.status_code == 402 and poor.json()["error"] == "insufficient_balance"
    repo.toggle_block(key.id, product)
    blocked = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1, "request_id": "e2"},
                          headers=headers)
    assert blocked.status_code == 403
    too_many = client.post("/api/v1/orders", json={"product_id": product, "quantity": 1000, "request_id": "e3"},
                           headers=headers)
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
        self.funds = 500_000

    def products(self):
        return [dict(r) for r in self.rows]

    def balance(self):
        return self.funds

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


def test_fatcat_402_keeps_order_waiting_then_delivers_after_admin_tops_up(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.WAITING_FUNDS_CHECK_SEC", 0)
    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    fake.results = [BuyResult(REJECTED, status_code=402, message="Số dư không đủ.")]
    fake.funds = 1_000
    order = repo.buy(BUYER, products[34].id, 1)  # số ví cũ còn đủ → gọi FatCat, FatCat báo 402
    store._fulfill_now(order.id, BUYER, None)
    waiting = repo.get_order(order.id)
    assert (waiting.status, waiting.waiting_funds, waiting.refunded) == ("pending", True, 0)
    assert repo.get_user(BUYER).balance == 200_000 - 155_000  # không hoàn, giữ đơn
    assert any("shop đang nhập hàng" in h for h in telegram.texts_to(BUYER))
    assert any("chờ anh nạp ví FatCat" in h and "nạp thêm ít nhất" in h for h in telegram.texts_to(ADMIN))

    store.retry_pending()  # ví vẫn thiếu → không gọi FatCat lần nữa
    assert len(fake.calls) == 1
    fake.funds = 300_000  # anh nạp ví
    store.retry_pending()
    assert len(fake.calls) == 2 and fake.calls[1][2] != fake.calls[0][2]  # request_id mới
    assert repo.get_order(order.id).status == "done"
    assert any("fc-34-0" in h for h in telegram.texts_to(BUYER))


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
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
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
    fake.results = [BuyResult(REJECTED, status_code=409, message="Hết hàng.")]
    bad = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(bad.id, BUYER, None)

    stats = repo.stats()
    assert (stats["topup_today"], stats["orders_today"], stats["revenue_today"]) == (400_000, 1, 155_000)
    assert (stats["cost_today"], stats["profit_today"], stats["refunded_today"]) == (151_900, 3_100, 155_000)
    store.handle_update(_click(ADMIN, "al", "boss"))
    ledger = telegram.edits[-1][2]
    assert "↩️ Hoàn" in ledger and "🛒 Mua" in ledger and "💰 Nạp" in ledger


def test_cashflow_screen_shows_margin_and_customer_money(fatcat, repo):
    store, telegram, fake, products = fatcat
    topup = repo.create_topup(BUYER, 400_000)
    repo.confirm_topup(topup.id, "admin:1")
    good = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(good.id, BUYER, None)
    repo.adjust_balance(BUYER, 5_000, "tặng", "admin:1")

    cf = repo.cashflow(1)
    total = cf["total"]
    assert (total["cash_in"], total["revenue"], total["cost"], total["profit"]) == (400_000, 155_000, 151_900, 3_100)
    assert total["adjust"] == 5_000 and cf["previous"]["revenue"] == 0 and cf["buckets"] == []
    week = repo.cashflow(7)
    assert week["unit"] == "day" and len(week["buckets"]) == 7 and week["buckets"][0]["cash_in"] == 400_000
    month = repo.cashflow(30)
    assert month["unit"] == "week" and len(month["buckets"]) == 5 and month["buckets"][0]["profit"] == 3_100
    assert repo.cashflow(None)["unit"] == "month" and repo.cashflow(None)["total"]["profit"] == 3_100
    assert cf["balances"] == 400_000 - 155_000 + 5_000 and cf["top"][0]["profit"] == 3_100

    store.handle_update(_click(ADMIN, "acf30", "boss"))
    text, markup = telegram.edits[-1][2], telegram.edits[-1][3]
    assert "DÒNG TIỀN & BIÊN LÃI · 30 NGÀY" in text and "Biên lãi gộp" in text and "2,0%" in text
    assert "+248.100" in text and "250.000" in text and "admin cộng/trừ tay +5.000đ" in text
    assert "• 30 ngày •" in str(markup)
    store.handle_update(_click(BUYER, "acf"))  # khách bấm mã admin → không có quyền, không lộ số liệu
    assert all("Dòng tiền" not in t for t in telegram.texts_to(BUYER))


def test_admin_records_outside_expense_and_profit_drops(fatcat, repo):
    store, telegram, fake, products = fatcat
    topup = repo.create_topup(BUYER, 155_000)
    repo.confirm_topup(topup.id, "admin:1")
    good = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(good.id, BUYER, None)

    store.handle_update(_click(ADMIN, "axn", "boss"))
    store.handle_update(_private(ADMIN, "chào", "boss"))  # sai mẫu → hỏi lại, không ghi
    assert repo.recent_expenses() == []
    store.handle_update(_private(ADMIN, f"52k bù khách đơn #{good.id} key lỗi", "boss"))
    [row] = repo.recent_expenses()
    assert (row["amount"], row["order_id"]) == (52_000, good.id)
    total = repo.cashflow(None)["total"]
    assert (total["profit"], total["expense"], total["net"]) == (3_100, 52_000, -48_900)
    assert repo.stats()["profit_all"] == -48_900
    report = telegram.texts_to(ADMIN)[-1]
    assert "Lãi ròng" in report and "−48.900" in report and "Chi ngoài" in report
    assert repo.get_user(BUYER).balance == 0  # không đụng ví khách

    store.handle_update(_click(ADMIN, f"a:xd:{row['id']}", "boss"))
    assert repo.recent_expenses() == [] and repo.stats()["profit_all"] == 3_100
    store.handle_update(_click(BUYER, "axn"))
    assert repo.get_state(f"await:{BUYER}") is None


def test_admin_wallet_separated_and_fatcat_capital_reconciled(fatcat, repo):
    store, telegram, fake, products = fatcat
    for who, amount in ((BUYER, 155_000), (ADMIN, 200_000)):
        topup = repo.create_topup(who, amount)
        repo.confirm_topup(topup.id, "admin:1")
        order = repo.buy(who, products[34].id, 1)
        store._fulfill_now(order.id, who, None)

    cf = repo.cashflow(None, admins={ADMIN})
    assert (cf["total"]["cash_in"], cf["total"]["revenue"], cf["total"]["orders"]) == (155_000, 155_000, 1)
    assert (cf["admin"]["cash_in"], cf["admin"]["revenue"], cf["admin"]["cost"]) == (200_000, 155_000, 151_900)
    assert (cf["balances"], cf["admin_balance"]) == (0, 45_000)
    assert cf["capital_used"] == 2 * 151_900 and cf["capital"] == 0
    assert repo.stats({ADMIN})["revenue_all"] == 155_000 and repo.stats()["revenue_all"] == 310_000

    store.handle_update(_click(ADMIN, "avn", "boss"))
    store.handle_update(_private(ADMIN, "abc", "boss"))
    assert repo.capital_total() == 0
    store.handle_update(_private(ADMIN, "400k nạp qua MB", "boss"))
    store.handle_update(_click(ADMIN, "avn", "boss"))
    store.handle_update(_private(ADMIN, "-50k rút về", "boss"))
    assert repo.capital_total() == 350_000
    report = telegram.texts_to(ADMIN)[-1]
    assert "Ví admin" in report and "Anh tự nạp vào ví" in report and "Vốn FatCat" in report
    assert "Anh đã ghi nạp" in report and "Lẽ ra còn" in report

    store.handle_update(_click(ADMIN, "avl", "boss"))
    rows = repo.recent_capital()
    store.handle_update(_click(ADMIN, f"a:vd:{rows[0]['id']}", "boss"))
    assert repo.capital_total() == 400_000
    store.handle_update(_click(BUYER, "avn"))
    assert repo.get_state(f"await:{BUYER}") is None


def test_admin_home_groups_and_every_hub_button_works(fatcat, repo):
    store, telegram, fake, products = fatcat
    repo.create_topup(BUYER, 50_000)  # 1 yêu cầu nạp chờ duyệt → hiện ở «Cần xử lý» + nút tắt
    store.handle_update(_click(ADMIN, "adm", "boss"))
    text, markup = telegram.edits[-1][2], telegram.edits[-1][3]
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert "QUẢN LÝ SHOP" in text and "Đang mở cửa" in text and "1</b> yêu cầu nạp chờ duyệt" in text
    assert labels[:1] == ["💳 Duyệt nạp (1)"] and {"💰 Tài chính", "📦 Hàng hoá", "👥 Khách & đại lý"} <= set(labels)

    titles = {"agf": "TÀI CHÍNH", "agp": "HÀNG HOÁ", "agc": "KHÁCH & ĐẠI LÝ"}
    for hub, title in titles.items():
        store.handle_update(_click(ADMIN, hub, "boss"))
        assert title in telegram.edits[-1][2]
        hub_buttons = [b["callback_data"] for row in telegram.edits[-1][3]["inline_keyboard"] for b in row]
        assert hub_buttons[-1] == "adm"
        for data in hub_buttons:
            if data == "abt":
                continue  # bật/tắt — thử riêng bên dưới
            before = len(telegram.edits)
            store.handle_update(_click(ADMIN, data, "boss"))
            assert len(telegram.edits) > before, data  # nút nào cũng mở được màn
            assert "Không có quyền" not in str(telegram.answers[-1:]), data
            store._clear_await(ADMIN)
    on = store.restock_dm_enabled()
    store.handle_update(_click(ADMIN, "abt", "boss"))
    assert store.restock_dm_enabled() != on and "KHÁCH & ĐẠI LÝ" in telegram.edits[-1][2]
    store.handle_update(_click(BUYER, "agf"))
    assert telegram.answers[-1][0] == "Không có quyền."


def test_fatcat_wallet_reconciles_itself(fatcat, repo):
    from datetime import datetime, timedelta, timezone
    store, telegram, fake, products = fatcat  # fixture đã đồng bộ → mốc = 500.000đ
    later = lambda sec: datetime.now(timezone.utc) + timedelta(seconds=sec)  # noqa: E731

    topup = repo.create_topup(BUYER, 155_000)
    repo.confirm_topup(topup.id, "admin:1")
    order = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(order.id, BUYER, None)  # bot mua 151.900đ — ngay sau đó chưa «yên» nên chưa đối chiếu
    assert repo.recent_capital() == []
    assert repo.reconcile_funds(500_000 - 151_900, later(300)) is None  # khớp đơn bot → không ghi gì

    nap = repo.reconcile_funds(500_000 - 151_900 + 200_000, later(600))  # anh nạp 200k
    assert repo.get_capital(nap)["amount"] == 200_000
    mua = repo.reconcile_funds(500_000 - 151_900 + 200_000 - 49_000, later(900))  # anh mua thẳng 49k
    assert repo.get_capital(mua)["amount"] == -49_000
    base = 500_000 - 151_900 + 200_000 - 49_000
    assert repo.reconcile_funds(base - 600, later(1200)) is None  # lệch nhỏ: cộng dồn
    small = repo.reconcile_funds(base - 1_200, later(1500))
    assert repo.get_capital(small)["amount"] == -1_200
    assert repo.reconcile_funds(base + 999_999, later(1400)) is None  # số đọc cũ hơn mốc → bỏ qua

    fake.results = [BuyResult(PENDING, status_code=202)]
    repo.adjust_balance(BUYER, 155_000, "test", "admin")
    pending = repo.buy(BUYER, products[34].id, 1)
    store._fulfill_now(pending.id, BUYER, None)  # đơn đang gọi FatCat (202) → không đối chiếu
    assert repo.reconcile_funds(1, later(3600)) is None

    store.notify_auto_capital()
    notices = telegram.texts_to(ADMIN)
    assert any("Ví FatCat tăng +200.000đ" in t for t in notices) and any("FatCat trừ 49.000đ" in t for t in notices)
    store.notify_auto_capital()  # báo một lần
    assert len(telegram.texts_to(ADMIN)) == len(notices)
    store.handle_update(_click(ADMIN, f"a:vx:{mua}", "boss"))
    store.handle_update(_click(ADMIN, f"a:vx:{mua}", "boss"))  # bấm lại không ghi 2 lần
    assert [e["amount"] for e in repo.recent_expenses()] == [49_000]
    assert repo.capital_total() == 200_000 - 49_000 - 1_200


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
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
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

    def fake_post(_session, url, json=None, **_):
        calls.append(json)
        return Response(json)

    monkeypatch.setattr("store_bot.telegram_api.requests.Session.post", fake_post)
    api = TelegramApi("t")
    markup = {"inline_keyboard": [[{"text": "Capcut", "callback_data": "p:1", "icon_custom_emoji_id": "1"}]]}
    assert api.send_message(1, '<tg-emoji emoji-id="1">🎬</tg-emoji> Capcut', markup) == 7
    assert calls[-1]["text"] == "🎬 Capcut"
    assert calls[-1]["reply_markup"] == {"inline_keyboard": [[{"text": "Capcut", "callback_data": "p:1"}]]}


def test_markup_parse_and_math():
    assert pricing.parse("10%", msg.parse_amount) == pricing.Markup("pct", 1_000)
    assert pricing.parse("7,5", msg.parse_amount) == pricing.Markup("pct", 750)
    assert pricing.parse("5.000", msg.parse_amount) == pricing.Markup("vnd", 5_000)
    assert pricing.parse("+3k", msg.parse_amount) == pricing.Markup("vnd", 3_000)
    assert pricing.parse("300%", msg.parse_amount) is None and pricing.parse("abc", msg.parse_amount) is None
    assert pricing.sell_price(20_253, 200, pricing.NO_MARKUP) == 20_666
    assert pricing.sell_price(20_253, 200, pricing.Markup("pct", 1_000)) == 23_000  # làm tròn lên 1.000đ
    assert pricing.sell_price(20_253, 200, pricing.Markup("vnd", 5_000)) == 25_666
    assert pricing.decode(pricing.Markup("pct", 1_500).code) == pricing.Markup("pct", 1_500)


def test_admin_previews_markup_before_applying(fatcat, repo):
    store, telegram, fake, products = fatcat
    gpt = products[34]
    repo.adjust_balance(BUYER, 400_000, "test", "admin")
    repo.buy(BUYER, gpt.id, 2)
    store.fulfiller.attempt(repo.list_orders(BUYER)[0].id)

    store.handle_update(_click(ADMIN, "amk", "boss"))
    assert "Đang dùng cho mọi món: <b>giữ giá lẻ FatCat</b>" in telegram.edits[-1][2]
    store.handle_update(_click(ADMIN, "a:mkp:0:p1000", "boss"))
    preview = telegram.edits[-1][2]
    assert "Chưa áp dụng" in preview and "Bán 155.000đ → <b>171.000đ</b>" in preview
    assert "lãi <b>19.100đ</b>/món" in preview
    assert "Khách trả: 310.000đ → <b>342.000đ</b>" in preview and "(2 món)" in preview
    assert "Lãi: 6.200đ → <b>38.200đ</b> (+32.000đ)" in preview
    assert repo.get_product(gpt.id).price == 155_000  # xem trước không đổi gì

    store.handle_update(_click(ADMIN, "a:mka:0:p1000", "boss"))
    assert "Đổi giá 2 món" in telegram.edits[-1][2]
    assert repo.get_product(gpt.id).price == 171_000
    store.handle_update(_click(ADMIN, "amk", "boss"))  # xem lại: giá FatCat → giá đang bán + mức đã tăng
    assert "FatCat 155.000đ → <b>171.000đ</b> (+10%) · lãi 19.100đ" in telegram.edits[-1][2]
    store.handle_update(_click(ADMIN, f"a:p:{gpt.id}", "boss"))
    assert "Giá lẻ FatCat 155.000đ · bạn tăng: <b>+10%</b>" in telegram.edits[-1][2]
    store.sync_upstream()  # đồng bộ FatCat vẫn giữ mức tăng
    assert repo.get_product(gpt.id).price == 171_000


def test_admin_sets_own_markup_for_one_product(fatcat, repo):
    store, telegram, fake, products = fatcat
    gpt, other = products[34], products[49]
    store.handle_update(_click(ADMIN, f"a:mkx:{gpt.id}", "boss"))
    store.handle_update(_private(ADMIN, "5k", "boss"))
    assert "Giá riêng" in telegram.texts_to(ADMIN)[-1] and "<b>160.000đ</b>" in telegram.texts_to(ADMIN)[-1]
    store.handle_update(_click(ADMIN, f"a:mka:{gpt.id}:v5000", "boss"))
    store.handle_update(_click(ADMIN, "a:mka:0:p2000", "boss"))  # đổi mức chung: món có giá riêng giữ nguyên
    store.handle_update(_click(ADMIN, "amk", "boss"))
    assert "FatCat 155.000đ → <b>160.000đ</b> (🔒 +5.000đ)" in telegram.edits[-1][2]
    assert "1 món có giá riêng" in telegram.edits[-1][2]
    assert repo.get_product(gpt.id).price == 160_000
    assert repo.get_product(other.id).price == pricing.sell_price(other.cost, 200, pricing.Markup("pct", 2_000))
    store.handle_update(_click(ADMIN, f"a:mka:{gpt.id}:x", "boss"))  # bỏ giá riêng → theo mức chung +20%
    assert repo.get_product(gpt.id).price == 186_000
    store.handle_update(_click(BUYER, "a:mka:0:p0"))
    assert telegram.answers[-1][0] == "Không có quyền." and repo.get_product(gpt.id).price == 186_000


def test_start_source_counts_new_customers_once(bot, repo, product):
    """PLAN-153: ?start=live / buy_<id> ghi nguồn khách mới một lần; khách cũ và mã lạ không tính."""
    store, telegram = bot
    NEWBIE = 900_001  # chưa từng /start (BUYER có sẵn trong fixture)
    store.handle_update(_private(NEWBIE, "/start live"))
    store.handle_update(_private(NEWBIE, "/start video"))
    store.handle_update(_private(NEWBIE + 1, f"/start buy_{product}"))
    store.handle_update(_private(NEWBIE + 2, "/start"))
    store.handle_update(_private(NEWBIE + 2, "/start live"))
    store.handle_update(_private(NEWBIE + 3, "/start Bad-Code!"))
    assert repo.get_state(f"src:{NEWBIE}") == "live"
    assert repo.get_state(f"src:{NEWBIE + 2}") is None and repo.get_state(f"src:{NEWBIE + 3}") is None
    assert repo.source_counts() == [("kenh", 1), ("live", 1)]
    assert "theo nguồn: kenh 1 · live 1" in msg.admin_stats(repo.stats(), None, repo.source_counts())


# ---------- ví FatCat thiếu, mã QR, bảo hành (06/11) ----------

def test_low_fatcat_wallet_still_sells_and_order_waits(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.WAITING_FUNDS_CHECK_SEC", 0)
    fake.funds = 100_000  # đủ nhập Gemini (18.620đ), không đủ GPT (151.900đ)
    store.sync_upstream()
    store.sync_upstream()  # danh sách món thiếu ví không đổi → không báo lại
    alerts = [h for h in telegram.texts_to(ADMIN) if "Ví FatCat còn" in h]
    assert len(alerts) == 1 and "Chat GPT Plus" in alerts[0] and "Gemini" not in alerts[0]

    gpt = products[34]
    store.handle_update(_click(BUYER, "shop"))
    labels = [row[0]["text"] for row in telegram.edits[-1][3]["inline_keyboard"][:-1]]
    assert any("Chat GPT" in t and "còn 44 · ⏳ giao sau ít phút" in t for t in labels)
    assert any("Gemini" in t and t.endswith("còn 7") for t in labels)
    store.handle_update(_click(BUYER, f"p:{gpt.id}"))
    assert "vẫn đặt bình thường" in telegram.edits[-1][2]
    assert any(b["callback_data"] == f"q:{gpt.id}:1" for row in telegram.edits[-1][3]["inline_keyboard"] for b in row)

    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    store.handle_update(_click(BUYER, f"q:{gpt.id}:1"))
    assert "vẫn đặt bình thường" in telegram.edits[-1][2]
    store.handle_update(_click(BUYER, telegram.edits[-1][3]["inline_keyboard"][0][0]["callback_data"]))
    assert fake.calls == []  # biết trước ví thiếu → không gọi FatCat
    screen = telegram.edits[-1]
    assert "shop đang nhập hàng" in screen[2]
    cancel = screen[3]["inline_keyboard"][0][0]
    assert cancel["callback_data"].startswith("ow:")
    order_id = int(cancel["callback_data"][3:])
    assert repo.get_user(BUYER).balance == 200_000 - 155_000

    store.handle_update(_click(BUYER, f"o:{order_id}"))
    assert "chờ shop nhập hàng" in telegram.answers[-1][0]
    fake.funds = 500_000
    store.retry_pending()
    assert repo.get_order(order_id).status == "done" and len(fake.calls) == 1
    store.handle_update(_click(BUYER, cancel["callback_data"]))  # bấm huỷ sau khi đã giao → không hoàn
    assert repo.get_user(BUYER).balance == 200_000 - 155_000


def test_customer_cancels_waiting_order_and_gets_money_back(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.funds = 1_000
    store.sync_upstream()
    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    order = repo.buy(BUYER, products[34].id, 1)
    assert order.waiting_funds
    store.handle_update(_click(BUYER, f"ow:{order.id}"))
    store.handle_update(_click(BUYER, f"ow:{order.id}"))  # bấm đúp không hoàn hai lần
    done = repo.get_order(order.id)
    assert (done.status, done.refunded) == ("failed", 155_000)
    assert repo.get_user(BUYER).balance == 200_000
    assert "Đã huỷ đơn theo yêu cầu" in telegram.edits[-1][2]
    fake.funds = 500_000
    store.retry_pending()
    assert fake.calls == []


def test_waiting_orders_released_in_order_within_wallet(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.funds = 0
    store.sync_upstream()
    gem = products[49]
    repo.adjust_balance(BUYER, 100_000, "test", "admin")
    first = repo.buy(BUYER, gem.id, 1, client_ref="a")
    second = repo.buy(BUYER, gem.id, 1, client_ref="b")
    assert first.waiting_funds and second.waiting_funds
    repo.set_state("upstream_balance", "30000")  # đủ 1 đơn (18.620đ)
    assert repo.release_waiting() == [first.id]
    assert repo.upstream_funds() == 30_000 - 18_620
    assert repo.release_waiting() == []


def test_wallet_reserved_per_order_so_second_order_waits(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.funds = 30_000
    store.sync_upstream()
    gem = products[49]
    repo.adjust_balance(BUYER, 100_000, "test", "admin")
    first = repo.buy(BUYER, gem.id, 1, client_ref="a")
    assert not first.waiting_funds and repo.upstream_funds() == 30_000 - 18_620
    second = repo.buy(BUYER, gem.id, 1, client_ref="b")
    assert second.waiting_funds  # ví giữ chỗ cho đơn đầu → đơn sau chờ, không gọi FatCat
    fake.funds = 11_380
    store._fulfill_now(first.id, BUYER, None)  # giao xong → đọc lại số thật
    assert repo.upstream_funds() == 11_380


def test_paid_qr_while_wallet_low_creates_waiting_order(fatcat, repo):
    store, telegram, fake, products = fatcat
    gpt = products[34]
    topup = repo.create_topup(BUYER, gpt.price, gpt.id, 1)
    fake.funds = 1_000
    store.sync_upstream()
    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))
    assert fake.calls == [] and repo.get_user(BUYER).balance == 0
    assert len(repo.waiting_orders()) == 1
    assert any("shop đang nhập hàng" in h for h in telegram.texts_to(BUYER))
    assert any("chờ anh nạp ví FatCat" in h for h in telegram.texts_to(ADMIN))


def test_api_order_waits_for_wallet_with_202(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.funds = 1_000
    store.sync_upstream()
    raw, _key = repo.issue_key(RESELLER, 0)
    repo.adjust_balance(RESELLER, 200_000, "test", "admin")
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
    res = client.post("/api/v1/orders", json={"product_id": products[34].id, "quantity": 1, "request_id": "r1"},
                      headers={"X-API-Key": raw})
    assert res.status_code == 202 and res.json()["status"] == "pending"
    assert fake.calls == [] and any("chờ anh nạp ví FatCat" in h for h in telegram.texts_to(ADMIN))


def test_pressing_qr_again_reuses_code_and_old_codes_expire(fatcat, repo):
    store, telegram, fake, products = fatcat
    gem = products[49]
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    pending = repo.pending_topups()
    assert len(pending) == 1
    assert sum("Để mua" in h for h in telegram.texts_to(ADMIN)) == 1
    assert sum(pending[0].code in caption for _, caption in telegram.photos) == 2

    assert repo.expire_topups(3600) == []
    assert len(repo.expire_topups(-1)) == 1
    assert repo.pending_topups() == []
    assert repo.get_topup(pending[0].id).status == "cancelled"


@pytest.mark.parametrize("name,expected", [
    ("Slot Canva Pro 1 Tháng BHF", "suốt thời hạn gói"),
    ("100$ API Claude 30D (FW)", "suốt thời hạn gói"),
    ("Chat GPT Plus Google Pay BH1D", "1 ngày"),
    ("Link Duolingo Super 12 tháng KBH", "không có"),
    ("Muse AI 1B Tokens (NW)", "không có"),
    ("Link Gemini Pro 18M (BH 5P)", "chỉ 5 phút sau khi nhận"),
    ("LINK GEMINI 18M BH 10p", "chỉ 10 phút sau khi nhận"),
    ("Link Gemini 18 Tháng (Dùng trong 20P)", "chỉ khi dùng ngay trong 20 phút"),
    ("CDK Gemini AI Pro 12 tháng", None),
])
def test_warranty_decoded_from_product_name(name, expected):
    got = msg.warranty(name)
    assert (got is None) if expected is None else got.startswith(expected)


def test_product_and_confirm_show_warranty(fatcat, repo):
    store, telegram, fake, products = fatcat
    gpt = products[34]
    store.handle_update(_click(BUYER, f"p:{gpt.id}"))
    assert "🛡️ Bảo hành: <b>1 ngày</b>" in telegram.edits[-1][2]
    store.handle_update(_click(BUYER, f"q:{gpt.id}:1"))
    assert "🛡️ Bảo hành: 1 ngày" in telegram.edits[-1][2]


def test_topup_text_without_sepay_does_not_promise_instant(fatcat, repo):
    store, telegram, fake, products = fatcat
    store.settings = _settings(sepay_webhook_key=None)
    store.handle_update(_click(BUYER, f"bq:{products[49].id}:1"))
    caption = telegram.photos[-1][1]
    assert "Shop xác nhận tiền" in caption and "ban đêm" in caption and "1 phút" not in caption


def test_delivery_shows_upstream_order_code_and_items_verbatim(fatcat, repo):
    store, telegram, fake, products = fatcat
    repo.adjust_balance(BUYER, 400_000, "test", "admin")
    raw = "acc@mail.com|Pa<ss>|2FA KEY"
    fake.results = [BuyResult(DELIVERED, [raw], "DH5FG3NW", None, 200, "complete")]
    gpt = products[34]
    store.handle_update(_click(BUYER, f"q:{gpt.id}:1"))
    store.handle_update(_click(BUYER, telegram.edits[-1][3]["inline_keyboard"][0][0]["callback_data"]))
    delivery = next(h for h in telegram.texts_to(BUYER) if "acc@mail.com" in h)
    assert "🔖 Mã hàng: <code>DH5FG3NW</code>" in delivery
    assert "<code>acc@mail.com|Pa&lt;ss&gt;|2FA KEY</code>" in delivery  # nguyên văn, chỉ thoát HTML
    assert "🔖 Mã hàng: <code>DH5FG3NW</code>" in telegram.edits[-1][2]  # màn «Mua thành công»
    assert any("mã DH5FG3NW" in h for h in telegram.texts_to(ADMIN))
    store.handle_update(_click(BUYER, "ord"))
    assert "DH5FG3NW" in telegram.edits[-1][3]["inline_keyboard"][0][0]["text"]


# ---------- spam / lỗi giữa chừng (06/11) ----------

def test_one_pending_qr_per_customer_until_confirmed_or_cancelled(fatcat, repo):
    store, telegram, fake, products = fatcat
    gem, gpt = products[49], products[34]
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    first = repo.pending_topups()[0]
    for data in (f"bq:{gem.id}:2", f"bq:{gpt.id}:1", "ta:100000"):  # món / số lượng / nạp khác → không tạo mã
        store.handle_update(_click(BUYER, data))
    assert [t.id for t in repo.pending_topups()] == [first.id]
    assert sum("Yêu cầu nạp" in h for h in telegram.texts_to(ADMIN)) == 1
    screen = telegram.edits[-1] if telegram.edits else None
    shown = [h for h in telegram.texts_to(BUYER) if "1 mã thanh toán chờ xác nhận" in h]
    shown += [screen[2]] if screen and "1 mã thanh toán chờ xác nhận" in screen[2] else []
    assert shown and first.code in shown[-1] and "đừng huỷ" in shown[-1]

    store.handle_update(_click(BUYER, f"tv:{first.id}"))  # xem lại mã
    assert first.code in telegram.photos[-1][1]
    store.handle_update(_click(RESELLER, f"tu:{first.id}", "Zusem10"))  # người khác không huỷ được
    assert repo.get_topup(first.id).status == "pending"
    store.handle_update(_click(BUYER, f"tu:{first.id}"))
    assert repo.get_topup(first.id).status == "cancelled"
    closed = [e for e in telegram.edits if e[0] == ADMIN and "Khách tự huỷ" in e[2]]
    assert closed and closed[-1][3] is None  # tin «Yêu cầu nạp» của admin ghi kết quả, hết nút ✅ ❌
    store.handle_update(_click(BUYER, f"bq:{gpt.id}:1"))  # huỷ xong tạo được mã mới
    assert len(repo.pending_topups()) == 1 and repo.pending_topups()[0].intent_product_id == gpt.id

    admin_ok = repo.pending_topups()[0]
    store.handle_update(_click(ADMIN, f"a:tc:{admin_ok.id}", "boss"))  # được xác nhận → lại tạo được mã
    store.handle_update(_click(BUYER, "ta:50000"))
    assert len(repo.pending_topups()) == 1

    store.handle_update(_click(RESELLER, "tx"))
    store.handle_update(_private(RESELLER, "999tr", "Zusem10"))
    assert any("tối đa 50.000.000đ" in h for h in telegram.texts_to(RESELLER))


def test_late_payment_to_cancelled_code_still_credited_without_buying(fatcat, repo):
    store, telegram, fake, products = fatcat
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
    gem = products[49]
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    topup = repo.pending_topups()[0]
    store.handle_update(_click(BUYER, f"tu:{topup.id}"))  # khách lỡ huỷ sau khi đã chuyển
    hook = {"id": 9100, "transferType": "in", "transferAmount": topup.amount, "content": topup.code}
    client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    assert repo.get_user(BUYER).balance == topup.amount  # vào ví
    assert repo.list_orders(BUYER) == [] and fake.calls == []  # không tự mua món cũ
    assert not any("không khớp" in h for h in telegram.texts_to(ADMIN))

    admin_cancelled = repo.create_topup(BUYER, 30_000)
    repo.cancel_topup(admin_cancelled.id, "admin:1")
    hook = {"id": 9101, "transferType": "in", "transferAmount": 30_000, "content": admin_cancelled.code}
    client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    assert repo.get_user(BUYER).balance == topup.amount  # mã admin huỷ → không tự cộng
    assert any("không khớp" in h for h in telegram.texts_to(ADMIN))


def test_sepay_error_after_credit_alerts_admin_and_returns_ok(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
    topup = repo.create_topup(BUYER, 19_000, products[49].id, 1)

    def boom(*_a, **_k):
        raise RuntimeError("tg down")
    monkeypatch.setattr(StoreBot, "on_topup_credited", boom)
    hook = {"id": 9001, "transferType": "in", "transferAmount": 19_000, "content": topup.code}
    res = client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    assert res.status_code == 200 and repo.get_user(BUYER).balance == 19_000
    assert any("bước báo khách / tự mua bị lỗi" in h for h in telegram.texts_to(ADMIN))
    client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})  # SePay gửi lại
    assert repo.get_user(BUYER).balance == 19_000
    bad = client.post("/webhooks/sepay", content=b"not json",
                      headers={"Authorization": "Apikey sepay-secret", "Content-Type": "application/json"})
    assert bad.status_code == 400


def test_delivery_message_retried_then_admin_alerted(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.SEND_RETRY_SEC", 0)
    repo.adjust_balance(BUYER, 400_000, "test", "admin")
    order = repo.buy(BUYER, products[49].id, 1)
    calls = []
    real = telegram.send_message

    def flaky(chat_id, html, reply_markup=None, disable_notification=False):
        if chat_id == BUYER and "fc-49-0" in html:
            calls.append(1)
            return None if len(calls) == 1 else real(chat_id, html, reply_markup, disable_notification)
        return real(chat_id, html, reply_markup, disable_notification)
    monkeypatch.setattr(telegram, "send_message", flaky)
    store._fulfill_now(order.id, BUYER, None)
    assert len(calls) == 2 and any("fc-49-0" in h for h in telegram.texts_to(BUYER))

    calls.clear()
    monkeypatch.setattr(telegram, "send_message", lambda chat_id, html, *a, **k: None if chat_id == BUYER
                        else real(chat_id, html, *a, **k))
    store.send_items(BUYER, repo.get_order(order.id))
    assert any("Gửi hàng đơn" in h for h in telegram.texts_to(ADMIN))


def test_qr_price_locked_when_price_rises_but_lower_price_wins(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    gem = products[49]
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    topup = repo.pending_topups()[0]
    assert topup.intent_unit_price == gem.price
    repo.update_product(gem.id, price=gem.price + 3_000)  # giá tăng sau khi khách lấy QR
    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))
    order = repo.list_orders(BUYER)[0]
    assert (order.status, order.total) == ("done", gem.price) and repo.get_user(BUYER).balance == 0

    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    second = repo.pending_topups()[0]
    repo.update_product(gem.id, price=gem.price - 300)  # giá giảm (vẫn trên vốn 18.620đ) → khách được giá mới
    store.handle_update(_click(ADMIN, f"a:tc:{second.id}", "boss"))
    assert repo.list_orders(BUYER)[0].total == gem.price - 300
    assert repo.get_user(BUYER).balance == 3_300  # QR thứ 2 tạo lúc giá 22.000đ, mua giá 18.700đ → dư nằm ví


def test_waiting_order_auto_refunded_after_6_hours(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    fake.funds = 1_000
    store.sync_upstream()
    repo.adjust_balance(BUYER, 200_000, "test", "admin")
    order = repo.buy(BUYER, products[34].id, 1)
    store.retry_pending()
    assert repo.get_order(order.id).status == "pending"  # chưa tới 6 giờ
    monkeypatch.setattr("store_bot.bot.WAITING_REFUND_SEC", -1)
    store.retry_pending()
    done = repo.get_order(order.id)
    assert (done.status, done.refunded) == ("failed", 155_000) and repo.get_user(BUYER).balance == 200_000
    assert any("tự huỷ đơn sau 6 giờ" in h for h in telegram.texts_to(BUYER))
    assert any("chờ nạp ví FatCat quá 6 giờ" in h for h in telegram.texts_to(ADMIN))
    store.retry_pending()  # không hoàn lần 2
    assert repo.get_user(BUYER).balance == 200_000
    fake.funds = 500_000
    store.retry_pending()
    assert fake.calls == []


def test_admin_topup_notice_closed_after_sepay_or_admin(fatcat, repo):
    store, telegram, fake, products = fatcat
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, InlineExecutor()))
    store.handle_update(_click(BUYER, "ta:50000"))
    topup = repo.pending_topups()[0]
    assert any(cid == ADMIN and "Yêu cầu nạp" in html for cid, html, _ in telegram.sent)
    hook = {"id": 9200, "transferType": "in", "transferAmount": 50_000, "content": topup.code}
    client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    edit = [e for e in telegram.edits if e[0] == ADMIN and "SePay tự cộng" in e[2]]
    assert len(edit) == 1 and edit[0][3] is None and f"Yêu cầu nạp #{topup.id}" in edit[0][2]
    assert repo.get_state(f"topup_msg:{topup.id}") is None

    store.handle_update(_click(ADMIN, f"a:tc:{topup.id}", "boss"))  # bấm nút cũ: không cộng lại
    assert repo.get_user(BUYER).balance == 50_000
    assert "Đã cộng 50.000đ" in telegram.edits[-1][2]

    store.handle_update(_click(RESELLER, "ta:100000", "Zusem10"))
    second = repo.pending_topups()[0]
    store.handle_update(_click(ADMIN, f"a:tc:{second.id}", "boss"))
    assert any("Admin xác nhận" in e[2] and e[3] is None for e in telegram.edits if e[0] == ADMIN)


def test_telegram_keeps_one_connection_per_thread():
    api = TelegramApi("t")
    first = api._http
    assert api._http is first  # cùng luồng: dùng lại kết nối (không mở TLS mới mỗi tin)
    other = []
    worker = threading.Thread(target=lambda: other.append(api._http))
    worker.start()
    worker.join()
    assert other[0] is not first  # luồng khác có Session riêng


def test_sepay_replies_before_slow_telegram_work(fatcat, repo):
    store, telegram, fake, products = fatcat

    class Deferred:
        def __init__(self):
            self.jobs = []

        def submit(self, fn, *args):
            self.jobs.append((fn, args))

    later = Deferred()
    client = TestClient(create_app(_settings(), repo, telegram, store.fulfiller, later))
    topup = repo.create_topup(BUYER, 19_000, products[49].id, 1)
    hook = {"id": 7300, "transferType": "in", "transferAmount": 19_000, "content": topup.code}
    res = client.post("/webhooks/sepay", json=hook, headers={"Authorization": "Apikey sepay-secret"})
    assert res.json() == {"success": True}
    assert repo.get_user(BUYER).balance == 19_000  # tiền đã ghi trước khi trả lời
    assert telegram.texts_to(BUYER) == [] and later.jobs  # Telegram / tự mua chưa chạy
    for fn, args in later.jobs:
        fn(*args)
    assert len(repo.list_orders(BUYER)) == 1 and any("SePay: nạp" in h for h in telegram.texts_to(ADMIN))


def test_broadcast_uses_own_thread_not_fulfillment_pool(repo):
    store = StoreBot(_settings(), repo, FakeTelegram(), "x")
    assert store.broadcast_executor is not store.executor
    assert store.broadcast_executor._max_workers == 1 and store.executor._max_workers == 4


def test_waiting_summary_and_batched_prices(fatcat, repo):
    store, telegram, fake, products = fatcat
    fake.funds = 0
    store.sync_upstream()
    repo.adjust_balance(BUYER, 500_000, "test", "admin")
    repo.buy(BUYER, products[34].id, 1, client_ref="w1")
    repo.buy(BUYER, products[49].id, 2, client_ref="w2")
    assert repo.waiting_summary() == (2, 151_900 + 2 * 18_620)
    store.fulfiller.set_markup(pricing.Markup("pct", 1_000))
    store.fulfiller.set_markup(pricing.Markup("vnd", 5_000), products[49].id)
    fn = store.fulfiller._price_fn()
    for p in repo.list_products():
        assert fn(p.cost, p.upstream_id) == store.fulfiller.price_for(p.cost, p.upstream_id) == p.price


# ---------- giờ nghỉ / gọi lại có giới hạn / dọn state (06/11) ----------

def test_hours_window_parse_and_status():
    from datetime import datetime as dt

    from store_bot import hours
    w = hours.parse_window("23h30-7h30")
    assert w.code == "23:30-07:30" and w.label == "23:30–07:30"
    at = lambda h, m: dt(2026, 11, 7, h, m, tzinfo=hours.ICT)  # noqa: E731
    assert hours.status(w, False, at(23, 45)) == hours.Status(True, reopen="07:30")
    assert hours.status(w, False, at(3, 0)).closed and not hours.status(w, False, at(7, 30)).closed
    assert not hours.status(w, False, at(12, 0)).closed
    day = hours.parse_window("12:00-13:00")
    assert hours.status(day, False, at(12, 30)).closed and not hours.status(day, False, at(13, 0)).closed
    assert hours.status(None, True) == hours.Status(True, manual=True)
    assert hours.parse_window("7-7") is None and hours.parse_window("24:00-1:00") is None


def test_admin_sets_hours_and_closes_shop(bot, repo):
    bot, telegram = bot
    bot.handle_update(_click(BUYER, "ahr"))
    assert telegram.answers[-1][0] == "Không có quyền."
    bot.handle_update(_click(ADMIN, "adm", "boss"))
    labels = [b["text"] for row in telegram.edits[-1][3]["inline_keyboard"] for b in row]
    assert "🌙 Đặt giờ nghỉ / đóng shop" in labels
    bot.handle_update(_click(ADMIN, "ahs", "boss"))
    bot.handle_update(_private(ADMIN, "sai giờ", "boss"))
    assert repo.get_state("closed_hours") is None
    bot.handle_update(_private(ADMIN, "23h-7h", "boss"))
    assert repo.get_state("closed_hours") == "23:00-07:00"
    assert "Giờ nghỉ hằng ngày: <b>23:00–07:00</b>" in telegram.texts_to(ADMIN)[-1]
    bot.handle_update(_click(ADMIN, "ahc", "boss"))
    assert repo.get_state("closed_manual") == "1" and "Đang ĐÓNG tay" in telegram.edits[-1][2]
    bot.handle_update(_click(ADMIN, "aho", "boss"))
    assert repo.get_state("closed_manual") is None
    bot.handle_update(_click(ADMIN, "ahx", "boss"))
    assert repo.get_state("closed_hours") is None


def test_closed_shop_blocks_buying_but_keeps_browse_topup_and_paid_qr(fatcat, repo):
    store, telegram, fake, products = fatcat
    gem = products[49]
    paid_before = repo.create_topup(BUYER, gem.price, gem.id, 1, gem.price)  # QR tạo trước giờ nghỉ
    repo.set_state("closed_manual", "1")

    store.handle_update(_click(BUYER, "home"))
    assert "Shop đang tạm nghỉ" in telegram.edits[-1][2]
    store.handle_update(_click(BUYER, f"p:{gem.id}"))
    detail = telegram.edits[-1]
    assert "Shop đang tạm nghỉ" in detail[2]
    assert not any(b["callback_data"].startswith(("q:", "qx:")) for row in detail[3]["inline_keyboard"] for b in row)
    store.handle_update(_click(BUYER, f"q:{gem.id}:1"))
    store.handle_update(_click(BUYER, f"bq:{gem.id}:1"))
    store.handle_update(_click(BUYER, f"bc:{gem.id}:1:abcd"))
    assert [t.id for t in repo.pending_topups()] == [paid_before.id] and repo.list_orders(BUYER) == []

    store.handle_update(_click(ADMIN, f"a:tc:{paid_before.id}", "boss"))  # tiền QR cũ về trong giờ nghỉ
    assert len(repo.list_orders(BUYER)) == 1 and fake.calls  # vẫn tự mua
    store.handle_update(_click(BUYER, "ta:50000"))  # nạp ví vẫn được
    assert any(t.amount == 50_000 for t in repo.pending_topups())

    fake.rows[0]["stock"] = 100
    store.sync_upstream()
    assert telegram.texts_to("@kenh") == [] and telegram.broadcasts == []  # nghỉ: không báo hàng mới


def test_api_closed_returns_503_but_replays_existing_order(api, repo, product):
    client, headers, key, _ = api
    repo.adjust_balance(RESELLER, 100_000, "test", "admin")
    body = {"product_id": product, "quantity": 1, "request_id": "z1"}
    first = client.post("/api/v1/orders", json=body, headers=headers)
    repo.set_state("closed_manual", "1")
    again = client.post("/api/v1/orders", json=body, headers=headers)
    assert again.json()["order_id"] == first.json()["order_id"]  # gọi lại đơn cũ vẫn trả đơn
    new = client.post("/api/v1/orders", json={**body, "request_id": "z2"}, headers=headers)
    assert new.status_code == 503 and new.json()["error"] == "shop_closed"


def test_retry_round_stops_when_fatcat_offline_and_rotates(fatcat, repo, monkeypatch):
    store, telegram, fake, products = fatcat
    monkeypatch.setattr("store_bot.bot.RETRY_AFTER_SEC", -1)
    repo.adjust_balance(BUYER, 500_000, "test", "admin")
    ids = [repo.buy(BUYER, products[49].id, 1, client_ref=f"r{i}").id for i in range(5)]
    fake.results = [BuyResult(PENDING, message="ConnectionError") for _ in range(20)]
    store.retry_pending()
    assert [c for c in fake.calls] and len(fake.calls) == 2  # mất kết nối 2 lần liền → dừng vòng
    store.retry_pending()
    assert len(fake.calls) == 4
    tried = [store.repo.upstream_job(i)[2] for i in ids]
    assert {c[2] for c in fake.calls} == set(tried[:4])  # vòng 2 đi tiếp đơn 3, 4 chứ không lặp đơn 1, 2


def test_cleanup_state_removes_only_stale_keys(fatcat, repo):
    import time as _t
    store, telegram, fake, products = fatcat
    now = _t.time()
    repo.adjust_balance(BUYER, 100_000, "test", "admin")
    order = repo.buy(BUYER, products[49].id, 1)
    store._fulfill_now(order.id, BUYER, None)  # đơn xong
    for k, v in {f"stuck_alerted:{order.id}": "1", "stuck_alerted:999999": "1", "topup_msg:424242": "[]",
                 "announced:1": str(now - 90_000), "announced:2": str(now), "callme:5": str(now - 90_000),
                 f"src:{BUYER}": "threads_ai_auto", f"menu_sent:{BUYER}": "1"}.items():
        repo.set_state(k, v)
    pending = repo.create_topup(BUYER, 10_000)
    repo.set_state(f"topup_msg:{pending.id}", "[]")
    repo.cleanup_state(now)
    left = repo.states_with_prefix("")
    assert f"stuck_alerted:{order.id}" not in left and "stuck_alerted:999999" not in left
    assert "topup_msg:424242" not in left and f"topup_msg:{pending.id}" in left
    assert "announced:1" not in left and "announced:2" in left and "callme:5" not in left
    assert f"src:{BUYER}" in left and f"menu_sent:{BUYER}" in left
