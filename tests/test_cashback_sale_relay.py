"""Kiểm thử tính năng tự động chuyển tiếp tin săn sale (PLAN-106)."""

from unittest.mock import MagicMock, patch

from cashback_bot import sale_relay


def test_clean_shopee_url():
    raw = (
        "https://shopee.vn/m/goi-ShopeeVIP?mmp_pid=an_17368430110"
        "&uls_trackid=570lq4d000lb&utm_source=an_17368430110&utm_medium=affiliates"
    )
    clean = sale_relay._clean_shopee_url(raw)
    assert clean == "https://shopee.vn/m/goi-ShopeeVIP"


def test_parse_channel_html():
    sample_html = """
    <div class="tgme_widget_message_wrap">
      <div class="tgme_widget_message" data-post="nhomsansale/99304">
        <div class="tgme_widget_message_bubble">
          <div class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.tele.pe/sample.jpg')"></div>
          <div class="tgme_widget_message_text">Mã giảm 30% nè<br>Check ngay https://s.shopee.vn/7Ad4vEC2TY</div>
        </div>
      </div>
    </div>
    """
    posts = sale_relay.parse_channel_html(sample_html)
    assert len(posts) == 1
    assert posts[0]["id"] == 99304
    assert posts[0]["photo_url"] == "https://cdn.tele.pe/sample.jpg"
    assert "Mã giảm 30% nè" in posts[0]["text"]
    assert "https://s.shopee.vn/7Ad4vEC2TY" in posts[0]["shopee_links"]


def test_process_post_content():
    post = {
        "id": 123,
        "text": "Deal hot nè: https://s.shopee.vn/4fxOJfjyWC mua gấp!",
        "photo_url": None,
        "shopee_links": ["https://s.shopee.vn/4fxOJfjyWC"],
    }
    with patch("cashback_bot.sale_relay.resolve_shopee_link", return_value="https://s.shopee.vn/an_redir?origin_link=clean&affiliate_id=123"):
        text, first_link, buttons = sale_relay.process_post_content(post, "123")
        assert "an_redir" in text
        assert first_link == "https://s.shopee.vn/an_redir?origin_link=clean&affiliate_id=123"
        assert len(buttons) == 1
        assert buttons[0][0]["url"] == first_link


def test_scan_channel_first_run_does_not_send():
    repo = MagicMock()
    repo.get_state.return_value = None  # first run
    telegram = MagicMock()

    sample_html = """
    <div class="tgme_widget_message_wrap">
      <div data-post="nhomsansale/100">
        <div class="tgme_widget_message_text">Post 100 https://s.shopee.vn/abc</div>
      </div>
    </div>
    """
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = sample_html

        sale_relay._scan_channel("nhomsansale", repo, telegram, "17315920094", -1004496405998)

        # Lần đầu tiên chỉ lưu last_id, không gửi
        repo.set_state.assert_called_with("relay_seen:nhomsansale", "100")
        telegram.send_message.assert_not_called()


def test_is_safe_shopee_url_blocks_ssrf():
    # Private / loopback / link-local / reserved IPs
    assert sale_relay.is_safe_shopee_url("http://127.0.0.1:9224/api/shop_vouchers?shopee.vn") is False
    assert sale_relay.is_safe_shopee_url("https://127.0.0.1:9224/api/shop_vouchers") is False
    assert sale_relay.is_safe_shopee_url("https://169.254.169.254/latest/meta-data/") is False
    assert sale_relay.is_safe_shopee_url("https://10.0.0.1/shopee.vn") is False
    assert sale_relay.is_safe_shopee_url("https://192.168.1.1/shopee.vn") is False
    assert sale_relay.is_safe_shopee_url("https://[::1]/shopee.vn") is False

    # Domain bypass attempts
    assert sale_relay.is_safe_shopee_url("http://shopee.vn.evil.com/test") is False
    assert sale_relay.is_safe_shopee_url("https://evil.com/shopee.vn") is False
    assert sale_relay.is_safe_shopee_url("https://attacker-shopee.vn") is False

    # Credentials in URL
    assert sale_relay.is_safe_shopee_url("https://admin:pass@shopee.vn/test") is False

    # Non-https
    assert sale_relay.is_safe_shopee_url("http://shopee.vn/test") is False

    # Valid Shopee URL
    assert sale_relay.is_safe_shopee_url("https://shopee.vn/product/123/456") is True
    assert sale_relay.is_safe_shopee_url("https://s.shopee.vn/7Ad4vEC2TY") is True


def test_is_safe_photo_url_whitelist():
    # Only HTTPS and whitelisted Telegram CDN domains
    assert sale_relay.is_safe_photo_url("https://cdn4.telesco.pe/file/abc.jpg") is True
    assert sale_relay.is_safe_photo_url("http://cdn4.telesco.pe/file/abc.jpg") is False  # not https
    assert sale_relay.is_safe_photo_url("https://127.0.0.1:9224/image.jpg") is False
    assert sale_relay.is_safe_photo_url("https://evil.com/fake_telesco.pe/image.jpg") is False
    assert sale_relay.is_safe_photo_url("https://evil-telesco.pe/image.jpg") is False


def test_unwrap_prevents_double_an_redir():
    # Single wrap
    single_wrap = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F123&affiliate_id=111"
    assert sale_relay._unwrap(single_wrap) == "https://shopee.vn/product/123"

    # Nested / double wrap
    nested_wrap = (
        "https://s.shopee.vn/an_redir?origin_link="
        "https%3A%2F%2Fs.shopee.vn%2Fan_redir%3Forigin_link%3Dhttps%253A%252F%252Fshopee.vn%252Fproduct%252F456"
        "&affiliate_id=222"
    )
    assert sale_relay._unwrap(nested_wrap) == "https://shopee.vn/product/456"

    # Normal URL unchanged
    normal = "https://shopee.vn/product/789"
    assert sale_relay._unwrap(normal) == normal


