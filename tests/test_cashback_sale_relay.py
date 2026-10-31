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
        with patch("cashback_bot.sale_relay._head", return_value=mock_resp):
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



def test_extract_voucher_codes_bai_tong_hop_moi_dong_mot_ma():
    text = (
        "🔥 TỔNG HỢP MÃ SHOPEE 11.11 🔥\n"
        "1. Mã SVIP15 giảm 15% tối đa 50k đơn tối thiểu 0đ\n"
        "2. Mã FSV50K giảm 50k đơn từ 199k\n"
        "3. SPAYLATER11: giảm 20% max 100K, ĐTT 1,5tr\n"
        "👉 Lưu tại https://s.shopee.vn/ABCD1234"
    )
    found = sale_relay.extract_voucher_codes(text)
    assert [v["code"] for v in found] == ["SVIP15", "FSV50K", "SPAYLATER11"], "bỏ chữ HOA thường gặp và mã trong URL"
    assert found[0] == {"code": "SVIP15", "discount": "15%", "discount_percent": 15.0, "discount_vnd": None,
                        "max_discount_vnd": 50_000, "min_spend_vnd": 0}
    assert (found[1]["discount"], found[1]["discount_vnd"], found[1]["min_spend_vnd"]) == ("50k", 50_000, 199_000)
    assert (found[2]["discount_percent"], found[2]["max_discount_vnd"], found[2]["min_spend_vnd"]) == \
        (20.0, 100_000, 1_500_000)


def test_extract_voucher_codes_dieu_kien_dong_duoi_va_nhieu_ma_mot_dong():
    text = (
        "Mã: METAPARIGDOCT2211\n"
        "Giảm 22% - Tối đa 300K - Đơn tối thiểu 50.000đ\n"
        "Hai mã: XBH1030 giảm 10% | XBL1030 giảm 30k đơn từ 0"
    )
    found = {v["code"]: v for v in sale_relay.extract_voucher_codes(text)}
    assert set(found) == {"METAPARIGDOCT2211", "XBH1030", "XBL1030"}
    assert (found["METAPARIGDOCT2211"]["discount_percent"], found["METAPARIGDOCT2211"]["max_discount_vnd"],
            found["METAPARIGDOCT2211"]["min_spend_vnd"]) == (22.0, 300_000, 50_000), "dòng dưới thuộc mã phía trên"
    assert found["XBH1030"]["discount"] == "10%" and found["XBH1030"]["min_spend_vnd"] is None, \
        "mã cùng dòng không lấy điều kiện của mã sau"
    assert (found["XBL1030"]["discount_vnd"], found["XBL1030"]["min_spend_vnd"]) == (30_000, 0)


def test_extract_voucher_codes_khong_co_ma_va_ma_trung():
    assert sale_relay.extract_voucher_codes("") == []
    assert sale_relay.extract_voucher_codes("SALE HOT 100K FREESHIP cho đơn từ 2TR, 12.12 nha cả nhà") == [], \
        "chữ HOA thường gặp, số tiền viết HOA, ngày sale không phải mã"
    found = sale_relay.extract_voucher_codes("Mã ABCD99 giảm 5%\nNhắc lại: ABCD99 giảm 5%, mã abcd12 không viết hoa")
    assert [v["code"] for v in found] == ["ABCD99"], "mã trùng chỉ giữ lần đầu, mã chữ thường bỏ"


def test_tick_quet_trong_luong_nen_khong_chay_chong():
    import threading
    import time

    gate, started = threading.Event(), threading.Event()

    def slow_run(*_args):
        started.set()
        gate.wait(5)

    sale_relay._LAST_TICK = 0.0
    with patch("cashback_bot.sale_relay.run_once", side_effect=slow_run) as run:
        thread = sale_relay.tick(MagicMock(), MagicMock(), "17315920094")
        assert thread is not None and started.wait(5), "tick trả ngay, lượt quét chạy ở luồng nền"
        sale_relay._LAST_TICK = 0.0
        assert sale_relay.tick(MagicMock(), MagicMock(), "17315920094") is None, "lượt trước chưa xong: không chạy chồng"
        gate.set()
        thread.join(5)
        assert run.call_count == 1 and not sale_relay._running.locked()
        sale_relay._LAST_TICK = time.time()
        assert sale_relay.tick(MagicMock(), MagicMock(), "17315920094") is None, "chưa tới POLL_INTERVAL_SEC"
    sale_relay._LAST_TICK = 0.0
    assert sale_relay.tick(MagicMock(), MagicMock(), None) is None, "không có affiliate_id: không quét"


