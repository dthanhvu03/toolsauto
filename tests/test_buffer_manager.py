"""Unit tests for BufferManager (Multi-Buffer API Keys & routing)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferError
from app.features.buffer.manager import (
    BufferManager,
    mask_key,
    parse_api_keys,
)


def test_mask_key():
    assert mask_key("") == "<empty>"
    assert mask_key("12345") == "...2345"
    assert mask_key("1/abcdef1234567890") == "1/ab...7890"


def test_parse_api_keys():
    # Comma-separated string
    raw_str = "key1, key2 , key3"
    assert parse_api_keys(raw_str) == ["key1", "key2", "key3"]

    # Newline & semicolon
    raw_multiline = "key1\nkey2;key3\r\nkey1"
    assert parse_api_keys(raw_multiline) == ["key1", "key2", "key3"]

    # JSON array
    raw_json = '["keyA", "keyB", "keyA"]'
    assert parse_api_keys(raw_json) == ["keyA", "keyB"]

    # JSON dict
    raw_dict = '{"acc1": "k1", "acc2": "k2"}'
    assert parse_api_keys(raw_dict) == ["k1", "k2"]

    # Python list of dicts
    list_dicts = [{"api_key": "x1"}, {"api_key": "x2"}]
    assert parse_api_keys(list_dicts) == ["x1", "x2"]


def test_manager_has_keys_and_primary_client():
    mgr_empty = BufferManager(keys=[])
    assert mgr_empty.has_keys() is False
    with pytest.raises(BufferError):
        mgr_empty.get_primary_client()

    mgr = BufferManager(keys=["key_one", "key_two"])
    assert mgr.has_keys() is True
    clients = mgr.get_clients()
    assert len(clients) == 2
    assert mgr.get_primary_client()._key == "key_one"


def test_channel_routing_between_multiple_accounts():
    client_a = MagicMock()
    client_a._key = "key_a"
    client_a.organizations.return_value = [{"id": "org_a"}]
    client_a.channels.return_value = [
        {"id": "chan_a1", "name": "Page A1", "service": "facebook"},
        {"id": "chan_a2", "name": "Page A2", "service": "facebook"},
    ]

    client_b = MagicMock()
    client_b._key = "key_b"
    client_b.organizations.return_value = [{"id": "org_b"}]
    client_b.channels.return_value = [
        {"id": "chan_b1", "name": "Page B1", "service": "facebook"},
        {"id": "chan_b2", "name": "Page B2", "service": "facebook"},
    ]

    mgr = BufferManager(clients=[client_a, client_b])

    # Route to Account A
    res_a = mgr.get_client_for_channel("chan_a1")
    assert res_a == client_a

    # Route to Account B
    res_b = mgr.get_client_for_channel("chan_b2")
    assert res_b == client_b

    # Unknown channel falls back to primary client (client_a)
    assert mgr.get_client_for_channel("unknown_chan") == client_a

    # Test list_all_channels
    all_channels = mgr.list_all_channels()
    assert len(all_channels) == 4
    names = [ch["name"] for ch in all_channels]
    assert names == ["Page A1", "Page A2", "Page B1", "Page B2"]


def test_quota_overview_aggregation():
    client_a = MagicMock()
    client_a._key = "key_alpha"
    client_a.quota_overview.return_value = (
        "<b>Hạn đăng A</b>\nUyển Nhi còn 5",
        [{"id": "p_a1", "label": "Post A1"}],
    )

    client_b = MagicMock()
    client_b._key = "key_beta"
    client_b.quota_overview.return_value = (
        "<b>Hạn đăng B</b>\nSống Nhẹ còn 10",
        [{"id": "p_b1", "label": "Post B1"}],
    )

    mgr = BufferManager(clients=[client_a, client_b])
    text, items = mgr.quota_overview()

    assert "Tài khoản #1" in text
    assert "Hạn đăng A" in text
    assert "Tài khoản #2" in text
    assert "Hạn đăng B" in text
    assert len(items) == 2
    assert [it["id"] for it in items] == ["p_a1", "p_b1"]


def test_post_statuses_batch_grouped_by_account():
    client_a = MagicMock()
    client_a._key = "key_a"
    client_a.post_statuses.return_value = {"post_a1": "sent", "post_a2": "scheduled"}

    client_b = MagicMock()
    client_b._key = "key_b"
    client_b.post_statuses.return_value = {"post_b1": "error"}

    mgr = BufferManager(clients=[client_a, client_b])

    # Map post_ids to clients
    mgr.get_client_for_post = MagicMock(
        side_effect=lambda pid, db=None: client_a if "a" in pid else client_b
    )

    statuses = mgr.post_statuses(["post_a1", "post_a2", "post_b1"])
    assert statuses == {
        "post_a1": "sent",
        "post_a2": "scheduled",
        "post_b1": "error",
    }
    client_a.post_statuses.assert_called_once_with(["post_a1", "post_a2"])
    client_b.post_statuses.assert_called_once_with(["post_b1"])


def test_buffer_adapter_routes_with_manager(monkeypatch):
    client_target = MagicMock()
    client_target.create_post.return_value = {"id": "new_post_999", "dueAt": "2026-10-17T08:00:00Z"}

    mgr = BufferManager(clients=[client_target])
    monkeypatch.setattr("app.features.buffer.manager.get_buffer_manager", lambda: mgr)

    adapter = BufferAdapter()  # no explicit client injected
    job = MagicMock()
    job.id = 100
    job.target_page = "target_channel_id"
    job.caption = "Test caption"
    job.schedule_ts = 0
    job.media_path = None
    job.processed_media_path = None

    monkeypatch.setattr("app.features.buffer.adapter.public_media_url", lambda j: None)

    res = adapter.publish(job)
    assert res.ok is True
    assert res.external_post_id == "new_post_999"
    client_target.create_post.assert_called_once()
