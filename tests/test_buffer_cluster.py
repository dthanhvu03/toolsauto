"""Unit test suite cho Buffer Cluster & Command Center Telemetry (Milestone 1).
Bao gồm 29 test cases kiểm định độc lập các endpoint F1, F2, F3, F4, F5 và schema contract.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants import JobStatus
from app.core.database.models import Base, Job
from app.main import app
import app.features.buffer.cluster_router as cluster_router_mod
from app.features.buffer.client import BufferClient
from app.features.buffer.manager import reset_buffer_manager


# ============================================================================
# Shared Fixtures & Mock Helpers
# ============================================================================

@pytest.fixture
def sqlite_db():
    """In-memory SQLite database cô lập cho từng test case."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(engine)
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
def test_client(sqlite_db):
    """FastAPI TestClient với SQLite DB cô lập và reset BufferManager."""
    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()

    with TestClient(app) as client:
        yield client

    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()



def make_mock_response(status_code: int = 200, json_data: dict = None, headers: dict = None):
    """Tạo mock HTTP response cho requests.post tới Buffer API."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


MOCK_200_PING_BODY = {
    "data": {
        "account": {
            "id": "acc_test_1",
            "email": "lamtruong0978@gmail.com",
            "name": "Lâm Trường",
        }
    }
}

MOCK_200_HEADERS = {
    "Content-Type": "application/json",
    "ratelimit": '"100-in-15min"; r=85; t=425, "250-in-1day"; r=142; t=20282',
    "ratelimit-policy": '"100-in-15min"; q=100; w=900, "250-in-1day"; q=250; w=86400',
    "x-ratelimit-limit": "250",
    "x-ratelimit-remaining": "142",
    "x-ratelimit-reset": "1792513107",
}

MOCK_429_PING_BODY = {
    "errors": [
        {
            "message": "Too many requests from this client. Please try again later.",
            "extensions": {"code": "RATE_LIMIT_EXCEEDED", "window": "24h"},
        }
    ]
}

MOCK_429_HEADERS = {
    "Content-Type": "application/json",
    "Retry-After": "20282",
    "ratelimit": '"100-in-15min"; r=41; t=425, "250-in-1day"; r=0; t=20282',
    "ratelimit-policy": '"100-in-15min"; q=100; w=900, "250-in-1day"; q=250; w=86400',
    "x-ratelimit-limit": "250",
    "x-ratelimit-remaining": "0",
    "x-ratelimit-reset": "1792513107",
}

MOCK_401_PING_BODY = {
    "errors": [
        {
            "message": "Access token is not valid",
            "extensions": {"code": "UNAUTHENTICATED"},
        }
    ]
}

MOCK_401_HEADERS = {
    "Content-Type": "application/json",
}

MOCK_500_PING_BODY = {
    "errors": [
        {
            "message": "Internal server error occurred at upstream Buffer service",
        }
    ]
}

MOCK_500_HEADERS = {
    "Content-Type": "application/json",
}


# ============================================================================
# Group 1: PWA Static & Router Integration (5 Tests)
# ============================================================================

def test_manifest_json_returns_200_and_valid_schema(test_client):
    """Kiểm tra /manifest.json trả về HTTP 200, JSON hợp lệ với cấu trúc PWA."""
    res = test_client.get("/manifest.json")
    assert res.status_code == 200
    assert "application/manifest+json" in res.headers["content-type"]
    data = res.json()
    assert data["name"] == "Buffer 3D Neural Cluster"
    assert data["short_name"] == "Buffer3D"
    assert data["start_url"] == "/buffer-cluster"
    assert data["display"] == "standalone"
    assert isinstance(data["icons"], list)
    assert len(data["icons"]) > 0


def test_manifest_accessible_without_auth_cookie(test_client):
    """Kiểm tra /manifest.json có thể truy cập công khai không cần session cookie."""
    res = test_client.get("/manifest.json")
    assert res.status_code == 200
    # Không bị chuyển hướng 302/307 tới /login
    assert res.history == []


def test_sw_js_returns_200_javascript(test_client):
    """Kiểm tra /sw.js trả về HTTP 200 và media_type javascript."""
    res = test_client.get("/sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]
    assert len(res.text.strip()) > 0


def test_sw_js_accessible_without_auth_cookie(test_client):
    """Kiểm tra /sw.js có thể truy cập công khai không bị chặn bởi cookie auth."""
    res = test_client.get("/sw.js")
    assert res.status_code == 200
    assert res.history == []


def test_buffer_cluster_html_page_renders_200(test_client):
    """Kiểm tra /buffer-cluster render trang HTML với 3D canvas container."""
    res = test_client.get("/buffer-cluster")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Buffer 3D Neural Cluster" in res.text
    assert "webgl-container" in res.text


# ============================================================================
# Group 2: Key Health Ping API (/api/buffer/ping-key) (9 Tests)
# ============================================================================

def test_ping_key_200_active_key_contract(test_client, monkeypatch):
    """Kiểm tra ping tài khoản hợp lệ trả về status ACTIVE, HTTP 200 và quota chính xác."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(200, MOCK_200_PING_BODY, MOCK_200_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is True
    assert data["accountIndex"] == 1
    assert data["status"] == "ACTIVE"
    assert data["httpStatus"] == 200
    assert isinstance(data["latencyMs"], (int, float))
    assert data["latencyMs"] >= 0
    assert data["quota"]["dailyRemaining"] == 142
    assert data["quota"]["dailyLimit"] == 250
    assert data["quota"]["burstRemaining"] == 85
    assert data["quota"]["burstLimit"] == 100
    assert data["quota"]["cooldownSeconds"] == 0
    assert data["quota"]["resetTs"] == 1792513107
    assert data["errorMessage"] is None


