"""PLAN-085: client RioHub × TikTok Shop. Phản hồi giả theo ví dụ trong spec 09/10/2026, không gọi mạng."""

from __future__ import annotations

import logging

import pytest
import requests

from cashback_bot import riohub_client
from cashback_bot.config import load_settings
from cashback_bot.riohub_client import (
    BASE_URLS,
    RioHubClient,
    RioHubError,
    commission_rate_bps,
    parse_order,
    price_range_vnd,
    product_id_of,
    product_image,
    product_title,
    sync_window,
    to_vnd,
    validate_sub_id,
)

KEY = "rk_test_khong_that_123"

PRODUCT = {
    "id": "1732000000000000001", "title": "Dao cạo", "main_image_url": "https://img/x.jpg",
    "commission": {"rate": 600, "amount": "3299.94 - 5099.94", "currency": "VND"},
    "shop_ads_commission": {"rate": 200},
    "sales_price": {"minimum_amount": "", "maximum_amount": "", "currency": ""},
    "original_price": {"minimum_amount": "89000", "maximum_amount": "139000", "currency": "VND"},
    "observed_commission": {"commission_rate": 2300, "commission_bonus_rate": 1500, "scope": "creator"},
}

ORDER = {
    "order_id": "5800000000000001", "sku_id": "1730000000000009", "product_id": "1732000000000000001",
    "sub_id": "abc123", "sub1": "abc123", "sub2": "", "sub3": "", "sub4": "",
    "trace_id": "abc123", "trace_type": "SPECIFIC", "quantity": 1, "refunded_quantity": 0, "fully_refunded": 0,
    "est_commission": "12.50", "actual_commission": None, "currency": "VND",
    "settlement_status": "AWAITING PAYMENT", "status": 1, "tt_order_status": 100, "create_time": 1749513600,
}


