"""JSON API for React Settings UI — wraps runtime_settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database.core import get_db
from app.core import settings as runtime_settings
from app.platform.settings_api.mapper import build_values_payload, list_field_metas, section_slug

router = APIRouter(prefix="/api/settings", tags=["settings-api"])


@router.get("/metadata")
def get_settings_metadata():
    return {"fields": list_field_metas()}


@router.get("/values")
def get_settings_values(db: Session = Depends(get_db)):
    return build_values_payload(db)


@router.patch("/sections/{section}")
def patch_settings_section(
    section: str,
    body: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Partial update. `section` is a slug for client grouping;
    only keys present in body are written. Unknown keys → 400.
    """
    updated_by = request.client.host if request.client else None
    updated: list[str] = []
    errors: dict[str, str] = {}

    for key, raw in body.items():
        spec = runtime_settings.SETTINGS.get(key)
        if not spec or runtime_settings.is_studio_only(spec):
            errors[key] = "Unknown setting"
            continue
        if spec.env_only:
            errors[key] = "Environment-locked"
            continue
        if section_slug(spec.section) != section:
            errors[key] = f"Key belongs to section {section_slug(spec.section)}"
            continue
        if spec.is_secret and (raw is None or str(raw).strip() == ""):
            continue
        try:
            runtime_settings.upsert_setting(
                db, key=key, raw_value="" if raw is None else str(raw), updated_by=updated_by
            )
            updated.append(key)
        except ValueError as e:
            errors[key] = str(e)
        except Exception as e:
            errors[key] = str(e)

    if errors and not updated:
        return JSONResponse({"errors": errors}, status_code=400)

    if updated:
        runtime_settings.load_runtime_settings_into_process(db)

    values_out = build_values_payload(db)
    patched_values = {
        k: values_out["values"].get(k)
        for k in updated
        if k in values_out["values"]
    }
    return {
        "updated": updated,
        "values": patched_values,
        "errors": errors or None,
    }


@router.post("/test/{test_id}")
def test_settings_connection(test_id: str, body: dict[str, Any] | None = None):
    """Lightweight connectivity checks for Integrations."""
    body = body or {}
    if test_id == "tikwm_ping":
        import time
        import urllib.request

        import app.config as config

        overrides = (body.get("overrides") or {}) if isinstance(body, dict) else {}
        base = str(overrides.get("TIKWM_API_BASE") or getattr(config, "TIKWM_API_BASE", "")).rstrip(
            "/"
        )
        if not base:
            return {"ok": False, "message": "TIKWM_API_BASE is empty"}
        url = base + "/"
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": "toolsauto-settings"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                _ = resp.read(64)
                status = resp.status
            ms = int((time.perf_counter() - t0) * 1000)
            return {"ok": True, "latencyMs": ms, "message": f"HTTP {status}"}
        except Exception as e:
            return {"ok": False, "message": str(e)[:200]}
    return JSONResponse({"ok": False, "message": f"Unknown test id: {test_id}"}, status_code=404)
