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
from app.config import MCP_PROXY_PORT
import json, time, logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform-config", tags=["platform-config"])


# ─── MCP Inspector API ───────────────────────────────────────────

@router.post("/mcp-inspector/start")
def start_mcp_inspector(request: Request):
    """Start MCP Inspector via tmux and return the access URL."""
    import subprocess
    import re
    import time

    session_name = "n8n_mcp_inspector_ux"
    mcp_server_port = 6277

    # Step 1: Dọn dẹp/Restart (Giết tmux session cũ nếu có như recommend)
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
    subprocess.run(
        f"fuser -k {MCP_PROXY_PORT}/tcp {mcp_server_port}/tcp",
        shell=True,
        capture_output=True,
    )
    time.sleep(1)

    # Step 2: Khởi tạo session tmux mới (Fixed from review: dùng HOST, CLIENT_PORT, SERVER_PORT và --)
    import os
    import sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    python_exec = sys.executable
    mcp_script = os.path.join(project_root, "mcp_server.py")
    
    cmd = (
        f"cd {project_root} && "
        f"HOST=0.0.0.0 CLIENT_PORT={MCP_PROXY_PORT} SERVER_PORT={mcp_server_port} "
        f"npx -y @modelcontextprotocol/inspector -- {python_exec} {mcp_script}"
    )
    subprocess.run(["tmux", "new", "-d", "-s", session_name, cmd])

    # Step 3: Poll output để lấy token
    auth_token = None
    last_out = ""
    for _ in range(60):
        time.sleep(0.5)
        res = subprocess.run(["tmux", "capture-pane", "-p", "-t", session_name], capture_output=True, text=True)
        out = res.stdout
        last_out = out

        # Parse token chuẩn (nghiêm ngặt theo specs)
        m = re.search(r"MCP_PROXY_AUTH_TOKEN=([a-zA-Z0-9]+)", out)
        if m:
            auth_token = m.group(1)
            break

        m2 = re.search(r"Session token:\s*([a-zA-Z0-9]+)", out)
        if m2:
            auth_token = m2.group(1)
            break

    if not auth_token:
        # Tự động kill nếu lỗi khởi chạy
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
        return JSONResponse(
            {"error": f"Không thể bắt được Auth Token. Dữ liệu log: {last_out[-200:] if last_out else 'Empty log'}"},
            status_code=500
        )

    # Step 4: Trả full absolute URL về Frontend (backend tự giải quyết host)
    host = request.url.hostname or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
        
    url = f"http://{host}:{MCP_PROXY_PORT}/?MCP_PROXY_AUTH_TOKEN={auth_token}"

    return JSONResponse({"success": True, "url": url})


