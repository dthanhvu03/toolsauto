"""
Kiểm định nghĩa DocType và dữ liệu bản ghi — hàm thuần, không đọc DB (``service`` lo phần cần DB: link tồn tại,
unique, bảng con).

Kiểu trường: ``data`` (chữ ngắn ≤ 140), ``text``, ``int``, ``float``, ``check``, ``select`` (``options``), ``date``
(YYYY-MM-DD), ``datetime`` (ISO), ``link`` (``options`` = DocType đích), ``table`` (``options`` = DocType con),
``json``.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

FIELDTYPES = ("data", "text", "int", "float", "check", "select", "date", "datetime", "link", "table", "json")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RESERVED = {"name", "doctype", "id", "created_at", "modified_at"}
FIELD_KEYS = {"fieldname", "label", "fieldtype", "options", "required", "default", "unique", "in_list_view",
              "read_only", "description"}
DATA_MAX = 140


class DocTypeError(ValueError):
    """Định nghĩa / thao tác sai — câu đưa thẳng cho người dùng."""


class DocValidationError(ValueError):
    """Dữ liệu bản ghi sai — ``errors``: {trường: lý do}."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _select_options(raw: Any) -> list[str]:
    items = raw.splitlines() if isinstance(raw, str) else list(raw or [])
    return [str(x).strip() for x in items if str(x).strip()]


def normalize_fields(fields: list[dict]) -> list[dict]:
    """Định nghĩa trường → dạng chuẩn. Sai thì ``DocTypeError`` nói rõ trường nào."""
    if not isinstance(fields, list):
        raise DocTypeError("fields phải là danh sách")
    out: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(fields, 1):
        if not isinstance(raw, dict):
            raise DocTypeError(f"trường thứ {i} không hợp lệ")
        extra = set(raw) - FIELD_KEYS
        if extra:
            raise DocTypeError(f"trường thứ {i}: khoá lạ {sorted(extra)}")
        fn = str(raw.get("fieldname") or "").strip()
        if not NAME_RE.match(fn) or fn in RESERVED:
            raise DocTypeError(f"tên trường «{fn}» không hợp lệ (chữ thường / số / _, bắt đầu bằng chữ, không trùng {sorted(RESERVED)})")
        if fn in seen:
            raise DocTypeError(f"trùng tên trường «{fn}»")
        seen.add(fn)
        ft = str(raw.get("fieldtype") or "data")
        if ft not in FIELDTYPES:
            raise DocTypeError(f"trường «{fn}»: kiểu «{ft}» không có (có: {', '.join(FIELDTYPES)})")
        field = {
            "fieldname": fn,
            "label": str(raw.get("label") or fn).strip()[:120],
            "fieldtype": ft,
            "required": bool(raw.get("required")),
            "unique": bool(raw.get("unique")),
            "in_list_view": bool(raw.get("in_list_view")),
            "read_only": bool(raw.get("read_only")),
            "description": str(raw.get("description") or "").strip()[:300],
        }
        if ft == "select":
            opts = _select_options(raw.get("options"))
            if not opts:
                raise DocTypeError(f"trường «{fn}» (select) cần options")
            field["options"] = opts
        elif ft in ("link", "table"):
            target = str(raw.get("options") or "").strip()
            if not NAME_RE.match(target):
                raise DocTypeError(f"trường «{fn}» ({ft}) cần options = tên DocType đích")
            field["options"] = target
        if ft == "table" and (field["unique"] or raw.get("default") not in (None, "", [])):
            raise DocTypeError(f"trường «{fn}» (table) không có unique / default")
        default = raw.get("default")
        if not _empty(default):
            try:
                field["default"] = coerce(field, default)
            except DocTypeError as exc:
                raise DocTypeError(f"trường «{fn}»: default sai — {exc}") from exc
        out.append(field)
    return out


def coerce(field: dict, value: Any) -> Any:
    """Ép ``value`` về kiểu của trường. Sai thì ``DocTypeError`` (câu ngắn)."""
    ft = field["fieldtype"]
    if _empty(value):
        return [] if ft == "table" else None
    try:
        if ft == "data":
            text = str(value).strip()
            if len(text) > DATA_MAX:
                raise DocTypeError(f"dài quá {DATA_MAX} ký tự")
            return text
        if ft == "text":
            return str(value)
        if ft == "int":
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise DocTypeError("phải là số nguyên")
            return int(str(value).strip()) if isinstance(value, str) else int(value)
        if ft == "float":
            if isinstance(value, bool):
                raise DocTypeError("phải là số")
            return float(value)
        if ft == "check":
            if isinstance(value, str):
                if value.strip().lower() in ("1", "true", "yes", "on", "có"):
                    return True
                if value.strip().lower() in ("0", "false", "no", "off", "không"):
                    return False
                raise DocTypeError("phải là có / không")
            return bool(value)
        if ft == "select":
            text = str(value).strip()
            if text not in field["options"]:
                raise DocTypeError(f"phải là một trong {field['options']}")
            return text
        if ft == "date":
            return date.fromisoformat(str(value).strip()[:10]).isoformat()
        if ft == "datetime":
            return datetime.fromisoformat(str(value).strip()).isoformat(timespec="seconds")
        if ft == "link":
            return str(value).strip()
        if ft == "table":
            if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
                raise DocTypeError("phải là danh sách dòng")
            return value
        if ft == "json":
            data = json.loads(value) if isinstance(value, str) else value
            json.dumps(data)
            return data
    except DocTypeError:
        raise
    except (TypeError, ValueError) as exc:
        raise DocTypeError(f"sai kiểu {ft}") from exc
    raise DocTypeError(f"kiểu {ft} không có")


def validate_data(fields: list[dict], data: dict) -> dict:
    """
    Dữ liệu gửi lên → dữ liệu sạch theo định nghĩa: ép kiểu, default, bắt buộc. Trường lạ → lỗi. Không kiểm link / unique /
    nội dung bảng con (cần DB — ``service``).
    """
    if not isinstance(data, dict):
        raise DocValidationError({"_": "dữ liệu phải là object"})
    known = {f["fieldname"]: f for f in fields}
    errors = {k: "trường không có trong DocType" for k in data if k not in known}
    clean: dict[str, Any] = {}
    for fn, field in known.items():
        value = data.get(fn, field.get("default"))
        try:
            value = coerce(field, value)
        except DocTypeError as exc:
            errors[fn] = str(exc)
            continue
        if field["required"] and _empty(value):
            errors[fn] = "bắt buộc"
            continue
        clean[fn] = value
    if errors:
        raise DocValidationError(errors)
    return clean
