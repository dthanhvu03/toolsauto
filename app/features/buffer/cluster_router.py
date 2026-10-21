"""Router cung cấp API trạng thái cụm tài khoản Buffer, telemetry chẩn đoán và Dashboard 3D Three.js.
"""
from __future__ import annotations

import copy
import logging
import math
import os
import re
import time
from typing import Any, Optional

import requests
from fastapi import APIRouter, Body, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.constants import JobStatus
from app.core import settings as runtime_settings
from app.core.database.core import SessionLocal
from app.core.database.models import Job
from app.features.buffer.manager import get_buffer_manager, mask_key
from app.features.buffer.when import format_ict

logger = logging.getLogger(__name__)

router = APIRouter(tags=["buffer-cluster"])
templates = Jinja2Templates(directory="app/templates")

MAX_COOLDOWN_SEC = 2592000  # Trần bảo vệ tối đa 30 ngày (tránh tràn số năm trong format_ict)
CHANNEL_CACHE_TTL_SEC = 300  # 5 phút — tránh poll cluster đốt organizations/channels

# Ánh xạ email theo Masked Key (tuân thủ CWE-798: không lưu token thô trong source code)
KNOWN_EMAILS: dict[str, str] = {
    "AnD9...ABTm": "lamtruong0978@gmail.com",
    "RZX2...PVmg": "thanhvu08103@gmail.com",
    "ZVsP...1QO5": "dthanhvu08103@gmail.com",
}

# Ánh xạ email mặc định theo số thứ tự tài khoản
ACCOUNT_EMAILS_BY_INDEX: dict[int, str] = {
    1: "lamtruong0978@gmail.com",
    2: "thanhvu08103@gmail.com",
    3: "dthanhvu08103@gmail.com",
}

# Cache email đã đọc từ Buffer GraphQL (TTL 24h)
_email_cache: dict[str, str] = {}

# Persistent key telemetry cache: key -> {status, cooldown_until, latency_ms, last_ping, quota}
_KEY_TELEMETRY: dict[str, dict[str, Any]] = {}

# Persistent channel cache: key -> list[dict]
_KEY_CHANNELS_CACHE: dict[str, list[dict]] = {}

# Timestamp cập nhật cache kênh: key -> float
_KEY_CHANNELS_TS: dict[str, float] = {}
_KEY_CHANNELS_CACHE_TS: dict[str, float] = _KEY_CHANNELS_TS


def reset_cluster_cache() -> None:
    """Reset all in-memory telemetry, channel caches, and email resolution caches for test isolation."""
    _KEY_TELEMETRY.clear()
    _KEY_CHANNELS_CACHE.clear()
    _KEY_CHANNELS_TS.clear()
    _email_cache.clear()



def _safe_format_ict(ts: Optional[Any]) -> Optional[str]:
    """Chuyển đổi timestamp sang chuỗi ICT an toàn, chặn tràn năm và bắt ngoại lệ."""
    if ts is None:
        return None
    try:
        t = int(ts)
        if t <= 0 or t > 253402300799:  # Giới hạn năm 9999
            return None
        return format_ict(t)
    except Exception:
        return None


def _get_fallback_channels_for_account(idx: int) -> list[dict]:
    """Phân bổ 8 kênh mặc định từ BUFFER_CHANNELS cho 3 tài khoản Buffer."""
    try:
        raw_channels = runtime_settings.get_json("BUFFER_CHANNELS") or []
    except Exception:
        raw_channels = []
    if not isinstance(raw_channels, list) or not raw_channels:
        return []
    channels_copy = copy.deepcopy(raw_channels)
    # Account 1 (idx=1): 0..3 (3 channels)
    # Account 2 (idx=2): 3..6 (3 channels)
    # Account 3 (idx=3): 6..8 (2 channels)
    if idx == 1:
        return channels_copy[0:3]
    elif idx == 2:
        return channels_copy[3:6]
    elif idx == 3:
        return channels_copy[6:8]
    start = (idx - 1) * 3
    return channels_copy[start : start + 3]


