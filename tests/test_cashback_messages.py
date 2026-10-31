"""Unit tests for messages.py hardening: button URLs and HTML escaping."""

from cashback_bot import messages
from cashback_bot.messages import BotReply, _is_safe_button_url


def test_is_safe_button_url_valid_schemes():
    assert _is_safe_button_url("https://shopee.vn/product/123") is True
    assert _is_safe_button_url("http://shopee.vn/shop/456") is True
    assert _is_safe_button_url("tg://resolve?domain=san_sale_bot") is True
    assert _is_safe_button_url("tg://user?id=123456") is True


def test_is_safe_button_url_rejects_dangerous_schemes():
    assert _is_safe_button_url("javascript:alert(document.cookie)") is False
    assert _is_safe_button_url("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==") is False
    assert _is_safe_button_url("file:///etc/passwd") is False
    assert _is_safe_button_url("ftp://ftp.example.com") is False
    assert _is_safe_button_url("vbscript:msgbox(1)") is False


def test_is_safe_button_url_rejects_whitespace_and_newlines():
    assert _is_safe_button_url("https://shopee.vn /test") is False
    assert _is_safe_button_url("https://shopee.vn\n/test") is False
    assert _is_safe_button_url("https://shopee.vn\r/test") is False
    assert _is_safe_button_url("https://shopee.vn\t/test") is False
    assert _is_safe_button_url("") is False
    assert _is_safe_button_url("   ") is False
    assert _is_safe_button_url(None) is False
    assert _is_safe_button_url(12345) is False


def test_bot_reply_markup_with_safe_and_unsafe_urls():
    # Safe button_url is preserved
    reply = BotReply("hello", button_url="https://shopee.vn/item")
    markup = reply.markup()
    assert markup == {"inline_keyboard": [[{"text": "🛒 Mua trên Shopee", "url": "https://shopee.vn/item"}]]}

    # Unsafe button_url (e.g. javascript:) is stripped
    reply_unsafe = BotReply("hello", button_url="javascript:alert(1)")
    assert reply_unsafe.markup() is None

    # Inline keyboard row with tg:// is classified as URL button (not callback_data)
    reply_tg = BotReply(
        "hello",
        inline_keyboard=((("Mở nhóm", "tg://resolve?domain=group"), ("Bấm đây", "u:action")),),
    )
    markup_tg = reply_tg.markup()
    assert markup_tg == {
        "inline_keyboard": [
            [
                {"text": "Mở nhóm", "url": "tg://resolve?domain=group"},
                {"text": "Bấm đây", "callback_data": "u:action"},
            ]
        ]
    }

    # Inline keyboard row with javascript is classified as callback_data (not URL)
    reply_js = BotReply(
        "hello",
        inline_keyboard=((("XSS test", "javascript:alert(1)"),),),
    )
    markup_js = reply_js.markup()
    assert markup_js == {
        "inline_keyboard": [
            [{"text": "XSS test", "callback_data": "javascript:alert(1)"}]
        ]
    }


def test_order_new_notice_escapes_dynamic_order():
    malicious_order = "<script>alert('XSS')</script>&test"
    notice = messages.order_new_notice(
        order=malicious_order,
        order_status="COMPLETED",
        cashback=50000,
        validation="APPROVED",
    )
    assert "<script>" not in notice
    assert "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;&amp;test" in notice
    assert "Mã đơn: &lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;&amp;test" in notice


def test_order_update_notice_escapes_dynamic_order():
    malicious_order = "ORD<123>&'\""
    notice = messages.order_update_notice(
        order=malicious_order,
        statuses=["COMPLETED"],
        ineligible=False,
        approved=True,
        old_cashback=10000,
        new_cashback=20000,
    )
    assert "<123>" not in notice
    assert "ORD&lt;123&gt;&amp;&#x27;&quot;" in notice
    assert "Mã đơn: ORD&lt;123&gt;&amp;&#x27;&quot;" in notice


def test_order_detail_reply_escapes_dynamic_order_and_date():
    row = {
        "order": "ORDER<999>&X",
        "date": "2026-10-30 <HACK>&",
        "order_status": "COMPLETED",
        "validation_status": "APPROVED",
        "settlement_status": "SETTLED",
        "entry_status": "available",
        "cashback": 25000,
        "product": "Áo thun cotton <100%>",
        "sub_id": "SUB<123>",
        "conversion_id": 456,
    }
    reply = messages.order_detail_reply(row)
    assert "<999>" not in reply.text
    assert "<HACK>" not in reply.text
    assert "ORDER&lt;999&gt;&amp;X" in reply.text
    assert "2026-10-30 &lt;HACK&gt;&amp;" in reply.text
