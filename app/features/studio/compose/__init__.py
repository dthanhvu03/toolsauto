"""
Bước ``compose`` — đúng một việc: asset + kênh + mẫu → ``StudioProject`` (DRAFT) có spec.

payload: ``channel_id``, ``template_id`` (thiếu thì lấy mẫu mặc định của kênh, rồi tới ``basic``),
``params`` (ghi đè tham số mẫu cho riêng dự án này). Biến thể A/B: ``parent_project_id`` + ``caption`` / ``hashtags``
của bản gốc (bước caption thấy đã có caption thì không gọi AI).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.features.studio import paths, store
from app.features.studio.compose.templates import TEMPLATES, ComposeInput
from app.features.studio.contracts import ProjectStatus, StageError, StageResult


def run(db: Session, task: StudioTask) -> StageResult:
    asset = db.get(StudioAsset, task.asset_id) if task.asset_id else None
    if asset is None:
        raise StageError(f"không có asset #{task.asset_id}", retryable=False)
    if asset.kind != "video":
        raise StageError(f"asset #{asset.id} là {asset.kind}, mẫu cần video", retryable=False)

    kind, params, template, channel = store.template_for(db, task.payload)
    build = TEMPLATES.get(kind)
    if build is None:
        raise StageError(f"không có mẫu {kind!r}", retryable=False)

    transcript = store.analysis(db, asset.id, "transcript") or {}
    spec = build(
        ComposeInput(
            asset_id=asset.id,
            duration=float(asset.duration or 0.0),
            has_audio=bool(asset.has_audio),
            has_transcript=bool(transcript.get("lines")),
            credit=asset.credit,
            params=params,
            transcript_lang=transcript.get("lang"),
            dub=store.analysis(db, asset.id, "dub"),
            silences=store.analysis(db, asset.id, "silences") or [],
            scenes=store.analysis(db, asset.id, "scenes") or [],
            origin=asset.origin or "upload",
            lut_names=paths.lut_names(),
            intro_asset_id=channel.intro_asset_id if channel else None,
            outro_asset_id=channel.outro_asset_id if channel else None,
            logo_asset_id=channel.logo_asset_id if channel else None,
            show_credit=channel.show_credit if channel else True,
        )
    )
    p = task.payload or {}
    project = StudioProject(
        channel_id=channel.id if channel else None,
        template_id=template.id if template else None,
        asset_id=asset.id,
        spec=spec.model_dump(mode="json"),
        status=ProjectStatus.DRAFT,
        parent_project_id=p.get("parent_project_id"),
        caption=p.get("caption"),
        hashtags=p.get("hashtags"),
    )
    db.add(project)
    db.commit()
    return StageResult(project_id=project.id, note=f"mẫu {kind}")