@router.post("/mcp-inspector/stop")
def stop_mcp_inspector():
    import subprocess
    subprocess.run(["tmux", "kill-session", "-t", "n8n_mcp_inspector_ux"], capture_output=True)
    return JSONResponse({"success": True, "message": "Đã ngừng Inspector"})


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
    import os
    now = int(time.time())
    try:
        adapter_class_str = payload.get("adapter_class", "")
        platform_id = payload.get("platform", "").lower()

        # [No-Code] Skip file scaffolding for GenericAdapter — it's data-driven
        is_generic = "generic.adapter.GenericAdapter" in adapter_class_str
        
        # [n8n-lite Phase 3] Auto-scaffold only for custom adapter classes
        if adapter_class_str and platform_id and not is_generic:
            try:
                parts = adapter_class_str.split('.')
                if len(parts) >= 2:
                    class_name = parts[-1]
                    module_path = ".".join(parts[:-1])
                    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
                    file_path = os.path.join(project_root, module_path.replace('.', '/')) + ".py"
                    dir_path = os.path.dirname(file_path)
                    
                    if not os.path.exists(file_path):
                        os.makedirs(dir_path, exist_ok=True)
                        init_path = os.path.join(dir_path, "__init__.py")
                        if not os.path.exists(init_path):
                            with open(init_path, "w") as f:
                                pass
                                
                        template = f'''import logging
from typing import Any
from playwright.sync_api import Playwright, BrowserContext, Page, Locator
from app.adapters.contracts import AdapterInterface, PublishResult
from app.database.models import Job

logger = logging.getLogger(__name__)

class {class_name}(AdapterInterface):
    """
    Auto-generated Scaffolding for the {platform_id.capitalize()} adapter.
    """
    def __init__(self):
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        
    def open_session(self, profile_path: str) -> bool:
        logger.info("{class_name}: Opening session at %s", profile_path)
        # TODO: Implement session recovery
        return False

    def publish(self, job: Job) -> PublishResult:
        logger.info("{class_name}: Attempting to publish job %s", job.id)
        # TODO: Implement upload/post automation
        return PublishResult(ok=False, is_fatal=False, error="Not implemented yet")

    def check_published_state(self, job: Job) -> PublishResult:
        logger.info("{class_name}: Checking footprint for job %s", job.id)
        # TODO: Implement idempotency check
        return PublishResult(ok=False, is_fatal=False, error="Not implemented yet")

    def post_comment(self, post_url: str, comment_text: str) -> PublishResult:
        logger.info("{class_name}: Posting comment to %s", post_url)
        # TODO: Implement comment automation
        return PublishResult(ok=False, is_fatal=False, error="Not implemented yet")

    def close_session(self) -> None:
        logger.info("{class_name}: Closing session")
        if self.page:
            try: self.page.close()
            except Exception: pass
        if self.context:
            try: self.context.close()
            except Exception: pass
        if self.playwright:
            try: self.playwright.stop()
            except Exception: pass
        self.page = None
        self.context = None
        self.playwright = None
'''
                        with open(file_path, "w") as f:
                            f.write(template)
                        logger.info(f"Auto-generated adapter scaffolding at {file_path}")
            except Exception as scaffold_err:
                logger.warning(f"Failed to auto-scaffold adapter for {platform_id}: {scaffold_err}")

        db.execute(text("""
            INSERT INTO platform_configs
            (platform, adapter_class, display_name, display_emoji,
             is_active, base_urls, viewport, media_extensions,
             created_at, updated_at)
            VALUES (:platform, :adapter_class, :display_name,
                    :display_emoji, true, :base_urls, :viewport,
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


@router.post("/workflows")
def create_workflow(payload: dict, db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    platform = (payload.get("platform") or "").strip()
    job_type = (payload.get("job_type") or "POST").strip()

    if not name or not platform:
        return JSONResponse({"error": "Tên workflow và Platform ID là bắt buộc."}, status_code=400)

    # Check duplicate
    exists = db.execute(
        text("SELECT id FROM workflow_definitions WHERE name = :name"),
        {"name": name}
    ).fetchone()
    if exists:
        return JSONResponse({"error": f"Workflow '{name}' đã tồn tại."}, status_code=400)

    now = int(time.time())
    db.execute(text("""
        INSERT INTO workflow_definitions
        (name, platform, job_type, is_active, steps, timing_config, retry_config, created_at, updated_at)
        VALUES (:name, :platform, :job_type, false, '[]', '{}', '{}', :now, :now)
    """), {
        "name": name, "platform": platform, "job_type": job_type, "now": now
    })
    db.commit()
    invalidate()
    return JSONResponse({"success": True, "message": f"Đã tạo workflow '{name}'."})


@router.post("/workflows/{workflow_id}/test")
def test_workflow(workflow_id: int, payload: dict = {}, db: Session = Depends(get_db)):
    """
    Dry-run validation of a workflow.
    Checks: step schema, selector coverage, value sources.
    Does NOT launch a browser.
    """
    from app.services.workflow_registry import WorkflowRegistry

    # Load workflow
    row = db.execute(text(
        "SELECT id, name, platform, job_type, steps, is_active "
        "FROM workflow_definitions WHERE id = :id"
    ), {"id": workflow_id}).fetchone()

    if not row:
        return JSONResponse({"success": False, "error": "Workflow not found"}, 404)

    wf_name = row[1]
    platform = row[2]
    job_type = row[3]
    supplied_steps = payload.get("steps") if payload else None
    raw_steps = supplied_steps if supplied_steps is not None else json.loads(row[4] or "[]")
    is_active = row[5]

    results = []
    overall_ok = True
    warnings = []

    if not is_active:
        warnings.append("Workflow is inactive. Activate before use.")

    VALID_ACTIONS = {"navigate", "click", "fill", "upload_file", "wait", "verify", "check_auth", "legacy"}
    VALID_VALUE_SOURCES = {"job.caption", "job.media_path", "job.post_url", "account.username"}

    for i, raw in enumerate(raw_steps):
        step_result = {"index": i + 1, "checks": []}

        # Parse step
        if isinstance(raw, str):
            step_result["name"] = raw
            step_result["action"] = "legacy"
            step_result["status"] = "pass"
            step_result["checks"].append({
                "check": "format",
                "status": "pass",
                "detail": f"Legacy static step (handled by Custom Adapter)."
            })
            results.append(step_result)
            continue

        name = raw.get("name", "unnamed")
        action = raw.get("action", "unknown")
        step_result["name"] = name
        step_result["action"] = action
        step_ok = True

        # Check action type
        if action not in VALID_ACTIONS:
            step_result["checks"].append({
                "check": "action",
                "status": "fail",
                "detail": f"Unknown action '{action}'. Valid: {', '.join(sorted(VALID_ACTIONS))}"
            })
            step_ok = False
        else:
            step_result["checks"].append({
                "check": "action", "status": "pass", "detail": action
            })

        # Check selector coverage
        selector_keys = raw.get("selector_keys", [])
        if action in ("click", "fill", "upload_file") and not selector_keys:
            step_result["checks"].append({
                "check": "selectors",
                "status": "fail",
                "detail": "No selector_keys provided. Element cannot be found."
            })
            step_ok = False
        elif selector_keys:
            for key in selector_keys:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    cat, sel_name = parts
                    db_selectors = WorkflowRegistry.get_selectors(platform, cat)
                    matching = [s for s in db_selectors if s.selector_name == sel_name]
                    if matching:
                        step_result["checks"].append({
                            "check": f"selector:{key}",
                            "status": "pass",
                            "detail": f"Found {len(matching)} selector(s) in DB"
                        })
                    else:
                        step_result["checks"].append({
                            "check": f"selector:{key}",
                            "status": "warn",
                            "detail": f"No DB selectors for '{key}'. Will rely on heuristic fallback."
                        })
                else:
                    step_result["checks"].append({
                        "check": f"selector:{key}",
                        "status": "warn",
                        "detail": f"Raw selector (no category:name format): '{key}'"
                    })

        # Check value_source
        vs = raw.get("value_source", "")
        if action in ("fill", "upload_file") and not vs:
            step_result["checks"].append({
                "check": "value_source",
                "status": "fail",
                "detail": "No value_source. Field will have nothing to fill/upload."
            })
            step_ok = False
        elif vs:
            if vs.startswith("literal:") or vs in VALID_VALUE_SOURCES:
                step_result["checks"].append({
                    "check": "value_source", "status": "pass", "detail": vs
                })
            else:
                step_result["checks"].append({
                    "check": "value_source",
                    "status": "warn",
                    "detail": f"Unrecognized source '{vs}'. May fail at runtime."
                })

        # Check URL for navigate
        if action == "navigate":
            url = raw.get("url", "")
            url_key = raw.get("url_key", "")
            if not url and not url_key and not vs:
                step_result["checks"].append({
                    "check": "url",
                    "status": "fail",
                    "detail": "Navigate has no url, url_key, or value_source."
                })
                step_ok = False
            elif url_key:
                base_url = WorkflowRegistry.get_base_url(platform, url_key)
                if base_url:
                    step_result["checks"].append({
                        "check": "url", "status": "pass",
                        "detail": f"url_key '{url_key}' -> {base_url}"
                    })
                else:
                    step_result["checks"].append({
                        "check": "url", "status": "warn",
                        "detail": f"url_key '{url_key}' not found in base_urls."
                    })
            else:
                step_result["checks"].append({
                    "check": "url", "status": "pass", "detail": url or vs
                })

        step_result["status"] = "pass" if step_ok else "fail"
        if not step_ok:
            overall_ok = False
        results.append(step_result)

    # Summary
    pass_count = sum(1 for r in results if r["status"] == "pass")
    fail_count = sum(1 for r in results if r["status"] == "fail")
    warn_count = sum(1 for r in results if r["status"] == "warn")

    return JSONResponse({
        "success": True,
        "workflow": wf_name,
        "platform": platform,
        "job_type": job_type,
        "overall": "pass" if overall_ok else "fail",
        "summary": {
            "total": len(results),
            "pass": pass_count,
            "fail": fail_count,
            "warn": warn_count,
        },
        "warnings": warnings,
        "steps": results,
    })


@router.put("/workflows/{workflow_id}/steps")
def update_workflow_steps(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    """Update step list (content + order) after drag-and-drop or inline edit."""
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


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """Delete a workflow definition."""
    db.execute(
        text("DELETE FROM workflow_definitions WHERE id = :id"),
        {"id": workflow_id}
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id: int, db: Session = Depends(get_db)):
    """Delete a platform config."""
    db.execute(
        text("DELETE FROM platform_configs WHERE id = :id"),
        {"id": platform_id}
    )
    db.commit()
    invalidate()
    return JSONResponse({"success": True})


@router.put("/workflows/{workflow_id}/timing")
def update_workflow_timing(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    timing = payload.get("timing_config", {})
    
    # ── [n8n-lite Phase 1 Hardening] Timing Validation ──
    for key, val in timing.items():
        if not isinstance(val, (int, float)) or val < 0:
            return JSONResponse({"error": f"Timing '{key}' phải là số dương."}, status_code=400)
        if val > 300000:
            return JSONResponse({"error": f"Timing '{key}' vượt quá giới hạn cực đại 300000ms (5 phút)."}, status_code=400)
            
    if "upload_settle_wait" in timing and timing["upload_settle_wait"] < 1000:
        return JSONResponse({"error": "upload_settle_wait tối thiểu là 1000ms để đảm bảo render DOM."}, status_code=400)
        
    if "feed_browse_pause" in timing and timing["feed_browse_pause"] < 500:
        return JSONResponse({"error": "feed_browse_pause tối thiểu là 500ms để tránh bị detect boot."}, status_code=400)

    db.execute(text("""
        UPDATE workflow_definitions
        SET timing_config = :timing, updated_at = :now
        WHERE id = :id
    """), {
        "timing": json.dumps(timing),
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
                    :now, true, :notes, :now, :now)
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
                :niche, :priority, true, :now)
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


# ─── Phase 3D: Presets API ────────────────────────────────────────

@router.get("/presets")
def list_presets_api(platform: str = "facebook", job_type: str = "POST"):
    from app.services.workflow_registry import WorkflowRegistry
    return WorkflowRegistry.list_presets(platform, job_type)


@router.post("/presets/apply")
def apply_preset_api(payload: dict):
    from app.services.workflow_registry import WorkflowRegistry
    name = payload.get("name", "")
    msg = WorkflowRegistry.apply_preset(name)
    ok = "activated" in msg
    return JSONResponse({"success": ok, "message": msg})


@router.get("/runtime-config")
def runtime_config_api(platform: str = "facebook", job_type: str = "POST"):
    from app.services.workflow_registry import WorkflowRegistry
    return WorkflowRegistry.get_runtime_snapshot(platform, job_type)


@router.get("/selector-health")
def selector_health_api():
    from app.services.runtime_events import get_enriched_selector_health
    return get_enriched_selector_health()


@router.get("/presets/preview-switch")
def preview_switch_api(
    from_preset: str = "", to_preset: str = "", mode: str = "cache",
    platform: str = "facebook", job_type: str = "POST"
):
    """Compute diff between two presets for impact preview modal."""
    from app.services.workflow_registry import WorkflowRegistry, PRESET_DESCRIPTIONS
    from app.database.core import SessionLocal
    from sqlalchemy import text as sa_text

    db = SessionLocal()
    try:
        nodes_to_query = [to_preset]
        if mode == "db" or not from_preset:
            nodes_to_query.append(from_preset)

        # Tranh duplicate trong query IN (:a, :b) neu tuong tu nhau:
        node_a = nodes_to_query[0]
        node_b = nodes_to_query[1] if len(nodes_to_query) > 1 else node_a

        rows = db.execute(sa_text(
            "SELECT name, steps, timing_config, retry_config "
            "FROM workflow_definitions WHERE name IN (:a, :b)"
        ), {"a": node_a, "b": node_b}).fetchall()

        presets = {}
        for r in rows:
            presets[r[0]] = {
                "name": r[0],
                "steps": json.loads(r[1] or "[]"),
                "timing": json.loads(r[2] or "{}"),
                "retry": json.loads(r[3] or "{}"),
            }

        # Override from_preset bang cache neu dang chay mode cache
        if mode == "cache" and from_preset:
            wf = WorkflowRegistry.get_workflow(platform, job_type)
            if wf and wf.name == from_preset:
                presets[from_preset] = {
                    "name": wf.name,
                    "steps": wf.steps or [],
                    "timing": wf.timing or {},
                    "retry": wf.retry or {}
                }

        if from_preset not in presets or to_preset not in presets:
            return JSONResponse(
                {"error": "Preset not found"}, status_code=404
            )

        f, t = presets[from_preset], presets[to_preset]

        # Step diff
        steps_removed = [s for s in f["steps"] if s not in t["steps"]]
        steps_added = [s for s in t["steps"] if s not in f["steps"]]

        # Timing diff
        all_keys = set(list(f["timing"].keys()) + list(t["timing"].keys()))
        timing_changed = []
        for key in sorted(all_keys):
            fv = f["timing"].get(key)
            tv = t["timing"].get(key)
            if fv != tv:
                pct = None
                if fv and tv and fv != 0:
                    pct = round((tv - fv) / fv * 100)
                timing_changed.append({
                    "key": key,
                    "from": fv,
                    "to": tv,
                    "change_pct": pct,
                })

        # Risk
        risk_messages = []
        if steps_removed:
            risk_messages.append(
                f"{len(steps_removed)} steps se bi SKIP "
                f"({', '.join(steps_removed)})"
            )
        for tc in timing_changed:
            if tc["change_pct"] and tc["change_pct"] <= -40:
                risk_messages.append(
                    f"{tc['key']} giam {abs(tc['change_pct'])}%"
                )

        risk_level = "safe"
        if steps_removed:
            risk_level = "warning"
        if len(steps_removed) >= 2 or any(
            tc["change_pct"] and tc["change_pct"] <= -50
            for tc in timing_changed
        ):
            risk_level = "high"

        return {
            "from": {
                **f, "description": PRESET_DESCRIPTIONS.get(f["name"], "")
            },
            "to": {
                **t, "description": PRESET_DESCRIPTIONS.get(t["name"], "")
            },
            "diff": {
                "steps_added": steps_added,
                "steps_removed": steps_removed,
                "timing_changed": timing_changed,
            },
            "risk_level": risk_level,
            "risk_messages": risk_messages,
        }
    finally:
        db.close()


@router.get("/overview-warnings")
def overview_warnings_api(
    platform: str = "facebook", job_type: str = "POST"
):
    """Compute aggregated warnings for Overview alert banner."""
    from app.services.workflow_registry import (
        WorkflowRegistry, PRESET_DESCRIPTIONS, get_cache_status,
    )
    from app.services.runtime_events import get_enriched_selector_health

    warnings = []

    # 1. Selector health warnings
    health = get_enriched_selector_health()
    failing = health["summary"]["failing"]
    low_rate = health["summary"]["warning"]
    static_heavy = sum(
        1 for i in health["items"]
        if i["last_source"] == "static_fallback"
    )

    if failing >= 3:
        warnings.append({
            "severity": "critical",
            "text": f"{failing} selectors dang fail hoan toan (0% hit rate). "
                    "Worker co the khong hoan thanh job.",
            "link": "selector-health",
        })
    elif failing > 0:
        warnings.append({
            "severity": "warning",
            "text": f"{failing} selector dang fail. Xem Selector Health de xu ly.",
            "link": "selector-health",
        })
    if low_rate > 0:
        warnings.append({
            "severity": "warning",
            "text": f"{low_rate} selector co hit rate thap (<50%).",
            "link": "selector-health",
        })
    if static_heavy >= 2:
        warnings.append({
            "severity": "warning",
            "text": f"{static_heavy} selector dang dung static fallback.",
            "link": "selector-health",
        })

    # 2. Cache warnings
    cache = get_cache_status()
    if cache["is_stale"]:
        age = cache["age_seconds"]
        if age and age > 300:
            warnings.append({
                "severity": "critical",
                "text": f"Cache da cu ({int(age)}s). Config co the khong phan anh thay doi gan day.",
                "link": "cache",
            })
        else:
            warnings.append({
                "severity": "warning",
                "text": "Cache stale. Bam Reload de dong bo config moi nhat.",
                "link": "cache",
            })

    # 3. Preset warnings
    wf = WorkflowRegistry.get_workflow(platform, job_type)
    if not wf:
        warnings.append({
            "severity": "critical",
            "text": f"Khong co preset active cho {platform}:{job_type}. "
                    "Worker se dung config mac dinh.",
            "link": "preset",
        })
    elif wf.name and "fast" in wf.name:
        skipped = [
            s for s in WorkflowRegistry.get_step_resolution(platform, job_type)
            if s["status"] == "SKIP"
        ]
        if skipped:
            warnings.append({
                "severity": "warning",
                "text": f"Preset fast dang active - {len(skipped)} steps bi skip.",
                "link": "preset",
            })
    elif wf.name and "stealth" in wf.name:
        warnings.append({
            "severity": "info",
            "text": "Preset stealth active - delay tang, throughput giam.",
            "link": "preset",
        })

    # 4. Timing warnings
    if wf:
        timing = wf.timing or {}
        for k, v in timing.items():
            if "browse" in k and isinstance(v, (int, float)) and v < 1000:
                warnings.append({
                    "severity": "warning",
                    "text": f"Timing {k} = {v}ms - thap hon nguong khuyen nghi.",
                    "link": "runtime",
                })
            if "settle" in k and isinstance(v, (int, float)) and v < 2000:
                warnings.append({
                    "severity": "warning",
                    "text": f"Timing {k} = {v}ms - co the gay loi DOM chua render.",
                    "link": "runtime",
                })

    # 5. CTA fallback warning
    try:
        cta = WorkflowRegistry.get_cta_templates(platform, locale="vi")
        if cta == ["{link}"]:
            warnings.append({
                "severity": "info",
                "text": "Khong co CTA template tuy chinh, dang dung fallback.",
                "link": "cta",
            })
    except Exception:
        pass

    # Sort by severity
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    warnings.sort(key=lambda w: sev_order.get(w["severity"], 9))

    return {
        "has_critical": any(w["severity"] == "critical" for w in warnings),
        "has_warning": any(w["severity"] == "warning" for w in warnings),
        "total": len(warnings),
        "items": warnings,
    }