def _resolve_account_email(client: Any, key: str, idx: int = 1) -> str:
    """Lấy email từ cache hoặc query Buffer GraphQL, fallback theo masked key hoặc index."""
    if key in _email_cache:
        return _email_cache[key]
    masked = mask_key(key)
    if masked in _email_cache:
        return _email_cache[masked]
    if client and hasattr(client, "execute"):
        try:
            res = client.execute("query { account { email name } }")
            acc = res.get("account") or {}
            email = (acc.get("email") or "").strip()
            if email:
                _email_cache[key] = email
                _email_cache[masked] = email
                return email
        except Exception:
            pass
    if masked in KNOWN_EMAILS:
        return KNOWN_EMAILS[masked]
    if idx in ACCOUNT_EMAILS_BY_INDEX:
        return ACCOUNT_EMAILS_BY_INDEX[idx]
    return "chua_xac_dinh@buffer.com"


# ============================================================================
# F1: PWA Endpoints (/manifest.json, /sw.js)
# ============================================================================

@router.get("/manifest.json")
def get_manifest():
    """Manifest định danh Web App PWA cho Mobile & Desktop."""
    manifest_path = "app/static/manifest.json"
    if os.path.exists(manifest_path) and os.path.getsize(manifest_path) > 10:
        return FileResponse(manifest_path, media_type="application/manifest+json")
    return JSONResponse(
        {
            "name": "Buffer 3D Neural Cluster",
            "short_name": "Buffer3D",
            "description": "Buffer 3D Neural Cluster & Command Center",
            "start_url": "/buffer-cluster",
            "display": "standalone",
            "background_color": "#07090e",
            "theme_color": "#07090e",
            "icons": [
                {
                    "src": "/static/img/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": "/static/img/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                },
            ],
        },
        media_type="application/manifest+json",
    )


@router.get("/sw.js")
def get_service_worker():
    """Service Worker quản lý bộ nhớ đệm và offline cache."""
    sw_path = "app/static/sw.js"
    if os.path.exists(sw_path) and os.path.getsize(sw_path) > 10:
        return FileResponse(sw_path, media_type="application/javascript")
    return Response(
        "/* Buffer 3D Neural Cluster Service Worker */\n"
        "const CACHE_NAME = 'buffer-cluster-v1';\n"
        "self.addEventListener('install', (e) => { self.skipWaiting(); });\n"
        "self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });\n"
        "self.addEventListener('fetch', (e) => {});\n",
        media_type="application/javascript",
    )


# ============================================================================
# F2 & F5: Expanded Cluster Status API (/api/buffer/cluster-status)
# ============================================================================

@router.get("/api/buffer/cluster-status", response_class=JSONResponse)
def get_cluster_status():
    """Trả về dữ liệu thời gian thực của toàn bộ cụm tài khoản Buffer và các kênh vệ tinh."""
    bm = get_buffer_manager()
    clients = bm.get_clients()
    now_ts = int(time.time())

    # -------------------------------------------------------------------------
    # GIAI ĐOẠN 1: Thu thập metadata & channels (Hoàn toàn NGOÀI Database Session)
    # -------------------------------------------------------------------------
    account_snapshots: list[dict[str, Any]] = []
    for idx, client in enumerate(clients, 1):
        key = getattr(client, "_key", "")
        masked = mask_key(key)
        email = _resolve_account_email(client, key, idx=idx)

        telemetry = _KEY_TELEMETRY.get(key, {})
        if not isinstance(telemetry, dict):
            telemetry = {}

        cd_val = telemetry.get("cooldown_until", 0)
        try:
            cached_cooldown_until = float(cd_val) if cd_val is not None else 0.0
            if not math.isfinite(cached_cooldown_until):
                cached_cooldown_until = 0.0
        except (ValueError, TypeError, OverflowError):
            cached_cooldown_until = 0.0

        client_cd_raw = getattr(client, "_cooldown_until", 0)
        try:
            client_cd = float(client_cd_raw) if client_cd_raw is not None else 0.0
            if not math.isfinite(client_cd):
                client_cd = 0.0
        except (ValueError, TypeError, OverflowError):
            client_cd = 0.0

        effective_cd_until = max(cached_cooldown_until, client_cd)

        try:
            diff = effective_cd_until - now_ts
            if not math.isfinite(diff):
                remaining_cd = 0
            else:
                remaining_cd = max(0, int(diff))
                if remaining_cd > MAX_COOLDOWN_SEC:
                    remaining_cd = MAX_COOLDOWN_SEC
        except (ValueError, TypeError, OverflowError):
            remaining_cd = 0
        status = "COOLDOWN" if remaining_cd > 0 else "ACTIVE"

        client_channels = []
        raw_cache_ts = _KEY_CHANNELS_TS.get(key, 0)
        try:
            cache_age = now_ts - float(raw_cache_ts)
        except (ValueError, TypeError, OverflowError):
            cache_age = 999999999.0

        cached_entry = _KEY_CHANNELS_CACHE.get(key)
        valid_cached_channels = (
            [copy.deepcopy(ch) for ch in cached_entry if isinstance(ch, dict)]
            if isinstance(cached_entry, list)
            else None
        )

        # Không live-fetch khi COOLDOWN / client đang khóa 429 — chỉ dùng cache/fallback
        client_cd_left = 0.0
        if hasattr(client, "cooldown_remaining"):
            try:
                client_cd_left = float(client.cooldown_remaining() or 0)
            except Exception:
                client_cd_left = 0.0
        if client_cd_left > 0:
            status = "COOLDOWN"
            remaining_cd = max(remaining_cd, int(client_cd_left) + 1)

        # Cache 5 phút nếu ACTIVE; hết hạn mới gọi organizations/channels
        if status != "COOLDOWN" and valid_cached_channels and cache_age < CHANNEL_CACHE_TTL_SEC:
            client_channels = copy.deepcopy(valid_cached_channels)
        elif status != "COOLDOWN" and client_cd_left <= 0:
            try:
                orgs = client.organizations() if hasattr(client, "organizations") else []
                if isinstance(orgs, list):
                    for org in orgs:
                        if not isinstance(org, dict):
                            continue
                        channels = client.channels(org.get("id", "")) if hasattr(client, "channels") else []
                        if isinstance(channels, list):
                            for ch in channels:
                                if isinstance(ch, dict):
                                    cid = str(ch.get("id") or "").strip()
                                    if cid:
                                        client_channels.append(ch)
                if client_channels:
                    _KEY_CHANNELS_CACHE[key] = copy.deepcopy(client_channels)
                    _KEY_CHANNELS_TS[key] = now_ts
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str:
                    status = "COOLDOWN"
                    match = re.search(r"thử lại sau (\d+)s", err_str)
                    if match:
                        remaining_cd = int(match.group(1))
                    elif remaining_cd == 0:
                        remaining_cd = 900
                    if remaining_cd > MAX_COOLDOWN_SEC:
                        remaining_cd = MAX_COOLDOWN_SEC
                    if hasattr(client, "mark_rate_limited"):
                        try:
                            client.mark_rate_limited(remaining_cd)
                        except Exception:
                            pass
                    _KEY_TELEMETRY[key] = {
                        "status": "COOLDOWN",
                        "cooldown_until": now_ts + remaining_cd,
                        "last_ping": now_ts,
                    }

        # FALLBACK TIER (F2): Khi live channels rỗng (do 429 hoặc lỗi kết nối mạng)
        if not client_channels:
            if valid_cached_channels:
                client_channels = copy.deepcopy(valid_cached_channels)
            else:
                client_channels = _get_fallback_channels_for_account(idx)

        reset_ts = now_ts + remaining_cd if remaining_cd > 0 else None
        quota_raw = telemetry.get("quota") if isinstance(telemetry, dict) else None
        quota_dict = quota_raw if isinstance(quota_raw, dict) else {}

        raw_lim = quota_dict.get("dailyLimit", 250)
        try:
            daily_lim = int(raw_lim)
        except (ValueError, TypeError, OverflowError):
            daily_lim = 250

        if status == "COOLDOWN":
            daily_rem = 0
        else:
            raw_rem = quota_dict.get("dailyRemaining", 250)
            try:
                daily_rem = int(raw_rem)
            except (ValueError, TypeError, OverflowError):
                daily_rem = 250

        account_snapshots.append({
            "idx": idx,
            "name": f"Tài khoản #{idx}",
            "email": email,
            "maskedKey": masked,
            "status": status,
            "remaining_cd": remaining_cd,
            "reset_ts": reset_ts,
            "daily_lim": daily_lim,
            "daily_rem": daily_rem,
            "raw_channels": client_channels,
        })

    # -------------------------------------------------------------------------
    # GIAI ĐOẠN 2: Làm giàu dữ liệu hàng đợi từ Database (Mở DB Session ngắn hạn)
    # -------------------------------------------------------------------------
    accounts_data = []
    total_channels_count = 0
    total_queued_count = 0
    active_accounts_count = 0

    with SessionLocal() as db:
        for snap in account_snapshots:
            enriched_channels = []
            raw_channels = snap.get("raw_channels")
            if not isinstance(raw_channels, list):
                raw_channels = []
            for ch in raw_channels:
                if not isinstance(ch, dict):
                    continue
                cid = str(ch.get("id") or "").strip()
                if not cid:
                    continue

                # Đếm số bài đang chờ trong DB
                pending_cnt = (
                    db.query(Job)
                    .filter(
                        Job.platform == "buffer",
                        Job.target_page == cid,
                        Job.status.in_([JobStatus.PENDING, JobStatus.DONE]),
                        Job.schedule_ts > now_ts,
                    )
                    .count()
                )

                # Bài đăng kế tiếp
                next_job = (
                    db.query(Job)
                    .filter(
                        Job.platform == "buffer",
                        Job.target_page == cid,
                        Job.status.in_([JobStatus.PENDING, JobStatus.DONE]),
                        Job.schedule_ts > now_ts,
                    )
                    .order_by(Job.schedule_ts.asc())
                    .first()
                )

                # Bài đăng gần nhất
                last_job = (
                    db.query(Job)
                    .filter(
                        Job.platform == "buffer",
                        Job.target_page == cid,
                        Job.status == JobStatus.DONE,
                        Job.schedule_ts <= now_ts,
                    )
                    .order_by(Job.schedule_ts.desc())
                    .first()
                )

                next_time_str = _safe_format_ict(next_job.schedule_ts) if next_job and next_job.schedule_ts else None
                last_ts = (
                    (last_job.finished_at or last_job.schedule_ts)
                    if last_job
                    else None
                )
                last_time_str = _safe_format_ict(last_ts) if last_ts else None

                total_queued_count += pending_cnt
                enriched_channels.append(
                    {
                        "id": cid,
                        "name": str(ch.get("name") or cid),
                        "service": str(ch.get("service") or "facebook").lower(),
                        "pendingCount": pending_cnt,
                        "nextPostTime": next_time_str,
                        "nextPostTs": next_job.schedule_ts if next_job else None,
                        "lastPostTime": last_time_str,
                        "lastPostTs": last_ts,
                    }
                )

            if snap["status"] == "ACTIVE":
                active_accounts_count += 1

            total_channels_count += len(enriched_channels)
            reset_ts = snap["reset_ts"]

            accounts_data.append(
                {
                    "index": snap["idx"],
                    "name": snap["name"],
                    "email": snap["email"],
                    "maskedKey": snap["maskedKey"],
                    "status": snap["status"],
                    "cooldownSeconds": snap["remaining_cd"],
                    "resetTimeIct": _safe_format_ict(reset_ts),
                    "resetTs": reset_ts,
                    "quota": {
                        "dailyLimit": snap["daily_lim"],
                        "dailyRemaining": snap["daily_rem"],
                    },
                    "channelCount": len(enriched_channels),
                    "channels": enriched_channels,
                }
            )

    return {
        "ok": True,
        "timestamp": now_ts,
        "summary": {
            "totalAccounts": len(clients),
            "activeAccounts": active_accounts_count,
            "cooldownAccounts": len(clients) - active_accounts_count,
            "totalChannels": total_channels_count,
            "totalQueuedPosts": total_queued_count,
        },
        "accounts": accounts_data,
    }


# ============================================================================
# F3: Key Health Ping API (/api/buffer/ping-key)
# ============================================================================

def _handle_ping_key(
    account_index: Optional[Any] = None,
    key: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Any:
    """Xử lý đo độ trễ mạng, kiểm tra trạng thái token và trích xuất quota từ Buffer API."""
    bm = get_buffer_manager()
    keys = bm.get_keys()
    now_ts = int(time.time())

    # Trích xuất tham số từ body payload nếu có
    if payload and isinstance(payload, dict):
        if account_index is None:
            account_index = payload.get("account_index")
            if account_index is None:
                account_index = payload.get("accountIndex")
        if key is None and "key" in payload:
            key = payload.get("key")

    target_idx = 1
    raw_key = ""

    if account_index is not None:
        try:
            target_idx = int(account_index)
        except (ValueError, TypeError, OverflowError):
            return JSONResponse({"ok": False, "errorMessage": "account_index không hợp lệ."}, status_code=422)

        if 1 <= target_idx <= len(keys):
            raw_key = keys[target_idx - 1]
        else:
            return JSONResponse(
                {
                    "ok": False,
                    "errorMessage": f"Account index {target_idx} not found (Chỉ mục tài khoản #{target_idx} không tồn tại).",
                },
                status_code=400,
            )
    elif key is not None:
        if not isinstance(key, str):
            return JSONResponse(
                {"ok": False, "errorMessage": "Tham số key phải là chuỗi (string)."},
                status_code=422,
            )
        clean_k = key.strip()
        if not clean_k:
            return JSONResponse(
                {"ok": False, "errorMessage": "Tham số key không được để trống."},
                status_code=422,
            )
        try:
            clean_k.encode("latin-1")
        except (UnicodeEncodeError, UnicodeError):
            return JSONResponse(
                {"ok": False, "errorMessage": "Tham số key chứa ký tự không hợp lệ."},
                status_code=422,
            )
        for idx, k in enumerate(keys, 1):
            if k == clean_k or mask_key(k) == clean_k:
                raw_key = k
                target_idx = idx
                break
        if not raw_key:
            raw_key = clean_k
            target_idx = 1
    else:
        if keys:
            raw_key = keys[0]
            target_idx = 1

    if not raw_key:
        return JSONResponse({"ok": False, "errorMessage": "Không tìm thấy API key."}, status_code=400)

    masked = mask_key(raw_key)
    email = _resolve_account_email(None, raw_key, idx=target_idx)

    # High-resolution timing
    t0 = time.perf_counter()
    resp = None
    try:
        resp = requests.post(
            "https://api.buffer.com",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {raw_key}",
            },
            json={"query": "query Ping { account { id email name } }"},
            timeout=10,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latency_ms = max(0.1, round(elapsed_ms, 1))
    except requests.exceptions.ConnectTimeout as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latency_ms = max(0.1, round(elapsed_ms, 1))
        return {
            "ok": False,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "ERROR",
            "httpStatus": 504,
            "latencyMs": latency_ms,
            "quota": None,
            "errorMessage": f"Lỗi kết nối Buffer: ConnectTimeout ({exc})",
            "timestamp": now_ts,
        }
    except (requests.RequestException, UnicodeError, ValueError) as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latency_ms = max(0.1, round(elapsed_ms, 1))
        return {
            "ok": False,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "ERROR",
            "httpStatus": 500,
            "latencyMs": latency_ms,
            "quota": None,
            "errorMessage": f"Lỗi kết nối Buffer: {exc.__class__.__name__} ({exc})",
            "timestamp": now_ts,
        }

    status_code = resp.status_code
    headers = resp.headers

    # Phân tích Rate Limit Headers
    daily_limit = 250
    try:
        daily_limit = int(headers.get("x-ratelimit-limit", 250))
    except (ValueError, TypeError, OverflowError):
        pass

    daily_remaining = 250
    try:
        daily_remaining = int(headers.get("x-ratelimit-remaining", 250))
    except (ValueError, TypeError, OverflowError):
        pass

    burst_limit = 100
    burst_remaining = 100
    ratelimit_header = headers.get("ratelimit", "")
    if ratelimit_header:
        burst_match = re.search(r'100-in-15min";\s*r=(\d+)', ratelimit_header)
        if burst_match:
            burst_remaining = int(burst_match.group(1))
        daily_match = re.search(r'250-in-1day";\s*r=(\d+)', ratelimit_header)
        if daily_match:
            daily_remaining = int(daily_match.group(1))

    retry_after = 0
    try:
        retry_after = int(headers.get("Retry-After", 0))
    except (ValueError, TypeError, OverflowError):
        pass

    reset_ts = now_ts + (retry_after or 86400)
    try:
        if "x-ratelimit-reset" in headers:
            reset_ts = int(headers["x-ratelimit-reset"])
    except (ValueError, TypeError, OverflowError):
        pass

    # Timestamp clamping: bảo vệ chống tràn ngày giờ từ upstream header bất thường
    if not (now_ts <= reset_ts <= now_ts + MAX_COOLDOWN_SEC):
        reset_ts = now_ts + 86400

    reset_time_ict = _safe_format_ict(reset_ts) or format_ict(now_ts)

    if status_code == 200:
        try:
            body = resp.json()
            acc = body.get("data", {}).get("account", {})
            if acc.get("email"):
                email = acc["email"].strip()
                _email_cache[raw_key] = email
                _email_cache[masked] = email
        except Exception:
            pass

        quota_info = {
            "dailyLimit": daily_limit,
            "dailyRemaining": daily_remaining,
            "burstLimit": burst_limit,
            "burstRemaining": burst_remaining,
            "resetTs": reset_ts,
            "resetTimeIct": reset_time_ict,
            "cooldownSeconds": 0,
        }

        _KEY_TELEMETRY[raw_key] = {
            "status": "ACTIVE",
            "cooldown_until": 0,
            "latency_ms": latency_ms,
            "last_ping": now_ts,
            "quota": quota_info,
        }

        return {
            "ok": True,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "ACTIVE",
            "httpStatus": 200,
            "latencyMs": latency_ms,
            "quota": quota_info,
            "errorMessage": None,
            "timestamp": now_ts,
        }

    elif status_code == 429:
        cd_sec = retry_after if retry_after > 0 else 3600
        if cd_sec > MAX_COOLDOWN_SEC:
            cd_sec = MAX_COOLDOWN_SEC
        cooldown_until = now_ts + cd_sec
        quota_info = {
            "dailyLimit": daily_limit,
            "dailyRemaining": 0,
            "burstLimit": burst_limit,
            "burstRemaining": burst_remaining,
            "resetTs": reset_ts,
            "resetTimeIct": reset_time_ict,
            "cooldownSeconds": cd_sec,
        }
        _KEY_TELEMETRY[raw_key] = {
            "status": "COOLDOWN",
            "cooldown_until": cooldown_until,
            "latency_ms": latency_ms,
            "last_ping": now_ts,
            "quota": quota_info,
        }
        return {
            "ok": True,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "COOLDOWN",
            "httpStatus": 429,
            "latencyMs": latency_ms,
            "quota": quota_info,
            "errorMessage": f"Buffer HTTP 429: Too many requests. Thử lại sau {cd_sec}s ({reset_time_ict} ICT).",
            "timestamp": now_ts,
        }

    elif status_code == 401:
        return {
            "ok": False,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "UNAUTHORIZED",
            "httpStatus": 401,
            "latencyMs": latency_ms,
            "quota": None,
            "errorMessage": "Buffer từ chối key (401). Access token is not valid hoặc đã hết hạn.",
            "timestamp": now_ts,
        }

    else:
        return {
            "ok": False,
            "accountIndex": target_idx,
            "email": email,
            "maskedKey": masked,
            "status": "ERROR",
            "httpStatus": status_code,
            "latencyMs": latency_ms,
            "quota": None,
            "errorMessage": f"Buffer trả về mã lỗi {status_code}.",
            "timestamp": now_ts,
        }


@router.get("/api/buffer/ping-key", response_class=JSONResponse)
def ping_buffer_key_get(
    account_index: Optional[int] = Query(None),
    key: Optional[str] = Query(None),
):
    """Đo độ trễ mạng và chẩn đoán trạng thái API key (GET)."""
    return _handle_ping_key(account_index=account_index, key=key)


@router.post("/api/buffer/ping-key", response_class=JSONResponse)
def ping_buffer_key_post(
    account_index: Optional[int] = Query(None),
    key: Optional[str] = Query(None),
    payload: Optional[dict] = Body(None),
):
    """Đo độ trễ mạng và chẩn đoán trạng thái API key (POST)."""
    return _handle_ping_key(account_index=account_index, key=key, payload=payload)


# ============================================================================
# F4: Live Dispatch Feed API (/api/buffer/dispatch-feed)
# ============================================================================

@router.get("/api/buffer/dispatch-feed", response_class=JSONResponse)
def get_dispatch_feed(limit: int = 25):
    """Truy xuất nhật ký các lượt phát hành bài viết Buffer gần nhất từ Database."""
    now_ts = int(time.time())
    bm = get_buffer_manager()
    keys = bm.get_keys()

    # Kẹp giá trị limit từ 1 đến 100
    clamped_limit = max(1, min(100, int(limit)))

    # Tạo map channel_id -> {name, service}
    raw_channels = runtime_settings.get_json("BUFFER_CHANNELS") or []
    if not isinstance(raw_channels, list):
        raw_channels = []
    channel_info_map = {ch.get("id"): ch for ch in raw_channels if isinstance(ch, dict) and ch.get("id")}

    events = []
    with SessionLocal() as db:
        jobs = (
            db.query(Job)
            .filter(Job.platform == "buffer")
            .order_by(Job.id.desc())
            .limit(clamped_limit)
            .all()
        )

        for j in jobs:
            cid = str(j.target_page or "")
            ch_meta = channel_info_map.get(cid, {})
            ch_name = ch_meta.get("name") or cid or "Kênh không xác định"
            service = (ch_meta.get("service") or "facebook").lower()

            # Xác định account sở hữu kênh
            acc_idx = 1
            key_masked = mask_key(keys[0]) if keys else "<none>"
            for idx, raw_k in enumerate(keys, 1):
                fb_chans = _get_fallback_channels_for_account(idx)
                if any(c.get("id") == cid for c in fb_chans):
                    acc_idx = idx
                    key_masked = mask_key(raw_k)
                    break

            # Map status và httpStatus
            err = str(j.last_error or "")
            if j.status == JobStatus.DONE:
                status_str = "DONE"
                http_code = 200
                msg = "Đăng thành công qua Buffer API"
            elif j.status == JobStatus.FAILED:
                status_str = "FAILED"
                if "429" in err:
                    http_code = 429
                    msg = err or "Buffer HTTP 429: Rate limit exceeded"
                elif "first comment" in err.lower() or "plan" in err.lower() or "validation" in err.lower():
                    http_code = 422
                    msg = err
                elif "401" in err or "unauthenticated" in err.lower():
                    http_code = 401
                    msg = err
                else:
                    http_code = 500
                    msg = err or "Lỗi xử lý xuất bản bài viết"
            elif j.status == JobStatus.RUNNING:
                status_str = "RUNNING"
                http_code = 102
                msg = "Đang gửi bài tới Buffer API"
            else:
                status_str = "PENDING"
                http_code = 202
                msg = "Đang chờ phát hành trong hàng đợi"

            event_ts = j.finished_at or j.started_at or j.schedule_ts or j.created_at or now_ts
            events.append(
                {
                    "jobId": j.id,
                    "channelId": cid,
                    "channelName": ch_name,
                    "service": service,
                    "accountIndex": acc_idx,
                    "keyMasked": key_masked,
                    "status": status_str,
                    "httpStatus": http_code,
                    "timeIct": _safe_format_ict(event_ts) or format_ict(now_ts),
                    "timestamp": event_ts,
                    "message": msg,
                    "caption": (j.caption or "")[:400],
                    "postUrl": j.post_url or "",
                }
            )

    return {
        "ok": True,
        "timestamp": now_ts,
        "events": events,
    }


# ============================================================================
# Dashboard HTML View (/buffer-cluster)
# ============================================================================

@router.get("/buffer-cluster", response_class=HTMLResponse)
def render_buffer_cluster(request: Request):
    """Trang giao diện 3D Three.js giám sát cụm tài khoản Buffer."""
    return templates.TemplateResponse("pages/buffer_3d_cluster.html", {"request": request})
