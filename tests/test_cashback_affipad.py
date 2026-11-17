"""PLAN-174: AffiPad trackingOnly — bridge short + rotate FB/IG; chặn farm cùng món liên tiếp."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from cashback_bot.affiliate import build_an_redir
from cashback_bot.affipad import AffiPadClient, is_meta_signed, pick_tracking_preset
from cashback_bot.messages import (
    FB_VOUCHER_HINT,
    FB_VOUCHER_LEAD,
    FB_VOUCHER_RULE,
    IG_VOUCHER_LEAD,
    SAME_ITEM_VOUCHER,
    _render_card,
    render_success,
    tip_reply,
)
from cashback_bot.shopee_shortener import shorten_if_an_redir, zalo_buy_url
from cashback_bot.zalo_render import META_BUY_LEAD, render
from tests.test_cashback_bot import NOW, FakeClient, payload, service


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "json": json})
        return self.response


def test_is_meta_signed():
    plain = build_an_redir("https://shopee.vn/product/9/8", "17300001", "Ab12Cd34")
    assert not is_meta_signed(plain)
    signed = plain + "&fb_content_id=x&encrypted_payload=y&sm_sig_id=z"
    assert is_meta_signed(signed)


def test_pick_tracking_preset_rotate_and_lock():
    assert pick_tracking_preset("fb_reels") == "fb_reels"
    assert pick_tracking_preset("ig") == "ig_reels"
    presets = {pick_tracking_preset("rotate", salt=s) for s in ("a", "b", "aa", "ab", "abc", "xyz")}
    assert presets == {"fb_reels", "ig_reels"}


def test_sign_tracking_only_success():
    an = build_an_redir("https://shopee.vn/product/9/8", "17300001", "Ab12Cd34")
    signed = an + "&fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=fb"
    client = AffiPadClient("key", "tool", session=_Session(_Resp(200, {"data": {"results": [{"link": signed}]}})))
    out = client.sign_tracking_only(an, preset="fb_reels")
    assert out == signed
    assert client._session.posts[0]["json"]["trackingOnly"] is True
    assert client._session.posts[0]["json"]["tracking"]["preset"] == "fb_reels"


def test_sign_tracking_only_http_error_returns_none():
    an = build_an_redir("https://shopee.vn/product/9/8", "17300001", "Ab12Cd34")
    client = AffiPadClient("key", "tool", session=_Session(_Resp(429, {"error": "RATE_LIMITED"})))
    assert client.sign_tracking_only(an) is None


def test_shortener_keeps_meta_signed_url(monkeypatch):
    an = build_an_redir("https://shopee.vn/product/9/8", "17300001", "Ab12Cd34")
    signed = an + "&fb_content_id=x&sm_sig_id=z"
    monkeypatch.setattr("cashback_bot.shopee_shortener.shorten_shopee_url", lambda *a, **k: "https://s.shopee.vn/STRIPPED")
    assert shorten_if_an_redir(signed, any_sub=True) == signed


def test_card_shows_fb_voucher_notes_when_meta_signed():
    plain = render_success("Áo", 210_000, 10_000, "https://s.shopee.vn/an_redir?x=1")
    assert FB_VOUCHER_LEAD not in plain.text and FB_VOUCHER_HINT not in plain.text
    assert plain.inline_keyboard[0][0][1] == "u:tip"
    signed = "https://s.shopee.vn/AAInOGcctN?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=fb"
    card = render_success("Áo", 210_000, 10_000, signed)
    assert FB_VOUCHER_LEAD in card.text and FB_VOUCHER_HINT in card.text
    assert "hết lượt" in card.text and "0h / 9h / 15h / 20h" in card.text
    tip_data = card.inline_keyboard[0][0][1]
    assert tip_data.endswith("f")
    assert FB_VOUCHER_RULE in tip_reply(tip_data).text
    ig = "https://s.shopee.vn/AAInOGcctN?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=ig"
    assert IG_VOUCHER_LEAD in render_success("Áo", 210_000, 10_000, ig).text


def test_service_uses_bridge_short_then_affipad(tmp_path, monkeypatch):
    """Owner-confirm path: s.shopee.vn/XXXX → AffiPad → s.shopee.vn/XXXX?Meta."""
    monkeypatch.setattr(
        "cashback_bot.service.shorten_shopee_url",
        lambda url, sub_id="", timeout=6.0: "https://s.shopee.vn/AAInOGcctN",
    )
    seen = []

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            assert url == "https://s.shopee.vn/AAInOGcctN"
            assert preset in {"fb_reels", "ig_reels"}
            seen.append(preset)
            channel = "ig" if preset == "ig_reels" else "fb"
            return url + f"?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type={channel}"

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t", affipad_tracking_preset="rotate")
    bot.affipad = FakePad()
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    url = reply.button_url or ""
    assert url.startswith("https://s.shopee.vn/AAInOGcctN")
    assert "an_redir" not in url
    assert is_meta_signed(url)
    assert "sm_sig_id" in parse_qs(urlparse(url).query)
    assert FB_VOUCHER_HINT in reply.text and "săn voucher" in reply.text
    assert seen and seen[0] in {"fb_reels", "ig_reels"}
    with bot.repo.connect() as conn:
        saved = conn.execute("SELECT affiliate_url FROM link_requests").fetchone()[0]
    assert saved == url


def test_service_locks_ig_preset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cashback_bot.service.shorten_shopee_url",
        lambda *a, **k: "https://s.shopee.vn/AAInOGcctN",
    )

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            assert preset == "ig_reels"
            return url + "?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=ig"

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t", affipad_tracking_preset="ig_reels")
    bot.affipad = FakePad()
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    assert IG_VOUCHER_LEAD in reply.text
    assert parse_qs(urlparse(reply.button_url).query)["channel_type"] == ["ig"]


def test_service_blocks_consecutive_same_item_when_affipad_on(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cashback_bot.service.shorten_shopee_url",
        lambda *a, **k: "https://s.shopee.vn/AAInOGcctN",
    )
    calls = {"n": 0}

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            calls["n"] += 1
            return url + "?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=fb"

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t", affipad_tracking_preset="fb_reels")
    bot.affipad = FakePad()
    first = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    second = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=2, now=NOW)
    assert SAME_ITEM_VOUCHER.split("\n")[0] in second.text
    assert second.button_url == first.button_url
    assert calls["n"] == 1
    with bot.repo.connect() as conn:
        created = conn.execute("SELECT COUNT(*) FROM link_requests WHERE link_status='created'").fetchone()[0]
        rejected = conn.execute(
            "SELECT COUNT(*) FROM link_requests WHERE reject_reason='same_item_voucher'"
        ).fetchone()[0]
    assert created == 1 and rejected == 1


def test_service_allows_same_item_after_other_item(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cashback_bot.service.shorten_shopee_url",
        lambda *a, **k: "https://s.shopee.vn/AAInOGcctN",
    )

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            return url + f"?fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=fb&n={preset}"

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t", affipad_tracking_preset="fb_reels")
    bot.affipad = FakePad()
    bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    bot.client = FakeClient(payload(itemId=88, shopId=9, productLink="https://shopee.vn/product/9/88"))
    bot.handle_text(111, "buyer", "https://shopee.vn/product/9/88", update_id=2, now=NOW)
    bot.client = FakeClient(payload())
    again = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=3, now=NOW)
    assert SAME_ITEM_VOUCHER.split("\n")[0] not in again.text
    assert is_meta_signed(again.button_url or "")


def test_service_falls_back_to_an_redir_sign_when_bridge_offline(tmp_path, monkeypatch):
    monkeypatch.setattr("cashback_bot.service.shorten_shopee_url", lambda *a, **k: None)

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            assert "an_redir" in url and preset in {"fb_reels", "ig_reels"}
            return url + "&fb_content_id=x&encrypted_payload=y&sm_sig_id=z&channel_type=fb"

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t", affipad_tracking_preset="fb_reels")
    bot.affipad = FakePad()
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    url = reply.button_url or ""
    assert is_meta_signed(url)
    assert "an_redir" in url


def test_service_falls_back_to_an_redir_when_affipad_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cashback_bot.service.shorten_shopee_url",
        lambda *a, **k: "https://s.shopee.vn/AAInOGcctN",
    )

    class FakePad:
        def sign_tracking_only(self, url, *, preset="fb_reels"):
            return None

    bot = service(tmp_path, FakeClient(payload()), affipad_fb_voucher_enabled=True,
                  affipad_api_key="k", affipad_tool_id="t")
    bot.affipad = FakePad()
    bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    with bot.repo.connect() as conn:
        saved = conn.execute("SELECT affiliate_url FROM link_requests").fetchone()[0]
    assert saved.startswith("https://s.shopee.vn/an_redir")
    assert not is_meta_signed(saved)


def test_service_skips_affipad_when_disabled(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    assert bot.affipad is None


def test_zalo_buy_url_shortens_meta(monkeypatch):
    meta = (
        "https://s.shopee.vn/AAInOGcctN?fb_content_id=x&encrypted_payload="
        + ("y" * 80)
        + "&sm_sig_id="
        + ("z" * 80)
        + "&channel_type=fb"
    )
    monkeypatch.setattr(
        "cashback_bot.shopee_shortener.public_shorten",
        lambda url, timeout=3.0: "https://is.gd/abc123",
    )
    assert zalo_buy_url(meta) == "https://is.gd/abc123"
    plain = "https://s.shopee.vn/an_redir?origin_link=https%3A%2F%2Fshopee.vn%2Fp&affiliate_id=1&sub_id=Ab12Cd34"
    monkeypatch.setattr(
        "cashback_bot.shopee_shortener.shorten_if_an_redir",
        lambda url, timeout=6.0, any_sub=False: "https://s.shopee.vn/shortPlain",
    )
    assert zalo_buy_url(plain) == "https://s.shopee.vn/shortPlain"


def test_zalo_render_uses_short_meta_link(monkeypatch):
    meta = (
        "https://s.shopee.vn/AAInOGcctN?fb_content_id=x&encrypted_payload="
        + ("y" * 80)
        + "&sm_sig_id=z&channel_type=ig"
    )
    monkeypatch.setattr("cashback_bot.zalo_render.zalo_buy_url", lambda url: "https://is.gd/zalo1")
    messages_out, _menu = render(_render_card("Áo", 210_000, 10_000, meta))
    text = messages_out[0].text
    assert META_BUY_LEAD in text
    assert "https://is.gd/zalo1" in text
    assert "encrypted_payload" not in text
    assert "sm_sig_id" not in text
