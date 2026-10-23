"""Vá rate-limit Buffer: cooldown gate + giãn request + retry bỏ first_comment."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.buffer.adapter import BufferAdapter
from app.features.buffer import client as buffer_client
from app.features.buffer.client import (
    MAX_429_COOLDOWN_SEC,
    MIN_429_COOLDOWN_SEC,
    BufferClient,
    BufferError,
    any_key_can_publish,
    soonest_cooldown_seconds,
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


def test_429_retry_after_kept_up_to_18h(monkeypatch):
    def fake_post(*args, **kwargs):
        return _response({}, status=429, headers={"Retry-After": str(15 * 3600)})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-keep")
    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }")
    assert exc.value.retry_after == 15 * 3600
    assert client.cooldown_remaining() >= 15 * 3600 - 2


def test_429_retry_after_40h_is_kept(monkeypatch):
    """Header 142824s ngày 21/10 là khóa thật. Trần cũ 18 giờ làm tool gọi lại khi còn khóa."""
    def fake_post(*args, **kwargs):
        return _response({}, status=429, headers={"Retry-After": "142824"})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-40h")
    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }")
    assert exc.value.retry_after == 142824
    assert client.cooldown_remaining() >= 142824 - 2


def test_429_retry_after_caps_at_72h(monkeypatch):
    def fake_post(*args, **kwargs):
        return _response({}, status=429, headers={"Retry-After": "400000"})

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    monkeypatch.setattr("app.features.buffer.client.MIN_REQUEST_INTERVAL_SEC", 0)
    client = BufferClient("k-cap")
    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }")
    assert MAX_429_COOLDOWN_SEC == 72 * 3600
    assert exc.value.retry_after == MAX_429_COOLDOWN_SEC
    assert client.cooldown_remaining() <= MAX_429_COOLDOWN_SEC


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


def test_publish_gate_waits_for_soonest_cooldown():
    locked = BufferClient("k-locked")
    open_key = BufferClient("k-open")
    locked.mark_rate_limited(3600)
    assert any_key_can_publish(["k-locked", "k-open"]) is True
    assert soonest_cooldown_seconds(["k-locked", "k-open"]) == 0
    open_key.mark_rate_limited(900)
    assert any_key_can_publish(["k-locked", "k-open"]) is False
    assert 900 <= soonest_cooldown_seconds(["k-locked", "k-open"]) <= 901


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


# --- PLAN-068: đọc suất 24 giờ từ header RateLimit ----------------------------------

_THREE_WINDOWS = (
    '"100-in-15min";r=98;t=897, "250-in-1day";r=60;t=20282, "3000-in-30days";r=2500;t=696980'
)


def test_ratelimit_header_uses_tightest_window(monkeypatch):
    """x-ratelimit 2500/3000 là cửa sổ 30 ngày; cửa sổ ngày còn 60/250 mới là chỗ sắp cạn."""
    monkeypatch.setattr(
        "app.features.buffer.client.requests.post",
        lambda *a, **k: _response(
            {"data": {"account": {"id": "1"}}},
            headers={"RateLimit": _THREE_WINDOWS, "x-ratelimit-limit": "3000", "x-ratelimit-remaining": "2500"},
        ),
    )
    client = BufferClient("k-windows")
    client.execute("query { account { id } }")
    row = buffer_client._KEY_GUARD["k-windows"]
    assert (row["limit"], row["remaining"]) == (250, 60)
    assert "60/250" in (client.reserve_block_reason() or "")


def test_ratelimit_header_with_spaces_lowercase_name():
    windows = buffer_client._ratelimit_windows({"ratelimit": '"100-in-15min"; r=0; t=753'})
    assert windows == [(100, 0, 753, "100-in-15min")]


def test_exhausted_window_on_success_rests_key_without_429(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return _response(
            {"data": {"account": {"id": "1"}}},
            headers={"RateLimit": '"100-in-15min";r=40;t=425, "250-in-1day";r=0;t=20282'},
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("k-empty-day")
    client.execute("query { account { id } }")  # request này thành công
    assert client.cooldown_remaining() >= 20282 - 2

    with pytest.raises(BufferError) as exc:
        client.execute("query { account { id } }", purpose="publish")
    assert exc.value.status_code == 429
    assert calls == [1]


def test_without_ratelimit_header_falls_back_to_x_ratelimit(monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.client.requests.post",
        lambda *a, **k: _response(
            {"data": {"account": {"id": "1"}}},
            headers={"x-ratelimit-limit": "250", "x-ratelimit-remaining": "200"},
        ),
    )
    client = BufferClient("k-legacy")
    client.execute("query { account { id } }")
    row = buffer_client._KEY_GUARD["k-legacy"]
    assert (row["limit"], row["remaining"]) == (250, 200)
    assert client.cooldown_remaining() == 0


def test_status_sync_runs_at_most_hourly():
    from app.features.buffer import sync_posted

    assert sync_posted.INTERVAL_SEC == 60 * 60


def test_every_sent_request_logs_one_req_line_without_raw_key(monkeypatch, caplog):
    """PLAN-072: mỗi request một dòng [Buffer][req], có cửa sổ còn lại, không có key thô."""
    import logging

    from app.features.buffer import client as client_mod

    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"RateLimit": '"100-in-15min";r=98;t=897, "250-in-1day";r=142;t=86397'}
    resp.json.return_value = {"data": {"account": {"id": "1"}}}
    monkeypatch.setattr(client_mod.requests, "post", lambda *a, **k: resp)
    key = "secretkey_ABCDEFGH_1234"
    c = client_mod.BufferClient(key)

    with caplog.at_level(logging.INFO, logger="app.features.buffer.client"):
        c.execute("query GetOrganizations { account { id } }")
        c.execute("{ account { id } }", purpose="publish")

    lines = [r.getMessage() for r in caplog.records if "[Buffer][req]" in r.getMessage()]
    assert len(lines) == 2
    assert "#1 GetOrganizations purpose=background HTTP 200" in lines[0]
    assert "250-in-1day r=142" in lines[0]
    assert "#2 account purpose=publish" in lines[1]
    assert all(key not in line and "secr...1234" in line for line in lines)


def test_held_request_is_not_logged_as_sent(monkeypatch, caplog):
    import logging

    from app.features.buffer import client as client_mod

    sent = []
    monkeypatch.setattr(client_mod.requests, "post", lambda *a, **k: sent.append(1))
    c = client_mod.BufferClient("key_held_12345678")
    with client_mod._GUARD_LOCK:
        row = client_mod._guard_row("key_held_12345678")
        row["limit"], row["remaining"] = 250, 10
    with caplog.at_level(logging.INFO, logger="app.features.buffer.client"):
        with pytest.raises(client_mod.BufferError):
            c.execute("query X { account { id } }")
    assert not sent
    assert not [r for r in caplog.records if "[Buffer][req]" in r.getMessage()]
