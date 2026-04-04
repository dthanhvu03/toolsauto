"""
Platform Configuration API
CRUD for: platform_configs, workflow_definitions,
          platform_selectors, cta_templates
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.core import get_db
from app.main_templates import templates
from app.services.workflow_registry import invalidate
import json, time, logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform-config", tags=["platform-config"])


# ─── Page ────────────────────────────────────────────────────────

@router.get("/")
def platform_config_page(request: Request):
    return templates.TemplateResponse(
        "pages/platform_config.html", {"request": request}
    )


# ─── Cache Invalidation ──────────────────────────────────────────

@router.post("/cache/invalidate")
def invalidate_cache():
    from app.services.workflow_registry import invalidate
    invalidate()
    return JSONResponse({"success": True, "message": "Cache cleared"})


# ─── Platform Configs ────────────────────────────────────────────

@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, platform, adapter_class, display_name, "
        "display_emoji, is_active, base_urls, viewport, "
        "media_extensions, created_at "
        "FROM platform_configs ORDER BY platform"
    )).fetchall()
    return [{
        "id": r[0], "platform": r[1], "adapter_class": r[2],
        "display_name": r[3], "display_emoji": r[4],
        "is_active": bool(r[5]),
        "base_urls": json.loads(r[6] or "{}"),
        "viewport": json.loads(r[7] or "{}"),
        "media_extensions": json.loads(r[8] or "[]"),
        "created_at": r[9]
    } for r in rows]


@router.post("/platforms")
def add_platform(payload: dict, db: Session = Depends(get_db)):
    now = int(time.time())
    try:
        db.execute(text("""
            INSERT INTO platform_configs
            (platform, adapter_class, display_name, display_emoji,
             is_active, base_urls, viewport, media_extensions,
             created_at, updated_at)
            VALUES (:platform, :adapter_class, :display_name,
                    :display_emoji, 1, :base_urls, :viewport,
                    :media_extensions, :now, :now)
        """), {
            "platform": payload.get("platform", "").lower(),
            "adapter_class": payload.get("adapter_class", ""),
            "display_name": payload.get("display_name", ""),
            "display_emoji": payload.get("display_emoji", ""),
            "base_urls": json.dumps(payload.get("base_urls", {})),
            "viewport": json.dumps(
                payload.get("viewport", {"width": 1280, "height": 720})
            ),
            "media_extensions": json.dumps(
                payload.get("media_extensions", [])
            ),
            "now": now
        })
        db.commit()
        invalidate()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    fields, params = [], {"id": platform_id, "now": int(time.time())}
    for key in ["display_name", "display_emoji",
                "adapter_class", "is_active"]:
        if key in payload:
            fields.append(f"{key} = :{key}")
            params[key] = payload[key]
    for key in ["base_urls", "viewport", "media_extensions"]:
        if key in payload:
            fields.append(f"{key} = :{key}")
            params[key] = json.dumps(payload[key])
    if not fields:
        return JSONResponse({"error": "Nothing to update"},
                            status_code=400)
    fields.append("updated_at = :now")
    db.execute(
        text(f"UPDATE platform_configs SET "
             f"{', '.join(fields)} WHERE id = :id"), params
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


# ─── Workflow Definitions ────────────────────────────────────────

@router.get("/workflows")
def list_workflows(
    platform: str = "", db: Session = Depends(get_db)
):
    query = ("SELECT id, name, platform, job_type, is_active, "
             "steps, timing_config, retry_config "
             "FROM workflow_definitions WHERE 1=1")
    params = {}
    if platform:
        query += " AND platform = :platform"
        params["platform"] = platform
    query += " ORDER BY platform, job_type"
    rows = db.execute(text(query), params).fetchall()
    return [{
        "id": r[0], "name": r[1], "platform": r[2],
        "job_type": r[3], "is_active": bool(r[4]),
        "steps": json.loads(r[5] or "[]"),
        "timing_config": json.loads(r[6] or "{}"),
        "retry_config": json.loads(r[7] or "{}")
    } for r in rows]


@router.put("/workflows/{workflow_id}/steps")
def update_workflow_steps(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    """Update step order after drag-and-drop."""
    steps = payload.get("steps", [])
    db.execute(text("""
        UPDATE workflow_definitions
        SET steps = :steps, updated_at = :now
        WHERE id = :id
    """), {
        "steps": json.dumps(steps),
        "id": workflow_id,
        "now": int(time.time())
    })
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.put("/workflows/{workflow_id}/timing")
def update_workflow_timing(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    db.execute(text("""
        UPDATE workflow_definitions
        SET timing_config = :timing, updated_at = :now
        WHERE id = :id
    """), {
        "timing": json.dumps(payload.get("timing_config", {})),
        "id": workflow_id,
        "now": int(time.time())
    })
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


# ─── Selectors ───────────────────────────────────────────────────

@router.get("/selectors")
def list_selectors(
    platform: str = "", category: str = "",
    db: Session = Depends(get_db)
):
    query = (
        "SELECT id, platform, category, selector_name, "
        "selector_type, selector_value, locale, priority, "
        "version, is_active, notes, valid_from, valid_until "
        "FROM platform_selectors WHERE 1=1"
    )
    params = {}
    if platform:
        query += " AND platform = :platform"
        params["platform"] = platform
    if category:
        query += " AND category = :category"
        params["category"] = category
    query += " ORDER BY platform, category, priority DESC"
    rows = db.execute(text(query), params).fetchall()
    return [{
        "id": r[0], "platform": r[1], "category": r[2],
        "selector_name": r[3], "selector_type": r[4],
        "selector_value": r[5], "locale": r[6],
        "priority": r[7], "version": r[8],
        "is_active": bool(r[9]), "notes": r[10],
        "valid_from": r[11], "valid_until": r[12]
    } for r in rows]


@router.post("/selectors")
def add_selector(payload: dict, db: Session = Depends(get_db)):
    now = int(time.time())
    try:
        db.execute(text("""
            INSERT INTO platform_selectors
            (platform, category, selector_name, selector_type,
             selector_value, locale, priority, version,
             valid_from, is_active, notes, created_at, updated_at)
            VALUES (:platform, :category, :name, :stype,
                    :value, :locale, :priority, 1,
                    :now, 1, :notes, :now, :now)
        """), {
            "platform": payload.get("platform"),
            "category": payload.get("category"),
            "name": payload.get("selector_name"),
            "stype": payload.get("selector_type", "css"),
            "value": payload.get("selector_value"),
            "locale": payload.get("locale", "*"),
            "priority": payload.get("priority", 0),
            "notes": payload.get("notes", ""),
            "now": now
        })
        db.commit()
        invalidate()
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/selectors/{selector_id}")
def update_selector(
    selector_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    fields, params = [], {"id": selector_id, "now": int(time.time())}
    for key in ["selector_value", "selector_type", "locale",
                "priority", "is_active", "notes",
                "valid_from", "valid_until"]:
        if key in payload:
            fields.append(f"{key} = :{key}")
            params[key] = payload[key]
    fields.append("updated_at = :now")
    db.execute(
        text(f"UPDATE platform_selectors SET "
             f"{', '.join(fields)} WHERE id = :id"), params
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.delete("/selectors/{selector_id}")
def delete_selector(
    selector_id: int, db: Session = Depends(get_db)
):
    db.execute(
        text("DELETE FROM platform_selectors WHERE id = :id"),
        {"id": selector_id}
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.put("/selectors/reorder")
def reorder_selectors(
    payload: dict, db: Session = Depends(get_db)
):
    """
    Bulk update priority after drag-and-drop.
    payload: {"items": [{"id": 1, "priority": 10}, ...]}
    """
    items = payload.get("items", [])
    now = int(time.time())
    for item in items:
        db.execute(text("""
            UPDATE platform_selectors
            SET priority = :priority, updated_at = :now
            WHERE id = :id
        """), {"priority": item["priority"],
               "id": item["id"], "now": now})
    db.commit()
    invalidate()
    return JSONResponse({"success": True, "updated": len(items)})


# ─── CTA Templates ───────────────────────────────────────────────

@router.get("/cta")
def list_cta(
    platform: str = "", db: Session = Depends(get_db)
):
    query = (
        "SELECT id, platform, template, locale, "
        "page_url, niche, priority, is_active "
        "FROM cta_templates WHERE 1=1"
    )
    params = {}
    if platform:
        query += " AND platform = :platform"
        params["platform"] = platform
    query += " ORDER BY platform, priority DESC"
    rows = db.execute(text(query), params).fetchall()
    return [{
        "id": r[0], "platform": r[1], "template": r[2],
        "locale": r[3], "page_url": r[4], "niche": r[5],
        "priority": r[6], "is_active": bool(r[7])
    } for r in rows]


@router.post("/cta")
def add_cta(payload: dict, db: Session = Depends(get_db)):
    now = int(time.time())
    db.execute(text("""
        INSERT INTO cta_templates
        (platform, template, locale, page_url, niche,
         priority, is_active, created_at)
        VALUES (:platform, :template, :locale, :page_url,
                :niche, :priority, 1, :now)
    """), {
        "platform": payload.get("platform"),
        "template": payload.get("template"),
        "locale": payload.get("locale", "vi"),
        "page_url": payload.get("page_url"),
        "niche": payload.get("niche"),
        "priority": payload.get("priority", 0),
        "now": now
    })
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.delete("/cta/{cta_id}")
def delete_cta(cta_id: int, db: Session = Depends(get_db)):
    db.execute(
        text("DELETE FROM cta_templates WHERE id = :id"),
        {"id": cta_id}
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.put("/cta/reorder")
def reorder_cta(payload: dict, db: Session = Depends(get_db)):
    """Bulk update priority after drag-and-drop."""
    items = payload.get("items", [])
    now = int(time.time())
    for item in items:
        db.execute(text("""
            UPDATE cta_templates
            SET priority = :priority
            WHERE id = :id
        """), {"priority": item["priority"], "id": item["id"]})
    db.commit()
    invalidate()
    return JSONResponse({"success": True})
