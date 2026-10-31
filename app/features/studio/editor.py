"""
Trình edit v1 (PLAN-106 P4) — các việc trên một dự án đã có. Gọi từ ``router.py``.

- ``detail``: mọi thứ trình edit cần trong một lần gọi (spec, asset, câu phụ đề đã dời theo đoạn cắt).
- ``save_spec``: kiểm spec → lưu → render lại (flow ``rerender``). Đổi đoạn cắt thì bỏ sửa tay phụ đề:
  sửa tay đánh số theo câu đã dời, đoạn cắt đổi là số lệch sang câu khác.
- ``update_meta``: caption / hashtag / kênh — không cần render lại.
- ``recompose``: đổi mẫu → dự án mới từ cùng asset (flow ``recompose``), dự án cũ thành REJECTED.
- ``frame_strip`` / ``poster``: ảnh dải khung hình cho thanh cắt, ảnh bìa cho bảng duyệt (cache theo file).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database.models import StudioAsset, StudioChannel, StudioProject, StudioTask, StudioTemplate
from app.core.media import ffmpeg_path
from app.features.studio import paths, pipeline, store
from app.features.studio.contracts import ProjectStatus
from app.features.studio.render.graph import Media, SpecError, clip_ranges
from app.features.studio.render.subtitles import shift_lines
from app.features.studio.spec import ProjectSpec

# Dự án đã sang Buffer thì không sửa ở đây nữa (publish từ chối đổi bài đã hẹn).
EDITABLE = {ProjectStatus.DRAFT, ProjectStatus.RENDERED, ProjectStatus.REVIEW, ProjectStatus.FAILED, ProjectStatus.REJECTED}
STRIP_FRAMES = 16
STRIP_WIDTH = 120


class EditError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def _project(db: Session, project_id: int) -> StudioProject:
    project = db.get(StudioProject, project_id)
    if project is None:
        raise EditError(f"không có dự án #{project_id}")
    return project


def _media(db: Session, ids: set[int]) -> dict[int, Media]:
    return {
        a.id: Media(path=a.path, kind=a.kind, duration=float(a.duration or 0.0), has_audio=bool(a.has_audio))
        for a in db.query(StudioAsset).filter(StudioAsset.id.in_(ids))
    }


def asset_row(a: StudioAsset) -> dict:
    return {
        "id": a.id, "kind": a.kind, "origin": a.origin, "title": a.title, "credit": a.credit,
        "duration": a.duration, "width": a.width, "height": a.height, "has_audio": a.has_audio,
        "source_url": a.source_url, "created_at": a.created_at,
    }


def subtitle_lines(db: Session, spec: ProjectSpec) -> list[dict]:
    """Câu phụ đề theo giây video ra, **trước** khi áp sửa tay — số thứ tự khớp ``subtitles.edits``."""
    sub = spec.subtitles
    if sub.source == "lines":
        return [line.model_dump() for line in sub.lines]
    try:
        ranges = clip_ranges(spec, _media(db, {c.asset for c in spec.clips}))
    except SpecError:
        return []
    return shift_lines(ranges, {c.asset: store.lines_for(db, c.asset, sub.source) for c in spec.clips})


def detail(db: Session, project_id: int) -> dict:
    project = _project(db, project_id)
    spec = ProjectSpec.model_validate(project.spec)
    asset = db.get(StudioAsset, project.asset_id) if project.asset_id else None
    channel = db.get(StudioChannel, project.channel_id) if project.channel_id else None
    template = db.get(StudioTemplate, project.template_id) if project.template_id else None
    tasks = (
        db.query(StudioTask).filter(StudioTask.project_id == project.id).order_by(StudioTask.id.desc()).limit(10).all()
    )
    return {
        "project": {
            "id": project.id, "status": project.status, "caption": project.caption,
            "hashtags": project.hashtags or [], "duration": project.duration, "error": project.error,
            "rendered_at": project.rendered_at, "approved_at": project.approved_at,
            "viral_material_id": project.viral_material_id, "editable": project.status in EDITABLE,
        },
        "spec": spec.model_dump(mode="json"),
        "asset": asset_row(asset) if asset else None,
        "assets": [asset_row(a) for a in db.query(StudioAsset).filter(StudioAsset.id.in_(spec.asset_ids()))],
        "channel": {"id": channel.id, "name": channel.name} if channel else None,
        "template": {"id": template.id, "name": template.name, "kind": template.kind} if template else None,
        "subtitle_lines": subtitle_lines(db, spec),
        "tasks": [{"id": t.id, "stage": t.stage, "status": t.status, "error": t.error} for t in tasks],
    }


def save_spec(db: Session, project_id: int, raw: dict) -> StudioTask:
    project = _project(db, project_id)
    if project.status not in EDITABLE:
        raise EditError(f"dự án #{project_id} đang {project.status} — đã sang Buffer, không sửa được")
    try:
        spec = ProjectSpec.model_validate(raw)
    except ValidationError as exc:
        raise EditError(f"spec sai: {exc.errors()[0].get('msg')} ({'.'.join(map(str, exc.errors()[0].get('loc', ())))})") from exc
    missing = spec.asset_ids() - {a for (a,) in db.query(StudioAsset.id).filter(StudioAsset.id.in_(spec.asset_ids()))}
    if missing:
        raise EditError(f"spec trỏ tới asset không có: {sorted(missing)}")
    old = ProjectSpec.model_validate(project.spec)
    if [c.model_dump() for c in old.clips] != [c.model_dump() for c in spec.clips] and spec.subtitles.edits == old.subtitles.edits:
        spec.subtitles.edits = {}
    project.spec = spec.model_dump(mode="json")
    project.status = ProjectStatus.DRAFT
    project.error = None
    db.commit()
    return pipeline.start(db, "rerender", project_id=project.id)


def update_meta(
    db: Session, project_id: int, *, caption: str | None = None, hashtags: list[str] | None = None,
    channel_id: int | None = None,
) -> StudioProject:
    project = _project(db, project_id)
    if project.status not in EDITABLE:
        raise EditError(f"dự án #{project_id} đang {project.status} — đã sang Buffer, không sửa được")
    if caption is not None:
        project.caption = caption.strip()
    if hashtags is not None:
        project.hashtags = [t if t.startswith("#") else f"#{t}" for t in (x.strip() for x in hashtags) if t]
    if channel_id is not None:
        if db.get(StudioChannel, channel_id) is None:
            raise EditError(f"không có kênh #{channel_id}")
        project.channel_id = channel_id
    db.commit()
    return project


def recompose(db: Session, project_id: int, *, template_id: int | None, channel_id: int | None) -> StudioTask:
    project = _project(db, project_id)
    if project.status not in EDITABLE:
        raise EditError(f"dự án #{project_id} đang {project.status} — đã sang Buffer, không sửa được")
    if not project.asset_id:
        raise EditError("dự án không có asset gốc")
    project.status = ProjectStatus.REJECTED
    project.error = "đổi mẫu — thay bằng dự án mới"
    db.commit()
    payload = {"channel_id": channel_id or project.channel_id, "template_id": template_id}
    return pipeline.start(db, "recompose", asset_id=project.asset_id, payload=payload)


def _ffmpeg(args: list[str], out: Path) -> Path:
    tmp = out.with_suffix(".tmp.jpg")
    proc = subprocess.run(
        [ffmpeg_path.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args, str(tmp)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise EditError(f"không dựng được ảnh: {(proc.stderr or '').strip()[-200:]}")
    tmp.replace(out)
    return out


def thumbs_dir() -> Path:
    path = paths.ROOT / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frame_strip(db: Session, asset_id: int) -> tuple[Path, int]:
    """Một ảnh ngang ``STRIP_FRAMES`` khung cách đều của asset video. Trả (ảnh, số khung)."""
    asset = db.get(StudioAsset, asset_id)
    if asset is None or asset.kind != "video" or not Path(asset.path).is_file():
        raise EditError(f"asset #{asset_id} không phải video còn file")
    out = thumbs_dir() / f"strip_{asset.sha256[:20]}_{STRIP_FRAMES}.jpg"
    if out.is_file():
        return out, STRIP_FRAMES
    rate = STRIP_FRAMES / max(float(asset.duration or 1.0), 0.1)
    return _ffmpeg(
        ["-i", asset.path, "-vf", f"fps={rate:.5f},scale={STRIP_WIDTH}:-2,tile={STRIP_FRAMES}x1", "-frames:v", "1", "-q:v", "5"],
        out,
    ), STRIP_FRAMES


def poster(db: Session, project_id: int) -> Path:
    """Ảnh bìa bản render (giây 1). Đổi theo ``rendered_at`` nên render lại là ảnh mới."""
    project = _project(db, project_id)
    if not project.output_path or not Path(project.output_path).is_file():
        raise EditError("dự án chưa có bản render")
    out = thumbs_dir() / f"poster_{project.id}_{project.rendered_at or 0}.jpg"
    if out.is_file():
        return out
    for old in thumbs_dir().glob(f"poster_{project.id}_*.jpg"):
        old.unlink(missing_ok=True)
    seek = "1" if float(project.duration or 0) > 1.5 else "0"
    return _ffmpeg(["-ss", seek, "-i", project.output_path, "-vf", "scale=360:-2", "-frames:v", "1", "-q:v", "4"], out)
