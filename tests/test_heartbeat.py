"""
Ping healthchecks.io (ADR-014).

Trọng tâm: **im lặng đúng cách**. Không URL thì không chạm mạng; mạng hỏng thì
không được ném lỗi ra ngoài — người gọi là lệnh backup và vòng lặp worker.
"""
from __future__ import annotations

import pytest

from app.core.observability import heartbeat


class _FakeResponse:
    def raise_for_status(self):
        pass


@pytest.fixture()
def http(monkeypatch):
    """Thay requests.get bằng bản ghi lại URL; trả về danh sách URL đã gọi."""
    calls: list[tuple[str, float]] = []

    def fake_get(url, timeout=None):
        calls.append((url, timeout))
        return _FakeResponse()

    monkeypatch.setattr(heartbeat.requests, "get", fake_get)
    return calls


def _set_url(monkeypatch, value: str):
    monkeypatch.setattr(heartbeat, "_read_url", lambda key, db=None: value)


def test_no_url_is_silent_and_never_touches_network(monkeypatch, http):
    _set_url(monkeypatch, "")

    assert heartbeat.ping("monitor.hc_url_backup") is False
    assert http == []


def test_pings_exact_url_when_configured(monkeypatch, http):
    _set_url(monkeypatch, "https://hc-ping.com/abc")

    assert heartbeat.ping("monitor.hc_url_backup") is True
    assert http == [("https://hc-ping.com/abc", heartbeat.TIMEOUT_SEC)]


def test_fail_appends_fail_suffix_without_double_slash(monkeypatch, http):
    _set_url(monkeypatch, "https://hc-ping.com/abc/")

    assert heartbeat.ping("monitor.hc_url_backup", fail=True) is True
    assert [u for u, _ in http] == ["https://hc-ping.com/abc/fail"]


def test_network_error_returns_false_and_does_not_raise(monkeypatch):
    _set_url(monkeypatch, "https://hc-ping.com/abc")

    def boom(url, timeout=None):
        raise ConnectionError("mat mang")

    monkeypatch.setattr(heartbeat.requests, "get", boom)

    assert heartbeat.ping("monitor.hc_url_maintenance") is False


def test_settings_read_error_returns_false_and_does_not_raise(monkeypatch, http):
    def boom(key, db=None):
        raise RuntimeError("db chua len")

    monkeypatch.setattr(heartbeat, "_read_url", boom)

    assert heartbeat.ping("monitor.hc_url_publisher", fail=True) is False
    assert http == []