class FakeResponse:
    def __init__(self, status_code: int, payload, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "params": params, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(monkeypatch, *responses, **kwargs):
    http = FakeHttp(*responses)
    monkeypatch.setattr(riohub_client.requests, "request", http)
    slept: list[float] = []
    return RioHubClient(KEY, "twot283", sleep=slept.append, **kwargs), http, slept


def test_tao_link_gui_khoa_trong_header_va_nhan_product_url_hoac_id(monkeypatch):
    client, http, _ = _client(monkeypatch, FakeResponse(200, {"affiliate_link": "https://vt.tiktok.com/A/"}),
                              FakeResponse(200, {"affiliate_link": "https://vt.tiktok.com/B/"}))
    assert client.create_link("https://vt.tiktok.com/XXXXXX/", "abc123") == "https://vt.tiktok.com/A/"
    client.create_link("1729000000000000001", "abc123")
    first, second = http.calls
    assert first["method"] == "POST" and first["url"] == f"{BASE_URLS[0]}/partner/tiktok/affiliate/links"
    assert first["headers"]["X-Riohub-Api-Key"] == KEY
    assert first["json"] == {"creator_username": "twot283", "product_url": "https://vt.tiktok.com/XXXXXX/",
                             "sub_id": "abc123"}
    assert second["json"]["product_id"] == "1729000000000000001" and "product_url" not in second["json"]


@pytest.mark.parametrize("bad", ["", "a b", "có-dấu", "x" * 129, "a-b-c-d-e"])
def test_sub_id_sai_bi_chan_truoc_khi_goi(monkeypatch, bad):
    client, http, _ = _client(monkeypatch)
    with pytest.raises(ValueError):
        client.create_link("1729", bad)
    assert http.calls == []
    assert validate_sub_id("abc-def--") == "abc-def--", "4 phần, phần rỗng hợp lệ"


def test_san_pham_khong_co_hoa_hong_khong_thu_lai(monkeypatch):
    client, http, slept = _client(monkeypatch, FakeResponse(422, {"error": "product_not_promotable", "message": "x"}))
    with pytest.raises(RioHubError) as caught:
        client.create_link("1729", "abc123")
    assert caught.value.kind == "not_promotable" and len(http.calls) == 1 and slept == []


def test_429_doi_retry_after_roi_thu_lai_mot_lan(monkeypatch):
    client, http, slept = _client(
        monkeypatch,
        FakeResponse(429, {"error": "rate_limited"}, {"Retry-After": "7"}),
        FakeResponse(200, {"affiliate_link": "https://vt.tiktok.com/A/"}),
    )
    assert client.create_link("1729", "abc123") == "https://vt.tiktok.com/A/"
    assert slept == [7] and len(http.calls) == 2


def test_429_lien_tuc_thi_dung(monkeypatch):
    client, _http, slept = _client(monkeypatch, *[FakeResponse(429, {}, {"Retry-After": "999"})] * 2)
    with pytest.raises(RioHubError) as caught:
        client.create_link("1729", "abc123")
    assert caught.value.kind == "rate_limited" and slept == [riohub_client.RETRY_AFTER_CAP_SEC]


def test_doi_ten_mien_chi_khi_loi_mang(monkeypatch):
    client, http, _ = _client(monkeypatch, requests.ConnectionError("dns"), requests.Timeout("t"),
                              FakeResponse(200, {"affiliate_link": "https://vt.tiktok.com/A/"}))
    client.create_link("1729", "abc123")
    assert [call["url"].split("/partner")[0] for call in http.calls] == list(BASE_URLS)

    client, http, _ = _client(monkeypatch, FakeResponse(502, {"error": "tiktok_shop_error"}))
    with pytest.raises(RioHubError) as caught:
        client.create_link("1729", "abc123")
    assert caught.value.kind == "transient" and len(http.calls) == 1, "5xx không đổi tên miền"

    client, _http, _ = _client(monkeypatch, *[requests.ConnectionError("x")] * 3)
    with pytest.raises(RioHubError) as caught:
        client.create_link("1729", "abc123")
    assert caught.value.kind == "network"


@pytest.mark.parametrize(("status", "error", "kind"), [
    (401, None, "auth"), (403, None, "creator"), (404, None, "creator"),
    (424, "creator_token_invalid", "creator"), (422, "validation_error", "invalid"),
    (503, "tiktok_scope_unavailable", "unavailable"),
])
def test_phan_loai_loi(monkeypatch, status, error, kind):
    client, _http, _ = _client(monkeypatch, FakeResponse(status, {"error": error} if error else ValueError()))
    with pytest.raises(RioHubError) as caught:
        client.get_products(["1"])
    assert caught.value.kind == kind and caught.value.status_code == status


def test_doc_loi_dang_long_cua_riohub(monkeypatch):
    """Dạng lỗi thật (thử 2026-10-25): creator chưa vào RioMCN."""
    client, _http, _ = _client(monkeypatch, FakeResponse(403, {"error": {
        "code": "mcn_membership_required", "message": "Creator 'twot283' chưa là thành viên RioMCN"}}))
    with pytest.raises(RioHubError) as caught:
        list(client.iter_orders(0, 1))
    assert caught.value.kind == "creator" and caught.value.code == "mcn_membership_required"
    assert "RioMCN" in caught.value.message
    client, _http, _ = _client(monkeypatch, FakeResponse(422, {"error": {"code": "product_not_promotable"}}))
    with pytest.raises(RioHubError) as caught:
        client.create_link("1729", "abc123")
    assert caught.value.kind == "not_promotable"


def test_log_khong_ghi_khoa(monkeypatch, caplog):
    client, _http, _ = _client(monkeypatch, FakeResponse(401, {"error": "unauthorized"}))
    with caplog.at_level(logging.INFO, logger="cashback_bot"), pytest.raises(RioHubError):
        client.create_link("1729", "abc123")
    assert caplog.records and KEY not in caplog.text


def test_product_links_thieu_thong_tin_san_pham_van_tra_link(monkeypatch):
    client, _http, _ = _client(monkeypatch, FakeResponse(200, {
        "affiliate_link": "https://vt.tiktok.com/A/", "sub_id": "abc123", "product_id": "1729",
        "product": None, "product_error": "tiktok timeout",
    }))
    result = client.create_product_link("https://vt.tiktok.com/XXXXXX/", "abc123")
    assert result.affiliate_link == "https://vt.tiktok.com/A/" and result.product is None
    assert result.product_error == "tiktok timeout"


def test_doc_san_pham_phong_thu_va_ty_le_tong():
    assert commission_rate_bps(PRODUCT) == 2300, "observed_commission là tỷ lệ tổng"
    without = {key: value for key, value in PRODUCT.items() if key != "observed_commission"}
    assert commission_rate_bps(without) == 800, "không có observed → chuẩn + shop ads"
    assert commission_rate_bps({"commission_rate": 500}) == 500
    assert commission_rate_bps({}) is None
    assert price_range_vnd(PRODUCT) == (89000, 139000), "sales_price rỗng → original_price"
    assert price_range_vnd({"sales_price": {"minimum_amount": "99000.9", "maximum_amount": ""}}) == (99000, 99000)
    assert price_range_vnd({}) is None
    other = {"product_id": "9", "product_name": "Áo", "cover_url": "https://img/y.jpg"}
    assert (product_id_of(other), product_title(other), product_image(other)) == ("9", "Áo", "https://img/y.jpg")


def test_lay_san_pham_gom_100_id_moi_luot(monkeypatch):
    ids = [str(number) for number in range(150)] + ["0"]
    client, http, _ = _client(
        monkeypatch,
        FakeResponse(200, {"products": [PRODUCT], "not_found": ["5"]}),
        FakeResponse(200, {"products": [], "not_found": []}),
    )
    found, missing = client.get_products(ids)
    assert len(http.calls) == 2 and missing == ["5"] and found == [PRODUCT]
    assert len(http.calls[0]["params"]["product_id"].split(",")) == 100
    assert len(http.calls[1]["params"]["product_id"].split(",")) == 50, "id trùng được gộp"


def test_keo_don_lap_het_trang(monkeypatch):
    page = [dict(ORDER, sku_id=str(number)) for number in range(200)]
    client, http, _ = _client(
        monkeypatch,
        FakeResponse(200, {"total": 201, "orders": page}),
        FakeResponse(200, {"total": 201, "orders": [ORDER]}),
    )
    rows = list(client.iter_orders(1000, 2000))
    assert len(rows) == 201 and [call["params"]["page"] for call in http.calls] == [1, 2]
    assert http.calls[0]["params"]["page_size"] == 200
    assert http.calls[0]["params"]["update_time_start"] == 1000 and http.calls[0]["params"]["update_time_end"] == 2000


def test_keo_don_khong_co_total_van_doc_het_trang(monkeypatch):
    """Rà soát 2026-10-26: spec không chắc có «total»; thiếu thì đọc tới trang thiếu, không dừng ở trang đầu."""
    page = [dict(ORDER, sku_id=str(number)) for number in range(200)]
    client, http, _ = _client(monkeypatch, FakeResponse(200, {"orders": page}), FakeResponse(200, {"orders": [ORDER]}))
    assert len(list(client.iter_orders(1000, 2000))) == 201 and len(http.calls) == 2


def test_doc_don_dung_decimal_va_trang_thai():
    order = parse_order(ORDER)
    assert (order.order_id, order.sku_id, order.status, order.trace_type) == (
        "5800000000000001", "1730000000000009", 1, "SPECIFIC")
    assert order.est_commission_vnd == 12 and order.actual_commission_vnd is None and not order.fully_refunded
    settled = parse_order(dict(ORDER, status=2, actual_commission="4567.99", settled_at_iso="2026-10-01T03:00:00Z"))
    assert settled.actual_commission_vnd == 4567 and settled.settled_at_iso == "2026-10-01T03:00:00Z"
    assert parse_order(dict(ORDER, status=9)) is None and parse_order(dict(ORDER, sku_id="")) is None
    assert to_vnd(0.1) is None and to_vnd("abc") is None and to_vnd("NaN") is None and to_vnd("-1.5") == -1


def test_moc_dong_bo_chong_lan_10_phut():
    assert sync_window(10_000, 20_000) == (9_400, 20_000)
    assert sync_window(None, 1_000_000) == (1_000_000 - 7 * 86_400, 1_000_000)


def test_cau_hinh_doc_khoa_riohub():
    base = {"CASHBACK_BOT_TOKEN": "1:x", "SHOPEE_AFFILIATE_ID": "12345", "ADDLIVETAG_API_KEY": "k",
            "CASHBACK_RATE_PERCENT": "70", "PRODUCT_MAX_AGE_HOURS": "3"}
    assert load_settings(base).riohub_api_key is None
    settings = load_settings(dict(base, RIOHUB_API_KEY=" k1 ", RIOHUB_CREATOR_USERNAME="@twot283"))
    assert settings.riohub_api_key == "k1" and settings.riohub_creator_username == "twot283"
