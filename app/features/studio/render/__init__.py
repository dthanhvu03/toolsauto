"""
Bước ``render`` — đúng một việc: spec của dự án → một file mp4.

Ghi ra file tạm rồi mới đổi tên, nên không bao giờ có file dở dang mang tên thật. Thư mục làm việc
(ASS, chữ) xoá trong ``finally``.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.core.media import ffmpeg_path
from app.features.studio import paths, store
from app.features.studio.contracts import ProjectStatus, StageError, StageResult
from app.features.studio.render.graph import Media, SpecError, build
from app.features.studio.spec import ProjectSpec

FONT_FILE = "BeVietnamPro-Bold.ttf"


def _validate(path: Path, expect_sec: float) -> float:
    """Thời lượng file ra. Thiếu hình hoặc ngắn hơn nửa thời lượng mong đợi → hỏng."""
    proc = subprocess.run(
        [ffmpeg_path.ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type:format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    out = (proc.stdout or "").split()
    try:
        duration = float(out[-1])
    except (IndexError, ValueError):
        duration = 0.0
    if "video" not in out or duration < expect_sec * 0.5:
        raise StageError(f"file render hỏng (có hình: {'video' in out}, dài {duration:.1f}s / {expect_sec:.1f}s)")
    return duration


def run(db: Session, task: StudioTask) -> StageResult:
    project = db.get(StudioProject, task.project_id) if task.project_id else None
    if project is None:
        raise StageError(f"không có dự án #{task.project_id}", retryable=False)
    try:
        spec = ProjectSpec.model_validate(project.spec)
    except ValidationError as exc:
        raise StageError(f"spec dự án #{project.id} sai: {exc}", retryable=False) from exc

    assets = {a.id: a for a in db.query(StudioAsset).filter(StudioAsset.id.in_(spec.asset_ids()))}
    missing = [a for a in sorted(spec.asset_ids()) if a not in assets or not Path(assets[a].path).is_file()]
    if missing:
        raise StageError(f"thiếu file asset {missing}", retryable=False)
    media = {
        a.id: Media(path=a.path, kind=a.kind, duration=float(a.duration or 0.0), has_audio=bool(a.has_audio))
        for a in assets.values()
    }
    transcripts = {}
    if spec.subtitles.enabled and spec.subtitles.source != "lines":
        transcripts = {c.asset: store.lines_for(db, c.asset, spec.subtitles.source) for c in spec.clips}

    project.status = ProjectStatus.RENDERING
    project.error = None
    db.commit()

    final = paths.renders_dir() / f"project_{project.id}.mp4"
    tmp = final.with_suffix(".tmp.mp4")
    work = paths.work_dir() / f"p{project.id}-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True)
    try:
        try:
            plan = build(
                spec, media, output=str(tmp), workdir=str(work),
                font_file=str(paths.fonts_dir() / FONT_FILE), fonts_dir=str(paths.fonts_dir()),
                transcripts=transcripts, ffmpeg=ffmpeg_path.ffmpeg_bin(),
            )
        except SpecError as exc:
            raise StageError(str(exc), retryable=False) from exc
        for file_path, content in plan.files.items():
            Path(file_path).write_text(content, encoding="utf-8")
        nice = ["nice", "-n", "19"] if shutil.which("nice") else []
        proc = subprocess.run(
            nice + plan.argv, capture_output=True, text=True, timeout=max(600, int(plan.duration * 20)),
        )
        if proc.returncode != 0:
            raise StageError(f"ffmpeg lỗi {proc.returncode}: {(proc.stderr or '').strip()[-1500:]}")
        duration = _validate(tmp, plan.duration)
        tmp.replace(final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        tmp.unlink(missing_ok=True)

    project.output_path = str(final)
    project.duration = duration
    project.rendered_at = int(time.time())
    project.status = ProjectStatus.RENDERED
    db.commit()
    return StageResult(project_id=project.id, note=f"{duration:.1f}s")
