"""Adversarial stress-testing and empirical fuzzing harness for Cashback Bot security hardening (Milestone 1).

Covers:
1. SSRF & URL Resolution Fuzzing:
   - Evaluates is_safe_shopee_url and resolve_shopee_link against 25+ adversarial payloads
     including private/loopback/link-local/cloud-metadata IPs, userinfo/credential bypasses,
     subdomain/open-redirect spoofing, protocol smuggling, and DNS rebinding simulations.
2. Photo Streaming & Byte Cap Testing:
   - Evaluates is_safe_photo_url and _download_safe_photo against non-whitelisted domains,
     Content-Length spoofing, chunked streaming over 10MB, non-HTTPS schemes, and HTTP errors.
3. Button URL & Telegram HTML Escaping:
   - Evaluates _is_safe_button_url against dangerous schemes, whitespace/newline injection,
     BotReply.markup() routing, format_vouchers_detail malformed payloads (None, negative, strings,
     100 vouchers overflow), and Telegram HTML entity escaping.
"""

from unittest.mock import MagicMock, patch
import pytest

from cashback_bot import messages, sale_relay, shop_voucher
from cashback_bot.messages import BotReply, _is_safe_button_url


# ==============================================================================
# TARGET AREA 1: SSRF & URL Resolution Fuzzing
# ==============================================================================

ADVERSARIAL_URLS_FROM_PROMPT = [
    "http://127.0.0.1:9224/api/shop_vouchers?shopee.vn",
    "https://127.0.0.1/",
    "https://localhost/",
    "https://169.254.169.254/",
    "https://[::1]/",
    "https://0.0.0.0/",
    "https://10.0.0.1/",
    "https://172.16.0.1/",
    "https://192.168.1.1/",
    "https://shopee.vn@attacker.com/",
    "https://attacker.com/shopee.vn",
    "https://attacker.com#shopee.vn",
    "https://s.shopee.vn.attacker.com/",
]

ADDITIONAL_ADVERSARIAL_SSRF_URLS = [
    "http://shopee.vn/",  # HTTP instead of HTTPS
    "https://attacker.com/shopee.vn/product/123",
    "https://evil-shopee.vn/item",
    "https://shopee.vn.evil.com/item",
    "https://user:password@shopee.vn/product/123",
    "https://admin:pass@s.shopee.vn/item",
    "ftp://shopee.vn/file",
    "file:///etc/passwd",
    "javascript:alert(document.domain)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "https://[fe80::1]/link-local",
    "https://[::ffff:127.0.0.1]/ipv4-mapped-ipv6",
    "https://10.255.255.255/private",
    "https://172.31.255.255/private",
    "https://192.168.254.254/private",
    "https://127.0.0.1:8080/internal",
    "https://0177.0.0.1/",  # Octal loopback attempt
    "",
    "   ",
]


@pytest.mark.parametrize("url", ADVERSARIAL_URLS_FROM_PROMPT + ADDITIONAL_ADVERSARIAL_SSRF_URLS)
def test_is_safe_shopee_url_rejects_adversarial_payloads(url):
    """Verify that EVERY adversarial URL is rejected by is_safe_shopee_url."""
    assert sale_relay.is_safe_shopee_url(url) is False


