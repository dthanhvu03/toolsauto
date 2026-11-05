"""Manifest xuất POC: storyboard + credit + audit."""
from __future__ import annotations

import json
from pathlib import Path

from app.features.studio import paths
from app.features.studio.doc.schema import DocState


def doc_dir(project_id: int) -> Path:
    d = paths.ROOT / "doc" / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(state: DocState, *, project_id: int, output_uri: str | None = None) -> Path:
    folder = doc_dir(project_id)
    credits = []
    timeline = []
    for shot in state.shots:
        entry = {
            "shot_id": shot.shot_id,
            "start_ms": shot.start_ms,
            "end_ms": shot.end_ms,
            "beat_id": shot.beat_id,
            "motion": shot.motion,
            "illustration": bool(shot.selected and shot.selected.illustration),
        }
        if shot.selected:
            entry.update({
                "asset_id": shot.selected.asset_id,
                "source_page": shot.selected.source_page,
                "credit": shot.selected.credit,
                "license": shot.selected.license,
                "rights_status": shot.selected.rights_status.value,
            })
            credits.append({
                "shot_id": shot.shot_id,
                "asset_id": shot.selected.asset_id,
                "provider": shot.selected.provider,
                "author": shot.selected.author,
                "credit": shot.selected.credit,
                "license": shot.selected.license,
                "license_url": shot.selected.license_url,
                "source_page": shot.selected.source_page,
                "seconds": f"{shot.start_ms / 1000:.2f}-{shot.end_ms / 1000:.2f}",
            })
        timeline.append(entry)

    payload = {
        "v": 1,
        "project_id": project_id,
        "audio_asset_id": state.audio_asset_id,
        "duration_ms": state.duration_ms,
        "preview_end_ms": state.preview_end_ms,
        "output_uri": output_uri,
        "beats": [b.model_dump(mode="json") for b in state.beats],
        "timeline": timeline,
        "credits": credits,
        "audit": state.audit,
    }
    path = folder / "storyboard.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
