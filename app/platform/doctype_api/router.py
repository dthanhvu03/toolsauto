"""
API DocType (PLAN-109) cho SPA ``/app/go/doctype*``.

- ``/api/doctypes``: định nghĩa (danh sách, tạo, sửa, xoá khi rỗng).
- ``/api/doc/{doctype}``: bản ghi (danh sách có tìm, tạo, sửa, xoá khi không bị link) + ``/options`` cho ô chọn link.

Lỗi định nghĩa / thao tác → 400 ``{detail}``; dữ liệu sai → 422 ``{detail, errors: {trường: lý do}}``.
Đăng nhập: middleware cookie chung.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core.doctype import service
from app.core.doctype.schema import FIELDTYPES, DocTypeError, DocValidationError

router = APIRouter(prefix="/api", tags=["doctype"])


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, DocValidationError):
        return JSONResponse({"detail": str(exc), "errors": exc.errors}, status_code=422)
    return JSONResponse({"detail": str(exc)}, status_code=404 if str(exc).startswith("không có") else 400)


# ── Định nghĩa ───────────────────────────────────────────────────────────────


@router.get("/doctypes")
def list_doctypes(db: Session = Depends(get_db)):
    return {"doctypes": service.list_doctypes(db), "fieldtypes": list(FIELDTYPES)}


@router.get("/doctypes/{name}")
def get_doctype(name: str, db: Session = Depends(get_db)):
    try:
        return service.doctype_row(service.get_doctype(db, name))
    except DocTypeError as exc:
        return _error(exc)


@router.post("/doctypes")
def create_doctype(body: dict, db: Session = Depends(get_db)):
    try:
        return service.doctype_row(service.save_doctype(db, body))
    except (DocTypeError, DocValidationError) as exc:
        return _error(exc)


@router.put("/doctypes/{name}")
def update_doctype(name: str, body: dict, db: Session = Depends(get_db)):
    try:
        return service.doctype_row(service.save_doctype(db, body, name))
    except (DocTypeError, DocValidationError) as exc:
        return _error(exc)


@router.delete("/doctypes/{name}")
def delete_doctype(name: str, db: Session = Depends(get_db)):
    try:
        service.delete_doctype(db, name)
    except DocTypeError as exc:
        return _error(exc)
    return {"ok": True}


# ── Bản ghi ──────────────────────────────────────────────────────────────────


@router.get("/doc/{doctype}")
def list_records(
    doctype: str, q: str = Query(""), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        dt = service.get_doctype(db, doctype)
        rows, total = service.list_records(db, doctype, q=q, limit=limit, offset=offset)
    except DocTypeError as exc:
        return _error(exc)
    return {"doctype": service.doctype_row(dt), "records": rows, "total": total}


@router.get("/doc/{doctype}/options")
def link_options(doctype: str, q: str = Query(""), db: Session = Depends(get_db)):
    """Giá trị cho ô chọn ``link`` trỏ tới ``doctype``."""
    try:
        rows, _total = service.list_records(db, doctype, q=q, limit=100)
    except DocTypeError as exc:
        return _error(exc)
    return {"options": [{"name": r["name"], "title": r["title"]} for r in rows]}


@router.get("/doc/{doctype}/{name}")
def get_record(doctype: str, name: str, db: Session = Depends(get_db)):
    try:
        return service.record_row(service.get_record(db, doctype, name))
    except DocTypeError as exc:
        return _error(exc)


@router.post("/doc/{doctype}")
def create_record(doctype: str, body: dict, db: Session = Depends(get_db)):
    try:
        return service.record_row(service.save_record(db, doctype, body))
    except (DocTypeError, DocValidationError) as exc:
        return _error(exc)


@router.put("/doc/{doctype}/{name}")
def update_record(doctype: str, name: str, body: dict, db: Session = Depends(get_db)):
    try:
        return service.record_row(service.save_record(db, doctype, body, name))
    except (DocTypeError, DocValidationError) as exc:
        return _error(exc)


@router.delete("/doc/{doctype}/{name}")
def delete_record(doctype: str, name: str, db: Session = Depends(get_db)):
    try:
        service.delete_record(db, doctype, name)
    except DocTypeError as exc:
        return _error(exc)
    return {"ok": True}
