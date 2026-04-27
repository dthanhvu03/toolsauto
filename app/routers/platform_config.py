"""
Platform Configuration API
CRUD for: platform_configs, workflow_definitions,
          platform_selectors, cta_templates
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.main_templates import templates
from app.services.workflow_registry import invalidate
from app.config import MCP_PROXY_PORT
import json, time, logging

from app.services import platform_config_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform-config", tags=["platform-config"])

@router.post("/mcp-inspector/start")
def start_mcp_inspector(request: Request):
    return platform_config_service.start_mcp_inspector(request)

@router.post("/mcp-inspector/stop")
def stop_mcp_inspector():
    return platform_config_service.stop_mcp_inspector()

@router.get("/")
def platform_config_page(request: Request):
    return platform_config_service.platform_config_page(request)

@router.post("/cache/invalidate")
def invalidate_cache():
    return platform_config_service.invalidate_cache()

@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db)):
    return platform_config_service.list_platforms(db)

@router.post("/platforms")
def add_platform(payload: dict, db: Session = Depends(get_db)):
    return platform_config_service.add_platform(payload, db)

@router.put("/platforms/{platform_id}")
def update_platform(
    platform_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    return platform_config_service.update_platform(platform_id, payload, db)

@router.get("/workflows")
def list_workflows(
    platform: str = "", db: Session = Depends(get_db)
):
    return platform_config_service.list_workflows(platform, db)

@router.post("/workflows")
def create_workflow(payload: dict, db: Session = Depends(get_db)):
    return platform_config_service.create_workflow(payload, db)

@router.post("/workflows/{workflow_id}/test")
def test_workflow(workflow_id: int, payload: dict = {}, db: Session = Depends(get_db)):
    return platform_config_service.test_workflow(workflow_id, payload, db)

@router.put("/workflows/{workflow_id}/steps")
def update_workflow_steps(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    return platform_config_service.update_workflow_steps(workflow_id, payload, db)

@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    return platform_config_service.delete_workflow(workflow_id, db)

@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id: int, db: Session = Depends(get_db)):
    return platform_config_service.delete_platform(platform_id, db)

@router.put("/workflows/{workflow_id}/timing")
def update_workflow_timing(
    workflow_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    return platform_config_service.update_workflow_timing(workflow_id, payload, db)

@router.get("/selectors")
def list_selectors(
    platform: str = "", category: str = "",
    db: Session = Depends(get_db)
):
    return platform_config_service.list_selectors(platform, category, db)

@router.post("/selectors")
def add_selector(payload: dict, db: Session = Depends(get_db)):
    return platform_config_service.add_selector(payload, db)

@router.put("/selectors/{selector_id}")
def update_selector(
    selector_id: int, payload: dict,
    db: Session = Depends(get_db)
):
    return platform_config_service.update_selector(selector_id, payload, db)

@router.delete("/selectors/{selector_id}")
def delete_selector(
    selector_id: int, db: Session = Depends(get_db)
):
    return platform_config_service.delete_selector(selector_id, db)

@router.put("/selectors/reorder")
def reorder_selectors(
    payload: dict, db: Session = Depends(get_db)
):
    return platform_config_service.reorder_selectors(payload, db)

@router.get("/cta")
def list_cta(
    platform: str = "", db: Session = Depends(get_db)
):
    return platform_config_service.list_cta(platform, db)

@router.post("/cta")
def add_cta(payload: dict, db: Session = Depends(get_db)):
    return platform_config_service.add_cta(payload, db)

@router.delete("/cta/{cta_id}")
def delete_cta(cta_id: int, db: Session = Depends(get_db)):
    return platform_config_service.delete_cta(cta_id, db)

@router.put("/cta/reorder")
def reorder_cta(payload: dict, db: Session = Depends(get_db)):
    return platform_config_service.reorder_cta(payload, db)

@router.get("/presets")
def list_presets_api(platform: str = "facebook", job_type: str = "POST"):
    return platform_config_service.list_presets_api(platform, job_type)

@router.post("/presets/apply")
def apply_preset_api(payload: dict):
    return platform_config_service.apply_preset_api(payload)

@router.get("/runtime-config")
def runtime_config_api(platform: str = "facebook", job_type: str = "POST"):
    return platform_config_service.runtime_config_api(platform, job_type)

@router.get("/selector-health")
def selector_health_api():
    return platform_config_service.selector_health_api()

@router.get("/presets/preview-switch")
def preview_switch_api(
    from_preset: str = "", to_preset: str = "", mode: str = "cache",
    platform: str = "facebook", job_type: str = "POST"
):
    return platform_config_service.preview_switch_api(from_preset, to_preset, mode, platform, job_type)

@router.get("/overview-warnings")
def overview_warnings_api(
    platform: str = "facebook", job_type: str = "POST"
):
    return platform_config_service.overview_warnings_api(platform, job_type)

