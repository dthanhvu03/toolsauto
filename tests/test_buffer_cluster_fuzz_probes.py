"""Empirical Challenger M1.R2.1 Extended Fuzz & Stress Probes.
Tests edge-case inputs, malformed types, extreme floats/ints, unicode headers,
and corrupt in-memory states against all Buffer telemetry endpoints.
Used to identify and verify 0 unhandled 500 exceptions across all probes.
"""
from __future__ import annotations

import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import Base
from app.main import app
import app.features.buffer.cluster_router as cluster_router_mod
from app.features.buffer.manager import get_buffer_manager, reset_buffer_manager


@pytest.fixture
def isolated_env():
    """File-based SQLite database in WAL mode and clean in-memory state."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}?timeout=30", echo=False)
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    session_factory = sessionmaker(bind=engine)

    orig_session_local = cluster_router_mod.SessionLocal
    cluster_router_mod.SessionLocal = session_factory

    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    cluster_router_mod.SessionLocal = orig_session_local
    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()
    engine.dispose()


# ============================================================================
# Section 1: POST /api/buffer/ping-key Fuzzing
# ============================================================================

@pytest.mark.parametrize(
    "payload",
    [
        {"account_index": None},
        {"account_index": 1.0},
        {"account_index": 1.99},
        {"account_index": -0.0},
        {"account_index": 0},
        {"account_index": -1},
        {"account_index": 10**50},
        {"account_index": -10**50},
        {"account_index": "1"},
        {"account_index": "99999"},
        {"account_index": ""},
        {"account_index": " "},
        {"account_index": "1e2"},
        {"account_index": True},
        {"account_index": False},
        {"account_index": []},
        {"account_index": {}},
        {},
    ],
)
def test_ping_key_post_fuzz_indices(isolated_env, payload):
    """POST /api/buffer/ping-key with exotic account_index representations must not crash with 500."""
    res = isolated_env.post("/api/buffer/ping-key", json=payload)
    assert res.status_code != 500, f"500 crash on payload {payload}: {res.text}"
    assert res.status_code in (200, 400, 422)


@pytest.mark.parametrize(
    "bad_key",
    [
        None,
        "",
        "   \t\n   ",
        "\x00\x01\x02",
        "🔑🚀⚡",
        "khóa_bảo_mật",
        "a" * 5000,
        "' OR '1'='1; --",
        "<script>alert(1)</script>",
        0,
        123456789,
        3.14159,
        True,
        False,
        [],
        [1, 2, "abc"],
        {"nested": "dict"},
        {"nested": {"deep": [1, 2, 3]}},
    ],
)
def test_ping_key_post_fuzz_keys(isolated_env, bad_key):
    """POST /api/buffer/ping-key with exotic keys must return 200, 400, or 422, never unhandled 500."""
    res = isolated_env.post("/api/buffer/ping-key", json={"key": bad_key})
    assert res.status_code != 500, f"500 crash on key {bad_key!r}: {res.text}"
    assert res.status_code in (200, 400, 422)


# ============================================================================
# Section 2: GET /api/buffer/ping-key Fuzzing
# ============================================================================

@pytest.mark.parametrize(
    "q",
    [
        "",
        "?account_index=",
        "?account_index=1",
        "?account_index=0",
        "?account_index=-1",
        "?account_index=99999999999999999999999999999999999999999999",
        "?account_index=-99999999999999999999999999999999999999999999",
        "?account_index=1e1000",
        "?account_index=NaN",
        "?account_index=Infinity",
        "?account_index=null",
        "?account_index=True",
        "?account_index=abc",
        "?account_index=1&key=somekey",
        "?key=",
        "?key=   ",
        "?key=🔑🚀",
        "?key=khóa_bảo_mật",
        "?key=" + "X" * 1000,
        "?key=%00%01%02",
        "?key=' OR 1=1 --",
    ],
)
def test_ping_key_get_fuzz_params(isolated_env, q):
    """GET /api/buffer/ping-key query parameters must never trigger unhandled 500."""
    res = isolated_env.get(f"/api/buffer/ping-key{q}")
    assert res.status_code != 500, f"500 crash on query '{q}': {res.text}"
    assert res.status_code in (200, 400, 422)


# ============================================================================
# Section 3: Raw Body Payloads
# ============================================================================

@pytest.mark.parametrize(
    "raw_body",
    [
        b"",
        b"{}",
        b"null",
        b"[]",
        b"\"just a string\"",
        b"12345",
        b"true",
        b"{\"account_index\": 1e1000}",
        b"{\"account_index\": -1e1000}",
        b"{\"account_index\": NaN}",
        b"{\"account_index\": Infinity}",
        b"{\"account_index\": 9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999}",
        b"{\"key\": null, \"account_index\": null}",
        b"{\"key\": \x00}",
        b"malformed json {{{",
    ],
)
def test_ping_key_raw_body_fuzz(isolated_env, raw_body):
    """POST /api/buffer/ping-key with raw content bodies must not crash with 500."""
    res = isolated_env.post(
        "/api/buffer/ping-key",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code != 500, f"500 crash on raw body {raw_body[:50]}: {res.text}"
    assert res.status_code in (200, 400, 422)


# ============================================================================
# Section 4: GET /api/buffer/cluster-status In-Memory Poisoning
# ============================================================================

@pytest.mark.parametrize(
    "poison",
    [
        {},
        {"status": "ACTIVE"},
        {"status": "UNKNOWN_STATUS", "cooldown_until": -100},
        {"status": "COOLDOWN", "cooldown_until": float("inf"), "last_ping": 100},
        {"status": "COOLDOWN", "cooldown_until": float("-inf"), "last_ping": 100},
        {"status": "COOLDOWN", "cooldown_until": float("nan"), "last_ping": 100},
        {"status": "COOLDOWN", "cooldown_until": "invalid_ts", "last_ping": "now"},
        {"status": "COOLDOWN", "cooldown_until": None, "last_ping": None},
        {"status": "ACTIVE", "cooldown_until": 0, "quota": "not a dict"},
        {"status": "ACTIVE", "cooldown_until": 0, "quota": None},
        {"status": "ACTIVE", "cooldown_until": 0, "quota": {"dailyLimit": "inf", "dailyRemaining": -999}},
    ],
)
def test_cluster_status_resilience_to_poisoned_telemetry(isolated_env, poison):
    """Corrupt _KEY_TELEMETRY with edge-case types; cluster-status must not crash with 500."""
    bm = get_buffer_manager()
    keys = bm.get_keys()
    target_key = keys[0] if keys else "test_key"

    cluster_router_mod._KEY_TELEMETRY[target_key] = poison
    res = isolated_env.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"500 crash on poisoned telemetry state ({poison}): {res.text}"
    data = res.json()
    assert data.get("ok") is True


@pytest.mark.parametrize(
    "poison_cache",
    [
        "not a list",
        None,
        123,
        {"a": "b"},
        [None, 123, "string"],
        [{"id": 12345}],
        [{"id": "c1", "name": None, "service": None, "pendingCount": "invalid"}],
    ],
)
def test_cluster_status_resilience_to_poisoned_channel_cache(isolated_env, poison_cache):
    """Corrupt _KEY_CHANNELS_CACHE; cluster-status must not crash with 500."""
    bm = get_buffer_manager()
    keys = bm.get_keys()
    target_key = keys[0] if keys else "test_key"

    cluster_router_mod._KEY_CHANNELS_CACHE[target_key] = poison_cache
    cluster_router_mod._KEY_CHANNELS_TS[target_key] = 9999999999
    res = isolated_env.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"500 crash on poisoned channel cache ({poison_cache}): {res.text}"
    data = res.json()
    assert data.get("ok") is True


# ============================================================================
# Section 5: GET /api/buffer/dispatch-feed Fuzzing
# ============================================================================

@pytest.mark.parametrize(
    "q",
    [
        "",
        "?limit=0",
        "?limit=-1",
        "?limit=-999999",
        "?limit=1000000",
        "?limit=99999999999999999999999999999999999999999999",
        "?limit=abc",
        "?limit=1.5",
        "?limit=1e500",
        "?limit=NaN",
        "?limit=True",
        "?limit=' OR 1=1 --",
    ],
)
def test_dispatch_feed_fuzz_queries(isolated_env, q):
    """GET /api/buffer/dispatch-feed with fuzzed limit query must never raise 500."""
    res = isolated_env.get(f"/api/buffer/dispatch-feed{q}")
    assert res.status_code != 500, f"500 crash on dispatch-feed query '{q}': {res.text}"
    assert res.status_code in (200, 422)
