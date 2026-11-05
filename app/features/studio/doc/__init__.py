"""
ADR-064 / PLAN-156 — bước ``doc_plan``: tạo DocState + StudioProject, dừng chờ người.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database.models import StudioAnalysis, StudioAsset, StudioProject, StudioTask
from app.features.studio import store
from app.features.studio.contracts import ProjectStatus, StageError, StageResult
from app.features.studio.doc import seed
from app.features.studio.doc.schema import DocState
from app.features.studio.doc.service import build_preview_spec, ensure_placeholder_image
from app.features.studio.spec import ProjectSpec


def run(db: Session, task: StudioTask) -> StageResult:
    asset = db.get(StudioAsset, task.asset_id) if task.asset_id else None
    if asset is None:
        raise StageError(f"không có asset #{task.asset_id}", retryable=False)
    if asset.kind != "audio":
        raise StageError(f"audio_doc cần asset audio, nhận {asset.kind}", retryable=False)

    raw = store.analysis(db, asset.id, "doc")
    if raw:
        state = DocState.model_validate(raw)
    else:
        transcript = store.analysis(db, asset.id, "transcript") or {}
        state = seed.build_initial_state(
            audio_asset_id=asset.id,
            duration_ms=int(round(float(asset.duration or 0.0) * 1000)),
            transcript_lines=list(transcript.get("lines") or []),
            lang=transcript.get("lang"),
        )
        db.add(StudioAnalysis(asset_id=asset.id, kind="doc", data=state.model_dump(mode="json")))
        db.commit()

    # Chạy lại (retry / tác vụ lặp) → dùng lại dự án đã tạo, không đẻ dự án trùng.
    existing = db.get(StudioProject, state.project_id) if state.project_id else None
    if existing is not None:
        return StageResult(
            asset_id=asset.id,
            project_id=existing.id,
            stop=True,
            note=f"doc_plan: dùng lại dự án #{existing.id}",
            payload={"doc": True},
        )

    ensure_placeholder_image(db)
    spec: ProjectSpec = build_preview_spec(db, state)
    project = StudioProject(
        channel_id=(task.payload or {}).get("channel_id"),
        template_id=None,
        asset_id=asset.id,
        spec=spec.model_dump(mode="json"),
        status=ProjectStatus.DRAFT,
        caption=(task.payload or {}).get("title") or asset.title,
    )
    db.add(project)
    db.commit()

    state.project_id = project.id
    row = db.query(StudioAnalysis).filter_by(asset_id=asset.id, kind="doc").first()
    if row is not None:
        row.data = state.model_dump(mode="json")
        db.commit()

    return StageResult(
        asset_id=asset.id,
        project_id=project.id,
        stop=True,
        note=f"doc_plan: {len(state.beats)} beats / {len(state.shots)} shots — chờ gắn ảnh",
        payload={"doc": True},
    )
