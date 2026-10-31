"""
Bước ``intake`` — đúng một việc: đưa một file vào kho Studio thành ``StudioAsset``.

payload: ``path`` (bắt buộc), ``origin`` (reup/upload/ai/brand), ``kind`` (tự đoán theo đuôi
nếu thiếu), ``source_url``, ``credit``, ``title``, ``viral_material_id``, ``move`` (xoá file gốc
sau khi đưa vào kho — dùng cho file trong hộp thư Studio), ``channel_id``.

Trùng nội dung (sha256) thì dùng lại asset cũ. Riêng reup: asset đó đã có dự án cho kênh này
(hoặc cả hai đều không có kênh) thì dừng — cùng một video bị đưa vào kênh lần hai.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database.models import StudioProject, StudioTask
from app.features.studio import store
from app.features.studio.contracts import StageError, StageResult

_KIND_BY_SUFFIX = {
    **dict.fromkeys((".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"), "video"),
    **dict.fromkeys((".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"), "audio"),
    **dict.fromkeys((".jpg", ".jpeg", ".png", ".webp"), "image"),
}


def kind_for(path: Path) -> str | None:
    return _KIND_BY_SUFFIX.get(path.suffix.lower())


def run(db: Session, task: StudioTask) -> StageResult:
    p = task.payload or {}
    src = Path(str(p.get("path") or ""))
    if not src.is_file():
        raise StageError(f"không thấy file: {src}", retryable=False)
    kind = p.get("kind") or kind_for(src)
    if kind not in ("video", "audio", "image"):
        raise StageError(f"không nhận loại file {src.suffix!r}", retryable=False)
    origin = p.get("origin") or "upload"

    try:
        asset, created = store.add_asset(
            db, src, kind=kind, origin=origin, move=bool(p.get("move")),
            source_url=p.get("source_url"), credit=p.get("credit"), title=p.get("title"),
            viral_material_id=p.get("viral_material_id"),
        )
    except OSError as exc:
        raise StageError(str(exc)) from exc
    if created:
        return StageResult(asset_id=asset.id)
    if origin == "reup":
        seen = db.query(StudioProject.id).filter(
            StudioProject.asset_id == asset.id, StudioProject.channel_id == p.get("channel_id"),
        ).first()
        if seen is not None:
            return StageResult(asset_id=asset.id, stop=True, note=f"trùng asset #{asset.id} (dự án #{seen.id})")
    return StageResult(asset_id=asset.id, note=f"dùng lại asset #{asset.id}")
