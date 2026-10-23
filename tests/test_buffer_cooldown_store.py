"""PLAN-061: mốc 429 ghi ra file — restart và process khác vẫn thấy, không gửi request."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from app.features.buffer import client as buffer_client
from app.features.buffer import cluster_router
from app.features.buffer import cooldown_store
from app.features.buffer.client import BufferClient, BufferError, any_key_can_publish

KEY = "real-secret-key-abc123"


def _response(status: int, headers: dict | None = None, payload: dict | None = None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.json.return_value = payload or {"data": {"account": {"id": "1", "email": "a@b.c"}}}
    return resp


def _no_network(*args, **kwargs):
    raise AssertionError("Key đang cooldown mà vẫn gửi request Buffer")


def _lock_key_via_429(monkeypatch, retry_after: int = 142824) -> None:
    monkeypatch.setattr(buffer_client, "MIN_REQUEST_INTERVAL_SEC", 0)
    monkeypatch.setattr(
        buffer_client.requests,
        "post",
        lambda *a, **k: _response(429, {"Retry-After": str(retry_after)}),
    )
    with pytest.raises(BufferError):
        BufferClient(KEY).execute("query { account { id } }")


def test_restart_still_sees_cooldown_and_sends_nothing(monkeypatch):
    _lock_key_via_429(monkeypatch)
    buffer_client._KEY_GUARD.clear()  # giả lập restart: RAM mất
    monkeypatch.setattr(buffer_client.requests, "post", _no_network)

    fresh = BufferClient(KEY)
    assert fresh.cooldown_remaining() >= 142824 - 5
    assert not any_key_can_publish([KEY])
    with pytest.raises(BufferError) as exc:
        fresh.execute("query { account { id } }", purpose="publish")
    assert exc.value.status_code == 429


def test_other_process_write_is_seen(monkeypatch):
    """Process khác ghi file sau khi process này đã có row trong RAM."""
    monkeypatch.setattr(buffer_client.requests, "post", _no_network)
    client = BufferClient(KEY)
    assert client.cooldown_remaining() == 0

    cooldown_store.save(KEY, time.time() + 3600, 3600)
    assert client.cooldown_remaining() > 3500


def test_file_has_no_raw_key(monkeypatch):
    _lock_key_via_429(monkeypatch, retry_after=7200)
    text = cooldown_store.PATH.read_text(encoding="utf-8")
    assert KEY not in text
    data = json.loads(text)
    assert list(data) == [cooldown_store.key_id(KEY)]
    assert data[cooldown_store.key_id(KEY)]["retry_after"] == 7200


def test_save_keeps_later_deadline_and_prunes_expired():
    now = time.time()
    cooldown_store.save(KEY, now + 7200, 7200)
    cooldown_store.save(KEY, now + 60, 60)
    assert cooldown_store.until(KEY) == pytest.approx(now + 7200, abs=1)

    cooldown_store.save("old-key", now - 10, 1)
    cooldown_store.save("other-key", now + 30, 30)
    data = json.loads(cooldown_store.PATH.read_text(encoding="utf-8"))
    assert cooldown_store.key_id("old-key") not in data


def test_expired_cooldown_allows_one_call(monkeypatch):
    cooldown_store.save(KEY, time.time() - 1, 10)
    calls = []
    monkeypatch.setattr(buffer_client, "MIN_REQUEST_INTERVAL_SEC", 0)
    monkeypatch.setattr(
        buffer_client.requests,
        "post",
        lambda *a, **k: calls.append(1) or _response(200, payload={"data": {"account": {"id": "1"}}}),
    )
    BufferClient(KEY).execute("query { account { id } }")
    assert calls == [1]


def test_corrupt_file_is_ignored():
    cooldown_store.PATH.write_text("{not json", encoding="utf-8")
    assert cooldown_store.until(KEY) == 0.0
    cooldown_store.save(KEY, time.time() + 100, 100)
    assert cooldown_store.until(KEY) > 0


def _manager_with_key(monkeypatch):
    bm = MagicMock()
    bm.get_keys.return_value = [KEY]
    monkeypatch.setattr(cluster_router, "get_buffer_manager", lambda: bm)


def test_ping_key_skips_network_while_cooldown(monkeypatch):
    _manager_with_key(monkeypatch)
    cooldown_store.save(KEY, time.time() + 3600, 3600)
    monkeypatch.setattr(cluster_router.requests, "post", _no_network)

    result = cluster_router._handle_ping_key(account_index=1)
    assert result["status"] == "COOLDOWN"
    assert result["ok"] is False
    assert "Không gửi ping" in result["errorMessage"]


def test_ping_key_429_locks_shared_guard(monkeypatch):
    _manager_with_key(monkeypatch)
    monkeypatch.setattr(
        cluster_router.requests,
        "post",
        lambda *a, **k: _response(429, {"Retry-After": "80717"}),
    )
    result = cluster_router._handle_ping_key(account_index=1)
    assert result["status"] == "COOLDOWN"
    assert result["quota"]["cooldownSeconds"] == 80717

    monkeypatch.setattr(buffer_client.requests, "post", _no_network)
    buffer_client._KEY_GUARD.clear()
    assert BufferClient(KEY).cooldown_remaining() >= 80717 - 5
