"""API logic POC: load/save DocState, gắn ảnh, dựng ProjectSpec preview, quyền."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import BinaryIO

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database.models import StudioAnalysis, StudioAsset, StudioProject
from app.features.studio import paths, store
from app.features.studio.contracts import ProjectStatus
from app.features.studio.doc.manifest import write_manifest
from app.features.studio.doc.rights import check_export
from app.features.studio.doc.schema import DocState, ImageRef, RightsStatus, Shot, TranscriptSeg
from app.features.studio.doc.seed import lines_to_segments
from app.features.studio.spec import (
    Audio,
    AudioTrack,
    Canvas,
    Clip,
    ProjectSpec,
    SubLine,
    Subtitles,
)

FIXTURES = paths.ROOT / "fixtures"
PLACEHOLDER_NAME = "placeholder_illustration.png"
_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".webp"}


class DocError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def ensure_placeholder_image(db: Session) -> StudioAsset:
    src = FIXTURES / PLACEHOLDER_NAME
    if not src.is_file():
        raise DocError(f"thiếu fixture {src}")
    asset, _ = store.add_asset(
        db, src, kind="image", origin="brand", move=False,
        title="POC placeholder illustration", credit="internal-placeholder",
        width=1280, height=720,
    )
    if asset.duration is None:
        asset.duration = 0.0
        db.commit()
    return asset


def get_state(db: Session, project_id: int) -> tuple[StudioProject, DocState]:
    project = db.get(StudioProject, project_id)
    if project is None or not project.asset_id:
        raise DocError(f"không có dự án doc #{project_id}")
    raw = store.analysis(db, project.asset_id, "doc")
    if not raw:
        raise DocError(f"dự án #{project_id} chưa có DocState")
    return project, DocState.model_validate(raw)


def save_state(db: Session, asset_id: int, state: DocState) -> DocState:
    row = db.query(StudioAnalysis).filter_by(asset_id=asset_id, kind="doc").first()
    data = state.model_dump(mode="json")
    if row is None:
        db.add(StudioAnalysis(asset_id=asset_id, kind="doc", data=data))
    else:
        row.data = data
    db.commit()
    return state


def _audit(state: DocState, action: str, **extra) -> None:
    state.audit.append({"action": action, "ts": int(time.time()), **extra})


def detail(db: Session, project_id: int) -> dict:
    project, state = get_state(db, project_id)
    gate = check_export(state)
    audio = db.get(StudioAsset, state.audio_asset_id)
    return {
        "project": {
            "id": project.id,
            "status": project.status,
            "caption": project.caption,
            "duration": project.duration,
            "error": project.error,
            "has_video": bool(project.output_path and Path(project.output_path).is_file()),
            "output_path": project.output_path,
            "editable": project.status in {
                ProjectStatus.DRAFT, ProjectStatus.RENDERED, ProjectStatus.REVIEW, ProjectStatus.FAILED,
            },
        },
        "doc": state.model_dump(mode="json"),
        "audio": {
            "id": audio.id if audio else None,
            "title": audio.title if audio else None,
            "duration": audio.duration if audio else None,
            "path_exists": bool(audio and Path(audio.path).is_file()),
        },
        "rights_gate": {
            "ok": gate.ok,
            "blockers": gate.blockers,
            "missing_images": gate.missing_images,
            "can_export": gate.ok,
        },
    }


def update_transcript(db: Session, project_id: int, segments: list[dict]) -> dict:
    project, state = get_state(db, project_id)
    out: list[TranscriptSeg] = []
    for raw in segments:
        out.append(_checked(TranscriptSeg, {
            "start_ms": raw.get("start_ms"),
            "end_ms": raw.get("end_ms"),
            "raw_text": str(raw.get("raw_text") or ""),
            "reviewed_text": str(raw.get("reviewed_text") or raw.get("raw_text") or ""),
        }, "đoạn transcript"))
    state.transcript = out
    _audit(state, "transcript_edit", n=len(out))
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def _shot_index(state: DocState, shot_id: str) -> int:
    for i, s in enumerate(state.shots):
        if s.shot_id == shot_id:
            return i
    raise DocError(f"không có shot {shot_id}")


def _checked(model, data: dict, what: str):
    """Kiểm qua schema trước khi ghi — giá trị sai không được lọt vào DocState (lưu rồi sẽ không mở lại được)."""
    try:
        return model.model_validate(data)
    except (ValidationError, ValueError, TypeError) as exc:
        raise DocError(f"{what} không hợp lệ: {exc}") from exc


def update_shot(db: Session, project_id: int, shot_id: str, patch: dict) -> dict:
    project, state = get_state(db, project_id)
    idx = _shot_index(state, shot_id)
    data = state.shots[idx].model_dump()
    if patch.get("motion") is not None:
        data["motion"] = patch["motion"]
    if "narration" in patch:
        data["narration"] = str(patch["narration"] or "")
    for key in ("start_ms", "end_ms"):
        if key in patch:
            data[key] = patch[key]
    shot = _checked(Shot, data, f"shot {shot_id}")
    if shot.end_ms <= shot.start_ms:
        raise DocError("end_ms phải lớn hơn start_ms")
    state.shots[idx] = shot
    _audit(state, "shot_edit", shot_id=shot_id)
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def attach_image(
    db: Session,
    project_id: int,
    shot_id: str,
    stream: BinaryIO,
    filename: str,
    *,
    source_page: str = "",
    credit: str = "",
    license: str = "",
    rights_status: str = RightsStatus.UNKNOWN.value,
    illustration: bool = False,
    proof_note: str = "",
) -> dict:
    project, state = get_state(db, project_id)
    shot = state.shots[_shot_index(state, shot_id)]
    suffix = Path(filename or "").suffix.lower()
    if suffix not in _IMAGE_SUFFIX:
        raise DocError(f"cần file ảnh, nhận {suffix or '(không đuôi)'}")
    try:  # kiểm trước khi ghi file / tạo asset — tránh asset mồ côi
        status = RightsStatus(rights_status)
    except ValueError as exc:
        raise DocError(f"rights_status không hợp lệ: {rights_status}") from exc
    dest = paths.inbox_dir() / f"docimg-{project_id}-{shot_id}-{int(time.time())}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(stream, out, length=1024 * 1024)
    asset, _ = store.add_asset(
        db, dest, kind="image", origin="upload", move=True,
        title=Path(filename).stem[:200], credit=(credit or None),
        source_url=source_page or None,
    )
    shot.selected = ImageRef(
        asset_id=asset.id,
        source_page=source_page[:500],
        credit=credit[:255],
        license=license[:255],
        rights_status=status,
        illustration=bool(illustration),
        proof_note=proof_note[:500],
    )
    shot.status = "HAS_IMAGE"
    _audit(state, "attach_image", shot_id=shot_id, asset_id=asset.id, rights=status.value)
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def set_shot_rights(db: Session, project_id: int, shot_id: str, patch: dict) -> dict:
    project, state = get_state(db, project_id)
    shot = state.shots[_shot_index(state, shot_id)]
    if shot.selected is None:
        raise DocError(f"shot {shot_id} chưa có ảnh")
    data = shot.selected.model_dump()
    if "rights_status" in patch:
        data["rights_status"] = patch["rights_status"]
    for key, limit in (("license", 255), ("credit", 255), ("source_page", 500), ("proof_note", 500)):
        if key in patch:
            data[key] = str(patch[key] or "")[:limit]
    if "illustration" in patch:
        data["illustration"] = bool(patch["illustration"])
    shot.selected = _checked(ImageRef, data, f"quyền ảnh {shot_id}")
    if shot.selected.rights_status in (RightsStatus.APPROVED, RightsStatus.RIGHTS_VERIFIED):
        shot.status = "APPROVED"
    _audit(state, "rights_edit", shot_id=shot_id, rights=shot.selected.rights_status.value)
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def build_preview_spec(db: Session, state: DocState) -> ProjectSpec:
    """Chỉ các shot trong cửa sổ preview có ảnh; audio master không đổi tốc độ."""
    end_ms = min(state.preview_end_ms, state.duration_ms or state.preview_end_ms)
    clips: list[Clip] = []
    sub_lines: list[SubLine] = []
    cursor = 0.0
    for shot in state.shots:
        if shot.start_ms >= end_ms:
            break
        shot_end = min(shot.end_ms, end_ms)
        if shot_end <= shot.start_ms:
            continue
        if shot.selected is None:
            img = ensure_placeholder_image(db)
            asset_id = img.id
            motion = "static"
        else:
            asset_id = shot.selected.asset_id
            motion = shot.motion
        dur = (shot_end - shot.start_ms) / 1000.0
        clips.append(Clip(asset=asset_id, start=0.0, end=dur, motion=motion))  # type: ignore[arg-type]
        text = shot.narration.strip()
        if not text:
            # lấy reviewed transcript giao với khoảng shot
            parts = [
                s.reviewed_text for s in state.transcript
                if s.end_ms > shot.start_ms and s.start_ms < shot_end and s.reviewed_text.strip()
            ]
            text = " ".join(parts)[:180]
        if text:
            sub_lines.append(SubLine(start=cursor, end=cursor + dur, text=text))
        cursor += dur
    if not clips:
        img = ensure_placeholder_image(db)
        clips = [Clip(asset=img.id, start=0.0, end=min(30.0, end_ms / 1000.0), motion="static")]
    return ProjectSpec(
        canvas=Canvas(w=1920, h=1080, fps=30, fit="crop"),
        clips=clips,
        audio=Audio(
            original=0.0,
            tracks=[AudioTrack(asset=state.audio_asset_id, volume=1.0, start=0.0)],
        ),
        subtitles=Subtitles(enabled=bool(sub_lines), source="lines", lines=sub_lines, font_size=48, margin_v=80),
        credit="audio-doc-poc",
    )


def prepare_preview(db: Session, project_id: int, *, require_rights: bool = True) -> dict:
    """
    Kiểm quyền (nếu bật), ghi ProjectSpec + manifest. Caller (entry/router) xếp flow ``rerender``.
    Không import pipeline — tuân ADR-061 import-linter.
    """
    project, state = get_state(db, project_id)
    gate = check_export(state)
    if require_rights and not gate.ok:
        raise DocError("không render được: " + "; ".join(gate.blockers[:8]))
    spec = build_preview_spec(db, state)
    project.spec = spec.model_dump(mode="json")
    project.status = ProjectStatus.DRAFT
    project.error = None
    db.commit()
    manifest = write_manifest(state, project_id=project.id)
    _audit(state, "preview_prepared", require_rights=require_rights, manifest=str(manifest))
    save_state(db, project.asset_id, state)
    return {
        "ok": True,
        "project_id": project.id,
        "rights_ok": gate.ok,
        "blockers": gate.blockers,
        "manifest": str(manifest),
    }


def sync_transcript_from_analysis(db: Session, asset_id: int) -> None:
    """Sau analyze: nếu DocState đã có thì bổ sung transcript nếu đang trống."""
    raw = store.analysis(db, asset_id, "doc")
    if not raw:
        return
    state = DocState.model_validate(raw)
    if state.transcript:
        return
    transcript = store.analysis(db, asset_id, "transcript") or {}
    state.transcript = lines_to_segments(list(transcript.get("lines") or []))
    state.language = transcript.get("lang") or state.language
    save_state(db, asset_id, state)
