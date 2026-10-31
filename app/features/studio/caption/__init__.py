"""
Bước ``caption`` — đúng một việc: AI viết caption + hashtag cho video đã render.

Dùng lại ``ContentOrchestrator.generate_caption`` của hệ cũ (6 khung hình + lời thoại → AI), có tên
kênh để AI viết đúng giọng kênh. Dự án đã có caption (render lại sau khi sửa) thì không viết lại.
AI hỏng không làm hỏng dự án: ghi chú lại, người duyệt viết tay.

params của mẫu: ``caption_style`` (mặc định theo cài đặt ``ai.caption_style``), ``caption`` (False
để tắt). payload ``caption: false`` cũng tắt.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.core.orchestrator import ContentOrchestrator
from app.features.studio import store
from app.features.studio.contracts import ProjectStatus, StageError, StageResult

logger = logging.getLogger(__name__)


def _hashtags(raw) -> list[str]:
    out = []
    for tag in raw if isinstance(raw, list) else []:
        tag = re.sub(r"\s+", "", str(tag or ""))
        if tag:
            out.append(tag if tag.startswith("#") else f"#{tag}")
    return out


def run(db: Session, task: StudioTask) -> StageResult:
    project = db.get(StudioProject, task.project_id) if task.project_id else None
    if project is None:
        raise StageError(f"không có dự án #{task.project_id}", retryable=False)
    if project.status == ProjectStatus.REJECTED:
        return StageResult(project_id=project.id, stop=True, note="dự án đã bỏ")
    if (project.caption or "").strip():  # biến thể nhận caption của bản gốc lúc compose
        return StageResult(project_id=project.id, note="đã có caption")
    _kind, params, _template, channel = store.template_for(
        db, {"channel_id": project.channel_id, "template_id": project.template_id},
    )
    if (task.payload or {}).get("caption") is False or params.get("caption") is False:
        return StageResult(project_id=project.id, note="tắt caption")
    if not project.output_path or not Path(project.output_path).is_file():
        raise StageError(f"dự án #{project.id} chưa có file render", retryable=False)

    asset = db.get(StudioAsset, project.asset_id) if project.asset_id else None
    style = params.get("caption_style") or runtime_settings.get_str("ai.caption_style", default="short", db=db) or "short"
    try:
        result = ContentOrchestrator().generate_caption(
            project.output_path,
            style=style,
            context=(asset.title if asset else "") or "",
            page_name=channel.name if channel else "",
        ) or {}
    except Exception as exc:  # AI / Whisper hỏng: không chặn duyệt
        logger.warning("[STUDIO] caption dự án #%s hỏng: %s", project.id, exc)
        return StageResult(project_id=project.id, note=f"AI hỏng ({type(exc).__name__}) — viết tay khi duyệt")

    caption = str(result.get("caption") or "").strip()
    if not caption:
        return StageResult(project_id=project.id, note="AI không trả caption — viết tay khi duyệt")
    project.caption = caption
    project.hashtags = _hashtags(result.get("hashtags"))
    db.commit()
    return StageResult(project_id=project.id, note=f"caption {len(caption)} ký tự")