def test_ping_key_get_query_param(test_client, monkeypatch):
    """Kiểm tra ping qua HTTP GET với tham số query account_index."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(200, MOCK_200_PING_BODY, MOCK_200_HEADERS),
    )

    res = test_client.get("/api/buffer/ping-key?account_index=1")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["accountIndex"] == 1
    assert data["status"] == "ACTIVE"


def test_ping_key_429_cooldown_detection(test_client, monkeypatch):
    """Kiểm tra phát hiện 429 Rate Limit, trích xuất cooldownSeconds và resetTimeIct."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(429, MOCK_429_PING_BODY, MOCK_429_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()

    # Contract 1: ok is True when health probe successfully assesses 429 cooldown status
    assert data["ok"] is True
    assert data["status"] == "COOLDOWN"
    assert data["httpStatus"] == 429
    assert data["quota"]["dailyRemaining"] == 0
    assert data["quota"]["cooldownSeconds"] == 20282
    assert "20/10" in data["quota"]["resetTimeIct"]
    assert "429" in data["errorMessage"]


def test_ping_key_401_unauthorized_token(test_client, monkeypatch):
    """Kiểm tra phát hiện token bị Buffer từ chối (401 UNAUTHORIZED)."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(401, MOCK_401_PING_BODY, MOCK_401_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is False
    assert data["status"] == "UNAUTHORIZED"
    assert data["httpStatus"] == 401
    assert data["quota"] is None
    assert "401" in data["errorMessage"] or "valid" in data["errorMessage"].lower()


def test_ping_key_500_server_error(test_client, monkeypatch):
    """Kiểm tra xử lý lỗi 500 từ máy chủ Buffer."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(500, MOCK_500_PING_BODY, MOCK_500_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is False
    assert data["status"] == "ERROR"
    assert data["httpStatus"] == 500
    assert data["errorMessage"] is not None


def test_ping_key_network_timeout(test_client, monkeypatch):
    """Kiểm tra xử lý ngoại lệ mất kết nối / timeout mạng."""
    def _raise_timeout(*args, **kwargs):
        raise requests.exceptions.ConnectTimeout("Connection timeout to api.buffer.com")

    monkeypatch.setattr("requests.post", _raise_timeout)

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is False
    assert data["status"] == "ERROR"
    assert data["httpStatus"] in (500, 504)
    assert "ConnectTimeout" in data["errorMessage"] or "timeout" in data["errorMessage"].lower()


