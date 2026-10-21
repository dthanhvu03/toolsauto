"""Adversarial stress-testing suite for Buffer Cluster & Command Center Telemetry.
Authored by Empirical Challenger M1.1.

Tests boundary conditions, fuzz inputs, malformed types, header injection,
burst concurrency, and upstream rate-limit header tampering.
"""
from __future__ import annotations

import concurrent.futures
import tempfile
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import Base
from app.main import app
import app.features.buffer.cluster_router as cluster_router_mod
from app.features.buffer.manager import reset_buffer_manager


@pytest.fixture
def file_db():
    """File-based SQLite database in WAL mode for true multi-threaded isolation."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}?timeout=30", echo=False)
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    session_factory = sessionmaker(bind=engine)

    orig_session_local = cluster_router_mod.SessionLocal
    cluster_router_mod.SessionLocal = session_factory

    yield session_factory

    cluster_router_mod.SessionLocal = orig_session_local
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_cluster_state():
    """Autouse fixture to reset cluster cache and buffer manager before and after every test."""
    cluster_router_mod.reset_cluster_cache()
    reset_buffer_manager()
    yield
    cluster_router_mod.reset_cluster_cache()
    reset_buffer_manager()


@pytest.fixture
def client(file_db):
    """FastAPI TestClient with isolated DB and non-throwing server exceptions for status verification."""
    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()



def make_mock_response(status_code: int = 200, json_data: dict = None, headers: dict = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"data": {"account": {"id": "acc_1", "email": "test@gmail.com"}}}
    resp.headers = headers or {}
    return resp


# ============================================================================
# Section 1: Malformed Account Indices & Type Fuzzing (/api/buffer/ping-key)
# ============================================================================

@pytest.mark.parametrize("bad_idx", [0, -1, -999, 99999, 1000000])
def test_ping_key_out_of_bounds_indices(client, bad_idx):
    """Boundary indices outside [1..len(keys)] must return clean 400 Bad Request, never 500."""
    res = client.post("/api/buffer/ping-key", json={"account_index": bad_idx})
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert "errorMessage" in data


@pytest.mark.parametrize("invalid_type_idx", ["invalid_string", [1], {"idx": 1}])
def test_ping_key_invalid_type_indices(client, invalid_type_idx):
    """Non-integer account indices in POST body must return clean 422 JSON, never 500."""
    res = client.post("/api/buffer/ping-key", json={"account_index": invalid_type_idx})
    assert res.status_code == 422
    data = res.json()
    assert data["ok"] is False
    assert "errorMessage" in data


def test_ping_key_get_query_non_integer(client):
    """Query parameter account_index=abc must return 422."""
    res = client.get("/api/buffer/ping-key?account_index=abc")
    assert res.status_code == 422


def test_ping_key_overflow_inf_index(client):
    """CRASH REPRODUCTION: 1e1000 parses as float('inf'), causing OverflowError in int(account_index).
    Must return clean 422, never unhandled 500.
    """
    res = client.post(
        "/api/buffer/ping-key",
        content=b'{"account_index": 1e1000}',
        headers={"Content-Type": "application/json"},
    )
    # Target assertion: must NOT be 500
    assert res.status_code == 422, f"Expected 422 for overflow inf index, got {res.status_code} ({res.text})"


@pytest.mark.parametrize("bad_key", [12345, True, False, ["key_arr"], {"key": "val"}])
def test_ping_key_non_string_key_type(client, bad_key):
    """CRASH REPRODUCTION: non-string key in POST body crashes with AttributeError: '...' object has no attribute 'strip'.
    Must return clean 400 or 422 JSON, never unhandled 500.
    """
    res = client.post("/api/buffer/ping-key", json={"key": bad_key})
    assert res.status_code in (400, 422), f"Expected 400/422 for non-string key, got {res.status_code} ({res.text})"
    data = res.json()
    assert data["ok"] is False


# ============================================================================
# Section 2: Rate-Limit Header Tampering & Extreme Timestamp Resilience
# ============================================================================

def test_ping_key_extreme_reset_timestamp_tampering(client, monkeypatch):
    """CRASH REPRODUCTION: Upstream Buffer returning extreme x-ratelimit-reset (e.g. 9999999999999)
    causes ValueError: year ... is out of range in format_ict(reset_ts).
    Must handle gracefully without crashing with 500.
    """
    mock_resp = make_mock_response(200, headers={"x-ratelimit-reset": "9999999999999"})
    monkeypatch.setattr("requests.post", lambda *a, **kw: mock_resp)

    res = client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200, f"Expected 200 with sanitized timestamp, got {res.status_code} ({res.text})"
    data = res.json()
    assert data["ok"] is True


def test_ping_key_extreme_retry_after_tampering(client, monkeypatch):
    """CRASH REPRODUCTION: Upstream Buffer 429 with extreme Retry-After header
    causes format_ict overflow and poisons _KEY_TELEMETRY.
    Must handle gracefully without crashing with 500.
    """
    mock_resp = make_mock_response(429, headers={"Retry-After": "9999999999999"})
    monkeypatch.setattr("requests.post", lambda *a, **kw: mock_resp)

    res = client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COOLDOWN"


def test_cluster_status_resilience_to_corrupt_telemetry_cooldown(client):
    """CRASH REPRODUCTION: If _KEY_TELEMETRY contains an extreme or corrupt cooldown_until timestamp,
    /api/buffer/cluster-status must not crash with 500.
    """
    cluster_router_mod._KEY_TELEMETRY["AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm"] = {
        "status": "COOLDOWN",
        "cooldown_until": 9999999999999,
        "last_ping": 123456,
    }

    res = client.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"Expected 200 from cluster-status, got {res.status_code} ({res.text})"
    data = res.json()
    assert data["ok"] is True


# ============================================================================
# Section 3: BUFFER_CHANNELS Format Resilience
# ============================================================================

def test_cluster_status_resilience_to_non_list_buffer_channels(client, monkeypatch):
    """CRASH REPRODUCTION: If BUFFER_CHANNELS setting is a dict or non-list,
    _get_fallback_channels_for_account must not raise TypeError (unhashable type: 'slice').
    """
    from app.core import settings as runtime_settings
    monkeypatch.setattr(runtime_settings, "get_json", lambda k: {"corrupt": "dict"} if k == "BUFFER_CHANNELS" else [])

    res = client.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"Expected 200 with non-list BUFFER_CHANNELS, got {res.status_code} ({res.text})"
    data = res.json()
    assert data["ok"] is True


def test_dispatch_feed_resilience_to_non_list_buffer_channels(client, monkeypatch):
    """CRASH REPRODUCTION: If BUFFER_CHANNELS setting is a dict,
    dispatch-feed channel name resolution must not crash.
    """
    from app.core import settings as runtime_settings
    monkeypatch.setattr(runtime_settings, "get_json", lambda k: {"corrupt": "dict"} if k == "BUFFER_CHANNELS" else [])

    res = client.get("/api/buffer/dispatch-feed")
    assert res.status_code == 200, f"Expected 200 with non-list BUFFER_CHANNELS, got {res.status_code} ({res.text})"
    data = res.json()
    assert data["ok"] is True


# ============================================================================
# Section 4: Concurrency & Burst Stress Testing
# ============================================================================

def test_burst_concurrent_requests(client, monkeypatch):
    """Verify system handles 60 concurrent requests across cluster-status, dispatch-feed, and ping-key."""
    mock_resp = make_mock_response(200, headers={"x-ratelimit-remaining": "100", "x-ratelimit-limit": "250"})
    monkeypatch.setattr("requests.post", lambda *a, **kw: mock_resp)

    def _call(endpoint_type, i):
        if endpoint_type == "status":
            return client.get("/api/buffer/cluster-status").status_code
        elif endpoint_type == "feed":
            return client.get("/api/buffer/dispatch-feed?limit=25").status_code
        else:
            return client.post("/api/buffer/ping-key", json={"account_index": (i % 3) + 1}).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        futures = []
        for i in range(20):
            futures.append(ex.submit(_call, "status", i))
            futures.append(ex.submit(_call, "feed", i))
            futures.append(ex.submit(_call, "ping", i))

        results = [f.result() for f in futures]

    assert set(results) == {200}, f"Expected all 200 OK under burst, got: {set(results)}"


# ============================================================================
# Section 5: Header Injection & XSS Immunity
# ============================================================================

def test_header_injection_and_xss_immunity(client):
    """Verify malicious headers (XSS payloads, SQLi strings) do not trigger errors or reflection."""
    malicious_headers = {
        "X-Forwarded-For": "<script>alert('XSS')</script>",
        "User-Agent": "\"/><svg/onload=alert(1)>",
        "Cookie": "session=<script>alert(1)</script>; token=' OR 1=1 --",
    }

    res_manifest = client.get("/manifest.json", headers=malicious_headers)
    assert res_manifest.status_code == 200

    res_sw = client.get("/sw.js", headers=malicious_headers)
    assert res_sw.status_code == 200

    res_status = client.get("/api/buffer/cluster-status", headers=malicious_headers)
    assert res_status.status_code == 200
