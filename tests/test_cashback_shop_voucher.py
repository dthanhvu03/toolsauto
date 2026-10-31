"""Kiểm thử tính năng mã giảm giá của Shop (PLAN-105: Shop Vouchers)."""

from unittest.mock import MagicMock, patch

from cashback_bot import shop_voucher


def test_format_amount():
    assert shop_voucher.format_amount(None) == "0₫"
    assert shop_voucher.format_amount(0) == "0₫"
    # Shopee micro-units (>= 1.000.000.000)
    assert shop_voucher.format_amount(10_000_000_000) == "100.000₫"
    assert shop_voucher.format_amount(20_000_000_000) == "200.000₫"
    # Số tiền VND bình thường (< 1.000.000.000)
    assert shop_voucher.format_amount(250_000) == "250.000₫"
    assert shop_voucher.format_amount(15_000_000) == "15.000.000₫"


def test_format_vouchers_detail_escapes_html():
    vouchers = [
        {
            "code": "SHOP<SPECIAL>&CODE",
            "discount_percentage": 18,
            "discount_cap": 10_000_000_000,
            "min_spend": 20_000_000_000,
            "percentage_used": 95,
        }
    ]
    detail = shop_voucher.format_vouchers_detail("562665255", vouchers)
    assert "MÃ GIẢM GIÁ TỪ SHOP (Shop ID: 562665255)" in detail
    assert "Giảm 18% (tối đa 100.000₫)" in detail
    assert "SHOP&lt;SPECIAL&gt;&amp;CODE" in detail
    assert "Đơn tối thiểu 200.000₫" in detail
    assert "Đã dùng 95%" in detail


def test_markup_renders_url_buttons():
    from cashback_bot.messages import BotReply

    reply = BotReply(
        "test",
        inline_keyboard=((("🎟️ Mã giảm giá Shop", "https://shopee.vn/shop/123"),), (("🛡️ Lưu ý", "u:tip"),)),
    )
    markup = reply.markup()
    assert markup == {
        "inline_keyboard": [
            [{"text": "🎟️ Mã giảm giá Shop", "url": "https://shopee.vn/shop/123"}],
            [{"text": "🛡️ Lưu ý", "callback_data": "u:tip"}],
        ]
    }


def test_card_row():
    assert shop_voucher.card_row(None) == ()
    assert shop_voucher.card_row("") == ()
    row = shop_voucher.card_row(562665255)
    assert len(row) == 1
    assert row[0][0][0] == "🎟️ Mã giảm giá Shop"
    assert row[0][0][1] == "https://shopee.vn/shop/562665255"

    row_aff = shop_voucher.card_row(562665255, "17000000000")
    assert "an_redir" in row_aff[0][0][1]
    assert "affiliate_id=17000000000" in row_aff[0][0][1]
    assert shop_voucher.card_row(None) == ()
    assert shop_voucher.card_row("") == ()
    row = shop_voucher.card_row(562665255)
    assert len(row) == 1
    assert row[0][0][0] == "🎟️ Mã giảm giá Shop"
    assert row[0][0][1] == "https://shopee.vn/shop/562665255"

    row_aff = shop_voucher.card_row(562665255, "17000000000")
    assert "an_redir" in row_aff[0][0][1]
    assert "affiliate_id=17000000000" in row_aff[0][0][1]


def test_enabled_default_off():
    repo = MagicMock()
    repo.get_state.return_value = None
    assert shop_voucher.enabled(repo) is False

    repo.get_state.return_value = "0"
    assert shop_voucher.enabled(repo) is False

    repo.get_state.return_value = "1"
    assert shop_voucher.enabled(repo) is True


def test_action_bridge_failure_does_not_say_no_vouchers():
    repo = MagicMock()
    with patch("cashback_bot.shop_voucher.fetch_shop_vouchers", return_value=(False, [])):
        reply = shop_voucher.action(repo, 123456, "u:sv:562665255")
        assert reply.toast == "Tạm thời chưa kiểm tra được mã shop, bạn xem trực tiếp trên app Shopee nhé!"
        assert not reply.text


def test_action_shop_has_no_vouchers():
    repo = MagicMock()
    with patch("cashback_bot.shop_voucher.fetch_shop_vouchers", return_value=(True, [])):
        reply = shop_voucher.action(repo, 123456, "u:sv:562665255")
        assert reply.toast == "Shop này hiện chưa có mã giảm giá riêng."
        assert not reply.text


