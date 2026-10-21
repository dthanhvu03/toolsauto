"""Additional empirical adversarial challenger tests for M1.R3.1.
Verifies boundary conditions, complex Vietnamese diacritics, ZWJ emojis,
infinity/NaN corruptions, and malformed database/cache entries.
"""
from __future__ import annotations

import math
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import Base, Job
from app.constants import JobStatus
from app.main import app
import app.features.buffer.cluster_router as cluster_router_mod
from app.features.buffer.manager import get_buffer_manager, reset_buffer_manager


@pytest.fixture
def isolated_client():
    """Isolated environment with temporary WAL SQLite database and cleared caches."""
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
        yield c, session_factory

    cluster_router_mod.SessionLocal = orig_session_local
    reset_buffer_manager()
    cluster_router_mod.reset_cluster_cache()
    engine.dispose()


# ============================================================================
# Section 1: Complex Vietnamese Unicode Diacritics & Combining Marks
# ============================================================================

VIETNAMESE_PROBES = [
    "Tiếng Việt có dấu đầy đủ chữ hoa chữ thường",
    "Đoàn Thị Điểm, Nguyễn Huệ, Trần Hưng Đạo",
    "Khóa_bí_mật_cực_kỳ_dài_có_dấu_huyền_sắc_hỏi_ngã_nặng_ạ_ẽ_ĩ_õ_ũ_ơ_ư",
    "Cộng hòa Xã hội Chủ nghĩa Việt Nam - Độc lập - Tự do - Hạnh phúc",
    "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ",
    "ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴĐ",
]

@pytest.mark.parametrize("vn_text", VIETNAMESE_PROBES)
def test_ping_key_post_vietnamese_characters(isolated_client, vn_text):
    """POST /api/buffer/ping-key with complex Vietnamese text in key must return clean 422, never 500."""
    client, _ = isolated_client
    res = client.post("/api/buffer/ping-key", json={"key": vn_text})
    assert res.status_code == 422, f"Failed for Vietnamese key '{vn_text}': got {res.status_code}"
    data = res.json()
    assert data["ok"] is False
    assert "chứa ký tự không hợp lệ" in data.get("errorMessage", "") or "không hợp lệ" in data.get("errorMessage", "")


@pytest.mark.parametrize("vn_text", VIETNAMESE_PROBES)
def test_ping_key_get_vietnamese_characters(isolated_client, vn_text):
    """GET /api/buffer/ping-key with complex Vietnamese text in query param must return clean 422, never 500."""
    client, _ = isolated_client
    res = client.get("/api/buffer/ping-key", params={"key": vn_text})
    assert res.status_code == 422, f"Failed for GET Vietnamese key '{vn_text}': got {res.status_code}"
    data = res.json()
    assert data["ok"] is False


@pytest.mark.parametrize("vn_text", VIETNAMESE_PROBES)
def test_ping_key_account_index_vietnamese(isolated_client, vn_text):
    """POST /api/buffer/ping-key with Vietnamese text as account_index must return clean 422, never 500."""
    client, _ = isolated_client
    res = client.post("/api/buffer/ping-key", json={"account_index": vn_text})
    assert res.status_code == 422
    data = res.json()
    assert data["ok"] is False


# ============================================================================
# Section 2: Emoji Strings (ZWJ, Multi-byte, Modifiers, Flags)
# ============================================================================

EMOJI_PROBES = [
    "👨‍👩‍👧‍👦",  # Family with ZWJ
    "🧑🏽‍💻",  # Technologist with skin tone & ZWJ
    "🇻🇳🇯🇵🇺🇸🇩🇪",  # Flag sequences
    "🔑🔒🛡️⚡🚀🎉🔥",  # Standard symbols
    "\U0001F600\U0001F603\U0001F604\U0001F601",  # High code points
    "TestKey_With_🔥_And_Vietnamese_Việt",  # Mixed
]

@pytest.mark.parametrize("emoji_str", EMOJI_PROBES)
def test_ping_key_post_emoji_strings(isolated_client, emoji_str):
    """POST /api/buffer/ping-key with complex emoji strings must return 422, never 500."""
    client, _ = isolated_client
    res = client.post("/api/buffer/ping-key", json={"key": emoji_str})
    assert res.status_code == 422, f"Failed for emoji key '{emoji_str}': got {res.status_code}"
    data = res.json()
    assert data["ok"] is False


@pytest.mark.parametrize("emoji_str", EMOJI_PROBES)
def test_ping_key_get_emoji_strings(isolated_client, emoji_str):
    """GET /api/buffer/ping-key with complex emoji strings in query must return 422, never 500."""
    client, _ = isolated_client
    res = client.get("/api/buffer/ping-key", params={"key": emoji_str})
    assert res.status_code == 422, f"Failed for GET emoji key '{emoji_str}': got {res.status_code}"
    data = res.json()
    assert data["ok"] is False


# ============================================================================
# Section 3: NaN, Inf, and Extreme Cooldowns & Quotas
# ============================================================================

EXTREME_COOLDOWNS = [
    float("inf"),
    float("-inf"),
    float("nan"),
    math.inf,
    -math.inf,
    math.nan,
    1e308,
    -1e308,
    sys.maxsize,
    -sys.maxsize,
    253402300800,  # Year 10000 overflow
    -1,
    0,
    None,
    "inf",
    "-inf",
    "nan",
    "infinity",
    "NaN",
]