def test_clean_shopee_url_comprehensive_tracking_removal():
    dirty = (
        "https://shopee.vn/product/123/456?"
        "utm_source=aff&utm_medium=cpc&utm_campaign=sale&utm_term=keyword&utm_content=banner&"
        "mmp_pid=an_123&uls_trackid=xyz&gads_t_sig=sig1&affiliate_id=old_aff&sub_id=old_sub&"
        "af_sub_siteid=sub&c=camp&is_from_login=1&smtt=0.0.9&deep_and_deferred_rec=1&pid=pid1&"
        "af_dp=app&af_web_dp=web&af_adset=adset1&af_ad=ad1&af_channel=fb&keep_param=valid_value"
    )
    cleaned = sale_relay._clean_shopee_url(dirty)
    assert "keep_param=valid_value" in cleaned
    assert "utm_source" not in cleaned
    assert "mmp_pid" not in cleaned
    assert "affiliate_id" not in cleaned
    assert "af_sub_siteid" not in cleaned
    assert "smtt" not in cleaned
    assert "deep_and_deferred_rec" not in cleaned


def test_process_post_content_prefix_sorting():
    post = {
        "id": 101,
        "text": "Link 1: https://shp.ee/abc và Link 2: https://shp.ee/abcdef",
        "photo_url": None,
        "shopee_links": ["https://shp.ee/abc", "https://shp.ee/abcdef"],
    }
    with patch("cashback_bot.sale_relay.resolve_shopee_link") as mock_resolve:
        mock_resolve.side_effect = lambda u, aff: f"https://s.shopee.vn/an_redir?aff={aff}&u={u}"
        text, first_link, buttons = sale_relay.process_post_content(post, "777")
        # Ensure the longer URL was replaced without prefix mangling
        assert "u=https://shp.ee/abcdef" in text
        assert "u=https://shp.ee/abc " in text or "u=https://shp.ee/abc" in text
        # Must not contain corrupted strings like https://s.shopee.vn/an_redir?aff=777&u=https://shp.ee/abcdefdef
        assert "abcdefdef" not in text


def test_download_safe_photo_checks_size_limits():
    # 1. Content-Length too big (> 10MB)
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": str(15 * 1024 * 1024)}
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/huge.jpg")
            assert result is None

    # 2. Chunk streaming exceeds 10MB
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}
            mock_resp.iter_content.return_value = [b"A" * (6 * 1024 * 1024), b"B" * (6 * 1024 * 1024)]
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/chunk_huge.jpg")
            assert result is None

    # 3. Valid photo within limit
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": "1000"}
            mock_resp.iter_content.return_value = [b"VALID_IMAGE_DATA"]
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/valid.jpg")
            assert result == b"VALID_IMAGE_DATA"


def test_send_to_channel_escapes_html():
    telegram = MagicMock()
    text = "Áo thun giá < 50k & Voucher > 70%"
    sale_relay.send_to_channel(telegram, -100123456, text, None, [])

    telegram.send_message.assert_called_once()
    args, kwargs = telegram.send_message.call_args
    sent_text = args[1]
    assert "< 50k" not in sent_text
    assert "&lt; 50k &amp; Voucher &gt; 70%" in sent_text


def test_enqueue_for_subscribers_no_br_tags():
    repo = MagicMock()
    conn = MagicMock()
    repo.connect.return_value.__enter__.return_value = conn

    multiline_text = "Dòng 1\nDòng 2\nDòng 3 <tag>"
    with patch("cashback_bot.sale_relay.enqueue_event", return_value=True) as mock_enqueue:
        queued = sale_relay.enqueue_for_subscribers(repo, 999, multiline_text, [], [111, 222])
        assert queued == 2
        calls = mock_enqueue.call_args_list
        for call in calls:
            kwargs = call.kwargs
            html_msg = kwargs["message_html"]
            # Absolutely no <br> tags allowed! Telegram HTML parser fails on <br>
            assert "<br>" not in html_msg
            assert "<br/>" not in html_msg
            assert "&lt;tag&gt;" in html_msg
            assert "Dòng 1\nDòng 2\nDòng 3" in html_msg


def test_resolve_shopee_link_blocks_redirect_to_private_ip():
    # If a short link redirects to a private IP (e.g. 127.0.0.1 or cloud metadata), resolver aborts
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "http://127.0.0.1:9224/api/shop_vouchers"}

    with patch("cashback_bot.sale_relay.is_safe_shopee_url", side_effect=[True, False]):
        with patch("requests.head", return_value=mock_resp):
            result = sale_relay.resolve_shopee_link("https://s.shopee.vn/short123", "12345")
            # Should not wrap the private redirect
            assert "127.0.0.1" not in result
            assert result == "https://s.shopee.vn/short123"


def test_sqlite_wal_pragmas(tmp_path):
    from cashback_bot.db import TrackingRepository
    db_file = str(tmp_path / "test_wal.sqlite")
    repo = TrackingRepository(db_file)
    with repo.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        sync_mode = conn.execute("PRAGMA synchronous").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

        assert journal_mode.lower() == "wal"
        # PRAGMA synchronous: 1 is NORMAL, 2 is FULL
        assert sync_mode in (1, "NORMAL")
        assert busy_timeout >= 15000