def test_resolve_chi_head_link_rut_gon():
    redirect = MagicMock(status_code=302, headers={"Location": "https://shopee.vn/product/1/2?sp_atk=x"})
    with patch("cashback_bot.sale_relay.is_safe_shopee_url", return_value=True), \
         patch("cashback_bot.sale_relay._head", return_value=redirect) as head:
        wrapped = sale_relay.resolve_shopee_link("https://s.shopee.vn/abc123", "17315920094")
        assert head.call_count == 1, "tới trang shopee.vn thì dừng, không HEAD thêm"
        assert "origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F1%2F2&" in wrapped
        sale_relay.resolve_shopee_link("https://shopee.vn/product/1/2", "17315920094")
        old = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fproduct%2F3%2F4&affiliate_id=1"
        assert "product%2F3%2F4" in sale_relay.resolve_shopee_link(old, "17315920094")
        assert head.call_count == 1, "trang sản phẩm và an_redir không cần HEAD"


def test_cache_dns_va_link_chi_trong_mot_luot_quet():
    public = [(2, 1, 6, "", ("147.75.0.1", 0))]
    with patch("socket.getaddrinfo", return_value=public) as dns:
        sale_relay._RUN = {"dns": {}, "links": {}}
        try:
            assert sale_relay.is_safe_shopee_url("https://shopee.vn/a")
            assert sale_relay.is_safe_shopee_url("https://shopee.vn/b")
            assert dns.call_count == 1, "cùng host trong một lượt: phân giải một lần"
            with patch("cashback_bot.sale_relay.resolve_shopee_link", return_value="W") as resolve:
                assert sale_relay._resolve("https://s.shopee.vn/x", "1") == sale_relay._resolve("https://s.shopee.vn/x", "1")
                assert resolve.call_count == 1, "link gặp lại trong lượt: dùng kết quả cũ"
        finally:
            sale_relay._RUN = None
        sale_relay.is_safe_shopee_url("https://shopee.vn/c")
        assert dns.call_count == 2, "ngoài lượt quét: luôn kiểm tra lại"


def test_thay_link_mot_luot_khong_thay_chong():
    short, page = "https://s.shopee.vn/abcdef", "https://shopee.vn/p"
    post = {"id": 1, "text": f"A {short} B {page}", "photo_url": None, "shopee_links": [short, page]}
    mapping = {short: f"NEW1({page})", page: "NEW2"}
    with patch("cashback_bot.sale_relay._resolve", side_effect=lambda link, _aff: mapping[link]):
        text, first, _buttons = sale_relay.process_post_content(post, "1")
    assert text == f"A NEW1({page}) B NEW2" and first == f"NEW1({page})"


def test_luu_ma_boc_duoc_vao_voucher_posts_de_magiam_hien(tmp_path):
    from datetime import datetime, timedelta, timezone

    from cashback_bot import voucher
    from cashback_bot.db import TrackingRepository

    repo = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    repo.migrate()
    now = datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc)
    text = "Mã SVIP15 giảm 15% tối đa 50k đơn từ 0đ\nMã FSV50K giảm 50k đơn từ 199k"
    url = "https://s.shopee.vn/an_redir?origin_link=x&affiliate_id=1&sub_id=AUTOSALE"
    assert sale_relay.store_codes(repo, "nhomsansale", 500, text, url, now) == 2
    with repo.connect() as conn:
        rows = conn.execute("SELECT * FROM voucher_posts ORDER BY id").fetchall()
        assert [(r["code"], r["discount"], r["max_discount"], r["min_spend"], r["message_id"]) for r in rows] == [
            ("SVIP15", "15%", "50.000đ", "0đ", 50_000), ("FSV50K", "50k", "", "199.000đ", 50_001)]
        assert {r["channel_id"] for r in rows} == {sale_relay.source_channel_id("nhomsansale")}
        assert all(r["sent"] == 0 and r["url"] == url and r["status"] == "live" for r in rows)
        assert [r["code"] for r in voucher.live(conn, now)] == ["FSV50K", "SVIP15"]
    assert sale_relay.source_channel_id("nhomsansale") > -10**10, "không trùng id kênh Telegram thật (-100…)"
    assert sale_relay.store_codes(repo, "nhomsansale", 501, text, None, now + timedelta(hours=1)) == 0, \
        "mã đã có trong 24 giờ: không ghi lại"
    assert sale_relay.store_codes(repo, "nhomsansale", 502, text, None, now + timedelta(hours=25)) == 2
    repo.set_state(voucher.CHANNEL_KEY, "-1001")
    repo.set_state(voucher.AUDIENCE_KEY, "all")
    assert voucher.tick(repo, now + timedelta(hours=26)) == 0, "relay tự gửi khách: voucher.tick không gửi lại"


