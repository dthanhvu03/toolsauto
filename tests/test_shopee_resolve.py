"""PLAN-177 Phase 1.1: resolve short Shopee ≤3 hop + SSRF."""

from __future__ import annotations

import ipaddress
from types import SimpleNamespace

import pytest

from cashback_bot.shopee_resolve import (
    MAX_HOPS,
    ResolveError,
    from_target,
    is_safe_hop_url,
    parse_product_ids,
    resolve_to_product,
)
from cashback_bot.shopee_url import ShopeeTarget, parse_shopee_target


def test_max_hops_matches_project_ssrf():
    assert MAX_HOPS == 3


def test_parse_product_and_opaanlp():
    assert parse_product_ids("https://shopee.vn/product/9/8") == (9, 8)
    assert parse_product_ids("https://shopee.vn/Ao-i.9.8") == (9, 8)
    assert parse_product_ids("https://www.shopee.vn/opaanlp/11/22") == (11, 22)
    assert parse_product_ids("https://s.shopee.vn/AbCd") is None


def test_from_target_canonical():
    target = parse_shopee_target("https://shopee.vn/product/9/8")
    resolved = from_target(target)
    assert resolved is not None
    assert resolved.product_url == "https://shopee.vn/product/9/8"
    assert resolved.hops == 0


def test_from_target_short_needs_http():
    target = ShopeeTarget("https://s.shopee.vn/AbCdEf", None, None, "https://s.shopee.vn/AbCdEf")
    assert from_target(target) is None


def test_resolve_follows_redirect(monkeypatch):
    monkeypatch.setattr(
        "cashback_bot.shopee_resolve._public_host",
        lambda host: True,
    )
    hops = {"https://s.shopee.vn/AbCd": "https://shopee.vn/product/9/8"}

    def head(url, timeout):
        assert timeout > 0
        loc = hops.get(url)
        if loc:
            return SimpleNamespace(status_code=302, headers={"Location": loc})
        return SimpleNamespace(status_code=200, headers={})

    resolved = resolve_to_product("https://s.shopee.vn/AbCd", head=head)
    assert resolved.shop_id == 9 and resolved.item_id == 8
    assert resolved.hops == 1


def test_resolve_stops_at_3_hops(monkeypatch):
    monkeypatch.setattr("cashback_bot.shopee_resolve._public_host", lambda host: True)
    chain = {
        "https://s.shopee.vn/a": "https://s.shopee.vn/b",
        "https://s.shopee.vn/b": "https://s.shopee.vn/c",
        "https://s.shopee.vn/c": "https://s.shopee.vn/d",
        "https://s.shopee.vn/d": "https://shopee.vn/product/1/2",
    }

    def head(url, timeout):
        return SimpleNamespace(status_code=302, headers={"Location": chain[url]})

    with pytest.raises(ResolveError) as caught:
        resolve_to_product("https://s.shopee.vn/a", head=head)
    assert caught.value.code == "max_hops"


def test_ssrf_blocks_private(monkeypatch):
    def fake_getaddrinfo(host, _port):
        return [(0, 0, 0, 0, ("127.0.0.1", 0))]

    monkeypatch.setattr("cashback_bot.shopee_resolve.socket.getaddrinfo", fake_getaddrinfo)
    assert is_safe_hop_url("https://s.shopee.vn/x", allow_short=True) is False


def test_ssrf_blocks_ipv4_mapped(monkeypatch):
    def fake_getaddrinfo(host, _port):
        return [(0, 0, 0, 0, ("::ffff:10.0.0.1", 0))]

    monkeypatch.setattr("cashback_bot.shopee_resolve.socket.getaddrinfo", fake_getaddrinfo)
    assert is_safe_hop_url("https://shopee.vn/product/1/2", allow_short=False) is False
    # sanity: mapped helper recognises private
    assert ipaddress.ip_address("::ffff:10.0.0.1").ipv4_mapped.is_private