def test_is_safe_shopee_url_dns_rebinding_simulation():
    """Simulate DNS rebinding attack where an allowed hostname resolves to a private IP."""
    # Attacker manipulates DNS resolution of shopee.vn to return loopback or private IP
    fake_sockaddr = [
        (2, 1, 0, "", ("127.0.0.1", 0)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_sockaddr):
        assert sale_relay.is_safe_shopee_url("https://shopee.vn/product/123") is False

    fake_private_sockaddr = [
        (2, 1, 0, "", ("10.0.0.5", 0)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_private_sockaddr):
        assert sale_relay.is_safe_shopee_url("https://shopee.vn/product/123") is False


def test_is_safe_shopee_url_accepts_valid_shopee_urls():
    """Verify valid public Shopee domains and subdomains are accepted."""
    assert sale_relay.is_safe_shopee_url("https://shopee.vn/product/123/456") is True
    assert sale_relay.is_safe_shopee_url("https://www.shopee.vn/item") is True
    assert sale_relay.is_safe_shopee_url("https://s.shopee.vn/7Ad4vEC2TY") is True
    assert sale_relay.is_safe_shopee_url("https://shp.ee/abcdef") is True
    assert sale_relay.is_safe_shopee_url("https://vn.shp.ee/xyz123") is True
    assert sale_relay.is_safe_shopee_url("https://shope.ee/mno456") is True


@pytest.mark.parametrize("url", ADVERSARIAL_URLS_FROM_PROMPT)
def test_resolve_shopee_link_rejects_adversarial_input_urls(url):
    """Verify resolve_shopee_link returns safe fallback without fetching adversarial URLs."""
    with patch("requests.head") as mock_head:
        resolved = sale_relay.resolve_shopee_link(url, affiliate_id="12345678")
        # For adversarial URLs, it must return the unmodified input URL without making any network call
        assert resolved == url
        mock_head.assert_not_called()


def test_resolve_shopee_link_rejects_redirect_to_private_ip():
    """Verify that a legitimate short link redirecting to private IP aborts and does not wrap."""
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

    with patch("requests.head", return_value=mock_resp):
        resolved = sale_relay.resolve_shopee_link("https://s.shopee.vn/short_deal", affiliate_id="12345678")
        assert "169.254.169.254" not in resolved
        assert resolved == "https://s.shopee.vn/short_deal"


def test_resolve_shopee_link_rejects_redirect_to_open_redirect_external():
    """Verify that a legitimate short link redirecting to external attacker domain aborts."""
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "https://attacker.com/malicious_payload"}

    with patch("requests.head", return_value=mock_resp):
        resolved = sale_relay.resolve_shopee_link("https://s.shopee.vn/short_deal", affiliate_id="12345678")
        assert "attacker.com" not in resolved
        assert resolved == "https://s.shopee.vn/short_deal"


def test_resolve_shopee_link_bounds_redirect_hops():
    """Verify that an infinite redirect loop terminates at 3 hops."""
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "https://s.shopee.vn/loop_next"}

    with patch("requests.head", return_value=mock_resp) as mock_head:
        sale_relay.resolve_shopee_link("https://s.shopee.vn/loop_start", affiliate_id="12345678")
        assert mock_head.call_count == 3


def test_resolve_shopee_link_with_invalid_affiliate_id():
    """Verify non-numeric affiliate IDs return original URL immediately without network calls."""
    with patch("requests.head") as mock_head:
        assert sale_relay.resolve_shopee_link("https://s.shopee.vn/test", affiliate_id="") == "https://s.shopee.vn/test"
        assert sale_relay.resolve_shopee_link("https://s.shopee.vn/test", affiliate_id="abc") == "https://s.shopee.vn/test"
        assert sale_relay.resolve_shopee_link("https://s.shopee.vn/test", affiliate_id=None) == "https://s.shopee.vn/test"
        assert sale_relay.resolve_shopee_link("https://s.shopee.vn/test", affiliate_id="-123") == "https://s.shopee.vn/test"
        mock_head.assert_not_called()


# ==============================================================================
# TARGET AREA 2: Photo Streaming & Byte Cap Testing
# ==============================================================================

ADVERSARIAL_PHOTO_URLS = [
    "https://evil.com/pic.jpg",
    "http://cdn4.telesco.pe/pic.jpg",  # Non-HTTPS
    "https://telesco.pe.attacker.com/pic.jpg",
    "https://attacker-telesco.pe/pic.jpg",
    "https://admin:pass@cdn4.telesco.pe/pic.jpg",
    "https://127.0.0.1/pic.jpg",
    "https://localhost/pic.jpg",
    "ftp://telegram.org/pic.jpg",
    "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
]


@pytest.mark.parametrize("url", ADVERSARIAL_PHOTO_URLS)
def test_is_safe_photo_url_rejects_adversarial_urls(url):
    """Verify is_safe_photo_url blocks non-whitelisted domains, non-HTTPS, credentials, and IPs."""
    assert sale_relay.is_safe_photo_url(url) is False


def test_is_safe_photo_url_accepts_valid_telegram_cdns():
    """Verify is_safe_photo_url accepts legitimate Telegram CDN domains with public IPs."""
    public_ip_sockaddr = [(2, 1, 0, "", ("91.108.4.1", 0))]
    with patch("socket.getaddrinfo", return_value=public_ip_sockaddr):
        assert sale_relay.is_safe_photo_url("https://telesco.pe/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://cdn1.telesco.pe/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://cdn4.telesco.pe/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://tele.pe/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://cdn.tele.pe/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://telegram.org/file.jpg") is True
        assert sale_relay.is_safe_photo_url("https://cdn.telegram.org/file.jpg") is True


