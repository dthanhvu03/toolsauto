"""
API Studio (ADR-061) cho SPA ``/app/go/studio*`` (PLAN-106 P4).

- Dự án: danh sách / bảng duyệt, chi tiết cho trình edit, lưu spec (render lại), sửa caption / kênh, đổi mẫu,
  duyệt / bỏ; file render + ảnh bìa.
- Nguyên liệu: danh sách asset, upload (``brand``), file + dải khung hình.
- Kênh & mẫu: ``setup.py``.
- Việc: theo dõi một lần upload theo ``parent_id``.
- Lấy từ TikTok (PLAN-113): quét link → chọn → tải & dựng; dự án đăng tay: tải video, «Đã đăng».

Đăng nhập: middleware cookie chung của app chặn trước khi tới đây (cả file video / ảnh).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core.database.models import StudioAsset, StudioChannel, StudioProject, StudioTask, StudioTemplate
from app.core.media import tts
from app.features.studio import editor, entry, progress, setup, source, store

router = APIRouter(prefix="/studio/api", tags=["studio"])

_MEDIA_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4", ".wav": "audio/wav", ".flac": "audio/flac", ".png": "image/png",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _file(path: str | Path, *, cache: bool = False) -> FileResponse:
    p = Path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="không còn file")
    headers = {"Cache-Control": "private, max-age=86400" if cache else "no-cache"}
    return FileResponse(p, media_type=_MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"), headers=headers)


# ── Upload / việc ────────────────────────────────────────────────────────────


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    channel_id: int | None = Form(None),
    template_id: int | None = Form(None),
    brand: bool = Form(False),
    collected: bool = Form(False),
    credit: str = Form(""),
    has_text: bool = Form(False),
    db: Session = Depends(get_db),
) -> dict:
    """
    Video → flow ``upload`` (thành dự án). ``brand=true``: logo / intro / nhạc → chỉ vào kho.
    ``collected``: video sưu tầm (ghi nguồn ``credit``); ``has_text``: đã có chữ sẵn → không đốt phụ đề.
    Không ``channel_id`` = đăng tay (không sang Buffer).
    """
    try:
        task = entry.accept_file(
            db, file.file, file.filename or "", channel_id=channel_id, template_id=template_id, brand=brand,
            collected=collected, credit=credit, has_text=has_text,
        )
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "task_id": task.id, "flow": task.flow}


class ScanBody(BaseModel):
    url: str
    limit: int = 10


class TakeItem(BaseModel):
    url: str
    title: str = ""


class TakeBody(BaseModel):
    items: list[TakeItem]
    channel_id: int | None = None
    template_id: int | None = None
    has_text: bool = False
    hook: str = ""
    voice: str = ""


@router.post("/tiktok/scan")
def tiktok_scan(body: ScanBody, db: Session = Depends(get_db)) -> dict:
    """Chỉ đọc danh sách video (không tải). ``taken``: video đã có trong Studio / đang tải."""
    try:
        items = source.scan(body.url, body.limit)
    except source.SourceError as exc:
        raise _bad(exc) from exc
    taken = entry.taken_urls(db, [i["url"] for i in items])
    return {"items": [{**i, "taken": i["url"] in taken} for i in items]}


@router.post("/tiktok/take")
def tiktok_take(body: TakeBody, db: Session = Depends(get_db)) -> dict:
    try:
        tasks = entry.take_links(
            db, [i.model_dump() for i in body.items], channel_id=body.channel_id, template_id=body.template_id,
            has_text=body.has_text, hook=body.hook, voice=body.voice,
        )
    except ValueError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "count": len(tasks), "task_ids": [t.id for t in tasks]}


@router.get("/jobs")
def jobs(ids: str = Query(""), db: Session = Depends(get_db)) -> dict:
    """Tiến trình từng video (PLAN-114). ``ids=1,2``: chỉ các việc gốc này; trống: đang chạy + xong / lỗi 2 giờ qua."""
    wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:100]
    return progress.jobs(db, ids=wanted or None)


@router.get("/tasks/{task_id}")
def task_status(task_id: int, db: Session = Depends(get_db)) -> dict:
    """Việc này và các bước sau nó (theo ``parent_id``), để web theo dõi một lần upload."""
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="không có việc này")
    chain = [task]
    while len(chain) < 50:
        child = db.query(StudioTask).filter(StudioTask.parent_id == chain[-1].id).first()
        if child is None:
            break
        chain.append(child)
    return {
        "tasks": [
            {"id": t.id, "stage": t.stage, "status": t.status, "attempts": t.attempts, "error": t.error,
             "asset_id": t.asset_id, "project_id": t.project_id}
            for t in chain
        ],
    }


# ── Dự án ────────────────────────────────────────────────────────────────────


def _project_row(p: StudioProject, channels: dict[int, str], ctx: tuple[dict, dict] = ({}, {})) -> dict:
    origins, templates = ctx
    return {
        "id": p.id, "status": p.status, "channel": channels.get(p.channel_id or 0), "channel_id": p.channel_id,
        "caption": p.caption, "hashtags": p.hashtags or [], "duration": p.duration, "error": p.error,
        "viral_material_id": p.viral_material_id, "created_at": p.created_at, "rendered_at": p.rendered_at,
        "approved_at": p.approved_at, "has_video": bool(p.output_path), "parent_project_id": p.parent_project_id,
        "tags": store.techniques(p.spec, p.asset_id, origin=origins.get(p.asset_id), template=templates.get(p.template_id)),
    }


@router.get("/projects")
def projects(
    status: str = Query("", description="một hoặc nhiều trạng thái, cách nhau dấu phẩy"),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(StudioProject)
    wanted = [s.strip().upper() for s in status.split(",") if s.strip()]
    if wanted:
        q = q.filter(StudioProject.status.in_(wanted))
    channels = {c.id: c.name for c in db.query(StudioChannel)}
    rows = q.order_by(StudioProject.id.desc()).limit(limit).all()
    origins = dict(db.query(StudioAsset.id, StudioAsset.origin).filter(StudioAsset.id.in_({p.asset_id for p in rows})).all())
    templates = {t.id: t.name for t in db.query(StudioTemplate).filter(StudioTemplate.id.in_({p.template_id for p in rows}))}
    counts = dict(db.query(StudioProject.status, func.count(StudioProject.id)).group_by(StudioProject.status).all())
    queued = db.query(func.count(StudioTask.id)).filter(StudioTask.status.in_(["QUEUED", "RUNNING"])).scalar() or 0
    return {
        "projects": [_project_row(p, channels, (origins, templates)) for p in rows],
        "counts": {str(k): int(v) for k, v in counts.items()},
        "tasks_pending": int(queued),
    }


@router.get("/projects/{project_id}")
def project_detail(project_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return editor.detail(db, project_id)
    except editor.EditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class SpecBody(BaseModel):
    spec: dict


@router.put("/projects/{project_id}/spec")
def save_spec(project_id: int, body: SpecBody, db: Session = Depends(get_db)) -> dict:
    try:
        task = editor.save_spec(db, project_id, body.spec)
    except editor.EditError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "task_id": task.id}


class MetaBody(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    channel_id: int | None = None


@router.patch("/projects/{project_id}")
def update_meta(project_id: int, body: MetaBody, db: Session = Depends(get_db)) -> dict:
    try:
        editor.update_meta(db, project_id, caption=body.caption, hashtags=body.hashtags, channel_id=body.channel_id)
    except editor.EditError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


class RecomposeBody(BaseModel):
    template_id: int | None = None
    channel_id: int | None = None


@router.post("/projects/{project_id}/recompose")
def recompose(project_id: int, body: RecomposeBody, db: Session = Depends(get_db)) -> dict:
    try:
        task = editor.recompose(db, project_id, template_id=body.template_id, channel_id=body.channel_id)
    except editor.EditError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "task_id": task.id}


class VariantsBody(BaseModel):
    n: int = 3


@router.post("/projects/{project_id}/variants")
def make_variants(project_id: int, body: VariantsBody, db: Session = Depends(get_db)) -> dict:
    try:
        tasks, note = editor.make_variants(db, project_id, body.n)
    except editor.EditError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "task_ids": [t.id for t in tasks], "note": note}


class ApproveBody(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/projects/{project_id}/approve")
def approve(project_id: int, body: ApproveBody, db: Session = Depends(get_db)) -> dict:
    try:
        task = entry.approve(db, project_id, caption=body.caption, hashtags=body.hashtags)
    except entry.ReviewError as exc:
        raise _bad(exc) from exc
    return {"ok": True, "task_id": task.id}


@router.post("/projects/{project_id}/posted")
def mark_posted(project_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        entry.mark_posted(db, project_id)
    except entry.ReviewError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


@router.post("/projects/{project_id}/reject")
def reject(project_id: int, body: RejectBody, db: Session = Depends(get_db)) -> dict:
    try:
        entry.reject(db, project_id, reason=body.reason)
    except entry.ReviewError as exc:
        raise _bad(exc) from exc
    return {"ok": True}


@router.api_route("/projects/{project_id}/video", methods=["GET", "HEAD"])
def project_video(project_id: int, download: bool = Query(False), db: Session = Depends(get_db)) -> FileResponse:
    """``download=1``: tải về máy (đăng tay) với tên ``studio_<id>.mp4``."""
    project = db.get(StudioProject, project_id)
    if project is None or not project.output_path:
        raise HTTPException(status_code=404, detail="chưa có bản render")
    if download and Path(project.output_path).is_file():
        return FileResponse(project.output_path, media_type="video/mp4", filename=f"studio_{project_id}.mp4")
    return _file(project.output_path)


@router.get("/projects/{project_id}/poster.jpg")
def project_poster(project_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        return _file(editor.poster(db, project_id), cache=True)
    except editor.EditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Nguyên liệu ──────────────────────────────────────────────────────────────


@router.get("/assets")
def assets(
    kind: str = Query(""), origin: str = Query(""), limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db),
) -> dict:
    q = db.query(StudioAsset)
    if kind:
        q = q.filter(StudioAsset.kind == kind)
    if origin:
        q = q.filter(StudioAsset.origin == origin)
    return {"assets": [editor.asset_row(a) for a in q.order_by(StudioAsset.id.desc()).limit(limit)]}


@router.api_route("/assets/{asset_id}/file", methods=["GET", "HEAD"])
def asset_file(asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(StudioAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="không có asset")
    return _file(asset.path, cache=True)


@router.get("/assets/{asset_id}/strip.jpg")
def asset_strip(asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    try:
        path, _n = editor.frame_strip(db, asset_id)
    except editor.EditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _file(path, cache=True)


# ── Kênh & mẫu ───────────────────────────────────────────────────────────────


@router.get("/setup")
def setup_overview(db: Session = Depends(get_db)) -> dict:
    return setup.overview(db)


@router.post("/channels")
def create_channel(body: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return setup.channel_row(setup.save_channel(db, body))
    except (setup.SetupError, ValueError, TypeError) as exc:
        raise _bad(exc) from exc


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return setup.channel_row(setup.save_channel(db, body, channel_id))
    except (setup.SetupError, ValueError, TypeError) as exc:
        raise _bad(exc) from exc


@router.get("/voices")
def voices() -> dict:
    found = tts.vieneu_voices()
    return {"online": bool(found), "voices": found}


@router.post("/voices/preview")
def voice_preview(body: dict) -> Response:
    try:
        return Response(content=setup.preview_voice(str(body.get("voice") or "")), media_type="audio/wav")
    except setup.SetupError as exc:
        raise _bad(exc) from exc


@router.post("/templates")
def create_template(body: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return setup.template_row(setup.save_template(db, body))
    except setup.SetupError as exc:
        raise _bad(exc) from exc


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    try:
        return setup.template_row(setup.save_template(db, body, template_id))
    except setup.SetupError as exc:
        raise _bad(exc) from exc
