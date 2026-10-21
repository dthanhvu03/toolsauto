"""Vá rate-limit Buffer: cooldown gate + giãn request + retry bỏ first_comment."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.buffer.adapter import BufferAdapter
from app.features.buffer import client as buffer_client
from app.features.buffer.client import (
    MIN_429_COOLDOWN_SEC,
    BufferClient,
    BufferError,
)


@pytest.fixture(autouse=True)
def _clear_buffer_key_guard():
    buffer_client._KEY_GUARD.clear()
    yield
    buffer_client._KEY_GUARD.clear()


def _response(payload: dict, status: int = 200, headers: dict | None = None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.json.return_value = payload
    return resp


def test_execute_blocks_during_local_cooldown_without_http(monkeypatch):
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return _response({"data": {"account": {"id": "1"}}})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-test")
    client.mark_rate_limited(1200)
    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }")
    assert exc.value.status_code == 429
    assert calls["n"] == 0
    assert client.cooldown_remaining() > 0


def test_429_response_sets_cooldown_floor(monkeypatch):
    def fake_post(*args, **kwargs):
        return _response({}, status=429, headers={"Retry-After": "30"})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-test")
    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }")
    assert exc.value.status_code == 429
    assert exc.value.retry_after >= MIN_429_COOLDOWN_SEC
    assert client.cooldown_remaining() >= MIN_429_COOLDOWN_SEC - 2


def test_min_interval_between_calls(monkeypatch):
    times = []

    def fake_post(*args, **kwargs):
        times.append(time.time())
        return _response({"data": {"account": {"id": "1"}}})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    # Giữ interval thật nhỏ để test nhanh nhưng > 0
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0.15)
    client = BufferClient("k-test")
    client.execute("query { account { id } }")
    client.execute("query { account { id } }")
    assert len(times) == 2
    assert times[1] - times[0] >= 0.14


def test_background_stops_when_post_reserve_reached(monkeypatch):
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return _response(
            {"data": {"createPost": {"post": {"id": "p", "text": "hi", "dueAt": None}}}},
            headers={"x-ratelimit-limit": "100", "x-ratelimit-remaining": "70"},
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-reserve")
    client.execute("mutation CreatePost { createPost { id } }", purpose="publish")
    with pytest.raises(BufferError) as exc:
        client.execute("query Channels { channels { id } }")
    assert "đăng bài" in str(exc.value)
    assert calls["n"] == 1
    client.execute("mutation CreatePost { createPost { id } }", purpose="publish")
    assert calls["n"] == 2


def test_cooldown_is_shared_across_clients(monkeypatch):
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return _response({"data": {"account": {"id": "1"}}})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    BufferClient("k-shared").mark_rate_limited(1200)
    with pytest.raises(BufferError):
        BufferClient("k-shared").execute("query { account { id } }")
    assert calls["n"] == 0


def test_adapter_retries_without_first_comment_on_paid_plan(monkeypatch):
    calls = {"n": 0, "with_fc": 0}

    class FakeClient:
        def infer_channel_service(self, channel_id):
            return "facebook"

        def create_post(self, **kwargs):
            calls["n"] += 1
            if kwargs.get("first_comment"):
                calls["with_fc"] += 1
                raise BufferError(
                    "Invalid post: First comment requires a paid plan.",
                    status_code=422,
                )
            return {"id": "post_ok", "dueAt": None}

    monkeypatch.setattr(
        "app.features.buffer.first_comment.get_or_create_first_comment",
        lambda caption, topic="": "comment demo",
    )
    monkeypatch.setattr(
        "app.features.buffer.adapter.public_media_url",
        lambda job: "https://cdn.example/a.mp4",
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    job = SimpleNamespace(
        id=1080,
        job_type="REUP",
        target_page="chan_hoa",
        caption="hello",
        auto_comment_text="",
        ai_style="",
        schedule_ts=0,
        service="facebook",
    )
    result = BufferAdapter(client=FakeClient()).publish(job)
    assert result.ok is True
    assert result.external_post_id == "post_ok"
    assert calls["n"] == 2
    assert calls["with_fc"] == 1