def test_download_safe_photo_rejects_non_whitelisted_domain_without_request():
    """Verify non-whitelisted photo domains return None without making network calls."""
    with patch("requests.get") as mock_get:
        result = sale_relay._download_safe_photo("https://evil.com/pic.jpg")
        assert result is None
        mock_get.assert_not_called()


def test_download_safe_photo_rejects_oversized_content_length():
    """Verify declared Content-Length > 10MB is immediately rejected without streaming."""
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": str(15 * 1024 * 1024)}  # 15MB
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/huge.jpg")
            assert result is None
            mock_resp.iter_content.assert_not_called()


def test_download_safe_photo_spoofed_content_length_stops_at_10mb():
    """Verify Content-Length spoofing (declares 100 bytes but delivers 20MB) is caught."""
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": "100"}  # Spoofed small header

            # Generator yielding 20 chunks of 1MB (total 20MB)
            chunk_1mb = b"X" * (1024 * 1024)
            chunks_delivered = []

            def stream_chunks(chunk_size=65536):
                for _ in range(20):
                    chunks_delivered.append(1)
                    yield chunk_1mb

            mock_resp.iter_content = stream_chunks
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/spoofed.jpg")
            assert result is None
            # Must stop streaming once 10MB limit is crossed (around 11 chunks, not exhausting 20 chunks)
            assert len(chunks_delivered) <= 12
            assert len(chunks_delivered) < 20


def test_download_safe_photo_chunked_streaming_without_content_length():
    """Verify chunked streaming (no Content-Length header) exceeding 10MB is truncated and rejected."""
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {}  # No Content-Length

            chunk_4mb = b"Y" * (4 * 1024 * 1024)
            mock_resp.iter_content.return_value = [chunk_4mb, chunk_4mb, chunk_4mb]  # Total 12MB
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/chunked_huge.jpg")
            assert result is None


def test_download_safe_photo_valid_stream_succeeds():
    """Verify valid image data under 10MB is correctly received."""
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Length": "1024"}
            mock_resp.iter_content.return_value = [b"VALID_IMAGE_BYTES_1024"]
            mock_get.return_value.__enter__.return_value = mock_resp

            result = sale_relay._download_safe_photo("https://cdn4.telesco.pe/valid.jpg")
            assert result == b"VALID_IMAGE_BYTES_1024"


def test_download_safe_photo_http_errors_return_none():
    """Verify non-200 HTTP statuses return None."""
    with patch("cashback_bot.sale_relay.is_safe_photo_url", return_value=True):
        with patch("requests.get") as mock_get:
            for status in (403, 404, 500, 502):
                mock_resp = MagicMock()
                mock_resp.status_code = status
                mock_get.return_value.__enter__.return_value = mock_resp
                assert sale_relay._download_safe_photo("https://cdn4.telesco.pe/error.jpg") is None


# ==============================================================================
# TARGET AREA 3: Button URL & Telegram HTML Escaping
# ==============================================================================

ADVERSARIAL_BUTTON_SCHEMES = [
    "javascript:alert(1)",
    "javascript:void(0)",
    "data:text/html,<script>alert(1)</script>",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "file:///etc/passwd",
    "ftp://valid.com",
    "vbscript:msgbox(1)",
    "chrome://flags",
    "about:blank",
]

INTERNAL_WHITESPACE_BUTTON_URLS = [
    "https://shopee.vn/test url",
    "https://shopee.vn /test",
    "https://shopee.vn\ntest",
    "https://shopee.vn\rtest",
    "https://shopee.vn\ttest",
    "https://shopee.vn\r\ntest",
    "https://shopee.vn/test\npath",
]

INVALID_TYPE_BUTTON_URLS = [
    "",
    "   ",
    "\n\n",
    "\t",
    None,
    12345,
    ["https://shopee.vn"],
]


@pytest.mark.parametrize("url", ADVERSARIAL_BUTTON_SCHEMES)
def test_is_safe_button_url_rejects_dangerous_schemes(url):
    """Verify _is_safe_button_url strictly rejects non-whitelisted schemes."""
    assert _is_safe_button_url(url) is False


