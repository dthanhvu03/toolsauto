"""
Logic Audio→Doc: DocState, sửa cảnh / transcript, gắn ảnh (tải lên hoặc chọn từ internet), quyền, dựng ProjectSpec.

Tham số đọc từ ``DocConfig`` (Cài đặt vận hành → Studio — Audio→Doc) — không hardcode ở đây (PLAN-157).
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import BinaryIO

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database.models import StudioAnalysis, StudioAsset, StudioProject
from app.features.studio import paths, store
from app.features.studio.contracts import ProjectStatus
from app.features.studio.doc import config as doc_config
from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.images import download, licenses
from app.features.studio.doc.images import search as image_search
from app.features.studio.doc.manifest import write_manifest
from app.features.studio.doc.rights import allowed, check_export
from app.features.studio.doc.schema import DocState, ImageRef, RightsStatus, Shot, TranscriptSeg
from app.features.studio.spec import (
    Audio,
    AudioTrack,
    Canvas,
    Clip,
    KenBurns,
    ProjectSpec,
    SubLine,
    Subtitles,
)

PLACEHOLDER_NAME = "placeholder_illustration.png"
_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".webp"}  # ảnh pipeline ffmpeg đọc được


class DocError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def ensure_placeholder_image(db: Session) -> StudioAsset:
    src = paths.ROOT / "fixtures" / PLACEHOLDER_NAME
    if not src.is_file():
        raise DocError(f"thiếu ảnh nền tạm {src}")
    asset, _ = store.add_asset(
        db, src, kind="image", origin="brand", move=False,
        title="Ảnh nền tạm (chưa có ảnh)", credit="internal-placeholder",
    )
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


def window_ms(state: DocState, cfg: DocConfig) -> int:
    return doc_config.window_end_ms(cfg, state.duration_ms)


def detail(db: Session, project_id: int) -> dict:
    project, state = get_state(db, project_id)
    cfg = doc_config.load(db)
    gate = check_export(state, cfg, end_ms=window_ms(state, cfg))
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
            "window_end_ms": window_ms(state, cfg),
        },
        "config": doc_config.public(cfg),
    }


def _checked(model, data: dict, what: str):
    """Kiểm qua schema trước khi ghi — giá trị sai không được lọt vào DocState (lưu rồi sẽ không mở lại được)."""
    try:
        return model.model_validate(data)
    except (ValidationError, ValueError, TypeError) as exc:
        raise DocError(f"{what} không hợp lệ: {exc}") from exc


def _shot_index(state: DocState, shot_id: str) -> int:
    for i, s in enumerate(state.shots):
        if s.shot_id == shot_id:
            return i
    raise DocError(f"không có shot {shot_id}")


def _clean_keywords(raw: object) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        raise DocError("keywords phải là danh sách chữ")
    return [str(k).strip()[:80] for k in raw if str(k).strip()][:8]


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


def update_shot(db: Session, project_id: int, shot_id: str, patch: dict) -> dict:
    project, state = get_state(db, project_id)
    idx = _shot_index(state, shot_id)
    data = state.shots[idx].model_dump()
    if patch.get("motion") is not None:
        data["motion"] = patch["motion"]
    if "narration" in patch:
        data["narration"] = str(patch["narration"] or "")
    if "keywords" in patch:
        data["keywords"] = _clean_keywords(patch["keywords"])
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


def _image_status(ref: ImageRef, cfg: DocConfig) -> str:
    return "APPROVED" if ref.rights_status in allowed(cfg) else "HAS_IMAGE"


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
    """Ảnh anh tải lên cho một cảnh."""
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
        provider="upload",
    )
    shot.status = _image_status(shot.selected, doc_config.load(db))
    _audit(state, "attach_image", shot_id=shot_id, asset_id=asset.id, rights=status.value)
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def search_images(
    db: Session, project_id: int, shot_id: str, keywords: object = None, *, http: httpx.Client | None = None,
) -> dict:
    """Tìm ảnh gợi ý cho một cảnh ở các nguồn đang bật; từ khóa đầu tiên là câu tìm. Lưu kết quả vào DocState."""
    project, state = get_state(db, project_id)
    shot = state.shots[_shot_index(state, shot_id)]
    if keywords is not None:
        shot.keywords = _clean_keywords(keywords)
    query = shot.keywords[0] if shot.keywords else ""
    if not query:
        raise DocError("cảnh chưa có từ khóa — gõ từ khóa rồi tìm")
    cfg = doc_config.load(db)
    found, notes = image_search.search(query, cfg, http=http)
    shot.candidates = found
    shot.search_note = "; ".join(notes)
    _audit(state, "image_search", shot_id=shot_id, query=query, n=len(found))
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def pick_image(
    db: Session, project_id: int, shot_id: str, index: int, *, http: httpx.Client | None = None,
) -> dict:
    """Tải ảnh gợi ý thứ ``index`` về, gắn vào cảnh; quyền tự điền theo giấy phép (``doc.auto_verify_licenses``)."""
    project, state = get_state(db, project_id)
    shot = state.shots[_shot_index(state, shot_id)]
    if not 0 <= int(index) < len(shot.candidates):
        raise DocError("không có ảnh gợi ý này — tìm lại")
    cand = shot.candidates[int(index)]
    cfg = doc_config.load(db)
    own = http is None
    http = http or image_search.client(cfg)
    stem = paths.inbox_dir() / f"docweb-{project_id}-{shot_id}-{int(time.time())}"
    try:
        dest = download.fetch(http, cand.image_url, stem, cfg)
    except download.DownloadError as exc:
        raise DocError(str(exc)) from exc
    finally:
        if own:
            http.close()
    asset, _ = store.add_asset(
        db, dest, kind="image", origin="web", move=True,
        title=(cand.title or cand.provider)[:200], credit=(cand.author or cand.provider)[:255],
        source_url=cand.source_page or cand.image_url,
    )
    status = licenses.rights_for(cand.license, cfg)
    proof = f"{cand.provider}: {cand.source_page or cand.image_url}"
    if cand.license_url:
        proof += f" · {cand.license_url}"
    shot.selected = ImageRef(
        asset_id=asset.id,
        source_page=(cand.source_page or cand.image_url)[:500],
        credit=(cand.author or cand.provider)[:255],
        license=cand.license if cand.license != "unknown" else "",
        rights_status=status,
        proof_note=proof[:500] if status == RightsStatus.RIGHTS_VERIFIED else "",
        provider=cand.provider,
        license_url=cand.license_url[:500],
        author=cand.author[:255],
    )
    shot.status = _image_status(shot.selected, cfg)
    _audit(state, "pick_image", shot_id=shot_id, asset_id=asset.id, provider=cand.provider, rights=status.value)
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
    shot.status = _image_status(shot.selected, doc_config.load(db))
    _audit(state, "rights_edit", shot_id=shot_id, rights=shot.selected.rights_status.value)
    save_state(db, project.asset_id, state)
    return detail(db, project_id)


def _sub_lines(state: DocState, end_ms: int, max_chars: int) -> list[SubLine]:
    """Phụ đề bám đúng mốc lời thoại; câu dài hơn ``max_chars`` tách thành nhiều câu chia theo thời gian."""
    out: list[SubLine] = []
    for seg in state.transcript:
        text = (seg.reviewed_text or seg.raw_text).strip()
        start, end = seg.start_ms, min(seg.end_ms, end_ms)
        if not text or end <= start or start >= end_ms:
            continue
        words = text.split()
        parts: list[list[str]] = [[]]
        for w in words:
            if parts[-1] and len(" ".join(parts[-1] + [w])) > max_chars:
                parts.append([])
            parts[-1].append(w)
        total = sum(len(" ".join(p)) for p in parts) or 1
        t = start
        for p in parts:
            piece = " ".join(p)
            span = (end - start) * len(piece) / total
            out.append(SubLine(start=t / 1000.0, end=(t + span) / 1000.0, text=piece))
            t += span
    return out


def build_preview_spec(db: Session, state: DocState, cfg: DocConfig) -> ProjectSpec:
    """
    Cảnh trong cửa sổ dựng → clip ảnh (thiếu ảnh dùng ảnh nền tạm). Audio gốc không đổi tốc độ.
    Cảnh liền nhau dùng cùng một ảnh đứng yên được gộp thành một clip (bớt input ffmpeg với bài dài).
    """
    end_ms = window_ms(state, cfg)
    clips: list[Clip] = []
    for shot in state.shots:
        if shot.start_ms >= end_ms:
            break
        shot_end = min(shot.end_ms, end_ms)
        if shot_end <= shot.start_ms:
            continue
        if shot.selected is None:
            asset_id, motion = ensure_placeholder_image(db).id, "static"
        else:
            asset_id, motion = shot.selected.asset_id, shot.motion
        dur = (shot_end - shot.start_ms) / 1000.0
        last = clips[-1] if clips else None
        if last is not None and last.asset == asset_id and last.motion == "static" and motion == "static":
            clips[-1] = last.model_copy(update={"end": (last.end or 0.0) + dur})
            continue
        clips.append(Clip(asset=asset_id, start=0.0, end=dur, motion=motion))  # type: ignore[arg-type]
    if not clips:
        clips = [Clip(asset=ensure_placeholder_image(db).id, start=0.0, end=max(1.0, end_ms / 1000.0))]
    lines = _sub_lines(state, end_ms, cfg.subtitle_max_chars) if cfg.subtitles else []
    return ProjectSpec(
        canvas=Canvas(w=cfg.width, h=cfg.height, fps=cfg.fps, fit=cfg.fit),  # type: ignore[arg-type]
        clips=clips,
        audio=Audio(original=0.0, tracks=[AudioTrack(asset=state.audio_asset_id, volume=cfg.voice_volume, start=0.0)]),
        subtitles=Subtitles(
            enabled=bool(lines), source="lines", lines=lines,
            font_size=cfg.subtitle_font_size, margin_v=cfg.subtitle_margin_v,
        ),
        credit=cfg.credit or None,
        motion=KenBurns(
            zoom_max=cfg.kb_zoom_max, zoom_per_sec=cfg.kb_zoom_per_sec,
            pan_zoom=cfg.kb_pan_zoom, upscale=cfg.kb_upscale,
        ),
    )


def prepare_preview(db: Session, project_id: int, *, require_rights: bool = True) -> dict:
    """
    Kiểm quyền (nếu bật), ghi ProjectSpec + manifest. Caller (entry) xếp flow ``doc_preview``.
    Không import pipeline — tuân ADR-061 import-linter.
    """
    project, state = get_state(db, project_id)
    cfg = doc_config.load(db)
    state.preview_end_ms = window_ms(state, cfg)
    gate = check_export(state, cfg, end_ms=state.preview_end_ms)
    if require_rights and not gate.ok:
        raise DocError("không render được: " + "; ".join(gate.blockers[:8]))
    try:
        spec = build_preview_spec(db, state, cfg)
    except ValidationError as exc:
        raise DocError(f"cấu hình dựng không hợp lệ: {exc}") from exc
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
