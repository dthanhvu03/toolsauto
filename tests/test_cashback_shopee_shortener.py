from unittest.mock import MagicMock, patch
import json
import time
import pytest

from cashback_bot import shopee_shortener


def test_shorten_shopee_url_mocked_success():
    shopee_shortener._CACHE.clear()
    shopee_shortener._LAST_BRIDGE_FAIL = 0.0
    fake_body = json.dumps({"success": True, "short_link": "https://s.shopee.vn/test123"}).encode("utf-8")
    mock_resp = MagicMock(status=200, read=lambda: fake_body)
    mock_resp.__enter__.return_value = mock_resp

    with patch.dict("os.environ", {"SHOPEE_SHORTENER_LIVE": "1"}), \
         patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = shopee_shortener.shorten_shopee_url("https://shopee.vn/product/1/2", "AUTOSALE")
        assert res == "https://s.shopee.vn/test123"
        assert mock_urlopen.call_count == 1

        # Caching test: call again
        res2 = shopee_shortener.shorten_shopee_url("https://shopee.vn/product/1/2", "AUTOSALE")
        assert res2 == "https://s.shopee.vn/test123"
        assert mock_urlopen.call_count == 1, "Cache phải trả ngay lập tức không gọi bridge lại"


def test_shorten_shopee_circuit_breaker():
    shopee_shortener._CACHE.clear()
    shopee_shortener._LAST_BRIDGE_FAIL = 0.0
    with patch.dict("os.environ", {"SHOPEE_SHORTENER_LIVE": "1"}), \
         patch("urllib.request.urlopen", side_effect=Exception("Connection refused")) as mock_urlopen:
        # Lần 1: Gọi lỗi -> kích hoạt circuit breaker
        res = shopee_shortener.shorten_shopee_url("https://shopee.vn/product/1/2", "AUTOSALE")
        assert res is None
        assert mock_urlopen.call_count == 1
        assert shopee_shortener._LAST_BRIDGE_FAIL > 0.0

        # Lần 2 ngay sau đó: Circuit breaker trả ngay None trong 0ms, không gọi urlopen
        res2 = shopee_shortener.shorten_shopee_url("https://shopee.vn/product/9/9", "AUTOSALE")
        assert res2 is None
        assert mock_urlopen.call_count == 1, "Circuit breaker phải chặn cuộc gọi tiếp theo"


def test_shorten_cache_max_size_eviction():
    shopee_shortener._CACHE.clear()
    shopee_shortener._LAST_BRIDGE_FAIL = 0.0
    with patch.object(shopee_shortener, "MAX_CACHE_SIZE", 2):
        fake_body = json.dumps({"success": True, "short_link": "https://s.shopee.vn/x"}).encode("utf-8")
        mock_resp = MagicMock(status=200, read=lambda: fake_body)
        mock_resp.__enter__.return_value = mock_resp

        with patch.dict("os.environ", {"SHOPEE_SHORTENER_LIVE": "1"}), \
             patch("urllib.request.urlopen", return_value=mock_resp):
            shopee_shortener.shorten_shopee_url("https://shopee.vn/p1", "AUTOSALE")
            shopee_shortener.shorten_shopee_url("https://shopee.vn/p2", "AUTOSALE")
            assert len(shopee_shortener._CACHE) == 2
            # Thêm item thứ 3 -> item 1 bị loại
            shopee_shortener.shorten_shopee_url("https://shopee.vn/p3", "AUTOSALE")
            assert len(shopee_shortener._CACHE) == 2
            assert ("https://shopee.vn/p1", "AUTOSALE") not in shopee_shortener._CACHE


def test_shorten_if_an_redir():
    shopee_shortener._CACHE.clear()
    shopee_shortener._LAST_BRIDGE_FAIL = 0.0
    with patch("cashback_bot.shopee_shortener.shorten_shopee_url", return_value="https://s.shopee.vn/short1") as m:
        # Link AUTOSALE -> rút gọn
        url_auto = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fm%2Ftest&sub_id=AUTOSALE"
        assert shopee_shortener.shorten_if_an_redir(url_auto) == "https://s.shopee.vn/short1"
        assert m.call_count == 1

        # Link VOUCHERS -> rút gọn
        url_v = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fm%2Fv&sub_id=VOUCHERS"
        assert shopee_shortener.shorten_if_an_redir(url_v) == "https://s.shopee.vn/short1"

        # Link đơn khách (sub_id 8 ký tự) -> giữ nguyên để đối soát
        url_cust = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fp&sub_id=a1b2c3d4"
        assert shopee_shortener.shorten_if_an_redir(url_cust) == url_cust

        # Link bình thường không phải an_redir -> giữ nguyên
        assert shopee_shortener.shorten_if_an_redir("https://google.com") == "https://google.com"