def test_scan_channel_luu_ma_ca_bai_khong_co_link():
    repo = MagicMock()
    repo.get_state.return_value = "99"
    sample_html = """
    <div class="tgme_widget_message_wrap"><div data-post="nhomsansale/100">
      <div class="tgme_widget_message_text">Mã ABCD99 giảm 10% đơn từ 0đ</div></div></div>
    """
    with patch("requests.get") as mock_get, patch("cashback_bot.sale_relay.store_codes") as store:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = sample_html
        sale_relay._scan_channel("nhomsansale", repo, MagicMock(), "17315920094", -1004496405998)
    store.assert_called_once_with(repo, "nhomsansale", 100, "Mã ABCD99 giảm 10% đơn từ 0đ", None)
    repo.set_state.assert_called_with("relay_seen:nhomsansale", "100")


def test_post_html_an_link_trung_nut_boc_link_con_lai():
    wrapped = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fm%2Fvip&affiliate_id=1&sub_id=AUTOSALE"
    other = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fp&affiliate_id=1&sub_id=AUTOSALE"
    buttons = [[{"text": "🎟 Lưu mã trên Shopee ↗", "url": wrapped}]]
    assert sale_relay.post_html(f"Mã 25% Shopee vip   {wrapped}", buttons) == "Mã 25% Shopee vip", \
        "link đã có nút: bỏ khỏi chữ"
    out = sale_relay.post_html(f"Mã A <b>: {wrapped}\nMã B: {other}.\nNhóm: https://t.me/x", buttons)
    assert "%3A%2F%2F" not in out.replace(f'href="{other.replace("&", "&amp;")}"', ""), "không in URL dài trong chữ"
    assert f'<a href="{other.replace("&", "&amp;")}">🔗 Lưu mã</a>.' in out
    assert "t.me" not in out and "Nhóm" not in out, "link không phải Shopee: bỏ cả dòng"
    assert "Mã A &lt;b&gt;:" in out, "chữ thường vẫn escape"
    assert sale_relay.post_html(f"Deal áo {other}", []) == f'Deal áo <a href="{other.replace("&", "&amp;")}">🔗 Mua ngay</a>'


def test_post_html_chi_giu_link_shopee_bo_cum_chi_co_link_ngoai():
    vip = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fm%2Fvip&affiliate_id=1&sub_id=AUTOSALE"
    video = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fvideo&affiliate_id=1&sub_id=AUTOSALE"
    text = (
        "🔥 🔥 SĂN MÃ SHOPEE LÚC 15H\n———\n.\n"
        "🔥 Săn deal Shopee flash sale 1K 9K nhomsansale.com/flashsale\n.\n"
        f"🔥 Mã Shopee Vip {vip}\n► 15h: Mã 25% tối đa 200k từ 0đ\n.\n"
        "🔥 Tạo link dùng mã FB nhomsansale.com/fb\n► Fb 25% tối đa 500k\n.\n"
        f"🔥 Shopee Video {video}\n► Gửi link để gắn tag video tại https://t.me/gantag\n"
        "► Xem các sản phẩm đã gắn tag video https://nhomsansale.com\n► Kênh tổng hợp shopee.vn/m/kenh"
    )
    out = sale_relay.post_html(text, [])
    assert "nhomsansale" not in out and "t.me" not in out and "🔗 Link" not in out
    assert "flash sale 1K 9K" not in out and "Fb 25% tối đa 500k" not in out, "cụm chỉ có link ngoài: bỏ cả cụm"
    assert "gắn tag video" not in out, "dòng chỉ có link ngoài: bỏ dòng"
    assert out.startswith("🔥 🔥 SĂN MÃ SHOPEE LÚC 15H\n———\n\n🔥 Mã Shopee Vip <a href="), \
        "đầu bài không link: giữ; dòng «.» thành dòng trống"
    assert "► 15h: Mã 25% tối đa 200k từ 0đ" in out and "🔥 Shopee Video <a href=" in out
    assert "► Kênh tổng hợp shopee.vn/m/kenh" in out, "tên miền trần Shopee: giữ nguyên chữ"
    assert "\n.\n" not in out and "\n\n\n" not in out and not out.endswith("\n")


