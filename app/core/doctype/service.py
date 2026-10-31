"""
Đọc / ghi DocType và bản ghi (PLAN-109). Feature khác đọc bản ghi qua ``list_records`` / ``get_record``.

Luật giữ dữ liệu: xoá DocType chỉ khi không còn bản ghi và không DocType nào trỏ tới; xoá bản ghi bị chặn khi bản ghi
khác đang ``link`` tới nó. Không bao giờ xoá kéo theo.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database.models import DocRecord, DocType
from app.core.doctype.schema import (
    NAME_RE,
    DocTypeError,
    DocValidationError,
    normalize_fields,
    validate_data,
)


def doctype_row(dt: DocType) -> dict:
    return {
        "name": dt.name, "label": dt.label, "module": dt.module, "description": dt.description,
        "fields": dt.fields or [], "is_child": bool(dt.is_child), "title_field": dt.title_field,
        "naming": dt.naming, "modified_at": dt.modified_at,
    }


def record_row(rec: DocRecord) -> dict:
    return {"name": rec.name, "doctype": rec.doctype, "data": rec.data or {}, "created_at": rec.created_at,
            "modified_at": rec.modified_at}


# ── DocType ──────────────────────────────────────────────────────────────────


def list_doctypes(db: Session) -> list[dict]:
    counts = _record_counts(db)
    return [
        {**doctype_row(dt), "records": counts.get(dt.name, 0)}
        for dt in db.query(DocType).order_by(DocType.module, DocType.label)
    ]


def _record_counts(db: Session) -> dict[str, int]:
    return {d: int(n) for d, n in db.query(DocRecord.doctype, func.count(DocRecord.id)).group_by(DocRecord.doctype)}


def get_doctype(db: Session, name: str) -> DocType:
    dt = db.query(DocType).filter(DocType.name == name).first()
    if dt is None:
        raise DocTypeError(f"không có DocType «{name}»")
    return dt


def save_doctype(db: Session, payload: dict, name: str | None = None) -> DocType:
    """Tạo (``name`` None) hoặc sửa DocType. Không đổi tên được (bản ghi / link đang trỏ theo tên)."""
    fields = normalize_fields(payload.get("fields") or [])
    is_child = bool(payload.get("is_child"))
    for f in fields:
        if f["fieldtype"] in ("link", "table"):
            target = db.query(DocType).filter(DocType.name == f["options"]).first()
            if target is None and f["options"] != (name or payload.get("name")):
                raise DocTypeError(f"trường «{f['fieldname']}»: không có DocType «{f['options']}»")
            if f["fieldtype"] == "table":
                if target is None or not target.is_child:
                    raise DocTypeError(f"trường «{f['fieldname']}»: DocType «{f['options']}» phải là DocType con")
                if is_child:
                    raise DocTypeError("DocType con không chứa bảng con khác")
            if f["fieldtype"] == "link" and target is not None and target.is_child:
                raise DocTypeError(f"trường «{f['fieldname']}»: không link tới DocType con «{f['options']}»")
    names = {f["fieldname"] for f in fields}
    title_field = str(payload.get("title_field") or "").strip() or None
    if title_field and title_field not in names:
        raise DocTypeError(f"title_field «{title_field}» không có trong trường")
    naming = str(payload.get("naming") or "autoincrement").strip()
    if naming != "autoincrement":
        fn = naming.removeprefix("field:")
        if not naming.startswith("field:") or fn not in names:
            raise DocTypeError("naming phải là «autoincrement» hoặc «field:<tên trường>» có trong DocType")
        field = next(f for f in fields if f["fieldname"] == fn)
        if field["fieldtype"] not in ("data", "int", "select", "date"):
            raise DocTypeError(f"không đặt tên bản ghi theo trường kiểu {field['fieldtype']}")

    if name is None:
        new_name = str(payload.get("name") or "").strip()
        if not NAME_RE.match(new_name):
            raise DocTypeError("tên DocType: chữ thường / số / _, bắt đầu bằng chữ (vd hook_library)")
        if db.query(DocType).filter(DocType.name == new_name).first():
            raise DocTypeError(f"DocType «{new_name}» đã có")
        dt = DocType(name=new_name)
        db.add(dt)
    else:
        dt = get_doctype(db, name)
        if payload.get("name") not in (None, "", name):
            raise DocTypeError("không đổi tên DocType được — tạo DocType mới")
        if bool(dt.is_child) != is_child and db.query(DocRecord.id).filter(DocRecord.doctype == name).first():
            raise DocTypeError("DocType đã có bản ghi — không đổi qua lại DocType con")
    dt.label = str(payload.get("label") or dt.name).strip()[:120]
    dt.module = (str(payload.get("module") or "").strip() or None)
    dt.description = (str(payload.get("description") or "").strip() or None)
    dt.fields = fields
    dt.is_child = is_child
    dt.title_field = title_field
    dt.naming = naming
    db.commit()
    return dt


def delete_doctype(db: Session, name: str) -> None:
    dt = get_doctype(db, name)
    if db.query(DocRecord.id).filter(DocRecord.doctype == name).first():
        raise DocTypeError(f"DocType «{name}» còn bản ghi — xoá bản ghi trước (không xoá kéo theo)")
    users = [d.name for d in db.query(DocType) if d.name != name and any(
        f.get("fieldtype") in ("link", "table") and f.get("options") == name for f in d.fields or [])]
    if users:
        raise DocTypeError(f"DocType khác đang trỏ tới «{name}»: {users}")
    db.delete(dt)
    db.commit()


# ── Bản ghi ──────────────────────────────────────────────────────────────────


def _title(dt: DocType, rec: DocRecord) -> str:
    return str((rec.data or {}).get(dt.title_field) or rec.name) if dt.title_field else rec.name


def list_records(
    db: Session, doctype: str, *, q: str = "", filters: dict[str, Any] | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[dict], int]:
    """Bản ghi mới sửa trước. ``q`` tìm trong tên + tiêu đề + trường chữ; ``filters`` so bằng theo trường."""
    dt = get_doctype(db, doctype)
    rows = db.query(DocRecord).filter(DocRecord.doctype == doctype).order_by(DocRecord.modified_at.desc(), DocRecord.id.desc()).all()
    needle = q.strip().casefold()
    text_fields = [f["fieldname"] for f in dt.fields or [] if f["fieldtype"] in ("data", "text", "select", "link")]
    out = []
    for rec in rows:
        data = rec.data or {}
        if filters and any(data.get(k) != v for k, v in filters.items()):
            continue
        if needle and needle not in " ".join([rec.name, *(str(data.get(f) or "") for f in text_fields)]).casefold():
            continue
        out.append({**record_row(rec), "title": _title(dt, rec)})
    return out[offset:offset + limit], len(out)


def get_record(db: Session, doctype: str, name: str) -> DocRecord:
    rec = db.query(DocRecord).filter(DocRecord.doctype == doctype, DocRecord.name == name).first()
    if rec is None:
        raise DocTypeError(f"không có bản ghi «{name}» trong «{doctype}»")
    return rec


def _check_links_and_tables(db: Session, dt: DocType, clean: dict) -> dict:
    errors: dict[str, str] = {}
    for f in dt.fields or []:
        fn, value = f["fieldname"], clean.get(f["fieldname"])
        if f["fieldtype"] == "link" and value not in (None, ""):
            if not db.query(DocRecord.id).filter(DocRecord.doctype == f["options"], DocRecord.name == value).first():
                errors[fn] = f"không có «{value}» trong {f['options']}"
        if f["fieldtype"] == "table" and value:
            child = get_doctype(db, f["options"])
            rows = []
            for i, row in enumerate(value, 1):
                try:
                    row_clean = validate_data(child.fields or [], row)
                    rows.append(_check_links_and_tables(db, child, row_clean))
                except DocValidationError as exc:
                    errors.update({f"{fn}[{i}].{k}": v for k, v in exc.errors.items()})
            clean[fn] = rows
    if errors:
        raise DocValidationError(errors)
    return clean


def _row_errors(db: Session, dt: DocType, data: dict) -> dict[str, str]:
    """Lỗi kiểu / bắt buộc trong các bảng con từ dữ liệu thô — để báo cùng lúc với lỗi trường chính."""
    errors: dict[str, str] = {}
    for f in dt.fields or []:
        rows = data.get(f["fieldname"]) if f["fieldtype"] == "table" else None
        if not isinstance(rows, list):
            continue
        child = db.query(DocType).filter(DocType.name == f["options"]).first()
        for i, row in enumerate(rows, 1):
            try:
                validate_data(child.fields if child else [], row)
            except DocValidationError as exc:
                errors.update({f"{f['fieldname']}[{i}].{k}": v for k, v in exc.errors.items()})
    return errors


def _check_unique(db: Session, dt: DocType, clean: dict, own_id: int | None) -> None:
    unique = [f["fieldname"] for f in dt.fields or [] if f.get("unique")]
    if not unique:
        return
    errors = {}
    for rec in db.query(DocRecord).filter(DocRecord.doctype == dt.name):
        if rec.id == own_id:
            continue
        for fn in unique:
            if clean.get(fn) not in (None, "") and (rec.data or {}).get(fn) == clean.get(fn):
                errors[fn] = f"trùng với bản ghi «{rec.name}»"
    if errors:
        raise DocValidationError(errors)


def _next_name(db: Session, doctype: str) -> str:
    nums = [int(n) for (n,) in db.query(DocRecord.name).filter(DocRecord.doctype == doctype) if str(n).isdigit()]
    return str(max(nums, default=0) + 1)


def save_record(db: Session, doctype: str, data: dict, name: str | None = None) -> DocRecord:
    """Tạo (``name`` None) hoặc sửa bản ghi — kiểm kiểu, bắt buộc, link, unique, bảng con."""
    dt = get_doctype(db, doctype)
    if dt.is_child:
        raise DocTypeError(f"«{doctype}» là DocType con — nhập trong bảng của DocType cha")
    rec = get_record(db, doctype, name) if name is not None else None
    try:
        clean = validate_data(dt.fields or [], data)
    except DocValidationError as exc:  # báo luôn lỗi trong bảng con, khỏi sửa từng đợt
        raise DocValidationError({**exc.errors, **_row_errors(db, dt, data if isinstance(data, dict) else {})}) from exc
    clean = _check_links_and_tables(db, dt, clean)
    _check_unique(db, dt, clean, rec.id if rec else None)
    if dt.naming.startswith("field:"):
        fn = dt.naming.removeprefix("field:")
        new_name = str(clean.get(fn) or "").strip()
        if not new_name:
            raise DocValidationError({fn: "bắt buộc (dùng làm tên bản ghi)"})
        if rec is None and db.query(DocRecord.id).filter(DocRecord.doctype == doctype, DocRecord.name == new_name).first():
            raise DocValidationError({fn: f"đã có bản ghi «{new_name}»"})
        if rec is not None and new_name != rec.name:
            raise DocValidationError({fn: "không đổi được — đây là tên bản ghi"})
    else:
        new_name = rec.name if rec else _next_name(db, doctype)
    if rec is None:
        rec = DocRecord(doctype=doctype, name=new_name)
        db.add(rec)
    rec.data = clean
    db.commit()
    return rec


def _links_to(fields: list[dict], data: dict, target: str, name: str, defs: dict[str, DocType]) -> bool:
    """``data`` (kể cả các dòng bảng con) có trường link nào trỏ tới ``target/name`` không."""
    for f in fields:
        value = data.get(f["fieldname"])
        if f["fieldtype"] == "link" and f.get("options") == target and value == name:
            return True
        if f["fieldtype"] == "table" and value and f.get("options") in defs:
            child = defs[f["options"]].fields or []
            if any(_links_to(child, row, target, name, defs) for row in value if isinstance(row, dict)):
                return True
    return False


def delete_record(db: Session, doctype: str, name: str) -> None:
    rec = get_record(db, doctype, name)
    defs = {d.name: d for d in db.query(DocType)}
    users = [
        f"{other.doctype}/{other.name}"
        for d in defs.values() if not d.is_child
        for other in db.query(DocRecord).filter(DocRecord.doctype == d.name)
        if _links_to(d.fields or [], other.data or {}, doctype, name, defs)
    ]
    if users:
        raise DocTypeError(f"bản ghi khác đang link tới «{name}»: {users[:5]}")
    db.delete(rec)
    db.commit()
