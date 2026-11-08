"""
Bước ``render`` — đúng một việc: spec của dự án → một file mp4.

Ghi ra file tạm rồi mới đổi tên, nên không bao giờ có file dở dang mang tên thật. Thư mục làm việc
(ASS, chữ) xoá trong ``finally``.

Video toàn ảnh tĩnh nhiều cảnh (Audio→Doc, PLAN-157): mỗi input ffmpeg mở cùng lúc tốn ~40 MB, bài 9 phút
~80 cảnh vượt RAM máy. Quá ``studio.segment_render_over`` cảnh → dựng từng cảnh thành clip câm, ghép bằng concat
(không mã hoá lại), rồi lượt cuối chỉ còn 1 input hình + tiếng + phụ đề.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.core.database.models import StudioAsset, StudioProject, StudioTask
from app.core.media import ffmpeg_path
from app.features.studio import paths, store
from app.features.studio.contracts import ProjectStatus, StageError, StageResult
from app.features.studio.render import encoder
from app.features.studio.render.graph import Media, SpecError, build
from app.features.studio.spec import Clip, ProjectSpec

FONT_FILE = "BeVietnamPro-Bold.ttf"
SLIDES_ASSET = -1  # id giả cho file ghép các cảnh ảnh (không phải asset trong DB)
logger = logging.getLogger(__name__)


def segment_over(db: Session | None = None) -> int:
    return runtime_settings.get_int("studio.segment_render_over", 12, db=db)


def segmented(spec: ProjectSpec, media: dict[int, Media], over: int) -> bool:
    """Toàn ảnh tĩnh (không tiếng riêng từng clip) và nhiều hơn ``over`` clip."""
    return (
        over > 0 and len(spec.clips) > over
        and all(media[c.asset].kind == "image" and not c.audio for c in spec.clips)
    )


def _render_slides(
    spec: ProjectSpec, media: dict[int, Media], work: Path, *, ffmpeg: str, enc: str, nice: list[str],
) -> tuple[Path, float]:
    """Từng clip ảnh → mp4 câm cùng thông số, ghép bằng concat demuxer (copy). Trả (file ghép, tổng giây)."""
    seg_dir = work / "slides"
    seg_dir.mkdir()
    canvas = spec.canvas.model_copy(update={"lut": None})  # tông màu áp ở lượt cuối
    parts: list[Path] = []
    total = 0.0
    for i, clip in enumerate(spec.clips):
        one = ProjectSpec(canvas=canvas, clips=[clip], motion=spec.motion)
        out = seg_dir / f"s{i:04d}.mp4"
        try:
            plan = build(
                one, media, output=str(out), workdir=str(seg_dir),
                font_file=str(paths.fonts_dir() / FONT_FILE), fonts_dir=str(paths.fonts_dir()),
                ffmpeg=ffmpeg, encoder=enc,
            )
        except SpecError as exc:
            raise StageError(str(exc), retryable=False) from exc
        proc = subprocess.run(nice + plan.argv, capture_output=True, text=True, timeout=max(120, int(plan.duration * 20)))
        if proc.returncode != 0:
            raise _SlideError(enc, proc.stderr or "")
        parts.append(out)
        total += plan.duration
    listing = seg_dir / "list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = work / "slides.mp4"
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(joined)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise StageError(f"ghép cảnh lỗi: {(proc.stderr or '').strip()[-800:]}")
    for p in parts:
        p.unlink(missing_ok=True)
    return joined, total


class _SlideError(Exception):
    def __init__(self, enc: str, stderr: str):
        super().__init__(stderr[-1500:])
        self.enc, self.stderr = enc, stderr


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


_GPU_ERRORS = ("nvenc", "cuda", "openencodesession", "no capable devices", "nvcuvid", "nvidia")


def _gpu_error(stderr: str | None) -> bool:
    """Lỗi do GPU / NVENC thật — lỗi khác (vd tiếng NaN) không được tắt NVENC cho cả worker (PLAN-119)."""
    text = (stderr or "").lower()
    return any(k in text for k in _GPU_ERRORS)


def run(db: Session, task: StudioTask) -> StageResult:
    project = db.get(StudioProject, task.project_id) if task.project_id else None
    if project is None:
        raise StageError(f"không có dự án #{task.project_id}", retryable=False)
    if project.status == ProjectStatus.REJECTED:  # anh bỏ lúc còn trong hàng: không render, không đè trạng thái
        return StageResult(project_id=project.id, stop=True, note="dự án đã bỏ")
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

    lut_file = None
    if spec.canvas.lut:
        candidate = paths.luts_dir() / spec.canvas.lut
        lut_file = str(candidate) if candidate.is_file() else None  # thiếu LUT: render không nhuộm, không hỏng

    project.status = ProjectStatus.RENDERING
    project.error = None
    db.commit()

    final = paths.renders_dir() / f"project_{project.id}.mp4"
    tmp = final.with_suffix(".tmp.mp4")
    work = paths.work_dir() / f"p{project.id}-{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True)
    ffmpeg = ffmpeg_path.ffmpeg_bin()
    used = encoder.pick(ffmpeg)
    nice = ["nice", "-n", "19"] if shutil.which("nice") else []
    render_spec, render_media, note_mode = spec, media, ""
    try:
        if segmented(spec, media, segment_over(db)):
            try:
                slides, total = _render_slides(spec, media, work, ffmpeg=ffmpeg, enc=used, nice=nice)
            except _SlideError as exc:
                if not (exc.enc == encoder.NVENC and _gpu_error(exc.stderr)):
                    raise StageError(f"ffmpeg lỗi khi dựng cảnh: {str(exc).strip()}") from exc
                logger.warning("[STUDIO] NVENC lỗi khi dựng cảnh dự án #%s, làm lại bằng CPU", project.id)
                encoder.mark_failed()
                used = encoder.X264
                shutil.rmtree(work / "slides", ignore_errors=True)
                try:
                    slides, total = _render_slides(spec, media, work, ffmpeg=ffmpeg, enc=used, nice=nice)
                except _SlideError as exc2:
                    raise StageError(f"ffmpeg lỗi khi dựng cảnh: {str(exc2).strip()}") from exc2
            render_media = {**media, SLIDES_ASSET: Media(path=str(slides), kind="video", duration=total, has_audio=False)}
            render_spec = spec.model_copy(update={"clips": [Clip(asset=SLIDES_ASSET, start=0.0, end=total)]})
            note_mode = f" · dựng theo {len(spec.clips)} cảnh"

        def plan_for(enc: str):
            try:
                return build(
                    render_spec, render_media, output=str(tmp), workdir=str(work),
                    font_file=str(paths.fonts_dir() / FONT_FILE), fonts_dir=str(paths.fonts_dir()),
                    transcripts=transcripts, lut_file=lut_file, ffmpeg=ffmpeg, encoder=enc,
                )
            except SpecError as exc:
                raise StageError(str(exc), retryable=False) from exc

        plan = plan_for(used)
        for file_path, content in plan.files.items():
            Path(file_path).write_text(content, encoding="utf-8")
        timeout = max(600, int(plan.duration * 20))
        proc = subprocess.run(nice + plan.argv, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 and used == encoder.NVENC and _gpu_error(proc.stderr):  # GPU hỏng → làm lại bằng CPU
            logger.warning("[STUDIO] NVENC lỗi ở dự án #%s, render lại bằng CPU: %s", project.id, (proc.stderr or "")[-300:])
            encoder.mark_failed()
            used = encoder.X264
            proc = subprocess.run(nice + plan_for(used).argv, capture_output=True, text=True, timeout=timeout)
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
    note = f"{duration:.1f}s · {'GPU' if used == encoder.NVENC else 'CPU'}{note_mode}"
    if spec.canvas.lut and not lut_file:
        note += f" · không thấy LUT {spec.canvas.lut}, bỏ qua"
    return StageResult(project_id=project.id, note=note)