@pytest.mark.parametrize("url", INTERNAL_WHITESPACE_BUTTON_URLS)
def test_is_safe_button_url_rejects_internal_whitespace(url):
    """Verify _is_safe_button_url strictly rejects URLs containing internal spaces, tabs, and newlines."""
    assert _is_safe_button_url(url) is False


@pytest.mark.parametrize("url", INVALID_TYPE_BUTTON_URLS)
def test_is_safe_button_url_rejects_empty_and_invalid_types(url):
    """Verify _is_safe_button_url strictly rejects empty strings and non-string types."""
    assert _is_safe_button_url(url) is False


def test_is_safe_button_url_accepts_valid_schemes():
    """Verify _is_safe_button_url accepts https, http, and tg schemes."""
    assert _is_safe_button_url("https://shopee.vn/product/123") is True
    assert _is_safe_button_url("http://shopee.vn/product/123") is True
    assert _is_safe_button_url("tg://resolve?domain=san_sale_bot") is True
    assert _is_safe_button_url("tg://user?id=12345678") is True
    assert _is_safe_button_url("https://valid.com") is True
    assert _is_safe_button_url("http://valid.com") is True


def test_button_url_leading_trailing_whitespace_handling():
    """Verify leading/trailing whitespace is safely trimmed by BotReply.markup()."""
    padded_url = "  https://shopee.vn/shop/123\n"
    # _is_safe_button_url trims padding before checking scheme and internal whitespace
    assert _is_safe_button_url(padded_url) is True

    # BotReply.markup() applies .strip() so no newline or whitespace leaks into payload
    reply = BotReply("test", button_url=padded_url)
    markup = reply.markup()
    assert markup == {
        "inline_keyboard": [[{"text": "🛒 Mua trên Shopee", "url": "https://shopee.vn/shop/123"}]]
    }
    assert "\n" not in markup["inline_keyboard"][0][0]["url"]
    assert " " not in markup["inline_keyboard"][0][0]["url"]


def test_bot_reply_markup_routing_adversarial_buttons():
    """Verify BotReply.markup() drops unsafe button_url and routes tg:// to URL button."""
    # Unsafe button_url is dropped
    reply_js = BotReply("test", button_url="javascript:alert(1)")
    assert reply_js.markup() is None

    # Safe button_url is included
    reply_safe = BotReply("test", button_url="https://shopee.vn/shop/123")
    assert reply_safe.markup() == {
        "inline_keyboard": [[{"text": "🛒 Mua trên Shopee", "url": "https://shopee.vn/shop/123"}]]
    }

    # tg:// in inline keyboard rows is converted to URL button
    reply_tg = BotReply(
        "test",
        inline_keyboard=((("Tham gia kênh", "tg://resolve?domain=test_chan"),),),
    )
    assert reply_tg.markup() == {
        "inline_keyboard": [[{"text": "Tham gia kênh", "url": "tg://resolve?domain=test_chan"}]]
    }

    # javascript: in inline keyboard rows is downgraded to callback_data
    reply_xss_row = BotReply(
        "test",
        inline_keyboard=((("XSS", "javascript:alert(1)"),),),
    )
    assert reply_xss_row.markup() == {
        "inline_keyboard": [[{"text": "XSS", "callback_data": "javascript:alert(1)"}]]
    }


def test_format_vouchers_detail_malformed_data_resilience():
    """Verify format_vouchers_detail does not crash with None, string percentages, or negative values."""
    malformed_vouchers = [
        None,
        "string entry",
        12345,
        {},
        {"code": None, "discount_percentage": None, "discount_value": None},
        {"code": "VOUCHER_STR", "discount_percentage": "30%", "discount_value": "50k"},
        {"code": "VOUCHER_NEG", "discount_percentage": -15, "discount_value": -50000, "min_spend": -1000},
        {"code": "VOUCHER_FLOAT", "discount_percentage": 20.5, "discount_value": 50000.0, "min_spend": 100000.0},
    ]

    detail = shop_voucher.format_vouchers_detail("987654321", malformed_vouchers)
    assert "MÃ GIẢM GIÁ TỪ SHOP (Shop ID: 987654321)" in detail
    assert "VOUCHER_STR" in detail
    assert "VOUCHER_NEG" in detail
    assert "VOUCHER_FLOAT" in detail
    assert "Giảm 20%" in detail


