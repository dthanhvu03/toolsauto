"""Router cung cấp API trạng thái cụm tài khoản Buffer và Dashboard 3D Three.js.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.constants import JobStatus
from app.core.database.core import SessionLocal
from app.core.database.models import Job
from app.features.buffer.manager import get_buffer_manager, mask_key
from app.features.buffer.when import format_ict

logger = logging.getLogger(__name__)

router = APIRouter(tags=["buffer-cluster"])
templates = Jinja2Templates(directory="app/templates")

KNOWN_EMAILS: dict[str, str] = {
    "AnD91BQ36HvaKzLUkQA3RS1j2NS_5GLd_VgJ85lABTm": "lamtruong0978@gmail.com",
    "RZX2FwqWTNrsayj3HzLj5EfCbqTaaUCJJDmf9pZPVmg": "thanhvu08103@gmail.com",
    "ZVsPJXyHKDoOmJ0LTLr-CA-izBv_2qcwTDRGkMh1QO5": "dthanhvu08103@gmail.com",
}

# Cache email đã đọc từ Buffer GraphQL (TTL 24h)
_email_cache: dict[str, str] = dict(KNOWN_EMAILS)


def _resolve_account_email(client: Any, key: str) -> str:
    """Lấy email từ cache hoặc query Buffer GraphQL."""
    if key in _email_cache:
        return _email_cache[key]
    try:
        res = client.execute("query { account { email name } }")
        acc = res.get("account") or {}
        email = (acc.get("email") or "").strip()
        if email:
            _email_cache[key] = email
            return email
    except Exception:
        pass
    return KNOWN_EMAILS.get(key, "chua_xac_dinh@buffer.com")


@router.get("/api/buffer/cluster-status", response_class=JSONResponse)
def get_cluster_status():
    """Trả về dữ liệu thời gian thực của toàn bộ cụm tài khoản Buffer và các kênh."""
    bm = get_buffer_manager()
    clients = bm.get_clients()
    now_ts = int(time.time())

    accounts_data = []
    total_channels_count = 0
    total_queued_count = 0
    active_accounts_count = 0

    with SessionLocal() as db:
        for idx, client in enumerate(clients, 1):
            key = getattr(client, "_key", "")
            masked = mask_key(key)
            email = _resolve_account_email(client, key)

            cooldown_until = getattr(client, "_cooldown_until", 0)
            remaining_cd = max(0, int(cooldown_until - now_ts))
            status = "ACTIVE" if remaining_cd == 0 else "COOLDOWN"

            client_channels = []
            try:
                orgs = client.organizations()
                for org in orgs:
                    channels = client.channels(org.get("id", ""))
                    for ch in channels:
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

                        next_time_str = format_ict(next_job.schedule_ts) if next_job and next_job.schedule_ts else None

                        total_queued_count += pending_cnt
                        client_channels.append(
                            {
                                "id": cid,
                                "name": ch.get("name") or cid,
                                "service": (ch.get("service") or "facebook").lower(),
                                "pendingCount": pending_cnt,
                                "nextPostTime": next_time_str,
                                "nextPostTs": next_job.schedule_ts if next_job else None,
                            }
                        )
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str:
                    status = "COOLDOWN"
                    match = re.search(r"thử lại sau (\d+)s", err_str)
                    if match:
                        remaining_cd = int(match.group(1))
                    elif remaining_cd == 0:
                        remaining_cd = 3600  # Giả định 1h mặc định

            if status == "ACTIVE":
                active_accounts_count += 1

            total_channels_count += len(client_channels)

            accounts_data.append(
                {
                    "index": idx,
                    "name": f"Tài khoản #{idx}",
                    "email": email,
                    "maskedKey": masked,
                    "status": status,
                    "cooldownSeconds": remaining_cd,
                    "channels": client_channels,
                    "channelCount": len(client_channels),
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


@router.get("/buffer-cluster", response_class=HTMLResponse)
def render_buffer_cluster(request: Request):
    """Trang giao diện 3D Three.js giám sát cụm tài khoản Buffer."""
    return templates.TemplateResponse("pages/buffer_3d_cluster.html", {"request": request})