def test_action_has_vouchers_and_one_click_button():
    repo = MagicMock()
    fake_vouchers = [
        {"code": "SVIP10", "discount_percentage": 10, "min_spend": 10_000_000_000}
    ]
    with patch("cashback_bot.shop_voucher.fetch_shop_vouchers", return_value=(True, fake_vouchers)):
        reply = shop_voucher.action(repo, 123456, "u:sv:562665255", affiliate_id="23456789")
        assert "Tìm thấy 1 mã từ Shop!" in (reply.toast or "")
        assert "SVIP10" in (reply.text or "")
        # Kiểm tra nút mở shop trực tiếp có gắn affiliate url
        assert reply.button_label == "🎟️ Mở Shop để Lưu Mã"
        assert reply.button_url is not None
        assert "s.shopee.vn/an_redir" in reply.button_url
        assert "sub_id=VOUCHERS" in reply.button_url
        assert "shop%2F562665255" in reply.button_url


def test_bridge_timeout_is_tightened():
    assert shop_voucher.REQUEST_TIMEOUT_SEC == (0.5, 0.8)


def test_lru_cache_eviction():
    shop_voucher._CACHE.clear()
    # Fill cache up to 500 items
    for i in range(500):
        shop_voucher._cache_set(f"shop_{i}", [{"code": f"V_{i}"}])
    assert len(shop_voucher._CACHE) == 500

    # Access shop_0 to make it recently used
    assert shop_voucher._cache_get("shop_0") is not None

    # Add 501st item - should trigger partial eviction (20%), NOT clear all
    shop_voucher._cache_set("shop_new", [{"code": "NEW"}])
    assert len(shop_voucher._CACHE) > 350
    assert "shop_new" in shop_voucher._CACHE
    # shop_0 should still exist because its timestamp was refreshed
    assert "shop_0" in shop_voucher._CACHE
    # shop_1 was oldest and should have been evicted
    assert "shop_1" not in shop_voucher._CACHE
    shop_voucher._CACHE.clear()


def test_format_vouchers_detail_type_guards():
    # Malformed voucher objects should not crash the formatter
    malformed_vouchers = [
        "not a dict",
        None,
        {"code": None, "discount_percentage": "not a number"},
        {"code": "VOUCH1", "discount_percentage": 20, "discount_cap": "bad_cap", "min_spend": None},
        {"code": "VOUCH2", "discount_value": 50000, "percentage_used": "bad_used"},
        {"code": "VOUCH3", "discount_value": None, "discount_percentage": None},
    ]
    # Should not raise any TypeError or AttributeError
    detail = shop_voucher.format_vouchers_detail(123456, malformed_vouchers)
    assert "Shop ID: 123456" in detail
    assert "VOUCH1" in detail
    assert "Giảm 20%" in detail
    assert "VOUCH2" in detail
    assert "50.000₫" in detail

    # None or non-list vouchers
    assert "hiện chưa có mã" in shop_voucher.format_vouchers_detail(123, None)
    assert "hiện chưa có mã" in shop_voucher.format_vouchers_detail(123, "invalid")


def test_format_vouchers_detail_length_capping():
    many_vouchers = [
        {
            "code": f"CODE_{i}_VERY_LONG_STRING_THAT_TAKES_A_LOT_OF_SPACE_TO_TEST_FIT_HTML",
            "discount_percentage": 10,
            "min_spend": 10000000000,
        }
        for i in range(50)
    ]
    detail = shop_voucher.format_vouchers_detail("999", many_vouchers)
    assert len(detail) <= 4000
    assert "CODE_1_" in detail


def test_card_row_validates_shop_id():
    assert shop_voucher.card_row("not_a_number") == ()
    assert shop_voucher.card_row("123; DROP TABLE") == ()
    assert shop_voucher.card_row("https://evil.com") == ()
    assert shop_voucher.card_row(None) == ()
    assert shop_voucher.card_row("") == ()

    # Valid shop_id with whitespace is accepted after stripping
    row = shop_voucher.card_row("  987654  ")
    assert len(row) == 1
    assert "https://shopee.vn/shop/987654" in row[0][0][1]