@pytest.mark.parametrize("cooldown_val", EXTREME_COOLDOWNS)
def test_cluster_status_extreme_cooldown_values(isolated_client, cooldown_val):
    """_KEY_TELEMETRY cooldown_until with extreme floats, inf, nan, or strings must not crash cluster-status."""
    client, _ = isolated_client
    bm = get_buffer_manager()
    keys = bm.get_keys()
    target_key = keys[0]

    cluster_router_mod._KEY_TELEMETRY[target_key] = {
        "status": "COOLDOWN",
        "cooldown_until": cooldown_val,
        "last_ping": 1000,
    }

    res = client.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"Failed on cooldown_val={cooldown_val}: {res.text}"
    data = res.json()
    assert data["ok"] is True
    acc = next(a for a in data["accounts"] if a["index"] == 1)
    # cooldownSeconds must be an integer and clamped
    assert isinstance(acc["cooldownSeconds"], int)
    assert 0 <= acc["cooldownSeconds"] <= cluster_router_mod.MAX_COOLDOWN_SEC


EXTREME_QUOTAS = [
    {"dailyLimit": float("inf"), "dailyRemaining": float("nan")},
    {"dailyLimit": float("-inf"), "dailyRemaining": float("-inf")},
    {"dailyLimit": 1e308, "dailyRemaining": -1e308},
    {"dailyLimit": None, "dailyRemaining": None},
    {"dailyLimit": "không phải số", "dailyRemaining": "nan"},
    {"dailyLimit": [1, 2], "dailyRemaining": {"nested": True}},
]

@pytest.mark.parametrize("quota_val", EXTREME_QUOTAS)
def test_cluster_status_extreme_quota_values(isolated_client, quota_val):
    """_KEY_TELEMETRY quota with extreme floats, inf, nan, or invalid types must not crash cluster-status."""
    client, _ = isolated_client
    bm = get_buffer_manager()
    keys = bm.get_keys()
    target_key = keys[0]

    cluster_router_mod._KEY_TELEMETRY[target_key] = {
        "status": "ACTIVE",
        "cooldown_until": 0,
        "quota": quota_val,
    }

    res = client.get("/api/buffer/cluster-status")
    assert res.status_code == 200, f"Failed on quota_val={quota_val}: {res.text}"
    data = res.json()
    assert data["ok"] is True
    acc = next(a for a in data["accounts"] if a["index"] == 1)
    assert isinstance(acc["quota"]["dailyLimit"], int)
    assert isinstance(acc["quota"]["dailyRemaining"], int)


# ============================================================================
# Section 4: Live Dispatch Feed with Unicode & Corrupt DB Rows
# ============================================================================

def test_dispatch_feed_with_unicode_and_vietnamese_jobs(isolated_client):
    """Dispatch feed with Vietnamese errors, emojis, and unusual statuses must serialize cleanly."""
    client, session_factory = isolated_client

    with session_factory() as db:
        j1 = Job(
            platform="buffer",
            target_page="6ad724e7778b240e2f66d1f9",
            status=JobStatus.FAILED,
            last_error="Lỗi phân quyền Facebook: Mã lỗi 422 - First comment requires a paid plan. 🚀🔑",
            schedule_ts=1792492800,
        )
        j2 = Job(
            platform="buffer",
            target_page="unknown_channel_xyz",
            status=JobStatus.DONE,
            last_error=None,
            schedule_ts=1792493800,
        )
        j3 = Job(
            platform="buffer",
            target_page=None,
            status=JobStatus.FAILED,
            last_error="Buffer HTTP 429: Thử lại sau 3600s",
            schedule_ts=None,
        )
        db.add_all([j1, j2, j3])
        db.commit()

    res = client.get("/api/buffer/dispatch-feed?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["events"]) == 3
    # Ordered by Job.id DESC: events[0] is j3, events[1] is j2, events[2] is j1
    event_j3 = data["events"][0]
    assert event_j3["httpStatus"] == 429
    assert "Buffer HTTP 429" in event_j3["message"]

    event_j1 = data["events"][2]
    assert "🚀🔑" in event_j1["message"]
    assert event_j1["httpStatus"] == 422


# ============================================================================
# Section 5: Cache Isolation & Memory Leaks
# ============================================================================

def test_reset_cluster_cache_cleans_everything():
    """reset_cluster_cache() must completely drain all 4 cache structures."""
    cluster_router_mod._KEY_TELEMETRY["test"] = {"status": "ACTIVE"}
    cluster_router_mod._KEY_CHANNELS_CACHE["test"] = [{"id": "1"}]
    cluster_router_mod._KEY_CHANNELS_TS["test"] = 12345.0
    cluster_router_mod._email_cache["test"] = "test@gmail.com"

    cluster_router_mod.reset_cluster_cache()

    assert len(cluster_router_mod._KEY_TELEMETRY) == 0
    assert len(cluster_router_mod._KEY_CHANNELS_CACHE) == 0
    assert len(cluster_router_mod._KEY_CHANNELS_TS) == 0
    assert len(cluster_router_mod._email_cache) == 0