def test_gui_kenh_va_khach_dung_html_gon(tmp_path):
    from cashback_bot.db import TrackingRepository

    wrapped = "https://s.shopee.vn/an_redir?origin_link=x&affiliate_id=1&sub_id=AUTOSALE"
    buttons = [[{"text": "🎟 Lưu mã trên Shopee ↗", "url": wrapped}]]
    telegram = MagicMock()
    sale_relay.send_to_channel(telegram, -100123, f"Mã hot {wrapped}", None, buttons)
    assert telegram.send_message.call_args[0][1] == "Mã hot"
    repo = TrackingRepository(str(tmp_path / "c.sqlite"))
    repo.migrate()
    assert sale_relay.enqueue_for_subscribers(repo, 7, f"Mã hot {wrapped}", buttons, [111]) == 1
    with repo.connect() as conn:
        assert conn.execute("SELECT message_html FROM admin_notifications").fetchone()[0] == "Mã hot"


def test_zalo_tin_ma_dan_link_bang_nhan_nut_mot_tin():
    from cashback_bot.zalo_bot import ZaloSender

    api, store = MagicMock(), MagicMock()
    store.external_id.return_value = "zalo-1"
    markup = {"inline_keyboard": [[{"text": "🎟 Lưu mã trên Shopee ↗", "url": "https://s.shopee.vn/an_redir?x=1"}],
                                  [{"text": "🔕 Tắt báo mã", "callback_data": "u:vc:off"}]]}
    ZaloSender(api, store).send_message(-5, "Mã hot", markup)
    [call] = api.send_message.call_args_list
    text = call[0][1]
    assert text.startswith("Mã hot\n\n👉 🎟 Lưu mã trên Shopee:\nhttps://s.shopee.vn/an_redir?x=1"), text
    assert "Bấm link này để mua" not in text and "1 · 🔕 Tắt báo mã" in text


def test_default_channels_chua_ca_hai_kenh():
    assert "nhomsansale" in sale_relay.DEFAULT_CHANNELS
    assert "sansaletele" in sale_relay.DEFAULT_CHANNELS
    assert len(sale_relay.DEFAULT_CHANNELS) >= 2


def test_check_trung_giua_hai_kenh(tmp_path):
    from datetime import datetime, timedelta, timezone
    from cashback_bot.db import TrackingRepository
    repo = TrackingRepository(str(tmp_path / "dedup.sqlite"))
    repo.migrate()

    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    # Kênh 1 đăng deal với link sản phẩm và mã voucher
    keys1 = sale_relay.extract_dedup_keys("Mã VIP100K giảm 100k tai nghe Sony", ["https://shopee.vn/product/123/456?sp_atk=1"])
    assert "code:VIP100K" in keys1
    assert "url:shopee.vn/product/123/456" in keys1

    # Lúc đầu chưa đăng: không trùng
    is_dup, _ = sale_relay.is_duplicate_deal(repo, keys1, now=now)
    assert not is_dup

    # Kênh nhomsansale đăng thành công:
    sale_relay.mark_deal_posted(repo, keys1, "nhomsansale", 101, now=now)

    # 15 phút sau, kênh sansaletele đăng cùng sản phẩm (dù URL có query tracking khác hoặc affiliate khác):
    keys2 = sale_relay.extract_dedup_keys("Tai nghe Sony siêu sale kèm mã VIP100K", ["https://shopee.vn/product/123/456?utm_source=other"])
    is_dup2, dup_info2 = sale_relay.is_duplicate_deal(repo, keys2, now=now + timedelta(minutes=15))
    assert is_dup2, "Phải phát hiện bài trùng từ kênh 2"
    assert "nhomsansale #101" in dup_info2

    # 13 giờ sau (> DEDUP_WINDOW 12h), cùng sản phẩm đó được đăng đợt flash sale mới -> không coi là trùng nữa:
    is_dup_later, _ = sale_relay.is_duplicate_deal(repo, keys2, now=now + timedelta(hours=13))
    assert not is_dup_later, "Sau 12 giờ thì cho phép đăng lại đợt mới"