def test_ping_key_invalid_account_index(test_client):
    """Kiểm tra chỉ mục tài khoản ngoài phạm vi trả về lỗi 400 Bad Request."""
    res = test_client.post("/api/buffer/ping-key?account_index=99")
    assert res.status_code in (400, 404)
    data = res.json()
    assert data["ok"] is False
    assert "Account index 99 not found" in data["errorMessage"] or "không tồn tại" in data["errorMessage"]


def test_ping_key_invalid_param_type(test_client):
    """Kiểm tra account_index dạng chuỗi không hợp lệ trả về lỗi 422."""
    res = test_client.get("/api/buffer/ping-key?account_index=abc")
    assert res.status_code == 422


def test_ping_key_by_raw_key_string(test_client, monkeypatch):
    """Kiểm tra ping chỉ định API key bằng masked key hoặc token."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(200, MOCK_200_PING_BODY, MOCK_200_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"key": "AnD9...ABTm"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["accountIndex"] == 1
    assert data["maskedKey"] == "AnD9...ABTm"


# ============================================================================
# Group 3: Cluster Status API (/api/buffer/cluster-status) (6 Tests)
# ============================================================================

def test_cluster_status_200_all_active(test_client, monkeypatch):
    """Kiểm tra cluster status khi các tài khoản đều ACTIVE và trả về kênh live."""
    mock_org = [{"id": "org_1"}]
    mock_chans = [
        {"id": "ch_1", "name": "Kênh 1", "service": "facebook"},
        {"id": "ch_2", "name": "Kênh 2", "service": "facebook"},
    ]

    monkeypatch.setattr(BufferClient, "organizations", lambda self: mock_org)
    monkeypatch.setattr(BufferClient, "channels", lambda self, org_id: mock_chans)

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is True
    assert data["summary"]["totalAccounts"] == 3
    assert data["summary"]["activeAccounts"] == 3
    assert data["summary"]["cooldownAccounts"] == 0
    assert len(data["accounts"]) == 3
    for acc in data["accounts"]:
        assert acc["status"] == "ACTIVE"
        assert len(acc["channels"]) == 2
        for ch in acc["channels"]:
            assert "id" in ch
            assert "name" in ch
            assert "service" in ch
            assert "pendingCount" in ch


def test_cluster_status_429_persistent_channel_fallback(test_client, monkeypatch):
    """Kiểm định F2: Khi Buffer API 429, kênh không biến mất mà lấy từ fallback cache (8 kênh)."""
    def _raise_429(self):
        raise Exception("Buffer HTTP 429. Vui lòng thử lại sau 3600s.")

    monkeypatch.setattr(BufferClient, "organizations", _raise_429)

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is True
    # Đảm bảo tổng số kênh không bị về 0
    assert data["summary"]["totalChannels"] == 8
    assert data["summary"]["cooldownAccounts"] == 3
    assert len(data["accounts"][0]["channels"]) == 3
    assert len(data["accounts"][1]["channels"]) == 3
    assert len(data["accounts"][2]["channels"]) == 2


def test_cluster_status_partial_cooldown(test_client, monkeypatch):
    """Kiểm tra tài khoản 1 bị 429, tài khoản 2 và 3 vẫn ACTIVE."""
    def _orgs_partial(self):
        if "AnD91" in getattr(self, "_key", ""):
            raise Exception("Buffer HTTP 429. Vui lòng thử lại sau 3600s.")
        return [{"id": "org_ok"}]

    monkeypatch.setattr(BufferClient, "organizations", _orgs_partial)
    monkeypatch.setattr(
        BufferClient,
        "channels",
        lambda self, org_id: [{"id": "ch_sub", "name": "Sub Channel", "service": "facebook"}],
    )

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    assert data["summary"]["activeAccounts"] == 2
    assert data["summary"]["cooldownAccounts"] == 1
    assert data["accounts"][0]["status"] == "COOLDOWN"
    assert data["accounts"][1]["status"] == "ACTIVE"
    assert data["accounts"][2]["status"] == "ACTIVE"


def test_cluster_status_queue_counts_and_next_post_time(test_client, sqlite_db, monkeypatch):
    """Kiểm tra tính toán số lượng bài chờ (pendingCount) và bài kế tiếp (nextPostTime)."""
    monkeypatch.setattr(
        BufferClient,
        "organizations",
        lambda self: (_ for _ in ()).throw(Exception("Buffer HTTP 429. Vui lòng thử lại sau 3600s.")),
    )

    target_cid = "6ad724e7778b240e2f66d1f9"  # Uyển Nhi
    now = int(time.time())

    with sqlite_db() as db:
        for i in range(1, 4):
            db.add(
                Job(
                    id=2000 + i,
                    platform="buffer",
                    target_page=target_cid,
                    status=JobStatus.PENDING,
                    schedule_ts=now + 1800 * i,
                    created_at=now - 100,
                )
            )
        db.commit()

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    acc1 = data["accounts"][0]
    uyennhi_ch = next((c for c in acc1["channels"] if c["id"] == target_cid), None)
    assert uyennhi_ch is not None
    assert uyennhi_ch["pendingCount"] == 3
    assert uyennhi_ch["nextPostTime"] is not None
    assert uyennhi_ch["nextPostTs"] == now + 1800
    assert data["summary"]["totalQueuedPosts"] >= 3


def test_cluster_status_last_post_time_formatting(test_client, sqlite_db, monkeypatch):
    """Kiểm tra trích xuất và định dạng thời gian bài đăng gần nhất (lastPostTime)."""
    monkeypatch.setattr(
        BufferClient,
        "organizations",
        lambda self: (_ for _ in ()).throw(Exception("Buffer HTTP 429. Vui lòng thử lại sau 3600s.")),
    )

    target_cid = "6ad724e7778b240e2f66d1f9"
    now = int(time.time())

    with sqlite_db() as db:
        db.add(
            Job(
                id=3001,
                platform="buffer",
                target_page=target_cid,
                status=JobStatus.DONE,
                schedule_ts=now - 3600,
                finished_at=now - 3500,
                created_at=now - 4000,
            )
        )
        db.commit()

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    acc1 = data["accounts"][0]
    uyennhi_ch = next((c for c in acc1["channels"] if c["id"] == target_cid), None)
    assert uyennhi_ch is not None
    assert uyennhi_ch["lastPostTime"] is not None
    assert uyennhi_ch["lastPostTs"] in (now - 3600, now - 3500)


def test_cluster_status_empty_db_zero_queues(test_client, sqlite_db, monkeypatch):
    """Kiểm tra khi database không có job nào thì queue count là 0 và post times là None."""
    monkeypatch.setattr(
        BufferClient,
        "organizations",
        lambda self: (_ for _ in ()).throw(Exception("Buffer HTTP 429. Vui lòng thử lại sau 3600s.")),
    )

    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()

    assert data["summary"]["totalQueuedPosts"] == 0
    for acc in data["accounts"]:
        for ch in acc["channels"]:
            assert ch["pendingCount"] == 0
            assert ch["nextPostTime"] is None
            assert ch["lastPostTime"] is None


# ============================================================================
# Group 4: Live Dispatch Feed API (/api/buffer/dispatch-feed) (6 Tests)
# ============================================================================

def test_dispatch_feed_schema_contract(test_client, sqlite_db):
    """Kiểm tra endpoint /api/buffer/dispatch-feed trả về đầy đủ các trường sự kiện."""
    now = int(time.time())
    with sqlite_db() as db:
        db.add(
            Job(
                id=101,
                platform="buffer",
                target_page="6ad724e7778b240e2f66d1f9",
                status=JobStatus.DONE,
                created_at=now - 100,
                finished_at=now - 50,
            )
        )
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed")
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is True
    assert data["timestamp"] > 0
    assert len(data["events"]) == 1

    ev = data["events"][0]
    assert ev["jobId"] == 101
    assert ev["channelId"] == "6ad724e7778b240e2f66d1f9"
    assert ev["channelName"] == "Uyển Nhi"
    assert ev["service"] == "facebook"
    assert ev["accountIndex"] == 1
    assert isinstance(ev["keyMasked"], str)
    assert ev["status"] == "DONE"
    assert ev["httpStatus"] == 200
    assert "timeIct" in ev
    assert ev["timestamp"] > 0
    assert "message" in ev


def test_dispatch_feed_status_mapping(test_client, sqlite_db):
    """Kiểm tra ánh xạ trạng thái DB -> HTTP Status (DONE->200, 429->429, 422->422, generic->500)."""
    now = int(time.time())
    with sqlite_db() as db:
        # Job 1: DONE -> 200
        db.add(Job(id=1, platform="buffer", target_page="ch1", status=JobStatus.DONE, created_at=now - 40))
        # Job 2: FAILED 429 -> 429
        db.add(
            Job(
                id=2,
                platform="buffer",
                target_page="ch2",
                status=JobStatus.FAILED,
                last_error="Buffer HTTP 429: Too many requests",
                created_at=now - 30,
            )
        )
        # Job 3: FAILED 422 -> 422 (First comment requires paid plan)
        db.add(
            Job(
                id=3,
                platform="buffer",
                target_page="ch3",
                status=JobStatus.FAILED,
                last_error="Invalid post: First comment requires a paid plan",
                created_at=now - 20,
            )
        )
        # Job 4: FAILED 500 -> 500 (Generic server error)
        db.add(
            Job(
                id=4,
                platform="buffer",
                target_page="ch4",
                status=JobStatus.FAILED,
                last_error="Internal database error",
                created_at=now - 10,
            )
        )
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed?limit=10")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 4

    # Sắp xếp id desc: Job 4, 3, 2, 1
    assert events[0]["jobId"] == 4
    assert events[0]["status"] == "FAILED"
    assert events[0]["httpStatus"] == 500

    assert events[1]["jobId"] == 3
    assert events[1]["status"] == "FAILED"
    assert events[1]["httpStatus"] == 422

    assert events[2]["jobId"] == 2
    assert events[2]["status"] == "FAILED"
    assert events[2]["httpStatus"] == 429

    assert events[3]["jobId"] == 1
    assert events[3]["status"] == "DONE"
    assert events[3]["httpStatus"] == 200


def test_dispatch_feed_limit_query_param(test_client, sqlite_db):
    """Kiểm tra tham số limit giới hạn đúng số lượng bản ghi trả về."""
    now = int(time.time())
    with sqlite_db() as db:
        for i in range(1, 16):
            db.add(Job(id=i, platform="buffer", target_page="ch_test", status=JobStatus.DONE, created_at=now))
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed?limit=5")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 5
    assert events[0]["jobId"] == 15
    assert events[4]["jobId"] == 11


def test_dispatch_feed_clamping_max_limit(test_client, sqlite_db):
    """Kiểm tra giá trị limit vượt quá 100 được kẹp tối đa 100."""
    now = int(time.time())
    with sqlite_db() as db:
        for i in range(1, 11):
            db.add(Job(id=i, platform="buffer", target_page="ch_test", status=JobStatus.DONE, created_at=now))
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed?limit=500")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 10


def test_dispatch_feed_filters_only_buffer_platform(test_client, sqlite_db):
    """Kiểm tra chỉ lấy các job có platform == 'buffer', bỏ qua các platform khác."""
    now = int(time.time())
    with sqlite_db() as db:
        db.add(Job(id=1, platform="buffer", target_page="ch_buf_1", status=JobStatus.DONE, created_at=now))
        db.add(Job(id=2, platform="facebook", target_page="fb_page", status=JobStatus.DONE, created_at=now))
        db.add(Job(id=3, platform="tiktok", target_page="tt_user", status=JobStatus.DONE, created_at=now))
        db.add(Job(id=4, platform="buffer", target_page="ch_buf_2", status=JobStatus.DONE, created_at=now))
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 2
    assert {e["jobId"] for e in events} == {1, 4}


def test_dispatch_feed_empty_db(test_client, sqlite_db):
    """Kiểm tra khi DB chưa có job nào thì trả về danh sách sự kiện rỗng an toàn."""
    res = test_client.get("/api/buffer/dispatch-feed")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["events"] == []


# ============================================================================
# Group 5: Strict Schema Contract Enforcement (3 Tests)
# ============================================================================

def test_ping_key_schema_strict_types(test_client, monkeypatch):
    """Kiểm định kiểu dữ liệu nghiêm ngặt của /api/buffer/ping-key theo Contract 1."""
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: make_mock_response(200, MOCK_200_PING_BODY, MOCK_200_HEADERS),
    )

    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    body = res.json()

    assert isinstance(body["ok"], bool)
    assert isinstance(body["accountIndex"], int)
    assert isinstance(body["email"], str)
    assert isinstance(body["maskedKey"], str)
    assert isinstance(body["status"], str)
    assert isinstance(body["httpStatus"], int)
    assert isinstance(body["latencyMs"], (float, int))
    assert isinstance(body["timestamp"], int)

    quota = body["quota"]
    assert isinstance(quota, dict)
    assert isinstance(quota["dailyLimit"], int)
    assert isinstance(quota["dailyRemaining"], int)
    assert isinstance(quota["burstLimit"], int)
    assert isinstance(quota["burstRemaining"], int)
    assert isinstance(quota["resetTs"], int)
    assert isinstance(quota["resetTimeIct"], str)
    assert isinstance(quota["cooldownSeconds"], int)


def test_cluster_status_schema_strict_types(test_client):
    """Kiểm định kiểu dữ liệu nghiêm ngặt của /api/buffer/cluster-status theo Contract 2."""
    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    body = res.json()

    assert isinstance(body["ok"], bool)
    assert isinstance(body["timestamp"], int)

    summary = body["summary"]
    assert isinstance(summary["totalAccounts"], int)
    assert isinstance(summary["activeAccounts"], int)
    assert isinstance(summary["cooldownAccounts"], int)
    assert isinstance(summary["totalChannels"], int)
    assert isinstance(summary["totalQueuedPosts"], int)

    accounts = body["accounts"]
    assert isinstance(accounts, list)
    assert len(accounts) > 0

    acc = accounts[0]
    assert isinstance(acc["index"], int)
    assert isinstance(acc["name"], str)
    assert isinstance(acc["email"], str)
    assert isinstance(acc["maskedKey"], str)
    assert isinstance(acc["status"], str)
    assert isinstance(acc["cooldownSeconds"], int)
    assert isinstance(acc["channelCount"], int)
    assert isinstance(acc["quota"], dict)
    assert isinstance(acc["channels"], list)

    if acc["channels"]:
        ch = acc["channels"][0]
        assert isinstance(ch["id"], str)
        assert isinstance(ch["name"], str)
        assert isinstance(ch["service"], str)
        assert isinstance(ch["pendingCount"], int)


def test_dispatch_feed_schema_strict_types(test_client, sqlite_db):
    """Kiểm định kiểu dữ liệu nghiêm ngặt của /api/buffer/dispatch-feed theo Contract 3."""
    now = int(time.time())
    with sqlite_db() as db:
        db.add(
            Job(
                id=999,
                platform="buffer",
                target_page="6ad724e7778b240e2f66d1f9",
                status=JobStatus.DONE,
                created_at=now,
            )
        )
        db.commit()

    res = test_client.get("/api/buffer/dispatch-feed")
    assert res.status_code == 200
    body = res.json()

    assert isinstance(body["ok"], bool)
    assert isinstance(body["timestamp"], int)
    assert isinstance(body["events"], list)
    assert len(body["events"]) > 0

    ev = body["events"][0]
    assert isinstance(ev["jobId"], int)
    assert isinstance(ev["channelId"], str)
    assert isinstance(ev["channelName"], str)
    assert isinstance(ev["service"], str)
    assert isinstance(ev["accountIndex"], int)
    assert isinstance(ev["keyMasked"], str)
    assert isinstance(ev["status"], str)
    assert isinstance(ev["httpStatus"], int)
    assert isinstance(ev["timeIct"], str)
    assert isinstance(ev["timestamp"], int)
    assert isinstance(ev["message"], str)


# ============================================================================
# Section 6: Additional Adversarial Hardening Tests (Iteration 2)
# ============================================================================

@pytest.mark.parametrize("bad_key", [12345, True, False, ["key_arr"], {"key": "val"}])
def test_ping_key_non_string_key_type_safety(test_client, bad_key):
    """Verify non-string key in POST body returns 400 or 422 JSON, never 500 unhandled exception."""
    res = test_client.post("/api/buffer/ping-key", json={"key": bad_key})
    assert res.status_code in (400, 422)
    data = res.json()
    assert data["ok"] is False
    assert "errorMessage" in data


def test_ping_key_overflow_infinity_account_index(test_client):
    """Verify float infinity account_index (1e1000) returns 422 instead of crashing with OverflowError."""
    res = test_client.post(
        "/api/buffer/ping-key",
        content=b'{"account_index": 1e1000}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
    data = res.json()
    assert data["ok"] is False


def test_ping_key_extreme_timestamp_clamping(test_client, monkeypatch):
    """Verify extreme rate-limit reset timestamps are clamped safely without year overflow."""
    resp = make_mock_response(200, MOCK_200_PING_BODY, {"x-ratelimit-reset": "9999999999999"})
    monkeypatch.setattr("requests.post", lambda *a, **kw: resp)
    res = test_client.post("/api/buffer/ping-key", json={"account_index": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "resetTimeIct" in data["quota"]


def test_cluster_status_resilience_to_malformed_buffer_channels_setting(test_client, monkeypatch):
    """Verify non-list BUFFER_CHANNELS setting defaults cleanly to empty list without slice crash."""
    from app.core import settings as runtime_settings
    monkeypatch.setattr(runtime_settings, "get_json", lambda k: {"corrupt": "dict"} if k == "BUFFER_CHANNELS" else [])
    res = test_client.get("/api/buffer/cluster-status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True


def test_cluster_status_60s_channel_cache_ttl(test_client):
    """Verify channel cache is maintained in memory without redundant network requests."""
    res1 = test_client.get("/api/buffer/cluster-status")
    assert res1.status_code == 200
    res2 = test_client.get("/api/buffer/cluster-status")
    assert res2.status_code == 200


def test_cluster_status_live_channel_fetch_60s_cache_ttl(test_client, monkeypatch):
    """Kiểm tra cơ chế cache TTL 60s cho live channel fetch:
    1. Lần gọi 1: Gọi BufferClient.organizations() và BufferClient.channels() để fetch live channels và lưu cache.
    2. Lần gọi 2 (sau < 60s): Sử dụng dữ liệu kênh đã cache, KHÔNG gọi lại API organizations()/channels().
    3. Lần gọi 3 (sau > 60s): Cache hết hạn, gọi lại Buffer API để làm mới danh sách kênh.
    """
    from app.features.buffer.client import BufferClient
    org_calls = 0
    chan_calls = 0

    def mock_orgs(self):
        nonlocal org_calls
        org_calls += 1
        return [{"id": "org_ttl_1"}]

    def mock_channels(self, org_id):
        nonlocal chan_calls
        chan_calls += 1
        return [
            {"id": "ch_ttl_1", "name": "TTL Channel 1", "service": "facebook"},
            {"id": "ch_ttl_2", "name": "TTL Channel 2", "service": "facebook"},
        ]

    monkeypatch.setattr(BufferClient, "organizations", mock_orgs)
    monkeypatch.setattr(BufferClient, "channels", mock_channels)

    current_simulated_time = 1792492800.0

    def mock_time():
        return current_simulated_time

    monkeypatch.setattr(time, "time", mock_time)

    # Lần 1: Chưa có cache -> Phải gọi API live
    res1 = test_client.get("/api/buffer/cluster-status")
    assert res1.status_code == 200
    assert org_calls > 0
    assert chan_calls > 0
    initial_org_calls = org_calls
    initial_chan_calls = chan_calls

    # Lần 2: 30s sau (< 60s TTL) -> Phải dùng cache, số lượt gọi API không tăng
    current_simulated_time += 30.0
    res2 = test_client.get("/api/buffer/cluster-status")
    assert res2.status_code == 200
    assert org_calls == initial_org_calls, "organizations() should NOT be called within 60s TTL window"
    assert chan_calls == initial_chan_calls, "channels() should NOT be called within 60s TTL window"

    # Lần 3: 65s sau (> 60s TTL) -> Cache hết hạn, phải gọi lại Buffer API
    current_simulated_time += 35.0  # Tổng cộng 65s > 60s
    res3 = test_client.get("/api/buffer/cluster-status")
    assert res3.status_code == 200
    assert org_calls > initial_org_calls, "organizations() MUST be called after 60s TTL expires"
    assert chan_calls > initial_chan_calls, "channels() MUST be called after 60s TTL expires"
