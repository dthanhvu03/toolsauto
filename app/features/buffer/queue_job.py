"""Xếp video reup + caption AI vào hàng chờ Buffer. Gọi từ nút Telegram.

Job platform=buffer, không account. Publisher Facebook chỉ lấy job facebook nên không đụng.
File reup không ghi vào media_path — dọn file job DONE sẽ xóa nhầm bản Buffer còn phải tải.
"""
from __future__ import annotations

import logging

from app.constants import JobStatus
from app.core.database.models import Job, ViralMaterial
from app.core.database.models.base import now_ts
from app.features.buffer.adapter import BufferAdapter

logger = logging.getLogger(__name__)


def _channels() -> list[dict]:
    from app.core import settings as runtime_settings

    data = runtime_settings.get_json("BUFFER_CHANNELS") or []
    rows = []
    for item in data:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            rows.append(
                {
                    "id": str(item["id"]).strip(),
                    "name": str(item.get("name") or item["id"]).strip(),
                }
            )
    return rows


def assign_page(db, material_id: int, channel_id: str) -> tuple[bool, str]:
    """Gắn video với một page Buffer. Không xếp hàng, không gọi API."""
    allowed = {row["id"] for row in _channels()}
    if channel_id not in allowed:
        return False, "Page không có trong danh sách Buffer."
    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    mat.target_page = channel_id
    db.commit()
    return True, f"#{material_id} thuộc {channel_name(channel_id)}."


def channel_name(channel_id: str) -> str:
    for row in _channels():
        if row["id"] == channel_id:
            return row["name"]
    return channel_id


def caption_of(mat) -> str:
    text = (getattr(mat, "ai_caption", None) or "").strip()
    tags = " ".join(getattr(mat, "ai_hashtags_list", None) or [])
    if text and tags:
        return f"{text}\n\n{tags}"
    return text


def queue_reup(db, material_id: int, channel_id: str) -> tuple[bool, str]:
    """Trả (ok, câu tiếng Việt cho Telegram). Không gọi Buffer khi thiếu caption hoặc page lạ."""
    allowed = {row["id"] for row in _channels()}
    if channel_id not in allowed:
        return False, "Page không có trong danh sách Buffer."

    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    text = caption_of(mat)
    if not text:
        return False, "Chưa có caption AI."

    name = channel_name(channel_id)
    if (mat.target_page or "") != channel_id:
        mat.target_page = channel_id
        db.commit()
    existing = (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.viral_material_id == material_id,
            Job.target_page == channel_id,
            Job.status == JobStatus.DONE,
        )
        .first()
    )
    if existing:
        return True, f"Đã xếp vào {name} rồi (job #{existing.id})."

    job = Job(
        platform="buffer",
        caption=text,
        viral_material_id=material_id,
        target_page=channel_id,
        schedule_ts=0,
        status=JobStatus.RUNNING,
        is_approved=True,
        media_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = BufferAdapter().publish(job)
    if not result.ok:
        job.status = JobStatus.FAILED
        job.last_error = (result.error or "Buffer từ chối")[:300]
        job.finished_at = now_ts()
        db.commit()
        logger.warning("[Buffer][job_%s] %s", job.id, job.last_error)
        return False, job.last_error

    job.status = JobStatus.DONE
    job.external_post_id = result.external_post_id
    job.finished_at = now_ts()
    job.last_error = None
    db.commit()
    due = ""
    if isinstance(result.details, dict) and result.details.get("dueAt"):
        due = f" · slot {result.details['dueAt']}"
    return True, f"Đã xếp vào hàng chờ {name}{due}."
