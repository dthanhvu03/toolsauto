"""
Báo Telegram khi dự án vào chờ duyệt (PLAN-106 P4): video + caption + nút ✅ Duyệt / 🗑 Bỏ / ✏️ Sửa trên web.

Biến thể A/B (P4.2): không gửi từng bản — bản cuối của lô vào chờ duyệt thì gửi **một** tin liệt kê cả nhóm,
mỗi bản một nút ✅ (duyệt 1 bản là các bản khác thành «Đã bỏ»).

``callback_data``: ``sok:<id>`` (duyệt), ``sno:<id>`` (bỏ) — ``telegram_bot`` nhận nút rồi gọi hook
``studio.approve`` / ``studio.reject``. Nút web chỉ có khi đã đặt ``PUBLIC_BASE_URL`` (https).

Đây là việc phụ của một bước đã commit xong: **không bao giờ raise**.
"""
from __future__ import annotations

import html
import logging

from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.core.database.models import StudioChannel, StudioProject
from app.core.media.thumbnail import telegram_video_within_size_limit
from app.core.notifier.service import NotifierService
from app.features.studio import store
from app.features.studio.contracts import ProjectStatus

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # caption của tin có video


def _mmss(sec: float | None) -> str:
    s = int(round(sec or 0))
    return f"{s // 60}:{s % 60:02d}"


def review_message(project: StudioProject, channel_name: str | None) -> str:
    head = f"🎬 <b>Studio #{project.id}</b> · {html.escape(channel_name or 'chưa gắn kênh')} · {_mmss(project.duration)}"
    caption = (project.caption or "").strip()
    tags = " ".join(project.hashtags or [])
    body = html.escape(caption) if caption else "<i>Chưa có caption — viết trên web rồi duyệt.</i>"
    if tags:
        body += "\n" + html.escape(tags)
    msg = f"{head}\n\n{body}"
    return msg if len(msg) <= CAPTION_LIMIT else msg[: CAPTION_LIMIT - 1] + "…"


def review_buttons(project_id: int, base_url: str = "") -> list[list[dict]]:
    rows = [[
        {"text": "✅ Duyệt", "callback_data": f"sok:{project_id}"},
        {"text": "🗑 Bỏ", "callback_data": f"sno:{project_id}"},
    ]]
    if base_url.startswith("https://"):
        rows.append([{"text": "✏️ Sửa trên web", "url": f"{base_url}/app/go/studio/{project_id}"}])
    return rows


IN_PROGRESS = {ProjectStatus.DRAFT, ProjectStatus.RENDERING, ProjectStatus.RENDERED}


def describe(spec: dict, asset_id: int | None) -> str:
    flip, lut = store.look(spec, asset_id or 0)
    parts = (["lật"] if flip else []) + ([lut.removesuffix(".cube")] if lut else [])
    return " + ".join(parts) or "gốc"


def variants_message(root: StudioProject, ready: list[StudioProject], channel_name: str | None) -> str:
    rows = "\n".join(f"• #{p.id}: {html.escape(describe(p.spec, p.asset_id))}" for p in ready)
    return (
        f"🎬 <b>Studio #{root.id}</b> · {html.escape(channel_name or 'chưa gắn kênh')} — {len(ready)} bản để chọn "
        f"(cùng caption):\n{rows}\n\nDuyệt 1 bản → các bản còn lại tự bỏ."
    )


def variants_buttons(root_id: int, ready: list[StudioProject], base_url: str = "") -> list[list[dict]]:
    ids = [p.id for p in ready]
    rows = [[{"text": f"✅ #{i}", "callback_data": f"sok:{i}"} for i in ids[k:k + 3]] for k in range(0, len(ids), 3)]
    if base_url.startswith("https://"):
        rows.append([{"text": "✏️ Xem trên web", "url": f"{base_url}/app/go/studio/{root_id}"}])
    return rows


def _variants_ready(db: Session, project: StudioProject, base: str) -> None:
    root, members = store.group_of(db, project)
    if any(m.status in IN_PROGRESS for m in members) or store.pending_variants(db, root):
        return  # còn bản đang dựng / chưa tạo — bản cuối sẽ gửi
    ready = [m for m in members if m.status == ProjectStatus.REVIEW]
    if not ready:
        return
    channel = db.get(StudioChannel, root.channel_id) if root.channel_id else None
    NotifierService._broadcast_with_buttons(
        variants_message(root, ready, channel.name if channel else None), variants_buttons(root.id, ready, base),
    )


def review_ready(db: Session, project: StudioProject) -> None:
    try:
        base = (runtime_settings.get_str("PUBLIC_BASE_URL", db=db) or "").strip().rstrip("/")
        if project.parent_project_id:
            _variants_ready(db, project, base)
            return
        channel = db.get(StudioChannel, project.channel_id) if project.channel_id else None
        msg = review_message(project, channel.name if channel else None)
        buttons = review_buttons(project.id, base)
        if project.output_path and telegram_video_within_size_limit(project.output_path):
            NotifierService._broadcast_video(project.output_path, msg, buttons)
        else:
            NotifierService._broadcast_with_buttons(msg + "\n\n(video quá 50 MB — xem trên web)", buttons)
    except Exception as exc:  # thông báo hỏng không được làm hỏng bước duyệt
        logger.warning("[STUDIO] báo Telegram dự án #%s hỏng: %s", getattr(project, "id", "?"), exc)