def _full_ma_post() -> str:
    """Bài «FULL MÃ SHOPEE» (relay:65102, 2026-10-31) dạng post_html, link rút gọn cho dễ đọc."""
    a = lambda n: f'<a href="https://s.shopee.vn/m{n}">🔗 Lưu mã</a>'  # noqa: E731
    return "\n".join([
        "FULL MÃ SHOPEE - LAZADA 18H - 21H", "",
        "📌 VOUCHER EXTRA", f"◼️ 18H: Back X2 mã 25% tối đa 100K/100K tại: {a(1)}", "",
        "📌 SHOPEE VIP", f"◼️ 18H,20H: Back mã giảm 25% tối đa 200K/0Đ lưu tại : {a(2)}",
        f"◼️ Cào xu thời trang hoàn 10% tối đa 100K/150K: {a(2)}", "",
        "📌 BÁCH HOÁ", f"◼️ 18H: Back X5 mã bách hoá giảm 30% tối đa 100K/300K lưu tại: {a(3)}", f"◼️ Áp list: {a(4)}", "",
        "📌 MÃ ĐỘC QUYỀN MXH", f"◼️ 20H: Back mã MXH 50%, 30% tối đa 50K tại: {a(5)}", "",
        "📌 ÁP TOÀN SÀN (LỌC USER)", f"◼️ Mã 80K/0Đ: {a(6)} + {a(7)} + {a(8)}", f"◼️ Mã giảm 50K/0Đ: {a(9)}", "",
        "📌 ÁP ĐA SỐ", f"◼️ AFFV266 giảm 35K/129K áp list: {a(10)}", f"◼️ AFFANAN giảm 40K/159K áp list: {a(11)}", "",
        "📌 CÁC MÃ KHÁC", f"◼️ X10 mã Xử lý giảm 35% tối đa 25K/20K sẵn ví áp list: {a(12)} (Mã ngày 29/10)",
        f"◼️ X10 mã quốc tế giảm 15K/20K sẵn ví áp list: {a(13)}", "",
        "📌 GAME", f"◼️ 21H: Chơi game nông trại săn mã thời trang 500K/0Đ: {a(14)}",
        f"◼️ Mở quà nhận 50K, 100K xu: {a(15)} ( Không lọc acc )", "◼️ Vào Shopee pay - quét QR chuyển 10K", "",
        f"📌 LƯU SỚM MÃ SPAYLATER GIẢM 11TR/5TR DÙNG SALE 11/11: {a(16)}",
    ])


def test_zalo_digest_giu_toi_da_6_link_chat_luong():
    from datetime import datetime, timezone

    out = sale_relay.zalo_digest(_full_ma_post(), now=datetime(2026, 10, 31, 10, 43, tzinfo=timezone.utc))
    kept = sale_relay._A_HREF.findall(out)
    assert [u.rsplit("/", 1)[1] for u in kept] == ["m1", "m2", "m3", "m5", "m10", "m11"], "giữ thứ tự bài gốc"
    assert out.startswith("FULL MÃ SHOPEE - LAZADA 18H - 21H\n\n📌 VOUCHER EXTRA\n"), "giữ tên bài + tiêu đề cụm"
    assert "LỌC USER" not in out and "GAME" not in out and "Shopee pay" not in out and "SPAYLATER" not in out
    assert "Mã ngày 29/10" not in out and "Cào xu" not in out and "Áp list" not in out
    assert out.endswith("bot chọn 6/16 link dễ dùng nhất, bỏ mã lọc tài khoản, game, mã cũ.</i>")
    few = '◼️ Mã A <a href="https://s.shopee.vn/a">🔗 Lưu mã</a>\n◼️ Game <a href="https://s.shopee.vn/b">🔗 Lưu mã</a>'
    assert sale_relay.zalo_digest(few) == few, "bài ít link: giữ nguyên"


def test_zalo_digest_khong_muc_nao_dat_van_lay_muc_tot_nhat():
    from datetime import datetime, timezone

    post = "\n".join(f'◼️ Chơi game {n}: <a href="https://s.shopee.vn/g{n}">🔗 Lưu mã</a>' for n in range(8))
    out = sale_relay.zalo_digest(post, now=datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert len(sale_relay._A_HREF.findall(out)) == 6 and "6/8" in out


def test_khach_zalo_nhan_ban_gon_telegram_nhan_du(tmp_path):
    from cashback_bot.db import TrackingRepository

    repo = TrackingRepository(str(tmp_path / "c.sqlite"))
    repo.migrate()
    with patch.object(sale_relay, "post_html", return_value=_full_ma_post()):
        assert sale_relay.enqueue_for_subscribers(repo, 7, "x", [], [111, -5]) == 2
    with repo.connect() as conn:
        rows = dict(conn.execute("SELECT chat_id, message_html FROM admin_notifications"))
    assert rows[111] == _full_ma_post()
    assert len(sale_relay._A_HREF.findall(rows[-5])) == 6 and "Bản gọn" in rows[-5]
