"""
Cửa vào Studio (ADR-061): file từ bên ngoài → ``inbox/`` → bắt đầu một flow.

- ``take_reup``: hệ cũ tải + chống trùng xong một video reup; kênh đích đã chuyển sang Studio
  (``studio_channels.take_reup``) thì Studio nhận. Gọi qua hook ``studio.take_reup`` (ADR-007).
- ``accept_file``: upload web.
- ``scan_inbox``: hộp thư Drive ``<DRIVE_ROOT_DIR>/Studio/Inbox/<tên kênh>/`` — worker làn light
  quét định kỳ. Thư mục ``_Kho`` = nguyên liệu (logo, intro, nhạc), không thành dự án.
- ``approve`` / ``reject``: cổng duyệt tay (web, Telegram). Duyệt → flow ``publish`` → Buffer; các bản cùng nhóm
  biến thể chưa sang Buffer thành REJECTED.

File luôn được **chuyển** vào ``inbox/`` trước khi xếp việc: lần quét sau không thấy lại nó, và
intake (``move``) dọn nó sau khi đưa vào kho.
"""
from __future__ import annotations

import logging
import re
import shutil
import time
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.database.models import StudioChannel, StudioProject, StudioTask
from app.core.storage import offsite
from app.features.studio import paths, pipeline, store
from app.features.studio.contracts import ProjectStatus
from app.features.studio.intake import kind_for

logger = logging.getLogger(__name__)

BRAND_FOLDER = "_Kho"
INBOX_MIN_AGE_SEC = 120  # Drive còn đang đồng bộ thì file chưa đủ — chờ file đứng yên 2 phút
_HANDLE_RE = re.compile(r"/@([A-Za-z0-9._-]+)")
_PLATFORM_CREDIT = {"douyin.com": "Douyin", "tiktok.com": "TikTok", "youtube.com": "YouTube", "facebook.com": "Facebook"}


def credit_from_url(url: str | None) -> str | None:
    """``…tiktok.com/@abc/video/1`` → ``@abc``; không có handle → tên nền tảng; không rõ → None."""
    url = str(url or "")
    m = _HANDLE_RE.search(url)
    if m:
        return f"@{m.group(1)}"
    return next((name for domain, name in _PLATFORM_CREDIT.items() if domain in url), None)


def _park(src: Path, prefix: str) -> Path:
    dest = paths.inbox_dir() / f"{prefix}-{uuid.uuid4().hex[:10]}{src.suffix.lower()}"
    shutil.move(str(src), dest)
    return dest


def take_reup(
    db: Session,
    *,
    channel_ids: list[str],
    path: str,
    url: str | None = None,
    title: str | None = None,
    material_id: int | None = None,
) -> bool:
    """
    ``True`` = Studio đã nhận (file đã chuyển đi, hệ cũ dừng xử lý material này).

    Chỉ nhận video có **đúng một** kênh đích và kênh đó bật ``take_reup``: video nhắm nhiều kênh vẫn
    đi đường cũ để không kênh nào bị bỏ sót.
    """
    ids = {str(x).strip() for x in channel_ids or [] if str(x or "").strip()}
    if len(ids) != 1 or not Path(path).is_file():
        return False
    channel = db.query(StudioChannel).filter(
        StudioChannel.buffer_channel_id == next(iter(ids)),
        StudioChannel.take_reup.is_(True),
        StudioChannel.active.is_(True),
    ).first()
    if channel is None:
        return False
    parked = _park(Path(path), f"reup{material_id or 0}")
    pipeline.start(db, "reup", payload={
        "path": str(parked), "origin": "reup", "move": True, "channel_id": channel.id,
        "source_url": url, "credit": credit_from_url(url), "title": title, "viral_material_id": material_id,
    })
    logger.info("[STUDIO] nhận reup material #%s cho kênh %s", material_id, channel.name)
    return True


def accept_file(
    db: Session,
    stream: BinaryIO,
    filename: str,
    *,
    channel_id: int | None = None,
    template_id: int | None = None,
    brand: bool = False,
    collected: bool = False,
    credit: str = "",
    has_text: bool = False,
) -> StudioTask:
    """
    Upload web: ghi luồng vào ``inbox/`` rồi bắt đầu flow ``upload`` (hoặc ``brand``).

    ``collected``: video sưu tầm (của người khác) → origin ``reup``: ghi nguồn ``credit``, không lật / biến thể
    (ADR-061 mục 11). ``has_text``: video đã có chữ / phụ đề sẵn → không đốt thêm phụ đề. Dự án bắt buộc có kênh
    (không thì không duyệt được).
    """
    suffix = Path(filename or "").suffix.lower()
    if kind_for(Path(f"x{suffix}")) is None:
        raise ValueError(f"không nhận loại file {suffix or '(không đuôi)'}")
    if not brand and not channel_id:
        raise ValueError("chọn kênh trước khi đưa video vào (chưa có kênh: thêm ở «Kênh & mẫu»)")
    dest = paths.inbox_dir() / f"upload-{uuid.uuid4().hex[:10]}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(stream, out, length=1024 * 1024)
    origin = "brand" if brand else ("reup" if collected else "upload")
    payload: dict = {"path": str(dest), "origin": origin, "move": True, "title": Path(filename).stem[:200]}
    if not brand:
        payload.update(channel_id=channel_id, template_id=template_id)
        if credit.strip():
            payload["credit"] = credit.strip()[:120]
        if has_text:
            payload["params"] = {"subtitles": False}
    return pipeline.start(db, "brand" if brand else "upload", payload=payload)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").strip().casefold()


