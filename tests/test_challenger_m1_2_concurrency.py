"""Challenger M1.2 Adversarial Test Suite: SQLite WAL Concurrency, Cache Integrity & Cooldown Monotonicity.

Empirical verification for:
1. SQLite WAL database concurrency under concurrent read/write load.
2. Race condition & memory leak freedom in _KEY_TELEMETRY and _KEY_CHANNELS_CACHE.
3. Accurate and strictly monotonic countdown for 429 cooldowns.
4. Persistent channel fallback integrity under network error and rate-limiting.
"""
from __future__ import annotations

import concurrent.futures
import os
import sqlite3
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.constants import JobStatus
from app.core.database.models import Base, Job
from app.main import app
import app.features.buffer.cluster_router as cluster_router_mod
from app.features.buffer.manager import reset_buffer_manager


# ============================================================================
# Helpers & Fixtures
# ============================================================================

@pytest.fixture
def temp_wal_db():
    """Create a real on-disk SQLite database file configured in WAL mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    # Set up WAL mode directly on SQLite file
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.commit()
    conn.close()

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 60},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    orig_session_local = cluster_router_mod.SessionLocal
    cluster_router_mod.SessionLocal = session_factory

    yield session_factory, db_path

    cluster_router_mod.SessionLocal = orig_session_local
    engine.dispose()
    for ext in ["", "-wal", "-shm"]:
        p = db_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def clean_cluster_state():
    """Autouse fixture to reset cluster cache and buffer manager before and after every test."""
    cluster_router_mod.reset_cluster_cache()
    reset_buffer_manager()
    yield
    cluster_router_mod.reset_cluster_cache()
    reset_buffer_manager()


@pytest.fixture
def client_with_wal(temp_wal_db):
    session_factory, db_path = temp_wal_db
    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()

    with TestClient(app) as c:
        yield c, session_factory, db_path

    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()



# ============================================================================
# Group 1: SQLite WAL Concurrency Under Parallel Load
# ============================================================================

def test_wal_concurrent_writer_and_dispatch_feed_reads(client_with_wal):
    """Simulate heavy background worker insertions while dispatch-feed is heavily queried."""
    client, session_factory, _ = client_with_wal
    errors = []
    read_counts = []

    def writer_worker(worker_id: int, num_jobs: int):
        try:
            for i in range(num_jobs):
                with session_factory() as db:
                    job = Job(
                        platform="buffer",
                        target_page=f"chan_{worker_id}_{i % 3}",
                        status=JobStatus.DONE if i % 2 == 0 else JobStatus.FAILED,
                        last_error="HTTP 429: Too many requests" if i % 2 != 0 else None,
                        schedule_ts=int(time.time()) - (i * 10),
                        finished_at=int(time.time()) - (i * 10),
                    )
                    db.add(job)
                    db.commit()
                time.sleep(0.002)
        except Exception as e:
            errors.append(f"Writer {worker_id} error: {e}")

    def reader_worker(reader_id: int, num_reads: int):
        try:
            for _ in range(num_reads):
                resp = client.get("/api/buffer/dispatch-feed?limit=20")
                if resp.status_code != 200:
                    errors.append(f"Reader {reader_id} got HTTP {resp.status_code}")
                data = resp.json()
                if not data.get("ok"):
                    errors.append(f"Reader {reader_id} ok != True")
                read_counts.append(len(data.get("events", [])))
                time.sleep(0.003)
        except Exception as e:
            errors.append(f"Reader {reader_id} error: {e}")

    # Launch 6 concurrent writers and 6 concurrent readers
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        writer_futures = [executor.submit(writer_worker, wid, 25) for wid in range(6)]
        reader_futures = [executor.submit(reader_worker, rid, 25) for rid in range(6)]
        concurrent.futures.wait(writer_futures + reader_futures, timeout=30)

    assert not errors, f"Errors encountered during WAL concurrency test: {errors}"
    assert len(read_counts) == 150, f"Expected 150 reads, got {len(read_counts)}"
    # At least some reads saw inserted data
    assert max(read_counts) > 0, "Expected readers to observe inserted jobs"


def test_wal_concurrent_writer_and_cluster_status_reads(client_with_wal):
    """Simulate background worker DB updates while cluster-status is heavily polled."""
    client, session_factory, _ = client_with_wal
    errors = []
    now_ts = int(time.time())

    def writer_worker(wid: int):
        try:
            for i in range(20):
                with session_factory() as db:
                    job = Job(
                        platform="buffer",
                        target_page="6ad724e7778b240e2f66d1f9",
                        status=JobStatus.PENDING,
                        schedule_ts=now_ts + 1000 + (wid * 100) + i,
                    )
                    db.add(job)
                    db.commit()
                time.sleep(0.003)
        except Exception as e:
            errors.append(f"Writer {wid} error: {e}")

    def reader_worker(rid: int):
        try:
            for _ in range(15):
                resp = client.get("/api/buffer/cluster-status")
                if resp.status_code != 200:
                    errors.append(f"Reader {rid} got HTTP {resp.status_code}")
                data = resp.json()
                if not data.get("ok"):
                    errors.append(f"Reader {rid} ok != True")
                time.sleep(0.004)
        except Exception as e:
            errors.append(f"Reader {rid} error: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        wf = [executor.submit(writer_worker, w) for w in range(5)]
        rf = [executor.submit(reader_worker, r) for r in range(5)]
        concurrent.futures.wait(wf + rf, timeout=30)

    assert not errors, f"Encountered concurrency errors: {errors}"


def test_wal_checkpoint_integrity_after_burst(client_with_wal):
    """Verify WAL file can checkpoint without database locked or transaction leakage."""
    client, session_factory, db_path = client_with_wal

    # Insert 50 jobs
    with session_factory() as db:
        for i in range(50):
            db.add(Job(platform="buffer", target_page=f"c_{i}", status=JobStatus.DONE))
        db.commit()

    # Query dispatch feed and cluster status
    resp1 = client.get("/api/buffer/dispatch-feed?limit=50")
    assert resp1.status_code == 200
    resp2 = client.get("/api/buffer/cluster-status")
    assert resp2.status_code == 200

    # Explicit checkpoint check directly on SQLite
    raw_conn = sqlite3.connect(db_path, timeout=5)
    cur = raw_conn.cursor()
    # TRUNCATE checkpoint must succeed with (0, x, x)
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    res = cur.fetchone()
    raw_conn.close()

    assert res is not None
    assert res[0] == 0, f"WAL checkpoint returned busy/error: {res}"


# ============================================================================
# Group 2: Race Conditions & Memory Leak Freedom in Caches
# ============================================================================

def test_key_telemetry_concurrent_race_free(client_with_wal):
    """Assert concurrent writes and reads to _KEY_TELEMETRY do not raise or corrupt."""
    client, *_ = client_with_wal
    errors = []

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"data": {"account": {"email": "lamtruong0978@gmail.com"}}}
    mock_200.headers = {
        "x-ratelimit-remaining": "100",
        "x-ratelimit-limit": "250",
        "x-ratelimit-reset": "1792513107",
    }

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.json.return_value = {"errors": [{"message": "Rate limit exceeded"}]}
    mock_429.headers = {"Retry-After": "60", "x-ratelimit-remaining": "0"}

    counter = 0
    counter_lock = threading.Lock()

    def mock_post_dispatcher(*args, **kwargs):
        nonlocal counter
        with counter_lock:
            counter += 1
            use_200 = (counter % 2 == 0)
        return mock_200 if use_200 else mock_429

    def worker_ping(i: int):
        try:
            resp = client.post("/api/buffer/ping-key", json={"account_index": (i % 3) + 1})
            if resp.status_code not in (200, 429):
                errors.append(f"Unexpected status: {resp.status_code}")
        except Exception as e:
            errors.append(f"Worker ping {i} exception: {e}")

    def worker_status(i: int):
        try:
            resp = client.get("/api/buffer/cluster-status")
            if resp.status_code != 200:
                errors.append(f"Status poll {i} failed: {resp.status_code}")
        except Exception as e:
            errors.append(f"Worker status {i} exception: {e}")

    with patch("requests.post", side_effect=mock_post_dispatcher):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            f_pings = [executor.submit(worker_ping, i) for i in range(40)]
            f_stats = [executor.submit(worker_status, i) for i in range(40)]
            concurrent.futures.wait(f_pings + f_stats, timeout=20)

    assert not errors, f"Race condition errors in cache: {errors}"
    # Verify _KEY_TELEMETRY keys are valid and not corrupted
    for k, v in cluster_router_mod._KEY_TELEMETRY.items():
        assert isinstance(k, str)
        assert "status" in v
        assert v["status"] in ("ACTIVE", "COOLDOWN")
        assert "cooldown_until" in v


def test_memory_leak_telemetry_cache_over_150_requests(client_with_wal):
    """Assert _KEY_TELEMETRY and _KEY_CHANNELS_CACHE do not grow unboundedly."""
    client, *_ = client_with_wal

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"account": {"email": "test@buffer.com"}}}
    mock_resp.headers = {"x-ratelimit-remaining": "200"}

    with patch("requests.post", return_value=mock_resp):
        for i in range(150):
            acc_idx = (i % 3) + 1
            client.get(f"/api/buffer/ping-key?account_index={acc_idx}")
            if i % 30 == 0:
                client.get("/api/buffer/cluster-status")

    # Bounded cache check: exactly <= 3 accounts configured
    assert len(cluster_router_mod._KEY_TELEMETRY) <= 3, (
        f"Memory leak detected! _KEY_TELEMETRY size is {len(cluster_router_mod._KEY_TELEMETRY)}"
    )
    assert len(cluster_router_mod._KEY_CHANNELS_CACHE) <= 3, (
        f"Memory leak detected! _KEY_CHANNELS_CACHE size is {len(cluster_router_mod._KEY_CHANNELS_CACHE)}"
    )


def test_unauthorized_fuzzed_keys_do_not_leak_into_telemetry_cache(client_with_wal):
    """Assert that probing with random invalid keys does not bloat _KEY_TELEMETRY."""
    client, *_ = client_with_wal

    mock_401 = MagicMock()
    mock_401.status_code = 401
    mock_401.json.return_value = {"message": "Invalid token"}
    mock_401.headers = {}

    initial_size = len(cluster_router_mod._KEY_TELEMETRY)

    with patch("requests.post", return_value=mock_401):
        for i in range(50):
            fuzzed_key = f"invalid_random_fuzzed_key_{i}_{time.time()}"
            resp = client.post("/api/buffer/ping-key", json={"key": fuzzed_key})
            assert resp.status_code in (200, 401)
            # Response must be unauthorized
            assert resp.json().get("status") == "UNAUTHORIZED"

    # Telemetry cache must not have been bloated with 50 invalid keys
    assert len(cluster_router_mod._KEY_TELEMETRY) == initial_size, (
        f"Invalid keys leaked into _KEY_TELEMETRY: initial {initial_size}, now {len(cluster_router_mod._KEY_TELEMETRY)}"
    )


# ============================================================================
# Group 3: Cooldown Monotonic Countdown & Accuracy
# ============================================================================

def test_cooldown_monotonic_countdown_progression(client_with_wal):
    """Verify that remaining cooldown seconds strictly decrease monotonically over time."""
    client, *_ = client_with_wal
    now_ts = 1792492800  # fixed base timestamp

    # Set key #1 to cooldown of 300 seconds
    key1 = "AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm"
    target_reset_ts = now_ts + 300
    cluster_router_mod._KEY_TELEMETRY[key1] = {
        "status": "COOLDOWN",
        "cooldown_until": target_reset_ts,
        "latency_ms": 120.0,
        "last_ping": now_ts,
        "quota": {"dailyLimit": 250, "dailyRemaining": 0},
    }

    # Query at successive time offsets
    time_offsets = [0, 50, 100, 200, 280, 299, 300, 350]
    expected_cds = [300, 250, 200, 100, 20, 1, 0, 0]
    expected_statuses = ["COOLDOWN", "COOLDOWN", "COOLDOWN", "COOLDOWN", "COOLDOWN", "COOLDOWN", "ACTIVE", "ACTIVE"]

    observed_cds = []
    observed_statuses = []
    observed_reset_ts = []

    with patch("app.features.buffer.client.BufferClient.organizations", return_value=[{"id": "org1"}]), \
         patch("app.features.buffer.client.BufferClient.channels", return_value=[{"id": "6ad724e7778b240e2f66d1f9", "name": "Chan 1", "service": "facebook"}]):
        for offset in time_offsets:
            simulated_now = now_ts + offset
            with patch("time.time", return_value=simulated_now):
                resp = client.get("/api/buffer/cluster-status")
                assert resp.status_code == 200
                data = resp.json()
                acc1 = next(a for a in data["accounts"] if a["index"] == 1)
                observed_cds.append(acc1["cooldownSeconds"])
                observed_statuses.append(acc1["status"])
                if acc1["resetTs"] is not None:
                    observed_reset_ts.append(acc1["resetTs"])

    assert observed_cds == expected_cds, f"Cooldown countdown violated: expected {expected_cds}, got {observed_cds}"
    assert observed_statuses == expected_statuses, f"Status progression violated: expected {expected_statuses}, got {observed_statuses}"
    # Verify resetTs was invariant throughout the cooldown period
    assert len(set(observed_reset_ts)) == 1, f"resetTs shifted during countdown: {observed_reset_ts}"
    assert observed_reset_ts[0] == target_reset_ts

    # Monotonicity check
    for i in range(len(observed_cds) - 1):
        assert observed_cds[i] >= observed_cds[i + 1], f"Non-monotonic cooldown at step {i}: {observed_cds}"


def test_cooldown_ict_time_formatting(client_with_wal):
    """Verify resetTimeIct produces valid HH:MM DD/MM in ICT timezone."""
    client, *_ = client_with_wal
    # 2026-10-20 12:00:00 UTC -> 19:00:00 ICT
    fixed_ts = 1792497600
    key1 = "AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm"
    cluster_router_mod._KEY_TELEMETRY[key1] = {
        "status": "COOLDOWN",
        "cooldown_until": fixed_ts + 3600,
        "latency_ms": 100.0,
        "last_ping": fixed_ts,
    }

    with patch("time.time", return_value=fixed_ts):
        resp = client.get("/api/buffer/cluster-status")
        assert resp.status_code == 200
        acc1 = resp.json()["accounts"][0]
        assert acc1["resetTimeIct"] is not None
        # Format must match HH:MM DD/MM
        import re
        assert re.match(r"^\d{2}:\d{2}\s+\d{2}/\d{2}$", acc1["resetTimeIct"]), (
            f"Invalid ICT format: {acc1['resetTimeIct']}"
        )


def test_ping_cooldown_syncs_immediately_to_cluster_status(client_with_wal):
    """Assert ping-key receiving 429 immediately updates cluster-status."""
    client, *_ = client_with_wal
    now_ts = 1792492800

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.json.return_value = {"message": "Rate limited"}
    mock_429.headers = {"Retry-After": "720"}

    with patch("time.time", return_value=now_ts):
        with patch("requests.post", return_value=mock_429):
            ping_resp = client.post("/api/buffer/ping-key", json={"account_index": 2})
            assert ping_resp.status_code == 200
            assert ping_resp.json()["status"] == "COOLDOWN"
            assert ping_resp.json()["quota"]["cooldownSeconds"] == 720

        # Now immediately read cluster status
        stat_resp = client.get("/api/buffer/cluster-status")
        assert stat_resp.status_code == 200
        acc2 = next(a for a in stat_resp.json()["accounts"] if a["index"] == 2)
        assert acc2["status"] == "COOLDOWN"
        assert acc2["cooldownSeconds"] == 720


def test_cooldown_reentry_when_buffer_still_returns_429(client_with_wal):
    """When cooldown expires but live call still encounters 429, router gracefully re-enters cooldown."""
    client, *_ = client_with_wal
    now_ts = 1792492800

    key1 = "AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm"
    # Cooldown until exactly now_ts (expired)
    cluster_router_mod._KEY_TELEMETRY[key1] = {
        "status": "COOLDOWN",
        "cooldown_until": now_ts,
        "latency_ms": 100.0,
        "last_ping": now_ts,
    }

    # Live call gets 429 with 'thử lại sau 180s'
    from app.features.buffer.client import BufferError
    err_429 = BufferError("Buffer HTTP 429: Vui lòng thử lại sau 180s.", status_code=429, retry_after=180)

    with patch("time.time", return_value=now_ts):
        with patch("app.features.buffer.client.BufferClient.organizations", side_effect=err_429):
            resp = client.get("/api/buffer/cluster-status")
            assert resp.status_code == 200
            data = resp.json()
            acc1 = next(a for a in data["accounts"] if a["index"] == 1)
            # Must safely re-enter COOLDOWN with 180s cooldown
            assert acc1["status"] == "COOLDOWN"
            assert acc1["cooldownSeconds"] == 180
            # Channels must not be lost (fallback channels preserved)
            assert len(acc1["channels"]) == 3
            assert acc1["channels"][0]["id"]



# ============================================================================
# Group 4: Persistent Channel Fallback & Node Preservation
# ============================================================================

def test_persistent_channel_fallback_preserves_all_8_channels_on_network_failure(client_with_wal):
    """When network raises exception during organization/channels fetch, all 8 channels are preserved."""
    client, *_ = client_with_wal

    with patch.object(cluster_router_mod, "get_buffer_manager") as mock_bm_getter:
        mock_bm = MagicMock()
        mock_clients = []
        for i, k in enumerate(["key1_aaaa", "key2_bbbb", "key3_cccc"], 1):
            c = MagicMock()
            c._key = k
            c._cooldown_until = 0
            # Network failure
            c.organizations.side_effect = ConnectionError("Buffer network gateway offline")
            mock_clients.append(c)

        mock_bm.get_clients.return_value = mock_clients
        mock_bm.get_keys.return_value = ["key1_aaaa", "key2_bbbb", "key3_cccc"]
        mock_bm_getter.return_value = mock_bm

        resp = client.get("/api/buffer/cluster-status")
        assert resp.status_code == 200
        data = resp.json()

        assert data["summary"]["totalChannels"] == 8, f"Expected 8 channels, got {data['summary']['totalChannels']}"
        assert len(data["accounts"]) == 3
        assert len(data["accounts"][0]["channels"]) == 3
        assert len(data["accounts"][1]["channels"]) == 3
        assert len(data["accounts"][2]["channels"]) == 2

        # Verify channels have non-empty ID and service
        for acc in data["accounts"]:
            for ch in acc["channels"]:
                assert ch["id"], "Channel id must not be empty"
                assert ch["service"] in ("facebook", "tiktok", "instagram")


def test_channel_cache_deep_isolation(client_with_wal):
    """Verify that mutating response channels does not mutate internal cache."""
    client, *_ = client_with_wal
    key1 = "AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm"

    # Seed channel cache
    cluster_router_mod._KEY_CHANNELS_CACHE[key1] = [
        {"id": "chan_iso_1", "name": "Immutable Name", "service": "facebook"}
    ]

    resp1 = client.get("/api/buffer/cluster-status")
    assert resp1.status_code == 200
    chans = resp1.json()["accounts"][0]["channels"]
    assert chans[0]["name"] == "Immutable Name"

    # Attempt to tamper with cache in router
    cluster_router_mod._KEY_CHANNELS_CACHE[key1][0]["name"] = "Corrupted Name"

    # Fallback function itself should not be affected
    fallback = cluster_router_mod._get_fallback_channels_for_account(1)
    assert len(fallback) == 3
    assert fallback[0]["name"] != "Corrupted Name"


def test_fallback_with_empty_or_malformed_buffer_channels_env(client_with_wal):
    """If BUFFER_CHANNELS is corrupt or empty, cluster-status returns 200 with 0 channels without 500 error."""
    client, *_ = client_with_wal

    with patch("app.core.settings.get_json", return_value=None):
        resp = client.get("/api/buffer/cluster-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["summary"]["totalAccounts"] >= 1