def test_format_vouchers_detail_100_vouchers_truncation():
    """Verify format_vouchers_detail bounds output to 15 items and <= 4000 chars for 100 vouchers."""
    hundred_vouchers = [
        {
            "code": f"CODE_{i:03d}",
            "discount_percentage": 10,
            "min_spend": 100_000,
        }
        for i in range(100)
    ]

    detail = shop_voucher.format_vouchers_detail("123456", hundred_vouchers)
    # Check max 15 entries are rendered
    assert "1. " in detail
    assert "15. " in detail
    assert "16. " not in detail
    # Total character count must respect Telegram limit <= 4000
    assert len(detail) <= 4000


def test_format_vouchers_detail_html_escaping():
    """Verify format_vouchers_detail escapes shop_id and code containing <, >, &."""
    malicious_shop_id = "<script>alert('shop')</script>&shop"
    malicious_vouchers = [
        {
            "code": "<img src=x onerror=alert('xss')>&code",
            "discount_percentage": 15,
            "discount_cap": 50000,
        }
    ]

    detail = shop_voucher.format_vouchers_detail(malicious_shop_id, malicious_vouchers)
    assert "<script>" not in detail
    assert "<img src=x" not in detail
    assert "&lt;script&gt;alert(&#x27;shop&#x27;)&lt;/script&gt;&amp;shop" in detail
    assert "&lt;img src=x onerror=alert(&#x27;xss&#x27;)&gt;&amp;code" in detail


def test_telegram_html_escaping_order_notices():
    """Verify order notices in messages.py escape <, >, & in dynamic fields."""
    dirty_order = "ORD<1>&2'\""

    new_notice = messages.order_new_notice(
        order=dirty_order,
        order_status="COMPLETED",
        cashback=10000,
        validation="APPROVED",
    )
    assert "<1>" not in new_notice
    assert "ORD&lt;1&gt;&amp;2&#x27;&quot;" in new_notice

    update_notice = messages.order_update_notice(
        order=dirty_order,
        statuses=["COMPLETED"],
        ineligible=False,
        approved=True,
        old_cashback=10000,
        new_cashback=20000,
    )
    assert "<1>" not in update_notice
    assert "ORD&lt;1&gt;&amp;2&#x27;&quot;" in update_notice

    detail_reply = messages.order_detail_reply({
        "order": dirty_order,
        "date": "2026-10-30 <date>",
        "order_status": "COMPLETED",
        "validation_status": "APPROVED",
        "settlement_status": "SETTLED",
        "entry_status": "available",
        "sub_id": "sub<&>",
        "cashback": 15000,
        "steps": [],
        "product": "Product <Name> & Co",
        "conversion_id": 456,
    })
    assert "<1>" not in detail_reply.text
    assert "<date>" not in detail_reply.text
    assert "Product &lt;Name&gt; &amp; Co" in detail_reply.text
    assert "sub&lt;&amp;&gt;" in detail_reply.text


def test_telegram_html_escaping_sale_relay():
    """Verify sale_relay escapes text with <, >, & and preserves newlines without <br>."""
    telegram = MagicMock()
    dirty_text = "Siêu sale < 99k & freeship > 0k!\nXem ngay:\nhttps://s.shopee.vn/an_redir"

    sale_relay.send_to_channel(telegram, -1001234567, dirty_text, None, [])
    telegram.send_message.assert_called_once()
    sent_text = telegram.send_message.call_args[0][1]
    assert "< 99k" not in sent_text
    assert "&lt; 99k &amp; freeship &gt; 0k!" in sent_text

    # Test subscriber queueing does not inject <br>
    repo = MagicMock()
    conn = MagicMock()
    repo.connect.return_value.__enter__.return_value = conn
    with patch("cashback_bot.sale_relay.enqueue_event") as mock_enqueue:
        sale_relay.enqueue_for_subscribers(repo, 888, dirty_text, [], [111])
        mock_enqueue.assert_called_once()
        html_msg = mock_enqueue.call_args.kwargs["message_html"]
        assert "<br>" not in html_msg
        assert "<br/>" not in html_msg
        assert "&lt; 99k &amp; freeship &gt; 0k!" in html_msg
        assert "Siêu sale &lt; 99k &amp; freeship &gt; 0k!\nXem ngay:" in html_msg