def accept_local_file(db: Session, path: str, filename: str, *, channel_hint: str = "") -> dict:
    """
    File đã nằm trên máy (Telegram tải về) → hộp thư → flow ``upload``. ``channel_hint`` (chữ kèm theo
    file) khớp tên / id kênh thì gắn kênh; không khớp thì để trống, gắn trên web trước khi duyệt.
    """
    src = Path(path)
    if kind_for(Path(f"x{Path(filename).suffix}")) != "video":
        raise ValueError(f"Studio chỉ nhận video ({filename})")
    channels = db.query(StudioChannel).filter(StudioChannel.active.is_(True)).all()
    channel = _channel_for_folder(channels, channel_hint) if channel_hint.strip() else None
    parked = _park(src, "tg")
    payload = {"path": str(parked), "origin": "upload", "move": True, "title": Path(filename).stem[:200]}
    if channel is not None:
        payload["channel_id"] = channel.id
    task = pipeline.start(db, "upload", payload=payload)
    note = f" · kênh {channel.name}" if channel else " · chưa gắn kênh (ghi tên kênh kèm file để tự gắn)"
    return {"task_id": task.id, "note": note}


def _channel_for_folder(channels: list[StudioChannel], name: str) -> StudioChannel | None:
    """Tên thư mục = tên kênh (không phân biệt hoa thường, NFC/NFD) hoặc id kênh Buffer."""
    key = _fold(name)
    return next((c for c in channels if key in (_fold(c.name), _fold(c.buffer_channel_id))), None)


def scan_inbox(db: Session, *, root: Path | None = None, now: float | None = None) -> int:
    """Một lượt quét hộp thư Drive. Trả số file đã nhận. Drive tắt / chưa gắn → 0."""
    root = root if root is not None else offsite.get_root()
    inbox = Path(root) / "Studio" / "Inbox" if root else None
    if inbox is None or not inbox.is_dir():
        return 0
    now = time.time() if now is None else now
    channels = db.query(StudioChannel).filter(StudioChannel.active.is_(True)).all()
    taken = 0
    for folder in sorted(p for p in inbox.iterdir() if p.is_dir()):
        brand = folder.name == BRAND_FOLDER
        channel = None if brand else _channel_for_folder(channels, folder.name)
        if not brand and channel is None:
            continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.name.startswith((".", "~")) or kind_for(f) is None:
                continue
            try:
                if now - f.stat().st_mtime < INBOX_MIN_AGE_SEC:
                    continue
                parked = _park(f, "drive")
            except OSError as exc:  # Drive đang khoá file / mất kết nối: lượt sau thử lại
                logger.warning("[STUDIO] hộp thư: chưa lấy được %s: %s", f.name, exc)
                continue
            payload = {"path": str(parked), "origin": "brand" if brand else "upload", "move": True, "title": f.stem[:200]}
            if channel is not None:
                payload["channel_id"] = channel.id
            pipeline.start(db, "brand" if brand else "upload", payload=payload)
            taken += 1
    if taken:
        logger.info("[STUDIO] hộp thư Drive: nhận %s file", taken)
    return taken


class ReviewError(ValueError):
    """Duyệt / bỏ không hợp lệ — thông điệp đưa thẳng cho người duyệt."""


def _reviewable(db: Session, project_id: int) -> StudioProject:
    project = db.get(StudioProject, project_id)
    if project is None:
        raise ReviewError(f"không có dự án #{project_id}")
    if project.status != ProjectStatus.REVIEW:
        raise ReviewError(f"dự án #{project_id} đang {project.status}, không ở chờ duyệt")
    return project


def approve(
    db: Session, project_id: int, *, caption: str | None = None, hashtags: list[str] | None = None,
) -> StudioTask:
    """Duyệt (sửa caption / hashtag cùng lúc nếu có) → APPROVED → flow ``publish``."""
    project = _reviewable(db, project_id)
    if caption is not None:
        project.caption = caption.strip()
    if hashtags is not None:
        project.hashtags = [t if t.startswith("#") else f"#{t}" for t in (x.strip() for x in hashtags) if t]
    if not (project.caption or "").strip():
        raise ReviewError("chưa có caption — viết caption rồi duyệt")
    if not project.channel_id:
        raise ReviewError("dự án chưa gắn kênh")
    project.status = ProjectStatus.APPROVED
    project.approved_at = int(time.time())
    # A/B: chọn 1 bản là xong nhóm — bản khác chưa sang Buffer thành REJECTED (không đăng trùng lên kênh).
    _root, members = store.group_of(db, project)
    for other in members:
        if other.id != project.id and other.status not in (ProjectStatus.APPROVED, ProjectStatus.SCHEDULED, ProjectStatus.POSTED):
            other.status = ProjectStatus.REJECTED
            other.error = f"đã chọn bản #{project.id}"
    db.commit()
    return pipeline.start(db, "publish", project_id=project.id)


def reject(db: Session, project_id: int, *, reason: str = "") -> StudioProject:
    project = _reviewable(db, project_id)
    project.status = ProjectStatus.REJECTED
    project.error = (reason or "").strip()[:500] or None
    db.commit()
    return project

