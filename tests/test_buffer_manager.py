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

    client_a.cooldown_remaining.return_value = 1200
    assert mgr.get_client_for_channel("unknown_chan") is None
    client_a.cooldown_remaining.side_effect = TypeError("not a duration")

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


# --- PLAN-067: bảng kênh lưu file, post_statuses gom theo key ---------------------------

from app.features.buffer import manager as manager_mod  # noqa: E402


def _fake_client(key: str, channels: list[str], *, held: bool = False, cooldown: float = 0):
    c = MagicMock()
    c._key = key
    c.allows.return_value = not held
    c.cooldown_remaining.return_value = cooldown
    c.organizations.return_value = [{"id": f"org_{key}"}]
    c.channels.return_value = [{"id": cid, "name": cid} for cid in channels]
    c.post_statuses.side_effect = lambda ids: {pid: "sent" for pid in ids}
    return c


class _Factory:
    """get_clients() thật tạo client mới mỗi lần — giả lập đúng kiểu đó."""

    def __init__(self, specs):
        self.specs = specs
        self.made: list[MagicMock] = []

    def __call__(self):
        out = [_fake_client(*s[:2], **(s[2] if len(s) > 2 else {})) for s in self.specs]
        self.made.extend(out)
        return out


def test_post_statuses_one_request_per_key_even_with_fresh_client_objects(monkeypatch):
    factory = _Factory([("key_a", ["chan_a"]), ("key_b", ["chan_b"])])
    mgr = BufferManager()
    monkeypatch.setattr(mgr, "get_clients", factory)
    monkeypatch.setattr(
        mgr,
        "get_client_for_post",
        lambda pid, db=None: factory()[0 if pid.startswith("a") else 1],
    )

    ids = [f"a{i}" for i in range(12)] + ["b1", "b2"]
    out = mgr.post_statuses(ids)

    assert set(out) == set(ids)
    calls = [c for c in factory.made if c.post_statuses.called]
    assert len(calls) == 2
    assert sorted(len(c.post_statuses.call_args.args[0]) for c in calls) == [2, 12]


def test_post_statuses_skips_posts_without_open_key(monkeypatch):
    mgr = BufferManager(clients=[_fake_client("key_a", []), _fake_client("key_b", [])])
    monkeypatch.setattr(mgr, "get_client_for_post", lambda pid, db=None: None)
    assert mgr.post_statuses(["x", "y"]) == {}


def test_held_key_without_saved_table_bootstraps_once_then_reads_file():
    a = _fake_client("key_a", ["chan_a"])
    b = _fake_client("key_b", ["chan_b"], held=True)
    mgr = BufferManager(clients=[a, b])

    assert mgr.get_client_for_channel("chan_b") is b
    b.organizations.assert_called_once_with(purpose="channel_bootstrap")
    b.channels.assert_called_once_with("org_key_b", purpose="channel_bootstrap")
    a.organizations.assert_called_once_with()

    # Restart: manager + client mới, file còn → không gọi Buffer.
    a2 = _fake_client("key_a", ["chan_a"])
    b2 = _fake_client("key_b", ["chan_b"], held=True)
    mgr2 = BufferManager(clients=[a2, b2])
    assert mgr2.get_client_for_channel("chan_b") is b2
    assert mgr2.get_client_for_channel("chan_a") is a2
    a2.organizations.assert_not_called()
    b2.organizations.assert_not_called()


def test_saved_file_has_no_raw_key():
    c = _fake_client("secret-key-xyz", ["chan_a"])
    c.organizations.return_value = [{"id": "org_1"}]
    mgr = BufferManager(clients=[c])
    mgr.get_channels_map()
    text = manager_mod.CHANNELS_FILE.read_text(encoding="utf-8")
    assert "secret-key-xyz" not in text
    assert "chan_a" in text


def test_cooldown_key_uses_stale_table_without_calling(monkeypatch):
    BufferManager(clients=[_fake_client("key_a", ["chan_a"]), _fake_client("key_b", ["chan_b"])]).get_channels_map()
    data = manager_mod._read_channels_file()
    for entry in data.values():
        entry["ts"] = 0  # cũ hơn 6 giờ
    manager_mod._write_channels_file(data)

    a = _fake_client("key_a", ["chan_a"])
    b = _fake_client("key_b", ["chan_b"], held=True, cooldown=3600)
    mgr = BufferManager(clients=[a, b])
    assert mgr.get_client_for_channel("chan_b") is b
    b.organizations.assert_not_called()
    a.organizations.assert_called_once_with()  # key mở, bảng cũ → quét lại bình thường


def test_cooldown_key_without_table_is_not_scanned():
    b = _fake_client("key_b", ["chan_b"], held=True, cooldown=3600)
    mgr = BufferManager(clients=[_fake_client("key_a", ["chan_a"]), b])
    mgr.get_channels_map()
    b.organizations.assert_not_called()


def test_unknown_channel_rescan_at_most_every_30_min(monkeypatch):
    a = _fake_client("key_a", ["chan_a"])
    mgr = BufferManager(clients=[a])
    mgr.get_channels_map()
    assert a.organizations.call_count == 1

    clock = [manager_mod.time.time() + manager_mod.CHANNEL_UNKNOWN_RESCAN_SEC + 5]
    monkeypatch.setattr(manager_mod.time, "time", lambda: clock[0])
    mgr._channel_cache_ts = clock[0]  # bảng RAM còn mới, chỉ đường kênh lạ chạy
    mgr.get_client_for_channel("chan_new")
    mgr.get_client_for_channel("chan_new_2")
    assert a.organizations.call_count == 2


def test_unknown_channel_not_sent_to_primary_while_a_key_has_no_table():
    """19:38 23/10: key 2, 3 khóa chưa có bảng → kênh của chúng từng đổ về key 1, đốt suất key 1."""
    a = _fake_client("key_a", ["chan_a"])
    b = _fake_client("key_b", ["chan_b"], held=True, cooldown=3600)
    mgr = BufferManager(clients=[a, b])
    assert mgr.get_client_for_channel("chan_a") is a
    assert mgr.get_client_for_channel("chan_b") is None
    assert mgr.get_client_for_channel("chan_x") is None
    a.post_statuses.assert_not_called()
